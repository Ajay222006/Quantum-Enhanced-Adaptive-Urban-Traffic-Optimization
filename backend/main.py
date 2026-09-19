"""FastAPI bridge for the live SUMO/TraCI traffic application.

SUMO remains the source of truth. Before SUMO is started, endpoints return an
explicit disconnected status and no synthetic traffic snapshot is generated.
Run with: uvicorn backend.main:app --reload
"""

from __future__ import annotations

import asyncio
import copy
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sumo.realtime_optimizer_loop import RealtimeSUMOOptimizer
from sumo.sumo_traci_bridge import SumoTraCIConnector

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMO_CONFIG = PROJECT_ROOT / "sumo" / "sumocfg.sumocfg"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


class StartRequest(BaseModel):
    gui: bool = False
    optimization_interval: int = Field(default=10, ge=10, le=30)
    duration: int = Field(default=3600, gt=0)


class SignalCommand(BaseModel):
    phase: int = Field(ge=0)


@dataclass
class RuntimeSnapshot:
    status: str = "DISCONNECTED"
    error: str | None = None
    simulation_time: float | None = None
    state: dict[str, Any] | None = None
    controller: str = "hybrid_qaoa"
    optimization: dict[str, Any] | None = None
    signals: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    prediction: dict[str, Any] = field(default_factory=dict)
    updated_at: float | None = None


@dataclass
class SumoRuntime:
    snapshot: RuntimeSnapshot = field(default_factory=RuntimeSnapshot)
    lock: threading.RLock = field(default_factory=threading.RLock)
    command_queue: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    connector: SumoTraCIConnector | None = None
    optimizer: RealtimeSUMOOptimizer | None = None
    duration: int = 3600
    optimization_interval: int = 10

    def public_snapshot(self) -> dict[str, Any]:
        with self.lock:
            current = self.snapshot
            state = current.state
            intersections = []
            if state:
                for intersection_id, directions in state.items():
                    all_records = list(directions.values())
                    vehicles = [vehicle for record in all_records for vehicle in record.get("vehicle_details", [])]
                    intersections.append({
                        "id": intersection_id,
                        "directions": directions,
                        "vehicle_count": len(vehicles),
                        "queue": sum(record.get("queue", 0) for record in all_records),
                        "density": round(sum(record.get("density", 0.0) for record in all_records) / max(len(all_records), 1), 3),
                        "average_speed": round(sum(record.get("avg_speed", 0.0) for record in all_records) / max(len(all_records), 1), 2),
                        "signal": current.signals.get(intersection_id, {}),
                        "optimized_timing": (current.optimization or {}).get("solution", {}),
                    })
            return {
                "status": current.status,
                "error": current.error,
                "simulation_time": current.simulation_time,
                "controller": current.controller,
                "optimization": current.optimization,
                "signals": current.signals,
                "metrics": current.metrics,
                "events": current.events,
                "prediction": current.prediction,
                "updated_at": current.updated_at,
                "intersections": intersections,
                "source": "SUMO TraCI" if state is not None else None,
            }

    def start(self, request: StartRequest) -> None:
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError("SUMO is already running")
            self.duration = request.duration
            self.optimization_interval = request.optimization_interval
            self.stop_event.clear()
            self.snapshot = RuntimeSnapshot(status="STARTING", controller="hybrid_qaoa")
            self.thread = threading.Thread(target=self._run, args=(request.gui,), daemon=True)
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        with self.lock:
            if self.snapshot.status != "ERROR":
                self.snapshot.status = "STOPPING"
            self.snapshot.updated_at = time.time()

    def enqueue_signal(self, tls_id: str, phase: int) -> None:
        with self.lock:
            if self.snapshot.status != "CONNECTED":
                raise RuntimeError("SUMO is not connected")
            self.command_queue.append(("phase", {"tls_id": tls_id, "phase": phase}))

    def _run(self, gui: bool) -> None:
        while not self.stop_event.is_set():
            connector = None
            completed = False
            try:
                with self.lock:
                    self.snapshot.status = "CONNECTING"
                    self.snapshot.error = None
                connector = SumoTraCIConnector(config_path=str(DEFAULT_SUMO_CONFIG), gui=gui)
                connector.start()
                optimizer = RealtimeSUMOOptimizer(optimization_interval=self.optimization_interval)
                with self.lock:
                    self.connector = connector
                    self.optimizer = optimizer
                    self.snapshot.status = "CONNECTED"

                while not self.stop_event.is_set():
                    now_before = connector.get_simulation_time()
                    if now_before is None or now_before >= self.duration:
                        completed = True
                        break
                    self._apply_commands()
                    connector.step()
                    now = connector.get_simulation_time()
                    if now is None:
                        raise RuntimeError("SUMO TraCI connection closed during simulation")
                    state = optimizer.estimator.update()
                    vehicle_metrics = connector.get_vehicle_metrics()
                    signal_info = connector.get_signal_info(optimizer.tls_id)
                    detected = optimizer.event_detector.check(now, state)
                    optimizer.event_log.extend(event.message for event in detected)
                    optimization = None
                    if detected or now >= optimizer.next_optimization:
                        trigger = "event" if detected else "scheduled"
                        optimization = optimizer.optimize_once(
                            now, current=copy.deepcopy(state), trigger=trigger
                        )
                        optimizer.next_optimization = now + optimizer.optimization_interval
                    with self.lock:
                        self.snapshot.simulation_time = now
                        self.snapshot.state = state
                        previous_metrics = self.snapshot.metrics
                        flow_per_minute = sum(
                            float(record.get("flow", 0.0))
                            for directions in state.values()
                            for record in directions.values()
                        )
                        self.snapshot.metrics = {
                            "active_vehicles": vehicle_metrics["active_vehicles"],
                            "queue_vehicles": sum(
                                int(record.get("queue", 0))
                                for directions in state.values()
                                for record in directions.values()
                            ),
                            "average_wait_seconds": round(
                                vehicle_metrics["total_waiting_seconds"] / max(vehicle_metrics["active_vehicles"], 1), 2
                            ),
                            "average_speed_mps": vehicle_metrics["average_speed_mps"],
                            "throughput_vehicles_per_hour": round(flow_per_minute * 60.0, 2),
                            "estimated_fuel_litres": round(
                                float(previous_metrics.get("estimated_fuel_litres", 0.0)) + vehicle_metrics["fuel_litres_per_second"], 4
                            ),
                            "estimated_co2_kg": round(
                                float(previous_metrics.get("estimated_co2_kg", 0.0)) + vehicle_metrics["co2_kg_per_second"], 4
                            ),
                            "environment_label": "Simulation-based estimates",
                        }
                        self.snapshot.signals = {optimizer.tls_id: signal_info}
                        self.snapshot.events = [
                            {"time": event.time, "kind": event.kind, "location": f"{event.intersection}/{event.direction}", "message": event.message}
                            for event in optimizer.event_detector.events[-20:]
                        ]
                        self.snapshot.prediction = (optimization or {}).get("predicted_state", {})
                        if optimization is not None:
                            self.snapshot.optimization = optimization
                        self.snapshot.updated_at = time.time()

                with self.lock:
                    if completed:
                        self.snapshot.status = "COMPLETED"
                    elif self.stop_event.is_set():
                        self.snapshot.status = "STOPPED"
            except Exception as exc:
                with self.lock:
                    self.snapshot.status = "RECONNECTING"
                    self.snapshot.error = f"{type(exc).__name__}: {exc}"
                    self.snapshot.updated_at = time.time()
            finally:
                if connector is not None:
                    connector.stop()
                with self.lock:
                    self.connector = None
                    self.optimizer = None
            if completed or self.stop_event.is_set():
                break
            self.stop_event.wait(2.0)

    def _apply_commands(self) -> None:
        with self.lock:
            commands = self.command_queue[:]
            self.command_queue.clear()
            connector = self.connector
        if connector is None:
            return
        for command, payload in commands:
            if command == "phase":
                connector.set_signal_phase(payload["tls_id"], payload["phase"])


