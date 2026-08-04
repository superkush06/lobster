"""Matching engine — price-time priority crossing."""

from __future__ import annotations

from collections.abc import Callable

from .book import OrderBook
from .order import Order, OrderType, Side
from .tape import Trade

TradeCallback = Callable[[Trade], None]


STP_POLICIES = ("cancel_resting", "cancel_taker")


def match(book: OrderBook, taker: Order,
          on_trade: TradeCallback | None = None,
          ts: float = 0.0,
          stp: str | None = None) -> list[Trade]:
    """Match `taker` against `book`; return trades and mutate the book.

    Trades carry **agent_id**s, not order ids — consumers (e.g. the
    Simulation P&L bookkeeper) need to know *who* traded, not *which order*.
    Use `Order.id` directly if you need order-level traceability.

    `taker` is mutated in place: `taker.qty` is decremented per fill, so
    after the call it holds the **leaves quantity**. A limit remainder is
    rested on the book; a market-order remainder is *not* (there is nothing
    left to match against) — check `taker.qty > 0` to detect that the book
    was exhausted before the order filled.

    `stp` (self-trade prevention) controls what happens when the taker would
    cross its own resting order (same `agent_id`), the way real venues do:

    - ``None``            — no prevention; the agent trades with itself.
    - ``"cancel_resting"``— the resting order is cancelled and matching
      continues (Nasdaq-style "cancel oldest").
    - ``"cancel_taker"``  — matching stops and the taker's remainder is
      discarded (not rested); the resting order survives.
    """
    if stp is not None and stp not in STP_POLICIES:
        raise ValueError(f"unknown stp policy {stp!r}; use one of {STP_POLICIES}")
    trades: list[Trade] = []
    opposite = taker.side.opposite
    taker_killed = False

    while taker.qty > 0 and not taker_killed:
        levels = book._bids if opposite is Side.BUY else book._asks
        if not levels:
            break
        level = levels[0]
        if taker.type is OrderType.LIMIT and not _crosses(taker, level.price):
            break
        while taker.qty > 0 and level.orders:
            resting = level.orders[0]
            if stp is not None and resting.agent_id == taker.agent_id:
                if stp == "cancel_resting":
                    level.orders.popleft()
                    level.total_qty -= resting.qty
                    book._index.pop(resting.id, None)
                    continue
                taker_killed = True  # cancel_taker
                break
            fill_qty = min(taker.qty, resting.qty)
            buyer_agent = resting.agent_id if opposite is Side.BUY else taker.agent_id
            seller_agent = taker.agent_id if opposite is Side.BUY else resting.agent_id
            trade = Trade(
                price=level.price, qty=fill_qty,
                buyer_id=buyer_agent, seller_id=seller_agent,
                ts=ts, aggressor=taker.side,
            )
            trades.append(trade)
            if on_trade is not None:
                on_trade(trade)
            resting.fill(fill_qty)
            taker.fill(fill_qty)
            level.total_qty -= fill_qty
            if resting.qty == 0:
                level.orders.popleft()
                book._index.pop(resting.id, None)
        if not level.orders:
            prices = book._bid_prices if opposite is Side.BUY else book._ask_prices
            del levels[0]
            del prices[0]

    if taker.type is OrderType.LIMIT and taker.qty > 0 and not taker_killed:
        book.add(taker)
    return trades


def _crosses(taker: Order, level_price: float) -> bool:
    if taker.side is Side.BUY:
        return taker.price >= level_price  # type: ignore[operator]
    return taker.price <= level_price      # type: ignore[operator]
