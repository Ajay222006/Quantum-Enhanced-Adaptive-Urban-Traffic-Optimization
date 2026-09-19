"""Normalized multi-objective traffic cost shared by classical and QUBO solvers."""

from dataclasses import dataclass, asdict
from typing import Mapping


@dataclass(frozen=True)
class ObjectiveWeights:
    """Baseline priorities; all weights sum to one.

    Waiting and queues receive the largest normal-traffic weights. Emergency
    delay is smaller in normal operation and can be raised temporarily by
    ``for_emergency()``. Throughput is a benefit, so its term is subtracted.
    """

    waiting: float = 0.25
    queue: float = 0.20
    congestion: float = 0.15
    emergency_delay: float = 0.15
    fuel: float = 0.10
    co2: float = 0.10
    throughput: float = 0.05

    def __post_init__(self):
        if abs(sum(asdict(self).values()) - 1.0) > 1e-9:
            raise ValueError("Objective weights must sum to 1.0")

    def for_emergency(self) -> "ObjectiveWeights":
        """Prioritize emergency delay while retaining normal traffic objectives."""
        return ObjectiveWeights(
            waiting=0.18, queue=0.14, congestion=0.10,
            emergency_delay=0.35, fuel=0.08, co2=0.08, throughput=0.07,
        )


@dataclass(frozen=True)
class MetricBounds:
    """Reference ranges used to normalize metrics to approximately [0, 1]."""

    waiting_max: float = 300.0
    queue_max: float = 100.0
    congestion_max: float = 1.0
    emergency_delay_max: float = 180.0
    fuel_max: float = 10.0
    co2_max: float = 25.0
    throughput_max: float = 100.0


def normalize(value: float, maximum: float) -> float:
    return max(0.0, min(1.0, float(value) / max(maximum, 1e-9)))


def calculate_overall_cost(metrics: Mapping[str, float],
                           weights: ObjectiveWeights = None,
                           bounds: MetricBounds = None) -> dict:
    """Return normalized components and the weighted overall cost.

    Expected metric keys are waiting, queue, congestion, emergency_delay, fuel,
    co2, and throughput. The returned components are deliberately explicit so
    the exact objective can be audited and translated into QUBO terms later.
    """
    weights = weights or ObjectiveWeights()
    bounds = bounds or MetricBounds()
    normalized = {
        "waiting": normalize(metrics.get("waiting", 0.0), bounds.waiting_max),
        "queue": normalize(metrics.get("queue", 0.0), bounds.queue_max),
        "congestion": normalize(metrics.get("congestion", 0.0), bounds.congestion_max),
        "emergency_delay": normalize(metrics.get("emergency_delay", 0.0), bounds.emergency_delay_max),
        "fuel": normalize(metrics.get("fuel", 0.0), bounds.fuel_max),
        "co2": normalize(metrics.get("co2", 0.0), bounds.co2_max),
        "throughput": normalize(metrics.get("throughput", 0.0), bounds.throughput_max),
    }
    contributions = {
        "waiting": weights.waiting * normalized["waiting"],
        "queue": weights.queue * normalized["queue"],
        "congestion": weights.congestion * normalized["congestion"],
        "emergency_delay": weights.emergency_delay * normalized["emergency_delay"],
        "fuel": weights.fuel * normalized["fuel"],
        "co2": weights.co2 * normalized["co2"],
        "throughput": -weights.throughput * normalized["throughput"],
    }
    return {
        "normalized": normalized,
        "contributions": contributions,
        "cost": sum(contributions.values()),
        "weights": asdict(weights),
        "bounds": asdict(bounds),
    }
