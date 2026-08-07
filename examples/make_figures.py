"""Render every figure in the README from a live simulation.

    python examples/make_figures.py            # all four
    python examples/make_figures.py depth      # docs/book_depth.png
    python examples/make_figures.py stylized   # docs/stylized_facts.png
    python examples/make_figures.py race       # docs/latency_race.png
    python examples/make_figures.py impact     # docs/impact_law.png

Nothing here is hand-drawn or cached: every panel is measured from a run of
the simulator with a fixed seed, so the numbers quoted in the README and the
pixels in the images always agree.
"""

from __future__ import annotations

import math
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")  # headless render
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LogNorm  # noqa: E402
from matplotlib.ticker import NullFormatter  # noqa: E402

from lobster import Order, OrderBook, Side, Simulation  # noqa: E402
from lobster.agents import (  # noqa: E402
    MarketMakerAgent,
    MomentumAgent,
    NoiseAgent,
)
from lobster.analytics import Analytics  # noqa: E402
from lobster.execution import (  # noqa: E402
    cost_to_trade,
    execute_metaorder,
    fit_power_law,
)
from lobster.latency import ConstantLatency, JitteredLatency  # noqa: E402
from lobster.stylized import (  # noqa: E402
    StylizedFacts,
    bin_centers,
    depth_profile,
)

DOCS = pathlib.Path(__file__).resolve().parents[1] / "docs"
INK = "#1b2430"
BID = "#2a7f62"
ASK = "#b5443a"
ACCENT = "#3d6fb4"

BIN = 0.05
MAXD = 1.5


def style() -> None:
    plt.rcParams.update({
        "figure.dpi": 140,
        "savefig.dpi": 140,
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "axes.edgecolor": "#c9ced6",
        "axes.labelcolor": INK,
        "axes.titlecolor": INK,
        "text.color": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "grid.color": "#e4e8ee",
        "legend.frameon": False,
    })


def demo_agents(momentum: bool = True, lookback: int = 20) -> list:
    """The bundled demo config: two noise traders, a chaser, one maker."""
    agents = [
        NoiseAgent(agent_id=1, intensity=0.6, spread_offset=0.6, qty=8,
                   market_order_rate=0.25),
        NoiseAgent(agent_id=2, intensity=0.5, spread_offset=0.6, qty=8,
                   market_order_rate=0.25),
    ]
    if momentum:
        agents.append(MomentumAgent(agent_id=3, lookback=lookback,
                                    threshold=0.5, qty=5, max_position=100))
    agents.append(MarketMakerAgent(agent_id=4, half_spread=0.4, qty=12,
                                   inv_skew=0.02))
    return agents


# ---- figure 1: the book through time --------------------------------------

