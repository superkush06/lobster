"""Driver the browser figures call into.

Everything interesting already lives in the package. This wires it into the
three experiments the page runs and reports what the tape says afterwards. The
numbers the page draws come from the package itself, from the matching engine,
`Analytics.markout`, `lobster.stylized` and `fit_power_law`, rather than from a
re-derivation in JavaScript.

Three experiments, two agent mixes, one engine:

* `run` / `one` race two makers that differ only in wire delay. Nothing else
  is in the book but noise, because anything that quotes heavily near the
  touch dilutes the thing being measured: add the value ladder here and the
  faster maker's share of the front of the queue falls from 0.72 to 0.58.
* `impact_point` works a parent order into the mix `docs/validation.md`
  scores, with a switch for the latent-liquidity ladder. That switch is the
  difference between cost that is concave in size and cost that is convex.
* `tape_facts` runs the same mix once and hands back the return distribution
  and the volatility autocorrelation.

The one addition to the package is `_ladder`: a periodic snapshot of the bid
side that keeps each level's orders separate instead of summing them, which is
the thing the first figure animates. It is read straight off
`book.iter_levels`, so it is the real queue the engine matched against.
"""

from __future__ import annotations

import math

from lobster.agents import (
    MarketMakerAgent,
    MomentumAgent,
    NoiseAgent,
    ValueAgent,
)
from lobster.analytics import Analytics
from lobster.execution import execute_metaorder, fit_power_law
from lobster.latency import ConstantLatency, JitteredLatency
from lobster.order import Side
from lobster.sim import Simulation
from lobster.stylized import ReturnFacts, log_returns

FAST, SLOW = 1, 2
MM = dict(half_spread=0.4, qty=10, inv_skew=0.0, inventory_cap=10_000)


def _ladder(sim: Simulation, depth: int = 10, cap: int = 12):
    """The top `depth` bid levels, each as the ordered queue of orders in it.

    Standard book views aggregate a level to one number, which hides the only
    thing that matters here: within a level, orders fill in arrival order. So
    this keeps the orders separate and tags each with its owner:
    1 fast, 2 slow, 0 anyone else.
    """
    out = []
    for i, level in enumerate(sim.book.iter_levels(Side.BUY)):
        if i >= depth:
            break
        q = []
        for o in level.orders:
            owner = o.agent_id if o.agent_id in (FAST, SLOW) else 0
            q.append((owner, o.qty))
            if len(q) >= cap:
                break
        out.append({"px": round(level.price, 2), "q": q})
    return out


def _front_of_queue(sim: Simulation):
    """Which maker, if either, is first in line at the best bid."""
    for level in sim.book.iter_levels(Side.BUY):
        for o in level.orders:
            if o.agent_id in (FAST, SLOW):
                return o.agent_id
        break
    return None


def run(fast_latency: float, slow_latency: float, steps: int = 1500,
        seed: int = 11, queue_every: int = 6, warmup: int = 120,
        capture: bool = True):
    """Race two makers that differ only in wire delay, and report the tape.

    `warmup` ticks are simulated but not filmed: the book starts empty, and the
    first hundred-odd ticks are it filling up rather than the thing being shown.
    Every statistic below still counts them. Only `frames` skips them.

    `capture=False` drops the film strip, which only the first figure wants.
    """
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
    frames = []          # the film strip the queue figure plays
    lead_curve = []      # running front-of-queue share, for the second figure

    for k in range(steps):
        m = sim.step(ts=float(k))
        leader = _front_of_queue(sim)
        if leader is not None:
            front[leader] += 1
        if capture and k >= warmup and k % queue_every == 0:
            frames.append(_ladder(sim))
        if m.mid is not None:
            mids.append(round(m.mid, 3))
        seen = front[FAST] + front[SLOW]
        if k % 10 == 0:
            lead_curve.append(round(front[FAST] / seen, 4) if seen else 0.5)

    an = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    fills = {FAST: 0, SLOW: 0}
    for t in sim.tape:
        for aid in (t.buyer_id, t.seller_id):
            if aid in fills:
                fills[aid] += t.qty

    total = front[FAST] + front[SLOW]
    return {
        "front_fast": front[FAST],
        "front_slow": front[SLOW],
        "share_fast": (front[FAST] / total) if total else 0.5,
        "lead_curve": lead_curve,
        "fills_fast": fills[FAST],
        "fills_slow": fills[SLOW],
        "markout_fast": round(an.markout(agent_id=FAST, horizon=20), 5),
        "markout_slow": round(an.markout(agent_id=SLOW, horizon=20), 5),
        "n_trades": len(sim.tape),
        "mids": mids,
        "frames": frames,
        "frame0_tick": warmup,      # so the figure can label ticks honestly
        "frame_every": queue_every,
    }


