import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sumo.fixed_time_controller import run_scenario


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run fixed-time SUMO baseline scenarios")
    parser.add_argument("--scenario", choices=["low", "normal", "rush", "congestion"], default="normal")
    parser.add_argument("--duration", type=int, default=3600)
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()

    result = run_scenario(args.scenario, duration=args.duration,
                          output_dir=args.output_dir, gui=args.gui)
    print(json.dumps(result, indent=2))
