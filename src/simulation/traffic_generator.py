"""
Generates vehicles at the entry roads (Phase 2: the digital twin's demand).

Arrivals follow a Poisson process: for each entry road and each 1-second
tick, a vehicle appears with probability (demand_vph / 3600).
Demand can be scaled per road at runtime -> that is how the
"sudden congestion" event is injected.
"""

import random
from typing import Dict, List

from config import settings
from src.simulation.vehicle import Vehicle


class TrafficGenerator:
    def __init__(self, network, profile: str = "normal", seed: int = settings.RANDOM_SEED):
        self.net = network
        self.rng = random.Random(seed)
        self.base_demand = settings.DEMAND_PROFILES[profile]
        self.profile = profile
        # demand multiplier per entry road (events change these)
        self.demand_scale: Dict[str, float] = {r: 1.0 for r in network.entry_roads}
        self.spawned = 0
        self.rejected = 0          # vehicles that could not enter (gridlock)

    # ---------- demand control (used by EventManager) ----------
    def scale_demand(self, road_id: str, factor: float):
        if road_id in self.demand_scale:
            self.demand_scale[road_id] = factor

    def scale_all(self, factor: float):
        for r in self.demand_scale:
            self.demand_scale[r] = factor

    # ---------- vehicle creation ----------
    def _pick_type(self):
        x, acc = self.rng.random(), 0.0
        for vtype, p, pcu, fuel in settings.VEHICLE_MIX:
            acc += p
            if x <= acc:
                return vtype, pcu, fuel
        return "car", 1.0, 1.0

    def _make_vehicle(self, entry_road: str, now: float):
        routes = self.net.routes_from(entry_road)
        if not routes:
            return None
        route = self.rng.choice(routes)
        vtype, pcu, fuel = self._pick_type()
        return Vehicle(route=list(route), depart_time=now,
                       vtype=vtype, pcu=pcu, fuel_factor=fuel)

    # ---------- main hook ----------
    def spawn(self, now: float, dt: float) -> List[Vehicle]:
        new = []
        for rid in self.net.entry_roads:
            vph = self.base_demand * self.demand_scale[rid]
            if self.rng.random() < (vph / 3600.0) * dt:
                road = self.net.roads[rid]
                if not road.has_space():
                    self.rejected += 1
                    continue
                v = self._make_vehicle(rid, now)
                if v:
                    new.append(v)
                    self.spawned += 1
        return new
