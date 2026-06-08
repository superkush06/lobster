"""LOBSTER-format message replay — reconstruct book state from a message stream.

The LOBSTER dataset (https://lobsterdata.com) distributes NASDAQ order flow as
CSV "message" files, one event per row:

    Time, EventType, OrderID, Size, Price, Direction

EventType:
    1  new limit order
    2  partial cancellation (Size shares removed)
    3  full deletion of a limit order
    4  execution of a visible limit order (Size shares matched)
    5  execution of a hidden order        (no visible-book change)
    6  cross / auction trade              (no visible-book change here)
    7  trading halt indicator             (no book change)

Direction:  1 = buy (bid side), -1 = sell (ask side).

Feeding such a stream through `replay()` rebuilds the limit order book exactly
as the exchange saw it — which is what makes `lobster` usable on real data, not
just its own simulator. Prices are taken as-is (LOBSTER stores price * 10000;
pass `price_scale=1e-4` to convert to dollars).
"""

from __future__ import annotations

from dataclasses import dataclass

from .book import OrderBook
from .order import Order, Side

NEW = 1
PARTIAL_CANCEL = 2
DELETE = 3
EXECUTE_VISIBLE = 4
EXECUTE_HIDDEN = 5
CROSS = 6
HALT = 7


@dataclass(frozen=True)
class Message:
    """A single LOBSTER order-flow event."""
    time: float
    event_type: int
    order_id: int
    size: int
    price: float
    direction: int  # 1 = buy, -1 = sell

    @property
    def side(self) -> Side:
        return Side.BUY if self.direction == 1 else Side.SELL


def parse_lobster_line(line: str, *, price_scale: float = 1.0) -> Message:
    """Parse one CSV row of a LOBSTER message file into a `Message`."""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 6:
        raise ValueError(f"expected 6 LOBSTER columns, got {len(parts)}: {line!r}")
    return Message(
        time=float(parts[0]),
        event_type=int(parts[1]),
        order_id=int(parts[2]),
        size=int(parts[3]),
        price=float(parts[4]) * price_scale,
        direction=int(parts[5]),
    )


def apply_message(book: OrderBook, msg: Message) -> None:
    """Apply a single message to the book, mutating it in place."""
    if msg.event_type == NEW:
        book.add(Order(side=msg.side, qty=msg.size, price=msg.price,
                       agent_id=0, id=msg.order_id, ts=msg.time))
    elif msg.event_type in (PARTIAL_CANCEL, EXECUTE_VISIBLE):
        # Both remove `size` shares from a known resting order.
        book.reduce(msg.order_id, msg.size)
    elif msg.event_type == DELETE:
        book.cancel(msg.order_id)
    # EXECUTE_HIDDEN / CROSS / HALT leave the visible book unchanged.


def replay(messages: list[Message], book: OrderBook | None = None) -> OrderBook:
    """Apply a sequence of messages and return the resulting book."""
    book = book if book is not None else OrderBook()
    for msg in messages:
        apply_message(book, msg)
    return book


def replay_csv(path: str, *, price_scale: float = 1.0,
               book: OrderBook | None = None) -> OrderBook:
    """Replay a LOBSTER message CSV file from disk."""
    book = book if book is not None else OrderBook()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            apply_message(book, parse_lobster_line(line, price_scale=price_scale))
    return book
