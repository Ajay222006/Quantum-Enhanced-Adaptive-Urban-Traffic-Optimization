"""
Standardised test scenarios (Phase 16 - experimental evaluation).

Every controller is run against the SAME scenario + SAME seed,
so the comparison table is fair.
"""

from src.emergency.emergency_manager import EmergencyManager
from src.events.event_manager import Event, EventManager

SCENARIOS = ["normal", "rush", "sudden_congestion", "accident",
             "road_closure", "emergency", "emergency_congestion"]


def _internal_road(net):
    """Pick a road between two intersections (for accidents/closures)."""
    for rid, r in net.roads.items():
        if not r.is_entry and not r.is_exit:
            return rid
    return list(net.roads)[0]


def build_scenario(name: str, net):
    """Return (demand_profile, EventManager, EmergencyManager|None)."""
    em = EventManager()
    emergency = None
    profile = "normal"

    if name == "normal":
        pass

    elif name == "rush":
        profile = "rush"

    elif name == "sudden_congestion":
        em.add(Event(time=600, kind="congestion", target="ALL", value=2.4, duration=600))

    elif name == "accident":
        em.add(Event(time=600, kind="accident", target=_internal_road(net),
                     value=0.25, duration=600))

    elif name == "road_closure":
        em.add(Event(time=600, kind="road_closure", target=_internal_road(net),
                     duration=600))

    elif name == "emergency":
        emergency = EmergencyManager(net)
        emergency.schedule(time=600)

    elif name == "emergency_congestion":
        profile = "rush"
        em.add(Event(time=500, kind="congestion", target="ALL", value=2.0, duration=700))
        emergency = EmergencyManager(net)
        emergency.schedule(time=700)

    else:
        raise ValueError(f"Unknown scenario '{name}'. Options: {SCENARIOS}")

    return profile, em, emergency
