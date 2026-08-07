import pytest

from lobster.book import OrderBook
from lobster.matching import match
from lobster.order import Order, OrderType, Side
from lobster.tape import Tape


def test_simple_cross_at_best_ask():
    book = OrderBook()
    book.add(Order(Side.SELL, qty=10, price=100.0))
    taker = Order(Side.BUY, qty=10, price=100.0)
    trades = match(book, taker)
    assert len(trades) == 1
    assert trades[0].price == 100.0
    assert trades[0].qty == 10
    assert book.best_ask is None


def test_partial_fill_leaves_residual_on_book():
    book = OrderBook()
    book.add(Order(Side.SELL, qty=10, price=100.0))
    taker = Order(Side.BUY, qty=15, price=100.0)
    trades = match(book, taker)
    assert len(trades) == 1
    assert trades[0].qty == 10
    # 5 residual buy now resting at 100.0
    assert book.best_bid == 100.0


def test_market_order_sweeps_top():
    book = OrderBook()
    book.add(Order(Side.SELL, qty=5, price=100.0))
    book.add(Order(Side.SELL, qty=5, price=101.0))
    taker = Order(Side.BUY, qty=8, type=OrderType.MARKET)
    trades = match(book, taker)
    assert sum(t.qty for t in trades) == 8
    assert {t.price for t in trades} == {100.0, 101.0}
    # 2 left at 101.0
    assert book.depth(Side.SELL)[0] == (101.0, 2)


def test_limit_no_cross_rests():
    book = OrderBook()
    book.add(Order(Side.SELL, qty=10, price=101.0))
    # Bid at 99.5 doesn't cross 101.0 ask
    book.add(Order(Side.BUY, qty=10, price=99.5))
    assert book.best_bid == 99.5
    assert book.best_ask == 101.0


def test_market_order_on_empty_side_no_trade():
    book = OrderBook()
    # No asks; market buy can't fill
    trades = match(book, Order(Side.BUY, qty=10, type=OrderType.MARKET))
    assert trades == []


def test_callback_invoked_per_trade():
    book = OrderBook()
    book.add(Order(Side.SELL, qty=5, price=100.0))
    book.add(Order(Side.SELL, qty=5, price=101.0))
    tape = Tape()
    match(book, Order(Side.BUY, qty=10, type=OrderType.MARKET),
          on_trade=tape.record)
    assert len(tape) == 2


def test_fifo_priority_within_level():
    book = OrderBook()
    o1 = Order(Side.SELL, qty=5, price=100.0, agent_id=11)
    o2 = Order(Side.SELL, qty=5, price=100.0, agent_id=22)
    book.add(o1); book.add(o2)
    trades = match(book, Order(Side.BUY, qty=5, price=100.0,
                               agent_id=99))
    # o1 (agent 11) should be fully consumed first because of FIFO.
    assert trades[0].seller_id == 11
    assert trades[0].buyer_id == 99


def test_market_order_remainder_stays_on_taker():
    """A 50-lot market buy against 5 on the book fills 5; the unfilled 45
    must remain observable as the taker's leaves quantity, and must not
    silently rest on the book."""
    book = OrderBook()
    book.add(Order(Side.SELL, qty=5, price=100.0))
    taker = Order(Side.BUY, qty=50, type=OrderType.MARKET)
    trades = match(book, taker)
    assert sum(t.qty for t in trades) == 5
    assert taker.qty == 45          # leaves qty; book exhausted
    assert book.best_bid is None    # remainder did NOT rest
    assert book.best_ask is None


def test_full_fill_leaves_zero_qty_on_taker():
    book = OrderBook()
    book.add(Order(Side.SELL, qty=10, price=100.0))
    taker = Order(Side.BUY, qty=10, price=100.0)
    match(book, taker)
    assert taker.qty == 0


# ---- self-trade prevention ----------------------------------------------------


def test_no_stp_by_default_agent_can_self_trade():
    """Backward-compat: match() alone still permits self-trades."""
    book = OrderBook()
    book.add(Order(Side.SELL, qty=10, price=100.0, agent_id=7))
    trades = match(book, Order(Side.BUY, qty=10, price=100.0, agent_id=7))
    assert len(trades) == 1
    assert trades[0].buyer_id == trades[0].seller_id == 7


def test_stp_cancel_resting_removes_own_quote_and_continues():
    book = OrderBook()
    book.add(Order(Side.SELL, qty=10, price=100.0, agent_id=7))   # own stale ask
    book.add(Order(Side.SELL, qty=10, price=100.0, agent_id=8))   # someone else
    trades = match(book, Order(Side.BUY, qty=10, price=100.0, agent_id=7),
                   stp="cancel_resting")
    assert len(trades) == 1
    assert trades[0].seller_id == 8          # own order skipped, not traded
    assert all(t.buyer_id != t.seller_id for t in trades)
    assert book.best_ask is None             # own stale quote was cancelled


def test_stp_cancel_taker_keeps_resting_order():
    book = OrderBook()
    book.add(Order(Side.SELL, qty=10, price=100.0, agent_id=7))
    taker = Order(Side.BUY, qty=10, price=100.0, agent_id=7)
    trades = match(book, taker, stp="cancel_taker")
    assert trades == []
    assert book.best_ask == 100.0            # resting order survives
    assert book.best_bid is None             # taker remainder NOT rested


def test_stp_cancel_resting_rests_taker_if_no_liquidity_left():
    book = OrderBook()
    book.add(Order(Side.SELL, qty=10, price=100.0, agent_id=7))
    taker = Order(Side.BUY, qty=10, price=100.0, agent_id=7)
    trades = match(book, taker, stp="cancel_resting")
    assert trades == []
    assert book.best_ask is None
    assert book.best_bid == 100.0            # taker rests after own quote pulled


def test_stp_rejects_unknown_policy():
    book = OrderBook()
    with pytest.raises(ValueError):
        match(book, Order(Side.BUY, qty=1, price=1.0), stp="decrement")
