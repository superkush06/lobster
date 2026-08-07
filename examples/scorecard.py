"""Grade the simulator against four textbook microstructure facts.

The bundled demo mix is run twice, once with the momentum agent and once
without, and each run is scored on the diagnostics in `lobster.stylized`.
The point is not to pass: two of the four fail, and the second column
explains why by removing the agent responsible.

The second half of the output is the spread block: Roll's implied spread
recomputed from trade prices alone, next to the quoted spread the book
actually showed. Every spread and variance-ratio figure quoted in
`docs/theory.md` is printed there.

    python examples/scorecard.py                  # 100k ticks, ~10 s
    python examples/scorecard.py --steps 20000    # rougher, ~2 s
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

from lobster import Simulation
from lobster.agents import (
    MarketMakerAgent,
    MomentumAgent,
    NoiseAgent,
    ValueAgent,
)
from lobster.stylized import StylizedFacts, depth_profile, trade_prices

BIN, MAXD = 0.05, 1.5


@dataclass
class Run:
    """One simulation, reduced to the numbers the docs quote."""

    facts: StylizedFacts
    autocov1: float             # gamma_1 of trade-price changes
    quoted_spread: float        # time-averaged, over every tick
    traded_spread: float        # averaged over ticks where a trade printed

    @property
    def roll_spread(self) -> float | None:
        """Roll (1984): s_hat = 2 * sqrt(-gamma_1); None if gamma_1 >= 0."""
        return 2.0 * math.sqrt(-self.autocov1) if self.autocov1 < 0 else None

    @property
    def half_spread(self) -> float:
        return self.quoted_spread / 2.0


def demo_agents(*, momentum: bool) -> list:
    agents = [
        NoiseAgent(agent_id=1, intensity=0.6, spread_offset=0.6, qty=8,
                   market_order_rate=0.25),
        NoiseAgent(agent_id=2, intensity=0.5, spread_offset=0.6, qty=8,
                   market_order_rate=0.25),
    ]
    if momentum:
        agents.append(MomentumAgent(agent_id=3, lookback=20, threshold=0.5,
                                    qty=5, max_position=100))
    agents.append(MarketMakerAgent(agent_id=4, half_spread=0.4, qty=12,
                                   inv_skew=0.02))
    # The latent-liquidity side of the book. Without it nothing here resists a
    # metaorder and cost comes out convex in size; see docs/validation.md 2c.
    agents.append(ValueAgent(agent_id=5, value=100.0))
    return agents


def measure(steps: int, seed: int, *, momentum: bool) -> Run:
    sim = Simulation(agents=demo_agents(momentum=momentum), seed=seed)
    profiles = []
    for k, m in enumerate(sim.run(steps)):
        if k % 10 == 0 and m.mid is not None:
            profiles.append(depth_profile(sim.book, BIN, MAXD))
    mids = [m.mid for m in sim.metrics if m.mid is not None]
    facts = StylizedFacts.measure(sim.tape, mids, profiles, max_lag=128,
                                  depth_bin_width=BIN)

    px = trade_prices(sim.tape)
    dpx = [px[i] - px[i - 1] for i in range(1, len(px))]
    n = len(dpx)
    mu = sum(dpx) / n if n else 0.0
    autocov1 = (sum((dpx[i] - mu) * (dpx[i + 1] - mu) for i in range(n - 1)) / n
                if n > 1 else 0.0)
    quoted = [m.spread for m in sim.metrics if m.spread is not None]
    traded = [m.spread for m in sim.metrics
              if m.spread is not None and m.n_trades > 0]
    return Run(
        facts=facts,
        autocov1=autocov1,
        quoted_spread=sum(quoted) / len(quoted) if quoted else 0.0,
        traded_spread=sum(traded) / len(traded) if traded else 0.0,
    )


def grade(sf: StylizedFacts) -> list[tuple[str, str, str]]:
    """(fact, verdict, evidence). Thresholds are stated, not tuned."""
    rows = []

    ok = -0.5 <= sf.bounce < -0.15
    rows.append((
        "bid-ask bounce",
        "yes" if ok else "no",
        f"rho1 = {sf.bounce:+.3f} against Roll's floor of -0.5",
    ))

    touch_share = sf.depth[0] / max(sf.depth) if sf.depth else 0.0
    ok = touch_share < 0.25 and sf.depth_peak > sf.depth_bin_width
    rows.append((
        "humped depth profile",
        "yes" if ok else "no",
        f"peak {sf.depth_peak:.2f} from the mid; the touch holds "
        f"{touch_share:.1%} of peak size",
    ))

    horizon, gamma = sf.memory_horizon(), sf.flow_memory
    if horizon == 0:
        verdict, why = "no", (
            f"rho1 = {sf.sign_acf[0]:+.3f}, inside the noise band from lag 1"
        )
    else:
        verdict = ("yes" if horizon >= len(sf.sign_acf)
                   and gamma is not None and gamma < 0.8 else "partly")
        why = (f"rho1 = {sf.sign_acf[0]:+.3f}, gone by lag {horizon}"
               + (f", gamma = {gamma:.2f}" if gamma is not None else ""))
    rows.append(("long memory of order flow", verdict,
                 why + " (real flow: gamma ~ 0.5, never gone)"))

    vr = sf.summary()["vr_mid_100"]
    if vr is None:
        verdict, why = "n/a", "not enough data"
    else:
        verdict = ("yes" if 0.8 < vr < 1.25
                   else "partly" if 0.5 < vr < 2.0 else "no")
        why = f"VR(100) = {vr:.2f}; 1.0 is a random walk"
    rows.append(("mid is a martingale", verdict, why))
    return rows


def spread_rows(run: Run) -> list[tuple[str, str]]:
    """The figures docs/theory.md §3 and §4 quote, as (label, value)."""
    sf = run.facts
    roll = run.roll_spread
    rows = [
        ("gamma1, lag-1 autocovariance of trade-price changes",
         f"{run.autocov1:.6f}"),
        ("Roll implied spread, 2*sqrt(-gamma1)",
         f"{roll:.4f}" if roll is not None else "n/a"),
        ("quoted spread, time-averaged over every tick",
         f"{run.quoted_spread:.4f}"),
        ("quoted spread at the ticks where a trade printed",
         f"{run.traded_spread:.4f}"),
        ("mean half-spread", f"{run.half_spread:.4f}"),
    ]
    vr2 = sf._vr(sf.vr_trades, 2)
    if vr2 is not None:
        rows.append((f"VR(2) on trade prices (1 + rho1 = {1 + sf.bounce:.3f})",
                     f"{vr2:.3f}"))
    vr100 = sf._vr(sf.vr_mid, 100)
    if vr100 is not None:
        rows.append(("VR(100) on mid prices", f"{vr100:.3f}"))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=100_000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    runs = {
        "demo mix": measure(args.steps, args.seed, momentum=True),
        "no chaser": measure(args.steps, args.seed, momentum=False),
    }
    print(f"Stylized-facts scorecard: {args.steps:,} ticks, seed {args.seed}")
    for name, run in runs.items():
        print(f"\n{name}  ({run.facts.n_trades:,} trades)")
        for fact, verdict, why in grade(run.facts):
            print(f"  {verdict:>6}  {fact:<26} {why}")

    print("\nSpreads: what Roll's estimator recovers from trade prices alone")
    for name, run in runs.items():
        print(f"\n{name}")
        for label, value in spread_rows(run):
            print(f"  {label:<52} {value:>10}")


if __name__ == "__main__":
    main()
