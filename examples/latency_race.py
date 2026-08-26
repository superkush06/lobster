"""Latency race: two identical market makers, one faster than the other.

Both makers quote the same prices off the same mid (inv_skew=0), so the only
difference is the wire: the fast maker's quotes arrive 3x sooner. Price-time
priority then puts the fast maker at the front of the queue at every shared
level, which shows up as (a) front-of-queue share, (b) passive fill volume,
and (c) markout, the canonical result that latency buys queue position.

Run:  python examples/latency_race.py --steps 4000 --seed 11
      python examples/latency_race.py --steps 4000 --seeds 1-12
"""

from __future__ import annotations

import argparse
import statistics

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


def run_race(steps: int, seed: int) -> dict:
    """One race at one seed: front counts, fill volumes, markouts, trades."""
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
        seed=seed,
    )

    front = {FAST: 0, SLOW: 0}
    for k in range(steps):
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
    return {
        "front": front,
        "vol": vol,
        "markout": {m: an.markout(m, horizon=10) for m in (FAST, SLOW)},
        "trades": len(sim.tape),
    }


def sweep(steps: int, first: int, last: int) -> None:
    """The same race at every seed in [first, last], then the summary.

    The per-seed quantity that decides anything is the markout gap
    (fast minus slow); its t statistic is the paired mean over the sample
    standard deviation of the gaps, times sqrt(n).
    """
    shares, gaps = [], []
    vols = {FAST: 0, SLOW: 0}
    marks: dict[int, list[float]] = {FAST: [], SLOW: []}
    n = last - first + 1
    for seed in range(first, last + 1):
        r = run_race(steps, seed)
        denom = r["front"][FAST] + r["front"][SLOW]
        shares.append(r["front"][FAST] / denom if denom else 0.0)
        for m in (FAST, SLOW):
            vols[m] += r["vol"][m]
            marks[m].append(r["markout"][m])
        gaps.append(r["markout"][FAST] - r["markout"][SLOW])

    gap_mean = statistics.mean(gaps)
    gap_sd = statistics.stdev(gaps)
    t = gap_mean / (gap_sd / n ** 0.5) if gap_sd else float("inf")
    print(f"Latency sweep: seeds {first} to {last}, steps={steps}")
    print(f"  front-of-queue share (fast):  {min(shares):.1%} to {max(shares):.1%}")
    print(f"  mean passive fill volume:     fast {vols[FAST] / n:,.0f}, "
          f"slow {vols[SLOW] / n:,.0f}")
    print(f"  markout(h=10) mean:           fast {statistics.mean(marks[FAST]):+.4f}, "
          f"slow {statistics.mean(marks[SLOW]):+.4f}")
    print(f"  fast ahead on markout:        {sum(g > 0 for g in gaps)} of {n} seeds")
    print(f"  gap (fast minus slow):        mean {gap_mean:+.4f}, "
          f"sd {gap_sd:.4f}, t = {t:+.2f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--seeds", default=None, metavar="A-B",
                    help="run every seed in the range and print the summary "
                         "instead of one race")
    args = ap.parse_args()

    if args.seeds:
        first, last = (int(x) for x in args.seeds.split("-"))
        sweep(args.steps, first, last)
        return

    r = run_race(args.steps, args.seed)
    denom = r["front"][FAST] + r["front"][SLOW]
    print("Latency race: identical makers, fast delay=0.05 vs slow delay=0.15")
    print(f"steps={args.steps}  seed={args.seed}  trades={r['trades']}")
    for mid_, label in ((FAST, "fast"), (SLOW, "slow")):
        share = r["front"][mid_] / denom if denom else 0.0
        print(f"  {label} maker: front-of-queue share={share:5.1%}  "
              f"passive fill volume={r['vol'][mid_]:6d}  "
              f"markout(h=10)={r['markout'][mid_]:+.5f}")


if __name__ == "__main__":
    main()
