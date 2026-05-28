"""Order types, sides, and the Order dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from itertools import count

_id_counter = count(1)


def next_order_id() -> int:
    return next(_id_counter)


class Side(Enum):
    BUY = 1
    SELL = -1

    @property
    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(Enum):
    LIMIT = "limit"
    MARKET = "market"


@dataclass
class Order:
    """A resting or arriving order.

    `qty` mutates with fills; `price` is immutable. `id` is auto-assigned
    monotonically increasing if not given.
    """

    side: Side
    qty: int
    price: float | None = None
    type: OrderType = OrderType.LIMIT
    agent_id: int = 0
    id: int = field(default_factory=next_order_id)
    ts: float = 0.0

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValueError(f"qty must be positive, got {self.qty}")
        if self.type is OrderType.LIMIT and self.price is None:
            raise ValueError("limit order requires a price")
        if self.type is OrderType.MARKET and self.price is not None:
            raise ValueError("market order must not specify a price")

    @property
    def is_buy(self) -> bool:
        return self.side is Side.BUY

    def fill(self, qty: int) -> None:
        if qty <= 0 or qty > self.qty:
            raise ValueError(
                f"invalid fill {qty} for order with remaining qty {self.qty}"
            )
        self.qty -= qty
