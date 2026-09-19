"""Closed-loop SUMO -> prediction -> QUBO -> optimizer -> SUMO control."""

from __future__ import annotations

import json
import os
from typing import Dict, Mapping

try:
    import traci
except ImportError:
    traci = None

from src.optimization.qubo_builder import DynamicQUBOBuilder
from src.optimization.ising import qubo_to_ising
from src.optimization.qaoa_solver import QAOASolver
from sumo.emergency_green_corridor import EmergencyGreenCorridorController
from sumo.event_detection import SumoEventDetector, SumoIncidentManager
from sumo.realtime_traffic_state import SumoTrafficStateEstimator


class HybridQUBOSolver:
    """Solve the small timing QUBO exactly by enumerating valid one-hot plans.

    This is the classical fallback for the future QAOA backend. It uses the
    same QUBO energy and therefore provides a reliable integration test before
    replacing the solver with a quantum or hybrid sampler.
    """

    def __init__(self, builder: DynamicQUBOBuilder):
        self.builder = builder
        self.qaoa = QAOASolver(builder, layers=1, grid_size=3, shots=128)

    def solve(self, model) -> dict:
        ising = qubo_to_ising(model)
        result = self.qaoa.solve(model, ising)
        result["ising"] = {
            "fields": len(ising.fields),
            "couplings": len(ising.couplings),
            "constant": ising.constant,
        }
        return result


class RealtimeSUMOOptimizer:
    """Run a live closed-loop optimizer against one SUMO traffic light."""

    def __init__(self, tls_id: str = "C", optimization_interval: int = 10,
                 model_path: str = None, emergency_active: bool = False,
                 incident: SumoIncidentManager = None):
        self.tls_id = tls_id
        self.optimization_interval = optimization_interval
        self.estimator = SumoTrafficStateEstimator()
        self.builder = DynamicQUBOBuilder()
        self.solver = HybridQUBOSolver(self.builder)
        self.predictor = None
        self.emergency_active = emergency_active
        self.emergency_corridor = EmergencyGreenCorridorController(tls_ids=[tls_id])
        self.plan = {"NS": 30, "EW": 30}
        self.last_phase = None
        self.optimization_log = []
        self.event_detector = SumoEventDetector()
        self.incident = incident
        self.event_log = []
        self.next_optimization = 0.0

        if model_path:
            from src.prediction.traffic_prediction import RealTimeTrafficPredictor
            self.predictor = RealTimeTrafficPredictor(model_path)

    @staticmethod
    def _value(record: Mapping, name: str, default: float = 0.0) -> float:
        try:
            return float(record.get(name, default))
        except (AttributeError, TypeError, ValueError):
            return default

    def _direction_state(self, records: Mapping[str, Mapping], directions) -> dict:
        selected = [records.get(direction, {}) for direction in directions]
        return {
            "queue": sum(self._value(item, "queue") for item in selected),
            "density": sum(self._value(item, "density") for item in selected) / max(len(selected), 1),
            "waiting": sum(
                self._value(vehicle, "waiting_time")
                for item in selected
                for vehicle in item.get("vehicle_details", [])
            ),
            "flow": sum(self._value(item, "flow") for item in selected),
            "capacity": sum(self._value(item, "capacity") for item in selected),
            "emergency_delay": 0.0,
            "fuel": 0.0,
            "co2": 0.0,
        }

    def _qubo_state(self, current: Mapping, predicted: Mapping = None) -> dict:
        """Aggregate N/S and E/W SUMO approaches for the two-phase QUBO."""
        predicted = predicted or {}
        state = {"C": current.get("C", {})}
        result = {
            "NS": self._direction_state(state["C"], ("N", "S")),
            "EW": self._direction_state(state["C"], ("E", "W")),
        }
        for phase, directions in (("NS", ("N", "S")), ("EW", ("E", "W"))):
            forecast_records = predicted.get("C", {})
            if not forecast_records:
                continue
            forecast = self._direction_state(forecast_records, directions)
            for name in ("queue", "density", "flow"):
                result[phase][name] = (result[phase][name] + forecast[name]) / 2.0
        return result

    def _apply_current_phase(self):
        phase = traci.trafficlight.getPhase(self.tls_id)
        if phase == 0:
            duration = self.plan["NS"]
        elif phase == 2:
            duration = self.plan["EW"]
        else:
            return
        if phase != self.last_phase:
            traci.trafficlight.setPhaseDuration(self.tls_id, duration)
            self.last_phase = phase

    def optimize_once(self, simulation_time: float, current: Mapping = None,
                      trigger: str = "scheduled") -> dict:
        current = current or self.estimator.update()
        prediction = {}
        if self.predictor is not None:
            prediction = self.predictor.update(current, simulation_time)

        arrival_times = {
            "C": 12.0,
            "I1": 27.0,
            "I2": 43.0,
            "I3": 59.0,
        }
        emergency_state = self.emergency_corridor.attach_emergency_priority(
            current,
            arrival_times=arrival_times,
        )
        for signal_id, signal_data in emergency_state.items():
            if signal_id not in current:
                continue
            current[signal_id] = signal_data

        state = self._qubo_state(current, prediction)
        if self.emergency_active or self.emergency_corridor.is_emergency_active():
            for phase in ("NS", "EW"):
                state[phase]["emergency_delay"] = max(
                    float(state[phase].get("emergency_delay", 0.0)),
                    8.0,
                )
        model = self.builder.build(state, emergency_active=self.emergency_active or self.emergency_corridor.is_emergency_active())
        solution = self.solver.solve(model)
        self.plan = solution["timings"]
        self.last_phase = None
        self._apply_current_phase()
        record = {
            "time": simulation_time,
            "trigger": trigger,
            "current_state": current,
            "predicted_state": prediction,
            "qubo": {
                "variables": len(model.variables),
                "linear_terms": len(model.linear),
                "quadratic_terms": len(model.quadratic),
                "offset": model.offset,
            },
            "ising": solution["ising"],
            "solution": solution["timings"],
            "energy": solution["energy"],
        }
        self.optimization_log.append(record)
        return record

    def step(self, simulation_time: float):
        incident_messages = []
        if self.incident:
            incident_messages = self.incident.update(simulation_time)
            self.event_log.extend(incident_messages)
        current = self.estimator.update()
        detected = self.event_detector.check(simulation_time, current)
        self.event_log.extend(event.message for event in detected)
        self._apply_current_phase()
        forced = bool(detected or incident_messages)
        scheduled = simulation_time >= self.next_optimization
        if forced or scheduled:
            trigger = "incident" if incident_messages else ("event" if detected else "scheduled")
            result = self.optimize_once(simulation_time, current, trigger)
            self.next_optimization = simulation_time + self.optimization_interval
            return result
        return None


