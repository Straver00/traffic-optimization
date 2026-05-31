"""Neural network for Double DQN."""

from __future__ import annotations

from typing import Iterable

import torch
from torch import nn


class QNetwork(nn.Module):
    def __init__(self, input_dim: int, output_dim: int, hidden_sizes: Iterable[int] = (128, 128, 64)):
        super().__init__()
        layers = []
        last_dim = input_dim
        for size in hidden_sizes:
            layers.append(nn.Linear(last_dim, size))
            layers.append(nn.ReLU())
            last_dim = size
        layers.append(nn.Linear(last_dim, output_dim))
        self._net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self._net(x)
