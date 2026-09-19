"""Compare timing decisions under documented objective-weight policies."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.control.traffic_objective import MetricBounds, ObjectiveWeights, calculate_overall_cost
from sumo.classical_optimizer_controller import ApproachState, ClassicalSignalOptimizer


POLICIES = {
    "baseline": ObjectiveWeights(),
    "emergency": ObjectiveWeights().for_emergency(),
    "queue_priority": ObjectiveWeights(
        waiting=0.30, queue=0.30, congestion=0.15,
        emergency_delay=0.10, fuel=0.05, co2=0.05, throughput=0.05,
    ),
    "throughput_priority": ObjectiveWeights(
        waiting=0.15, queue=0.10, congestion=0.10,
        emergency_delay=0.10, fuel=0.10, co2=0.05, throughput=0.40,
    ),
}


def run(output_path: str):
    # Replace this with a live state snapshot when running a SUMO experiment.
    state = {
        "NS": ApproachState(queue=35, density=0.72, waiting=120,
                             flow=51, capacity=100, emergency_delay=18,
                             fuel=2.0, co2=5.0),
        "EW": ApproachState(queue=12, density=0.30, waiting=45,
                             flow=35, capacity=100, emergency_delay=0,
                             fuel=1.5, co2=3.8),
    }
    results = {}
    for name, weights in POLICIES.items():
        optimizer = ClassicalSignalOptimizer()
        optimizer.weights = weights
        evaluation = optimizer.optimize(state)
        results[name] = {
            "weights": vars(weights),
            "selected": evaluation["selected"],
            "top_candidates": sorted(evaluation["evaluations"], key=lambda item: item["cost"])[:5],
        }

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run objective-weight sensitivity analysis")
    parser.add_argument("--output", default="results/weight_sensitivity.json")
    run(parser.parse_args().output)
