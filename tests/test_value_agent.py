"""ValueAgent: the ladder shape, and that it actually bends impact.

The shape tests are exact. The impact test is the point of the agent, so it
is asserted at a deliberately loose tolerance: it checks that cost stops being
convex in size, not that a stochastic exponent lands on a particular decimal.
"""

from __future__ import annotations

import pytest

from lobster.agents import MarketMakerAgent, NoiseAgent, ValueAgent
from lobster.agents.base import AgentContext
from lobster.execution import execute_metaorder, fit_power_law
from lobster.order import Side
from lobster.sim import Simulation


def _ctx(sim: Simulation, ts: float = 0.0) -> AgentContext:
    return AgentContext(book=sim.book, tape=sim.tape, rng=sim._rng, ts=ts)


def test_rejects_nonsense_parameters():
    for kw in ({"levels": 0}, {"tick": 0.0}, {"tick": -1.0},
               {"slope": 0.0}, {"refill": 0}):
        with pytest.raises(ValueError):
            ValueAgent(agent_id=1, **kw)


def test_ladder_is_thicker_further_from_value():
    """The whole mechanism: depth grows with distance from the fundamental."""
    a = ValueAgent(agent_id=1, value=100.0, levels=5, tick=0.05, slope=2.0,
                   refill=10_000, value_drift=0.0)
    sim = Simulation(agents=[a], seed=0)
    orders = a.step(_ctx(sim))

    sells = {o.price: o.qty for o in orders if o.side is Side.SELL}
    buys = {o.price: o.qty for o in orders if o.side is Side.BUY}
    assert sells == {100.05: 2, 100.10: 4, 100.15: 6, 100.20: 8, 100.25: 10}
    assert buys == {99.95: 2, 99.90: 4, 99.85: 6, 99.80: 8, 99.75: 10}

    # ...and it is linear in the distance, which is the condition that makes
    # walking the book cost sqrt(Q).
    qty = [sells[round(100.0 + i * 0.05, 2)] for i in range(1, 6)]
    steps = {b - a_ for a_, b in zip(qty, qty[1:], strict=False)}
    assert steps == {2}


def test_refill_caps_shares_added_per_tick():
    a = ValueAgent(agent_id=1, levels=40, slope=2.0, refill=7, value_drift=0.0)
    sim = Simulation(agents=[a], seed=0)
    assert sum(o.qty for o in a.step(_ctx(sim))) == 7
    assert sum(o.qty for o in a.step(_ctx(sim, 1.0))) == 7


def test_fills_free_up_room_to_requote_that_level():
    a = ValueAgent(agent_id=1, value=100.0, levels=2, tick=0.05, slope=2.0,
                   refill=10_000, value_drift=0.0)
    sim = Simulation(agents=[a], seed=0)
    a.step(_ctx(sim))
    assert a.step(_ctx(sim, 1.0)) == []       # ladder already complete

    a.on_fill(side_sign=-1, price=100.05, qty=2)   # our 100.05 ask traded
    again = a.step(_ctx(sim, 2.0))
    assert [(o.side, o.price, o.qty) for o in again] == [(Side.SELL, 100.05, 2)]


def test_inventory_cap_stops_one_side_only():
    a = ValueAgent(agent_id=1, value=100.0, levels=3, slope=2.0,
                   refill=10_000, max_position=10, value_drift=0.0)
    sim = Simulation(agents=[a], seed=0)
    a.inventory = 50                                   # long past the cap
    sides = {o.side for o in a.step(_ctx(sim))}
    assert sides == {Side.SELL}                        # will sell, will not buy


def test_drift_retires_rungs_left_behind():
    a = ValueAgent(agent_id=1, value=100.0, levels=2, tick=0.05, slope=2.0,
                   refill=10_000, value_drift=0.0)
    sim = Simulation(agents=[a], seed=0)
    a.step(_ctx(sim))
    assert len(a._resting) == 4

    a.value = 130.0                     # a jump far outside the old ladder
    a.value_drift = 1e-12               # any non-zero value enables retirement
    a.step(_ctx(sim, 1.0))
    assert all(129.0 <= price <= 131.0 for _, price in a._resting)


def _mix(with_value: bool):
    agents = [
        NoiseAgent(agent_id=1, intensity=0.6, spread_offset=0.6, qty=8,
                   market_order_rate=0.25),
        NoiseAgent(agent_id=2, intensity=0.5, spread_offset=0.6, qty=8,
                   market_order_rate=0.25),
        MarketMakerAgent(agent_id=4, half_spread=0.4, qty=12, inv_skew=0.02),
    ]
    if with_value:
        agents.append(ValueAgent(agent_id=5, value=100.0))
    return agents


def _cost_exponent(with_value: bool, trials: int = 6) -> float | None:
    xs, ys = [], []
    for total in (40, 160, 640):
        costs = []
        for t in range(trials):
            agents = _mix(with_value)
            sim = Simulation(agents=agents, seed=1000 + t)
            va = next((a for a in agents if isinstance(a, ValueAgent)), None)
            for _ in sim.run(400):
                pass
            if sim.book.spread is None:
                continue
            mo = execute_metaorder(
                sim, Side.BUY, total, slice_qty=8, every=2, agent_id=99,
                start_ts=400.0,
                reference=None if va is None else (lambda va=va: va.value),
            )
            if mo.shortfall is not None:
                costs.append(mo.shortfall)
        if costs:
            xs.append(float(total))
            ys.append(sum(costs) / len(costs))
    fit = fit_power_law(xs, ys)
    return fit[1] if fit else None


def test_value_agent_bends_the_cost_curve_down():
    """The reason this agent exists (docs/validation.md 2c).

    Nothing else here replenishes into a metaorder, so cost per share climbs
    too fast with size. This agent is what bends the curve toward the
    empirical exponent.

    Thresholds are set for the cheap configuration above: three sizes, no
    chaser, six trials, which measures roughly 0.79 without and 0.56 with.
    The headline figures (1.38 convex, down to 0.57) need the full harness in
    `examples/validate.py`, which runs seven sizes out to 1280 lots; the
    convexity does not show at 640.
    """
    without = _cost_exponent(with_value=False)
    with_ = _cost_exponent(with_value=True)
    assert without is not None and with_ is not None
    assert with_ < 0.70, f"expected a concave cost exponent, got {with_:.3f}"
    assert without - with_ > 0.12, (
        f"expected the agent to lower the exponent; {without:.3f} -> {with_:.3f}"
    )
