"""Unit tests for the execution-cost layer."""

from __future__ import annotations

import math

import pytest

from lobster import Order, OrderBook, Side, Simulation
from lobster.agents import MarketMakerAgent, NoiseAgent
from lobster.execution import (
    Sweep,
    cost_to_trade,
    execute_metaorder,
    fit_power_law,
)


def three_level_book() -> OrderBook:
    book = OrderBook()
    for price, qty in ((99.5, 100), (99.0, 50)):
        book.add(Order(Side.BUY, qty=qty, price=price))
    for price, qty in ((100.0, 10), (100.5, 20), (101.0, 40)):
        book.add(Order(Side.SELL, qty=qty, price=price))
    return book


def test_cost_to_trade_walks_the_levels_in_order():
    book = three_level_book()
    sweep = cost_to_trade(book, Side.BUY, 25)
    assert sweep is not None
    assert sweep.filled == 25
    assert sweep.complete
    # 10 @ 100.0 + 15 @ 100.5
    assert sweep.notional == pytest.approx(10 * 100.0 + 15 * 100.5)
    assert sweep.avg_price == pytest.approx(sweep.notional / 25)
    # arrival mid (99.5 + 100.0)/2 = 99.75; after, best ask is 100.5
    assert sweep.arrival_mid == pytest.approx(99.75)
    assert sweep.mid_after == pytest.approx(100.0)
    assert sweep.impact == pytest.approx(0.25)
    assert sweep.slippage == pytest.approx(sweep.avg_price - 99.75)


def test_cost_to_trade_does_not_mutate_the_book():
    book = three_level_book()
    before = book.snapshot(levels=5)
    cost_to_trade(book, Side.BUY, 60)
    assert book.snapshot(levels=5) == before


def test_cost_to_trade_reports_an_incomplete_walk():
    book = three_level_book()
    sweep = cost_to_trade(book, Side.BUY, 1000)
    assert sweep is not None
    assert not sweep.complete
    assert sweep.filled == 70


def test_cost_to_trade_needs_a_two_sided_book():
    book = OrderBook()
    book.add(Order(Side.SELL, qty=10, price=100.0))
    assert cost_to_trade(book, Side.BUY, 5) is None
    with pytest.raises(ValueError):
        cost_to_trade(three_level_book(), Side.BUY, 0)


def test_sell_side_signs_are_mirrored():
    book = three_level_book()
    sweep = cost_to_trade(book, Side.SELL, 120)
    assert sweep is not None
    # 100 @ 99.5 + 20 @ 99.0, and the touch drops to 99.0
    assert sweep.avg_price == pytest.approx(11930 / 120)
    assert sweep.slippage == pytest.approx(99.75 - 11930 / 120)
    assert sweep.slippage > 0.0
    assert sweep.impact == pytest.approx(0.25)

    # A sell that does not clear the touch level moves nothing.
    assert cost_to_trade(book, Side.SELL, 50).impact == pytest.approx(0.0)


def test_empty_sweep_reports_no_price():
    sweep = Sweep(side=Side.BUY, requested=10, filled=0, notional=0.0,
                  arrival_mid=100.0, mid_after=100.0)
    assert sweep.avg_price is None
    assert sweep.slippage is None


def test_metaorder_pays_more_than_the_arrival_mid():
    agents = [
        NoiseAgent(agent_id=1, intensity=0.6, spread_offset=0.6, qty=8,
                   market_order_rate=0.2),
        MarketMakerAgent(agent_id=2, half_spread=0.4, qty=12),
    ]
    sim = Simulation(agents=agents, seed=3)
    for _ in sim.run(200):
        pass
    mo = execute_metaorder(sim, Side.BUY, total_qty=200, slice_qty=10,
                           every=2, agent_id=99, start_ts=200.0,
                           decay_steps=50)
    assert mo.children == 20
    assert mo.filled > 0
    assert mo.shortfall is not None and mo.shortfall > 0.0
    assert mo.peak_impact is not None
    assert mo.permanent_impact is not None
    assert mo.vwap == pytest.approx(mo.notional / mo.filled)


def test_metaorder_rejects_nonsense_arguments():
    sim = Simulation(agents=[MarketMakerAgent(agent_id=1)], seed=0)
    for _ in sim.run(5):
        pass
    with pytest.raises(ValueError):
        execute_metaorder(sim, Side.BUY, 0, 5)
    with pytest.raises(ValueError):
        execute_metaorder(sim, Side.BUY, 10, 5, every=0)


def test_metaorder_needs_a_warmed_up_book():
    sim = Simulation(agents=[MarketMakerAgent(agent_id=1)], seed=0)
    with pytest.raises(ValueError, match="no mid"):
        execute_metaorder(sim, Side.BUY, 10, 5)


def test_fit_power_law_is_exact_and_degrades_gracefully():
    xs = [1.0, 2.0, 4.0, 8.0]
    k, d = fit_power_law(xs, [3.0 * x ** 0.5 for x in xs])
    assert k == pytest.approx(3.0)
    assert d == pytest.approx(0.5)
    assert fit_power_law([1.0, 2.0], [1.0, 2.0]) is None       # too few points
    assert fit_power_law(xs, [1.0, -1.0, 2.0, 3.0]) is not None  # drops the -1
    assert fit_power_law([2.0] * 4, [1.0, 2.0, 3.0, 4.0]) is None  # no x spread
    assert math.isfinite(k)
