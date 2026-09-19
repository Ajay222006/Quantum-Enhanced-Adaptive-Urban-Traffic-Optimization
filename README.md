# Quantum-Enhanced Adaptive Urban Traffic Optimization

This repository contains a multi-intersection traffic system with fixed-time,
rule-based, classical optimization, and NumPy QAOA-style control paths. It also
includes SUMO/TraCI integration, real-time state estimation, traffic
prediction, emergency green-corridor handling, and normalized environmental
metrics.

---

## Folder structure

```
quantum_traffic/
├── run_simulation.py              # CLI: run one simulation
├── requirements.txt
├── config/
│   ├── settings.py                # all constants (timing, demand, fuel, CO2)
│   └── scenarios.py               # normal / rush / accident / emergency ...
├── src/
│   ├── network/
│   │   ├── road.py                # road: queue + transit + capacity
│   │   ├── signal.py              # signal FSM: green→yellow→all-red, safety rules
│   │   ├── intersection.py        # node: approaches + NS/EW phases
│   │   └── network_builder.py     # builds 4 / 6 / 8 intersection grid + routing
│   ├── simulation/
│   │   ├── vehicle.py             # agent with route + per-vehicle stats
│   │   ├── traffic_generator.py   # Poisson arrivals, vehicle mix, demand scaling
│   │   └── simulator.py           # THE MAIN LOOP (1 tick = 1 second)
│   ├── state/
│   │   └── state_estimator.py     # raw sim → per-intersection state (optimizer input)
│   ├── control/
│   │   ├── base_controller.py     # ← the interface QAOA will implement
│   │   ├── fixed_time.py          # baseline 1
│   │   └── rule_based.py          # baseline 2 (adaptive)
│   ├── events/
│   │   └── event_manager.py       # inject congestion/accident/closure + auto-detector
│   ├── emergency/
│   │   └── emergency_manager.py   # green corridor preemption + restoration
│   └── metrics/
│       └── metrics.py             # waiting, queue, congestion, throughput, fuel, CO2
├── experiments/
│   ├── compare_controllers.py     # custom simulator comparison table
│   └── benchmark_optimizers.py   # exact classical vs NumPy QAOA
└── data/networks/                 # (later) saved SUMO / JSON networks
```

---

## How to run

```bash
cd quantum_traffic

python3 run_simulation.py                                               # fixed-time, normal
python3 run_simulation.py --controller rule_based --scenario rush
python3 run_simulation.py --controller rule_based --scenario emergency
python3 run_simulation.py --controller rule_based --scenario accident --verbose
python3 run_simulation.py --intersections 8 --duration 3600             # scalability

python3 experiments/compare_controllers.py --scenario rush
python3 experiments/benchmark_optimizers.py
```

## Installation and environment variables

The project uses these Python packages:

- `numpy`: QAOA statevector simulation and numerical operations
- `xgboost`: traffic prediction model
- `pandas`: prediction-data tooling
- `scikit-learn`: regression wrappers and MAE/RMSE/R² metrics
- `joblib`: saved prediction models
- `traci`: Python client for SUMO

Install them from the project root with PowerShell:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

SUMO itself is a separate Windows application. Install it from the official
SUMO distribution, then set these variables. With the current installation
layout, the commands are:

```powershell
$env:SUMO_HOME = 'C:\Program Files (x86)\Eclipse\Sumo'
$env:Path += ';C:\Program Files (x86)\Eclipse\Sumo\bin'
$env:PYTHONPATH = 'C:\Users\Ajay S\OneDrive\Documents\Quantex_project'
```

`SUMO_HOME` points to the SUMO installation root. `PATH` must contain the
folder containing `sumo.exe` and `sumo-gui.exe`. `PYTHONPATH` points to this
project root so imports such as `src.optimization` and `sumo` work when commands
are launched outside the root directory. These commands affect only the current
PowerShell session. Run `setup_windows.ps1` as an administrator-approved user
setup script to persist them for future terminals:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_windows.ps1
```

Verify the installation:

```powershell
sumo --version
python -c "import numpy, traci, xgboost, sklearn, joblib; print('Python dependencies OK')"
```

Qiskit is optional. The current QAOA implementation uses the NumPy statevector
simulator and does not require Qiskit. To install Qiskit Aer for a future
backend, run:

```powershell
python -m pip install -r requirements-qiskit.txt
```

The requested Qiskit stack is:

- `qiskit`: `QuantumCircuit`, Pauli operators, and core quantum circuit APIs
- `qiskit-aer`: local statevector and QASM simulators through `AerSimulator`
- `qiskit-optimization`: `QuadraticProgram`, QUBO formulation, and optimization converters
- `qiskit-algorithms`: `QAOA`, `COBYLA`, and minimum-eigenvalue algorithms

Install and verify the complete stack with:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_quantum_stack.ps1
```

