"""Tests para decision/traffic_config.py — sin dependencias externas."""

import pytest
from decision.traffic_config import (
    ALL_RED_S,
    FLOW_WEIGHT_AV80,
    FLOW_WEIGHT_C65,
    GREEN_MAX_S,
    GREEN_MAX_SHARED,
    GREEN_MIN_S,
    TRAFFIC_LIGHTS_2x2,
    YELLOW_S,
    PHASE_GREEN_AV80,
    PHASE_YELLOW_AV80,
    PHASE_ALL_RED_AV80,
    PHASE_GREEN_C65,
    PHASE_YELLOW_C65,
    PHASE_ALL_RED_C65,
    EDGES_AV80,
    EDGES_C65,
)


def test_duraciones_verde():
    assert GREEN_MIN_S > 0
    assert GREEN_MIN_S < GREEN_MAX_S
    assert GREEN_MAX_SHARED <= GREEN_MAX_S


def test_duraciones_fijas():
    assert YELLOW_S == 3
    assert ALL_RED_S == 15


def test_flujos_positivos():
    assert FLOW_WEIGHT_AV80 > 0
    assert FLOW_WEIGHT_C65 > 0


def test_fases_distintas():
    fases = [
        PHASE_GREEN_AV80, PHASE_YELLOW_AV80, PHASE_ALL_RED_AV80,
        PHASE_GREEN_C65, PHASE_YELLOW_C65, PHASE_ALL_RED_C65,
    ]
    assert len(set(fases)) == 6, "Todas las fases deben tener índices únicos"


def test_fases_orden_correcto():
    # El plan semafórico define el orden 0→5
    assert PHASE_GREEN_AV80 == 0
    assert PHASE_YELLOW_AV80 == 1
    assert PHASE_ALL_RED_AV80 == 2
    assert PHASE_GREEN_C65 == 3
    assert PHASE_YELLOW_C65 == 4
    assert PHASE_ALL_RED_C65 == 5


def test_aristas_no_vacias():
    assert len(EDGES_AV80) > 0
    assert len(EDGES_C65) > 0


def test_escenario2_semaforos():
    assert len(TRAFFIC_LIGHTS_2x2) == 4
    assert set(TRAFFIC_LIGHTS_2x2) == {"J0", "J1", "J2", "J3"}


def test_escenario2_aristas_por_interseccion():
    from decision.traffic_config import EDGES_2x2
    for tl in TRAFFIC_LIGHTS_2x2:
        assert tl in EDGES_2x2
        assert "AV80" in EDGES_2x2[tl]
        assert "C65"  in EDGES_2x2[tl]
        assert len(EDGES_2x2[tl]["AV80"]) >= 1
        assert len(EDGES_2x2[tl]["C65"])  >= 1
