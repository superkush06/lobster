"""Market impact models — estimates of permanent + temporary price change."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod


class ImpactModel(ABC):
    @abstractmethod
    def impact(self, side_sign: int, qty: int) -> float:
        """Signed price impact for a trade of `qty` (positive int) on `side_sign`.

        side_sign is +1 for buys (pushes price up), -1 for sells.
        Returns the signed price change in price units.
        """


class LinearImpact(ImpactModel):
    """`eta * Q`. Simplest model; impact is linear in size."""

    def __init__(self, eta: float = 0.001) -> None:
        if eta < 0:
            raise ValueError("eta must be non-negative")
        self.eta = eta

    def impact(self, side_sign: int, qty: int) -> float:
        return side_sign * self.eta * qty


class SquareRootImpact(ImpactModel):
    """Almgren–Chriss-style sqrt model: `eta * sqrt(Q / V)`.

    Empirically observed to fit equities well: doubling trade size only
    increases impact by √2, not 2.
    """

    def __init__(self, eta: float = 0.1, daily_volume: float = 1e6) -> None:
        if eta < 0 or daily_volume <= 0:
            raise ValueError("eta must be >=0 and daily_volume > 0")
        self.eta = eta
        self.daily_volume = daily_volume

    def impact(self, side_sign: int, qty: int) -> float:
        return side_sign * self.eta * math.sqrt(qty / self.daily_volume)
