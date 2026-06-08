"""Order book data structures.

A PriceLevel keeps FIFO order arrival queue at one price; OrderBook combines
both sides and exposes top-of-book queries.

Internal representation:
- `_bids`: list of PriceLevels sorted by best-bid (descending price).
- `_asks`: list of PriceLevels sorted ascending.
- Parallel `_bid_prices`/`_ask_prices` arrays for O(log n) bisect insertion.
  Bids store negated prices so bisect operates ascendingly on both sides.
"""

from __future__ import annotations

import bisect
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field

from .order import Order, Side


@dataclass
class PriceLevel:
    price: float
    orders: deque[Order] = field(default_factory=deque)
    total_qty: int = 0

    def add(self, order: Order) -> None:
        if order.price != self.price:
            raise ValueError(
                f"order price {order.price} does not match level {self.price}"
            )
        self.orders.append(order)
        self.total_qty += order.qty

    def reduce(self, order_id: int, qty: int) -> int:
        """Reduce a resting order's size by `qty` (partial execution/cancel).

        Removes the order entirely if it reaches zero. Returns the quantity
        actually removed (0 if `order_id` is not on this level).
        """
        for i, o in enumerate(self.orders):
            if o.id == order_id:
                removed = min(qty, o.qty)
                o.qty -= removed
                self.total_qty -= removed
                if o.qty == 0:
                    del self.orders[i]
                return removed
        return 0

    def cancel(self, order_id: int) -> Order | None:
        for i, o in enumerate(self.orders):
            if o.id == order_id:
                del self.orders[i]
                self.total_qty -= o.qty
                return o
        return None

    def __len__(self) -> int:
        return len(self.orders)


class OrderBook:
    def __init__(self) -> None:
        self._bids: list[PriceLevel] = []
        self._bid_prices: list[float] = []  # negated prices for ascending bisect
        self._asks: list[PriceLevel] = []
        self._ask_prices: list[float] = []
        self._index: dict[int, tuple[Side, float]] = {}

    # ---- top-of-book properties ---------------------------------------------

    @property
    def best_bid(self) -> float | None:
        return self._bids[0].price if self._bids else None

    @property
    def best_ask(self) -> float | None:
        return self._asks[0].price if self._asks else None

    @property
    def mid(self) -> float | None:
        bb, ba = self.best_bid, self.best_ask
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2.0

    @property
    def spread(self) -> float | None:
        bb, ba = self.best_bid, self.best_ask
        if bb is None or ba is None:
            return None
        return ba - bb

    @property
    def microprice(self) -> float | None:
        """Mid weighted by opposite-side size (Stoikov 2017 microprice)."""
        if not self._bids or not self._asks:
            return None
        bb, ba = self._bids[0], self._asks[0]
        denom = bb.total_qty + ba.total_qty
        if denom == 0:
            return self.mid
        return (bb.price * ba.total_qty + ba.price * bb.total_qty) / denom

    # ---- mutations ----------------------------------------------------------

    def add(self, order: Order) -> None:
        if order.price is None:
            raise ValueError("cannot rest an order with no price on the book")
        if order.is_buy:
            levels, prices = self._bids, self._bid_prices
            key = -order.price
        else:
            levels, prices = self._asks, self._ask_prices
            key = order.price
        idx = bisect.bisect_left(prices, key)
        if idx < len(prices) and prices[idx] == key:
            levels[idx].add(order)
        else:
            level = PriceLevel(order.price)
            level.add(order)
            prices.insert(idx, key)
            levels.insert(idx, level)
        self._index[order.id] = (order.side, order.price)

    def cancel(self, order_id: int) -> Order | None:
        info = self._index.pop(order_id, None)
        if info is None:
            return None
        side, price = info
        if side is Side.BUY:
            levels, prices = self._bids, self._bid_prices
            key = -price
        else:
            levels, prices = self._asks, self._ask_prices
            key = price
        idx = bisect.bisect_left(prices, key)
        if idx >= len(prices) or prices[idx] != key:
            return None
        cancelled = levels[idx].cancel(order_id)
        if not levels[idx].orders:
            del levels[idx]
            del prices[idx]
        return cancelled

    # ---- queries ------------------------------------------------------------

    def depth(self, side: Side, levels: int = 5) -> list[tuple[float, int]]:
        src = self._bids if side is Side.BUY else self._asks
        return [(lv.price, lv.total_qty) for lv in src[:levels]]

    def snapshot(self, levels: int = 5) -> dict:
        return {
            "bids": self.depth(Side.BUY, levels),
            "asks": self.depth(Side.SELL, levels),
            "mid": self.mid,
            "spread": self.spread,
            "microprice": self.microprice,
        }

    def iter_levels(self, side: Side) -> Iterator[PriceLevel]:
        return iter(self._bids if side is Side.BUY else self._asks)

    def __len__(self) -> int:
        return len(self._index)
