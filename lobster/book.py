"""Order book data structures.

A PriceLevel keeps FIFO order arrival queue at one price; OrderBook combines
both sides and exposes top-of-book queries.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .order import Order


@dataclass
class PriceLevel:
    price: float
    orders: deque[Order] = field(default_factory=deque)
    total_qty: int = 0

    def add(self, order: Order) -> None:
        assert order.price == self.price
        self.orders.append(order)
        self.total_qty += order.qty

    def cancel(self, order_id: int) -> Order | None:
        for i, o in enumerate(self.orders):
            if o.id == order_id:
                del self.orders[i]
                self.total_qty -= o.qty
                return o
        return None

    def __len__(self) -> int:
        return len(self.orders)
