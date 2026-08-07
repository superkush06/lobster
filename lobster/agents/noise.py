"""NoiseAgent — random limit + market orders around mid.

Includes a `market_order_rate` knob so callers can inject crossing flow
(marketable orders) into an otherwise passive book, which is necessary
to bootstrap trade activity in agent-based microstructure simulators.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..order import Order, OrderType, Side
from .base import Agent, AgentContext

if TYPE_CHECKING:
    from ..latency import LatencyModel


class NoiseAgent(Agent):
    """Submits a random buy/sell order with probability `intensity`.

    A fraction `market_order_rate` of those orders are marketable (cross
    the spread). The rest sit inside the spread as passive limits.
    """

    def __init__(self, agent_id: int, intensity: float = 0.3,
                 spread_offset: float = 0.5, qty: int = 10,
                 market_order_rate: float = 0.0,
                 ref_price: float = 100.0,
                 ttl: float | None = 50.0, latency: LatencyModel | None = None) -> None:
        super().__init__(agent_id, latency=latency)
        if not 0.0 <= market_order_rate <= 1.0:
            raise ValueError("market_order_rate must be in [0, 1]")
        self.intensity = intensity
        self.spread_offset = spread_offset
        self.qty = qty
        self.market_order_rate = market_order_rate
        # Passive quotes expire after `ttl` ticks (None = good-till-cancel).
        # Without expiry a long noise-only run leaves one resting order per
        # submission and the book thickens without bound.
        self.ttl = ttl
        # Anchor when the book has no mid: last observed mid (seeded with
        # `ref_price`), so a one-sided book doesn't snap quotes back to a
        # hardcoded constant after the price has drifted away from it.
        self._last_mid = ref_price

    def step(self, ctx: AgentContext) -> list[Order]:
        if ctx.rng.random() > self.intensity:
            return []
        mid = ctx.book.mid
        if mid is None:
            mid = self._last_mid
        else:
            self._last_mid = mid
        side = Side.BUY if ctx.rng.random() < 0.5 else Side.SELL
        if ctx.rng.random() < self.market_order_rate:
            if side is Side.BUY and ctx.book.best_ask is None:
                return []
            if side is Side.SELL and ctx.book.best_bid is None:
                return []
            return [Order(side=side, qty=self.qty, type=OrderType.MARKET,
                          agent_id=self.id, ts=ctx.ts)]
        if side is Side.BUY:
            price = round(mid - self.spread_offset * ctx.rng.random(), 2)
        else:
            price = round(mid + self.spread_offset * ctx.rng.random(), 2)
        return [Order(side=side, qty=self.qty, price=price,
                      agent_id=self.id, ts=ctx.ts, ttl=self.ttl)]
