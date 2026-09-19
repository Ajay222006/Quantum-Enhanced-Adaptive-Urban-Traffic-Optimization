"""
Traffic signal = a finite state machine.

    GREEN(phase p) --> YELLOW --> ALL_RED --> GREEN(phase p+1) --> ...

The CONTROLLER only decides *how long* a green lasts (and, for emergencies,
*which* phase should come next). All safety rules (min green, max green,
yellow, clearance) are enforced here so no controller - classical, rule-based
or quantum - can ever produce an unsafe signal plan.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from config import settings

GREEN = "GREEN"
YELLOW = "YELLOW"
ALL_RED = "ALL_RED"


@dataclass
class Phase:
    """One signal phase = the set of approaches that get green together."""
    name: str                    # "NS" or "EW"
    approaches: List[str] = field(default_factory=list)   # road ids


class TrafficSignal:
    def __init__(self, intersection_id: str, phases: List[Phase]):
        self.intersection_id = intersection_id
        self.phases = phases
        self.phase_index = 0
        self.state = GREEN
        self.timer = 0.0
        self.green_duration = settings.DEFAULT_GREEN
        self._pending_green: Optional[float] = None
        self._preempt_phase: Optional[int] = None   # emergency override
        self.cycles_completed = 0
        self.switch_log = []                        # (time, phase, duration)

    # ---------------- queries ----------------
    @property
    def current_phase(self) -> Phase:
        return self.phases[self.phase_index]

    def green_approaches(self) -> List[str]:
        """Road ids that may discharge right now."""
        return self.current_phase.approaches if self.state == GREEN else []

    def phase_index_of(self, road_id: str) -> Optional[int]:
        for i, ph in enumerate(self.phases):
            if road_id in ph.approaches:
                return i
        return None

    def status(self) -> dict:
        return {
            "intersection": self.intersection_id,
            "phase": self.current_phase.name,
            "state": self.state,
            "elapsed": round(self.timer, 1),
            "green_duration": self.green_duration,
            "preempted": self._preempt_phase is not None,
        }

    # ---------------- control interface ----------------
    def set_green_duration(self, seconds: float):
        """Called by any controller. Clamped to the legal window."""
        seconds = max(settings.MIN_GREEN, min(settings.MAX_GREEN, float(seconds)))
        if self.state == GREEN and self._preempt_phase is None:
            # extend/shorten the running green, but never below elapsed+min slack
            self.green_duration = max(seconds, min(self.timer, settings.MAX_GREEN))
        else:
            self._pending_green = seconds

    def request_phase(self, phase_index: int):
        """Emergency preemption: hold this phase green until released."""
        self._preempt_phase = phase_index

    def release_preemption(self):
        self._preempt_phase = None
        self.timer = min(self.timer, self.green_duration)

    # ---------------- FSM ----------------
    def step(self, dt: float, now: float):
        self.timer += dt

        if self.state == GREEN:
            if self._preempt_phase is not None:
                if self._preempt_phase == self.phase_index:
                    return                                  # hold green
                if self.timer >= settings.MIN_GREEN:
                    self._start(YELLOW, now)
            elif self.timer >= self.green_duration:
                self._start(YELLOW, now)

        elif self.state == YELLOW:
            if self.timer >= settings.YELLOW_TIME:
                self._start(ALL_RED, now)

        elif self.state == ALL_RED:
            if self.timer >= settings.ALL_RED_TIME:
                self._advance_phase(now)

    def _start(self, state: str, now: float):
        if self.state == GREEN:
            self.switch_log.append((now, self.current_phase.name, round(self.timer, 1)))
        self.state = state
        self.timer = 0.0

    def _advance_phase(self, now: float):
        if self._preempt_phase is not None:
            self.phase_index = self._preempt_phase
        else:
            self.phase_index = (self.phase_index + 1) % len(self.phases)
            if self.phase_index == 0:
                self.cycles_completed += 1
        if self._pending_green is not None:
            self.green_duration = self._pending_green
            self._pending_green = None
        self.state = GREEN
        self.timer = 0.0
