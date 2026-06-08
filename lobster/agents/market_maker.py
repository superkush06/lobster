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
                 inventory_cap: int = 200, cancel_replace: bool = True) -> None:
        super().__init__(agent_id)
        self.half_spread = half_spread
        self.qty = qty
        self.inv_skew = inv_skew
        self.inventory_cap = inventory_cap
        self.cancel_replace = cancel_replace
        # Order ids the maker currently has resting on the book.
        self._resting_ids: list[int] = []

    def step(self, ctx: AgentContext) -> list[Order]:
        # Cancel/replace: pull our previous quotes before re-quoting so the
        # book doesn't accumulate stale layers. Cancelling an already-filled
        # (or partially-filled) order is a safe no-op — the book ignores ids
        # it no longer holds.
        if self.cancel_replace:
            for oid in self._resting_ids:
                ctx.book.cancel(oid)
            self._resting_ids = []

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
        self._resting_ids = [o.id for o in orders]
        return orders
