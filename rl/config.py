"""Configuration objects for Double DQN training and inference."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActionConfig:
    keep_idx: int = 0
    extend_idx: int = 1
    switch_idx: int = 2
    extend_step_s: int = 5

    def size(self) -> int:
        return 3


@dataclass(frozen=True)
class StateConfig:
    include_waiting_time: bool = True
    include_speed_avg: bool = True
    include_occupancy: bool = True
    include_throughput: bool = False
    include_phase_one_hot: bool = True
    include_phase_time: bool = True
    queue_speed_threshold: float = 0.1


@dataclass(frozen=True)
class StateNormalization:
    queue_scale: float = 50.0
    waiting_time_scale: float = 10.0
    speed_scale: float = 15.0
    occupancy_scale: float = 100.0
    throughput_scale: float = 10.0
    phase_time_scale: float = 90.0


@dataclass(frozen=True)
class RewardConfig:
    w_queue: float = 0.30
    w_wait: float = 0.25
    w_speed: float = 0.1
    w_throughput: float = 0.1
    w_co2: float = 0.25
    w_switch: float = 0.08
    queue_scale: float = 50.0
    waiting_time_scale: float = 10.0
    speed_scale: float = 15.0
    throughput_scale: float = 10.0
    co2_scale: float = 50_000_000.0


@dataclass(frozen=True)
class ExplorationConfig:
    epsilon_start: float = 1.0
    epsilon_end: float = 0.05
    epsilon_decay_steps: int = 50_000


@dataclass(frozen=True)
class TrainingConfig:
    gamma: float = 0.99
    learning_rate: float = 1e-4
    batch_size: int = 64
    buffer_size: int = 100_000
    min_replay_size: int = 5_000
    target_update_interval: int = 1_000
    tau: float = 0.005
    use_soft_update: bool = True
    update_every: int = 1
    max_grad_norm: float = 1.0
    device: str = "cpu"


@dataclass(frozen=True)
class DQNConfig:
    action: ActionConfig = field(default_factory=ActionConfig)
    state: StateConfig = field(default_factory=StateConfig)
    norm: StateNormalization = field(default_factory=StateNormalization)
    reward: RewardConfig = field(default_factory=RewardConfig)
    exploration: ExplorationConfig = field(default_factory=ExplorationConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
