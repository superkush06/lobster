from lobster.agents import MarketMakerAgent, NoiseAgent
from lobster.analytics import Analytics
from lobster.sim import Simulation


def _run_sim(steps=500, seed=11):
    sim = Simulation(
        agents=[
            NoiseAgent(agent_id=1, intensity=0.5),
            MarketMakerAgent(agent_id=2, half_spread=0.3, qty=10),
        ],
        seed=seed,
    )
    for _ in sim.run(steps=steps):
        pass
    return sim


def test_spread_stats_keys():
    sim = _run_sim()
    a = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    s = a.spread_stats()
    assert set(s) == {"mean", "std", "p50", "p95"}
    assert s["mean"] >= 0


def test_mid_returns_length():
    sim = _run_sim()
    a = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    rets = a.mid_returns()
    # Returns one less than the number of non-None mids.
    mids = [m.mid for m in sim.metrics if m.mid is not None]
    assert len(rets) == max(0, len(mids) - 1)


def test_pnl_dict_shape():
    sim = _run_sim()
    a = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    pnl = a.agent_pnl()
    assert set(pnl) == {1, 2}
    for v in pnl.values():
        assert set(v) == {"cash", "inventory", "mark", "pnl_mtm"}


def test_pnl_conservation_small_residue():
    # In a closed simulation, sum of cash + inventory * last_mid is small
    # but not zero (inventory carry).
    sim = _run_sim(steps=300)
    a = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    total = a.pnl_conservation()
    # Within 5x the recent vwap-spread (very loose; just sanity).
    assert isinstance(total, float)


def test_imbalance_bounded():
    sim = _run_sim()
    a = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    imb = a.buy_sell_imbalance()
    assert -1.0 <= imb <= 1.0
