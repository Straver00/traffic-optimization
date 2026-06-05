"""Tests para decision/state_extractor.py — usa mocks de TraCI."""

from unittest.mock import MagicMock
import pytest

from decision.state_extractor import StateExtractor
from decision.traffic_config import PHASE_GREEN_AV80, PHASE_GREEN_C65
from rl.config import DQNConfig


def _traci_mock(n_vehiculos=4, velocidad=5.0, espera=8.0, cola_av80=3, cola_c65=2):
    from decision.traffic_config import EDGES_AV80, EDGES_C65
    t = MagicMock()

    def get_ids(edge):
        if edge in EDGES_AV80:
            return [f"v_av80_{i}" for i in range(cola_av80)]
        if edge in EDGES_C65:
            return [f"v_c65_{i}" for i in range(cola_c65)]
        return []

    t.edge.getLastStepVehicleIDs.side_effect = get_ids
    # Todos detenidos para que cuenten como cola
    t.vehicle.getSpeed.return_value = 0.0
    ids = [f"veh{i}" for i in range(n_vehiculos)]
    t.vehicle.getIDList.return_value = ids
    t.vehicle.getWaitingTime.return_value = espera
    t.lanearea.getIDList.return_value = []
    t.simulation.getArrivedNumber.return_value = 1
    return t


class TestStateExtractor:

    def _extractor(self, **kw):
        t = _traci_mock(**kw)
        config = DQNConfig()
        return StateExtractor(t, tl_id="J0", config=config), config

    def test_dimension_estado_correcta(self):
        ext, config = self._extractor()
        snap = ext.build_state(PHASE_GREEN_AV80, time_in_phase_s=10)
        # 4 colas + 1 espera + 1 velocidad + 1 ocupacion + 4 one-hot + 1 tiempo
        esperado = 4
        if config.state.include_waiting_time:  esperado += 1
        if config.state.include_speed_avg:     esperado += 1
        if config.state.include_occupancy:     esperado += 1
        if config.state.include_phase_one_hot: esperado += 4
        if config.state.include_phase_time:    esperado += 1
        assert len(snap.state) == esperado

    def test_valores_normalizados(self):
        ext, _ = self._extractor()
        snap = ext.build_state(PHASE_GREEN_AV80, time_in_phase_s=10)
        for v in snap.state:
            assert v >= 0.0, f"Valor negativo en estado: {v}"
            assert v <= 2.0, f"Valor demasiado alto: {v}"  # tolerancia para espera/velocidad

    def test_phase_one_hot_verde_av80(self):
        ext, _ = self._extractor()
        snap = ext.build_state(PHASE_GREEN_AV80, time_in_phase_s=5)
        # Los 4 valores one-hot están al final (antes de phase_time)
        # índice: 4 (colas) + 1 espera + 1 velocidad + 1 ocupacion = 7 → one-hot en [7:11]
        one_hot = snap.state[7:11]
        assert sum(one_hot) == pytest.approx(1.0, abs=0.01)
        assert one_hot[0] == pytest.approx(1.0)  # is_green_av80

    def test_phase_one_hot_verde_c65(self):
        ext, _ = self._extractor()
        snap = ext.build_state(PHASE_GREEN_C65, time_in_phase_s=5)
        one_hot = snap.state[7:11]
        assert sum(one_hot) == pytest.approx(1.0, abs=0.01)
        assert one_hot[1] == pytest.approx(1.0)  # is_green_c65

    def test_queue_av80_y_c65(self):
        from decision.traffic_config import EDGES_AV80, EDGES_C65
        ext, _ = self._extractor(cola_av80=6, cola_c65=4)
        snap = ext.build_state(PHASE_GREEN_AV80, time_in_phase_s=0)
        assert snap.queue_av80 == 6 * len(EDGES_AV80)
        assert snap.queue_c65  == 4 * len(EDGES_C65)

    def test_phase_time_capped_en_1(self):
        """Tiempo en fase muy alto debe quedar normalizado a 1.0."""
        ext, config = self._extractor()
        tiempo_enorme = int(config.norm.phase_time_scale * 10)
        snap = ext.build_state(PHASE_GREEN_AV80, time_in_phase_s=tiempo_enorme)
        # phase_time es el último elemento
        assert snap.state[-1] == pytest.approx(1.0)
