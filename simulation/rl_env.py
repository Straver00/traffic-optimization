"""SUMO environment wrapper for training Double DQN with safety transitions."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from decision.state_extractor import StateExtractor
from decision.traffic_config import (
    ALL_RED_S,
    DECISION_STEP_S,
    GREEN_MAX_S,
    GREEN_MAX_SHARED,
    GREEN_MIN_S,
    PHASE_ALL_RED_AV80,
    PHASE_ALL_RED_C65,
    PHASE_GREEN_AV80,
    PHASE_GREEN_C65,
    PHASE_YELLOW_AV80,
    PHASE_YELLOW_C65,
    YELLOW_S,
)
from evaluation.metrics import MetricsCollector
from rl.config import DQNConfig
from simulation.traci_runner import (
    NET_FILE,
    OUTPUT_DIR,
    ROUTE_FILE,
    TL_ID,
    ensure_net_file,
    find_binary,
    setup_traci,
)


@dataclass
class StepInfo:
    valid_actions: list[int]
    steps: int
    waiting_avg: float
    queue_avg: float
    speed_avg: float
    co2_total: float
    throughput_total: int


class SumoDQNEnv:
    def __init__(
        self,
        config: DQNConfig,
        gui: bool = False,
        sim_duration_s: int = 3600,
        output_dir: Path | None = None,
    ) -> None:
        self._config = config
        self._gui = gui
        self._sim_duration_s = sim_duration_s
        self._output_dir = output_dir or OUTPUT_DIR

        self._traci = None
        self._collector: Optional[MetricsCollector] = None
        self._state_extractor: Optional[StateExtractor] = None

        self._current_green = PHASE_GREEN_AV80
        self._green_elapsed = 0
        self._planned_end = GREEN_MIN_S
        self._step = 0
        self._last_snapshot = None

    @property
    def state_dim(self) -> int:
        dim = 4
        if self._config.state.include_waiting_time:
            dim += 1
        if self._config.state.include_speed_avg:
            dim += 1
        if self._config.state.include_occupancy:
            dim += 1
        if self._config.state.include_throughput:
            dim += 1
        if self._config.state.include_phase_one_hot:
            dim += 4
        if self._config.state.include_phase_time:
            dim += 1
        return dim

    @property
    def action_dim(self) -> int:
        return self._config.action.size()

    def reset(self, demand: dict | None = None) -> tuple[list[float], list[int]]:
        self.close()
        setup_traci()
        import traci  # type: ignore

        ensure_net_file()

        binary = find_binary("sumo-gui" if self._gui else "sumo")
        if not binary:
            raise RuntimeError("SUMO binary not found")

        route_file = self._write_temp_routes(demand)
        self._temp_route_file = route_file

        sumo_cmd = [
            binary,
            "-n", str(NET_FILE),
            "-r", route_file,
            "--no-step-log",
            "--time-to-teleport", "-1",
            "--quit-on-end",
        ]
        if self._gui:
            sumo_cmd.append("--start")

        traci.start(sumo_cmd)
        self._traci = traci
        self._collector = MetricsCollector(traci, tl_id=TL_ID, mode="dqn")
        self._state_extractor = StateExtractor(traci, TL_ID, self._config)

        self._current_green = PHASE_GREEN_AV80
        self._green_elapsed = 0
        self._planned_end = GREEN_MIN_S
        self._step = 0

        self._set_phase(self._current_green, GREEN_MIN_S)

        snapshot = self._state_extractor.build_state(self._current_green, self._green_elapsed)
        self._last_snapshot = snapshot
        valid_actions = self._valid_actions(snapshot, self._max_duration(snapshot))
        return snapshot.state, valid_actions

    def step(self, action_index: int) -> tuple[list[float], float, bool, StepInfo]:
        if not self._traci or not self._collector or not self._state_extractor:
            raise RuntimeError("Environment not initialized. Call reset() first.")

        if self._last_snapshot is None:
            raise RuntimeError("Missing state snapshot before step().")

        snapshot = self._last_snapshot
        max_duration = self._max_duration(snapshot)
        if self._planned_end > max_duration:
            self._planned_end = max_duration
        valid_actions = self._valid_actions(snapshot, max_duration)

        if action_index not in valid_actions:
            action_index = self._config.action.keep_idx

        interval_metrics = IntervalMetrics()
        did_switch = False

        if (
            action_index == self._config.action.switch_idx
            and self._green_elapsed >= GREEN_MIN_S
        ):
            interval_metrics.accumulate(self._run_switch_sequence())
            did_switch = True
        else:
            if action_index == self._config.action.extend_idx:
                self._extend_planned_end(max_duration)
            interval_metrics.accumulate(self._run_steps(DECISION_STEP_S))
            self._green_elapsed += DECISION_STEP_S

            if not self._is_done():
                if self._green_elapsed >= max_duration or self._green_elapsed >= self._planned_end:
                    interval_metrics.accumulate(self._run_switch_sequence())
                    did_switch = True

        done = self._is_done()
        snapshot = self._state_extractor.build_state(self._current_green, self._green_elapsed)
        self._last_snapshot = snapshot
        valid_actions = self._valid_actions(snapshot, self._max_duration(snapshot))

        reward = self._compute_reward(interval_metrics, did_switch)
        info = StepInfo(
            valid_actions=valid_actions,
            steps=interval_metrics.steps,
            waiting_avg=interval_metrics.waiting_avg,
            queue_avg=interval_metrics.queue_avg,
            speed_avg=interval_metrics.speed_avg,
            co2_total=interval_metrics.co2_total,
            throughput_total=interval_metrics.throughput_total,
        )

        if done:
            self.close()

        return snapshot.state, reward, done, info

    def close(self) -> None:
        if self._traci is not None:
            try:
                self._traci.close()
            except Exception:
                pass
        if hasattr(self, "_temp_route_file") and self._temp_route_file != str(ROUTE_FILE):
            try:
                Path(self._temp_route_file).unlink(missing_ok=True)
            except Exception:
                pass
        self._traci = None
        self._collector = None
        self._state_extractor = None

    def _valid_actions(self, snapshot, max_duration: int) -> list[int]:
        actions = [self._config.action.keep_idx]
        if self._planned_end < max_duration:
            actions.append(self._config.action.extend_idx)
        if self._green_elapsed >= GREEN_MIN_S:
            actions.append(self._config.action.switch_idx)
        if self._green_elapsed >= max_duration:
            actions = [self._config.action.switch_idx]
        return actions

    def _extend_planned_end(self, max_duration: int) -> None:
        if self._planned_end >= max_duration:
            return
        extension = min(self._config.action.extend_step_s, max_duration - self._planned_end)
        if extension <= 0:
            return
        self._planned_end += extension
        remaining = max(self._planned_end - self._green_elapsed, 1)
        self._traci.trafficlight.setPhaseDuration(TL_ID, remaining)

    def _compute_reward(self, metrics, did_switch: bool) -> float:
        cfg = self._config.reward
        wait_term = metrics.waiting_avg / cfg.waiting_time_scale
        queue_term = metrics.queue_avg / cfg.queue_scale
        speed_term = metrics.speed_avg / cfg.speed_scale
        throughput_term = metrics.throughput_total / cfg.throughput_scale
        co2_term = metrics.co2_total / cfg.co2_scale

        reward = (
            -cfg.w_queue * queue_term
            -cfg.w_wait * wait_term
            +cfg.w_speed * speed_term
            +cfg.w_throughput * throughput_term
            -cfg.w_co2 * co2_term
            -cfg.w_switch * (1.0 if did_switch else 0.0)
        )
        return reward

    def _run_steps(self, steps: int) -> "IntervalMetrics":
        if not self._collector or not self._traci:
            raise RuntimeError("Collector not initialized")

        metrics = IntervalMetrics()
        for _ in range(steps):
            self._traci.simulationStep()
            snap = self._collector.collect(self._step)
            metrics.update(snap)
            self._step += 1
            if self._is_done():
                break
        return metrics

    def _run_switch_sequence(self) -> "IntervalMetrics":
        metrics = IntervalMetrics()
        if self._current_green == PHASE_GREEN_AV80:
            yellow_phase = PHASE_YELLOW_AV80
            all_red_phase = PHASE_ALL_RED_AV80
            next_green = PHASE_GREEN_C65
        else:
            yellow_phase = PHASE_YELLOW_C65
            all_red_phase = PHASE_ALL_RED_C65
            next_green = PHASE_GREEN_AV80

        self._set_phase(yellow_phase, YELLOW_S)
        metrics.accumulate(self._run_steps(YELLOW_S))
        if self._is_done():
            return metrics

        self._set_phase(all_red_phase, ALL_RED_S)
        metrics.accumulate(self._run_steps(ALL_RED_S))
        if self._is_done():
            return metrics

        self._current_green = next_green
        self._green_elapsed = 0
        self._planned_end = GREEN_MIN_S
        self._set_phase(self._current_green, GREEN_MIN_S)
        return metrics

    def _set_phase(self, phase_index: int, duration_s: int) -> None:
        if not self._traci:
            raise RuntimeError("TraCI not initialized")
        self._traci.trafficlight.setPhase(TL_ID, phase_index)
        self._traci.trafficlight.setPhaseDuration(TL_ID, duration_s)

    def _max_duration(self, snapshot) -> int:
        secondary_queue = snapshot.queue_c65 if self._current_green == PHASE_GREEN_AV80 else snapshot.queue_av80
        return GREEN_MAX_S if secondary_queue == 0 else GREEN_MAX_SHARED

    def _write_temp_routes(self, demand: dict | None) -> str:
        """Genera un .rou.xml temporal con los flujos del perfil dado.
        Si demand es None, devuelve ROUTE_FILE sin modificar."""
        if demand is None:
            return str(ROUTE_FILE)

        route_text = Path(ROUTE_FILE).read_text(encoding="utf-8")

        mapping = {
            "flow_NS": demand["flow_NS"],
            "flow_SN": demand["flow_SN"],
            "flow_EW": demand["flow_EW"],
            "flow_WE": demand["flow_WE"],
        }
        for flow_id, veh_per_hour in mapping.items():
            route_text = re.sub(
                rf'(<flow\s[^>]*id="{flow_id}"[^>]*)\bvehsPerHour="[^"]*"',
                rf'\1vehsPerHour="{veh_per_hour}"',
                route_text,
            )

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".rou.xml", delete=False,
            encoding="utf-8", dir=Path(ROUTE_FILE).parent
        )
        tmp.write(route_text)
        tmp.flush()
        tmp.close()
        return tmp.name

    def _is_done(self) -> bool:
        if not self._traci:
            return True
        return self._traci.simulation.getMinExpectedNumber() <= 0 or self._step >= self._sim_duration_s


class IntervalMetrics:
    def __init__(self) -> None:
        self.steps = 0
        self.waiting_sum = 0.0
        self.queue_sum = 0.0
        self.speed_sum = 0.0
        self.co2_total = 0.0
        self.throughput_total = 0

    def update(self, snap) -> None:
        self.steps += 1
        self.waiting_sum += snap.waiting_time_avg
        self.queue_sum += snap.queue_length_max
        self.speed_sum += snap.speed_avg
        self.co2_total += snap.co2_mg
        self.throughput_total += snap.throughput

    def accumulate(self, other: "IntervalMetrics") -> None:
        self.steps += other.steps
        self.waiting_sum += other.waiting_sum
        self.queue_sum += other.queue_sum
        self.speed_sum += other.speed_sum
        self.co2_total += other.co2_total
        self.throughput_total += other.throughput_total

    @property
    def waiting_avg(self) -> float:
        return self.waiting_sum / self.steps if self.steps else 0.0

    @property
    def queue_avg(self) -> float:
        return self.queue_sum / self.steps if self.steps else 0.0

    @property
    def speed_avg(self) -> float:
        return self.speed_sum / self.steps if self.steps else 0.0
