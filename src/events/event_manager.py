"""
Dynamic event handling (Phase 8 / 11).

Two parts:
  * EventManager  - INJECTS scheduled events into the running simulation
  * EventDetector - DETECTS abnormal traffic from the state only
                    (the detector is what will trigger re-optimization
                     once the QUBO/QAOA engine is added)

Supported events
  congestion   : demand on an entry road (or all) is multiplied
  accident     : a road keeps only `capacity` fraction of its flow
  road_closure : a road is fully closed (capacity_factor = 0)
  clear        : restore a road / demand back to normal
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Event:
    time: float
    kind: str                    # congestion | accident | road_closure | clear
    target: str = "ALL"          # road id, or "ALL" for network-wide demand
    value: float = 1.0           # demand multiplier or remaining capacity
    duration: float = None       # auto-clear after N seconds (optional)
    applied: bool = False
    cleared: bool = False


class EventManager:
    def __init__(self, events: List[Event] = None):
        self.events: List[Event] = events or []
        self.active_log: List[str] = []

    def add(self, event: Event):
        self.events.append(event)

    # ---------------- main hook ----------------
    def update(self, now: float, network, generator):
        for ev in self.events:
            if not ev.applied and now >= ev.time:
                self._apply(ev, network, generator, now)
            elif ev.applied and not ev.cleared and ev.duration and now >= ev.time + ev.duration:
                self._clear(ev, network, generator, now)

    def _apply(self, ev: Event, network, generator, now):
        if ev.kind == "congestion":
            if ev.target == "ALL":
                generator.scale_all(ev.value)
            else:
                generator.scale_demand(ev.target, ev.value)
            msg = f"[{now:.0f}s] CONGESTION on {ev.target}: demand x{ev.value}"

        elif ev.kind == "accident":
            network.roads[ev.target].capacity_factor = ev.value
            msg = f"[{now:.0f}s] ACCIDENT on {ev.target}: capacity -> {ev.value*100:.0f}%"

        elif ev.kind == "road_closure":
            network.roads[ev.target].capacity_factor = 0.0
            msg = f"[{now:.0f}s] ROAD CLOSED: {ev.target}"

        elif ev.kind == "clear":
            self._restore(ev.target, network, generator)
            msg = f"[{now:.0f}s] CLEARED: {ev.target}"
        else:
            msg = f"[{now:.0f}s] unknown event {ev.kind}"

        ev.applied = True
        self.active_log.append(msg)

    def _clear(self, ev: Event, network, generator, now):
        self._restore(ev.target, network, generator)
        ev.cleared = True
        self.active_log.append(f"[{now:.0f}s] RESTORED: {ev.target} ({ev.kind} over)")

    @staticmethod
    def _restore(target, network, generator):
        if target == "ALL":
            generator.scale_all(1.0)
        elif target in network.roads:
            network.roads[target].capacity_factor = 1.0
            generator.scale_demand(target, 1.0)


class EventDetector:
    """Detects abnormal traffic WITHOUT being told - used to trigger re-optimization."""

    def __init__(self, queue_jump: int = 12, density_threshold: float = 0.75):
        self.queue_jump = queue_jump
        self.density_threshold = density_threshold
        self._prev_queue: Dict[str, int] = {}
        self.alerts: List[str] = []

    def check(self, now: float, states: Dict) -> List[str]:
        triggers = []
        for iid, st in states.items():
            q = st.total_queue
            prev = self._prev_queue.get(iid, q)
            if q - prev >= self.queue_jump:
                triggers.append(f"[{now:.0f}s] {iid}: queue jumped {prev} -> {q}")
            for ph in st.phase_names:
                if st.density_of(ph) >= self.density_threshold:
                    triggers.append(f"[{now:.0f}s] {iid}/{ph}: density {st.density_of(ph):.2f} (saturated)")
            self._prev_queue[iid] = q
        self.alerts.extend(triggers)
        return triggers
