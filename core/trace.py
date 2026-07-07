"""Agent trace — captured per /chat call so the frontend can show what
happened under the hood (router decision + which specialists ran)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentTrace:
    query: str = ""
    route: str = ""
    reason: str = ""
    specialists_called: list[str] = field(default_factory=list)
    timings_ms: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "route": self.route,
            "reason": self.reason,
            "specialists_called": list(self.specialists_called),
            "timings_ms": dict(self.timings_ms),
        }
