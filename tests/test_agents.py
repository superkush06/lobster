"""Agent unit tests."""

import random

import pytest

from lobster.agents import AgentContext, MarketMakerAgent, MomentumAgent, NoiseAgent
from lobster.book import OrderBook
from lobster.order import Order, OrderType, Side
from lobster.tape import Tape, Trade


@pytest.fixture
def seed_rng():
    return random.Random(0)


def test_noise_agent_reproducible_under_seed(seed_rng):
    """Same seed -> same orders given identical context."""
    book = OrderBook()
    tape = Tape()
    a = NoiseAgent(agent_id=1, intensity=1.0)
    ctx = AgentContext(book=book, tape=tape, rng=seed_rng, ts=0)
    rng2 = random.Random(0)
    ctx2 = AgentContext(book=book, tape=tape, rng=rng2, ts=0)
    out1 = a.step(ctx)
    out2 = a.step(ctx2)
    assert len(out1) == len(out2)
    if out1:
        assert out1[0].side == out2[0].side
        assert out1[0].price == out2[0].price


def test_noise_agent_market_orders_kick_off_trades(seed_rng) -> None:
    """rate=1.0 -> always emits market orders when contra-liquidity exists."""
    book = OrderBook()
    book.add(Order(side=Side.BUY, qty=10, price=99.5, agent_id=0, ts=0))
    book.add(Order(side=Side.SELL, qty=10, price=100.5, agent_id=0, ts=0))
    tape = Tape()
    a = NoiseAgent(agent_id=1, intensity=1.0, market_order_rate=1.0)
    ctx = AgentContext(book=book, tape=tape, rng=seed_rng, ts=1)
    seen_market = False
    for _ in range(20):
        orders = a.step(ctx)
        if orders and orders[0].type is OrderType.MARKET:
            seen_market = True
            break
    assert seen_market


def test_noise_agent_market_order_rate_validates() -> None:
    with pytest.raises(ValueError):
        NoiseAgent(agent_id=1, market_order_rate=1.5)
    with pytest.raises(ValueError):
        NoiseAgent(agent_id=1, market_order_rate=-0.1)


def test_market_maker_quotes_both_sides(seed_rng):
    """Empty book -> MM should quote both bid and ask."""
    book = OrderBook()
    tape = Tape()
    mm = MarketMakerAgent(agent_id=2, half_spread=0.5, qty=10)
    ctx = AgentContext(book=book, tape=tape, rng=seed_rng, ts=0)
    orders = mm.step(ctx)
    sides = {o.side for o in orders}
    assert Side.BUY in sides and Side.SELL in sides


def test_market_maker_respects_inventory_cap(seed_rng):
    """If long beyond cap, MM should only sell."""
    book = OrderBook()
    tape = Tape()
    mm = MarketMakerAgent(agent_id=2, half_spread=0.5, qty=10,
                          inventory_cap=50)
    mm.inventory = 60  # over the cap
    ctx = AgentContext(book=book, tape=tape, rng=seed_rng, ts=0)
    orders = mm.step(ctx)
    assert all(o.side is Side.SELL for o in orders)


def test_momentum_agent_waits_for_lookback(seed_rng):
    """No tape -> no orders."""
    book = OrderBook()
    book.add(Order(side=Side.SELL, qty=10, price=100.5, agent_id=0, ts=0))
    tape = Tape()
    m = MomentumAgent(agent_id=3, lookback=20, threshold=0.3)
    ctx = AgentContext(book=book, tape=tape, rng=seed_rng, ts=0)
    assert m.step(ctx) == []


def test_momentum_agent_chases_imbalance(seed_rng):
    """Heavily one-sided tape -> momentum sends marketable in that direction."""
    book = OrderBook()
    book.add(Order(side=Side.SELL, qty=10, price=100.5, agent_id=0, ts=0))
    tape = Tape()
    for _ in range(20):
        tape.record(Trade(price=100, qty=10, buyer_id=0, seller_id=0,
                          ts=0, aggressor=Side.BUY))
    m = MomentumAgent(agent_id=3, lookback=20, threshold=0.3)
    ctx = AgentContext(book=book, tape=tape, rng=seed_rng, ts=1)
    orders = m.step(ctx)
    assert len(orders) == 1
    assert orders[0].side is Side.BUY
    assert orders[0].type is OrderType.MARKET
