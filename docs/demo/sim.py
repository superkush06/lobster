"""Driver the browser demo calls into.

Kept in its own file, and kept small, because everything interesting already
lives in the package: this only wires two market makers with different wire
delays into a `Simulation` and reports what the tape says afterwards. The
numbers the page shows are the package's own — `Analytics`, `OrderBook`, the
matching engine — not a re-derivation in JavaScript.
"""

from __future__ import annotations

from lobster.agents import MarketMakerAgent, NoiseAgent
from lobster.analytics import Analytics
from lobster.latency import ConstantLatency, JitteredLatency
from lobster.order import Side
from lobster.sim import Simulation

FAST, SLOW = 1, 2
MM = dict(half_spread=0.4, qty=10, inv_skew=0.0, inventory_cap=10_000)


def _front_of_queue(sim: Simulation) -> int | None:
    """Which maker, if either, is first in line at the best bid."""
    for level in sim.book.iter_levels(Side.BUY):
        for o in level.orders:
            if o.agent_id in (FAST, SLOW):
                return o.agent_id
        break  # best level only — queue position is a per-level fact
    return None


def run(fast_latency: float, slow_latency: float, steps: int, seed: int):
    """One race. Returns everything the page draws, as plain Python types."""
    sim = Simulation(
        agents=[
            MarketMakerAgent(agent_id=FAST,
                             latency=ConstantLatency(fast_latency), **MM),
            MarketMakerAgent(agent_id=SLOW,
                             latency=ConstantLatency(slow_latency), **MM),
            NoiseAgent(agent_id=3, intensity=0.6, market_order_rate=0.4,
                       qty=6, latency=JitteredLatency(mean=0.3, shape=2.0)),
            NoiseAgent(agent_id=4, intensity=0.5, market_order_rate=0.4,
                       qty=6, latency=JitteredLatency(mean=0.3, shape=2.0)),
        ],
        seed=seed,
    )

    front = {FAST: 0, SLOW: 0}
    mids: list[float] = []
    spreads: list[float] = []
    for k in range(steps):
        m = sim.step(ts=float(k))
        leader = _front_of_queue(sim)
        if leader is not None:
            front[leader] += 1
        if m.mid is not None:
            mids.append(round(m.mid, 4))
            spreads.append(round(m.spread or 0.0, 4))

    an = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    fills = {FAST: 0, SLOW: 0}
    for t in sim.tape:
        for aid in (t.buyer_id, t.seller_id):
            if aid in fills:
                fills[aid] += t.qty

    total_front = front[FAST] + front[SLOW]
    book = sim.book

    def ladder(side, n=8):
        out = []
        for i, level in enumerate(book.iter_levels(side)):
            if i >= n:
                break
            out.append((round(level.price, 2),
                        sum(o.qty for o in level.orders)))
        return out

    return {
        "front_fast": front[FAST],
        "front_slow": front[SLOW],
        "front_share_fast": (front[FAST] / total_front) if total_front else 0.0,
        "fills_fast": fills[FAST],
        "fills_slow": fills[SLOW],
        "markout_fast": an.markout(agent_id=FAST, horizon=20),
        "markout_slow": an.markout(agent_id=SLOW, horizon=20),
        "n_trades": len(sim.tape),
        "mids": mids,
        "spreads": spreads,
        "bids": ladder(Side.BUY),
        "asks": ladder(Side.SELL),
    }
