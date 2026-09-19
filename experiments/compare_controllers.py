"""
Classical comparison table (Phase 16).

    python experiments/compare_controllers.py
    python experiments/compare_controllers.py --scenario accident

Later you simply append "classical_opt" and "qaoa_hybrid" to CONTROLLERS
and this exact script produces your final results table.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings                                     # noqa: E402
from config.scenarios import SCENARIOS, build_scenario          # noqa: E402
from src.control.fixed_time import FixedTimeController          # noqa: E402
from src.control.rule_based import RuleBasedController          # noqa: E402
from src.network.network_builder import build_network           # noqa: E402
from src.simulation.simulator import Simulator                  # noqa: E402

CONTROLLERS = {
    "Fixed": FixedTimeController,
    "Rule-Based": RuleBasedController,
    # "Classical Opt": ClassicalOptimizerController,   <- Milestone 7
    # "Hybrid QAOA":   QAOAController,                 <- Milestone 8
}

METRICS = [
    ("Avg waiting time (s)", "avg_waiting_time_s"),
    ("Avg travel time (s)", "avg_travel_time_s"),
    ("Avg queue (veh)", "avg_total_queue"),
    ("Congestion index", "congestion_index"),
    ("Throughput (veh/h)", "throughput_vph"),
    ("Fuel (L)", "fuel_litres"),
    ("CO2 (kg)", "co2_kg"),
    ("Emergency travel (s)", "emergency_travel_time_s"),
]


def run_one(ctrl_cls, scenario, intersections, duration, seed):
    net = build_network(intersections)
    profile, events, emergency = build_scenario(scenario, net)
    sim = Simulator(net, ctrl_cls(net), duration=duration, profile=profile,
                    seed=seed, event_manager=events, emergency=emergency)
    return sim.run()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="rush", choices=SCENARIOS)
    p.add_argument("--intersections", type=int, default=4, choices=[4, 6, 8])
    p.add_argument("--duration", type=int, default=settings.DEFAULT_DURATION)
    p.add_argument("--seed", type=int, default=settings.RANDOM_SEED)
    args = p.parse_args()

    print(f"\nScenario: {args.scenario} | {args.intersections} intersections | "
          f"{args.duration}s | seed {args.seed}")

    results = {}
    for name, cls in CONTROLLERS.items():
        print(f"  running {name} ...")
        results[name] = run_one(cls, args.scenario, args.intersections,
                                args.duration, args.seed)

    names = list(results)
    width = 24
    header = "Metric".ljust(width) + "".join(n.rjust(16) for n in names)
    print("\n" + header)
    print("-" * len(header))
    for label, key in METRICS:
        values = [results[n].get(key) for n in names]
        if all(v is None for v in values):
            continue
        row = label.ljust(width)
        for v in values:
            row += ("-" if v is None else f"{v}").rjust(16)
        print(row)

    # improvement of the best adaptive method over the fixed baseline
    if "Fixed" in results and len(names) > 1:
        base = results["Fixed"]
        print("\nImprovement vs Fixed timing:")
        for n in names[1:]:
            r = results[n]
            def pct(key, lower_is_better=True):
                b, v = base.get(key), r.get(key)
                if not b or v is None:
                    return "n/a"
                change = (b - v) / b * 100
                if not lower_is_better:
                    change = -change
                return f"{change:+.1f}%"
            print(f"  {n}: waiting {pct('avg_waiting_time_s')}, "
                  f"queue {pct('avg_total_queue')}, "
                  f"CO2 {pct('co2_kg')}, "
                  f"throughput {pct('throughput_vph', lower_is_better=False)}")


if __name__ == "__main__":
    main()
