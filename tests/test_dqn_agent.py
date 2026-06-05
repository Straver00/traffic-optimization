"""Tests para rl/double_dqn_agent.py — sin SUMO, solo tensores."""

import tempfile
from pathlib import Path

import pytest

from rl.config import DQNConfig, ExplorationConfig
from rl.double_dqn_agent import DoubleDQNAgent
from dataclasses import replace


STATE_DIM  = 12
ACTION_DIM = 3
ACCIONES_VALIDAS = [0, 1, 2]


def _agente(epsilon_start=1.0, epsilon_end=0.0, decay_steps=1) -> DoubleDQNAgent:
    config = DQNConfig(
        exploration=ExplorationConfig(
            epsilon_start=epsilon_start,
            epsilon_end=epsilon_end,
            epsilon_decay_steps=decay_steps,
        )
    )
    return DoubleDQNAgent(STATE_DIM, ACTION_DIM, config)


def _estado():
    return [0.1] * STATE_DIM


class TestDoubleDQNAgent:

    def test_accion_valida_en_rango(self):
        agente = _agente()
        accion = agente.select_action(_estado(), ACCIONES_VALIDAS, training=False)
        assert accion in ACCIONES_VALIDAS

    def test_exploracion_con_epsilon_1(self):
        """Con epsilon=1.0 siempre explora — debe producir variedad de acciones."""
        agente = _agente(epsilon_start=1.0, epsilon_end=1.0, decay_steps=1_000_000)
        acciones = {agente.select_action(_estado(), ACCIONES_VALIDAS, training=True) for _ in range(30)}
        # Con epsilon=1.0 y 30 muestras, debe haber más de 1 acción distinta
        assert len(acciones) > 1

    def test_inferencia_determinista(self):
        """Con epsilon=0.0 el mismo estado siempre produce la misma acción."""
        agente = _agente(epsilon_start=0.0, epsilon_end=0.0, decay_steps=1)
        accion_a = agente.select_action(_estado(), ACCIONES_VALIDAS, training=False)
        accion_b = agente.select_action(_estado(), ACCIONES_VALIDAS, training=False)
        assert accion_a == accion_b

    def test_acciones_validas_respetadas(self):
        """select_action solo devuelve acciones que están en la lista válida."""
        agente = _agente(epsilon_start=1.0, epsilon_end=1.0, decay_steps=1_000_000)
        acciones_restringidas = [0]
        for _ in range(20):
            accion = agente.select_action(_estado(), acciones_restringidas, training=True)
            assert accion in acciones_restringidas

    def test_learn_sin_excepcion_con_batch_minimo(self):
        """learn() no debe lanzar excepciones si no hay suficiente buffer."""
        agente = _agente()
        # Sin transiciones — no debe aprender ni fallar
        agente.learn()

    def test_learn_con_buffer_lleno(self):
        """Llena el buffer mínimo y verifica que learn() se ejecuta."""
        config = DQNConfig()
        min_size = config.training.min_replay_size
        agente = DoubleDQNAgent(STATE_DIM, ACTION_DIM, config)

        for i in range(min_size + 10):
            estado_actual = [float(i % 10)] * STATE_DIM
            estado_sig    = [float((i+1) % 10)] * STATE_DIM
            agente.store_transition(
                estado_actual, 0, -0.5, estado_sig, False,
                ACCIONES_VALIDAS, ACCIONES_VALIDAS,
            )
        # No debe lanzar excepción
        agente.learn()

    def test_guardar_y_cargar_modelo(self):
        agente = _agente(epsilon_start=0.0, epsilon_end=0.0)
        estado = _estado()
        accion_antes = agente.select_action(estado, ACCIONES_VALIDAS, training=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            ruta = Path(tmpdir) / "modelo_test.pt"
            agente.save(str(ruta))
            assert ruta.exists()

            agente2 = DoubleDQNAgent(STATE_DIM, ACTION_DIM, DQNConfig())
            agente2.load(str(ruta))
            accion_despues = agente2.select_action(estado, ACCIONES_VALIDAS, training=False)

        assert accion_antes == accion_despues

    def test_store_transition_incrementa_buffer(self):
        config = DQNConfig()
        agente = DoubleDQNAgent(STATE_DIM, ACTION_DIM, config)
        for i in range(5):
            agente.store_transition(
                _estado(), 0, -1.0, _estado(), False,
                ACCIONES_VALIDAS, ACCIONES_VALIDAS,
            )
        assert len(agente._buffer) == 5
