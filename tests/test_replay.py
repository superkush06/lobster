"""LOBSTER message-replay tests."""

import pathlib

import pytest

from lobster.book import OrderBook
from lobster.order import Side
from lobster.replay import (
    Message,
    apply_message,
    parse_lobster_line,
    replay,
    replay_csv,
)

SAMPLE = pathlib.Path(__file__).resolve().parents[1] / "data" / "sample_messages.csv"


def test_parse_lobster_line():
    msg = parse_lobster_line("34200.001, 1, 7, 100, 995000, 1", price_scale=1e-4)
    assert msg.time == pytest.approx(34200.001)
    assert msg.event_type == 1
    assert msg.order_id == 7
    assert msg.size == 100
    assert msg.price == pytest.approx(99.5)
    assert msg.side is Side.BUY


def test_parse_rejects_short_row():
    with pytest.raises(ValueError):
        parse_lobster_line("1,2,3")


def test_new_order_rests_on_book():
    book = OrderBook()
    apply_message(book, Message(0.0, 1, 1, 100, 99.5, 1))
    assert book.best_bid == 99.5
    assert len(book) == 1


def test_partial_cancel_reduces_size():
    book = OrderBook()
    apply_message(book, Message(0.0, 1, 1, 100, 99.5, 1))
    apply_message(book, Message(1.0, 2, 1, 40, 99.5, 1))  # cancel 40
    assert book.depth(Side.BUY)[0] == (99.5, 60)


def test_execution_reduces_resting_order():
    book = OrderBook()
    apply_message(book, Message(0.0, 1, 2, 50, 100.5, -1))
    apply_message(book, Message(1.0, 4, 2, 30, 100.5, -1))  # execute 30
    assert book.depth(Side.SELL)[0] == (100.5, 20)


def test_delete_removes_order():
    book = OrderBook()
    apply_message(book, Message(0.0, 1, 3, 200, 99.0, 1))
    apply_message(book, Message(1.0, 3, 3, 200, 99.0, 1))  # delete
    assert book.best_bid is None
    assert len(book) == 0


def test_hidden_execution_leaves_book_unchanged():
    book = OrderBook()
    apply_message(book, Message(0.0, 1, 1, 100, 99.5, 1))
    apply_message(book, Message(1.0, 5, 999, 10, 99.5, 1))  # hidden exec
    assert book.depth(Side.BUY)[0] == (99.5, 100)


def test_replay_reconstructs_full_book_from_csv():
    book = replay_csv(str(SAMPLE), price_scale=1e-4)
    # order 1: 100-40=60 @ 99.50 (buy);  order 4: 80 @ 100.00 (sell)
    # order 2: 50-30=20 @ 100.50 (sell); order 3 deleted
    assert book.best_bid == 99.5
    assert book.best_ask == 100.0
    assert book.mid == pytest.approx(99.75)
    assert book.spread == pytest.approx(0.5)
    assert book.depth(Side.BUY)[0] == (99.5, 60)
    assert dict(book.depth(Side.SELL)) == {100.0: 80, 100.5: 20}


def test_replay_list_matches_csv():
    msgs = [
        Message(0.0, 1, 1, 100, 99.5, 1),
        Message(1.0, 1, 2, 50, 100.5, -1),
        Message(2.0, 4, 1, 40, 99.5, 1),
    ]
    book = replay(msgs)
    assert book.depth(Side.BUY)[0] == (99.5, 60)
    assert book.best_ask == 100.5
