"""Simulation event loop.

P&L attribution: trades carry agent ids (see matching.match), and after each
submitted order is matched we call `Agent.on_fill` for the buyer/seller agent
that appears in the resulting Trade. Order ids are *not* used here — they
are an internal book-keeping concern of the matching engine and OrderBook.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, field

from .agents.base import Agent, AgentContext
from .book import OrderBook
from .matching import match
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
    _rng: random.Random = field(init=False)
    metrics: list[StepMetrics] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def step(self, ts: float) -> StepMetrics:
        ctx = AgentContext(book=self.book, tape=self.tape, rng=self._rng, ts=ts)
        # Each agent gets to submit; we shuffle ordering to avoid bias.
        order_ix = list(range(len(self.agents)))
        self._rng.shuffle(order_ix)
        n_trades_before = len(self.tape)
        for i in order_ix:
            agent = self.agents[i]
            for new_order in agent.step(ctx):
                trades = match(self.book, new_order,
                               on_trade=self.tape.record, ts=ts)
                # Update agent P&L for fills they participated in.
                for t in trades:
                    self._apply_trade_to_agents(t)
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
            yield self.step(ts=k * dt)

    def _apply_trade_to_agents(self, t: Trade) -> None:
        for agent in self.agents:
            if agent.id == t.buyer_id:
                agent.on_fill(side_sign=+1, price=t.price, qty=t.qty)
            if agent.id == t.seller_id:
                agent.on_fill(side_sign=-1, price=t.price, qty=t.qty)
