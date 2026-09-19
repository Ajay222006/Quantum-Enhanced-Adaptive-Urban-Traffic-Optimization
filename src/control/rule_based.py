"""
Baseline 2: Rule-based adaptive control.

Logic (per intersection, every CONTROL_INTERVAL seconds):

  1. read the queue of the phase that is currently green (q_cur)
     and the queue of the competing phase (q_other)
  2. share = q_cur / (q_cur + q_other)
  3. green = MIN_GREEN + share * (MAX_GREEN - MIN_GREEN)
  4. gap-out : q_cur == 0 and q_other > 0  -> green = MIN_GREEN (switch early)
  5. spillback: the downstream road is jammed -> do not extend green

Example (MIN=10, MAX=60):
    q_cur = 24, q_other = 6  ->  share = 0.80  ->  green = 10 + 0.8*50 = 50 s
    q_cur = 3,  q_other = 21 ->  share = 0.125 ->  green = 10 + 0.125*50 = 16 s
"""

import time
from typing import Dict

from config import settings
from src.control.base_controller import BaseController


class RuleBasedController(BaseController):
    name = "rule_based"

    def __init__(self, network):
        super().__init__(network)
        self._reasons = {}

    def _downstream_jam(self, iid: str, phase: str) -> bool:
        """True if roads leaving this intersection are almost full."""
        inter = self.net.intersections[iid]
        outs = [self.net.roads[r] for r in inter.outgoing]
        return any(r.density > 0.9 or r.is_blocked for r in outs) if outs else False

    def decide(self, states: Dict, now: float) -> Dict[str, float]:
        t0 = time.perf_counter()
        decisions = {}

        for iid, st in states.items():
            cur = st.signal_phase
            others = [p for p in st.phase_names if p != cur]
            q_cur = st.queue_of(cur)
            q_other = sum(st.queue_of(p) for p in others)
            total = q_cur + q_other

            if total == 0:
                green, reason = settings.MIN_GREEN, "no demand -> minimum green"
            elif q_cur == 0 and q_other > 0:
                green, reason = settings.MIN_GREEN, "green phase empty -> switch early (gap-out)"
            else:
                share = q_cur / total
                green = settings.MIN_GREEN + share * (settings.MAX_GREEN - settings.MIN_GREEN)
                reason = (f"queue {q_cur} vs {q_other} -> share {share:.2f} "
                          f"-> green {green:.0f}s")

            if self._downstream_jam(iid, cur) and green > settings.MIN_GREEN:
                green = max(settings.MIN_GREEN, green * 0.6)
                reason += " | downstream jammed -> green reduced"

            green = max(settings.MIN_GREEN, min(settings.MAX_GREEN, green))
            decisions[iid] = green
            self._reasons[iid] = reason
            self.log(now, iid, green, reason)

        self.last_runtime_ms = (time.perf_counter() - t0) * 1000
        return decisions

    def explain(self, iid: str) -> str:
        return self._reasons.get(iid, "no decision yet")
