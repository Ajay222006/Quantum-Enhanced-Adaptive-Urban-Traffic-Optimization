"""Estimated fuel and CO2 estimation for SUMO traffic scenarios.

This module intentionally reports estimated values rather than real-world
measurements, because a SUMO simulation does not directly observe physical fuel
use or emissions. It uses vehicle-level information such as travel distance,
average speed, idle time, stop count, and acceleration events, which are all
available in the simulation records or can be collected from TraCI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional

from config import settings


@dataclass
class EnvironmentalEstimate:
    fuel_litres: float
    co2_kg: float
    idle_time_s: float = 0.0
    distance_m: float = 0.0
    avg_speed_kmh: float = 0.0
    stop_count: int = 0
    acceleration_events: int = 0

    @property
    def estimated_fuel_litres(self) -> float:
        return self.fuel_litres

    @property
    def estimated_co2_kg(self) -> float:
        return self.co2_kg


class EnvironmentalEstimator:
    """Estimate fuel burn and CO2 emissions from vehicle-level traffic data."""

    @staticmethod
    def estimate_vehicle(
        distance_m: float,
        avg_speed_kmh: float,
        idle_time_s: float,
        stop_count: int = 0,
        acceleration_events: int = 0,
        fuel_factor: float = 1.0,
    ) -> Dict[str, float]:
        """Estimate fuel and CO2 for one vehicle using a practical emission model."""
        distance_km = max(0.0, distance_m / 1000.0)
        speed_mps = max(0.0, avg_speed_kmh / 3.6)

        moving_fuel = distance_km * 0.08 * fuel_factor
        idle_fuel = idle_time_s * settings.IDLE_FUEL_L_PER_S * fuel_factor
        stop_penalty = stop_count * 0.002 * fuel_factor
        accel_penalty = acceleration_events * 0.0015 * fuel_factor

        if speed_mps > 0:
            cruise_efficiency = 1.0 / max(speed_mps, 1.0)
        else:
            cruise_efficiency = 0.0

        fuel_litres = max(0.0, moving_fuel + idle_fuel + stop_penalty + accel_penalty + cruise_efficiency * 0.005)
        co2_kg = fuel_litres * settings.CO2_G_PER_LITRE / 1000.0

        return {
            "distance_m": float(distance_m),
            "avg_speed_kmh": float(avg_speed_kmh),
            "idle_time_s": float(idle_time_s),
            "stop_count": int(stop_count),
            "acceleration_events": int(acceleration_events),
            "fuel_litres": round(float(fuel_litres), 6),
            "co2_kg": round(float(co2_kg), 6),
            "estimated_fuel_litres": round(float(fuel_litres), 6),
            "estimated_co2_kg": round(float(co2_kg), 6),
        }

    @classmethod
    def estimate_scenario(
        cls,
        vehicle_records: Iterable[Mapping[str, float]],
    ) -> Dict[str, float]:
        """Aggregate fuel and CO2 estimates for a scenario from vehicle records."""
        total_distance_m = 0.0
        total_idle_s = 0.0
        total_stop_count = 0
        total_accel = 0
        total_fuel = 0.0

        for record in vehicle_records:
            distance_m = float(record.get("distance_m", 0.0))
            avg_speed_kmh = float(record.get("avg_speed_kmh", 0.0))
            idle_time_s = float(record.get("idle_time_s", 0.0))
            stop_count = int(record.get("stop_count", 0))
            acceleration_events = int(record.get("acceleration_events", 0))
            fuel_factor = float(record.get("fuel_factor", 1.0))

            estimate = cls.estimate_vehicle(
                distance_m=distance_m,
                avg_speed_kmh=avg_speed_kmh,
                idle_time_s=idle_time_s,
                stop_count=stop_count,
                acceleration_events=acceleration_events,
                fuel_factor=fuel_factor,
            )
            total_distance_m += distance_m
            total_idle_s += idle_time_s
            total_stop_count += stop_count
            total_accel += acceleration_events
            total_fuel += estimate["fuel_litres"]

        return {
            "vehicles": int(len(list(vehicle_records))),
            "total_distance_m": round(total_distance_m, 2),
            "total_idle_time_s": round(total_idle_s, 2),
            "total_stops": int(total_stop_count),
            "total_acceleration_events": int(total_accel),
            "estimated_fuel_litres": round(total_fuel, 6),
            "estimated_co2_kg": round(total_fuel * settings.CO2_G_PER_LITRE / 1000.0, 6),
            "fuel_litres": round(total_fuel, 6),
            "co2_kg": round(total_fuel * settings.CO2_G_PER_LITRE / 1000.0, 6),
        }

    @staticmethod
    def from_sumo_vehicle(vehicle) -> Dict[str, float]:
        """Create a record from a SUMO vehicle-like object when those values are available."""
        try:
            speed_kmh = float(vehicle.speed_kmh)
        except Exception:
            speed_kmh = 0.0
        try:
            distance_m = float(vehicle.distance_m)
        except Exception:
            distance_m = 0.0
        try:
            idle_time_s = float(vehicle.idle_time_s)
        except Exception:
            idle_time_s = 0.0
        try:
            stops = int(vehicle.stop_count)
        except Exception:
            stops = 0
        try:
            accel = int(vehicle.acceleration_events)
        except Exception:
            accel = 0
        try:
            factor = float(vehicle.fuel_factor)
        except Exception:
            factor = 1.0

        return EnvironmentalEstimator.estimate_vehicle(
            distance_m=distance_m,
            avg_speed_kmh=speed_kmh,
            idle_time_s=idle_time_s,
            stop_count=stops,
            acceleration_events=accel,
            fuel_factor=factor,
        )


if __name__ == "__main__":
    sample = EnvironmentalEstimator.estimate_vehicle(
        distance_m=1500.0,
        avg_speed_kmh=35.0,
        idle_time_s=18.0,
        stop_count=3,
        acceleration_events=4,
    )
    print(sample)
