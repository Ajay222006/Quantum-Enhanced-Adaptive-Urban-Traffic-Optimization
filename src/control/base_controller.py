"""
Controller interface.

EVERY controller - fixed-time, rule-based, classical optimizer, and later the
QAOA / hybrid engine - implements the same two methods:

    decide(states, now) -> {intersection_id: green_seconds}

That single contract is the plug-in point for the quantum engine:
when you add QAOA, you only write a new subclass here. The simulator,
metrics, events, emergency logic and dashboard stay untouched.
"""

from abc import ABC, abstractmethod
from typing import Dict


class BaseController(ABC):
    name = "base"

    def __init__(self, network):
        self.net = network
        self.decision_log = []          # (time, intersection, green) - for explainability
        self.last_runtime_ms = 0.0      # compared against QAOA runtime later

    @abstractmethod
    def decide(self, states: Dict, now: float) -> Dict[str, float]:
        """Return the desired green duration for each intersection."""
        raise NotImplementedError

    def explain(self, iid: str) -> str:
        """Human-readable reason for the last decision (dashboard Phase 14)."""
        return "no explanation available"

    def log(self, now, iid, green, reason=""):
        self.decision_log.append({"t": now, "intersection": iid,
                                  "green": round(green, 1), "reason": reason})
