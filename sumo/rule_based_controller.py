"""Queue-responsive TraCI controller and fair SUMO baseline runner."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Dict

try:
    import traci
except ImportError:
    traci = None

from sumo.fixed_time_controller import FixedTimeMetrics, create_scenario_routes


class RuleBasedController:
    """Adjust the next green using live queues while preserving safety bounds."""

    def __init__(self, tls_id: str = "C", initial_green: int = 30,
                 min_green: int = 20, max_green: int = 60,
                 low_queue: int = 5, high_queue: int = 15,
                 adjustment_step: int = 5, yellow: int = 5):
        self.tls_id = tls_id
        self.green = {0: initial_green, 2: initial_green}
        self.min_green = min_green
        self.max_green = max_green
        self.low_queue = low_queue
        self.high_queue = high_queue
        self.adjustment_step = adjustment_step
        self.yellow = yellow
        self.last_green = dict(self.green)
        self.last_queue = {0: 0, 2: 0}

    def _queue_for_phase(self, phase_index: int) -> int:
        approach_edges = {
            0: ("north_in", "south_in"),
            2: ("east_in", "west_in"),
        }[phase_index]
        queue = 0
        for edge_id in approach_edges:
            for vehicle_id in traci.edge.getLastStepVehicleIDs(edge_id):
                if traci.vehicle.getSpeed(vehicle_id) < 0.5:
                    queue += 1
        return queue

    def _measure_queues(self) -> Dict[int, int]:
        return {phase: self._queue_for_phase(phase) for phase in (0, 2)}

    def _adjust(self, phase_index: int, queue: int) -> int:
        green = self.green[phase_index]
        if queue > self.high_queue:
            green += self.adjustment_step
        elif queue < self.low_queue:
            green -= self.adjustment_step
        return max(self.min_green, min(self.max_green, green))

    def apply(self) -> Dict[int, int]:
        """Measure queues and set the active SUMO phase duration."""
        queues = self._measure_queues()
        for phase_index, queue in queues.items():
            self.green[phase_index] = self._adjust(phase_index, queue)
        self.last_queue = queues
        phase = traci.trafficlight.getPhase(self.tls_id)
        if phase in self.green:
            duration = self.green[phase]
            traci.trafficlight.setPhaseDuration(self.tls_id, duration)
        self.last_green = dict(self.green)
        return dict(self.green)


def run_rule_based(config_path: str, route_path: str, output_path: str,
                   duration: int = 3600, tls_id: str = "C", gui: bool = False,
                   control_interval: int = 10) -> dict:
    if traci is None:
        raise RuntimeError("TraCI is not installed. Install SUMO Python support first.")

    sumo_binary = "sumo-gui" if gui else "sumo"
    command = [sumo_binary, "-c", config_path, "--route-files", route_path,
               "--begin", "0", "--end", str(duration)]
    traci.start(command)
    controller = RuleBasedController(tls_id=tls_id)
    metrics = FixedTimeMetrics()
    next_control = 0.0
    try:
        while traci.simulation.getMinExpectedNumber() > 0 or traci.simulation.getTime() < duration:
            now = traci.simulation.getTime()
            if now >= duration:
                break
            if now >= next_control:
                controller.apply()
                next_control += control_interval
            traci.simulationStep()
            metrics.update(traci.simulation.getTime())
        result = metrics.summary(min(float(duration), traci.simulation.getTime()))
        result.update({
            "controller": "rule_based",
            "cycle": "adaptive 20-60G-5Y",
            "control_interval_s": control_interval,
            "min_green_s": controller.min_green,
            "max_green_s": controller.max_green,
            "low_queue_threshold": controller.low_queue,
            "high_queue_threshold": controller.high_queue,
            "adjustment_step_s": controller.adjustment_step,
        })
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        return result
    finally:
        traci.close()


def run_scenario(scenario: str, sumo_dir: str = None, duration: int = 3600,
                 output_dir: str = "results", gui: bool = False,
                 control_interval: int = 10) -> dict:
    sumo_dir = sumo_dir or os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(sumo_dir, "sumocfg.sumocfg")
    source_routes = os.path.join(sumo_dir, "routes.rou.xml")
    os.makedirs(output_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        route_path = os.path.join(temp_dir, f"{scenario}.rou.xml")
        create_scenario_routes(source_routes, scenario, route_path)
        output_path = os.path.join(output_dir, f"rule_based_{scenario}.json")
        return run_rule_based(config_path, route_path, output_path, duration,
                      gui=gui, control_interval=control_interval)
