"""
Intersection = a node with a traffic signal, incoming approaches and
outgoing links. This is the unit the optimizer makes decisions for.
"""

from typing import Dict, List

from src.network.signal import Phase, TrafficSignal


class Intersection:
    def __init__(self, id: str, x: float, y: float):
        self.id = id
        self.x = x
        self.y = y
        self.incoming: List[str] = []     # road ids arriving here
        self.outgoing: List[str] = []     # road ids leaving here
        self.signal: TrafficSignal = None
        self.pedestrian_demand = 0        # placeholder for pedestrian phase rules

    def build_signal(self, roads: Dict[str, "Road"]):
        """Group incoming approaches into NS / EW phases."""
        ns = [r for r in self.incoming if roads[r].axis == "NS"]
        ew = [r for r in self.incoming if roads[r].axis == "EW"]
        phases = [Phase("NS", ns), Phase("EW", ew)]
        self.signal = TrafficSignal(self.id, phases)

    def approach_roads(self, phase_name: str) -> List[str]:
        for ph in self.signal.phases:
            if ph.name == phase_name:
                return ph.approaches
        return []

    def __repr__(self):
        return f"<Intersection {self.id} in={len(self.incoming)} out={len(self.outgoing)}>"
