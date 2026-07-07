"""SupervisorAgent — synthesises MULTI queries and the Daily Briefing.

NO tools of its own. It calls specialist agents as sub-agents and stitches
their structured outputs into one prioritised answer.
"""
from __future__ import annotations

import asyncio
import os
import time

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.prompts import BRIEFING_SYSTEM, SUPERVISOR_SYSTEM
from core.trace import AgentTrace

from . import catalog_agent, inventory_agent, pricing_agent, reviews_agent

NAME = "Supervisor"

SPECIALIST_REGISTRY = {
    "InventoryAgent": inventory_agent,
    "PricingAgent": pricing_agent,
    "ReviewsAgent": reviews_agent,
    "CatalogAgent": catalog_agent,
}


def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL_SUPERVISOR", "gpt-4o"),
        temperature=0.2,
        max_tokens=1200,
    )


def _focus_prompts(query: str, specialists: list[str]) -> dict[str, str]:
    """Generate focused sub-questions per specialist via a single small LLM call."""
    sys = SystemMessage(
        content=(
            "You are a routing assistant. Given a user question and a list of specialist agents, "
            "produce ONE focused sub-question per specialist that targets ONLY that specialist's domain. "
            "Return JSON like {\"InventoryAgent\": \"...\", \"PricingAgent\": \"...\"}. "
            "Inventory = stock/restock. Pricing = margin/price. Reviews = customer feedback. Catalog = search/aggregates."
        )
    )
    usr = HumanMessage(
        content=f"User question: {query}\nSpecialists: {', '.join(specialists)}\nReturn JSON only."
    )
    raw = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0, max_tokens=400).invoke([sys, usr]).content
    import json
    try:
        s = raw if isinstance(raw, str) else str(raw)
        return json.loads(s[s.index("{") : s.rindex("}") + 1])
    except Exception:
        return {sp: query for sp in specialists}


async def _run_specialist_async(name: str, sub_q: str, history: list[BaseMessage]) -> tuple[str, str, int]:
    mod = SPECIALIST_REGISTRY[name]
    t0 = time.time()
    out = await asyncio.to_thread(mod.run, sub_q, history)
    return name, out, int((time.time() - t0) * 1000)


def synthesize(
    query: str,
    suggested_specialists: list[str],
    history: list[BaseMessage],
    trace: AgentTrace,
) -> str:
    if not suggested_specialists:
        suggested_specialists = ["InventoryAgent", "ReviewsAgent", "PricingAgent"]
    suggested_specialists = list(dict.fromkeys(suggested_specialists))  # dedupe, keep order

    sub_qs = _focus_prompts(query, suggested_specialists)

    async def _gather():
        return await asyncio.gather(
            *[_run_specialist_async(name, sub_qs.get(name, query), history) for name in suggested_specialists]
        )

    results = asyncio.run(_gather())
    bundle_lines = []
    for name, out, ms in results:
        trace.specialists_called.append(name)
        trace.timings_ms[name] = ms
        bundle_lines.append(f"### [{name}]\n{out}")
    bundle = "\n\n".join(bundle_lines)

    sys = SystemMessage(content=SUPERVISOR_SYSTEM)
    usr = HumanMessage(
        content=(
            f"User question:\n{query}\n\n"
            f"Specialist outputs (use these — do not invent numbers):\n{bundle}"
        )
    )
    msg: AIMessage = _llm().invoke([sys, usr])
    return msg.content if isinstance(msg.content, str) else str(msg.content)


def daily_briefing(trace: AgentTrace) -> str:
    """Run all 4 specialists with focused briefing sub-questions, then synthesise."""
    sub_qs = {
        "InventoryAgent": "Run generate_restock_alert(threshold_days=7). List the top 3 most critically low-stock products with days_to_stockout and revenue_at_risk.",
        "ReviewsAgent": "Identify the worst-rated product in the catalog (lowest avg_rating among products with at least 1 review) and run get_review_insights on it. Give a one-line summary of why customers dislike it.",
        "PricingAgent": "Find the product with the lowest gross margin in the catalog and run get_pricing_analysis on it. If margin < 25%, suggest one action.",
        "CatalogAgent": 'Run get_category_performance("All") and report total_skus, critical_stock_count, avg_margin_percent and avg_rating.',
    }

    async def _gather():
        return await asyncio.gather(
            *[_run_specialist_async(name, q, []) for name, q in sub_qs.items()]
        )

    # Hint the inventory and pricing agents about which SKU to focus on.
    from tools._data import products_df

    df = products_df()
    worst_rated = df[df["review_count"] > 0].sort_values("avg_rating").head(1)
    margins = ((df["price"] - df["cost"]) / df["price"] * 100.0)
    lowest_margin_pid = df.loc[margins.idxmin(), "product_id"]
    if not worst_rated.empty:
        sub_qs["ReviewsAgent"] = (
            f"Run get_review_insights('{worst_rated.iloc[0]['product_id']}') and give a one-line summary "
            "of why customers dislike this product."
        )
    sub_qs["PricingAgent"] = (
        f"Run get_pricing_analysis('{lowest_margin_pid}') (this product has the lowest margin in the catalog). "
        "If margin < 25%, suggest one action."
    )

    results = asyncio.run(_gather())
    bundle_lines = []
    for name, out, ms in results:
        trace.specialists_called.append(name)
        trace.timings_ms[name] = ms
        bundle_lines.append(f"### [{name}]\n{out}")
    bundle = "\n\n".join(bundle_lines)

    sys = SystemMessage(content=BRIEFING_SYSTEM)
    usr = HumanMessage(content=f"Specialist reports:\n{bundle}")
    msg: AIMessage = _llm().invoke([sys, usr])
    return msg.content if isinstance(msg.content, str) else str(msg.content)
