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


# ---- snapshot bootstrap -------------------------------------------------------


def test_from_snapshot_seeds_depth():
    book = OrderBook.from_snapshot(
        bids=[(99.5, 300), (99.4, 120)],
        asks=[(100.0, 250), (100.2, 80)],
    )
    assert book.best_bid == 99.5
    assert book.best_ask == 100.0
    assert book.depth(Side.BUY, 2) == [(99.5, 300), (99.4, 120)]
    assert book.depth(Side.SELL, 2) == [(100.0, 250), (100.2, 80)]
    assert len(book) == 4


def test_from_snapshot_skips_padded_empty_levels():
    # LOBSTER pads missing levels with qty 0 dummy rows; those must not rest.
    book = OrderBook.from_snapshot(bids=[(99.5, 100), (0.0, 0)],
                                   asks=[(-9999999999.0, 0)])
    assert len(book) == 1
    assert book.best_ask is None


def test_from_snapshot_then_replay_applies_new_flow():
    from lobster.replay import Message, apply_message

    book = OrderBook.from_snapshot(bids=[(99.5, 100)], asks=[(100.5, 50)])
    apply_message(book, Message(1.0, 1, 42, 30, 100.0, -1))  # new ask inside
    assert book.best_ask == 100.0
    assert book.best_bid == 99.5


# ---- crossed-book guard -------------------------------------------------------


def test_add_rejects_bid_crossing_best_ask():
    b = OrderBook()
    b.add(Order(Side.SELL, qty=10, price=100.0))
    with pytest.raises(ValueError, match="crosses best ask"):
        b.add(Order(Side.BUY, qty=10, price=105.0))
    assert b.spread is None or b.spread >= 0


def test_add_rejects_ask_crossing_best_bid():
    b = OrderBook()
    b.add(Order(Side.BUY, qty=10, price=100.0))
    with pytest.raises(ValueError, match="crosses best bid"):
        b.add(Order(Side.SELL, qty=10, price=95.0))


def test_add_rejects_locked_book_too():
    b = OrderBook()
    b.add(Order(Side.SELL, qty=10, price=100.0))
    with pytest.raises(ValueError):
        b.add(Order(Side.BUY, qty=10, price=100.0))  # locked = crossed here


def test_add_allow_crossed_optin_for_replays():
    b = OrderBook()
    b.add(Order(Side.SELL, qty=10, price=100.0))
    b.add(Order(Side.BUY, qty=10, price=105.0), allow_crossed=True)
    assert b.spread == -5.0  # deliberate: caller opted in


def test_a_reused_order_id_is_refused_rather_than_orphaning_the_first():
    """Two resting orders sharing an id used to leave one unreachable.

    The id is how cancel, reduce and queue position find an order. The second
    add overwrote the index entry, and the first order stayed on its level
    with nothing able to reach it, so `len(book)` reported one order where two
    were resting and the book quietly disagreed with itself.
    """
    book = OrderBook()
    book.add(Order(Side.BUY, qty=100, price=99.5, id=7))
    with pytest.raises(ValueError, match="already resting"):
        book.add(Order(Side.BUY, qty=50, price=99.4, id=7))
    assert len(book) == 1
    # the id frees up once the order leaves
    book.cancel(7)
    book.add(Order(Side.BUY, qty=50, price=99.4, id=7))
    assert len(book) == 1
