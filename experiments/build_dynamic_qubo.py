import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.optimization.qubo_builder import DynamicQUBOBuilder
from sumo.classical_optimizer_controller import ApproachState


def load_state(path: str):
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    return {
        key: ApproachState(**values)
        for key, values in raw.items()
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a dynamic signal-timing QUBO")
    parser.add_argument("--state", required=True, help="JSON with NS and EW ApproachState fields")
    parser.add_argument("--output", default="results/dynamic_qubo.json")
    parser.add_argument("--emergency-priority", action="store_true")
    args = parser.parse_args()

    model = DynamicQUBOBuilder().build(
        load_state(args.state),
        emergency_active=args.emergency_priority,
    )
    model.save(args.output)
    print(json.dumps({
        "output": args.output,
        "variables": len(model.variables),
        "linear_terms": len(model.linear),
        "quadratic_terms": len(model.quadratic),
        "metadata": model.metadata,
    }, indent=2))
