"""Latency race: two identical market makers, one faster than the other.

Both makers quote the same prices off the same mid (inv_skew=0), so the only
difference is the wire: the fast maker's quotes arrive 3x sooner. Price-time
priority then puts the fast maker at the front of the queue at every shared
level, which shows up as (a) front-of-queue share, (b) passive fill volume,
and (c) markout, the canonical result that latency buys queue position.

Run:  python examples/latency_race.py --steps 4000 --seed 11
"""

from __future__ import annotations

import argparse

from lobster.agents import MarketMakerAgent, NoiseAgent
from lobster.analytics import Analytics
from lobster.latency import ConstantLatency, JitteredLatency
from lobster.order import Side
from lobster.sim import Simulation

FAST, SLOW = 1, 2


def front_of_queue(sim: Simulation) -> int | None:
    """Which maker (if any) is first among makers at the best bid level."""
    for level in sim.book.iter_levels(Side.BUY):
        for o in level.orders:
            if o.agent_id in (FAST, SLOW):
                return o.agent_id
        break  # best level only
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    mm_kwargs = dict(half_spread=0.4, qty=10, inv_skew=0.0,
                     inventory_cap=10_000)
    sim = Simulation(
        agents=[
            MarketMakerAgent(agent_id=FAST, latency=ConstantLatency(0.05),
                             **mm_kwargs),
            MarketMakerAgent(agent_id=SLOW, latency=ConstantLatency(0.15),
                             **mm_kwargs),
            NoiseAgent(agent_id=3, intensity=0.6, market_order_rate=0.4,
                       qty=6, latency=JitteredLatency(mean=0.3, shape=2.0)),
            NoiseAgent(agent_id=4, intensity=0.5, market_order_rate=0.4,
                       qty=6, latency=JitteredLatency(mean=0.3, shape=2.0)),
        ],
        seed=args.seed,
    )

    front = {FAST: 0, SLOW: 0}
    for k in range(args.steps):
        sim.step(ts=float(k))
        leader = front_of_queue(sim)
        if leader is not None:
            front[leader] += 1

    an = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    vol = {FAST: 0, SLOW: 0}
    for t in sim.tape:
        for mid_ in (FAST, SLOW):
            if mid_ in (t.buyer_id, t.seller_id):
                vol[mid_] += t.qty

    denom = front[FAST] + front[SLOW]
    print("Latency race: identical makers, fast delay=0.05 vs slow delay=0.15")
    print(f"steps={args.steps}  seed={args.seed}  trades={len(sim.tape)}")
    for mid_, label in ((FAST, "fast"), (SLOW, "slow")):
        share = front[mid_] / denom if denom else 0.0
        print(f"  {label} maker: front-of-queue share={share:5.1%}  "
              f"passive fill volume={vol[mid_]:6d}  "
              f"markout(h=10)={an.markout(mid_, horizon=10):+.5f}")


if __name__ == "__main__":
    main()