Or run the commands directly:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r requirements-qiskit.txt
python -c "from qiskit import QuantumCircuit; from qiskit_aer import AerSimulator; from qiskit_optimization import QuadraticProgram; from qiskit_algorithms import QAOA; print('Qiskit quantum stack OK')"
```

No environment variables are required for Qiskit, Qiskit Aer, Qiskit
Optimization, or Qiskit Algorithms. Only SUMO requires `SUMO_HOME` and its
`bin` directory on `PATH`; the project may use `PYTHONPATH` for imports.

## Quantum-library audit

The current implementation status is explicit:

- QUBO/Ising: implemented with the project’s own `QUBOModel` and
      `qubo_to_ising()` in `src/optimization`; no Qiskit dependency is currently
      used there.
- Quantum circuits/QAOA: implemented with a NumPy statevector simulator in
      `src/optimization/qaoa_solver.py`; it currently does not use `QuantumCircuit`
      or `AerSimulator`.
- QUBO optimization: candidate plans are currently decoded and evaluated by
      the project’s hybrid solver; `QuadraticProgram` and Qiskit Optimization are
      optional and not currently imported.

Run the reproducible optimizer benchmark from the project root:

```powershell
python experiments/benchmark_optimizers.py --output results/optimizer_benchmark.json
```

It evaluates exact classical enumeration and the NumPy QAOA-style solver on
the same state-specific QUBO and reports execution time, objective value,
success probability, problem size, and objective gap. The benchmark is small
by design: the current timing encoding is a correctness and integration test,
not evidence of quantum advantage.

Sample output (rush hour, 4 intersections, 1800 s):

| Metric | Fixed | Rule-Based |
|---|---|---|
| Avg waiting time (s) | 84.99 | 60.75 |
| Avg queue (veh) | 181.77 | 123.13 |
| Throughput (veh/h) | 6100 | 6388 |
| CO₂ (kg) | 1438.9 | 1297.6 |

---

## Core logic in one picture

```
 EventManager ──► TrafficGenerator ──► Simulator ──► StateEstimator
                                          │                │
                                          │                ▼
                           EmergencyManager           Controller
                                          │        (fixed / rule / QAOA)
                                          ▼                │
                                    TrafficSignal ◄────────┘
                                          │
                                          ▼
                                    MetricsCollector
```

**Key invariant:** the controller only returns
`{intersection_id: green_seconds}`. The signal FSM clamps it to
`MIN_GREEN / MAX_GREEN` and enforces yellow + all-red, so **no controller can
ever produce an unsafe plan** — including the quantum one.

---

## Where the quantum part plugs in

1. `src/control/traffic_objective.py` — normalized weighted traffic cost
2. `src/optimization/qubo_builder.py` — state → timing variables → QUBO
3. `sumo/classical_optimizer_controller.py` — exact candidate enumeration in SUMO
4. `src/optimization/qaoa_solver.py` — QUBO → Ising → NumPy QAOA-style sampling

The custom simulator under `src/` is a fast dependency-light model for
controller comparisons. The `sumo/` modules are the live TraCI path and use
SUMO’s network, vehicles, signals, and simulation clock. They share objective
and prediction components but are separate runtime backends; results from one
backend should not be presented as measurements from the other.

---

## What is already implemented ✅

- 4 / 6 / 8 intersection network with entry/exit roads and automatic routing
- NS/EW signal phases with min/max green, yellow, all-red clearance
- Poisson demand, vehicle mix (car/bike/bus/truck), spillback, gridlock rejection
- Traffic state estimation: queue, density, flow (veh/min), capacity, signal
- Fixed-time + rule-based adaptive controllers with explainability strings
- Events: sudden congestion, accident (capacity drop), road closure, auto-restore
- Automatic anomaly detection (queue jump / saturation) — the future re-optimization trigger
- Emergency green corridor: ETA-based preemption of current + next intersection, queue jump, restoration
- Metrics: waiting time, travel time, queue, congestion index, throughput, fuel, CO₂, emergency travel time
- `sim.snapshot()` returns a ready-to-render frame for the Streamlit dashboard
- SUMO live estimator: vehicle details, approach density, queue, average speed, crossing flow, capacity, and signal phase
- XGBoost traffic prediction: chronological train/validation/test workflow with MAE, RMSE, and R² metrics

## Traffic prediction workflow

Collect a time series from SUMO at five-second intervals. Run this once for each
traffic condition and use a different `--scenario` label for each dataset:

```bash
python sumo/collect_traffic_dataset.py --scenario normal --output data/normal.csv
python sumo/collect_traffic_dataset.py --scenario rush --output data/rush.csv
python sumo/collect_traffic_dataset.py --scenario road_closure --output data/closure.csv
```

Train a 30-second predictor from a 30-second history window:

```bash
python experiments/train_traffic_predictor.py \
      --data data/normal.csv \
      --model models/traffic_predictor.joblib \
      --interval 5 --history 30 --horizon 30