def run_closed_loop(config_path: str, route_path: str, output_path: str,
                    duration: int = 3600, optimization_interval: int = 10,
                    model_path: str = None, gui: bool = False,
                    emergency_active: bool = False,
                    incident: SumoIncidentManager = None) -> dict:
    if traci is None:
        raise RuntimeError("TraCI is not installed. Install SUMO Python support first.")
    if optimization_interval < 10 or optimization_interval > 30:
        raise ValueError("optimization_interval must be between 10 and 30 seconds")

    sumo_binary = "sumo-gui" if gui else "sumo"
    traci.start([sumo_binary, "-c", config_path, "--route-files", route_path,
                 "--begin", "0", "--end", str(duration)])
    controller = RealtimeSUMOOptimizer(
        optimization_interval=optimization_interval,
        model_path=model_path,
        emergency_active=emergency_active,
        incident=incident,
    )
    try:
        while traci.simulation.getMinExpectedNumber() > 0 or traci.simulation.getTime() < duration:
            now = traci.simulation.getTime()
            if now >= duration:
                break
            controller.step(now)
            traci.simulationStep()
        result = {
            "controller": "realtime_qubo_hybrid",
            "duration_s": min(float(duration), traci.simulation.getTime()),
            "optimization_interval_s": optimization_interval,
            "prediction_enabled": model_path is not None,
            "emergency_priority": emergency_active,
            "optimization_steps": len(controller.optimization_log),
            "final_plan": controller.plan,
            "events": controller.event_log,
            "optimization_log": controller.optimization_log,
        }
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        return result
    finally:
        traci.close()
