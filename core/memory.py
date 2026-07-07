"""Per-session conversational memory + session store.

Strategy: classic ConversationBufferMemory equivalent — keep every turn
verbatim as a list of BaseMessage objects. Sessions are short (typically
<15 turns) so token growth stays cheap and follow-ups like "and its
margin?" reference earlier turns verbatim.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .trace import AgentTrace


class BufferMemory:
    def __init__(self) -> None:
        self.messages: list[BaseMessage] = []

    def load_memory_variables(self, _: dict[str, Any] | None = None) -> dict[str, list[BaseMessage]]:
        return {"chat_history": list(self.messages)}

    def save_context(self, inputs: dict[str, Any], outputs: dict[str, Any]) -> None:
        self.messages.append(HumanMessage(content=inputs.get("input", "")))
        self.messages.append(AIMessage(content=outputs.get("output", "")))

    def clear(self) -> None:
        self.messages = []


@dataclass
class SessionState:
    memory: BufferMemory = field(default_factory=BufferMemory)
    briefing: str | None = None
    last_trace: AgentTrace | None = None
    category_filter: str | None = None


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState()
        return self._sessions[session_id]

    def reset(self, session_id: str) -> SessionState:
        self._sessions[session_id] = SessionState()
        return self._sessions[session_id]


_store = SessionStore()


def get_store() -> SessionStore:
    return _store
