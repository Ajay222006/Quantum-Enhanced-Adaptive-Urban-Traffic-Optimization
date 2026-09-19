import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sumo.fixed_time_controller import create_scenario_routes
from sumo.event_detection import SumoIncidentManager
from sumo.realtime_optimizer_loop import run_closed_loop


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the closed-loop SUMO QUBO optimizer")
    parser.add_argument("--scenario", choices=["low", "normal", "rush", "congestion"], default="normal")
    parser.add_argument("--duration", type=int, default=3600)
    parser.add_argument("--optimization-interval", type=int, default=10, choices=[10, 15, 20, 25, 30])
    parser.add_argument("--model", help="Optional trained traffic predictor .joblib")
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--emergency-priority", action="store_true")
    parser.add_argument("--incident-kind", choices=["accident", "road_closure"])
    parser.add_argument("--incident-edge", default="west_in")
    parser.add_argument("--incident-start", type=float, default=120.0)
    parser.add_argument("--incident-duration", type=float, default=120.0)
    parser.add_argument("--capacity-factor", type=float, default=0.25)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()

    sumo_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sumo")
    config_path = os.path.join(sumo_dir, "sumocfg.sumocfg")
    source_routes = os.path.join(sumo_dir, "routes.rou.xml")
    os.makedirs(args.output_dir, exist_ok=True)
    output_path = os.path.join(args.output_dir, f"realtime_qubo_{args.scenario}.json")
    incident = None
    if args.incident_kind:
        incident = SumoIncidentManager(
            edge_id=args.incident_edge,
            kind=args.incident_kind,
            start=args.incident_start,
            duration=args.incident_duration,
            capacity_factor=args.capacity_factor,
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        route_path = os.path.join(temp_dir, f"{args.scenario}.rou.xml")
        create_scenario_routes(source_routes, args.scenario, route_path)
        result = run_closed_loop(
            config_path,
            route_path,
            output_path,
            duration=args.duration,
            optimization_interval=args.optimization_interval,
            model_path=args.model,
            gui=args.gui,
            emergency_active=args.emergency_priority,
            incident=incident,
        )
    print(json.dumps({
        key: value for key, value in result.items()
        if key != "optimization_log"
    }, indent=2))
