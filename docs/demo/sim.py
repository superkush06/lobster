"""Driver the browser figures call into.

Everything interesting already lives in the package; this only wires two market
makers with different wire delays into a `Simulation` and reports what the tape
says afterwards. The numbers the page draws are the package's own — the
matching engine, `Analytics.markout` — not a re-derivation in JavaScript.

The one addition is `_ladder`: a periodic snapshot of the bid side that keeps
each level's orders separate instead of summing them, which is the thing the
first figure animates. It is read straight off `book.iter_levels`, so it is the
real queue the engine matched against, not a reconstruction.
"""

from __future__ import annotations

from lobster.agents import MarketMakerAgent, NoiseAgent
from lobster.analytics import Analytics
from lobster.latency import ConstantLatency, JitteredLatency
from lobster.order import Side
from lobster.sim import Simulation

FAST, SLOW = 1, 2
MM = dict(half_spread=0.4, qty=10, inv_skew=0.0, inventory_cap=10_000)


def _ladder(sim: Simulation, depth: int = 10, cap: int = 12):
    """The top `depth` bid levels, each as the ordered queue of orders in it.

    Standard book views aggregate a level to one number, which hides the only
    thing that matters here: within a level, orders fill in arrival order. So
    this keeps the orders separate and tags each with its owner —
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
        seed: int = 11, queue_every: int = 6, warmup: int = 120):
    """Race two makers that differ only in wire delay, and report the tape.

    `warmup` ticks are simulated but not filmed: the book starts empty, and the
    first hundred-odd ticks are it filling up rather than the thing being shown.
    Every statistic below still counts them — only `frames` skips them.
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
        if k >= warmup and k % queue_every == 0:
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


def sweep(fast_latency: float, slow_latency: float, seeds=range(11, 23)):
    """The same race under a dozen different random seeds.

    One run cannot tell you whether an effect is real or whether that seed was
    kind to you. Queue position survives this and markout does not, which is the
    point the third figure is making — so the page has to actually do the runs
    rather than quote a single lucky one.
    """
    out = {"share": [], "markout_fast": [], "markout_slow": [],
           "fills_fast": [], "fills_slow": [], "curves": []}
    for sd in seeds:
        r = run(fast_latency, slow_latency, seed=sd, queue_every=60)
        out["share"].append(r["share_fast"])
        out["markout_fast"].append(r["markout_fast"])
        out["markout_slow"].append(r["markout_slow"])
        out["fills_fast"].append(r["fills_fast"])
        out["fills_slow"].append(r["fills_slow"])
        out["curves"].append(r["lead_curve"])
    return out
