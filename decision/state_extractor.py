"""State extraction for RL controllers using TraCI queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from decision.traffic_config import (
    EDGES_AV80,
    EDGES_C65,
    PHASE_ALL_RED_AV80,
    PHASE_ALL_RED_C65,
    PHASE_GREEN_AV80,
    PHASE_GREEN_C65,
    PHASE_YELLOW_AV80,
    PHASE_YELLOW_C65,
)
from rl.config import DQNConfig


@dataclass(frozen=True)
class StateSnapshot:
    state: List[float]
    queue_av80: int
    queue_c65: int


class StateExtractor:
    def __init__(self, traci_module, tl_id: str, config: DQNConfig) -> None:
        self._t = traci_module
        self._tl_id = tl_id
        self._config = config

    def build_state(self, phase_index: int, time_in_phase_s: int) -> StateSnapshot:
        q_n, q_s = self._edge_queue_lengths(EDGES_AV80)
        q_e, q_w = self._edge_queue_lengths(EDGES_C65)

        queue_av80 = q_n + q_s
        queue_c65 = q_e + q_w

        waiting_avg, speed_avg, occupancy, throughput = self._global_metrics()

        norm = self._config.norm
        state: List[float] = [
            q_n / norm.queue_scale,
            q_s / norm.queue_scale,
            q_e / norm.queue_scale,
            q_w / norm.queue_scale,
        ]

        if self._config.state.include_waiting_time:
            state.append(waiting_avg / norm.waiting_time_scale)
        if self._config.state.include_speed_avg:
            state.append(speed_avg / norm.speed_scale)
        if self._config.state.include_occupancy:
            state.append(occupancy / norm.occupancy_scale)
        if self._config.state.include_throughput:
            state.append(throughput / norm.throughput_scale)

        if self._config.state.include_phase_one_hot:
            is_green_av80 = 1.0 if phase_index == PHASE_GREEN_AV80 else 0.0
            is_green_c65 = 1.0 if phase_index == PHASE_GREEN_C65 else 0.0
            is_yellow = 1.0 if phase_index in (PHASE_YELLOW_AV80, PHASE_YELLOW_C65) else 0.0
            is_all_red = 1.0 if phase_index in (PHASE_ALL_RED_AV80, PHASE_ALL_RED_C65) else 0.0
            state.extend([is_green_av80, is_green_c65, is_yellow, is_all_red])

        if self._config.state.include_phase_time:
            state.append(min(time_in_phase_s / norm.phase_time_scale, 1.0))

        return StateSnapshot(state=state, queue_av80=queue_av80, queue_c65=queue_c65)

    def _edge_queue_lengths(self, edges: List[str]) -> List[int]:
        counts = []
        threshold = self._config.state.queue_speed_threshold
        for edge in edges:
            count = 0
            try:
                veh_ids = self._t.edge.getLastStepVehicleIDs(edge)
                for vid in veh_ids:
                    if self._t.vehicle.getSpeed(vid) < threshold:
                        count += 1
            except Exception:
                count = 0
            counts.append(count)
        return counts

    def _global_metrics(self) -> tuple[float, float, float, int]:
        t = self._t
        try:
            vehicles = t.vehicle.getIDList()
            n = len(vehicles)
            if n == 0:
                waiting_avg = 0.0
                speed_avg = 0.0
            else:
                waiting_vals = [t.vehicle.getWaitingTime(v) for v in vehicles]
                speed_vals = [t.vehicle.getSpeed(v) for v in vehicles]
                waiting_avg = sum(waiting_vals) / n
                speed_avg = sum(speed_vals) / n
        except Exception:
            waiting_avg = 0.0
            speed_avg = 0.0

        try:
            det_ids = t.lanearea.getIDList()
            occ_vals = [t.lanearea.getLastStepOccupancy(d) for d in det_ids]
            occupancy = sum(occ_vals) / len(occ_vals) if occ_vals else 0.0
        except Exception:
            occupancy = 0.0

        try:
            throughput = t.simulation.getArrivedNumber()
        except Exception:
            throughput = 0

        return waiting_avg, speed_avg, occupancy, throughput
