"""Market impact models — estimates of permanent + temporary price change.

These are standalone estimators for pre-trade analysis (e.g. sizing a
parent order); the matching engine itself never applies them — price
impact in the simulator is *emergent* from orders eating through the
book's depth.
"""

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
    """Empirical square-root law: `eta * sqrt(Q / V)`.

    Doubling trade size only increases impact by √2, not 2 — a remarkably
    stable empirical regularity across asset classes (see e.g. Gatheral
    2010, "No-dynamic-arbitrage and market impact"). Note this is *not*
    Almgren–Chriss: their 2001 optimal-execution model uses impact that is
    linear in the trading rate. In full-strength versions eta carries a
    volatility scale (sigma * sqrt(Q/V)); here it is a free parameter.
    """

    def __init__(self, eta: float = 0.1, daily_volume: float = 1e6) -> None:
        if eta < 0 or daily_volume <= 0:
            raise ValueError("eta must be >=0 and daily_volume > 0")
        self.eta = eta
        self.daily_volume = daily_volume

    def impact(self, side_sign: int, qty: int) -> float:
        return side_sign * self.eta * math.sqrt(qty / self.daily_volume)
