"""Transparent SUMO event detection and accident/closure handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

try:
    import traci
except ImportError:
    traci = None


@dataclass
class DetectedEvent:
    time: float
    kind: str
    intersection: str
    direction: str
    queue: float
    density: float
    flow: float
    message: str


class SumoEventDetector:
    """Detect queue jumps, density increases, flow drops, and recovery."""

    def __init__(self, queue_jump: float = 8.0, density_jump: float = 0.15,
                 flow_drop_ratio: float = 0.40, high_density: float = 0.75,
                 recovery_density: float = 0.55, recovery_flow_ratio: float = 0.85,
                 minimum_flow: float = 10.0, minimum_flow_drop: float = 5.0):
        self.queue_jump = queue_jump
        self.density_jump = density_jump
        self.flow_drop_ratio = flow_drop_ratio
        self.high_density = high_density
        self.recovery_density = recovery_density
        self.recovery_flow_ratio = recovery_flow_ratio
        self.minimum_flow = minimum_flow
        self.minimum_flow_drop = minimum_flow_drop
        self.previous: Dict[Tuple[str, str], dict] = {}
        self.abnormal: Dict[Tuple[str, str], str] = {}
        self.events: List[DetectedEvent] = []

    @staticmethod
    def _number(record: dict, key: str) -> float:
        try:
            return float(record.get(key, 0.0))
        except (TypeError, ValueError):
            return 0.0

    def check(self, now: float, state: dict) -> List[DetectedEvent]:
        detected = []
        for intersection_id, directions in state.items():
            for direction, record in directions.items():
                key = (intersection_id, direction)
                queue = self._number(record, "queue")
                density = self._number(record, "density")
                flow = self._number(record, "flow")
                previous = self.previous.get(key)
                kind = None
                reason = None

                if previous:
                    queue_jump = queue - previous["queue"]
                    density_jump = density - previous["density"]
                    flow_drop = (
                        previous["flow"] >= self.minimum_flow
                        and previous["flow"] - flow >= self.minimum_flow_drop
                        and (previous["flow"] - flow) / previous["flow"] >= self.flow_drop_ratio
                    )
                    if queue_jump >= self.queue_jump or density_jump >= self.density_jump:
                        kind = "congestion"
                        reason = f"queue +{queue_jump:.1f}, density +{density_jump:.2f}"
                    elif flow_drop:
                        kind = "flow_drop"
                        reason = f"flow {previous['flow']:.1f}->{flow:.1f}"

                if density >= self.high_density and kind is None:
                    kind = "congestion"
                    reason = f"density {density:.2f}"

                if kind:
                    event = DetectedEvent(
                        now, kind, intersection_id, direction, queue, density, flow,
                        f"[{now:.0f}s] {kind.upper()} at {intersection_id}/{direction}: {reason}",
                    )
                    detected.append(event)
                    self.abnormal[key] = kind
                elif key in self.abnormal and previous:
                    recovered = (
                        density <= self.recovery_density
                        and (previous["flow"] <= 0 or flow >= previous["flow"] * self.recovery_flow_ratio)
                    )
                    if recovered:
                        event = DetectedEvent(
                            now, "recovery", intersection_id, direction, queue, density, flow,
                            f"[{now:.0f}s] RECOVERY at {intersection_id}/{direction}: normal operation restored",
                        )
                        detected.append(event)
                        del self.abnormal[key]

                self.previous[key] = {"queue": queue, "density": density, "flow": flow}

        self.events.extend(detected)
        return detected


class SumoIncidentManager:
    """Apply temporary SUMO road capacity changes and restore them."""

    def __init__(self, edge_id: str, kind: str = "accident", start: float = 120.0,
                 duration: float = 120.0, capacity_factor: float = 0.25):
        if kind not in {"accident", "road_closure"}:
            raise ValueError("kind must be accident or road_closure")
        if not 0.0 < capacity_factor <= 1.0:
            raise ValueError("capacity_factor must be between 0 and 1")
        self.edge_id = edge_id
        self.kind = kind
        self.start = start
        self.duration = duration
        self.capacity_factor = capacity_factor
        self.active = False
        self.cleared = False
        self.original_speeds = {}
        self.log: List[str] = []

    def _set_capacity(self, factor: float):
        if traci is None:
            raise RuntimeError("TraCI is required for SUMO incident handling")
        lane_ids = [
            f"{self.edge_id}_{index}"
            for index in range(traci.edge.getLaneNumber(self.edge_id))
        ]
        for lane_id in lane_ids:
            if lane_id not in self.original_speeds:
                self.original_speeds[lane_id] = traci.lane.getMaxSpeed(lane_id)
            traci.lane.setMaxSpeed(lane_id, max(0.1, self.original_speeds[lane_id] * factor))

    def update(self, now: float) -> List[str]:
        messages = []
        if not self.active and not self.cleared and now >= self.start:
            self._set_capacity(self.capacity_factor)
            self.active = True
            message = f"[{now:.0f}s] {self.kind.upper()} injected on {self.edge_id}: capacity {self.capacity_factor:.0%}"
            self.log.append(message)
            messages.append(message)
        elif self.active and now >= self.start + self.duration:
            for lane_id, speed in self.original_speeds.items():
                traci.lane.setMaxSpeed(lane_id, speed)
            self.active = False
            self.cleared = True
            message = f"[{now:.0f}s] INCIDENT CLEARED on {self.edge_id}: capacity restored"
            self.log.append(message)
            messages.append(message)
        return messages
