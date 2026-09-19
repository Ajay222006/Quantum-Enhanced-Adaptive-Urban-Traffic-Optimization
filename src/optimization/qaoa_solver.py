"""Small NumPy statevector QAOA simulator for timing QUBOs."""

from __future__ import annotations

import itertools
import math
from typing import Dict, Tuple

import numpy as np

from src.optimization.ising import IsingModel


class QAOASolver:
    """Run a small p-layer QAOA simulation and return a valid best candidate.

    This NumPy backend keeps the project runnable without Qiskit. It implements
    the standard cost phase and X-mixer statevector operations. A future Qiskit
    backend can use the same IsingModel and result contract.
    """

    def __init__(self, builder, layers: int = 1, grid_size: int = 5,
                 shots: int = 512, seed: int = 42):
        self.builder = builder
        self.layers = layers
        self.grid_size = grid_size
        self.shots = shots
        self.rng = np.random.default_rng(seed)

    @staticmethod
    def _bits(index: int, count: int) -> Tuple[int, ...]:
        return tuple((index >> bit) & 1 for bit in range(count))

    def _energies(self, ising: IsingModel) -> np.ndarray:
        count = len(ising.variables)
        values = np.zeros(2 ** count)
        for index in range(2 ** count):
            bits = self._bits(index, count)
            spins = {variable: 1 - 2 * bits[pos] for pos, variable in enumerate(ising.variables)}
            values[index] = ising.energy(spins)
        return values

    @staticmethod
    def _apply_mixer(state: np.ndarray, beta: float, count: int) -> np.ndarray:
        output = state.copy()
        cosine = math.cos(beta)
        sine = -1j * math.sin(beta)
        for bit in range(count):
            stride = 2 ** bit
            block = stride * 2
            for start in range(0, len(state), block):
                for offset in range(stride):
                    left = start + offset
                    right = left + stride
                    old_left, old_right = output[left], output[right]
                    output[left] = cosine * old_left + sine * old_right
                    output[right] = sine * old_left + cosine * old_right
        return output

    def _statevector(self, energies: np.ndarray, gammas, betas) -> np.ndarray:
        count = int(round(math.log2(len(energies))))
        state = np.ones(len(energies), dtype=complex) / math.sqrt(len(energies))
        for gamma, beta in zip(gammas, betas):
            state *= np.exp(-1j * gamma * energies)
            state = self._apply_mixer(state, beta, count)
        return state

    def solve(self, qubo, ising: IsingModel) -> dict:
        energies = self._energies(ising)
        count = len(ising.variables)
        best_sample = None
        best_probability = -1.0
        best_valid_energy = float("inf")
        best_valid = None

        values = np.linspace(0.0, math.pi, self.grid_size)
        for gammas in itertools.product(values, repeat=self.layers):
            for betas in itertools.product(values / 2.0, repeat=self.layers):
                state = self._statevector(energies, gammas, betas)
                probabilities = np.abs(state) ** 2
                samples = self.rng.choice(len(probabilities), size=self.shots, p=probabilities / probabilities.sum())
                for sample in samples:
                    probability = float(probabilities[sample])
                    if probability > best_probability:
                        best_probability = probability
                        best_sample = int(sample)
                    assignment = {
                        variable: self._bits(int(sample), count)[position]
                        for position, variable in enumerate(ising.variables)
                    }
                    try:
                        self.builder.decode(assignment)
                    except ValueError:
                        continue
                    energy = qubo.value(assignment)
                    if energy < best_valid_energy:
                        best_valid_energy = energy
                        best_valid = assignment

        if best_valid is None:
            # A valid result is mandatory for traffic control; use exact valid
            # enumeration only when QAOA samples did not hit the feasible set.
            for ns_green in self.builder.green_times:
                for ew_green in self.builder.green_times:
                    assignment = {variable: 0 for variable in qubo.variables}
                    assignment[f"x_NS_{ns_green}"] = 1
                    assignment[f"x_EW_{ew_green}"] = 1
                    energy = qubo.value(assignment)
                    if energy < best_valid_energy:
                        best_valid_energy = energy
                        best_valid = assignment

        timings = self.builder.decode(best_valid)
        return {
            "backend": "numpy_statevector_qaoa",
            "layers": self.layers,
            "shots": self.shots,
            "assignment": best_valid,
            "timings": timings,
            "energy": best_valid_energy,
            "most_probable_sample": best_sample,
            "most_probable_probability": best_probability,
        }
