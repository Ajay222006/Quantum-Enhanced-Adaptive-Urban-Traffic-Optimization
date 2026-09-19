"""
Vehicle = one agent travelling along a fixed route of road ids.
Each vehicle carries its own statistics, which is what the
waiting-time / fuel / CO2 metrics are computed from.
"""

import itertools
from dataclasses import dataclass, field
from typing import List

_counter = itertools.count(1)


@dataclass
class Vehicle:
    route: List[str]
    depart_time: float
    vtype: str = "car"
    pcu: float = 1.0                 # passenger car units (bus = 2.5)
    fuel_factor: float = 1.0
    is_emergency: bool = False

    id: int = field(default_factory=lambda: next(_counter))
    route_index: int = 0
    waiting_time: float = 0.0        # seconds spent stopped in a queue
    travel_time: float = 0.0
    distance_m: float = 0.0
    stops: int = 0
    fuel_l: float = 0.0
    finish_time: float = None

    # ---------- route helpers ----------
    @property
    def current_road(self) -> str:
        return self.route[self.route_index]

    @property
    def next_road(self):
        i = self.route_index + 1
        return self.route[i] if i < len(self.route) else None

    def advance(self):
        self.route_index += 1

    @property
    def co2_g(self) -> float:
        from config import settings
        return self.fuel_l * settings.CO2_G_PER_LITRE

    def __repr__(self):
        tag = "AMB" if self.is_emergency else self.vtype
        return f"<V{self.id} {tag} road={self.current_road} wait={self.waiting_time:.0f}s>"
