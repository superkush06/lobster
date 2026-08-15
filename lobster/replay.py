"""LOBSTER-format message replay: reconstruct book state from a message stream.

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

Feeding such a stream through `replay()` rebuilds the visible limit order
book. Prices are taken as-is (LOBSTER stores price * 10000; pass
`price_scale=1e-4` to convert to dollars).

Real message files reference orders that were already resting when the
capture window opened, so a cold-start replay *will* see executions and
cancels for order ids it has never been told about. What happens next is the
``on_unknown`` policy:

``"count"`` (default)
    Count the event on `ReplayStats` (``unknown_execs`` / ``unknown_cancels``
    / ``unknown_deletes``) and leave the book alone.
``"reduce_level"``
    Also decrement resting depth at the event's ``(side, price)`` by its
    size, front of the FIFO first. A snapshot seed puts depth on the book
    without the exchange's order ids, so this is the only way an event
    against a pre-window order can land where the snapshot says the shares
    are. Events that fully land count as ``level_reduced``; any shortfall
    (level short or absent) counts as ``unresolvable``. The corruption risk
    is double removal: if the id later turns out to be live after all — or
    the same pre-window shares are hit once by id guesswork and once by
    level — depth is removed twice and the reconstruction runs shallow, so
    this policy belongs with a snapshot seed and a diff against the
    exchange's own orderbook file, never on faith.
``"raise"``
    Raise `UnknownOrderError` on the first such event (``strict=True`` is
    the older spelling and takes precedence).

To reconstruct depth faithfully, seed the opening book from the companion
orderbook file via `OrderBook.from_snapshot` before replaying:

    book = OrderBook.from_snapshot(bids=[(99.5, 300)], asks=[(100.0, 250)])
    stats = ReplayStats()
    replay_csv("messages.csv", price_scale=1e-4, book=book, stats=stats,
               on_unknown="reduce_level")
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .book import OrderBook
from .order import Order, Side

NEW = 1
PARTIAL_CANCEL = 2
DELETE = 3
EXECUTE_VISIBLE = 4
EXECUTE_HIDDEN = 5
CROSS = 6
HALT = 7


class UnknownOrderError(KeyError):
    """A cancel/execute referenced an order id the book has never seen."""


@dataclass
class ReplayStats:
    """Counters for how faithfully a message stream applied to the book.

    A cold-start replay of a real LOBSTER file (no snapshot bootstrap) will
    typically show non-zero unknown_* counts: those are events against
    orders resting before the capture window. If any unknown counter is
    non-zero, reconstructed depth has drifted from the exchange's book.
    """

    applied: int = 0
    unknown_execs: int = 0
    unknown_cancels: int = 0
    unknown_deletes: int = 0
    # Outcomes of unknown events under on_unknown="reduce_level". The
    # unknown_* counters above record the fact of the stream; these record
    # what the policy managed to do about it.
    level_reduced: int = 0
    unresolvable: int = 0
    skipped_types: dict[int, int] = field(default_factory=dict)

    @property
    def unknown_total(self) -> int:
        return self.unknown_execs + self.unknown_cancels + self.unknown_deletes

    @property
    def clean(self) -> bool:
        """True when every book-touching event applied to a known order."""
        return self.unknown_total == 0


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


def apply_message(book: OrderBook, msg: Message, *,
                  strict: bool = False,
                  stats: ReplayStats | None = None,
                  on_unknown: str = "count") -> None:
    """Apply a single message to the book, mutating it in place.

    Events that reference an order id the book does not hold (pre-window
    orders in a cold-start replay) follow the `on_unknown` policy described
    in the module docstring; `strict=True` forces ``"raise"``.
    """
    if on_unknown not in ("count", "reduce_level", "raise"):
        raise ValueError(f"on_unknown must be count|reduce_level|raise, got {on_unknown!r}")
    if msg.event_type == NEW:
        # allow_crossed: with incomplete pre-window context a real feed can
        # transiently look crossed; trust the exchange's message stream.
        book.add(Order(side=msg.side, qty=msg.size, price=msg.price,
                       agent_id=0, id=msg.order_id, ts=msg.time),
                 allow_crossed=True)
        if stats is not None:
            stats.applied += 1
    elif msg.event_type in (PARTIAL_CANCEL, EXECUTE_VISIBLE):
        # Both remove `size` shares from a known resting order.
        removed = book.reduce(msg.order_id, msg.size)
        if removed == 0:
            _unknown(book, msg, strict, stats, on_unknown)
        elif stats is not None:
            stats.applied += 1
    elif msg.event_type == DELETE:
        cancelled = book.cancel(msg.order_id)
        if cancelled is None:
            _unknown(book, msg, strict, stats, on_unknown)
        elif stats is not None:
            stats.applied += 1
    else:
        # EXECUTE_HIDDEN / CROSS / HALT leave the visible book unchanged.
        if stats is not None:
            stats.skipped_types[msg.event_type] = (
                stats.skipped_types.get(msg.event_type, 0) + 1
            )


def _unknown(book: OrderBook, msg: Message, strict: bool,
             stats: ReplayStats | None, on_unknown: str) -> None:
    if strict or on_unknown == "raise":
        raise UnknownOrderError(
            f"event type {msg.event_type} at t={msg.time} references unknown "
            f"order id {msg.order_id} (resting before the capture window?)"
        )
    if stats is not None:
        if msg.event_type == PARTIAL_CANCEL:
            stats.unknown_cancels += 1
        elif msg.event_type == EXECUTE_VISIBLE:
            stats.unknown_execs += 1
        else:
            stats.unknown_deletes += 1
    if on_unknown == "reduce_level":
        removed = book.reduce_at(msg.side, msg.price, msg.size)
        if stats is not None:
            if removed == msg.size:
                stats.level_reduced += 1
            else:
                stats.unresolvable += 1


def replay(messages: list[Message], book: OrderBook | None = None, *,
           strict: bool = False,
           stats: ReplayStats | None = None,
           on_unknown: str = "count") -> OrderBook:
    """Apply a sequence of messages and return the resulting book."""
    book = book if book is not None else OrderBook()
    for msg in messages:
        apply_message(book, msg, strict=strict, stats=stats, on_unknown=on_unknown)
    return book


def replay_csv(path: str, *, price_scale: float = 1.0,
               book: OrderBook | None = None,
               strict: bool = False,
               stats: ReplayStats | None = None,
               on_unknown: str = "count") -> OrderBook:
    """Replay a LOBSTER message CSV file from disk."""
    book = book if book is not None else OrderBook()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            apply_message(book, parse_lobster_line(line, price_scale=price_scale),
                          strict=strict, stats=stats, on_unknown=on_unknown)
    return book
