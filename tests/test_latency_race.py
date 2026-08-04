"""Latency race: a faster market maker must win queue position and fills.

This is the canonical microstructure result the event-driven scheduler
exists to reproduce: with two makers quoting identical prices, the one with
lower submission latency reaches each price level first, sits at the front
of the FIFO queue, and captures a disproportionate share of passive fills.
"""

from lobster.agents import MarketMakerAgent, NoiseAgent
from lobster.latency import ConstantLatency, JitteredLatency
from lobster.order import Side
from lobster.sim import Simulation

FAST, SLOW = 1, 2


def _run_race(steps=1500, seed=11):
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
        for level in sim.book.iter_levels(Side.BUY):
            for o in level.orders:
                if o.agent_id in front:
                    front[o.agent_id] += 1
                    break
            break  # best bid level only
    vol = {FAST: 0, SLOW: 0}
    for t in sim.tape:
        for mid in (FAST, SLOW):
            if mid in (t.buyer_id, t.seller_id):
                vol[mid] += t.qty
    return sim, front, vol


def test_faster_maker_wins_front_of_queue():
    _, front, _ = _run_race()
    total = front[FAST] + front[SLOW]
    assert total > 0
    assert front[FAST] / total > 0.6, (
        f"fast maker only led the queue {front[FAST]}/{total} of the time"
    )


def test_faster_maker_captures_more_passive_volume():
    _, _, vol = _run_race()
    assert vol[FAST] > 2 * vol[SLOW], (
        f"expected the fast maker to dominate fills, got {vol}"
    )


def test_race_outcome_holds_across_seeds():
    for seed in (3, 7):
        _, front, vol = _run_race(steps=1000, seed=seed)
        assert front[FAST] > front[SLOW]
        assert vol[FAST] > vol[SLOW]
