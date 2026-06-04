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
    """Bounded buffer of recent trades."""

    def __init__(self, maxlen: int = 10_000) -> None:
        self._buf: deque[Trade] = deque(maxlen=maxlen)

    def record(self, trade: Trade) -> None:
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