SWEEP_SEEDS = range(11, 23)

_SUMMARY = ("share_fast", "markout_fast", "markout_slow",
            "fills_fast", "fills_slow", "lead_curve")


def one(fast_latency: float, slow_latency: float, seed: int):
    """One seed, summary only.

    The browser calls this in a loop instead of `sweep` so it can draw each
    seed as it lands. A full sweep is a second of CPU natively and several
    under WebAssembly, which is a long time to hold a page still.
    """
    r = run(fast_latency, slow_latency, seed=seed, capture=False)
    return {k: r[k] for k in _SUMMARY}


def sweep(fast_latency: float, slow_latency: float, seeds=SWEEP_SEEDS):
    """The same race under a dozen different random seeds.

    One run cannot tell you whether an effect is real or whether that seed was
    kind to you. Queue position survives this and markout does not, which is the
    point the third figure is making, so the page has to actually do the runs
    rather than quote a single lucky one.
    """
    out = {"share": [], "markout_fast": [], "markout_slow": [],
           "fills_fast": [], "fills_slow": [], "curves": []}
    for sd in seeds:
        r = one(fast_latency, slow_latency, sd)
        out["share"].append(r["share_fast"])
        out["markout_fast"].append(r["markout_fast"])
        out["markout_slow"].append(r["markout_slow"])
        out["fills_fast"].append(r["fills_fast"])
        out["fills_slow"].append(r["fills_slow"])
        out["curves"].append(r["lead_curve"])
    return out


# ---------------------------------------------------------------------------
# Experiment 2: what a big order costs
# ---------------------------------------------------------------------------

IMPACT_SIZES = (40, 100, 250, 630, 1280)


def _impact_mix(latent: bool):
    """The mix `docs/validation.md` scores, with the latent ladder switchable.

    Returns the agents and the `ValueAgent` itself, because impact has to be
    measured against the efficient price that agent is quoting off. Without
    that control a fundamental that wandered during execution is billed as
    impact, and the fitted exponent stops meaning anything.
    """
    agents = [
        NoiseAgent(agent_id=1, intensity=0.6, spread_offset=0.6, qty=8,
                   market_order_rate=0.25),
        NoiseAgent(agent_id=2, intensity=0.5, spread_offset=0.6, qty=8,
                   market_order_rate=0.25),
        MomentumAgent(agent_id=3, lookback=20, threshold=0.5, qty=5,
                      max_position=100),
        MarketMakerAgent(agent_id=4, half_spread=0.4, qty=12, inv_skew=0.02),
    ]
    va = ValueAgent(agent_id=5, value=100.0) if latent else None
    if va is not None:
        agents.append(va)
    return agents, va


def impact_point(size: int, latent: bool = True, trials: int = 3,
                 warmup: int = 300, seed: int = 1000):
    """Mean cost per share of a parent order of `size`, net of the half-spread.

    One point on the curve. The page asks for them one at a time so it can
    draw each as it lands rather than freezing for the whole sweep.
    """
    costs, halves = [], []
    for t in range(trials):
        agents, va = _impact_mix(latent)
        sim = Simulation(agents=agents, seed=seed + t)
        for _ in sim.run(warmup):
            pass
        if sim.book.spread is None:
            continue
        halves.append(sim.book.spread / 2.0)
        mo = execute_metaorder(
            sim, Side.BUY, size, slice_qty=8, every=2, agent_id=99,
            start_ts=float(warmup),
            reference=None if va is None else (lambda va=va: va.value),
        )
        if mo.shortfall is not None:
            costs.append(mo.shortfall)
    if not costs:
        return None
    return round(sum(costs) / len(costs) - sum(halves) / len(halves), 6)


def impact_fit(sizes, costs):
    """Fit cost ~ k * Q**delta. `delta` near 0.5 is the square-root law."""
    fit = fit_power_law(list(sizes), list(costs))
    if fit is None:
        return None
    k, delta = fit
    return {"k": k, "exponent": round(delta, 4)}


# ---------------------------------------------------------------------------
# Experiment 3: does the tape look like a real one?
# ---------------------------------------------------------------------------

_TAPE = None


