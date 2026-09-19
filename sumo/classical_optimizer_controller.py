"""Discrete classical signal-timing optimizer for SUMO/TraCI."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Dict, Tuple

try:
    import traci
except ImportError:
    traci = None

from sumo.fixed_time_controller import FixedTimeMetrics, create_scenario_routes
from src.control.traffic_objective import (
    MetricBounds,
    ObjectiveWeights,
    calculate_overall_cost,
)


@dataclass(frozen=True)
class ApproachState:
    queue: float
    density: float
    waiting: float
    flow: float
    capacity: float
    emergency_delay: float = 0.0
    fuel: float = 0.0
    co2: float = 0.0


class ClassicalSignalOptimizer:
    """Enumerate feasible green-time pairs and select the lowest-cost pair."""

    def __init__(self, tls_id: str = "C", candidates=(20, 25, 30, 35, 40, 45, 50),
                 yellow: int = 5, min_green: int = 20, max_green: int = 60,
                 emergency_active: bool = False):
        self.tls_id = tls_id
        self.candidates = tuple(sorted(set(candidates)))
        self.yellow = yellow
        self.min_green = min_green
        self.max_green = max_green
        self.last_solution = (30, 30)
        self.last_cost = None
        self.last_state = {}
        self.weights = ObjectiveWeights().for_emergency() if emergency_active else ObjectiveWeights()
        self.bounds = MetricBounds()

    def _approach_state(self, edges: Tuple[str, ...]) -> ApproachState:
        queue = 0.0
        density_count = 0.0
        waiting = 0.0
        flow = 0.0
        capacity = 0.0
        emergency_delay = 0.0
        fuel = 0.0
        co2 = 0.0
        for edge_id in edges:
            vehicles = traci.edge.getLastStepVehicleIDs(edge_id)
            queue += sum(traci.vehicle.getSpeed(vehicle_id) < 0.5 for vehicle_id in vehicles)
            density_count += traci.edge.getLastStepVehicleNumber(edge_id)
            waiting += traci.edge.getWaitingTime(edge_id)
            flow += traci.edge.getLastStepVehicleNumber(edge_id)
            for vehicle_id in vehicles:
                vehicle_type = traci.vehicle.getTypeID(vehicle_id).lower()
                if "emergency" in vehicle_type or "ambulance" in vehicle_type:
                    emergency_delay += traci.vehicle.getAccumulatedWaitingTime(vehicle_id)
                fuel += traci.vehicle.getFuelConsumption(vehicle_id) / 1_000_000.0
                co2 += traci.vehicle.getCO2Emission(vehicle_id) / 1_000_000.0
            for lane_index in range(traci.edge.getLaneNumber(edge_id)):
                lane_id = f"{edge_id}_{lane_index}"
                capacity += max(1.0, traci.lane.getLength(lane_id) / 5.0)
        capacity = max(1.0, capacity)
        return ApproachState(
            queue=queue,
            density=min(1.0, density_count / capacity),
            waiting=waiting,
            flow=flow,
            capacity=capacity,
            emergency_delay=emergency_delay,
            fuel=fuel,
            co2=co2,
        )

    def measure_state(self) -> Dict[str, ApproachState]:
        state = {
            "NS": self._approach_state(("north_in", "south_in")),
            "EW": self._approach_state(("east_in", "west_in")),
        }
        self.last_state = state
        return state

    def objective(self, ns_green: int, ew_green: int,
                  state: Dict[str, ApproachState]) -> dict:
        """Evaluate one candidate using the normalized shared traffic objective."""
        if not (self.min_green <= ns_green <= self.max_green):
            return {"cost": float("inf"), "metrics": {}, "objective": {}}
        if not (self.min_green <= ew_green <= self.max_green):
            return {"cost": float("inf"), "metrics": {}, "objective": {}}

        cycle = ns_green + ew_green + 2 * self.yellow
        ns_share = ns_green / cycle
        ew_share = ew_green / cycle
        ns = state["NS"]
        ew = state["EW"]
        metrics = {
            "waiting": ns.waiting * (1.0 - ns_share) + ew.waiting * (1.0 - ew_share),
            "queue": ns.queue * (1.0 - ns_share) + ew.queue * (1.0 - ew_share),
            "congestion": ns.density * (1.0 - ns_share) + ew.density * (1.0 - ew_share),
            "emergency_delay": ns.emergency_delay * (1.0 - ns_share) + ew.emergency_delay * (1.0 - ew_share),
            "fuel": (ns.fuel + ew.fuel) * (1.0 + 0.25 * (2.0 - ns_share - ew_share)),
            "co2": (ns.co2 + ew.co2) * (1.0 + 0.25 * (2.0 - ns_share - ew_share)),
            "throughput": ns.flow * ns_share + ew.flow * ew_share,
        }
        objective = calculate_overall_cost(metrics, self.weights, self.bounds)
        return {"cost": objective["cost"], "metrics": metrics, "objective": objective}

    def optimize(self, state: Dict[str, ApproachState] = None) -> dict:
        state = state or self.measure_state()
        evaluations = []
        for ns_green in self.candidates:
            for ew_green in self.candidates:
                evaluation = self.objective(ns_green, ew_green, state)
                evaluations.append({
                    "ns_green": ns_green,
                    "ew_green": ew_green,
                    "cost": round(evaluation["cost"], 6),
                    "metrics": evaluation["metrics"],
                    "normalized": evaluation["objective"].get("normalized", {}),
                    "contributions": evaluation["objective"].get("contributions", {}),
                })
        best = min(evaluations, key=lambda item: item["cost"])
        self.last_solution = (best["ns_green"], best["ew_green"])
        self.last_cost = best["cost"]
        return {"selected": best, "evaluations": evaluations, "state": state}

    def apply(self, solution: dict = None) -> dict:
        solution = solution or self.optimize()
        ns_green = solution["selected"]["ns_green"]
        ew_green = solution["selected"]["ew_green"]
        phase = traci.trafficlight.getPhase(self.tls_id)
        if phase == 0:
            traci.trafficlight.setPhaseDuration(self.tls_id, ns_green)
        elif phase == 2:
            traci.trafficlight.setPhaseDuration(self.tls_id, ew_green)
        return solution["selected"]


def run_classical(config_path: str, route_path: str, output_path: str,
                  duration: int = 3600, tls_id: str = "C", gui: bool = False,
                  optimization_interval: int = 10,
                  emergency_active: bool = False) -> dict:
    if traci is None:
        raise RuntimeError("TraCI is not installed. Install SUMO Python support first.")

    sumo_binary = "sumo-gui" if gui else "sumo"
    command = [sumo_binary, "-c", config_path, "--route-files", route_path,
               "--begin", "0", "--end", str(duration)]
    traci.start(command)
    optimizer = ClassicalSignalOptimizer(tls_id=tls_id, emergency_active=emergency_active)
    metrics = FixedTimeMetrics()
    next_optimization = 0.0
    optimization_log = []
    try:
        while traci.simulation.getMinExpectedNumber() > 0 or traci.simulation.getTime() < duration:
            now = traci.simulation.getTime()
            if now >= duration:
                break
            if now >= next_optimization:
                state = optimizer.measure_state()
                solution = optimizer.optimize(state)
                selected = optimizer.apply(solution)
                optimization_log.append({
                    "time": now,
                    "selected": selected,
                    "state": {
                        key: vars(value) for key, value in state.items()
                    },
                })
                next_optimization += optimization_interval
            traci.simulationStep()
            metrics.update(traci.simulation.getTime())
        result = metrics.summary(min(float(duration), traci.simulation.getTime()))
        result.update({
            "controller": "classical_optimizer",
            "cycle": "optimized candidate pair with 5s yellow",
            "optimization_interval_s": optimization_interval,
            "candidate_green_times_s": [20, 25, 30, 35, 40, 45, 50],
            "candidate_configurations_evaluated": 49,
            "objective": "normalized weighted multi-objective cost",
            "normalized_objective": "w1*waiting + w2*queue + w3*congestion + w4*emergency_delay + w5*fuel + w6*co2 - w7*throughput",
            "objective_weights": vars(optimizer.weights),
            "normalization_bounds": vars(optimizer.bounds),
            "emergency_priority": emergency_active,
            "optimization_steps": len(optimization_log),
            "final_solution": optimization_log[-1]["selected"] if optimization_log else None,
            "optimization_log": optimization_log,
        })
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        return result
    finally:
        traci.close()


def run_scenario(scenario: str, sumo_dir: str = None, duration: int = 3600,
                 output_dir: str = "results", gui: bool = False,
                 optimization_interval: int = 10,
                 emergency_active: bool = False) -> dict:
    sumo_dir = sumo_dir or os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(sumo_dir, "sumocfg.sumocfg")
    source_routes = os.path.join(sumo_dir, "routes.rou.xml")
    os.makedirs(output_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        route_path = os.path.join(temp_dir, f"{scenario}.rou.xml")
        create_scenario_routes(source_routes, scenario, route_path)
        output_path = os.path.join(output_dir, f"classical_optimizer_{scenario}.json")
        return run_classical(config_path, route_path, output_path, duration,
                             gui=gui, optimization_interval=optimization_interval,
                             emergency_active=emergency_active)
