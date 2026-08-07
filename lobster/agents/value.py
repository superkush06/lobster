"""ValueAgent: supplies liquidity against deviations from a fundamental value.

This is the agent `docs/validation.md` kept asking for. Every other agent here
quotes off the *mid*: the market maker centres on it, the noise traders sample
around it, the chaser follows it. So when a metaorder walks the book, nothing
pushes back. The maker re-quotes around a mid the metaorder has already moved
and the parent chases its own footprint, which is why cost came out convex in
size when the empirical law is famously concave.

A real book is the visible tip of a much larger reservoir of latent intentions.
Somebody who thinks the stock is worth 100 does not show all of their size at
100.05; they show a little there and more the further the price runs away from
what they think it is worth. That shape is the whole mechanism:

    depth at distance d from value  ~  slope * d          (linear in d)
    shares available within D       ~  slope * D^2 / 2
    so to buy Q you must walk       D ~ sqrt(2Q / slope)

which is the square-root law. Part 1c of the validation doc already shows the
estimator recovering 0.50 from a book engineered to have exactly this profile;
this agent is what puts that profile into a *simulated* book instead of a
hand-built one.

Resilience is deliberately partial. The ladder tops up by at most `refill`
shares per tick, so a parent order that consumes liquidity faster than that
outruns the replenishment and walks outward into the thicker levels. Cancel
and replace the whole ladder every tick instead and the book becomes perfectly
elastic: price snaps back between children and impact vanishes, which is as
wrong as the convex answer, in the other direction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..order import Order, Side
from .base import Agent, AgentContext

if TYPE_CHECKING:
    from ..latency import LatencyModel


class ValueAgent(Agent):
    """Ladders passive size around `value`, thicker the further out it goes.

    `slope` sets shares per level-index, so level *i* targets ``slope * i``
    shares at ``value +/- i * tick``. `refill` caps how many shares it will
    add per tick across all levels, nearest the value first.

    `value_drift` random-walks the fundamental so the price is not pinned to a
    constant; the mid then tracks a moving efficient price plus microstructure
    noise, which is the textbook decomposition.
    """

    # Defaults are the calibration docs/validation.md 2c reports against: they
    # put the bundled mix's cost exponent on the empirical 0.5 to 0.6 band.
    # `slope` and `refill` are the two that matter. Raising either makes the
    # book too elastic for a parent order to walk at all and drives the
    # exponent back toward 1.
    def __init__(self, agent_id: int, value: float = 100.0, levels: int = 40,
                 tick: float = 0.05, slope: float = 2.0, refill: int = 10,
                 value_drift: float = 0.02, max_position: int = 20_000,
                 latency: LatencyModel | None = None) -> None:
        super().__init__(agent_id, latency=latency)
        if levels < 1:
            raise ValueError("levels must be >= 1")
        if tick <= 0:
            raise ValueError("tick must be positive")
        if slope <= 0:
            raise ValueError("slope must be positive")
        if refill < 1:
            raise ValueError("refill must be >= 1")
        self.value = value
        self.levels = levels
        self.tick = tick
        self.slope = slope
        self.refill = refill
        self.value_drift = value_drift
        self.max_position = max_position
        # How much size we believe we still have resting at each (side, price).
        # Tracked from our own fills rather than read back off the book, so the
        # agent needs no privileged access to the engine's internals.
        self._resting: dict[tuple[Side, float], int] = {}
        self._ids: dict[tuple[Side, float], list[int]] = {}

    def _target(self, i: int) -> int:
        return max(1, round(self.slope * i))

    def _grid(self) -> list[tuple[Side, float, int]]:
        """(side, price, target size) for every rung, nearest the value first."""
        out = []
        for i in range(1, self.levels + 1):
            d = i * self.tick
            out.append((Side.SELL, round(self.value + d, 2), self._target(i)))
            out.append((Side.BUY, round(self.value - d, 2), self._target(i)))
        return out

    def on_fill(self, side_sign: int, price: float, qty: int) -> None:
        super().on_fill(side_sign, price, qty)
        # A buy fill consumed one of our resting bids, and vice versa.
        key = (Side.BUY if side_sign > 0 else Side.SELL, round(price, 2))
        if key in self._resting:
            self._resting[key] = max(0, self._resting[key] - qty)

    def step(self, ctx: AgentContext) -> list[Order]:
        if self.value_drift:
            self.value = round(self.value + ctx.rng.gauss(0.0, self.value_drift), 4)
            self._retire_stranded(ctx)

        budget = self.refill
        orders: list[Order] = []
        for side, price, target in self._grid():
            if budget <= 0:
                break
            key = (side, price)
            have = self._resting.get(key, 0)
            want = target - have
            if want <= 0:
                continue
            # Do not build a position we have already said we do not want.
            if side is Side.BUY and self.inventory >= self.max_position:
                continue
            if side is Side.SELL and self.inventory <= -self.max_position:
                continue
            add = min(want, budget)
            budget -= add
            o = Order(side=side, qty=add, price=price,
                      agent_id=self.id, ts=ctx.ts)
            orders.append(o)
            self._resting[key] = have + add
            self._ids.setdefault(key, []).append(o.id)
        return orders

    def _retire_stranded(self, ctx: AgentContext) -> None:
        """Pull rungs that the drifting value has left outside the ladder."""
        lo = round(self.value - self.levels * self.tick, 2)
        hi = round(self.value + self.levels * self.tick, 2)
        for key in [k for k in self._resting if not (lo <= k[1] <= hi)]:
            for oid in self._ids.pop(key, []):
                ctx.book.cancel(oid)
            del self._resting[key]