def fig_depth(steps: int = 1400, seed: int = 7) -> None:
    """Every resting order, every level, every tick."""
    sim = Simulation(agents=demo_agents(), seed=seed)
    grid: list[dict[int, int]] = []   # per step: price-bin -> resting qty
    touch: list[tuple[float | None, float | None]] = []
    prints: list[tuple[int, float, Side]] = []
    seen = 0
    for k, m in enumerate(sim.run(steps)):
        col: dict[int, int] = {}
        for side in (Side.BUY, Side.SELL):
            for lv in sim.book.iter_levels(side):
                b = round(lv.price / BIN)
                col[b] = col.get(b, 0) + lv.total_qty
        grid.append(col)
        touch.append((m.best_bid, m.best_ask))
        for t in list(sim.tape)[seen:]:
            prints.append((k, t.price, t.aggressor))
        seen = len(sim.tape)

    bins = sorted({b for col in grid for b in col})
    lo, hi = bins[0], bins[-1]
    img = [[float("nan")] * len(grid) for _ in range(hi - lo + 1)]
    for x, col in enumerate(grid):
        for b, q in col.items():
            img[b - lo][x] = q

    style()
    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(11.4, 6.4), height_ratios=[3.2, 1], sharex=True,
        gridspec_kw={"hspace": 0.1},
    )
    mesh = ax.imshow(
        img, origin="lower", aspect="auto", cmap="magma_r",
        norm=LogNorm(vmin=1, vmax=max(q for col in grid for q in col.values())),
        extent=(0, len(grid), (lo - 0.5) * BIN, (hi + 0.5) * BIN),
        interpolation="nearest",
    )
    ax.plot([b for b, _ in touch], color=BID, lw=0.9, label="best bid")
    ax.plot([a for _, a in touch], color=ASK, lw=0.9, label="best ask")
    buys = [(x, p) for x, p, s in prints if s is Side.BUY]
    sells = [(x, p) for x, p, s in prints if s is Side.SELL]
    ax.scatter([x for x, _ in buys], [p for _, p in buys], s=16, marker="^",
               facecolor=BID, edgecolor="white", linewidths=0.35,
               label="buyer-initiated print", zorder=4)
    ax.scatter([x for x, _ in sells], [p for _, p in sells], s=16, marker="v",
               facecolor=ASK, edgecolor="white", linewidths=0.35,
               label="seller-initiated print", zorder=4)
    ax.set_ylabel("price")
    ax.set_title("Every resting order, every level, every tick, "
                 "colour is queue depth on a log scale")
    ax.legend(loc="lower left", ncol=2, fontsize=8, handletextpad=0.5,
              columnspacing=1.4, frameon=True, framealpha=0.92,
              edgecolor="#c9ced6")
    cb = fig.colorbar(mesh, ax=ax, pad=0.008, fraction=0.028)
    cb.set_label("resting shares")

    spreads = [(a - b) if (a is not None and b is not None) else None
               for b, a in touch]
    ax2.fill_between(range(len(spreads)), 0, [s or 0 for s in spreads],
                     color=ACCENT, alpha=0.35, linewidth=0)
    ax2.plot(spreads, color=ACCENT, lw=0.6)
    ax2.set_ylabel("spread")
    ax2.set_xlabel("tick")
    ax2.set_ylim(bottom=0)
    ax2.grid(axis="y", lw=0.5)
    ax2.set_xlim(0, len(grid))
    # keep the two panels the same width despite the colorbar on the top one
    box, top = ax2.get_position(), ax.get_position()
    ax2.set_position([top.x0, box.y0, top.width, box.height])

    out = DOCS / "book_depth.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {out}  ({steps} ticks, {len(prints)} prints)")


# ---- figure 2: the stylized-facts scorecard --------------------------------

def _measure(steps: int, seed: int, **kw) -> StylizedFacts:
    sim = Simulation(agents=demo_agents(**kw), seed=seed)
    profiles = []
    for k, m in enumerate(sim.run(steps)):
        if k % 10 == 0 and m.mid is not None:
            profiles.append(depth_profile(sim.book, BIN, MAXD))
    mids = [m.mid for m in sim.metrics if m.mid is not None]
    return StylizedFacts.measure(sim.tape, mids, profiles, max_lag=128,
                                 depth_bin_width=BIN)


