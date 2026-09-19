"""
Baseline 1: Fixed-time control.

Every intersection runs the same green duration forever, exactly like an
old-style timer signal. It ignores queues completely - which is precisely
why it is the reference point for the comparison table.
"""

import time
from typing import Dict

from config import settings
from src.control.base_controller import BaseController


class FixedTimeController(BaseController):
    name = "fixed_time"

    def __init__(self, network, green: float = settings.DEFAULT_GREEN):
        super().__init__(network)
        self.green = green

    def decide(self, states: Dict, now: float) -> Dict[str, float]:
        t0 = time.perf_counter()
        decisions = {iid: self.green for iid in self.net.intersections}
        self.last_runtime_ms = (time.perf_counter() - t0) * 1000
        return decisions

    def explain(self, iid: str) -> str:
        return f"fixed plan: every phase gets {self.green}s regardless of traffic"
