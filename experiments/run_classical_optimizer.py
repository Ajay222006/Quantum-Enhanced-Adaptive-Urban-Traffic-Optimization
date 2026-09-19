import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sumo.classical_optimizer_controller import run_scenario


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run classical optimized SUMO scenarios")
    parser.add_argument("--scenario", choices=["low", "normal", "rush", "congestion"], default="normal")
    parser.add_argument("--duration", type=int, default=3600)
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--optimization-interval", type=int, default=10)
    parser.add_argument("--emergency-priority", action="store_true")
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()

    result = run_scenario(
        args.scenario,
        duration=args.duration,
        output_dir=args.output_dir,
        gui=args.gui,
        optimization_interval=args.optimization_interval,
        emergency_active=args.emergency_priority,
    )
    print(json.dumps(result, indent=2))
