"""Small NumPy statevector QAOA simulator for timing QUBOs."""

from __future__ import annotations

import itertools
import math
import time
from typing import Dict, Tuple

import numpy as np

from src.optimization.ising import IsingModel


class QAOASolver:
    """Run a classical-optimized QAOA-style ansatz on the timing QUBO.

    The optimizer searches over QAOA parameters (gamma and beta) using a simple
    classical optimizer, then samples the prepared state. This keeps the code
    runnable without Qiskit while still following the expected hybrid workflow.
    """

    def __init__(self, builder, layers: int = 1, grid_size: int = 5,
                 shots: int = 512, seed: int = 42, optimizer_steps: int = 40):
        self.builder = builder
        self.layers = layers
        self.grid_size = grid_size
        self.shots = shots
        self.rng = np.random.default_rng(seed)
        self.optimizer_steps = optimizer_steps

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

    def _optimize_parameters(self, energies: np.ndarray) -> Tuple[Tuple[float, ...], Tuple[float, ...], float]:
        """Classically optimize QAOA parameters using a small random-search loop."""
        best_score = float("inf")
        best_gammas = tuple(0.0 for _ in range(self.layers))
        best_betas = tuple(0.0 for _ in range(self.layers))

        coarse_gamma = np.linspace(0.0, math.pi, self.grid_size)
        coarse_beta = np.linspace(0.0, math.pi / 2.0, self.grid_size)
        candidate_gammas = list(itertools.product(coarse_gamma, repeat=self.layers))
        candidate_betas = list(itertools.product(coarse_beta, repeat=self.layers))

        for gammas in candidate_gammas:
            for betas in candidate_betas:
                state = self._statevector(energies, gammas, betas)
                probs = np.abs(state) ** 2
                score = float(np.sum(probs * energies))
                if score < best_score:
                    best_score = score
                    best_gammas = tuple(float(value) for value in gammas)
                    best_betas = tuple(float(value) for value in betas)

        for _ in range(self.optimizer_steps):
            gammas = tuple(float(self.rng.uniform(0.0, math.pi)) for _ in range(self.layers))
            betas = tuple(float(self.rng.uniform(0.0, math.pi / 2.0)) for _ in range(self.layers))
            state = self._statevector(energies, gammas, betas)
            probs = np.abs(state) ** 2
            score = float(np.sum(probs * energies))
            if score < best_score:
                best_score = score
                best_gammas = gammas
                best_betas = betas

        return best_gammas, best_betas, best_score

    def solve(self, qubo, ising: IsingModel) -> dict:
        start = time.perf_counter()
        energies = self._energies(ising)
        count = len(ising.variables)
        best_sample = None
        best_probability = -1.0
        best_valid_energy = float("inf")
        best_valid = None
        classical_fallback_used = False

        gammas, betas, _ = self._optimize_parameters(energies)
        state = self._statevector(energies, gammas, betas)
        probabilities = np.abs(state) ** 2
        probabilities_sum = probabilities.sum()
        if probabilities_sum <= 0.0:
            probabilities = np.ones_like(probabilities) / len(probabilities)
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
            classical_fallback_used = True
            for ns_green in self.builder.green_times:
                for ew_green in self.builder.green_times:
                    assignment = {variable: 0 for variable in qubo.variables}
                    assignment[f"x_NS_{ns_green}"] = 1
                    assignment[f"x_EW_{ew_green}"] = 1
                    energy = qubo.value(assignment)
                    if energy < best_valid_energy:
                        best_valid_energy = energy
                        best_valid = assignment

        if best_valid is None:
            raise ValueError("No valid signal assignment could be found for the current QUBO.")

        timings = self.builder.decode(best_valid)
        elapsed = time.perf_counter() - start
        return {
            "backend": "numpy_statevector_qaoa",
            "layers": self.layers,
            "shots": self.shots,
            "assignment": best_valid,
            "timings": timings,
            "energy": best_valid_energy,
            "most_probable_sample": best_sample,
            "most_probable_probability": float(best_probability),
            "execution_time_s": float(elapsed),
            "objective_value": float(best_valid_energy),
            "solution_quality": "optimal" if classical_fallback_used else "sampled",
            "success_probability": float(best_probability),
            "problem_size": int(len(qubo.variables)),
            "classical_fallback_used": bool(classical_fallback_used),
            "optimizer_parameters": {"gammas": list(map(float, gammas)), "betas": list(map(float, betas))},
        }
