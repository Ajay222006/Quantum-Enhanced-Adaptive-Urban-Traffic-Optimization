"""
Traffic State Estimator (Phase 4).

Turns raw simulator data into the compact per-intersection state that every
controller consumes:

    I00:
      NS -> queue=12  density=0.31  flow=18 veh/min
      EW -> queue=4   density=0.11  flow=9  veh/min
      signal = GREEN(NS), elapsed 14s

IMPORTANT: this dict is the *single input contract* for controllers.
The fixed-time, rule-based, classical-optimizer and QAOA controllers all
read the same structure - so swapping the brain never touches the simulator.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ApproachState:
    road_id: str
    queue: int = 0
    density: float = 0.0
    occupancy: int = 0
    capacity: int = 0
    flow_vpm: float = 0.0            # vehicles per minute crossing the stop line
    capacity_factor: float = 1.0
    blocked: bool = False


@dataclass
class IntersectionState:
    id: str
    phase_names: List[str] = field(default_factory=list)
    approaches: Dict[str, List[ApproachState]] = field(default_factory=dict)  # phase -> approaches
    signal_phase: str = ""
    signal_state: str = ""
    elapsed: float = 0.0
    green_duration: float = 0.0
    preempted: bool = False

    # ----- aggregates the controllers/optimizer use -----
    def queue_of(self, phase: str) -> int:
        return sum(a.queue for a in self.approaches.get(phase, []))

    def density_of(self, phase: str) -> float:
        aps = self.approaches.get(phase, [])
        return max([a.density for a in aps], default=0.0)

    def flow_of(self, phase: str) -> float:
        return sum(a.flow_vpm for a in self.approaches.get(phase, []))

    @property
    def total_queue(self) -> int:
        return sum(self.queue_of(p) for p in self.phase_names)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "signal": f"{self.signal_state}({self.signal_phase})",
            "elapsed": round(self.elapsed, 1),
            "green_duration": self.green_duration,
            "queues": {p: self.queue_of(p) for p in self.phase_names},
            "density": {p: round(self.density_of(p), 2) for p in self.phase_names},
            "flow_vpm": {p: round(self.flow_of(p), 1) for p in self.phase_names},
        }


class StateEstimator:
    def __init__(self, network):
        self.net = network
        self._prev_counts: Dict[str, int] = {r: 0 for r in network.roads}
        self._prev_time: float = 0.0

    def estimate(self, now: float, discharge_counts: Dict[str, int]) -> Dict[str, IntersectionState]:
        window = max(now - self._prev_time, 1e-6)
        states = {}
        for iid, inter in self.net.intersections.items():
            st = IntersectionState(
                id=iid,
                phase_names=[p.name for p in inter.signal.phases],
                signal_phase=inter.signal.current_phase.name,
                signal_state=inter.signal.state,
                elapsed=inter.signal.timer,
                green_duration=inter.signal.green_duration,
                preempted=inter.signal.status()["preempted"],
            )
            for ph in inter.signal.phases:
                lst = []
                for rid in ph.approaches:
                    road = self.net.roads[rid]
                    crossed = discharge_counts.get(rid, 0) - self._prev_counts.get(rid, 0)
                    lst.append(ApproachState(
                        road_id=rid,
                        queue=road.queue_length,
                        density=road.density,
                        occupancy=road.occupancy,
                        capacity=road.storage_capacity,
                        flow_vpm=crossed * 60.0 / window,
                        capacity_factor=road.capacity_factor,
                        blocked=road.is_blocked,
                    ))
                st.approaches[ph.name] = lst
            states[iid] = st

        self._prev_counts = dict(discharge_counts)
        self._prev_time = now
        return states
