"""Fixed-time SUMO controller and baseline metric collection."""

from __future__ import annotations

import json
import os
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict

try:
    import traci
except ImportError:
    traci = None


class FixedTimeController:
    """Keep one signal on an unchanged 30-5-30-5 second cycle."""

    def __init__(self, tls_id: str = "C", ns_green: int = 30,
                 yellow: int = 5, ew_green: int = 30):
        self.tls_id = tls_id
        self.phase_durations = (ns_green, yellow, ew_green, yellow)
        self.cycle_seconds = sum(self.phase_durations)
        self._last_phase = None

    def apply(self, simulation_time: float) -> None:
        """Apply the fixed phase schedule without reading traffic state."""
        elapsed = simulation_time % self.cycle_seconds
        phase = 0
        phase_start = 0
        for index, duration in enumerate(self.phase_durations):
            if elapsed < phase_start + duration:
                phase = index
                break
            phase_start += duration

        if phase != self._last_phase:
            traci.trafficlight.setPhase(self.tls_id, phase)
            traci.trafficlight.setPhaseDuration(self.tls_id, self.phase_durations[phase])
            self._last_phase = phase
        else:
            remaining = max(0.1, phase_start + self.phase_durations[phase] - elapsed)
            traci.trafficlight.setPhaseDuration(self.tls_id, remaining)


class FixedTimeMetrics:
    """Collect baseline metrics directly from TraCI."""

    INCOMING_EDGES = ("west_in", "east_in", "north_in", "south_in")

    def __init__(self, queue_speed_threshold: float = 0.5):
        self.queue_speed_threshold = queue_speed_threshold
        self.waiting_seconds = 0.0
        self.queue_samples = []
        self.throughput = 0
        self.departed = 0
        self.arrival_times: Dict[str, float] = {}
        self.waiting_by_vehicle: Dict[str, float] = {}
        self.travel_times = []
        self.fuel_litres = 0.0
        self.co2_kg = 0.0

    def update(self, now: float) -> None:
        vehicle_ids = traci.vehicle.getIDList()
        queue = 0
        for vehicle_id in vehicle_ids:
            self.waiting_by_vehicle[vehicle_id] = float(
                traci.vehicle.getAccumulatedWaitingTime(vehicle_id)
            )
            self.fuel_litres += float(traci.vehicle.getFuelConsumption(vehicle_id)) / 1_000_000.0
            self.co2_kg += float(traci.vehicle.getCO2Emission(vehicle_id)) / 1_000_000.0
            if traci.vehicle.getSpeed(vehicle_id) < self.queue_speed_threshold:
                road_id = traci.vehicle.getRoadID(vehicle_id)
                if road_id in self.INCOMING_EDGES:
                    queue += 1

        self.queue_samples.append(queue)
        for vehicle_id in traci.simulation.getDepartedIDList():
            self.departed += 1
            self.arrival_times[vehicle_id] = now
        for vehicle_id in traci.simulation.getArrivedIDList():
            self.throughput += 1
            departure = self.arrival_times.pop(vehicle_id, None)
            self.waiting_seconds += self.waiting_by_vehicle.pop(vehicle_id, 0.0)
            if departure is not None:
                self.travel_times.append(now - departure)

    def summary(self, duration: float) -> dict:
        return {
            "duration_s": duration,
            "vehicles_departed": self.departed,
            "vehicles_completed": self.throughput,
            "throughput_vph": round(self.throughput * 3600.0 / max(duration, 1.0), 2),
            "avg_waiting_time_s": round(self.waiting_seconds / max(self.departed, 1), 3),
            "avg_queue_vehicles": round(sum(self.queue_samples) / max(len(self.queue_samples), 1), 3),
            "max_queue_vehicles": max(self.queue_samples, default=0),
            "avg_travel_time_s": round(sum(self.travel_times) / max(len(self.travel_times), 1), 3),
            "fuel_litres": round(self.fuel_litres, 6),
            "co2_kg": round(self.co2_kg, 6),
            "controller": "fixed_time",
            "cycle": "30G-5Y-30G-5Y",
        }


def create_scenario_routes(source_path: str, scenario: str, output_path: str) -> str:
    """Create a route file containing only one traffic condition."""
    allowed_prefixes = {
        "low": ("low_", "bus_", "truck_", "bike_"),
        "normal": ("normal_", "bus_", "truck_", "bike_"),
        "rush": ("rush_", "bus_", "truck_", "bike_"),
        "congestion": ("burst_", "bus_", "truck_", "bike_"),
    }
    if scenario not in allowed_prefixes:
        raise ValueError(f"Unknown scenario '{scenario}'. Use low, normal, rush, or congestion.")

    tree = ET.parse(source_path)
    root = tree.getroot()
    prefixes = allowed_prefixes[scenario]
    for flow in list(root.findall("flow")):
        flow_id = flow.attrib.get("id", "")
        if not flow_id.startswith(prefixes):
            root.remove(flow)
    ET.indent(tree, space="    ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path


def run_fixed_time(config_path: str, route_path: str, output_path: str,
                   duration: int = 3600, tls_id: str = "C", gui: bool = False) -> dict:
    if traci is None:
        raise RuntimeError("TraCI is not installed. Install SUMO Python support first.")

    sumo_binary = "sumo-gui" if gui else "sumo"
    command = [sumo_binary, "-c", config_path, "--route-files", route_path,
               "--begin", "0", "--end", str(duration)]
    traci.start(command)
    controller = FixedTimeController(tls_id=tls_id)
    metrics = FixedTimeMetrics()
    try:
        while traci.simulation.getMinExpectedNumber() > 0 or traci.simulation.getTime() < duration:
            now = traci.simulation.getTime()
            if now >= duration:
                break
            controller.apply(now)
            traci.simulationStep()
            metrics.update(traci.simulation.getTime())
        result = metrics.summary(min(float(duration), traci.simulation.getTime()))
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        return result
    finally:
        traci.close()


def run_scenario(scenario: str, sumo_dir: str = None, duration: int = 3600,
                 output_dir: str = "results", gui: bool = False) -> dict:
    sumo_dir = sumo_dir or os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(sumo_dir, "sumocfg.sumocfg")
    source_routes = os.path.join(sumo_dir, "routes.rou.xml")
    os.makedirs(output_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        route_path = os.path.join(temp_dir, f"{scenario}.rou.xml")
        create_scenario_routes(source_routes, scenario, route_path)
        output_path = os.path.join(output_dir, f"fixed_time_{scenario}.json")
        return run_fixed_time(config_path, route_path, output_path, duration, gui=gui)
