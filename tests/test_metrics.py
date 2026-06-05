"""Tests para evaluation/metrics.py — usa mocks de TraCI."""

import csv
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evaluation.metrics import MetricsCollector, TrafficSnapshot


def _mock_traci(n_vehiculos=5, velocidad=5.0, espera=10.0, co2=1000.0, fase=0):
    """Crea un módulo TraCI simulado con n_vehiculos activos."""
    t = MagicMock()
    ids = [f"veh{i}" for i in range(n_vehiculos)]
    t.vehicle.getIDList.return_value = ids
    t.vehicle.getSpeed.return_value = velocidad
    t.vehicle.getWaitingTime.return_value = espera
    t.vehicle.getCO2Emission.return_value = co2
    t.simulation.getArrivedNumber.return_value = 2
    t.lanearea.getIDList.return_value = []
    t.trafficlight.getPhase.return_value = fase
    return t


class TestMetricsCollector:

    def test_collect_devuelve_snapshot(self):
        traci = _mock_traci(n_vehiculos=3)
        col = MetricsCollector(traci, tl_id="J0", mode="fixed")
        snap = col.collect(step=1)
        assert isinstance(snap, TrafficSnapshot)
        assert snap.step == 1

    def test_waiting_time_promedio(self):
        traci = _mock_traci(n_vehiculos=4, espera=20.0)
        col = MetricsCollector(traci, tl_id="J0", mode="adaptive")
        snap = col.collect(step=0)
        assert snap.waiting_time_avg == pytest.approx(20.0, abs=0.01)

    def test_queue_length_max_cuenta_detenidos(self):
        # Todos a velocidad < 0.1 → todos en cola
        traci = _mock_traci(n_vehiculos=6, velocidad=0.0)
        col = MetricsCollector(traci, tl_id="J0", mode="fixed")
        snap = col.collect(step=0)
        assert snap.queue_length_max == 6

    def test_queue_length_ninguno_detenido(self):
        traci = _mock_traci(n_vehiculos=4, velocidad=10.0)
        col = MetricsCollector(traci, tl_id="J0", mode="fixed")
        snap = col.collect(step=0)
        assert snap.queue_length_max == 0

    def test_throughput_registrado(self):
        traci = _mock_traci(n_vehiculos=3)
        traci.simulation.getArrivedNumber.return_value = 5
        col = MetricsCollector(traci, tl_id="J0", mode="fixed")
        snap = col.collect(step=0)
        assert snap.throughput == 5

    def test_co2_suma_todos_vehiculos(self):
        n = 4
        traci = _mock_traci(n_vehiculos=n, co2=500.0)
        col = MetricsCollector(traci, tl_id="J0", mode="fixed")
        snap = col.collect(step=0)
        assert snap.co2_mg == pytest.approx(n * 500.0, abs=0.1)

    def test_summary_claves_esperadas(self):
        traci = _mock_traci(n_vehiculos=3)
        col = MetricsCollector(traci, tl_id="J0", mode="fixed")
        for i in range(5):
            col.collect(step=i)
        resumen = col.summary()
        for clave in [
            "waiting_time_avg_s", "queue_length_avg_veh", "queue_length_max_veh",
            "speed_avg_ms", "throughput_total_veh", "co2_total_mg",
        ]:
            assert clave in resumen, f"Clave faltante: {clave}"

    def test_summary_steady_state_excluye_warmup(self):
        traci_alto  = _mock_traci(n_vehiculos=5, espera=50.0)
        traci_bajo  = _mock_traci(n_vehiculos=5, espera=5.0)

        col = MetricsCollector(traci_alto, tl_id="J0", mode="fixed")
        # Pasos 0-99: espera alta (warmup)
        for i in range(100):
            col.collect(step=i)

        # Reemplazar traci para pasos posteriores (espera baja)
        col._traci = traci_bajo
        for i in range(100, 200):
            col.collect(step=i)

        resumen = col.summary_steady_state(warmup_steps=100)
        # La media del steady-state debe ser baja (pasos 100-199, espera=5)
        assert resumen["waiting_time_avg_s"] < 10.0

    def test_save_csv_filas_correctas(self):
        traci = _mock_traci(n_vehiculos=2)
        col = MetricsCollector(traci, tl_id="J0", mode="fixed")
        n_pasos = 7
        for i in range(n_pasos):
            col.collect(step=i)

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            ruta = f.name
        col.save(ruta)

        with open(ruta, encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        assert len(filas) == n_pasos

    def test_summary_vacio_devuelve_dict_vacio(self):
        traci = _mock_traci()
        col = MetricsCollector(traci, tl_id="J0", mode="fixed")
        assert col.summary() == {}
