"""QUBO to Ising conversion using x_i = (1 - z_i) / 2."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Dict, Tuple

from src.optimization.qubo_builder import QUBOModel


@dataclass(frozen=True)
class IsingModel:
    variables: Tuple[str, ...]
    fields: Dict[str, float]
    couplings: Dict[str, float]
    constant: float
    metadata: dict

    def energy(self, spins: Dict[str, int]) -> float:
        """Evaluate constant + sum(h_i z_i) + sum(J_ij z_i z_j)."""
        total = self.constant
        for variable, coefficient in self.fields.items():
            total += coefficient * int(spins.get(variable, 1))
        for pair, coefficient in self.couplings.items():
            left, right = pair.split("|")
            total += coefficient * int(spins.get(left, 1)) * int(spins.get(right, 1))
        return total

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2)
        return path


def qubo_to_ising(qubo: QUBOModel) -> IsingModel:
    """Convert an upper-triangular QUBO to an equivalent Ising model.

    For a QUBO Q(x) = offset + sum_i a_i x_i + sum_ij b_ij x_i x_j,
    substituting x_i=(1-z_i)/2 gives:

      constant += a_i/2 + b_ij/4
      h_i       += -a_i/2 - b_ij/4
      h_j       += -b_ij/4
      J_ij      += b_ij/4
    """
    fields = {variable: -coefficient / 2.0 for variable, coefficient in qubo.linear.items()}
    constant = qubo.offset + sum(qubo.linear.values()) / 2.0
    couplings = {}
    for pair, coefficient in qubo.quadratic.items():
        left, right = pair.split("|")
        constant += coefficient / 4.0
        fields[left] = fields.get(left, 0.0) - coefficient / 4.0
        fields[right] = fields.get(right, 0.0) - coefficient / 4.0
        couplings[pair] = couplings.get(pair, 0.0) + coefficient / 4.0
    return IsingModel(
        variables=qubo.variables,
        fields=fields,
        couplings=couplings,
        constant=constant,
        metadata={
            "source": "qubo",
            "substitution": "x=(1-z)/2",
            "qubo_offset": qubo.offset,
            "qubo_metadata": qubo.metadata,
        },
    )


def qubo_assignment_to_spins(qubo: QUBOModel, assignment: Dict[str, int]) -> Dict[str, int]:
    return {variable: 1 - 2 * int(assignment.get(variable, 0)) for variable in qubo.variables}
