"""Epsilon-greedy exploration schedule."""

from __future__ import annotations


class EpsilonSchedule:
    def __init__(self, start: float, end: float, decay_steps: int) -> None:
        self._start = start
        self._end = end
        self._decay_steps = max(1, decay_steps)

    @property
    def end(self) -> float:
        return self._end

    def value(self, step: int) -> float:
        if step >= self._decay_steps:
            return self._end
        ratio = 1.0 - (step / self._decay_steps)
        return self._end + (self._start - self._end) * ratio
