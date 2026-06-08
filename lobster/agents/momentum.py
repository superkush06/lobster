"""MomentumAgent — chases recent tape imbalance."""

from __future__ import annotations

from ..order import Order, OrderType, Side
from .base import Agent, AgentContext


class MomentumAgent(Agent):
    """Sends marketable orders in the direction of recent tape imbalance.

    Imbalance = (buy-aggressor volume - sell-aggressor volume) / total volume
    over the last `lookback` trades. Trades market when |imbalance| > thresh.
    """

    def __init__(self, agent_id: int, lookback: int = 20,
                 threshold: float = 0.4, qty: int = 5) -> None:
        super().__init__(agent_id)
        self.lookback = lookback
        self.threshold = threshold
        self.qty = qty

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
        if imbalance > self.threshold and ctx.book.best_ask is not None:
            return [Order(side=Side.BUY, qty=self.qty, type=OrderType.MARKET,
                          agent_id=self.id, ts=ctx.ts)]
        if imbalance < -self.threshold and ctx.book.best_bid is not None:
            return [Order(side=Side.SELL, qty=self.qty, type=OrderType.MARKET,
                          agent_id=self.id, ts=ctx.ts)]
        return []
