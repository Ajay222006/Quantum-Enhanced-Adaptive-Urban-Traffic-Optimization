"""
Emergency Green Corridor - BASELINE version (Phase 9 / 12).

This is the rule-based preemption that the quantum optimizer will later be
compared against:

    ambulance ETA to intersection <= PREEMPT_ETA
            -> force that intersection to the ambulance's phase
            -> also pre-clear the NEXT intersection on the route (corridor)
            -> release preemption as soon as the ambulance has passed

Later (optimized version) the green windows are *scheduled* against the ETA
so that normal traffic is disturbed as little as possible - that is where
the cost term `w4 * emergency_delay` enters the QUBO.
"""

from typing import Dict, List, Optional

from config import settings
from src.simulation.vehicle import Vehicle


class EmergencyManager:
    def __init__(self, network):
        self.net = network
        self.spawn_time: Optional[float] = None
        self.entry_road: Optional[str] = None
        self.vehicle: Optional[Vehicle] = None
        self.route: List[str] = []
        self.corridor: List[str] = []          # intersection ids on the route
        self._preempted: set = set()
        self.finished = False
        self.log: List[str] = []

    # ---------------- setup ----------------
    def schedule(self, time: float, entry_road: str = None):
        self.spawn_time = time
        self.entry_road = entry_road

    def _pick_route(self) -> List[str]:
        entry = self.entry_road or self.net.entry_roads[0]
        routes = self.net.routes_from(entry)
        # prefer the longest corridor that never visits the same intersection twice
        def clean(route):
            nodes = self._intersections_on(route)
            return len(nodes) == len(set(nodes))
        straight = [r for r in routes if clean(r)]
        return list(max(straight or routes, key=len))

    def _intersections_on(self, route: List[str]) -> List[str]:
        return [self.net.roads[r].to_node for r in route
                if self.net.roads[r].to_node in self.net.intersections]

    # ---------------- main hook ----------------
    def update(self, now: float, sim):
        if self.spawn_time is None or self.finished:
            return

        # 1) spawn the ambulance once
        if self.vehicle is None and now >= self.spawn_time:
            self.route = self._pick_route()
            self.corridor = self._intersections_on(self.route)
            self.vehicle = Vehicle(route=list(self.route), depart_time=now,
                                   vtype="ambulance", pcu=1.0, fuel_factor=1.6,
                                   is_emergency=True)
            sim.enter_vehicle(self.vehicle, now)
            self.log.append(f"[{now:.0f}s] AMBULANCE {self.vehicle.id} dispatched "
                            f"via {' -> '.join(self.corridor)}")
            return

        if self.vehicle is None:
            return

        # 2) ambulance finished -> restore everything
        if self.vehicle.id not in sim.active:
            self._release_all()
            self.finished = True
            self.log.append(f"[{now:.0f}s] ambulance cleared - normal control restored")
            return

        # 3) preempt the current + next intersection on the route
        wanted: Dict[str, int] = {}
        eta = self.eta_to_next(now)
        idx = self.vehicle.route_index

        for offset in (0, 1):                       # current + one ahead = corridor
            i = idx + offset
            if i >= len(self.route):
                break
            rid = self.route[i]
            node = self.net.roads[rid].to_node
            if node not in self.net.intersections:
                continue
            if offset == 0 and eta > settings.EMERGENCY_PREEMPT_ETA:
                continue                            # still too far away
            phase = self.net.intersections[node].signal.phase_index_of(rid)
            if phase is not None:
                wanted[node] = phase

        for node, phase in wanted.items():
            sig = self.net.intersections[node].signal
            sig.request_phase(phase)
            if node not in self._preempted:
                self.log.append(f"[{now:.0f}s] green corridor ON at {node} "
                                f"(phase {sig.phases[phase].name}, ETA {eta:.0f}s)")
                self._preempted.add(node)

        for node in list(self._preempted):
            if node not in wanted:
                self.net.intersections[node].signal.release_preemption()
                self._preempted.discard(node)
                self.log.append(f"[{now:.0f}s] green corridor OFF at {node}")

    # ---------------- helpers ----------------
    def eta_to_next(self, now: float) -> float:
        """Seconds until the ambulance reaches the stop line ahead of it."""
        if self.vehicle is None:
            return float("inf")
        road = self.net.roads[self.vehicle.current_road]
        for entry in road.transit:
            if entry[0].id == self.vehicle.id:
                return max(0.0, entry[1] - now)
        return 0.0            # already queued at the stop line

    def _release_all(self):
        for node in list(self._preempted):
            self.net.intersections[node].signal.release_preemption()
        self._preempted.clear()

    def status(self, now: float = 0.0) -> dict:
        return {
            "active": self.vehicle is not None and not self.finished,
            "vehicle_id": self.vehicle.id if self.vehicle else None,
            "current_road": self.vehicle.current_road if self.vehicle and not self.finished else None,
            "corridor": self.corridor,
            "preempted": sorted(self._preempted),
            "eta_next_s": round(self.eta_to_next(now), 1) if self.vehicle and not self.finished else None,
        }
