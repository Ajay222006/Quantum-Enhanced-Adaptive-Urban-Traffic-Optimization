"""Dynamic QUBO construction for SUMO signal timing decisions.

Each binary variable is x(phase, green_time). Exactly one timing is selected for
NS and EW. Traffic-dependent objective coefficients are regenerated whenever a
new state snapshot is passed to ``build``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, is_dataclass
from typing import Dict, Iterable, Mapping, Tuple

from src.control.traffic_objective import MetricBounds, ObjectiveWeights, normalize


@dataclass(frozen=True)
class QUBOModel:
    variables: Tuple[str, ...]
    linear: Dict[str, float]
    quadratic: Dict[str, float]
    offset: float
    metadata: dict

    def value(self, assignment: Mapping[str, int]) -> float:
        """Evaluate Q(x) for a binary assignment."""
        total = self.offset
        for variable, coefficient in self.linear.items():
            total += coefficient * int(assignment.get(variable, 0))
        for pair, coefficient in self.quadratic.items():
            left, right = pair.split("|")
            total += coefficient * int(assignment.get(left, 0)) * int(assignment.get(right, 0))
        return total

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2)
        return path


class DynamicQUBOBuilder:
    """Build a state-specific QUBO for one signalized intersection."""

    def __init__(self, green_times: Iterable[int] = (20, 30, 40, 50),
                 yellow: int = 5, min_green: int = 20, max_green: int = 60,
                 penalty: float = 10.0, weights: ObjectiveWeights = None,
                 bounds: MetricBounds = None):
        self.green_times = tuple(sorted(set(int(value) for value in green_times)))
        self.yellow = yellow
        self.min_green = min_green
        self.max_green = max_green
        self.penalty = penalty
        self.weights = weights or ObjectiveWeights()
        self.bounds = bounds or MetricBounds()
        if not self.green_times:
            raise ValueError("green_times must contain at least one timing")
        if any(value < min_green or value > max_green for value in self.green_times):
            raise ValueError("green_times must satisfy min_green and max_green")

    @staticmethod
    def _variable(phase: str, green_time: int) -> str:
        return f"x_{phase}_{green_time}"

    @staticmethod
    def _pair(left: str, right: str) -> str:
        return "|".join(sorted((left, right)))

    def _add_linear(self, linear: Dict[str, float], variable: str, value: float):
        linear[variable] = linear.get(variable, 0.0) + value

    def _add_quadratic(self, quadratic: Dict[str, float], left: str, right: str, value: float):
        key = self._pair(left, right)
        quadratic[key] = quadratic.get(key, 0.0) + value

    def _one_hot_penalty(self, variables, linear, quadratic, offset):
        # P * (sum(x)-1)^2 = P + sum(-P*x) + sum(2P*x_i*x_j)
        offset += self.penalty
        for variable in variables:
            self._add_linear(linear, variable, -self.penalty)
        for index, left in enumerate(variables):
            for right in variables[index + 1:]:
                self._add_quadratic(quadratic, left, right, 2.0 * self.penalty)
        return offset

    def _state_metrics(self, state: Mapping, ns_green: int, ew_green: int) -> dict:
        ns = state["NS"]
        ew = state["EW"]
        cycle = ns_green + ew_green + 2 * self.yellow
        ns_share = ns_green / cycle
        ew_share = ew_green / cycle

        def get(approach, name):
            if isinstance(approach, Mapping):
                return float(approach.get(name, 0.0))
            return float(getattr(approach, name, 0.0))

        return {
            "waiting": get(ns, "waiting") * (1 - ns_share) + get(ew, "waiting") * (1 - ew_share),
            "queue": get(ns, "queue") * (1 - ns_share) + get(ew, "queue") * (1 - ew_share),
            "congestion": get(ns, "density") * (1 - ns_share) + get(ew, "density") * (1 - ew_share),
            "emergency_delay": get(ns, "emergency_delay") * (1 - ns_share) + get(ew, "emergency_delay") * (1 - ew_share),
            "fuel": (get(ns, "fuel") + get(ew, "fuel")) * (1.0 + 0.25 * (2 - ns_share - ew_share)),
            "co2": (get(ns, "co2") + get(ew, "co2")) * (1.0 + 0.25 * (2 - ns_share - ew_share)),
            "throughput": get(ns, "flow") * ns_share + get(ew, "flow") * ew_share,
        }

    def _objective_cost(self, metrics: Mapping[str, float]) -> float:
        normalized = {
            "waiting": normalize(metrics["waiting"], self.bounds.waiting_max),
            "queue": normalize(metrics["queue"], self.bounds.queue_max),
            "congestion": normalize(metrics["congestion"], self.bounds.congestion_max),
            "emergency_delay": normalize(metrics["emergency_delay"], self.bounds.emergency_delay_max),
            "fuel": normalize(metrics["fuel"], self.bounds.fuel_max),
            "co2": normalize(metrics["co2"], self.bounds.co2_max),
            "throughput": normalize(metrics["throughput"], self.bounds.throughput_max),
        }
        return (
            self.weights.waiting * normalized["waiting"]
            + self.weights.queue * normalized["queue"]
            + self.weights.congestion * normalized["congestion"]
            + self.weights.emergency_delay * normalized["emergency_delay"]
            + self.weights.fuel * normalized["fuel"]
            + self.weights.co2 * normalized["co2"]
            - self.weights.throughput * normalized["throughput"]
        )

    def build(self, state: Mapping, emergency_active: bool = False) -> QUBOModel:
        """Regenerate a QUBO from the latest traffic snapshot."""
        weights = self.weights.for_emergency() if emergency_active else self.weights
        original_weights = self.weights
        self.weights = weights
        try:
            variables = tuple(
                self._variable(phase, green_time)
                for phase in ("NS", "EW")
                for green_time in self.green_times
            )
            linear: Dict[str, float] = {}
            quadratic: Dict[str, float] = {}
            offset = 0.0
            ns_variables = [self._variable("NS", value) for value in self.green_times]
            ew_variables = [self._variable("EW", value) for value in self.green_times]
            offset = self._one_hot_penalty(ns_variables, linear, quadratic, offset)
            offset = self._one_hot_penalty(ew_variables, linear, quadratic, offset)

            candidate_costs = {}
            base_ns = self.green_times[0]
            base_ew = self.green_times[0]
            pair_costs = {}
            for ns_time in self.green_times:
                for ew_time in self.green_times:
                    metrics = self._state_metrics(state, ns_time, ew_time)
                    cost = self._objective_cost(metrics)
                    pair_costs[(ns_time, ew_time)] = cost
                    candidate_costs[f"{ns_time}|{ew_time}"] = {
                        "cost": cost,
                        "metrics": metrics,
                    }

            base_cost = pair_costs[(base_ns, base_ew)]
            offset -= base_cost
            for ns_time in self.green_times:
                variable = self._variable("NS", ns_time)
                self._add_linear(linear, variable, pair_costs[(ns_time, base_ew)])
            for ew_time in self.green_times:
                variable = self._variable("EW", ew_time)
                self._add_linear(linear, variable, pair_costs[(base_ns, ew_time)])
            for ns_time in self.green_times:
                for ew_time in self.green_times:
                    correction = (
                        pair_costs[(ns_time, ew_time)]
                        - pair_costs[(ns_time, base_ew)]
                        - pair_costs[(base_ns, ew_time)]
                        + base_cost
                    )
                    self._add_quadratic(
                        quadratic,
                        self._variable("NS", ns_time),
                        self._variable("EW", ew_time),
                        correction,
                    )

            # Penalize incompatible simultaneous extremes: both phases cannot
            # demand the maximum green in a cycle without violating a practical
            # 120-second cycle budget including yellow transitions.
            for ns_time in self.green_times:
                for ew_time in self.green_times:
                    if ns_time + ew_time + 2 * self.yellow > 120:
                        left = self._variable("NS", ns_time)
                        right = self._variable("EW", ew_time)
                        self._add_quadratic(quadratic, left, right, self.penalty)

            serializable_state = {
                key: asdict(value) if is_dataclass(value) else dict(value)
                for key, value in state.items()
            }
            metadata = {
                "encoding": "x(phase,green_time)",
                "phases": ["NS", "EW"],
                "green_times": list(self.green_times),
                "yellow_seconds": self.yellow,
                "min_green_seconds": self.min_green,
                "max_green_seconds": self.max_green,
                "penalty": self.penalty,
                "objective": "normalized weighted multi-objective traffic cost",
                "weights": asdict(weights),
                "bounds": asdict(self.bounds),
                "emergency_active": emergency_active,
                "candidate_costs": candidate_costs,
                "dynamic_state": serializable_state,
            }
            return QUBOModel(variables, linear, quadratic, offset, metadata)
        finally:
            self.weights = original_weights

    def decode(self, assignment: Mapping[str, int]) -> dict:
        """Decode a binary solution and reject invalid one-hot assignments."""
        selected = {}
        for phase in ("NS", "EW"):
            choices = [
                green_time for green_time in self.green_times
                if int(assignment.get(self._variable(phase, green_time), 0)) == 1
            ]
            if len(choices) != 1:
                raise ValueError(f"Assignment must select exactly one {phase} timing: {choices}")
            selected[phase] = choices[0]
        return selected
