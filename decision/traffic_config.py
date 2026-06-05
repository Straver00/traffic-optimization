"""Shared traffic signal configuration and constants."""

GREEN_MIN_S = 15
GREEN_MAX_S = 90
GREEN_MAX_SHARED = 60
YELLOW_S = 3
ALL_RED_S = 15
MAX_SKIP_CYCLES = 1

DECISION_STEP_S = 1

PHASE_GREEN_AV80 = 0
PHASE_YELLOW_AV80 = 1
PHASE_ALL_RED_AV80 = 2
PHASE_GREEN_C65 = 3
PHASE_YELLOW_C65 = 4
PHASE_ALL_RED_C65 = 5

PROGRAM_ID = "programa_av80_c65"

EDGES_AV80 = ["N_in", "S_in"]
EDGES_C65 = ["E_in", "W_in"]

FALLBACK_GREEN_AV80 = 52
FALLBACK_GREEN_C65 = 33

FLOW_WEIGHT_AV80 = 2508   # aforo vespertino real: 1147 + 1361 veh/h (15/05/2025)
FLOW_WEIGHT_C65  = 1328   # aforo vespertino real: 308 + 280 + 431 + 309 veh/h (15/05/2025)

# ---------------------------------------------------------------------------
# Escenario 2 — Red 2×2 (4 intersecciones en cuadrícula)
# ---------------------------------------------------------------------------

# IDs de los 4 semáforos
TRAFFIC_LIGHTS_2x2 = ["J0", "J1", "J2", "J3"]

# IDs de program por semáforo
PROGRAM_IDS_2x2 = {
    "J0": "programa_J0",
    "J1": "programa_J1",
    "J2": "programa_J2",
    "J3": "programa_J3",
}

# Aristas de acceso por intersección
# Clave "AV80": acceso N-S (Av. 80) | "C65": acceso E-O (C65)
EDGES_2x2 = {
    "J0": {
        "AV80": ["N0_in", "J2_J0"],   # norte externo + sur interno
        "C65":  ["J1_J0", "W0_in"],   # oriente interno + occidente externo
    },
    "J1": {
        "AV80": ["N1_in", "J3_J1"],
        "C65":  ["E0_in", "J0_J1"],
    },
    "J2": {
        "AV80": ["J0_J2", "S0_in"],
        "C65":  ["J3_J2", "W1_in"],
    },
    "J3": {
        "AV80": ["J1_J3", "S1_in"],
        "C65":  ["E1_in", "J2_J3"],
    },
}
