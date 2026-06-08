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
