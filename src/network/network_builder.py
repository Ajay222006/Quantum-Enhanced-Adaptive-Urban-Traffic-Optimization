"""
Builds the urban traffic network (Phase 1 of the project).

A grid of intersections + external entry/exit nodes:

        N00      N01
         |        |
 W00 -- I00 ---- I01 -- E01
         |        |
 W10 -- I10 ---- I11 -- E11
         |        |
        S10      S11

rows x cols  ->  4 (2x2), 6 (2x3) or 8 (2x4) intersections.
The same builder is reused for the scalability study later.
"""

from collections import deque
from typing import Dict, List, Optional

from config import settings
from src.network.intersection import Intersection
from src.network.road import Road


class TrafficNetwork:
    def __init__(self, name: str = "grid"):
        self.name = name
        self.intersections: Dict[str, Intersection] = {}
        self.roads: Dict[str, Road] = {}
        self.node_pos: Dict[str, tuple] = {}
        self.entry_roads: List[str] = []
        self.exit_roads: List[str] = []
        self._route_cache: Dict[str, List[List[str]]] = {}

    # ---------------- construction ----------------
    def add_intersection(self, iid: str, x: float, y: float):
        self.intersections[iid] = Intersection(iid, x, y)
        self.node_pos[iid] = (x, y)

    def add_external(self, nid: str, x: float, y: float):
        self.node_pos[nid] = (x, y)

    def add_road(self, a: str, b: str, length: float, axis: str, lanes: int = None):
        rid = f"{a}->{b}"
        road = Road(
            id=rid, from_node=a, to_node=b, length_m=length, axis=axis,
            lanes=lanes or settings.DEFAULT_LANES,
            is_entry=a not in self.intersections,
            is_exit=b not in self.intersections,
        )
        self.roads[rid] = road
        if a in self.intersections:
            self.intersections[a].outgoing.append(rid)
        if b in self.intersections:
            self.intersections[b].incoming.append(rid)
        if road.is_entry:
            self.entry_roads.append(rid)
        if road.is_exit:
            self.exit_roads.append(rid)
        return road

    def finalize(self):
        for inter in self.intersections.values():
            inter.build_signal(self.roads)

    # ---------------- topology helpers ----------------
    def next_roads(self, road_id: str) -> List[str]:
        """Roads a vehicle may take after `road_id` (no U-turn)."""
        road = self.roads[road_id]
        node = road.to_node
        if node not in self.intersections:
            return []
        out = []
        for rid in self.intersections[node].outgoing:
            if self.roads[rid].to_node != road.from_node:      # block U-turn
                out.append(rid)
        return out

    def routes_from(self, entry_road: str) -> List[List[str]]:
        """Shortest path (in hops) from an entry road to every exit road."""
        if entry_road in self._route_cache:
            return self._route_cache[entry_road]
        routes, seen_exit = [], set()
        q = deque([[entry_road]])
        while q:
            path = q.popleft()
            last = path[-1]
            if self.roads[last].is_exit:
                if last not in seen_exit:
                    seen_exit.add(last)
                    routes.append(path)
                continue
            if len(path) > 6:
                continue
            for nxt in self.next_roads(last):
                if nxt not in path:
                    q.append(path + [nxt])
        self._route_cache[entry_road] = routes
        return routes

    # ---------------- reporting ----------------
    def summary(self) -> str:
        return (f"Network '{self.name}': {len(self.intersections)} intersections, "
                f"{len(self.roads)} roads, {len(self.entry_roads)} entries, "
                f"{len(self.exit_roads)} exits")

    def reset(self):
        for r in self.roads.values():
            r.reset_dynamic_state()
        self.finalize()


# ---------------- factory ----------------
def build_grid_network(rows: int = 2, cols: int = 2, spacing: float = None) -> TrafficNetwork:
    spacing = spacing or settings.INTERNAL_ROAD_LENGTH
    ext = settings.EXTERNAL_ROAD_LENGTH
    net = TrafficNetwork(name=f"grid_{rows}x{cols}")

    # intersections (row 0 is the top row)
    for r in range(rows):
        for c in range(cols):
            net.add_intersection(f"I{r}{c}", x=c * spacing, y=(rows - 1 - r) * spacing)

    def link(a, b, axis, length):
        net.add_road(a, b, length, axis)
        net.add_road(b, a, length, axis)

    # internal links
    for r in range(rows):
        for c in range(cols):
            if c + 1 < cols:
                link(f"I{r}{c}", f"I{r}{c+1}", "EW", spacing)
            if r + 1 < rows:
                link(f"I{r}{c}", f"I{r+1}{c}", "NS", spacing)

    # external links on the border
    for r in range(rows):
        for c in range(cols):
            iid, (x, y) = f"I{r}{c}", net.node_pos[f"I{r}{c}"]
            if c == 0:
                net.add_external(f"W{r}{c}", x - ext, y); link(f"W{r}{c}", iid, "EW", ext)
            if c == cols - 1:
                net.add_external(f"E{r}{c}", x + ext, y); link(f"E{r}{c}", iid, "EW", ext)
            if r == 0:
                net.add_external(f"N{r}{c}", x, y + ext); link(f"N{r}{c}", iid, "NS", ext)
            if r == rows - 1:
                net.add_external(f"S{r}{c}", x, y - ext); link(f"S{r}{c}", iid, "NS", ext)

    net.finalize()
    return net


def build_network(num_intersections: int = 4) -> TrafficNetwork:
    """4 -> 2x2, 6 -> 2x3, 8 -> 2x4 (used by the scalability study)."""
    layout = {4: (2, 2), 6: (2, 3), 8: (2, 4)}
    if num_intersections not in layout:
        raise ValueError("Supported sizes: 4, 6, 8")
    return build_grid_network(*layout[num_intersections])
