"""Double DQN agent with target network and replay buffer."""

from __future__ import annotations

import random
from typing import List, Optional

import torch
from dataclasses import asdict
from torch import nn

from rl.config import DQNConfig
from rl.epsilon_schedule import EpsilonSchedule
from rl.q_network import QNetwork
from rl.replay_buffer import ReplayBuffer


class DoubleDQNAgent:
    def __init__(self, state_dim: int, action_dim: int, config: DQNConfig) -> None:
        self._config = config
        self._device = torch.device(config.training.device)
        self._action_dim = action_dim

        self._q_net = QNetwork(state_dim, action_dim).to(self._device)
        self._target_net = QNetwork(state_dim, action_dim).to(self._device)
        self._target_net.load_state_dict(self._q_net.state_dict())
        self._target_net.eval()

        self._optimizer = torch.optim.Adam(self._q_net.parameters(), lr=config.training.learning_rate)
        self._loss_fn = nn.SmoothL1Loss()

        self._buffer = ReplayBuffer(config.training.buffer_size)
        self._epsilon = EpsilonSchedule(
            config.exploration.epsilon_start,
            config.exploration.epsilon_end,
            config.exploration.epsilon_decay_steps,
        )
        self._step_count = 0
        self._update_count = 0

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    def save(self, path: str) -> None:
        payload = {
            "model": self._q_net.state_dict(),
            "config": asdict(self._config),
        }
        torch.save(payload, path)

    def load(self, path: str) -> None:
        try:
            payload = torch.load(path, map_location=self._device, weights_only=False)
        except TypeError:
            payload = torch.load(path, map_location=self._device)

        state_dict = payload["model"] if isinstance(payload, dict) and "model" in payload else payload
        self._q_net.load_state_dict(state_dict)
        self._target_net.load_state_dict(self._q_net.state_dict())

    def select_action(
        self,
        state: List[float],
        valid_actions: Optional[List[int]],
        training: bool = True,
    ) -> int:
        if not valid_actions:
            valid_actions = list(range(self._action_dim))

        epsilon = self._epsilon.value(self._step_count) if training else self._epsilon.end
        self._step_count += 1

        if training and random.random() < epsilon:
            return random.choice(valid_actions)

        with torch.no_grad():
            state_tensor = torch.tensor([state], dtype=torch.float32, device=self._device)
            q_values = self._q_net(state_tensor).squeeze(0)
            return self._masked_argmax(q_values, valid_actions)

    def store_transition(
        self,
        state: List[float],
        action: int,
        reward: float,
        next_state: List[float],
        done: bool,
        valid_actions: Optional[List[int]],
        next_valid_actions: Optional[List[int]],
    ) -> None:
        self._buffer.push(state, action, reward, next_state, done, valid_actions, next_valid_actions)

    def learn(self) -> Optional[float]:
        cfg = self._config.training
        if len(self._buffer) < cfg.min_replay_size:
            return None
        if self._update_count % cfg.update_every != 0:
            self._update_count += 1
            return None

        batch = self._buffer.sample(cfg.batch_size)
        states, actions, rewards, next_states, dones, valid_actions, next_valid_actions = zip(*batch)

        state_tensor = torch.tensor(states, dtype=torch.float32, device=self._device)
        action_tensor = torch.tensor(actions, dtype=torch.int64, device=self._device).unsqueeze(1)
        reward_tensor = torch.tensor(rewards, dtype=torch.float32, device=self._device).unsqueeze(1)
        next_state_tensor = torch.tensor(next_states, dtype=torch.float32, device=self._device)
        done_tensor = torch.tensor(dones, dtype=torch.float32, device=self._device).unsqueeze(1)

        q_values = self._q_net(state_tensor).gather(1, action_tensor)

        with torch.no_grad():
            next_q_online = self._q_net(next_state_tensor)
            next_action_indices = self._masked_argmax_batch(next_q_online, list(next_valid_actions))
            next_q_target = self._target_net(next_state_tensor).gather(1, next_action_indices)
            targets = reward_tensor + cfg.gamma * (1.0 - done_tensor) * next_q_target

        loss = self._loss_fn(q_values, targets)
        self._optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self._q_net.parameters(), cfg.max_grad_norm)
        self._optimizer.step()

        if cfg.use_soft_update:
            self._soft_update(cfg.tau)
        elif self._step_count % cfg.target_update_interval == 0:
            self._hard_update()

        self._update_count += 1
        return float(loss.item())

    def _soft_update(self, tau: float) -> None:
        for target_param, param in zip(self._target_net.parameters(), self._q_net.parameters()):
            target_param.data.copy_(tau * param.data + (1.0 - tau) * target_param.data)

    def _hard_update(self) -> None:
        self._target_net.load_state_dict(self._q_net.state_dict())

    @staticmethod
    def _masked_argmax(q_values: torch.Tensor, valid_actions: List[int]) -> int:
        mask = torch.full_like(q_values, -1e9)
        mask[valid_actions] = 0.0
        return int(torch.argmax(q_values + mask).item())

    @staticmethod
    def _masked_argmax_batch(
        q_values: torch.Tensor,
        valid_actions_batch: List[Optional[List[int]]],
    ) -> torch.Tensor:
        batch_size, action_dim = q_values.shape
        mask = torch.full((batch_size, action_dim), -1e9, device=q_values.device)
        for i, valid_actions in enumerate(valid_actions_batch):
            if not valid_actions:
                mask[i, :] = 0.0
            else:
                mask[i, valid_actions] = 0.0
        return torch.argmax(q_values + mask, dim=1, keepdim=True)
