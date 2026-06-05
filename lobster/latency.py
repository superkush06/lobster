"""Latency models for simulated order submission delays."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod


class LatencyModel(ABC):
    @abstractmethod
    def sample(self, rng: random.Random) -> float:
        """Return a non-negative delay in simulated time units."""


class ConstantLatency(LatencyModel):
    def __init__(self, delay: float = 1.0) -> None:
        if delay < 0:
            raise ValueError("delay must be non-negative")
        self.delay = delay

    def sample(self, rng: random.Random) -> float:
        return self.delay


class JitteredLatency(LatencyModel):
    """Gamma-distributed latency with given mean and shape.

    Higher shape → less variance. Shape=1 is exponential (memoryless).
    """

    def __init__(self, mean: float = 1.0, shape: float = 2.0) -> None:
        if mean <= 0 or shape <= 0:
            raise ValueError("mean and shape must be positive")
        self.mean = mean
        self.shape = shape

    def sample(self, rng: random.Random) -> float:
        scale = self.mean / self.shape
        return rng.gammavariate(self.shape, scale)
