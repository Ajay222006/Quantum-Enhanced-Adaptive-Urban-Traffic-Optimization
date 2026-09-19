import collections
import os
import time
from typing import Dict, List, Tuple

try:
    import traci
except ImportError:  # pragma: no cover - only needed when SUMO is installed
    traci = None


DEFAULT_INTERSECTION_MAP = {
    "C": {
        "N": ["north_in"],
        "S": ["south_in"],
        "E": ["east_in"],
        "W": ["west_in"],
    }
}


class SumoTrafficStateEstimator:
    """Estimate live traffic state for each direction at each SUMO intersection.

    The estimator continuously reads vehicle-level data from TraCI and turns it into
    a structured state record such as:

    {
        "C": {
            "N": {
                "density": 0.72,
                "queue": 28,
                "avg_speed": 2.8,
                "flow": 51.0,
                "capacity": 100,
                "signal": "RED",
                "vehicles": ["veh_0", "veh_7", ...],
            },
            ...
        }
    }
    """

    def __init__(
        self,
        intersection_map: Dict[str, Dict[str, List[str]]] = None,
        queue_speed_threshold: float = 0.5,
        flow_window_seconds: float = 30.0,
        default_vehicle_length_m: float = 5.0,
    ):
        self.intersection_map = intersection_map or DEFAULT_INTERSECTION_MAP
        self.queue_speed_threshold = queue_speed_threshold
        self.flow_window_seconds = flow_window_seconds
        self.default_vehicle_length_m = default_vehicle_length_m

        self._flow_history: Dict[Tuple[str, str], collections.deque] = {}
        self._previous_vehicles: Dict[Tuple[str, str], set] = {}
        self._last_step_time = None

    def _ensure_history(self, intersection_id: str, direction: str):
        key = (intersection_id, direction)
        if key not in self._flow_history:
            self._flow_history[key] = collections.deque(maxlen=200)

    def _edge_capacity(self, edge_id: str) -> int:
        """Estimate approach capacity from the lane length in the SUMO network."""
        if traci is None:
            return 50

        try:
            lanes = traci.edge.getLanes(edge_id)
        except (AttributeError, TypeError, ValueError):
            return 50

        capacity = 0
        for lane in lanes:
            try:
                lane_length = traci.lane.getLength(lane)
            except (AttributeError, TypeError, ValueError):
                lane_length = 100.0
            capacity += max(1, int(lane_length / self.default_vehicle_length_m))

        return max(1, capacity)

    def _current_signal_for_intersection(self, intersection_id: str) -> Dict[str, str]:
        if traci is None:
            return {"phase": "UNKNOWN", "state": "UNKNOWN"}

        try:
            signal_ids = traci.trafficlight.getIDList()
            if intersection_id not in signal_ids:
                return {"phase": "UNKNOWN", "state": "UNKNOWN"}

            phase_index = traci.trafficlight.getPhase(intersection_id)
            state = traci.trafficlight.getRedYellowGreenState(intersection_id)
            return {
                "phase": str(phase_index),
                "state": str(state),
            }
        except (AttributeError, TypeError, ValueError):
            return {"phase": "UNKNOWN", "state": "UNKNOWN"}

    def _approach_vehicles(self, intersection_id: str, direction: str) -> List[str]:
        """Return all vehicles on the defined incoming roads for one direction."""
        if traci is None:
            return []

        approach_edges = self.intersection_map.get(intersection_id, {}).get(direction, [])
        vehicles: List[str] = []
        seen = set()

        for vehicle_id in traci.vehicle.getIDList():
            try:
                road_id = traci.vehicle.getRoadID(vehicle_id)
            except (AttributeError, TypeError, ValueError):
                continue

            if any(road_id == edge or road_id.startswith(edge) for edge in approach_edges):
                if vehicle_id not in seen:
                    vehicles.append(vehicle_id)
                    seen.add(vehicle_id)

        return vehicles

    def _flow_for_direction(self, intersection_id: str, direction: str,
                            vehicle_ids: List[str]) -> float:
        """Count vehicles leaving an approach and convert the window to veh/min."""
        current_time = traci.simulation.getTime() if traci is not None else time.time()
        self._ensure_history(intersection_id, direction)
        history = self._flow_history[(intersection_id, direction)]

        key = (intersection_id, direction)
        current_vehicles = set(vehicle_ids)
        previous_vehicles = self._previous_vehicles.get(key, set())
        crossed = len(previous_vehicles - current_vehicles) if previous_vehicles else 0
        self._previous_vehicles[key] = current_vehicles
        history.append((current_time, crossed))
        while history and current_time - history[0][0] > self.flow_window_seconds:
            history.popleft()

        window_seconds = max(self.flow_window_seconds, 1.0)
        vehicles_crossed = sum(count for _, count in history)
        return (vehicles_crossed / window_seconds) * 60.0

    def update(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        """Collect the live traffic state for all intersections and directions."""
        if traci is None:
            raise RuntimeError("TraCI is not available. SUMO must be installed for real-time state estimation.")

        result: Dict[str, Dict[str, Dict[str, float]]] = {}

        for intersection_id, directions in self.intersection_map.items():
            result[intersection_id] = {}
            signal_info = self._current_signal_for_intersection(intersection_id)

            for direction, edge_ids in directions.items():
                vehicles = self._approach_vehicles(intersection_id, direction)

                speeds = []
                queue_count = 0
                vehicle_details = []
                for vehicle_id in vehicles:
                    try:
                        speed = float(traci.vehicle.getSpeed(vehicle_id))
                        vehicle_details.append({
                            "id": vehicle_id,
                            "road_id": traci.vehicle.getRoadID(vehicle_id),
                            "lane_id": traci.vehicle.getLaneID(vehicle_id),
                            "position": round(float(traci.vehicle.getLanePosition(vehicle_id)), 2),
                            "speed": round(speed, 2),
                            "waiting_time": round(float(traci.vehicle.getWaitingTime(vehicle_id)), 2),
                        })
                    except (AttributeError, TypeError, ValueError):
                        speed = 0.0
                    speeds.append(speed)
                    if speed < self.queue_speed_threshold:
                        queue_count += 1

                capacity = 0
                for edge_id in edge_ids:
                    capacity += self._edge_capacity(edge_id)
                capacity = max(1, capacity)

                density = len(vehicles) / capacity if capacity else 0.0
                avg_speed = sum(speeds) / len(speeds) if speeds else 0.0
                flow = self._flow_for_direction(intersection_id, direction, vehicles)

                result[intersection_id][direction] = {
                    "density": round(density, 3),
                    "queue": int(queue_count),
                    "avg_speed": round(avg_speed, 2),
                    "flow": round(flow, 2),
                    "capacity": int(capacity),
                    "signal": signal_info["state"],
                    "phase": signal_info["phase"],
                    "vehicles": vehicles,
                    "vehicle_details": vehicle_details,
                }

        return result


if __name__ == "__main__":
    # Example usage when SUMO is running through TraCI.
    # Connect to the SUMO bridge first, then start the estimator.
    # Example:
    # from sumo_traci_bridge import SumoTraCIConnector
    # bridge = SumoTraCIConnector(config_path=os.path.join(os.getcwd(), 'sumo', 'sumocfg.sumocfg'))
    # bridge.start()
    # estimator = SumoTrafficStateEstimator()
    # while True:
    #     bridge.step()
    #     print(estimator.update())
    #     if traci.simulation.getTime() > 300:
    #         break
    # bridge.stop()
    print("Use this estimator alongside SUMO TraCI. Example: bridge.step(); estimator.update()")