runtime = SumoRuntime()
app = FastAPI(title="Quantum Traffic SUMO API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    data = runtime.public_snapshot()
    return {"service": "ok", "sumo": data["status"], "source": data["source"], "error": data["error"]}


@app.get("/api/status")
def status() -> dict[str, Any]:
    data = runtime.public_snapshot()
    return {
        "sumo": data["status"],
        "traci": data["status"],
        "prediction": "ACTIVE" if data.get("prediction") else "READY",
        "classical_optimizer": "READY" if data["status"] in {"CONNECTED", "CONNECTING", "RECONNECTING"} else "OFFLINE",
        "qaoa": "READY" if data["status"] in {"CONNECTED", "CONNECTING", "RECONNECTING"} else "OFFLINE",
        "emergency": "NORMAL",
        "incident_detection": "ACTIVE" if data["status"] == "CONNECTED" else "INACTIVE",
        "error": data["error"],
    }


@app.get("/api/snapshot")
def snapshot() -> dict[str, Any]:
    return runtime.public_snapshot()


@app.post("/api/simulation/start")
def start_simulation(request: StartRequest) -> dict[str, Any]:
    try:
        runtime.start(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return runtime.public_snapshot()


@app.post("/api/simulation/stop")
def stop_simulation() -> dict[str, Any]:
    runtime.stop()
    return runtime.public_snapshot()


@app.post("/api/signals/{tls_id}/phase")
def set_phase(tls_id: str, command: SignalCommand) -> dict[str, Any]:
    try:
        runtime.enqueue_signal(tls_id, command.phase)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"queued": True, "tls_id": tls_id, "phase": command.phase}


@app.websocket("/ws/live")
async def live_updates(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(runtime.public_snapshot())
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, RuntimeError):
        return


# Keep API routes above this mount. StaticFiles serves the existing dashboard
# and its linked HTML/CSS/JavaScript pages from the same origin as the API.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
