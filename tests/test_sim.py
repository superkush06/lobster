"""Simulation event-loop tests."""


from lobster.agents import MarketMakerAgent, NoiseAgent
from lobster.sim import Simulation


def test_sim_deterministic_with_seed():
    def run(seed):
        sim = Simulation(
            agents=[
                NoiseAgent(agent_id=1, intensity=0.5, market_order_rate=0.2),
                MarketMakerAgent(agent_id=2, half_spread=0.3, qty=15),
            ],
            seed=seed,
        )
        for _ in sim.run(steps=200, dt=1.0):
            pass
        return [m.mid for m in sim.metrics if m.mid is not None]

    a = run(42)
    b = run(42)
    assert a == b


def test_sim_metrics_emitted():
    sim = Simulation(
        agents=[
            NoiseAgent(agent_id=1, intensity=0.5),
            MarketMakerAgent(agent_id=2, half_spread=0.3, qty=15),
        ],
        seed=7,
    )
    for _ in sim.run(steps=50):
        pass
    assert len(sim.metrics) == 50


def test_sim_soak_5k_steps():
    """5k-step soak: nothing crashes and trades occur."""
    sim = Simulation(
        agents=[
            NoiseAgent(agent_id=1, intensity=0.6, market_order_rate=0.2),
            NoiseAgent(agent_id=2, intensity=0.6, market_order_rate=0.2),
            MarketMakerAgent(agent_id=3, half_spread=0.3, qty=10),
        ],
        seed=1234,
    )
    for _ in sim.run(steps=5000):
        pass
    assert len(sim.metrics) == 5000
    assert len(sim.tape) > 0


def test_simulation_attributes_pnl_to_agents() -> None:
    """Regression: trades must update on_fill, so agents end with non-zero
    inventory/cash. Catches the agent_id vs Order.id mix-up bug.
    """
    sim = Simulation(
        agents=[
            NoiseAgent(agent_id=1, intensity=1.0, market_order_rate=1.0,
                       qty=5),
            MarketMakerAgent(agent_id=2, half_spread=0.2, qty=20),
        ],
        seed=42,
    )
    for _ in sim.run(steps=200):
        pass
    pnl = {a.id: (a.cash, a.inventory) for a in sim.agents}
    assert len(sim.tape) > 0
    nonzero = [pid for pid, (c, i) in pnl.items() if c != 0 or i != 0]
    assert nonzero, f"no agent received fills; attribution broken: {pnl}"


def _demo_agents():
    """The README demo configuration (2 noise + momentum + maker)."""
    from lobster.agents import MomentumAgent
    return [
        NoiseAgent(agent_id=1, intensity=0.6, spread_offset=0.6,
                   qty=8, market_order_rate=0.25),
        NoiseAgent(agent_id=2, intensity=0.5, spread_offset=0.6,
                   qty=8, market_order_rate=0.25),
        MomentumAgent(agent_id=3, lookback=20, threshold=0.35, qty=5),
        MarketMakerAgent(agent_id=4, half_spread=0.4, qty=12, inv_skew=0.02),
    ]


def test_default_sim_has_no_wash_trades():
    """Regression: without STP, ~58% of trades in this exact config were an
    agent trading with itself. The default sim must produce a clean tape."""
    from lobster.analytics import Analytics

    sim = Simulation(agents=_demo_agents(), seed=7)
    for _ in sim.run(steps=1000):
        pass
    an = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    assert len(sim.tape) > 100  # still an active market
    assert an.wash_trade_fraction() == 0.0
    assert all(t.buyer_id != t.seller_id for t in sim.tape)


def test_stp_none_reproduces_wash_trades():
    """Control for the test above: turning STP off brings self-trades back,
    proving the default is doing the filtering."""
    from lobster.analytics import Analytics

    sim = Simulation(agents=_demo_agents(), seed=7, stp=None)
    for _ in sim.run(steps=1000):
        pass
    an = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    # Noise TTL already removes many stale quotes, but a measurable share
    # of self-trades still prints without STP.
    assert an.wash_trade_fraction() > 0.03


def test_noise_ttl_bounds_resting_book():
    """Regression: a pure-noise run used to leave one resting order per
    submission (20k orders after 20k steps). With default TTL the book
    stays bounded."""
    sim = Simulation(
        agents=[NoiseAgent(agent_id=1, intensity=0.5, market_order_rate=0.0)],
        seed=3,
    )
    for _ in sim.run(steps=2000):
        pass
    # ~1000 submissions; without expiry len(book) ~= 1000.
    assert len(sim.book) < 300, f"book grew to {len(sim.book)} resting orders"


def test_ttl_expires_resting_order():
    from lobster.book import OrderBook
    from lobster.order import Order, Side

    class OneShot(NoiseAgent):
        """Submits exactly one TTL'd limit order at ts=0."""
        def step(self, ctx):
            if ctx.ts == 0:
                return [Order(side=Side.BUY, qty=5, price=99.0,
                              agent_id=self.id, ts=ctx.ts, ttl=3.0)]
            return []

    sim = Simulation(agents=[OneShot(agent_id=1)], book=OrderBook(), seed=0)
    sim.step(ts=0.0)
    assert sim.book.best_bid == 99.0
    sim.step(ts=1.0)
    assert sim.book.best_bid == 99.0   # still alive
    sim.step(ts=3.0)
    assert sim.book.best_bid is None   # expired at ts >= 3.0


def test_order_ttl_validates():
    import pytest

    from lobster.order import Order, Side
    with pytest.raises(ValueError):
        Order(Side.BUY, qty=1, price=1.0, ttl=-1.0)
