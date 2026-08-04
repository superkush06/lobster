"""Check the library against things that are true outside the library.

Two kinds of check, kept apart on purpose.

**Part 1 — estimators against ground truth.** Feed a process whose answer is
known in closed form to the estimator and see whether it comes back. Roll's
implied spread against a synthetic Roll process with a spread we chose; the
variance-ratio sampling distribution against Lo and MacKinlay's asymptotic
formula; the book-walk cost against depth profiles whose impact exponent can
be done on paper. If these fail, nothing downstream means anything.

**Part 2 — the simulator against published stylized facts.** Fat tails,
volatility clustering, uncorrelated returns, long-memory order flow, the
humped book and the square-root impact law. Some of these the simulator
reproduces and some it does not; the output says which, and `docs/validation.md`
records the numbers with the reasons.

    python examples/validate.py            # ~20 s
    python examples/validate.py --quick    # ~4 s, coarser Monte Carlo

Nothing here is tuned to agree. Where the answer is embarrassing it is
printed anyway.
"""

from __future__ import annotations

import argparse
import math
import pathlib
import random
import sys

from lobster import Analytics, Order, OrderBook, Side, Simulation, SquareRootImpact
from lobster.execution import cost_to_trade, execute_metaorder, fit_power_law
from lobster.stylized import (
    ReturnFacts,
    StylizedFacts,
    autocorrelation,
    depth_profile,
    log_returns,
    variance_ratio,
)

# The bundled demo mix, imported rather than re-typed so the scorecard and
# this script can never drift apart.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scorecard import demo_agents  # noqa: E402

BIN, MAXD = 0.05, 1.5
_DEMO_CACHE: dict[tuple[int, int, bool], tuple] = {}


def rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def row(label: str, ours: str, reference: str, verdict: str) -> None:
    print(f"  {label:<44}{ours:>20}   vs {reference:<25} {verdict}")


# ===========================================================================
# Part 1 — estimators against closed-form / brute-force ground truth
# ===========================================================================

def roll_process(n: int, spread: float, sigma: float,
                 rng: random.Random) -> list[float]:
    """p_t = m_t + (s/2) q_t with m a random walk and q iid +-1 (Roll 1984)."""
    c, m = spread / 2.0, 100.0
    out = []
    for _ in range(n):
        m += rng.gauss(0.0, sigma)
        out.append(m + c * (1 if rng.random() < 0.5 else -1))
    return out


def check_roll(reps: int, n: int) -> None:
    rule("1a. Roll's implied spread against a process with a known spread")
    print("     rho1 = -c^2 / (sigma^2 + 2c^2),  s_hat = 2*sqrt(-gamma1)")
    rng = random.Random(12345)
    for spread, sigma in ((0.10, 0.01), (0.05, 0.02), (0.20, 0.05)):
        ests, rhos = [], []
        for _ in range(reps):
            p = roll_process(n, spread, sigma, rng)
            d = [p[i] - p[i - 1] for i in range(1, len(p))]
            k = len(d)
            mu = sum(d) / k
            g1 = sum((d[i] - mu) * (d[i + 1] - mu) for i in range(k - 1)) / k
            if g1 < 0:
                ests.append(2.0 * math.sqrt(-g1))
            rhos.append(autocorrelation(d, 1)[0])
        c = spread / 2.0
        rho_theory = -c * c / (sigma * sigma + 2 * c * c)
        s_hat = sum(ests) / len(ests)
        rho_hat = sum(rhos) / len(rhos)
        err = 100.0 * (s_hat - spread) / spread
        row(f"s={spread:.2f} sigma={sigma:.2f}: implied spread",
            f"{s_hat:.5f}", f"{spread:.5f}", f"{err:+.2f}%")
        row(f"s={spread:.2f} sigma={sigma:.2f}: rho1",
            f"{rho_hat:.5f}", f"{rho_theory:.5f}",
            f"{100 * (rho_hat - rho_theory) / abs(rho_theory):+.2f}%")


def check_variance_ratio(reps: int, n: int) -> None:
    rule("1b. Variance-ratio null against Lo and MacKinlay's asymptotics")
    print("     under a random walk VR(q) -> 1 with sd sqrt(2(2q-1)(q-1)/(3qT))")
    rng = random.Random(99)
    qs = (2, 5, 10, 50)
    vals: dict[int, list[float]] = {q: [] for q in qs}
    for _ in range(reps):
        p = [100.0]
        for _ in range(n):
            p.append(p[-1] + rng.gauss(0.0, 1.0))
        for q in qs:
            vals[q].append(variance_ratio(p, q))
    for q in qs:
        v = vals[q]
        m = sum(v) / len(v)
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / len(v))
        theory = math.sqrt(2 * (2 * q - 1) * (q - 1) / (3 * q * n))
        row(f"q={q}: mean VR over {reps} paths", f"{m:.4f}", "1.0000",
            f"{100 * (m - 1):+.2f}%")
        row(f"q={q}: sd of VR", f"{sd:.4f}", f"{theory:.4f}",
            f"{100 * (sd - theory) / theory:+.2f}%")


