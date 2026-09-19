"""Benchmark the exact classical and NumPy QAOA solvers on one traffic QUBO.

Run from the project root:
    python experiments/benchmark_optimizers.py --output results/optimizer_benchmark.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimization.ising import qubo_to_ising
from src.optimization.qaoa_solver import QAOASolver
from src.optimization.qubo_builder import DynamicQUBOBuilder


def sample_state() -> dict:
    return {
        "NS": {
            "queue": 24.0,
            "density": 0.50,
            "waiting": 30.0,
            "flow": 22.0,
            "capacity": 60.0,
            "fuel": 1.2,
            "co2": 1.4,
            "emergency_delay": 0.0,
        },
        "EW": {
            "queue": 18.0,
            "density": 0.40,
            "waiting": 20.0,
            "flow": 18.0,
            "capacity": 60.0,
            "fuel": 1.0,
            "co2": 1.2,
            "emergency_delay": 0.0,
        },
    }


def solve_exact(builder: DynamicQUBOBuilder, qubo) -> dict:
    start = time.perf_counter()
    best_assignment = None
    best_energy = float("inf")
    valid_assignments = 0
    for ns_green in builder.green_times:
        for ew_green in builder.green_times:
            assignment = {variable: 0 for variable in qubo.variables}
            assignment[f"x_NS_{ns_green}"] = 1
            assignment[f"x_EW_{ew_green}"] = 1
            energy = qubo.value(assignment)
            valid_assignments += 1
            if energy < best_energy:
                best_energy = energy
                best_assignment = assignment
    elapsed = time.perf_counter() - start
    return {
        "solver": "exact_classical_enumeration",
        "assignment": best_assignment,
        "timings": builder.decode(best_assignment),
        "objective_value": float(best_energy),
        "execution_time_s": float(elapsed),
        "success_probability": 1.0,
        "solution_quality": "optimal",
        "problem_size": len(qubo.variables),
        "candidate_configurations_evaluated": valid_assignments,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/optimizer_benchmark.json")
    parser.add_argument("--shots", type=int, default=512)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    builder = DynamicQUBOBuilder()
    qubo = builder.build(sample_state())
    ising = qubo_to_ising(qubo)
    classical = solve_exact(builder, qubo)
    qaoa = QAOASolver(builder, layers=1, grid_size=5, shots=args.shots, seed=args.seed).solve(qubo, ising)
    benchmark = {
        "problem": {
            "variables": len(qubo.variables),
            "candidate_configurations": len(builder.green_times) ** 2,
            "green_times": list(builder.green_times),
        },
        "solvers": [classical, {key: value for key, value in qaoa.items() if key != "assignment"}],
        "objective_gap": float(qaoa["objective_value"] - classical["objective_value"]),
        "qaoa_matches_classical": bool(qaoa["objective_value"] == classical["objective_value"]),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(benchmark, handle, indent=2)

    print(json.dumps(benchmark, indent=2))
    print(f"Benchmark written to {os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
