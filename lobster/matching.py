"""Matching engine — price-time priority crossing."""

from __future__ import annotations

from collections.abc import Callable

from .book import OrderBook
from .order import Order, OrderType, Side
from .tape import Trade

TradeCallback = Callable[[Trade], None]


def match(book: OrderBook, taker: Order,
          on_trade: TradeCallback | None = None,
          ts: float = 0.0) -> list[Trade]:
    """Match `taker` against `book`; return trades and mutate the book.

    Trades carry **agent_id**s, not order ids — consumers (e.g. the
    Simulation P&L bookkeeper) need to know *who* traded, not *which order*.
    Use `Order.id` directly if you need order-level traceability.
    """
    trades: list[Trade] = []
    opposite = taker.side.opposite

    while taker.qty > 0:
        levels = book._bids if opposite is Side.BUY else book._asks
        if not levels:
            break
        level = levels[0]
        if taker.type is OrderType.LIMIT and not _crosses(taker, level.price):
            break
        while taker.qty > 0 and level.orders:
            resting = level.orders[0]
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

    if taker.type is OrderType.LIMIT and taker.qty > 0:
        book.add(taker)
    return trades


def _crosses(taker: Order, level_price: float) -> bool:
    if taker.side is Side.BUY:
        return taker.price >= level_price  # type: ignore[operator]
    return taker.price <= level_price      # type: ignore[operator]
