from sumo.emergency_green_corridor import EmergencyGreenCorridorController


def test_green_window_generation_and_release_logic():
    controller = EmergencyGreenCorridorController(
        tls_ids=["C"],
        emergency_vehicle_type="ambulance",
    )

    windows = controller.generate_green_windows(
        ambulance_id="AMB_1",
        arrival_times={"C": 12.0, "J2": 27.0, "J3": 43.0},
        traffic_state={"C": {"queue": 12, "flow": 20}, "J2": {"queue": 8, "flow": 18}},
    )

    assert "C" in windows
    assert windows["C"]["start_time"] <= 12.0 <= windows["C"]["end_time"]
    assert windows["C"]["duration_seconds"] > 0
    assert controller._is_emergency_window_for_signal("C", 12.0)

    controller.release_signal("C")
    assert not controller._is_emergency_window_for_signal("C", 12.0)