def tape_begin(seed: int = 7):
    """Start a tape run the page can advance in pieces.

    Nine thousand ticks is about eleven seconds under WebAssembly, which is a
    long time to show an empty figure. Held here so the browser can step it and
    redraw between steps.
    """
    global _TAPE
    agents, _ = _impact_mix(True)
    _TAPE = {"sim": Simulation(agents=agents, seed=seed), "k": 0}
    return 0


def tape_advance(chunk: int = 1500):
    """Run `chunk` more ticks and report the histogram so far."""
    st = _TAPE
    for _ in range(chunk):
        st["sim"].step(ts=float(st["k"]))
        st["k"] += 1
    mids = [m.mid for m in st["sim"].metrics if m.mid is not None]
    h = _histogram(log_returns(mids))
    h["k"] = st["k"]
    return h


def _histogram(r, bins: int = 41, clip: float = 5.0):
    n = len(r)
    if n < 2:
        return {"n": n, "edges": [], "counts": [], "gauss": [], "zero_share": 0.0}
    mu = sum(r) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in r) / (n - 1)) or 1.0
    edges = [-clip + 2 * clip * i / bins for i in range(bins + 1)]
    counts = [0] * bins
    for x in r:
        j = int(((x - mu) / sd + clip) / (2 * clip) * bins)
        if 0 <= j < bins:
            counts[j] += 1
    width = 2 * clip / bins
    gauss = [n * width * math.exp(-c * c / 2) / math.sqrt(2 * math.pi)
             for c in (e + width / 2 for e in edges[:-1])]
    return {
        "n": n,
        "zero_share": round(sum(1 for x in r if x == 0.0) / n, 4),
        "edges": [round(e, 4) for e in edges],
        "counts": counts,
        "gauss": [round(g, 3) for g in gauss],
    }


def tape_finish():
    """The autocorrelations and moments, once enough ticks have accumulated."""
    mids = [m.mid for m in _TAPE["sim"].metrics if m.mid is not None]
    r = log_returns(mids)
    facts = ReturnFacts.measure(r, max_lag=100)
    out = _histogram(r)
    out.update({
        "abs_acf": [round(v, 5) for v in facts.abs_ret_acf],
        "ret_acf": [round(v, 5) for v in facts.ret_acf[:20]],
        "kurtosis": round(facts.excess_kurtosis, 2),
        "tail_index": (round(facts.tail_index, 2)
                       if facts.tail_index is not None else None),
        "decay": (round(facts.clustering_decay, 3)
                  if facts.clustering_decay is not None else None),
    })
    return out


def tape_facts(steps: int = 9000, seed: int = 7, bins: int = 41,
               clip: float = 5.0):
    """Return distribution and volatility memory from one run of the mix.

    The histogram is of returns in units of their own standard deviation, so
    it can be laid over a standard normal with the same area. Zero returns are
    counted and reported separately: the mid only moves when the touch does,
    so a large point mass at zero is real and it inflates kurtosis
    mechanically. Saying how many there are is the difference between a heavy
    tail and an artefact.
    """
    agents, _ = _impact_mix(True)
    sim = Simulation(agents=agents, seed=seed)
    for _ in sim.run(steps):
        pass
    mids = [m.mid for m in sim.metrics if m.mid is not None]
    r = log_returns(mids)
    facts = ReturnFacts.measure(r, max_lag=100)

    n = len(r)
    zeros = sum(1 for x in r if x == 0.0)
    mu = sum(r) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in r) / (n - 1))
    edges = [-clip + 2 * clip * i / bins for i in range(bins + 1)]
    counts = [0] * bins
    for x in r:
        z = (x - mu) / sd
        j = int((z + clip) / (2 * clip) * bins)
        if 0 <= j < bins:
            counts[j] += 1
    width = 2 * clip / bins
    gauss = [n * width * math.exp(-c * c / 2) / math.sqrt(2 * math.pi)
             for c in (e + width / 2 for e in edges[:-1])]

    return {
        "n": n,
        "zero_share": round(zeros / n, 4),
        "edges": [round(e, 4) for e in edges],
        "counts": counts,
        "gauss": [round(g, 3) for g in gauss],
        "abs_acf": [round(v, 5) for v in facts.abs_ret_acf],
        "ret_acf": [round(v, 5) for v in facts.ret_acf[:20]],
        "kurtosis": round(facts.excess_kurtosis, 2),
        "tail_index": (round(facts.tail_index, 2)
                       if facts.tail_index is not None else None),
        "decay": (round(facts.clustering_decay, 3)
                  if facts.clustering_decay is not None else None),
    }