def fig_stylized(steps: int = 100_000, seed: int = 7) -> None:
    with_mom = _measure(steps, seed)
    no_mom = _measure(steps, seed, momentum=False)

    style()
    fig, axes = plt.subplots(2, 2, figsize=(11.9, 7.9))
    (a, b), (c, d) = axes
    fig.subplots_adjust(hspace=0.34, wspace=0.24)

    # (a) bid-ask bounce in transaction prices
    lags = range(1, 11)
    a.bar([x - 0.2 for x in lags], with_mom.price_change_acf[:10], width=0.4,
          color=ACCENT, label="demo mix")
    a.bar([x + 0.2 for x in lags], no_mom.price_change_acf[:10], width=0.4,
          color="#9aa7b8", label="noise + maker only")
    a.axhline(-0.5, color=ASK, ls="--", lw=1)
    a.text(6.4, -0.47, "Roll (1984) floor  $-1/2$", color=ASK, fontsize=8)
    a.axhline(0, color="#c9ced6", lw=0.8)
    a.set_title("(a) bid–ask bounce: trade-price changes")
    a.set_xlabel("lag (trades)")
    a.set_ylabel("autocorrelation")
    a.set_xticks(list(lags))
    a.legend(fontsize=8)

    # (b) long memory of order flow
    ref_l = list(range(1, 129))
    band = 2.0 / math.sqrt(with_mom.n_trades)
    b.fill_between(ref_l, -band, band, color="#9aa7b8", alpha=0.22, lw=0,
                   label=r"$\pm 2/\sqrt{N}$")
    b.plot(ref_l, [with_mom.sign_acf[i - 1] for i in ref_l], color=ACCENT,
           lw=1.4, label="demo mix")
    b.plot(ref_l, [no_mom.sign_acf[i - 1] for i in ref_l],
           color="#7d8896", lw=1.0, label="noise + maker only")
    b.plot(ref_l, [0.15 * x ** -0.5 for x in ref_l], color=ASK, ls="--",
           lw=1.2, label="empirical $0.15\\,\\ell^{-1/2}$")
    b.axvline(20, color="#8a94a3", lw=1, ls=":")
    b.text(22, 0.152, "chaser lookback = 20", fontsize=7.5, color="#6b7684")
    b.axhline(0, color="#c9ced6", lw=0.8)
    b.set_xlim(1, 128)
    b.set_ylim(-0.03, 0.175)
    b.set_title("(b) order-flow memory: trade-sign autocorrelation")
    b.set_xlabel("lag $\\ell$ (trades)")
    b.set_ylabel(r"$\rho(\ell)$")
    b.grid(lw=0.5)
    b.legend(fontsize=8, loc="upper right")

    # (c) variance ratios
    qs = with_mom.vr_qs
    c.semilogx(qs, with_mom.vr_mid, "o-", color=ACCENT, ms=3.5,
               label="mid, demo mix")
    c.semilogx(qs, no_mom.vr_mid, "o-", color="#9aa7b8", ms=3.5,
               label="mid, noise + maker only")
    c.semilogx(qs, with_mom.vr_trades, "s--", color=BID, ms=3.5,
               label="trade price, demo mix")
    c.semilogx(qs, no_mom.vr_trades, "s--", color="#b9c1cc", ms=3.5,
               label="trade price, noise + maker only")
    c.axhline(1.0, color=ASK, ls="--", lw=1)
    c.text(1.15, 1.1, "martingale", color=ASK, fontsize=8)
    c.set_yscale("log")
    c.set_title("(c) variance ratio $VR(q)$")
    c.set_xlabel("horizon $q$")
    c.set_ylabel(r"$\mathrm{Var}(\Delta_q p)\,/\,q\,\mathrm{Var}(\Delta_1 p)$")
    c.grid(lw=0.5)
    c.legend(fontsize=8, loc="upper left")

    # (d) depth profile
    ctr = bin_centers(BIN, len(with_mom.depth))
    d.fill_between(ctr, 0, with_mom.depth, color=ACCENT, alpha=0.25, lw=0)
    d.plot(ctr, with_mom.depth, color=ACCENT, lw=1.4, label="demo mix")
    d.plot(ctr, no_mom.depth, color="#9aa7b8", lw=1.2,
           label="noise + maker only")
    d.axvline(with_mom.depth_peak, color=ASK, ls="--", lw=1)
    d.text(with_mom.depth_peak + 0.05, max(with_mom.depth) * 0.55,
           f"peak {with_mom.depth_peak:.2f}\nfrom the mid", color=ASK,
           fontsize=8)
    d.set_title("(d) mean depth vs distance from the mid")
    d.set_xlabel("|price − mid|")
    d.set_ylabel("mean resting shares")
    d.grid(lw=0.5)
    d.legend(fontsize=8)

    fig.suptitle(f"Stylized-facts scorecard: {steps:,} ticks, "
                 f"{with_mom.n_trades:,} trades, seed {seed}",
                 fontsize=11, y=0.975)
    out = DOCS / "stylized_facts.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {out}")
    for label, sf in (("demo mix", with_mom), ("noise+maker", no_mom)):
        print(f"  {label:12s} " + "  ".join(
            f"{k}={v:.4g}" if isinstance(v, float) else f"{k}={v}"
            for k, v in sf.summary().items()))


# ---- figure 3: the latency race -------------------------------------------

FAST, SLOW = 1, 2


