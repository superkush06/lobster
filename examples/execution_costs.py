"""Where a microstructure model earns its keep: sizing a rebalance.

A portfolio optimiser hands you target weights. A risk model hands you the
covariance those weights were chosen against. Neither of them knows what it
costs to get from where you are to where they say you should be, and the
usual placeholder — a flat number of basis points, linear in size — is wrong
in a specific and expensive way: it has no shape, so it can never tell you
to trade *part* of the way.

This script closes that loop without importing anything outside `lobster`.

1. Work parent orders of increasing size through a simulated book on a fixed
   schedule, and measure implementation shortfall against the arrival mid.
2. Express size as participation — the parent divided by the volume that
   printed while it was working — and fit `cost = k * pi**delta` to it.
3. Take an inlined three-asset mean-variance problem (alphas, covariance, a
   current position), solve it with no cost term, then re-solve it along the
   rebalance direction paying the fitted cost.

The optimiser wants to move the whole way. Once you charge it what the book
charges, it wants to move part of the way, and the fraction it settles on is
a number that only a model of the book can produce.

    python examples/execution_costs.py
    python examples/execution_costs.py --trials 48   # tighter cost fit

The portfolio maths here is three assets and a closed-form solve — it is a
stand-in for the real thing, not a replacement for it. The cost number is
what this package contributes.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from lobster import Side, Simulation
from lobster.agents import ValueAgent
from lobster.execution import execute_metaorder, fit_power_law

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from scorecard import demo_agents  # noqa: E402

# ---- the inlined "upstream" inputs ----------------------------------------
# What portfolio construction and risk would have handed over: annualised
# expected excess returns, a covariance matrix, and today's book.

ASSETS = ("ALPHA-1", "ALPHA-2", "ALPHA-3")
MU = (0.045, 0.060, 0.085)
COV = (
    (0.0225, 0.0120, 0.0105),
    (0.0120, 0.0324, 0.0180),
    (0.0105, 0.0180, 0.0576),
)
CURRENT = (0.55, 0.30, 0.15)
RISK_AVERSION = 8.0

# A small fund in three thinly traded names — the regime where execution
# cost is not a rounding error. Shares, not dollars, because the book is.
NAV = 10_000_000.0
PRICE = 100.0
DAILY_SHARES = (25_000.0, 12_000.0, 9_000.0)

# The calibration schedule: a parent worked in equal child orders every
# other tick, over a fixed 320-tick horizon, so that the *rate* of trading
# is what varies with parent size and not the duration.
HORIZON, EVERY = 320, 2
SLICES = (1, 2, 3, 4, 6, 8)


# ---- linear algebra, three assets wide ------------------------------------

def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting. Three assets; no numpy."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-15:
            raise ValueError("singular covariance matrix")
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def utility(w: list[float]) -> float:
    """mu'w - (lambda/2) w'Sigma w, the objective before costs."""
    var = sum(w[i] * COV[i][j] * w[j] for i in range(3) for j in range(3))
    return sum(MU[i] * w[i] for i in range(3)) - 0.5 * RISK_AVERSION * var


def optimal_weights() -> list[float]:
    """Maximise the objective subject to the weights summing to one.

    w = (1/lambda) S^-1 (mu - gamma 1), with gamma set by the budget
    constraint. Both S^-1 mu and S^-1 1 come out of the same solver.
    """
    cov = [list(r) for r in COV]
    a = solve(cov, list(MU))
    b = solve([list(r) for r in COV], [1.0, 1.0, 1.0])
    gamma = (sum(a) - RISK_AVERSION) / sum(b)
    return [(a[i] - gamma * b[i]) / RISK_AVERSION for i in range(3)]


# ---- step 1: measure what the book charges --------------------------------

def calibrate(trials: int, warmup: int, seed: int) -> tuple[float, float,
                                                            float, float]:
    """Fit shortfall = k * participation**delta on simulated metaorders.

    Shortfall is measured net of the arrival half-spread, so the fit
    describes the part of the cost that scales with size rather than the
    fixed toll every crossing order pays. Returns (k, delta) plus the
    lowest and highest participation the fit actually covers — quoting a
    cost outside that range is extrapolation and the caller should know it.
    """
    print("  parent orders worked over "
          f"{HORIZON} ticks, one child every {EVERY}")
    print(f"  {'parent':>10}{'participation':>16}{'shortfall':>12}"
          f"{'net of spread':>15}")
    xs, ys = [], []
    for slice_qty in SLICES:
        total = slice_qty * (HORIZON // EVERY)
        shortfalls, parts, halves = [], [], []
        for t in range(trials):
            agents = demo_agents(momentum=False)
            sim = Simulation(agents=agents, seed=seed + t)
            # Net out the efficient price's own drift, or a fundamental that
            # wandered while the parent worked gets billed as impact.
            va = next((a for a in agents if isinstance(a, ValueAgent)), None)
            for _ in sim.run(warmup):
                pass
            if sim.book.spread is None:
                continue
            halves.append(sim.book.spread / 2.0)
            before = sum(x.qty for x in sim.tape)
            mo = execute_metaorder(sim, Side.BUY, total, slice_qty=slice_qty,
                                   every=EVERY, agent_id=99,
                                   start_ts=float(warmup),
                                   reference=(None if va is None
                                              else lambda va=va: va.value))
            printed = sum(x.qty for x in sim.tape) - before
            if mo.shortfall is None or printed <= 0:
                continue
            shortfalls.append(mo.shortfall)
            parts.append(total / printed)
        if not shortfalls:
            continue
        gross = sum(shortfalls) / len(shortfalls)
        net = gross - sum(halves) / len(halves)
        pi = sum(parts) / len(parts)
        xs.append(pi)
        ys.append(net)
        print(f"  {total:>10,}{pi:>16.1%}{gross:>12.4f}{net:>15.4f}")
    fit = fit_power_law(xs, ys)
    if fit is None:
        raise SystemExit("cost calibration failed — no usable points")
    return fit[0], fit[1], min(xs), max(xs)


# ---- step 2: charge the portfolio for it ----------------------------------

def participations(w_from: list[float], w_to: list[float]) -> list[float]:
    return [abs(w_to[i] - w_from[i]) * NAV / PRICE / DAILY_SHARES[i]
            for i in range(3)]


def trade_cost(w_from: list[float], w_to: list[float],
               k: float, delta: float) -> float:
    """Cost of the rebalance as a fraction of NAV.

    Per asset: participation is the shares traded over the name's daily
    volume, the fitted law prices a share at that participation, and the
    dollars are divided back out by NAV so the number can be subtracted
    from the mean-variance objective directly.
    """
    total = 0.0
    for i, pi in enumerate(participations(w_from, w_to)):
        if pi <= 0.0:
            continue
        shares = abs(w_to[i] - w_from[i]) * NAV / PRICE
        total += k * pi ** delta * shares
    return total / NAV


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=24)
    ap.add_argument("--warmup", type=int, default=400)
    ap.add_argument("--seed", type=int, default=1000)
    args = ap.parse_args()

    print("Step 1 — what does the book charge?")
    k, delta, pi_lo, pi_hi = calibrate(args.trials, args.warmup, args.seed)
    print(f"\n  cost per share = {k:.3f} * participation^{delta:.2f}, "
          f"fitted over {pi_lo:.0%}-{pi_hi:.0%} participation")
    print(f"  the exponent is {'above' if delta > 1 else 'below'} 1, so cost "
          "is convex in the rate you trade at.")
    print("  Note this is the participation curve, not the size curve: the "
          "horizon is fixed, so a")
    print("  bigger parent here means trading faster rather than trading for "
          "longer. The size law")
    print("  is the one published studies put near 0.5, and docs/validation.md "
          "2c measures it")
    print("  separately. Participation this high (a fifth to two thirds of "
          "printed volume) is far")
    print("  outside the few-percent range those studies cover, and cost is "
          "expected to bend up.")

    print("\nStep 2 — the portfolio problem, costs ignored")
    target = optimal_weights()
    current = list(CURRENT)
    print(f"  {'asset':<10}{'current':>10}{'target':>10}{'move':>10}"
          f"{'participation':>16}")
    pis = participations(current, target)
    for i, name in enumerate(ASSETS):
        print(f"  {name:<10}{current[i]:>10.1%}{target[i]:>10.1%}"
              f"{target[i] - current[i]:>+10.1%}{pis[i]:>16.1%}")
    gain = utility(target) - utility(current)
    print(f"  utility gain from the full rebalance: {gain:>+.4%} of NAV")

    print("\nStep 3 — the same problem, paying what the book charges")
    print(f"  {'fraction moved':>16}{'utility gain':>15}{'cost':>10}{'net':>11}")
    best_f, best_net = 0.0, 0.0
    for step in range(21):
        f = step / 20.0
        w = [current[i] + f * (target[i] - current[i]) for i in range(3)]
        g = utility(w) - utility(current)
        c = trade_cost(current, w, k, delta)
        if g - c > best_net:
            best_f, best_net = f, g - c
        if step % 4 == 0 or step == 20:
            print(f"  {f:>16.0%}{g:>15.4%}{c:>10.4%}{g - c:>11.4%}")

    w = [current[i] + best_f * (target[i] - current[i]) for i in range(3)]
    print(f"\n  best move: {best_f:.0%} of the way to target, "
          f"net {best_net:+.4%} of NAV against {gain:+.4%} if trading were free")
    print(f"  {'asset':<10}{'current':>10}{'target':>10}{'trade to':>10}"
          f"{'participation':>16}")
    for i, pi in enumerate(participations(current, w)):
        print(f"  {ASSETS[i]:<10}{current[i]:>10.1%}{target[i]:>10.1%}"
              f"{w[i]:>10.1%}{pi:>16.1%}")
    print("\n  Read the last column against the calibration range above: where")
    print("  it falls below it the cost curve is being extrapolated, which is")
    print("  the honest limit of a venue this small. The shape of the answer —")
    print("  a partial rebalance and a no-trade band — is what a flat")
    print("  basis-point assumption can never give you.")


if __name__ == "__main__":
    main()
