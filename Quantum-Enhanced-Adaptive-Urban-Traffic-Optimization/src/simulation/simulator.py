"""
The simulation engine - the heart of the classical system.

One tick (1 simulated second):

  1. apply scheduled events        (congestion / accident / closure)
  2. generate new vehicles         (Poisson arrivals at entry roads)
  3. update emergency corridor     (preempt / release signals)
  4. advance vehicles in transit   (moving -> stop-line queue)
  5. step every signal FSM         (green -> yellow -> all-red -> green)
  6. run the CONTROLLER            (every CONTROL_INTERVAL seconds)  <-- QAOA hook
  7. discharge queues on green     (with spillback + emergency priority)
  8. accumulate waiting time, fuel, CO2
  9. record metrics
"""

from typing import Dict, List

from config import settings
from src.events.event_manager import EventDetector, EventManager
from src.metrics.metrics import MetricsCollector
from src.simulation.traffic_generator import TrafficGenerator
from src.state.state_estimator import StateEstimator


class Simulator:
    def __init__(self, network, controller, duration=settings.DEFAULT_DURATION,
                 profile="normal", seed=settings.RANDOM_SEED,
                 event_manager: EventManager = None, emergency=None, verbose=False):
        self.net = network
        self.controller = controller
        self.duration = duration
        self.dt = settings.TIME_STEP
        self.t = 0.0
        self.verbose = verbose

        self.generator = TrafficGenerator(network, profile, seed)
        self.estimator = StateEstimator(network)
        self.events = event_manager or EventManager()
        self.detector = EventDetector()
        self.emergency = emergency
        self.metrics = MetricsCollector()

        self.active: Dict[int, "Vehicle"] = {}
        self.discharge_counts: Dict[str, int] = {r: 0 for r in network.roads}
        self.states: Dict = {}
        self.triggers: List[str] = []

    # ---------------- vehicle movement ----------------
    def enter_vehicle(self, vehicle, now: float):
        road = self.net.roads[vehicle.current_road]
        road.transit.append([vehicle, now + road.travel_time()])
        self.active[vehicle.id] = vehicle

    def _advance_transit(self, now: float):
        for road in self.net.roads.values():
            if not road.transit:
                continue
            arrived = [e for e in road.transit if e[1] <= now]
            if not arrived:
                continue
            road.transit = [e for e in road.transit if e[1] > now]
            for vehicle, _ in arrived:
                if road.is_exit:                       # left the network
                    self.active.pop(vehicle.id, None)
                    self.metrics.record_completion(vehicle, now)
                else:
                    vehicle.stops += 1
                    if vehicle.is_emergency:
                        road.queue.appendleft(vehicle)  # ambulance jumps the queue
                    else:
                        road.queue.append(vehicle)

    def _discharge(self, now: float):
        for inter in self.net.intersections.values():
            for rid in inter.signal.green_approaches():
                road = self.net.roads[rid]
                road.discharge_credit += road.saturation_flow * self.dt
                while road.discharge_credit >= 1.0 and road.queue:
                    vehicle = road.queue[0]
                    nxt = vehicle.next_road
                    if nxt is None:                    # route ends here
                        road.queue.popleft()
                        road.discharge_credit -= 1.0
                        self.active.pop(vehicle.id, None)
                        self.metrics.record_completion(vehicle, now)
                        continue
                    nroad = self.net.roads[nxt]
                    if not nroad.has_space():          # spillback: cannot move
                        break
                    road.queue.popleft()
                    road.discharge_credit -= 1.0
                    self.discharge_counts[rid] += 1
                    vehicle.distance_m += road.length_m
                    vehicle.advance()
                    nroad.transit.append([vehicle, now + nroad.travel_time()])

            # credit does not accumulate across red phases
            for rid in inter.incoming:
                if rid not in inter.signal.green_approaches():
                    self.net.roads[rid].discharge_credit = 0.0

    def _update_vehicle_stats(self):
        idle = settings.IDLE_FUEL_L_PER_S * self.dt
        for road in self.net.roads.values():
            for vehicle in road.queue:
                vehicle.waiting_time += self.dt
                vehicle.fuel_l += idle * vehicle.fuel_factor
            if road.transit:
                move = road.free_flow_speed_ms * self.dt * settings.MOVE_FUEL_L_PER_M
                for vehicle, _ in road.transit:
                    vehicle.fuel_l += move * vehicle.fuel_factor

    # ---------------- control ----------------
    def _run_controller(self, now: float):
        self.states = self.estimator.estimate(now, self.discharge_counts)
        new_triggers = self.detector.check(now, self.states)
        if new_triggers:
            self.triggers.extend(new_triggers)
            if self.verbose:
                for msg in new_triggers:
                    print("  ! " + msg)

        decisions = self.controller.decide(self.states, now)
        for iid, green in decisions.items():
            sig = self.net.intersections[iid].signal
            if not sig.status()["preempted"]:
                sig.set_green_duration(green)

    # ---------------- main loop ----------------
    def step(self):
        now = self.t
        self.events.update(now, self.net, self.generator)

        for vehicle in self.generator.spawn(now, self.dt):
            self.enter_vehicle(vehicle, now)

        if self.emergency:
            self.emergency.update(now, self)

        self._advance_transit(now)

        for inter in self.net.intersections.values():
            inter.signal.step(self.dt, now)

        if int(now) % settings.CONTROL_INTERVAL == 0:
            self._run_controller(now)

        self._discharge(now)
        self._update_vehicle_stats()
        self.metrics.record_step(now, self.net, self.active)
        self.t += self.dt

    def run(self) -> dict:
        while self.t < self.duration:
            self.step()
            if self.verbose and int(self.t) % 300 == 0:
                print(f"  t={int(self.t):>5}s  active={len(self.active):>4}  "
                      f"queue={self.metrics.total_queue[-1]:>4}  "
                      f"done={len(self.metrics.completed)}")
        return self.metrics.summary(self.duration, self.active)

    # ---------------- dashboard support ----------------
    def snapshot(self) -> dict:
        """Everything the Streamlit dashboard needs for one frame."""
        return {
            "time": self.t,
            "intersections": {iid: st.as_dict() for iid, st in self.states.items()},
            "roads": {rid: {"queue": r.queue_length,
                            "density": round(r.density, 3),
                            "blocked": r.is_blocked}
                      for rid, r in self.net.roads.items()},
            "emergency": self.emergency.status(self.t) if self.emergency else None,
            "active_vehicles": len(self.active),
            "completed": len(self.metrics.completed),
            "events": self.events.active_log[-5:],
            "controller": self.controller.name,
        }
