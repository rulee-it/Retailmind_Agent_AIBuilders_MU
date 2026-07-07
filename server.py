"""FastAPI bridge between the HTML/JS frontend and the LangChain multi-agent backend."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

load_dotenv(HERE / ".env")

from agents import catalog_agent, inventory_agent, pricing_agent, reviews_agent  # noqa: E402
from agents import supervisor  # noqa: E402
from agents.router import route  # noqa: E402
from core.memory import get_store  # noqa: E402
from core.trace import AgentTrace  # noqa: E402
from tools._data import CATEGORIES, products_df  # noqa: E402


SPECIALIST_RUN = {
    "INVENTORY": inventory_agent,
    "PRICING": pricing_agent,
    "REVIEWS": reviews_agent,
    "CATALOG": catalog_agent,
}
SPECIALIST_LABEL = {
    "INVENTORY": "InventoryAgent",
    "PRICING": "PricingAgent",
    "REVIEWS": "ReviewsAgent",
    "CATALOG": "CatalogAgent",
}


app = FastAPI(title="RetailMind v2 — Multi-Agent API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND_DIR = HERE / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# -----------------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------------
class ChatIn(BaseModel):
    session_id: str
    message: str
    category_filter: str | None = None


class ChatOut(BaseModel):
    response: str
    route: str
    reason: str
    specialists: list[str]


class ClearIn(BaseModel):
    session_id: str


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/categories")
def categories() -> dict:
    return {"categories": ["All Categories", *CATEGORIES]}


@app.get("/summary")
def summary() -> dict:
    df = products_df()
    safe_daily = df["avg_daily_sales"].replace(0, float("nan"))
    d2s = (df["stock_quantity"] / safe_daily).fillna(float("inf"))
    margins = ((df["price"] - df["cost"]) / df["price"] * 100.0)
    return {
        "total_skus": int(len(df)),
        "critical_stock_count": int((d2s < 7).sum()),
        "low_stock_count": int(((d2s >= 7) & (d2s <= 14)).sum()),
        "avg_margin_percent": round(float(margins.mean()), 2),
        "avg_rating": round(float(df["avg_rating"].mean()), 2),
    }


@app.get("/briefing")
def briefing(session_id: str) -> dict:
    store = get_store()
    sess = store.get(session_id)
    if sess.briefing is None:
        trace = AgentTrace(query="<daily-briefing>", route="BRIEFING", reason="App startup orchestration.")
        sess.briefing = supervisor.daily_briefing(trace)
        sess.last_trace = trace
    return {"briefing": sess.briefing}


@app.post("/clear")
def clear(body: ClearIn) -> dict:
    store = get_store()
    sess = store.reset(body.session_id)
    trace = AgentTrace(query="<daily-briefing>", route="BRIEFING", reason="Manual clear → fresh briefing.")
    sess.briefing = supervisor.daily_briefing(trace)
    sess.last_trace = trace
    return {"briefing": sess.briefing}


@app.get("/trace/{session_id}")
def get_trace(session_id: str) -> dict:
    sess = get_store().get(session_id)
    return sess.last_trace.to_dict() if sess.last_trace else {}


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(500, "OPENAI_API_KEY not set on the server. Edit retailmind_agent/.env.")

    store = get_store()
    sess = store.get(body.session_id)
    if body.category_filter:
        sess.category_filter = body.category_filter if body.category_filter != "All Categories" else None

    history = sess.memory.load_memory_variables()["chat_history"]
    user_msg = body.message.strip()
    if sess.category_filter:
        framed_msg = f"{user_msg}\n\n[Active category filter: {sess.category_filter}]"
    else:
        framed_msg = user_msg

    trace = AgentTrace(query=user_msg)

    # 1. Route
    t0 = time.time()
    decision = route(user_msg, history=history, category_filter=sess.category_filter)
    trace.route = decision.route
    trace.reason = decision.reason
    trace.timings_ms["RouterAgent"] = int((time.time() - t0) * 1000)

    # 2. Dispatch
    if decision.route == "MULTI":
        response = supervisor.synthesize(framed_msg, decision.suggested_specialists, history, trace)
    elif decision.route == "GENERAL":
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage

        sys = SystemMessage(
            content=(
                "You are RetailMind, a friendly product-intelligence assistant for StyleCraft. "
                "For greetings or meta questions, respond briefly. If the user asks for the daily briefing, "
                "tell them to scroll up — it is already pinned at the top of the chat. Keep replies under 80 words."
            )
        )
        msgs = [sys] + list(history) + [HumanMessage(content=framed_msg)]
        ai = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0.4, max_tokens=300).invoke(msgs)
        response = ai.content if isinstance(ai.content, str) else str(ai.content)
    else:
        mod = SPECIALIST_RUN[decision.route]
        t1 = time.time()
        response = mod.run(framed_msg, history)
        trace.specialists_called.append(SPECIALIST_LABEL[decision.route])
        trace.timings_ms[SPECIALIST_LABEL[decision.route]] = int((time.time() - t1) * 1000)

    sess.memory.save_context({"input": user_msg}, {"output": response})
    sess.last_trace = trace

    return ChatOut(
        response=response,
        route=decision.route,
        reason=decision.reason,
        specialists=trace.specialists_called,
    )
