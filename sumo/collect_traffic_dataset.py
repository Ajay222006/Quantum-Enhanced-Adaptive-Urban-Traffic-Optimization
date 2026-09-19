import argparse
import os

from sumo.realtime_traffic_state import SumoTrafficStateEstimator
from sumo.sumo_traci_bridge import SumoTraCIConnector
from src.prediction.traffic_prediction import TrafficStateRecorder


def collect(scenario: str, output: str, duration: int, interval: int, gui: bool = False):
    """Run SUMO and record estimator snapshots for one labeled scenario."""
    connector = SumoTraCIConnector(gui=gui)
    estimator = SumoTrafficStateEstimator()
    recorder = TrafficStateRecorder(output)
    try:
        connector.start()
        next_sample = 0.0
        while True:
            connector.step()
            now = float(__import__("traci").simulation.getTime())
            if now >= next_sample:
                recorder.record(estimator.update(), now, scenario)
                next_sample += interval
            if now >= duration:
                break
    finally:
        connector.stop()
    return recorder.save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect SUMO traffic-state time series")
    parser.add_argument("--scenario", required=True, help="Scenario label: normal, rush, closure, emergency, etc.")
    parser.add_argument("--output", default="data/traffic_states.csv")
    parser.add_argument("--duration", type=int, default=3600)
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    print(collect(args.scenario, args.output, args.duration, args.interval, args.gui))