def analytic_book(density, nlevels: int, tick: float = 0.01,
                  mid: float = 100.0) -> OrderBook:
    """A symmetric book whose level `i` holds `density(i)` shares."""
    book = OrderBook()
    for i in range(1, nlevels + 1):
        qty = max(1, int(density(i)))
        book.add(Order(Side.SELL, qty=qty, price=round(mid + i * tick, 4)),
                 allow_crossed=True)
        book.add(Order(Side.BUY, qty=qty, price=round(mid - i * tick, 4)),
                 allow_crossed=True)
    return book


def check_book_walk(nlevels: int) -> None:
    rule("1c. Book-walk impact exponent against depth profiles solvable on paper")
    print("     cumulative depth ~ d^(1+a) implies price impact ~ Q^(1/(1+a))")
    sizes = [1000 * 2 ** k for k in range(9)]
    cases = (
        ("flat depth, q(i) = 100", lambda i: 100, 1.0),
        ("depth linear in distance, q(i) = 2i", lambda i: 2 * i, 0.5),
        ("depth quadratic, q(i) = 3i^2", lambda i: 3 * i * i, 1.0 / 3.0),
    )
    for label, density, expected in cases:
        book = analytic_book(density, nlevels)
        xs, ys = [], []
        for q in sizes:
            s = cost_to_trade(book, Side.BUY, q)
            if s is not None and s.complete:
                xs.append(float(q))
                ys.append(s.impact)
        fit = fit_power_law(xs, ys)
        delta = fit[1] if fit else float("nan")
        row(label, f"{delta:.4f}", f"{expected:.4f}",
            f"{100 * (delta - expected) / expected:+.2f}%")


def check_sqrt_impact() -> None:
    rule("1d. SquareRootImpact is exactly a half-power law")
    model = SquareRootImpact(eta=0.1, daily_volume=1e6)
    base = model.impact(1, 1000)
    for mult in (4, 9, 16):
        ratio = model.impact(1, 1000 * mult) / base
        row(f"impact({mult}Q) / impact(Q)", f"{ratio:.12f}",
            f"{math.sqrt(mult):.12f}",
            "exact" if abs(ratio - math.sqrt(mult)) < 1e-12 else "MISMATCH")


# ===========================================================================
# Part 2 — the simulator against published stylized facts
# ===========================================================================

def run_demo(steps: int, seed: int, *, momentum: bool):
    """Run the demo mix once and memoise it — two sections read the same run."""
    key = (steps, seed, momentum)
    if key in _DEMO_CACHE:
        return _DEMO_CACHE[key]
    sim = Simulation(agents=demo_agents(momentum=momentum), seed=seed)
    profiles = []
    for k, m in enumerate(sim.run(steps)):
        if k % 10 == 0 and m.mid is not None:
            profiles.append(depth_profile(sim.book, BIN, MAXD))
    mids = [m.mid for m in sim.metrics if m.mid is not None]
    facts = StylizedFacts.measure(sim.tape, mids, profiles, max_lag=128,
                                  depth_bin_width=BIN)
    returns = ReturnFacts.measure(log_returns(mids), max_lag=100)
    _DEMO_CACHE[key] = (sim, facts, returns, mids)
    return _DEMO_CACHE[key]


def check_returns(steps: int, seed: int) -> None:
    rule("2a. Return distribution and volatility clustering (Cont 2001)")
    for momentum in (True, False):
        name = "demo mix" if momentum else "no chaser"
        sim, facts, rf, mids = run_demo(steps, seed, momentum=momentum)
        zeros = sum(1 for r in log_returns(mids) if r == 0.0) / max(rf.n, 1)
        print(f"\n  [{name}]  {rf.n:,} tick returns, {zeros:.1%} of them exactly zero")
        row("excess kurtosis of tick returns",
            f"{rf.excess_kurtosis:.2f}", "> 0 (heavy tailed)",
            "yes" if rf.excess_kurtosis > 0 else "no")
        row("Hill tail index of |r|, top 5%",
            f"{rf.tail_index:.2f}", "2 to 5", "yes"
            if 2.0 <= rf.tail_index <= 5.0 else "outside the band")
        agg = rf.aggregated_kurtosis
        row("excess kurtosis, 100-tick aggregation",
            f"{agg[100]:.2f}", f"< {agg[1]:.2f} (toward 0)",
            "yes" if agg[100] < agg[1] else "no")
        row("lag-1 autocorrelation of tick returns",
            f"{rf.ret_acf[0]:+.4f}", "~0 (Cont 2001)", "yes"
            if abs(rf.ret_acf[0]) < 0.05 else "no")
        row("rho(|r|) at lag 1", f"{rf.abs_ret_acf[0]:+.4f}", "> 0", "yes"
            if rf.abs_ret_acf[0] > 0 else "no")
        row("rho(|r|) at lag 100", f"{rf.abs_ret_acf[99]:+.4f}",
            "> 0, slow decay", "yes" if rf.abs_ret_acf[99] > 0 else "no")
        row("decay exponent of rho(|r|)",
            f"{rf.clustering_decay:.2f}" if rf.clustering_decay else "n/a",
            "< 1 (long memory)",
            "yes" if rf.clustering_decay and rf.clustering_decay < 1 else "no")


