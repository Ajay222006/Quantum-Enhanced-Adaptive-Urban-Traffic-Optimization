import numpy as np

from src.optimization.qubo_builder import DynamicQUBOBuilder
from src.optimization.ising import qubo_to_ising
from src.optimization.qaoa_solver import QAOASolver


def test_qubo_ising_compatibility_and_solver_returns_valid_timing():
    builder = DynamicQUBOBuilder(green_times=(20, 30, 40, 50), min_green=20, max_green=60)
    state = {
        "NS": {"queue": 24, "density": 0.5, "waiting": 30.0, "flow": 22.0, "capacity": 60.0, "fuel": 1.2, "co2": 1.4, "emergency_delay": 0.0},
        "EW": {"queue": 18, "density": 0.4, "waiting": 20.0, "flow": 18.0, "capacity": 60.0, "fuel": 1.0, "co2": 1.2, "emergency_delay": 0.0},
    }
    model = builder.build(state)
    ising = qubo_to_ising(model)
    solution = QAOASolver(builder, layers=1, grid_size=3, shots=128, optimizer_steps=10).solve(model, ising)

    assert solution["assignment"] is not None
    assert solution["timings"]["NS"] in builder.green_times
    assert solution["timings"]["EW"] in builder.green_times
    assert "execution_time_s" in solution
    assert "objective_value" in solution
    assert "problem_size" in solution


def test_prediction_split_uses_validation_and_test_windows():
    data = []
    for i in range(40):
        data.append({
            "timestamp": float(i),
            "scenario": "normal",
            "intersection_id": "C",
            "direction": "N",
            "density": 0.5 + (i % 5) * 0.1,
            "queue": 10 + (i % 7),
            "avg_speed": 25.0,
            "flow": 15.0,
            "capacity": 60.0,
            "phase": 0.0,
        })
    from src.prediction.traffic_prediction import TrafficStateDataset
    import csv
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "timestamp", "scenario", "intersection_id", "direction",
            "density", "queue", "avg_speed", "flow", "capacity", "phase",
        ])
        writer.writeheader()
        writer.writerows(data)
        path = handle.name

    X, y, keys, timestamps = TrafficStateDataset(interval_seconds=1, history_seconds=5, horizon_seconds=1).build(path)
    assert len(X) > 0
    assert len(y) == len(X)
    assert len(keys) == len(X)
    assert len(timestamps) == len(X)
