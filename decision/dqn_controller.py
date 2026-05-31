"""Double DQN controller for adaptive traffic light control."""

from __future__ import annotations

import random
import time
from pathlib import Path

from decision.state_extractor import StateExtractor
from decision.traffic_config import (
    ALL_RED_S,
    GREEN_MAX_S,
    GREEN_MAX_SHARED,
    GREEN_MIN_S,
    PHASE_ALL_RED_AV80,
    PHASE_ALL_RED_C65,
    PHASE_GREEN_AV80,
    PHASE_GREEN_C65,
    PHASE_YELLOW_AV80,
    PHASE_YELLOW_C65,
    PROGRAM_ID,
    YELLOW_S,
)
from rl.config import DQNConfig
from rl.double_dqn_agent import DoubleDQNAgent


def _state_dim(config: DQNConfig) -> int:
    dim = 4
    if config.state.include_waiting_time:
        dim += 1
    if config.state.include_speed_avg:
        dim += 1
    if config.state.include_occupancy:
        dim += 1
    if config.state.include_throughput:
        dim += 1
    if config.state.include_phase_one_hot:
        dim += 4
    if config.state.include_phase_time:
        dim += 1
    return dim


class DQNController:
    def __init__(
        self,
        traci_module,
        tl_id: str = "J0",
        mode: str = "dqn",
        model_path: str | None = None,
        config: DQNConfig | None = None,
    ) -> None:
        self._t = traci_module
        self._tl_id = tl_id
        self._mode = mode
        self._config = config or DQNConfig()

        self._current_phase: int = PHASE_GREEN_AV80
        self._phase_timer: int = GREEN_MIN_S
        self._green_elapsed: int = 0
        self._planned_end: int = GREEN_MIN_S
        self._fallback_active: bool = False
        self._last_phase_set_time: float = 0.0

        self._state_extractor = StateExtractor(self._t, self._tl_id, self._config)
        self._agent = DoubleDQNAgent(
            state_dim=_state_dim(self._config),
            action_dim=self._config.action.size(),
            config=self._config,
        )
        self._use_random_policy = False

        if model_path:
            if Path(model_path).exists():
                self._agent.load(model_path)
            else:
                print(f"[dqn] Modelo no encontrado en {model_path}. Usando politica aleatoria.")
                self._use_random_policy = True
        else:
            self._use_random_policy = True

        try:
            self._set_green(PHASE_GREEN_AV80)
        except Exception:
            pass

    def step(self, sim_step: int) -> None:
        if self._mode == "fixed":
            return
        try:
            if self._current_phase in (PHASE_GREEN_AV80, PHASE_GREEN_C65):
                self._handle_green_step()
            else:
                self._phase_timer -= 1
                if self._phase_timer > 0:
                    return
                self._advance_phase()
            self._fallback_active = False
        except Exception as exc:
            print(f"[dqn] ERROR TraCI en paso {sim_step}: {exc}")
            self._activate_fallback()

    @property
    def fallback_active(self) -> bool:
        return self._fallback_active

    @property
    def current_phase(self) -> int:
        return self._current_phase

    def _advance_phase(self) -> None:
        phase = self._current_phase

        if phase == PHASE_YELLOW_AV80:
            self._set_phase(PHASE_ALL_RED_AV80, ALL_RED_S)
        elif phase == PHASE_ALL_RED_AV80:
            self._set_green(PHASE_GREEN_C65)
        elif phase == PHASE_YELLOW_C65:
            self._set_phase(PHASE_ALL_RED_C65, ALL_RED_S)
        elif phase == PHASE_ALL_RED_C65:
            self._set_green(PHASE_GREEN_AV80)

    def _handle_green_step(self) -> None:
        self._green_elapsed += 1
        self._phase_timer -= 1

        snapshot = self._state_extractor.build_state(self._current_phase, self._green_elapsed)
        max_duration = self._max_duration(snapshot)
        if self._planned_end > max_duration:
            self._planned_end = max_duration

        if self._green_elapsed >= max_duration:
            self._start_yellow()
            return

        valid_actions = self._valid_actions(max_duration)
        action_index = self._select_action(snapshot.state, valid_actions)

        if action_index == self._config.action.switch_idx and self._green_elapsed >= GREEN_MIN_S:
            self._start_yellow()
            return

        if action_index == self._config.action.extend_idx:
            self._extend_green(max_duration)

        if self._green_elapsed >= self._planned_end or self._phase_timer <= 0:
            self._start_yellow()

    def _valid_actions(self, max_duration: int) -> list[int]:
        actions = [self._config.action.keep_idx]
        if self._planned_end < max_duration:
            actions.append(self._config.action.extend_idx)
        if self._green_elapsed >= GREEN_MIN_S:
            actions.append(self._config.action.switch_idx)
        if self._green_elapsed >= max_duration:
            actions = [self._config.action.switch_idx]
        return actions

    def _select_action(self, state, valid_actions: list[int]) -> int:
        if self._use_random_policy:
            return random.choice(valid_actions)
        return self._agent.select_action(state, valid_actions, training=False)

    def _extend_green(self, max_duration: int) -> None:
        if self._planned_end >= max_duration:
            return
        extension = min(self._config.action.extend_step_s, max_duration - self._planned_end)
        if extension <= 0:
            return
        self._planned_end += extension
        self._phase_timer += extension
        self._t.trafficlight.setPhaseDuration(self._tl_id, self._phase_timer)

    def _start_yellow(self) -> None:
        if self._current_phase == PHASE_GREEN_AV80:
            self._set_phase(PHASE_YELLOW_AV80, YELLOW_S)
        else:
            self._set_phase(PHASE_YELLOW_C65, YELLOW_S)

    def _set_phase(self, phase_index: int, duration_s: int) -> None:
        self._t.trafficlight.setPhase(self._tl_id, phase_index)
        self._t.trafficlight.setPhaseDuration(self._tl_id, duration_s)
        self._current_phase = phase_index
        self._phase_timer = duration_s
        self._last_phase_set_time = time.time()

    def _set_green(self, phase_index: int) -> None:
        self._green_elapsed = 0
        self._planned_end = GREEN_MIN_S
        self._set_phase(phase_index, GREEN_MIN_S)

    def _max_duration(self, snapshot) -> int:
        if self._current_phase == PHASE_GREEN_AV80:
            secondary_queue = snapshot.queue_c65
        else:
            secondary_queue = snapshot.queue_av80
        return GREEN_MAX_S if secondary_queue == 0 else GREEN_MAX_SHARED

    def _activate_fallback(self) -> None:
        if self._fallback_active:
            return
        print("[dqn] FALLBACK activado -> tiempos fijos")
        t0 = time.time()
        try:
            self._t.trafficlight.setProgram(self._tl_id, PROGRAM_ID)
        except Exception as exc:
            print(f"[dqn] No se pudo restaurar programa: {exc}")
        elapsed_ms = (time.time() - t0) * 1000
        print(f"[dqn] Fallback completado en {elapsed_ms:.1f} ms")
        self._fallback_active = True
