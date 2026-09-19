"""Emergency green-corridor utilities for SUMO ambulance priority.

The controller does not force every signal to green. Instead, it predicts the
ambulance ETA at each upcoming intersection, builds a small green window around
that ETA, and injects an emergency-delay penalty into the traffic-state record
so the existing QUBO objective naturally prefers plans that reduce emergency
travel time while still accounting for normal traffic delay, queues, fuel, and
CO2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional


@dataclass
class AmbulanceState:
    """Representation of a single emergency vehicle."""

    ambulance_id: str
    route: List[str]
    start_point: str
    destination: str
    current_signal: Optional[str] = None
    arrival_times: Dict[str, float] = field(default_factory=dict)
    active: bool = True


class EmergencyGreenCorridorController:
    """Create and track green windows for an ambulance through a signal corridor."""

    def __init__(
        self,
        tls_ids: Optional[Iterable[str]] = None,
        emergency_vehicle_type: str = "ambulance",
        green_lead_seconds: float = 8.0,
        green_tail_seconds: float = 10.0,
        max_window_seconds: float = 28.0,
    ):
        self.tls_ids = list(tls_ids or [])
        self.emergency_vehicle_type = emergency_vehicle_type
        self.green_lead_seconds = green_lead_seconds
        self.green_tail_seconds = green_tail_seconds
        self.max_window_seconds = max_window_seconds
        self.ambulance: Optional[AmbulanceState] = None
        self._signal_windows: Dict[str, Dict[str, float]] = {}

    def create_ambulance(
        self,
        ambulance_id: str,
        start_point: str,
        destination: str,
        route: Optional[Iterable[str]] = None,
    ) -> AmbulanceState:
        """Create a special ambulance vehicle and define its movement corridor."""
        self.ambulance = AmbulanceState(
            ambulance_id=ambulance_id,
            route=list(route or []),
            start_point=start_point,
            destination=destination,
        )
        return self.ambulance

    def update_arrivals(self, arrival_times: Mapping[str, float]) -> Dict[str, Dict[str, float]]:
        """Register predicted arrival times at intersections as green-window inputs."""
        if self.ambulance is None:
            self.ambulance = AmbulanceState(
                ambulance_id="AMB",
                route=[],
                start_point="",
                destination="",
            )

        self.ambulance.arrival_times = {
            str(signal_id): float(eta)
            for signal_id, eta in dict(arrival_times).items()
            if eta is not None
        }
        return self.generate_green_windows(
            ambulance_id=self.ambulance.ambulance_id,
            arrival_times=self.ambulance.arrival_times,
            traffic_state={},
        )

    def generate_green_windows(
        self,
        ambulance_id: str,
        arrival_times: Mapping[str, float],
        traffic_state: Optional[Mapping[str, Mapping[str, float]]] = None,
    ) -> Dict[str, Dict[str, float]]:
        """Build emergency green windows around the ambulance ETA at each signal.

        The green window is centered on the ETA and is reduced if the approach is
        already heavily congested. This gives the optimizer an appropriate
        emergency priority window instead of a blanket override.
        """
        traffic_state = traffic_state or {}
        windows: Dict[str, Dict[str, float]] = {}

        for signal_id, eta in sorted(arrival_times.items(), key=lambda item: item[1]):
            if eta is None or eta < 0:
                continue
            approach = traffic_state.get(signal_id, {})
            queue = float(approach.get("queue", 0.0))
            flow = float(approach.get("flow", 0.0))
            capacity = max(float(approach.get("capacity", 1.0)), 1.0)

            congestion_factor = min(1.0, queue / capacity)
            lead = min(self.green_lead_seconds, max(4.0, 12.0 - eta * 0.12))
            tail = min(self.green_tail_seconds, max(5.0, 12.0 - congestion_factor * 6.0 - flow / 12.0))
            start = max(0.0, eta - lead)
            end = eta + tail
            duration = max(0.0, end - start)

            windows[signal_id] = {
                "ambulance_id": ambulance_id,
                "start_time": round(start, 2),
                "end_time": round(end, 2),
                "duration_seconds": round(duration, 2),
                "target_arrival_s": float(eta),
                "priority_score": round(max(0.0, 1.0 - eta / 90.0) + (1.0 - congestion_factor) * 0.5, 3),
            }

        self._signal_windows = windows
        if self.ambulance is not None:
            self.ambulance.current_signal = next(iter(sorted(windows.keys())), None)
            self.ambulance.arrival_times = {
                signal_id: float(eta)
                for signal_id, eta in arrival_times.items()
            }
        return windows

    def attach_emergency_priority(
        self,
        traffic_state: Dict[str, Dict[str, float]],
        arrival_times: Optional[Mapping[str, float]] = None,
    ) -> Dict[str, Dict[str, float]]:
        """Inject emergency-delay penalties into the state used by the QUBO objective."""
        arrival_times = arrival_times or (self.ambulance.arrival_times if self.ambulance else {})
        state = {signal_id: dict(values) for signal_id, values in traffic_state.items()}
        for signal_id, eta in sorted(arrival_times.items(), key=lambda item: item[1]):
            if eta is None or eta < 0:
                continue
            signal_state = state.setdefault(signal_id, {})
            window = self._signal_windows.get(signal_id)
            if window is None:
                window = self.generate_green_windows(
                    ambulance_id=self.ambulance.ambulance_id if self.ambulance else "AMB",
                    arrival_times={signal_id: eta},
                    traffic_state={signal_id: signal_state},
                ).get(signal_id, {})

            emergency_penalty = max(0.0, 30.0 - eta) * 0.6
            signal_state["emergency_delay"] = max(
                float(signal_state.get("emergency_delay", 0.0)),
                float(emergency_penalty),
            )
            signal_state["green_window"] = window
            signal_state["priority_signal"] = signal_id in self._signal_windows
        return state

    def _is_emergency_window_for_signal(self, signal_id: str, now: float) -> bool:
        window = self._signal_windows.get(signal_id)
        if not window:
            return False
        return window["start_time"] <= now <= window["end_time"]

    def release_signal(self, signal_id: str) -> None:
        """Allow the signal to return to the standard adaptive optimizer."""
        self._signal_windows.pop(signal_id, None)

    def disable_emergency_mode(self) -> None:
        """Clear the ambulance state and release all green windows."""
        self._signal_windows.clear()
        if self.ambulance is not None:
            self.ambulance.active = False
            self.ambulance.arrival_times.clear()
            self.ambulance.current_signal = None

    def is_emergency_active(self) -> bool:
        return self.ambulance is not None and self.ambulance.active and bool(self._signal_windows)


if __name__ == "__main__":
    controller = EmergencyGreenCorridorController(tls_ids=["C", "I1", "I2", "I3", "I4"])
    example = controller.generate_green_windows(
        ambulance_id="AMB_1",
        arrival_times={"I1": 12.0, "I2": 27.0, "I3": 43.0, "I4": 59.0},
        traffic_state={
            "I1": {"queue": 12, "flow": 18, "capacity": 60},
            "I2": {"queue": 8, "flow": 20, "capacity": 60},
            "I3": {"queue": 15, "flow": 22, "capacity": 60},
            "I4": {"queue": 6, "flow": 14, "capacity": 60},
        },
    )
    print(example)
