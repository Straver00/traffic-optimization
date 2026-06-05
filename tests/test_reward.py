"""Tests para la función de reward de simulation/rl_env.py — sin SUMO."""

import pytest
from rl.config import RewardConfig, DQNConfig
from simulation.rl_env import IntervalMetrics


def _metricas(espera=0.0, cola=0.0, velocidad=0.0, co2=0.0, throughput=0, pasos=1):
    m = IntervalMetrics()
    m.steps = pasos
    m.waiting_sum = espera * pasos
    m.queue_sum   = cola   * pasos
    m.speed_sum   = velocidad * pasos
    m.co2_total   = co2
    m.throughput_total = throughput
    return m


def _recompensa(metricas: IntervalMetrics, cambio: bool, config=None) -> float:
    if config is None:
        config = DQNConfig()
    cfg = config.reward
    wait_t      = metricas.waiting_avg  / cfg.waiting_time_scale
    queue_t     = metricas.queue_avg    / cfg.queue_scale
    speed_t     = metricas.speed_avg    / cfg.speed_scale
    tput_t      = metricas.throughput_total / cfg.throughput_scale
    co2_t       = metricas.co2_total    / cfg.co2_scale
    return (
        -cfg.w_queue      * queue_t
        -cfg.w_wait       * wait_t
        +cfg.w_speed      * speed_t
        +cfg.w_throughput * tput_t
        -cfg.w_co2        * co2_t
        -cfg.w_switch     * (1.0 if cambio else 0.0)
    )


class TestRewardFunction:

    def test_reward_negativo_con_colas_altas(self):
        metricas = _metricas(cola=50.0, espera=30.0, velocidad=0.0)
        r = _recompensa(metricas, cambio=False)
        assert r < 0

    def test_reward_positivo_con_velocidad_alta_y_sin_cola(self):
        metricas = _metricas(cola=0.0, espera=0.0, velocidad=15.0, throughput=10)
        r = _recompensa(metricas, cambio=False)
        assert r > 0

    def test_penalizacion_switch_se_aplica(self):
        metricas = _metricas()
        r_sin_cambio = _recompensa(metricas, cambio=False)
        r_con_cambio = _recompensa(metricas, cambio=True)
        assert r_sin_cambio > r_con_cambio

    def test_penalizacion_switch_valor_correcto(self):
        metricas = _metricas()
        r_sin = _recompensa(metricas, cambio=False)
        r_con = _recompensa(metricas, cambio=True)
        cfg = DQNConfig().reward
        assert (r_sin - r_con) == pytest.approx(cfg.w_switch, abs=1e-6)

    def test_co2_scale_normaliza_correctamente(self):
        """Un paso con co2 = co2_scale debe aportar exactamente w_co2 de penalización."""
        cfg = DQNConfig().reward
        metricas = _metricas(co2=cfg.co2_scale)
        r = _recompensa(metricas, cambio=False)
        # Solo el término CO2 activo (resto = 0)
        esperado = -cfg.w_co2 * 1.0
        assert r == pytest.approx(esperado, abs=1e-6)

    def test_pesos_suman_uno(self):
        cfg = RewardConfig()
        suma = cfg.w_queue + cfg.w_wait + cfg.w_speed + cfg.w_throughput + cfg.w_co2
        assert suma == pytest.approx(1.0, abs=1e-9)

    def test_w_switch_no_incluido_en_suma_principal(self):
        """w_switch es penalización aparte, no parte de los pesos de recompensa."""
        cfg = RewardConfig()
        suma_sin_switch = cfg.w_queue + cfg.w_wait + cfg.w_speed + cfg.w_throughput + cfg.w_co2
        assert suma_sin_switch == pytest.approx(1.0, abs=1e-9)
        # w_switch puede ser cualquier valor positivo
        assert cfg.w_switch > 0

    def test_reward_aumenta_con_mayor_throughput(self):
        m_bajo  = _metricas(throughput=2)
        m_alto  = _metricas(throughput=20)
        assert _recompensa(m_alto, False) > _recompensa(m_bajo, False)

    def test_interval_metrics_acumular(self):
        m1 = _metricas(cola=10.0, pasos=2)
        m2 = _metricas(cola=20.0, pasos=3)
        m1.accumulate(m2)
        assert m1.steps == 5
        assert m1.queue_avg == pytest.approx((10 * 2 + 20 * 3) / 5, abs=0.01)
