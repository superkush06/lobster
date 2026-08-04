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


def test_market_maker_cancels_stale_quotes():
    """With cancel_replace on, the maker pulls its previous quotes each tick,
    so its resting layers never accumulate beyond the two fresh quotes."""
    book = OrderBook()
    mm = MarketMakerAgent(agent_id=1, half_spread=0.5, qty=10, inv_skew=0.0,
                          cancel_replace=True)
    rng = random.Random(0)
    for ts in range(20):
        ctx = AgentContext(book=book, tape=Tape(), rng=rng, ts=ts)
        for o in mm.step(ctx):
            book.add(o)
    # Only the two most-recent quotes should rest (mid drifts none here).
    assert len(book) == 2


def test_market_maker_without_cancel_accumulates():
    """Control: with cancel_replace off, stale layers pile up across ticks."""
    book = OrderBook()
    mm = MarketMakerAgent(agent_id=1, half_spread=0.5, qty=10, inv_skew=0.0,
                          cancel_replace=False)
    rng = random.Random(0)
    for ts in range(20):
        # Nudge mid so each tick quotes at a new price level
        book.add(Order(Side.BUY, qty=1, price=90.0 + ts * 0.1))
        ctx = AgentContext(book=book, tape=Tape(), rng=rng, ts=ts)
        for o in mm.step(ctx):
            book.add(o)
    # Far more than 2 resting orders — the accumulation the README warns about.
    assert len(book) > 10


def test_market_maker_anchors_to_last_mid_not_hardcoded_100():
    """If the book empties after the price drifted, the maker must quote
    around the last mid it saw — not snap back to 100 and flash-crash."""
    book = OrderBook()
    book.add(Order(Side.BUY, qty=10, price=149.5, agent_id=0, ts=0))
    book.add(Order(Side.SELL, qty=10, price=150.5, agent_id=0, ts=0))
    mm = MarketMakerAgent(agent_id=2, half_spread=0.5, qty=10, inv_skew=0.0,
                          cancel_replace=False)
    rng = random.Random(0)
    mm.step(AgentContext(book=book, tape=Tape(), rng=rng, ts=0))  # sees mid=150
    empty = OrderBook()  # book momentarily one-sided/empty
    orders = mm.step(AgentContext(book=empty, tape=Tape(), rng=rng, ts=1))
    for o in orders:
        assert abs(o.price - 150.0) < 5.0, f"quoted {o.price}, expected near 150"


def test_noise_agent_anchors_to_last_mid_not_hardcoded_100():
    book = OrderBook()
    book.add(Order(Side.BUY, qty=10, price=149.5, agent_id=0, ts=0))
    book.add(Order(Side.SELL, qty=10, price=150.5, agent_id=0, ts=0))
    a = NoiseAgent(agent_id=1, intensity=1.0)
    rng = random.Random(0)
    a.step(AgentContext(book=book, tape=Tape(), rng=rng, ts=0))  # sees mid=150
    empty = OrderBook()
    orders = a.step(AgentContext(book=empty, tape=Tape(), rng=rng, ts=1))
    assert orders, "intensity=1.0 must emit an order"
    assert abs(orders[0].price - 150.0) < 5.0


def test_ref_price_seeds_first_quote():
    """Before any mid is ever observed, quotes anchor at `ref_price`."""
    mm = MarketMakerAgent(agent_id=2, half_spread=0.5, qty=10, inv_skew=0.0,
                          ref_price=42.0)
    rng = random.Random(0)
    orders = mm.step(AgentContext(book=OrderBook(), tape=Tape(), rng=rng, ts=0))
    assert {o.price for o in orders} == {41.5, 42.5}


def test_momentum_agent_respects_max_position(seed_rng):
    """A capped momentum agent must not chase beyond its position limit —
    uncapped chasing on a wash-free tape feeds back into its own signal."""
    book = OrderBook()
    book.add(Order(side=Side.SELL, qty=10, price=100.5, agent_id=0, ts=0))
    tape = Tape()
    for _ in range(20):
        tape.record(Trade(price=100, qty=10, buyer_id=0, seller_id=0,
                          ts=0, aggressor=Side.BUY))
    m = MomentumAgent(agent_id=3, lookback=20, threshold=0.3, qty=5,
                      max_position=10)
    m.inventory = 8  # one more 5-lot buy would breach the cap
    ctx = AgentContext(book=book, tape=tape, rng=seed_rng, ts=1)
    assert m.step(ctx) == []
    m.inventory = 5  # exactly at the limit after the next buy -> allowed
    assert len(m.step(ctx)) == 1
