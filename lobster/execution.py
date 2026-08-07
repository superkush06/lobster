"""Execution costs — what it actually costs to get a position on.

The rest of the package is about the book. This module is about the bill.
Two objects, deliberately kept apart because they measure different things
and the literature routinely conflates them:

- `cost_to_trade` walks the resting book **read-only** and reports what a
  single market order of size Q would pay right now. That is *instantaneous*
  impact: it is arithmetic on the depth that happens to be resting, and its
  shape is whatever the depth profile's shape is.

- `execute_metaorder` works a parent order into a *running* simulation in
  child slices, so the book replenishes between children and the other
  agents react. That is the object the empirical impact literature measures
  — a metaorder worked over time — and it is the one whose exponent is worth
  comparing with published numbers.

`fit_power_law` is the two-line log-log OLS both of them get summarised by.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .book import OrderBook
from .matching import match
from .order import Order, OrderType, Side

if TYPE_CHECKING:
    from .sim import Simulation


@dataclass(frozen=True)
class Sweep:
    """The bill for a hypothetical market order, computed without trading."""

    side: Side
    requested: int
    filled: int
    notional: float
    arrival_mid: float
    mid_after: float

    @property
    def avg_price(self) -> float | None:
        """Volume-weighted price of the fills, or None if nothing filled."""
        return self.notional / self.filled if self.filled else None

    @property
    def slippage(self) -> float | None:
        """Signed cost per share against the arrival mid (positive = paid)."""
        avg = self.avg_price
        if avg is None:
            return None
        return self.side.value * (avg - self.arrival_mid)

    @property
    def impact(self) -> float:
        """Signed move of the mid caused by consuming the depth."""
        return self.side.value * (self.mid_after - self.arrival_mid)

    @property
    def complete(self) -> bool:
        return self.filled == self.requested


def cost_to_trade(book: OrderBook, side: Side, qty: int) -> Sweep | None:
    """What a market order of `qty` would pay against the book as it stands.

    Read-only: walks the opposite side's levels in priority order and
    accumulates notional, then reports the mid that would be left behind.
    Returns None if the book has no mid (one side empty), and a partial
    `Sweep` with `complete == False` if the book runs out of depth.
    """
    if qty <= 0:
        raise ValueError(f"qty must be positive, got {qty}")
    arrival = book.mid
    if arrival is None:
        return None
    opposite = side.opposite
    remaining, filled, notional = qty, 0, 0.0
    touch_after: float | None = None
    for level in book.iter_levels(opposite):
        if remaining <= 0:
            touch_after = level.price
            break
        take = min(remaining, level.total_qty)
        filled += take
        notional += take * level.price
        remaining -= take
        if take < level.total_qty:
            touch_after = level.price
            break
    else:
        touch_after = None  # walked the whole side away
    near = book.best_bid if side is Side.SELL else book.best_ask
    same = book.best_bid if side is Side.BUY else book.best_ask
    if near is None or same is None:  # unreachable: book.mid was not None above
        return None
    if touch_after is None:
        # Every level on the far side is gone; the best we can say is that the
        # touch moved to the last price traded.
        touch_after = notional / filled if filled else near
    mid_after = (touch_after + same) / 2.0
    return Sweep(side=side, requested=qty, filled=filled, notional=notional,
                 arrival_mid=arrival, mid_after=mid_after)


@dataclass(frozen=True)
class Metaorder:
    """A parent order worked into a live simulation in child slices."""

    side: Side
    requested: int
    filled: int
    notional: float
    arrival_mid: float
    end_mid: float | None
    decay_mid: float | None
    children: int

    @property
    def vwap(self) -> float | None:
        return self.notional / self.filled if self.filled else None

    @property
    def shortfall(self) -> float | None:
        """Implementation shortfall per share against the arrival mid."""
        v = self.vwap
        if v is None:
            return None
        return self.side.value * (v - self.arrival_mid)

    @property
    def peak_impact(self) -> float | None:
        """Mid displacement measured at the last child fill."""
        if self.end_mid is None:
            return None
        return self.side.value * (self.end_mid - self.arrival_mid)

    @property
    def permanent_impact(self) -> float | None:
        """Mid displacement still there `decay_steps` after the last child."""
        if self.decay_mid is None:
            return None
        return self.side.value * (self.decay_mid - self.arrival_mid)


def execute_metaorder(sim: Simulation, side: Side, total_qty: int, slice_qty: int, *,
                      every: int = 1, agent_id: int = 0,
                      start_ts: float = 0.0, dt: float = 1.0,
                      decay_steps: int = 0) -> Metaorder:
    """Work `total_qty` into a running `Simulation` as child market orders.

    The simulation is stepped forward; every `every` ticks a `slice_qty`
    market order is submitted through the same matching path the agents use,
    so the children compete with agent flow and the book refills in between.
    Ticks continue for `decay_steps` after the last child so the mid has a
    chance to revert.

    `agent_id` should be an id no agent in `sim` owns, unless you deliberately
    want the parent to interact with that agent's self-trade prevention.
    """
    if total_qty <= 0 or slice_qty <= 0:
        raise ValueError("total_qty and slice_qty must be positive")
    if every < 1:
        raise ValueError("every must be >= 1")
    arrival = sim.book.mid
    if arrival is None:
        raise ValueError("simulation book has no mid; warm it up first")
    filled, notional, children = 0, 0.0, 0
    requested = 0
    k = 0
    end_mid = None
    while requested < total_qty:
        ts = start_ts + k * dt
        sim.step(ts=ts, dt=dt)
        if k % every == 0:
            want = min(slice_qty, total_qty - requested)
            requested += want
            child = Order(side=side, qty=want, type=OrderType.MARKET,
                          agent_id=agent_id)
            trades = match(sim.book, child, on_trade=sim.tape.record,
                           ts=ts, stp=sim.stp)
            for t in trades:
                filled += t.qty
                notional += t.price * t.qty
            children += 1
            if sim.book.mid is not None:
                end_mid = sim.book.mid
        k += 1
    decay_mid = None
    for j in range(decay_steps):
        sim.step(ts=start_ts + (k + j) * dt, dt=dt)
    if decay_steps:
        decay_mid = sim.book.mid
    return Metaorder(side=side, requested=requested, filled=filled,
                     notional=notional, arrival_mid=arrival, end_mid=end_mid,
                     decay_mid=decay_mid, children=children)


def fit_power_law(xs: Sequence[float],
                  ys: Sequence[float]) -> tuple[float, float] | None:
    """OLS of log y on log x; returns ``(k, delta)`` for ``y = k * x**delta``.

    Points with a non-positive x or y are dropped (an impact estimate can
    come back negative from sampling noise). Returns None if fewer than
    three usable points survive or all the x's coincide.
    """
    pts = [(math.log(x), math.log(y))
           for x, y in zip(xs, ys, strict=True) if x > 0 and y > 0]
    if len(pts) < 3:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if sxx == 0.0:
        return None
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    delta = sxy / sxx
    return math.exp(my - delta * mx), delta
