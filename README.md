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

## Next steps

Milestone 5: short-term prediction (XGBoost) → Milestone 6: QUBO →
Milestone 7: classical optimizer → Milestone 8: QAOA → Milestone 12: dashboard.
