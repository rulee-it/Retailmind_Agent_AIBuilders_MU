"""LLM-powered RouterAgent.

NOT keyword/regex: uses ChatOpenAI(temperature=0) with a Pydantic
structured-output schema. Six routes including MULTI for cross-domain.
"""
from __future__ import annotations

import os
from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core.prompts import ROUTER_SYSTEM


Route = Literal["INVENTORY", "PRICING", "REVIEWS", "CATALOG", "MULTI", "GENERAL"]
Specialist = Literal["InventoryAgent", "PricingAgent", "ReviewsAgent", "CatalogAgent"]


class RoutingDecision(BaseModel):
    """Structured router output."""

    route: Route = Field(description="One of INVENTORY/PRICING/REVIEWS/CATALOG/MULTI/GENERAL.")
    reason: str = Field(description="One short sentence explaining the choice.")
    suggested_specialists: list[Specialist] = Field(
        default_factory=list,
        description="Required (≥2 items) ONLY when route == MULTI. Empty otherwise.",
    )


def _router_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0,
        max_tokens=250,
    )


def route(query: str, history: list[BaseMessage] | None = None, category_filter: str | None = None) -> RoutingDecision:
    llm = _router_llm().with_structured_output(RoutingDecision)
    ctx = []
    if category_filter:
        ctx.append(f"[Active category filter: {category_filter}]")
    if history:
        # Compact last 4 turns into router context so follow-ups resolve.
        recent = history[-8:]
        for m in recent:
            who = "User" if m.__class__.__name__ == "HumanMessage" else "Assistant"
            ctx.append(f"{who}: {m.content[:240]}")
    context_block = ("\n\nConversation context:\n" + "\n".join(ctx)) if ctx else ""

    messages = [
        SystemMessage(content=ROUTER_SYSTEM + context_block),
        HumanMessage(content=f"Classify this query:\n{query}"),
    ]
    return llm.invoke(messages)  # type: ignore[return-value]
