"""MomentumAgent — chases recent tape imbalance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..order import Order, OrderType, Side
from .base import Agent, AgentContext

if TYPE_CHECKING:
    from ..latency import LatencyModel


class MomentumAgent(Agent):
    """Sends marketable orders in the direction of recent tape imbalance.

    Imbalance = (buy-aggressor volume - sell-aggressor volume) / total volume
    over the last `lookback` trades. Trades market when |imbalance| > thresh.

    `max_position` caps absolute inventory, like any real momentum desk:
    the agent's own marketable flow prints on the tape and feeds back into
    the very imbalance signal it chases, so an uncapped chaser on a clean
    (self-trade-free) tape can push the price into a runaway trend.
    """

    def __init__(self, agent_id: int, lookback: int = 20,
                 threshold: float = 0.4, qty: int = 5,
                 max_position: int | None = None, latency: LatencyModel | None = None) -> None:
        super().__init__(agent_id, latency=latency)
        self.lookback = lookback
        self.threshold = threshold
        self.qty = qty
        self.max_position = max_position

    def _allowed(self, side: Side) -> bool:
        if self.max_position is None:
            return True
        if side is Side.BUY:
            return self.inventory + self.qty <= self.max_position
        return self.inventory - self.qty >= -self.max_position

    def step(self, ctx: AgentContext) -> list[Order]:
        recent = ctx.tape.recent(self.lookback)
        if len(recent) < self.lookback:
            return []
        buy_vol = sum(t.qty for t in recent if t.aggressor is Side.BUY)
        sell_vol = sum(t.qty for t in recent if t.aggressor is Side.SELL)
        total = buy_vol + sell_vol
        if total == 0:
            return []
        imbalance = (buy_vol - sell_vol) / total
        if (imbalance > self.threshold and ctx.book.best_ask is not None
                and self._allowed(Side.BUY)):
            return [Order(side=Side.BUY, qty=self.qty, type=OrderType.MARKET,
                          agent_id=self.id, ts=ctx.ts)]
        if (imbalance < -self.threshold and ctx.book.best_bid is not None
                and self._allowed(Side.SELL)):
            return [Order(side=Side.SELL, qty=self.qty, type=OrderType.MARKET,
                          agent_id=self.id, ts=ctx.ts)]
        return []
