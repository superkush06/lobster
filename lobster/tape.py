"""Trade tape — records executed trades."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .order import Side


@dataclass(frozen=True)
class Trade:
    price: float
    qty: int
    buyer_id: int
    seller_id: int
    ts: float
    aggressor: Side  # which side initiated the trade


class Tape:
    """Buffer of executed trades, unbounded by default.

    Pass `maxlen` to bound memory in very long runs — but note that
    analytics (markout, imbalance) iterate the tape, so a bounded tape
    silently windows them to the last `maxlen` trades. `evicted` /
    `truncated` report whether that has happened.
    """

    def __init__(self, maxlen: int | None = None) -> None:
        self._buf: deque[Trade] = deque(maxlen=maxlen)
        self._evicted = 0

    @property
    def evicted(self) -> int:
        """Number of trades dropped from the front (0 when unbounded)."""
        return self._evicted

    @property
    def truncated(self) -> bool:
        """True once at least one trade has been evicted; analytics that
        iterate this tape then only see a suffix of the trade history."""
        return self._evicted > 0

    def record(self, trade: Trade) -> None:
        if self._buf.maxlen is not None and len(self._buf) == self._buf.maxlen:
            self._evicted += 1
        self._buf.append(trade)

    def recent(self, n: int = 100) -> list[Trade]:
        if n >= len(self._buf):
            return list(self._buf)
        return list(self._buf)[-n:]

    def __len__(self) -> int:
        return len(self._buf)

    def __iter__(self):
        return iter(self._buf)

    def vwap(self, n: int = 100) -> float | None:
        trades = self.recent(n)
        if not trades:
            return None
        notional = sum(t.price * t.qty for t in trades)
        volume = sum(t.qty for t in trades)
        return notional / volume if volume > 0 else None