```

The trained artifact is loaded by `RealTimeTrafficPredictor`. During a TraCI
loop, call `predictor.update(estimator.update(), simulation_time)` after each
estimator snapshot. Its output contains predicted density, queue, and flow for
each intersection approach and is ready to be combined with current state by a
future QUBO/QAOA controller.

## Fixed-time SUMO baseline

The fixed-time controller uses an unchanged 70-second cycle:
`30 seconds green NS, 5 seconds yellow, 30 seconds green EW, 5 seconds yellow`.
It deliberately does not read traffic density or queue length when choosing the
phase. Run one clean demand condition at a time:

```bash
python experiments/run_fixed_time_baseline.py --scenario normal --duration 3600
python experiments/run_fixed_time_baseline.py --scenario rush --duration 3600
python experiments/run_fixed_time_baseline.py --scenario congestion --duration 3600
```

Results are saved as `results/fixed_time_<scenario>.json` and include waiting
time, queue length, travel time, throughput, fuel, and CO2. The scenario runner
filters `routes.rou.xml` so the baseline does not accidentally combine all
traffic patterns in one experiment.

## Rule-based SUMO baseline

The queue-responsive controller measures the North/South and East/West incoming
queues every 10 seconds. It increases the relevant green by 5 seconds above 15
queued vehicles, decreases it below 5 vehicles, and clamps every green between
20 and 60 seconds. It uses the same scenarios and metrics as the fixed-time
baseline:

```bash
python experiments/run_rule_based_baseline.py --scenario normal --duration 3600
python experiments/run_rule_based_baseline.py --scenario rush --duration 3600
python experiments/run_rule_based_baseline.py --scenario congestion --duration 3600
```

Results are saved as `results/rule_based_<scenario>.json` for direct comparison
with the fixed-time JSON files.

## Classical optimization SUMO baseline

The classical controller measures the current North/South and East/West state
every 10 seconds and enumerates all 49 combinations of green times from
`20, 25, 30, 35, 40, 45, 50` seconds. It selects the minimum-cost pair using:

`10*queue + 2*waiting + 100*density - 4*flow*green_share`

The selected timing is sent to SUMO, and every candidate cost plus the selected
solution is saved in the result JSON for later QUBO/QAOA comparison:

```bash
python experiments/run_classical_optimizer.py --scenario normal --duration 3600
python experiments/run_classical_optimizer.py --scenario rush --duration 3600
python experiments/run_classical_optimizer.py --scenario congestion --duration 3600
```

Results are saved as `results/classical_optimizer_<scenario>.json` and contain
the same waiting, queue, travel-time, throughput, fuel, and CO2 metrics as the
two baseline controllers.

## Dynamic QUBO generation

The QUBO builder is in `src/optimization/qubo_builder.py`. It creates binary
variables such as `x_NS_20` and `x_EW_40`, where one variable per phase must be
selected. The QUBO includes one-hot penalties, candidate min/max timing domains,
5-second yellow transitions, and a practical 120-second cycle compatibility
penalty. The linear and quadratic objective coefficients are regenerated from
each traffic-state snapshot, so different SUMO states produce different QUBOs.

The objective terms use the same normalized weights as the classical optimizer;
emergency-priority mode replaces them with the documented emergency weights.
Minimum green timing is also the pedestrian/signal-safety lower bound. Emergency
delay is included in the state-dependent objective, so an active emergency
changes the QUBO rather than requiring a separate optimizer.

Build a QUBO artifact from a current state snapshot:

```bash
python experiments/build_dynamic_qubo.py \
      --state data/example_traffic_state.json \
      --output results/dynamic_qubo.json