def fig_race(steps: int = 4000, seed: int = 11) -> None:
    mm = dict(half_spread=0.4, qty=10, inv_skew=0.0, inventory_cap=10_000)
    sim = Simulation(
        agents=[
            MarketMakerAgent(agent_id=FAST, latency=ConstantLatency(0.05), **mm),
            MarketMakerAgent(agent_id=SLOW, latency=ConstantLatency(0.15), **mm),
            NoiseAgent(agent_id=3, intensity=0.6, market_order_rate=0.4, qty=6,
                       latency=JitteredLatency(mean=0.3, shape=2.0)),
            NoiseAgent(agent_id=4, intensity=0.5, market_order_rate=0.4, qty=6,
                       latency=JitteredLatency(mean=0.3, shape=2.0)),
        ],
        seed=seed,
    )
    front = {FAST: 0, SLOW: 0}
    share, cum = [], {FAST: [], SLOW: []}
    vol = {FAST: 0, SLOW: 0}
    seen = 0
    for _ in range(steps):
        sim.step(ts=float(_))
        leader = None
        for lv in sim.book.iter_levels(Side.BUY):
            for o in lv.orders:
                if o.agent_id in (FAST, SLOW):
                    leader = o.agent_id
                    break
            break
        if leader is not None:
            front[leader] += 1
        denom = front[FAST] + front[SLOW]
        share.append(front[FAST] / denom if denom else 0.5)
        for t in list(sim.tape)[seen:]:
            for who in (FAST, SLOW):
                if who in (t.buyer_id, t.seller_id):
                    vol[who] += t.qty
        seen = len(sim.tape)
        cum[FAST].append(vol[FAST])
        cum[SLOW].append(vol[SLOW])

    an = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    mk = {w: an.markout(w, horizon=10) for w in (FAST, SLOW)}

    style()
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(12.2, 3.5),
                                  gridspec_kw={"width_ratios": [1.2, 1.2, 0.85]})
    fig.subplots_adjust(wspace=0.3)

    a.plot(share, color=ACCENT, lw=1.1)
    a.axhline(0.5, color="#9aa7b8", ls="--", lw=1)
    a.text(steps * 0.03, 0.52, "coin flip", color="#6b7684", fontsize=8)
    a.set_ylim(0.4, 1.0)
    a.set_title("front-of-queue share, fast maker")
    a.set_xlabel("tick")
    a.set_ylabel("running share")
    a.grid(lw=0.5)

    a2 = b
    a2.plot(cum[FAST], color=ACCENT, lw=1.3, label="fast (delay 0.05)")
    a2.plot(cum[SLOW], color="#9aa7b8", lw=1.3, label="slow (delay 0.15)")
    a2.set_title("cumulative passive fill volume")
    a2.set_xlabel("tick")
    a2.set_ylabel("shares")
    a2.grid(lw=0.5)
    a2.legend(fontsize=8, loc="upper left")

    lo = min(mk.values())
    c.bar(["fast", "slow"], [mk[FAST], mk[SLOW]],
          color=[ACCENT, "#9aa7b8"], width=0.5)
    c.axhline(0, color="#8a94a3", lw=0.9)
    for i, w in enumerate((FAST, SLOW)):
        c.text(i, mk[w] + abs(lo) * 0.05, f"{mk[w]:+.4f}", ha="center",
               va="bottom", fontsize=8)
    c.set_ylim(lo * 1.25, abs(lo) * 0.22)
    c.set_title("markout, $h=10$")
    c.set_ylabel("mid drift after a passive fill")
    c.grid(axis="y", lw=0.5)

    fig.suptitle("Identical quotes, different wires: "
                 f"{steps} ticks, seed {seed}, {len(sim.tape)} trades",
                 fontsize=11, y=1.03)
    out = DOCS / "latency_race.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {out}")
    denom = front[FAST] + front[SLOW]
    for who, label in ((FAST, "fast"), (SLOW, "slow")):
        print(f"  {label}: front={front[who] / denom:.3%} "
              f"vol={vol[who]} markout={mk[who]:+.5f}")


# ---- figure 4: does the impact law come out right? ------------------------

ANALYTIC_CASES = (
    ("flat depth", lambda i: 100, 1.0, "#9aa7b8"),
    ("depth ~ distance", lambda i: 2 * i, 0.5, ACCENT),
    ("depth ~ distance$^2$", lambda i: 3 * i * i, 1.0 / 3.0, BID),
)
METAORDER_SLICES = (1, 2, 3, 4, 6, 8)
HORIZON, EVERY = 320, 2


def _analytic_book(density, nlevels: int = 20_000, tick: float = 0.01,
                   mid: float = 100.0) -> OrderBook:
    book = OrderBook()
    for i in range(1, nlevels + 1):
        qty = max(1, int(density(i)))
        book.add(Order(Side.SELL, qty=qty, price=round(mid + i * tick, 4)),
                 allow_crossed=True)
        book.add(Order(Side.BUY, qty=qty, price=round(mid - i * tick, 4)),
                 allow_crossed=True)
    return book


