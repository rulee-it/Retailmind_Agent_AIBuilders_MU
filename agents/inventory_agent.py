"""InventoryAgent — scoped to inventory tools ONLY.

Specialist isolation: this file imports only tools.inventory_tools.
No cross-imports to pricing/reviews/catalog tools.
"""
from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI

from core.prompts import INVENTORY_SYSTEM
from tools.inventory_tools import INVENTORY_TOOLS


def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0,
        max_tokens=700,
    )


def run(query: str, history: list[BaseMessage] | None = None) -> str:
    agent = create_agent(model=_llm(), tools=INVENTORY_TOOLS, system_prompt=INVENTORY_SYSTEM)
    msgs = list(history or []) + [HumanMessage(content=query)]
    result = agent.invoke({"messages": msgs})
    last = result["messages"][-1]
    return getattr(last, "content", str(last))


NAME = "InventoryAgent"
