import os
import shutil
import subprocess
import sys
import time
from typing import Dict, List

try:
    import traci
except ImportError:
    traci = None


class SumoTraCIConnector:
    """Bridge between the Python controller system and a SUMO traffic model."""

    def __init__(self, sumo_binary=None, config_path=None, gui=False, port=8813):
        self.gui = gui
        self.port = port
        self.process = None
        self.connected = False
        self.config_path = os.path.abspath(config_path or os.path.join(os.path.dirname(__file__), 'sumocfg.sumocfg'))
        self.sumo_binary = self._resolve_sumo_binary(sumo_binary)

    def _resolve_sumo_binary(self, preferred=None):
        candidates = []
        if preferred:
            candidates.append(preferred)

        if self.gui:
            candidates += ['sumo-gui', 'sumo-gui.exe']
        candidates += ['sumo', 'sumo.exe']

        if os.name == 'nt':
            win_dirs = [
                r'C:\Program Files\SUMO\bin',
                r'C:\Program Files (x86)\SUMO\bin',
                r'C:\SUMO\bin',
            ]
            for d in win_dirs:
                if self.gui:
                    candidates.append(os.path.join(d, 'sumo-gui.exe'))
                candidates.append(os.path.join(d, 'sumo.exe'))

        for cand in candidates:
            resolved = shutil.which(cand)
            if resolved:
                return resolved
            if os.path.exists(cand):
                return cand

        raise FileNotFoundError(
            "SUMO executable not found. Install SUMO and ensure 'sumo' or 'sumo-gui' is on PATH. "
            "Typical Windows install: C:\\Program Files\\SUMO\\bin"
        )

    def start(self):
        """Start SUMO once and connect via TraCI on the given port."""
        if traci is None:
            raise RuntimeError("TraCI is not installed. Install SUMO Python support or verify your SUMO installation includes the Python API.")

        if not os.path.isfile(self.config_path):
            raise FileNotFoundError(
                f"SUMO config file is invalid or missing: {self.config_path}. "
                "Use a .sumocfg file, not the folder path."
            )

        cmd = [self.sumo_binary, '-c', self.config_path]
        if self.gui:
            cmd.append('--start')

        # Important: TraCI.start() launches the SUMO process itself.
        # Do not call subprocess.Popen(...) before this, or you end up with
        # two SUMO processes trying to bind the same remote-port.
        traci.start(cmd, port=self.port)
        self.connected = True

    def step(self):
        if not self.connected:
            raise RuntimeError("SUMO is not connected. Call start() first.")
        traci.simulationStep()

    def get_traffic_state(self):
        """Return a compact dictionary of live queue and flow values."""
        if not self.connected:
            return {}

        state = {}
        for edge_id in ['west_in', 'east_in', 'north_in', 'south_in']:
            lane_ids = [f"{edge_id}_{i}" for i in range(traci.edge.getLaneNumber(edge_id))]
            queue = 0
            for lane in lane_ids:
                queue += traci.lane.getWaitingTime(lane)
            state[edge_id] = {
                'queue': queue,
                'vehicles': traci.edge.getLastStepVehicleNumber(edge_id),
                'density': traci.edge.getLastStepOccupancy(edge_id),
            }
        return state

    def get_signal_state(self, tls_id='C'):
        if not self.connected:
            return {}
        return traci.trafficlight.getPhase(tls_id)

    def set_signal_phase(self, tls_id='C', phase_index=0):
        if not self.connected:
            return
        traci.trafficlight.setPhase(tls_id, phase_index)

    def stop(self):
        if self.connected:
            traci.close()
            self.connected = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)


if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(base_dir, 'sumocfg.sumocfg')

    conn = SumoTraCIConnector(config_path=config_file)
    try:
        conn.start()
        for _ in range(200):
            conn.step()
            print(conn.get_traffic_state())
        print('SUMO TraCI live connection working')
    finally:
        conn.stop()
