"""
Entry point - run ONE simulation.

Examples
    python run_simulation.py
    python run_simulation.py --controller rule_based --scenario rush
    python run_simulation.py --controller rule_based --scenario emergency --verbose
    python run_simulation.py --intersections 8 --duration 3600
"""

import argparse
import json

from config import settings
from config.scenarios import SCENARIOS, build_scenario
from src.control.fixed_time import FixedTimeController
from src.control.rule_based import RuleBasedController
from src.metrics.metrics import MetricsCollector
from src.network.network_builder import build_network
from src.simulation.simulator import Simulator

CONTROLLERS = {"fixed_time": FixedTimeController, "rule_based": RuleBasedController}


def run(controller_name="fixed_time", scenario="normal", intersections=4,
        duration=settings.DEFAULT_DURATION, seed=settings.RANDOM_SEED, verbose=False):
    net = build_network(intersections)
    profile, events, emergency = build_scenario(scenario, net)
    controller = CONTROLLERS[controller_name](net)

    sim = Simulator(net, controller, duration=duration, profile=profile,
                    seed=seed, event_manager=events, emergency=emergency,
                    verbose=verbose)

    print(net.summary())
    print(f"Controller : {controller_name} | Scenario: {scenario} | "
          f"Demand: {profile} | Duration: {duration}s")

    summary = sim.run()
    MetricsCollector.print_summary(f"{controller_name} / {scenario}", summary)

    if events.active_log:
        print("\n-- events --")
        for line in events.active_log:
            print("  " + line)
    if emergency and emergency.log:
        print("\n-- emergency corridor --")
        for line in emergency.log:
            print("  " + line)
    if sim.triggers:
        print(f"\n-- auto-detected anomalies: {len(sim.triggers)} "
              f"(first 3) --")
        for line in sim.triggers[:3]:
            print("  " + line)

    return sim, summary


def main():
    p = argparse.ArgumentParser(description="Adaptive urban traffic simulator")
    p.add_argument("--controller", default="fixed_time", choices=list(CONTROLLERS))
    p.add_argument("--scenario", default="normal", choices=SCENARIOS)
    p.add_argument("--intersections", type=int, default=4, choices=[4, 6, 8])
    p.add_argument("--duration", type=int, default=settings.DEFAULT_DURATION)
    p.add_argument("--seed", type=int, default=settings.RANDOM_SEED)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--json", help="write the summary to this file")
    args = p.parse_args()

    sim, summary = run(args.controller, args.scenario, args.intersections,
                       args.duration, args.seed, args.verbose)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"\nsaved -> {args.json}")


if __name__ == "__main__":
    main()
