import pytest

from lobster.book import OrderBook, PriceLevel
from lobster.order import Order, Side


def test_empty_book():
    b = OrderBook()
    assert b.best_bid is None
    assert b.best_ask is None
    assert b.mid is None
    assert b.spread is None
    assert len(b) == 0


def test_add_bid_ask():
    b = OrderBook()
    b.add(Order(Side.BUY, qty=10, price=99.5))
    b.add(Order(Side.SELL, qty=10, price=100.5))
    assert b.best_bid == 99.5
    assert b.best_ask == 100.5
    assert b.mid == 100.0
    assert b.spread == 1.0


def test_better_bid_replaces_top():
    b = OrderBook()
    b.add(Order(Side.BUY, qty=10, price=99.0))
    b.add(Order(Side.BUY, qty=5,  price=99.5))
    assert b.best_bid == 99.5


def test_cancel_removes_top():
    b = OrderBook()
    o1 = Order(Side.BUY, qty=10, price=99.0)
    o2 = Order(Side.BUY, qty=5,  price=99.5)
    b.add(o1); b.add(o2)
    cancelled = b.cancel(o2.id)
    assert cancelled is not None
    assert b.best_bid == 99.0


def test_cancel_unknown_returns_none():
    b = OrderBook()
    assert b.cancel(99999) is None


def test_depth_top_k():
    b = OrderBook()
    for p in (99.0, 99.5, 100.0):
        b.add(Order(Side.BUY, qty=10, price=p))
    d = b.depth(Side.BUY, levels=3)
    # Descending: best bid first
    assert d == [(100.0, 10), (99.5, 10), (99.0, 10)]


def test_snapshot_shape():
    b = OrderBook()
    b.add(Order(Side.BUY, qty=10, price=99.0))
    b.add(Order(Side.SELL, qty=10, price=101.0))
    snap = b.snapshot()
    assert set(snap) == {"bids", "asks", "mid", "spread", "microprice"}
    assert snap["mid"] == 100.0


def test_microprice_skews_to_thin_side():
    b = OrderBook()
    b.add(Order(Side.BUY, qty=1, price=99.0))
    b.add(Order(Side.SELL, qty=100, price=101.0))
    # Heavy ask should pull microprice toward the bid
    assert b.microprice is not None
    assert b.microprice < b.mid


def test_fifo_within_level():
    b = OrderBook()
    o1 = Order(Side.BUY, qty=10, price=100.0)
    o2 = Order(Side.BUY, qty=5,  price=100.0)
    b.add(o1); b.add(o2)
    # o1 arrived first, should be at front of queue
    level = next(b.iter_levels(Side.BUY))
    assert level.orders[0].id == o1.id


def test_price_level_rejects_mismatched_price():
    level = PriceLevel(price=100.0)
    with pytest.raises(ValueError):
        level.add(Order(Side.BUY, qty=10, price=101.0))


def test_price_level_reduce_partial_and_full():
    level = PriceLevel(price=100.0)
    o = Order(Side.BUY, qty=10, price=100.0)
    level.add(o)
    # partial reduction
    removed = level.reduce(o.id, 4)
    assert removed == 4
    assert o.qty == 6
    assert level.total_qty == 6
    # full reduction removes the order from the queue
    removed = level.reduce(o.id, 99)
    assert removed == 6
    assert len(level) == 0


def test_price_level_reduce_unknown_id_is_noop():
    level = PriceLevel(price=100.0)
    level.add(Order(Side.BUY, qty=10, price=100.0))
    assert level.reduce(order_id=999, qty=5) == 0
    assert level.total_qty == 10