def check_microstructure(steps: int, seed: int) -> None:
    rule("2b. Microstructure facts (Roll 1984; Bouchaud et al. 2002, 2004)")
    for momentum in (True, False):
        name = "demo mix" if momentum else "no chaser"
        sim, facts, rf, mids = run_demo(steps, seed, momentum=momentum)
        print(f"\n  [{name}]  {facts.n_trades:,} trades")
        row("lag-1 autocorrelation of trade-price changes",
            f"{facts.bounce:+.3f}", "in [-0.5, 0)",
            "yes" if -0.5 <= facts.bounce < 0 else "no")
        gamma, horizon = facts.flow_memory, facts.memory_horizon()
        if horizon == 0:
            row("order-flow sign memory: decay exponent gamma",
                "no memory to fit", "~0.5", "no")
        else:
            row("order-flow sign memory: decay exponent gamma",
                f"{gamma:.2f}" if gamma else "n/a", "~0.5",
                "yes" if gamma is not None and gamma < 0.8 else "no")
        row("order-flow memory horizon, in trades",
            f"{horizon}", "thousands of trades", "no")
        peak, touch = facts.depth_peak, facts.depth[0] / max(facts.depth)
        row("depth peaks away from the touch",
            f"{peak:.2f} ({touch:.1%} at touch)", "> 0 (humped)",
            "yes" if peak > BIN and touch < 0.25 else "no")
        an = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
        mk = an.markout(4, horizon=10)
        row("market maker's passive markout, h=10",
            f"{mk:+.5f}", "< 0 (adversely selected)",
            "yes" if mk < 0 else "no")


def check_impact_law(trials: int, warmup: int, seed: int) -> None:
    rule("2c. The impact of a metaorder (Almgren et al. 2005; Gatheral 2010)")
    print("     a parent order worked in 8-lot children every other tick")
    sizes = [20, 40, 80, 160, 320, 640, 1280]
    for momentum in (True, False):
        name = "demo mix" if momentum else "no chaser"
        print(f"\n  [{name}]")
        xs, gross, net, peak = [], [], [], []
        for total in sizes:
            sh, pk, half = [], [], []
            for t in range(trials):
                sim = Simulation(agents=demo_agents(momentum=momentum),
                                 seed=seed + t)
                for _ in sim.run(warmup):
                    pass
                if sim.book.spread is None:
                    continue
                half.append(sim.book.spread / 2.0)
                mo = execute_metaorder(sim, Side.BUY, total, slice_qty=8,
                                       every=2, agent_id=99,
                                       start_ts=float(warmup), decay_steps=200)
                if mo.shortfall is not None:
                    sh.append(mo.shortfall)
                if mo.peak_impact is not None:
                    pk.append(mo.peak_impact)
            if not sh:
                continue
            xs.append(float(total))
            gross.append(sum(sh) / len(sh))
            net.append(sum(sh) / len(sh) - sum(half) / len(half))
            peak.append(sum(pk) / len(pk))
            print(f"    Q={total:5d}  shortfall={gross[-1]:+.4f}  "
                  f"net of half-spread={net[-1]:+.4f}  peak impact={peak[-1]:+.4f}")
        for label, ys in (("shortfall incl. half-spread", gross),
                          ("shortfall net of half-spread", net),
                          ("peak mid impact", peak)):
            fit = fit_power_law(xs, ys)
            if fit is None:
                continue
            delta = fit[1]
            row(f"exponent of {label}", f"{delta:.2f}", "0.5 to 0.6",
                "yes" if 0.4 <= delta <= 0.7 else "no")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="fewer Monte Carlo paths and shorter simulations")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    q = args.quick

    print("lobster — validation against external ground truth")
    print("=" * 66)
    print("Part 1: estimators against closed-form answers")
    check_roll(reps=8 if q else 40, n=5_000 if q else 20_000)
    check_variance_ratio(reps=300 if q else 1500, n=2_000)
    check_book_walk(nlevels=4_000 if q else 20_000)
    check_sqrt_impact()

    print("\n" + "=" * 66)
    print("Part 2: the simulator against published stylized facts")
    steps = 20_000 if q else 100_000
    check_returns(steps, args.seed)
    check_microstructure(steps, args.seed)
    check_impact_law(trials=8 if q else 24, warmup=400, seed=1000)


if __name__ == "__main__":
    main()
