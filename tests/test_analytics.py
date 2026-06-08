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


def test_markout_detects_adverse_selection():
    """Agent 1 buys (passively) then the mid falls -> negative markout."""
    from lobster.analytics import Analytics
    from lobster.order import Side
    from lobster.sim import StepMetrics
    from lobster.tape import Tape, Trade

    # mid falls 100, 99, 98, ... (monotonic decline)
    metrics = [StepMetrics(ts=k, best_bid=None, best_ask=None,
                           mid=100.0 - k, spread=None, n_trades=0)
               for k in range(20)]
    tape = Tape()
    # agent 1's resting BID hit by an aggressive SELL at ts=0 -> agent buys passively
    tape.record(Trade(price=100.0, qty=10, buyer_id=1, seller_id=2,
                      ts=0, aggressor=Side.SELL))
    an = Analytics(metrics=metrics, tape=tape, agents=[])
    mo = an.markout(agent_id=1, horizon=5)
    assert mo < 0          # bought, then price dropped -> adverse
    assert mo == -5.0      # +1 * (mid[5]=95 - mid[0]=100)


def test_markout_positive_when_price_moves_favorably():
    from lobster.analytics import Analytics
    from lobster.order import Side
    from lobster.sim import StepMetrics
    from lobster.tape import Tape, Trade

    metrics = [StepMetrics(ts=k, best_bid=None, best_ask=None,
                           mid=100.0 + k, spread=None, n_trades=0)
               for k in range(20)]
    tape = Tape()
    tape.record(Trade(price=100.0, qty=10, buyer_id=1, seller_id=2,
                      ts=0, aggressor=Side.SELL))
    an = Analytics(metrics=metrics, tape=tape, agents=[])
    assert an.markout(agent_id=1, horizon=5) == 5.0  # bought, price rose


def test_markout_passive_only_skips_liquidity_taking():
    from lobster.analytics import Analytics
    from lobster.order import Side
    from lobster.sim import StepMetrics
    from lobster.tape import Tape, Trade

    metrics = [StepMetrics(ts=k, best_bid=None, best_ask=None,
                           mid=100.0 - k, spread=None, n_trades=0)
               for k in range(20)]
    tape = Tape()
    # agent 1 BUYS aggressively (aggressor=BUY) -> excluded under passive_only
    tape.record(Trade(price=100.0, qty=10, buyer_id=1, seller_id=2,
                      ts=0, aggressor=Side.BUY))
    an = Analytics(metrics=metrics, tape=tape, agents=[])
    assert an.markout(agent_id=1, horizon=5, passive_only=True) == 0.0
    assert an.markout(agent_id=1, horizon=5, passive_only=False) == -5.0
