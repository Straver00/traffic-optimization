"""Experience replay buffer for off-policy learning."""

from __future__ import annotations

import random
from collections import deque
from typing import Deque, List, Optional, Tuple


Transition = Tuple[
    List[float],
    int,
    float,
    List[float],
    bool,
    Optional[List[int]],
    Optional[List[int]],
]


class ReplayBuffer:
    def __init__(self, capacity: int) -> None:
        self._buffer: Deque[Transition] = deque(maxlen=capacity)

    def __len__(self) -> int:
        return len(self._buffer)

    def push(
        self,
        state: List[float],
        action: int,
        reward: float,
        next_state: List[float],
        done: bool,
        valid_actions: Optional[List[int]] = None,
        next_valid_actions: Optional[List[int]] = None,
    ) -> None:
        self._buffer.append((state, action, reward, next_state, done, valid_actions, next_valid_actions))

    def sample(self, batch_size: int) -> List[Transition]:
        return random.sample(self._buffer, batch_size)
