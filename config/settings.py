"""
Central configuration for the traffic platform.
Every magic number lives here so experiments stay reproducible.
"""

# ---------- Simulation ----------
TIME_STEP = 1.0                 # seconds per simulation tick
DEFAULT_DURATION = 1800         # 30 simulated minutes
RANDOM_SEED = 42

# ---------- Signal timing constraints (hard safety rules) ----------
MIN_GREEN = 10                  # seconds
MAX_GREEN = 60                  # seconds
YELLOW_TIME = 3                 # seconds
ALL_RED_TIME = 2                # seconds (clearance)
DEFAULT_GREEN = 30              # fixed-time baseline

# ---------- Control loop ----------
CONTROL_INTERVAL = 10           # re-decide green durations every N seconds
                                # (later: this is where QUBO/QAOA is called)

# ---------- Road / flow model ----------
SATURATION_FLOW_PER_LANE = 0.5  # vehicles per second per lane (= 1800 veh/h)
VEHICLE_LENGTH = 7.0            # metres of road occupied by one queued vehicle
DEFAULT_LANES = 2
DEFAULT_SPEED_KMH = 50.0
INTERNAL_ROAD_LENGTH = 500.0    # metres between two intersections
EXTERNAL_ROAD_LENGTH = 300.0    # metres from network edge to intersection

# ---------- Demand (vehicles/hour entering per entry road) ----------
DEMAND_PROFILES = {
    "low":        200,
    "normal":     500,
    "rush":       900,
    "congestion": 1300,
}

# ---------- Vehicle mix: (type, probability, pcu, fuel multiplier) ----------
VEHICLE_MIX = [
    ("car",   0.70, 1.0, 1.00),
    ("bike",  0.15, 0.5, 0.45),
    ("bus",   0.08, 2.5, 2.60),
    ("truck", 0.07, 2.0, 2.20),
]

# ---------- Environmental model ----------
IDLE_FUEL_L_PER_S = 0.00060     # litres burnt per second while stopped
MOVE_FUEL_L_PER_M = 0.00008     # litres burnt per metre travelled (~8 L/100 km)
CO2_G_PER_LITRE = 2310.0        # grams of CO2 per litre of fuel

# ---------- Emergency ----------
EMERGENCY_PREEMPT_ETA = 25      # seconds before arrival to start clearing signals
EMERGENCY_SPEED_KMH = 60.0
