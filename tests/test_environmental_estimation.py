from src.metrics.environment_estimation import EnvironmentalEstimator


def test_environmental_estimator_uses_speed_distance_and_idle_time():
    estimate = EnvironmentalEstimator.estimate_vehicle(
        distance_m=1200.0,
        avg_speed_kmh=30.0,
        idle_time_s=20.0,
        stop_count=2,
        acceleration_events=3,
    )

    assert estimate["fuel_litres"] > 0.0
    assert estimate["co2_kg"] > 0.0
    assert estimate["estimated_fuel_litres"] == estimate["fuel_litres"]
    assert estimate["estimated_co2_kg"] == estimate["co2_kg"]