```

The saved JSON contains variables, linear coefficients, quadratic coefficients,
penalty metadata, normalization bounds, weights, and the traffic state used to
create that QUBO. A future QAOA solver can consume `linear`, `quadratic`, and
`offset`, then decode its bitstring with `DynamicQUBOBuilder.decode()`.

## Closed-loop SUMO optimizer

`sumo/realtime_optimizer_loop.py` connects the full control loop. Every 10--30
simulation seconds it reads the live SUMO state, optionally calls the trained
traffic predictor, rebuilds the dynamic QUBO, solves the valid timing plans with
an exact hybrid fallback, and applies the selected NS/EW timings through TraCI.
The fallback enumerates the same valid one-hot plans that a future QAOA backend
will decode, so the integration contract is already fixed.

Run it without a predictor:

```bash
python experiments/run_realtime_optimizer.py --scenario rush \
      --duration 3600 --optimization-interval 10
```

Run it with a trained XGBoost artifact:

```bash
python experiments/run_realtime_optimizer.py --scenario rush \
      --model models/traffic_predictor.joblib --duration 3600
```

Each run writes `results/realtime_qubo_<scenario>.json`, including the current
state, prediction, QUBO dimensions, selected plan, and QUBO energy at every
optimization cycle.

## Automatic events and incidents

`sumo/event_detection.py` contains the transparent SUMO event layer. It detects
queue jumps of at least 8 vehicles, density increases of at least 0.15, density
above 0.75, or a flow decrease of at least 40% and 5 veh/min from a baseline of
at least 10 veh/min. This minimum-flow guard prevents small fluctuations from
being misclassified as incidents. When an event is detected, the QUBO is
regenerated immediately instead of waiting for the next scheduled interval.

Inject and clear an accident while the loop is running:

```bash
python experiments/run_realtime_optimizer.py --scenario normal \
      --duration 600 --optimization-interval 10 \
      --incident-kind accident --incident-edge west_in \
      --incident-start 120 --incident-duration 180 --capacity-factor 0.25
```

For a road closure, use:

```bash
python experiments/run_realtime_optimizer.py --scenario normal \
      --duration 600 --incident-kind road_closure \
      --incident-edge west_in --incident-start 120 --incident-duration 180
```

The incident manager reduces the affected SUMO lane speeds to model lower
capacity, restores the original speeds after the duration, and forces QUBO
regeneration at both incident start and clearance. Detector recovery messages
are recorded in the result JSON under `events`.

## Ising and QAOA backend

`src/optimization/ising.py` converts each dynamic QUBO with
`x=(1-z)/2` into an Ising Hamiltonian:

`H = constant + sum(h_i Z_i) + sum(J_ij Z_i Z_j)`

The conversion preserves the energy of every binary timing assignment. The
small-problem QAOA simulator is implemented in
`src/optimization/qaoa_solver.py` using a NumPy statevector, cost-phase
evolution, and an X mixer. It samples candidate bitstrings, rejects invalid
one-hot solutions, and falls back to exact feasible enumeration when a sample
does not satisfy the constraints. This keeps the live system reproducible even
when Qiskit is unavailable; a Qiskit backend can replace `QAOASolver` later
without changing the QUBO or SUMO interfaces.

The normalized objective is:

`w1*waiting + w2*queue + w3*congestion + w4*emergency_delay + w5*fuel + w6*co2 - w7*throughput`

The documented baseline weights are waiting `.25`, queue `.20`, congestion
`.15`, emergency delay `.15`, fuel `.10`, CO2 `.10`, and throughput `.05`.
Emergency-priority mode changes them to `.18`, `.14`, `.10`, `.35`, `.08`,
`.08`, and `.07` respectively. Metrics are normalized using explicit reference
limits stored in every result file, so units do not determine importance.

Run the weight-sensitivity experiment:

```bash
python experiments/weight_sensitivity.py --output results/weight_sensitivity.json
```

To run a SUMO experiment with emergency-priority weights:

```bash
python experiments/run_classical_optimizer.py --scenario normal --emergency-priority
```

## Next steps

Milestone 6: QUBO →
Milestone 7: classical optimizer → Milestone 8: QAOA → Milestone 12: dashboard.
#   q u a n t e x a _ p r o j e c t 
 
 