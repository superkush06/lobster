"""MarketMakerAgent — quotes both sides, skews on inventory."""

from __future__ import annotations

from ..order import Order, Side
from .base import Agent, AgentContext


class MarketMakerAgent(Agent):
    """Posts symmetric quotes around mid; widens & skews on inventory.

    Heuristic: quote bid = mid - half_spread - inv_skew * inventory
               quote ask = mid + half_spread - inv_skew * inventory
    Inventory cap: don't quote the side that would worsen inventory beyond cap.
    """

    def __init__(self, agent_id: int, half_spread: float = 0.5,
                 qty: int = 20, inv_skew: float = 0.01,
                 inventory_cap: int = 200) -> None:
        super().__init__(agent_id)
        self.half_spread = half_spread
        self.qty = qty
        self.inv_skew = inv_skew
        self.inventory_cap = inventory_cap

    def step(self, ctx: AgentContext) -> list[Order]:
        mid = ctx.book.mid
        if mid is None:
            mid = 100.0
        skew = self.inv_skew * self.inventory
        bid_price = round(mid - self.half_spread - skew, 2)
        ask_price = round(mid + self.half_spread - skew, 2)
        orders = []
        if self.inventory < self.inventory_cap:
            orders.append(Order(side=Side.BUY, qty=self.qty, price=bid_price,
                                agent_id=self.id, ts=ctx.ts))
        if self.inventory > -self.inventory_cap:
            orders.append(Order(side=Side.SELL, qty=self.qty, price=ask_price,
                                agent_id=self.id, ts=ctx.ts))
        return orders
