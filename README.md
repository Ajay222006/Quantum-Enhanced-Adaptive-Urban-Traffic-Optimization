# Quantum-Enhanced Adaptive Urban Traffic Optimization — Stage 1 (Classical Core)

This is **Milestones 1–4** of the project: a fully working multi-intersection
real-time traffic system with **no optimization technique inside yet**.
Fixed-time and rule-based control, dynamic events, emergency green corridor,
and all six objective metrics already work — so when QUBO/QAOA is added later,
you only write **one new controller class**.

Runs on plain Python 3 — **no external packages needed** for this stage.

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
│   └── compare_controllers.py     # the comparison table
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
```

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

1. `src/optimization/objective.py` — weighted cost from `IntersectionState`
2. `src/optimization/qubo_builder.py` — state → decision variables `x(i,p,t)` → QUBO matrix
3. `src/control/classical_opt.py` — solves the same QUBO with brute force / simulated annealing
4. `src/control/qaoa_controller.py` — QUBO → Ising → QAOA (Qiskit Aer) → best bitstring → green times

Each one subclasses `BaseController` and is added to `CONTROLLERS` in
`run_simulation.py` and `experiments/compare_controllers.py`. Nothing else changes.

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