def fig_impact(trials: int = 24, warmup: int = 400, seed: int = 1000) -> None:
    """Left: the estimator on books whose answer is known. Right: the sim."""
    style()
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.4, 4.3))
    fig.subplots_adjust(wspace=0.26)

    sizes = [1000 * 2 ** k for k in range(9)]
    for label, density, expected, colour in ANALYTIC_CASES:
        book = _analytic_book(density)
        xs, ys = [], []
        for q in sizes:
            sweep = cost_to_trade(book, Side.BUY, q)
            if sweep is not None and sweep.complete:
                xs.append(float(q))
                ys.append(sweep.impact)
        fit = fit_power_law(xs, ys)
        a.loglog(xs, ys, "o-", ms=3.5, lw=1.3, color=colour,
                 label=f"{label}: {fit[1]:.3f} vs {expected:.3f}")
    a.set_title("(a) the estimator, on books solvable on paper")
    a.set_xlabel("market order size $Q$ (shares)")
    a.set_ylabel("mid displacement")
    a.grid(which="both", lw=0.5)
    a.legend(fontsize=8, loc="upper left", title="measured vs analytic slope",
             title_fontsize=8)

    xs, ys = [], []
    for slice_qty in METAORDER_SLICES:
        total = slice_qty * (HORIZON // EVERY)
        shortfalls, parts, halves = [], [], []
        for t in range(trials):
            sim = Simulation(agents=demo_agents(momentum=False), seed=seed + t)
            for _ in sim.run(warmup):
                pass
            if sim.book.spread is None:
                continue
            halves.append(sim.book.spread / 2.0)
            before = sum(x.qty for x in sim.tape)
            mo = execute_metaorder(sim, Side.BUY, total, slice_qty=slice_qty,
                                   every=EVERY, agent_id=99,
                                   start_ts=float(warmup))
            printed = sum(x.qty for x in sim.tape) - before
            if mo.shortfall is None or printed <= 0:
                continue
            shortfalls.append(mo.shortfall)
            parts.append(total / printed)
        if not shortfalls:
            continue
        xs.append(sum(parts) / len(parts))
        ys.append(sum(shortfalls) / len(shortfalls)
                  - sum(halves) / len(halves))
    k, delta = fit_power_law(xs, ys)
    grid = [xs[0] * (xs[-1] / xs[0]) ** (i / 60.0) for i in range(61)]
    b.loglog(xs, ys, "o", ms=5, color=ACCENT, label="simulated metaorders")
    b.loglog(grid, [k * x ** delta for x in grid], "-", lw=1.3, color=ACCENT,
             label=f"fit: $\\pi^{{{delta:.2f}}}$")
    ref = ys[0] / xs[0] ** 0.5
    b.loglog(grid, [ref * x ** 0.5 for x in grid], "--", lw=1.3, color=ASK,
             label="square-root law: $\\pi^{0.5}$")
    b.set_title("(b) the simulator, against the published exponent")
    b.set_xlabel("participation rate $\\pi$")
    b.set_ylabel("shortfall per share, net of half-spread")
    b.set_xticks([0.2, 0.3, 0.4, 0.5, 0.6])
    b.set_xticklabels(["20%", "30%", "40%", "50%", "60%"])
    b.set_yticks([1.0, 2.0, 4.0, 6.0])
    b.set_yticklabels(["1", "2", "4", "6"])
    b.xaxis.set_minor_formatter(NullFormatter())
    b.yaxis.set_minor_formatter(NullFormatter())
    b.grid(which="both", lw=0.5)
    b.legend(fontsize=8, loc="upper left")

    fig.suptitle("Impact: the measurement is right, the market is not",
                 fontsize=11, y=1.02)
    out = DOCS / "impact_law.png"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {out}")
    print(f"  metaorder fit: cost = {k:.3f} * pi^{delta:.3f} over "
          f"{min(xs):.1%}-{max(xs):.1%} participation")


FIGURES = {"depth": fig_depth, "stylized": fig_stylized, "race": fig_race,
           "impact": fig_impact}


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    wanted = sys.argv[1:] or list(FIGURES)
    for name in wanted:
        if name not in FIGURES:
            raise SystemExit(f"unknown figure {name!r}; pick from {list(FIGURES)}")
        FIGURES[name]()


if __name__ == "__main__":
    main()
