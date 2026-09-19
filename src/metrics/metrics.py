"""
Performance + environmental measurement (Phase 10 / 13 of the plan).

These six numbers are exactly the objectives the optimizer will later
minimise/maximise, so the collector is deliberately controller-agnostic:
fixed-time, rule-based, classical and QAOA runs are all scored the same way.
"""

from statistics import mean
from typing import Dict, List

from config import settings
from src.metrics.environment_estimation import EnvironmentalEstimator


class MetricsCollector:
    def __init__(self):
        # per-step time series (used by the dashboard)
        self.time: List[float] = []
        self.total_queue: List[float] = []
        self.mean_density: List[float] = []
        self.active_count: List[int] = []
        # completed vehicles
        self.completed: List = []
        self.emergency_records: List[Dict] = []
        self.final_active: List = []

    # ---------------- per-step ----------------
    def record_step(self, now: float, network, active: Dict):
        queues = [r.queue_length for r in network.roads.values() if not r.is_exit]
        dens = [r.density for r in network.roads.values() if not r.is_exit]
        self.time.append(now)
        self.total_queue.append(sum(queues))
        self.mean_density.append(mean(dens) if dens else 0.0)
        self.active_count.append(len(active))

    # ---------------- events ----------------
    def record_completion(self, vehicle, now: float):
        vehicle.finish_time = now
        vehicle.travel_time = now - vehicle.depart_time
        self.completed.append(vehicle)
        if vehicle.is_emergency:
            self.emergency_records.append({
                "id": vehicle.id,
                "travel_time_s": round(vehicle.travel_time, 1),
                "waiting_time_s": round(vehicle.waiting_time, 1),
                "stops": vehicle.stops,
            })

    # ---------------- summary ----------------
    def summary(self, duration: float, active: Dict = None) -> Dict:
        active_list = list(active.values()) if active else []
        self.final_active = active_list
        all_v = self.completed + active_list

        fuel = sum(v.fuel_l for v in all_v)
        waits = [v.waiting_time for v in self.completed] or [0.0]
        travels = [v.travel_time for v in self.completed] or [0.0]
        stops = [v.stops for v in self.completed] or [0]
        n_appr = max(1, len([1 for _ in self.total_queue]))

        emg = self.emergency_records
        estimate = EnvironmentalEstimator.estimate_scenario([
            {
                "distance_m": float(getattr(v, "distance_m", 0.0)),
                "avg_speed_kmh": float(getattr(v, "speed_kmh", 0.0)),
                "idle_time_s": float(getattr(v, "waiting_time", 0.0)),
                "stop_count": int(getattr(v, "stops", 0)),
                "acceleration_events": int(getattr(v, "acceleration_events", 0)),
                "fuel_factor": float(getattr(v, "fuel_factor", 1.0)),
            }
            for v in all_v
        ])
        return {
            "duration_s": duration,
            "vehicles_completed": len(self.completed),
            "vehicles_in_network": len(active_list),
            "avg_waiting_time_s": round(mean(waits), 2),
            "avg_travel_time_s": round(mean(travels), 2),
            "avg_stops_per_vehicle": round(mean(stops), 2),
            "avg_total_queue": round(mean(self.total_queue) if self.total_queue else 0, 2),
            "max_total_queue": round(max(self.total_queue) if self.total_queue else 0, 2),
            "congestion_index": round(mean(self.mean_density) if self.mean_density else 0, 3),
            "throughput_veh": len(self.completed),
            "throughput_vph": round(len(self.completed) * 3600.0 / max(duration, 1), 1),
            "fuel_litres": round(estimate["fuel_litres"], 3),
            "co2_kg": round(estimate["co2_kg"], 3),
            "estimated_fuel_litres": round(estimate["estimated_fuel_litres"], 3),
            "estimated_co2_kg": round(estimate["estimated_co2_kg"], 3),
            "emergency_travel_time_s": round(mean([e["travel_time_s"] for e in emg]), 1) if emg else None,
            "emergency_waiting_time_s": round(mean([e["waiting_time_s"] for e in emg]), 1) if emg else None,
        }

    # ---------------- pretty print ----------------
    @staticmethod
    def print_summary(name: str, s: Dict):
        print(f"\n=== {name} ===")
        rows = [
            ("Vehicles completed", s["vehicles_completed"]),
            ("Still in network", s["vehicles_in_network"]),
            ("Avg waiting time (s)", s["avg_waiting_time_s"]),
            ("Avg travel time (s)", s["avg_travel_time_s"]),
            ("Avg total queue (veh)", s["avg_total_queue"]),
            ("Max total queue (veh)", s["max_total_queue"]),
            ("Congestion index", s["congestion_index"]),
            ("Throughput (veh/h)", s["throughput_vph"]),
            ("Estimated fuel (litres)", s["estimated_fuel_litres"]),
            ("Estimated CO2 (kg)", s["estimated_co2_kg"]),
            ("Emergency travel time (s)", s["emergency_travel_time_s"]),
        ]
        for label, value in rows:
            if value is not None:
                print(f"  {label:<28}: {value}")
