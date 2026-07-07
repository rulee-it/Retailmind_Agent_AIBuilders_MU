"""ReviewsAgent — scoped to reviews tools ONLY."""
from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI

from core.prompts import REVIEWS_SYSTEM
from tools.reviews_tools import REVIEWS_TOOLS


def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.2,
        max_tokens=700,
    )


def run(query: str, history: list[BaseMessage] | None = None) -> str:
    agent = create_agent(model=_llm(), tools=REVIEWS_TOOLS, system_prompt=REVIEWS_SYSTEM)
    msgs = list(history or []) + [HumanMessage(content=query)]
    result = agent.invoke({"messages": msgs})
    last = result["messages"][-1]
    return getattr(last, "content", str(last))


NAME = "ReviewsAgent"
