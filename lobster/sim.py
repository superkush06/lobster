"""Simulation event loop.

P&L attribution: trades carry agent ids (see matching.match), and after each
submitted order is matched we call `Agent.on_fill` for the buyer/seller agent
that appears in the resulting Trade. Order ids are *not* used here, and they
are an internal book-keeping concern of the matching engine and OrderBook.

Exchange-style hygiene, on by default:

- **Self-trade prevention** (`stp="cancel_resting"`): an agent crossing its
  own stale quote cancels it instead of printing a wash trade. Without this,
  a majority of trades in the default configs were an agent trading with
  itself, contaminating every tape-derived statistic. Pass `stp=None` to
  reproduce the old behavior.
- **Order TTL**: orders with `Order.ttl` set are cancelled `ttl` time units
  after submission, so passive flow (e.g. NoiseAgent quotes) does not pile
  up into an ever-thickening book.

Latency (event-driven arrivals): when an agent has a `latency` model, each
order it emits is queued and only reaches the matching engine
`latency.sample(rng)` time units after the decision. Arrivals are processed
in timestamp order from a heap, so two agents reacting to the same tick race
to the book and the faster one wins time priority, which is what makes
queue-position and latency questions studiable. Agents without a latency
model (the default) submit instantly, reproducing the synchronous loop
exactly. Trades from delayed arrivals are stamped with their arrival time.
"""

from __future__ import annotations

import heapq
import random
from collections.abc import Iterable
from dataclasses import dataclass, field

from .agents.base import Agent, AgentContext
from .book import OrderBook
from .matching import match
from .order import Order
from .tape import Tape, Trade


@dataclass
class StepMetrics:
    ts: float
    best_bid: float | None
    best_ask: float | None
    mid: float | None
    spread: float | None
    n_trades: int


@dataclass
class Simulation:
    agents: list[Agent]
    book: OrderBook = field(default_factory=OrderBook)
    tape: Tape = field(default_factory=Tape)
    seed: int = 0
    stp: str | None = "cancel_resting"
    _rng: random.Random = field(init=False)
    metrics: list[StepMetrics] = field(default_factory=list)
    _expiries: list[tuple[float, int]] = field(init=False, default_factory=list)
    _arrivals: list[tuple[float, int, Order]] = field(init=False,
                                                      default_factory=list)
    _arrival_seq: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def step(self, ts: float, dt: float = 1.0) -> StepMetrics:
        # Sweep TTL'd resting orders that expired by now (no-op if filled).
        while self._expiries and self._expiries[0][0] <= ts:
            _, oid = heapq.heappop(self._expiries)
            self.book.cancel(oid)
        # Deliver in-flight orders due by the start of this tick.
        self._drain_arrivals(ts, inclusive=True)
        ctx = AgentContext(book=self.book, tape=self.tape, rng=self._rng, ts=ts)
        # Each agent gets to submit; we shuffle ordering to avoid bias.
        order_ix = list(range(len(self.agents)))
        self._rng.shuffle(order_ix)
        n_trades_before = len(self.tape)
        for i in order_ix:
            agent = self.agents[i]
            for new_order in agent.step(ctx):
                delay = (agent.latency.sample(self._rng)
                         if agent.latency is not None else 0.0)
                if delay <= 0.0:
                    # Degenerate case: no latency -> match immediately, which
                    # is exactly the synchronous shuffled loop.
                    self._submit(new_order, ts)
                else:
                    self._arrival_seq += 1
                    heapq.heappush(self._arrivals,
                                   (ts + delay, self._arrival_seq, new_order))
        # Deliver arrivals that land within this tick, in timestamp order:
        # this is where a faster agent beats a slower one to the queue.
        self._drain_arrivals(ts + dt, inclusive=False)
        m = StepMetrics(
            ts=ts,
            best_bid=self.book.best_bid,
            best_ask=self.book.best_ask,
            mid=self.book.mid,
            spread=self.book.spread,
            n_trades=len(self.tape) - n_trades_before,
        )
        self.metrics.append(m)
        return m

    def run(self, steps: int, dt: float = 1.0) -> Iterable[StepMetrics]:
        for k in range(steps):
            yield self.step(ts=k * dt, dt=dt)

    def _drain_arrivals(self, until: float, inclusive: bool) -> None:
        """Deliver queued arrivals due before `until` in timestamp order."""
        while self._arrivals:
            due = self._arrivals[0][0]
            if not (due <= until if inclusive else due < until):
                break
            arrival_ts, _, order = heapq.heappop(self._arrivals)
            self._submit(order, arrival_ts)

    def _submit(self, order: Order, ts: float) -> None:
        trades = match(self.book, order, on_trade=self.tape.record,
                       ts=ts, stp=self.stp)
        # Update agent P&L for fills they participated in.
        for t in trades:
            self._apply_trade_to_agents(t)
        # Schedule expiry for the resting remainder of TTL'd orders.
        if (order.ttl is not None and order.qty > 0
                and order.id in self.book._index):
            heapq.heappush(self._expiries, (ts + order.ttl, order.id))

    def _apply_trade_to_agents(self, t: Trade) -> None:
        for agent in self.agents:
            if agent.id == t.buyer_id:
                agent.on_fill(side_sign=+1, price=t.price, qty=t.qty)
            if agent.id == t.seller_id:
                agent.on_fill(side_sign=-1, price=t.price, qty=t.qty)
