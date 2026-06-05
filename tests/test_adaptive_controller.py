"""Tests para decision/adaptive_controller.py — usa mocks de TraCI."""

from unittest.mock import MagicMock, call
import pytest

from decision.adaptive_controller import AdaptiveController
from decision.traffic_config import (
    FALLBACK_GREEN_AV80,
    FALLBACK_GREEN_C65,
    GREEN_MIN_S,
    GREEN_MAX_S,
    GREEN_MAX_SHARED,
    MAX_SKIP_CYCLES,
    PHASE_GREEN_AV80,
    PHASE_GREEN_C65,
    PHASE_YELLOW_AV80,
    PHASE_YELLOW_C65,
    PHASE_ALL_RED_AV80,
    PHASE_ALL_RED_C65,
)


def _traci_con_colas(cola_av80: int, cola_c65: int):
    """
    Crea un mock TraCI donde EDGES_AV80 tienen cola_av80 vehículos detenidos
    y EDGES_C65 tienen cola_c65. Un vehículo por arista (simplificado).
    """
    from decision.traffic_config import EDGES_AV80, EDGES_C65

    t = MagicMock()

    def get_ids(edge):
        if edge in EDGES_AV80:
            return [f"av80_{edge}_v{i}" for i in range(cola_av80)]
        if edge in EDGES_C65:
            return [f"c65_{edge}_v{i}" for i in range(cola_c65)]
        return []

    t.edge.getLastStepVehicleIDs.side_effect = get_ids
    # Todos detenidos (speed = 0)
    t.vehicle.getSpeed.return_value = 0.0
    return t


class TestAdaptiveController:

    def _controlador(self, cola_av80=0, cola_c65=0, modo="adaptive"):
        t = _traci_con_colas(cola_av80, cola_c65)
        ctrl = AdaptiveController(t, tl_id="J0", mode=modo)
        return ctrl, t

    # ------------------------------------------------------------------
    # Modo fijo — step no hace nada
    # ------------------------------------------------------------------

    def test_modo_fijo_no_llama_traci(self):
        t = _traci_con_colas(0, 0)
        ctrl = AdaptiveController(t, tl_id="J0", mode="fixed")
        t.reset_mock()
        for i in range(100):
            ctrl.step(i)
        t.trafficlight.setPhase.assert_not_called()

    # ------------------------------------------------------------------
    # GREEN_MIN_S y GREEN_MAX_S
    # ------------------------------------------------------------------

    def test_duracion_verde_minima(self):
        """Con colas iguales la duración no puede ser menor que GREEN_MIN_S."""
        ctrl, t = self._controlador(cola_av80=5, cola_c65=5)
        duracion = ctrl._decide_green(
            ["N_in", "S_in"], ["E_in", "W_in"],
            skip_secondary=0,
            flow_weight_primary=1000,
            flow_weight_secondary=1000,
        )
        assert duracion >= GREEN_MIN_S

    def test_duracion_verde_maxima_sin_cola_secundaria(self):
        """Sin cola secundaria puede llegar hasta GREEN_MAX_S."""
        ctrl, t = self._controlador(cola_av80=100, cola_c65=0)
        duracion = ctrl._decide_green(
            ["N_in", "S_in"], ["E_in", "W_in"],
            skip_secondary=0,
            flow_weight_primary=2000,
            flow_weight_secondary=100,
        )
        assert duracion <= GREEN_MAX_S

    def test_duracion_verde_capped_con_cola_secundaria(self):
        """Con cola secundaria la duración no supera GREEN_MAX_SHARED."""
        ctrl, t = self._controlador(cola_av80=50, cola_c65=10)
        duracion = ctrl._decide_green(
            ["N_in", "S_in"], ["E_in", "W_in"],
            skip_secondary=0,
            flow_weight_primary=2000,
            flow_weight_secondary=500,
        )
        assert duracion <= GREEN_MAX_SHARED

    # ------------------------------------------------------------------
    # MAX_SKIP_CYCLES
    # ------------------------------------------------------------------

    def test_max_skip_cycles_fuerza_minimo(self):
        """Si skip_secondary >= MAX_SKIP_CYCLES se devuelve GREEN_MIN_S."""
        ctrl, t = self._controlador(cola_av80=100, cola_c65=0)
        duracion = ctrl._decide_green(
            ["N_in", "S_in"], ["E_in", "W_in"],
            skip_secondary=MAX_SKIP_CYCLES,
            flow_weight_primary=2000,
            flow_weight_secondary=100,
        )
        assert duracion == GREEN_MIN_S

    # ------------------------------------------------------------------
    # Avance de fases
    # ------------------------------------------------------------------

    def test_avance_verde_av80_a_amarillo(self):
        ctrl, t = self._controlador()
        ctrl._current_phase = PHASE_GREEN_AV80
        ctrl._phase_timer   = 1  # expira en el próximo step

        ctrl.step(sim_step=0)

        fases_seteadas = [c.args[1] for c in t.trafficlight.setPhase.call_args_list]
        assert PHASE_YELLOW_AV80 in fases_seteadas

    def test_avance_amarillo_av80_a_todo_rojo(self):
        ctrl, t = self._controlador()
        ctrl._current_phase = PHASE_YELLOW_AV80
        ctrl._phase_timer   = 1

        ctrl.step(sim_step=0)

        fases_seteadas = [c.args[1] for c in t.trafficlight.setPhase.call_args_list]
        assert PHASE_ALL_RED_AV80 in fases_seteadas

    def test_fallback_activa_ante_excepcion(self):
        t = MagicMock()
        t.trafficlight.setPhase.side_effect = Exception("TraCI error")
        ctrl = AdaptiveController(t, tl_id="J0", mode="adaptive")
        ctrl._phase_timer = 1

        ctrl.step(sim_step=0)

        assert ctrl.fallback_active

    # ------------------------------------------------------------------
    # Propiedad current_phase
    # ------------------------------------------------------------------

    def test_current_phase_inicial(self):
        ctrl, _ = self._controlador()
        assert ctrl.current_phase == PHASE_GREEN_AV80
