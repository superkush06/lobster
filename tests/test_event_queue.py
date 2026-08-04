"""Event-driven arrival queue: latency models wired into the Simulation."""

from lobster.agents import MarketMakerAgent, NoiseAgent
from lobster.agents.base import Agent
from lobster.latency import ConstantLatency, JitteredLatency
from lobster.order import Order, Side
from lobster.sim import Simulation


def _trades_fingerprint(sim):
    return [(t.ts, t.price, t.qty, t.buyer_id, t.seller_id) for t in sim.tape]


def _mids(sim):
    return [m.mid for m in sim.metrics]


def _make_agents(latency=None):
    return [
        NoiseAgent(agent_id=1, intensity=0.6, market_order_rate=0.25,
                   latency=latency),
        NoiseAgent(agent_id=2, intensity=0.5, market_order_rate=0.25,
                   latency=latency),
        MarketMakerAgent(agent_id=3, half_spread=0.4, qty=12,
                         latency=latency),
    ]


def test_zero_latency_reproduces_synchronous_loop_exactly():
    """ConstantLatency(0) for every agent must be bit-identical to the
    latency-free synchronous loop — the degenerate case of the event queue."""
    sim_none = Simulation(agents=_make_agents(latency=None), seed=11)
    for _ in sim_none.run(steps=400):
        pass
    sim_zero = Simulation(
        agents=_make_agents(latency=ConstantLatency(0.0)), seed=11)
    for _ in sim_zero.run(steps=400):
        pass
    assert _trades_fingerprint(sim_zero) == _trades_fingerprint(sim_none)
    assert _mids(sim_zero) == _mids(sim_none)


class _OneShot(Agent):
    """Submits a single limit buy at ts=0, nothing else."""

    def __init__(self, agent_id, latency=None):
        super().__init__(agent_id, latency=latency)

    def step(self, ctx):
        if ctx.ts == 0:
            return [Order(side=Side.BUY, qty=5, price=99.0,
                          agent_id=self.id, ts=ctx.ts)]
        return []


def test_delayed_order_arrives_later_tick():
    """delay > dt: the order is in flight during tick 0 and only reaches the
    book once its arrival time is due."""
    sim = Simulation(agents=[_OneShot(agent_id=1,
                                      latency=ConstantLatency(1.5))], seed=0)
    sim.step(ts=0.0)
    assert sim.book.best_bid is None       # still in flight
    sim.step(ts=1.0)
    assert sim.book.best_bid == 99.0       # arrived at t=1.5, within tick 1


def test_sub_tick_delay_arrives_same_tick():
    sim = Simulation(agents=[_OneShot(agent_id=1,
                                      latency=ConstantLatency(0.25))], seed=0)
    sim.step(ts=0.0)
    assert sim.book.best_bid == 99.0


def test_arrival_order_follows_latency_not_submission_order():
    """Two agents submit in the same tick; the lower-latency one must be
    first in the FIFO queue at the shared price level."""
    fast = _OneShot(agent_id=1, latency=ConstantLatency(0.1))
    slow = _OneShot(agent_id=2, latency=ConstantLatency(0.9))
    # Run both orders through one tick regardless of shuffle order.
    sim = Simulation(agents=[slow, fast], seed=5)
    sim.step(ts=0.0)
    level = next(sim.book.iter_levels(Side.BUY))
    assert [o.agent_id for o in level.orders] == [1, 2]


def test_jittered_latency_is_deterministic_under_seed():
    def run(seed):
        sim = Simulation(
            agents=_make_agents(latency=JitteredLatency(mean=0.4, shape=2.0)),
            seed=seed)
        for _ in sim.run(steps=300):
            pass
        return _trades_fingerprint(sim)

    assert run(9) == run(9)


def test_delayed_trades_stamped_with_arrival_time():
    class _Sniper(Agent):
        def __init__(self, agent_id, latency=None):
            super().__init__(agent_id, latency=latency)

        def step(self, ctx):
            if ctx.ts == 1:  # lift the resting offer from tick 0
                from lobster.order import OrderType
                return [Order(side=Side.BUY, qty=5, type=OrderType.MARKET,
                              agent_id=self.id, ts=ctx.ts)]
            return []

    class _Poster(Agent):
        def step(self, ctx):
            if ctx.ts == 0:
                return [Order(side=Side.SELL, qty=5, price=100.0,
                              agent_id=self.id, ts=ctx.ts)]
            return []

    sim = Simulation(agents=[_Poster(agent_id=1),
                             _Sniper(agent_id=2,
                                     latency=ConstantLatency(0.5))], seed=0)
    sim.step(ts=0.0)
    sim.step(ts=1.0)
    assert len(sim.tape) == 1
    assert list(sim.tape)[0].ts == 1.5  # decision at 1.0 + 0.5 latency


def test_latency_none_agents_unchanged_by_dt():
    """Sanity: non-unit dt does not break the no-latency path."""
    sim = Simulation(agents=_make_agents(latency=None), seed=2)
    for _ in sim.run(steps=100, dt=0.5):
        pass
    assert len(sim.metrics) == 100
