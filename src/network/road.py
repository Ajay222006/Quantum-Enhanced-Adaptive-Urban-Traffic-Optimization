"""
Road = one directed link between two nodes.

Physical model (simple but realistic enough):

    [ transit zone ]  --->  [ queue at stop line ]  --->  intersection
     vehicles moving          vehicles stopped
"""

from collections import deque
from dataclasses import dataclass, field

from config import settings


@dataclass
class Road:
    id: str
    from_node: str
    to_node: str
    length_m: float = settings.INTERNAL_ROAD_LENGTH
    lanes: int = settings.DEFAULT_LANES
    speed_kmh: float = settings.DEFAULT_SPEED_KMH
    axis: str = "NS"                 # "NS" or "EW" -> decides signal phase
    is_entry: bool = False           # traffic is generated here
    is_exit: bool = False            # traffic leaves the network here

    # ---- dynamic state ----
    capacity_factor: float = 1.0     # 1.0 = normal, 0.2 = accident, 0.0 = closed
    queue: deque = field(default_factory=deque)      # Vehicle objects at stop line
    transit: list = field(default_factory=list)      # (Vehicle, arrival_tick)
    discharge_credit: float = 0.0    # fractional vehicles allowed to cross

    # ---------- static properties ----------
    @property
    def storage_capacity(self) -> int:
        """Max number of vehicles that physically fit on this road."""
        return max(1, int(self.lanes * self.length_m / settings.VEHICLE_LENGTH))

    @property
    def saturation_flow(self) -> float:
        """Vehicles per second that can cross the stop line on green."""
        return settings.SATURATION_FLOW_PER_LANE * self.lanes * self.capacity_factor

    @property
    def free_flow_speed_ms(self) -> float:
        base = self.speed_kmh / 3.6
        return max(1.0, base * max(self.capacity_factor, 0.1))

    # ---------- dynamic properties (these feed the optimizer later) ----------
    @property
    def queue_length(self) -> int:
        return len(self.queue)

    @property
    def occupancy(self) -> int:
        return len(self.queue) + len(self.transit)

    @property
    def density(self) -> float:
        """0.0 = empty road, 1.0 = completely jammed."""
        return min(1.0, self.occupancy / self.storage_capacity)

    @property
    def is_blocked(self) -> bool:
        return self.capacity_factor <= 0.01

    def has_space(self) -> bool:
        return (not self.is_blocked) and self.occupancy < self.storage_capacity

    def travel_time(self) -> float:
        return self.length_m / self.free_flow_speed_ms

    def reset_dynamic_state(self):
        self.capacity_factor = 1.0
        self.queue.clear()
        self.transit.clear()
        self.discharge_credit = 0.0

    def __repr__(self):
        return f"<Road {self.id} q={self.queue_length} d={self.density:.2f}>"
