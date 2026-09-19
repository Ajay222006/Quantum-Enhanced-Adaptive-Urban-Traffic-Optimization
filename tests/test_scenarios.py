import pytest

from config.scenarios import SCENARIOS, build_scenario
from src.network.network_builder import build_network


def test_all_declared_scenarios_build_for_standard_network():
    network = build_network(4)

    for name in SCENARIOS:
        profile, event_manager, emergency = build_scenario(name, network)
        assert profile in {"normal", "rush"}
        assert event_manager.events is not None
        if name in {"emergency", "emergency_congestion"}:
            assert emergency is not None
        else:
            assert emergency is None


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError, match="Unknown scenario"):
        build_scenario("not_a_scenario", build_network(4))


def test_accident_requires_an_internal_road():
    network = build_network(4)
    network.roads = {
        road_id: road
        for road_id, road in network.roads.items()
        if road.is_entry or road.is_exit
    }

    with pytest.raises(ValueError, match="internal road"):
        build_scenario("accident", network)
