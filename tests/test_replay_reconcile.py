"""The reconciliation path a real capture forces: events against orders the
snapshot could not name.

`OrderBook.from_snapshot` seeds depth as synthetic orders with fresh ids, so
every cancel or execution aimed at a pre-window order arrives with an id the
book has never held. These tests pin what `on_unknown="reduce_level"` does
about that — and, as important, what it refuses to invent when the level the
event names is short or missing. The fixture stream is synthetic on purpose:
it manufactures the exact three situations a cold-start LOBSTER replay
produces (pre-window id, short level, absent level) in eight messages instead
of four hundred thousand, so the assertions can be exact.
"""

import os
import pathlib
import subprocess
import sys

import pytest

from lobster.book import OrderBook
from lobster.order import Order, Side
from lobster.replay import (
    DELETE,
    EXECUTE_VISIBLE,
    NEW,
    PARTIAL_CANCEL,
    Message,
    ReplayStats,
    UnknownOrderError,
    apply_message,
    replay,
)


def msg(event_type, order_id, size, price, direction, time=1.0):
    return Message(time=time, event_type=event_type, order_id=order_id,
                   size=size, price=price, direction=direction)


def seeded_book():
    """Two levels a side, as a snapshot seed would build them."""
    return OrderBook.from_snapshot(
        bids=[(99.0, 300), (98.0, 200)],
        asks=[(101.0, 250), (102.0, 400)],
    )


# ---- reduce_at, the primitive underneath the policy -------------------------

def test_reduce_at_takes_from_the_front_of_the_queue():
    book = OrderBook()
    book.add(Order(side=Side.BUY, qty=100, price=99.0, agent_id=0, id=1, ts=0.0))
    book.add(Order(side=Side.BUY, qty=50, price=99.0, agent_id=0, id=2, ts=1.0))
    assert book.reduce_at(Side.BUY, 99.0, 120) == 120
    # order 1 (100 shares) drained and evicted; order 2 reduced to 30
    assert book.cancel(1) is None
    assert book.depth(Side.BUY, 1) == [(99.0, 30)]
    remaining = book.cancel(2)
    assert remaining is not None and remaining.qty == 30


def test_reduce_at_reports_the_shortfall_instead_of_inventing_depth():
    book = seeded_book()
    assert book.reduce_at(Side.SELL, 101.0, 400) == 250   # level held only 250
    assert book.reduce_at(Side.SELL, 101.0, 10) == 0      # level now pruned
    assert book.reduce_at(Side.SELL, 103.5, 10) == 0      # level never existed
    assert book.best_ask == 102.0


def test_reduce_at_prunes_an_emptied_level_and_its_index_entries():
    book = OrderBook()
    book.add(Order(side=Side.SELL, qty=60, price=101.0, agent_id=0, id=7, ts=0.0))
    assert book.reduce_at(Side.SELL, 101.0, 60) == 60
    assert book.best_ask is None
    assert len(book) == 0            # id 7 left the index with its shares
    assert book.cancel(7) is None


# ---- the policy itself ------------------------------------------------------

def test_unknown_exec_lands_on_the_level_the_snapshot_vouched_for():
    book = seeded_book()
    stats = ReplayStats()
    apply_message(book, msg(EXECUTE_VISIBLE, order_id=999_999, size=100,
                            price=101.0, direction=-1),
                  stats=stats, on_unknown="reduce_level")
    assert stats.unknown_execs == 1
    assert stats.level_reduced == 1
    assert stats.unresolvable == 0
    assert book.depth(Side.SELL, 1) == [(101.0, 150)]


def test_shortfall_is_counted_unresolvable_not_papered_over():
    book = seeded_book()
    stats = ReplayStats()
    # 300 shares deleted at a level holding 200: partial landing, honest count.
    apply_message(book, msg(DELETE, order_id=999_998, size=300,
                            price=98.0, direction=1),
                  stats=stats, on_unknown="reduce_level")
    assert stats.unknown_deletes == 1
    assert stats.level_reduced == 0
    assert stats.unresolvable == 1
    assert book.depth(Side.BUY, 2) == [(99.0, 300)]   # 98.0 fully drained, pruned


def test_absent_level_is_unresolvable_and_leaves_the_book_alone():
    book = seeded_book()
    stats = ReplayStats()
    before = book.snapshot(5)
    apply_message(book, msg(PARTIAL_CANCEL, order_id=999_997, size=10,
                            price=97.25, direction=1),
                  stats=stats, on_unknown="reduce_level")
    assert stats.unknown_cancels == 1
    assert stats.unresolvable == 1
    assert book.snapshot(5) == before


def test_default_policy_is_unchanged_count_only():
    book = seeded_book()
    stats = ReplayStats()
    apply_message(book, msg(EXECUTE_VISIBLE, order_id=999_996, size=100,
                            price=101.0, direction=-1),
                  stats=stats)
    assert stats.unknown_execs == 1
    assert stats.level_reduced == 0
    assert book.depth(Side.SELL, 1) == [(101.0, 250)]   # untouched


def test_raise_policy_and_strict_both_raise():
    for kwargs in ({"on_unknown": "raise"}, {"strict": True}):
        book = seeded_book()
        with pytest.raises(UnknownOrderError):
            apply_message(book, msg(DELETE, order_id=999_995, size=10,
                                    price=99.0, direction=1), **kwargs)


def test_bogus_policy_name_is_refused():
    with pytest.raises(ValueError):
        apply_message(seeded_book(), msg(NEW, order_id=1, size=10,
                                         price=99.5, direction=1),
                      on_unknown="guess")


def test_known_ids_never_touch_the_reconciliation_path():
    book = seeded_book()
    stats = ReplayStats()
    book.add(Order(side=Side.BUY, qty=80, price=99.0, agent_id=0, id=42, ts=2.0))
    apply_message(book, msg(EXECUTE_VISIBLE, order_id=42, size=30,
                            price=99.0, direction=1),
                  stats=stats, on_unknown="reduce_level")
    assert stats.applied == 1
    assert stats.unknown_total == 0
    assert stats.level_reduced == 0
    # 300 snapshot shares untouched in front of order 42's remaining 50
    assert book.depth(Side.BUY, 1) == [(99.0, 350)]


# ---- a miniature cold-start day --------------------------------------------

def test_eight_message_cold_start_reconciles_to_the_expected_book():
    """Pre-window flow interleaved with fresh flow, every count accounted for."""
    book = seeded_book()
    stats = ReplayStats()
    stream = [
        msg(NEW, order_id=10, size=100, price=100.0, direction=1, time=1.0),
        msg(EXECUTE_VISIBLE, order_id=900_001, size=50, price=101.0,
            direction=-1, time=2.0),                          # pre-window ask
        msg(NEW, order_id=11, size=75, price=101.5, direction=-1, time=3.0),
        msg(PARTIAL_CANCEL, order_id=900_002, size=100, price=99.0,
            direction=1, time=4.0),                           # pre-window bid
        msg(EXECUTE_VISIBLE, order_id=10, size=40, price=100.0,
            direction=1, time=5.0),                           # known, by id
        msg(DELETE, order_id=900_003, size=200, price=98.0,
            direction=1, time=6.0),                           # drains a level
        msg(DELETE, order_id=900_004, size=10, price=97.0,
            direction=1, time=7.0),                           # level never seeded
        msg(NEW, order_id=12, size=25, price=99.0, direction=1, time=8.0),
    ]
    replay(stream, book, stats=stats, on_unknown="reduce_level")

    assert stats.applied == 4                     # 3 NEW + 1 known execution
    assert stats.unknown_total == 4
    assert stats.level_reduced == 3
    assert stats.unresolvable == 1
    assert book.depth(Side.BUY, 3) == [(100.0, 60), (99.0, 225)]
    assert book.depth(Side.SELL, 3) == [(101.0, 200), (101.5, 75), (102.0, 400)]


# ---- the real day, when the data is present ---------------------------------

REAL_MESSAGES = pathlib.Path(__file__).resolve().parents[1] / "data" / "real" / \
    "AAPL_2012-06-21_34200000_57600000_message_10.csv"


@pytest.mark.skipif(not REAL_MESSAGES.exists(),
                    reason="real LOBSTER sample not fetched "
                           "(python tools/fetch_lobster_sample.py)")
def test_the_real_day_numbers_are_the_ones_documented():
    """Rerun the whole AAPL 2012-06-21 reconciliation and diff the headline
    numbers against the ones docs/real_replay.md and the README quote.

    Everything in the pipeline is deterministic - no RNG, no wall-clock in
    the metrics - so these are exact string pins, same policy as
    test_readme_examples.py. Runtime is ~10 s, which is why it only runs
    where the (gitignored) data actually is.
    """
    proc = subprocess.run(
        [sys.executable, "examples/replay_real_day.py"],
        cwd=REAL_MESSAGES.parents[2], capture_output=True, text=True, timeout=600,
        env={**os.environ, "PYTHONPATH": str(REAL_MESSAGES.parents[2])},
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    for line in (
        "top-of-book exact         100.00% of rows",
        "top-5 book exact          100.00% of rows",
        "full level-10 window     73.88% of rows",
        "depth error               0.00% of shares",
        "applied by order id       372,074",
        "pre-window unknowns       8,381",
        "reappeared unknowns       8,603",
        "  reconciled by level     16,984",
        "  unresolvable            0",
        "hidden executions         11,332",
        "band promotions imported  104,562 levels / 19,829,292 shares",
        "band demotions pruned     106,380 levels / 19,668,918 shares",
    ):
        assert line in out, f"expected {line!r} in the real-day table\n{out}"


def test_a_negative_reduction_is_refused_not_applied_in_reverse():
    """min(qty, o.qty) with qty < 0 would grow the order; the guard says no.

    A replay feeds `reduce` sizes parsed straight from a CSV, so one corrupt
    row must not quietly inflate resting depth. Zero is refused too: there
    is nothing to reduce by.
    """
    book = OrderBook()
    book.add(Order(side=Side.BUY, qty=100, price=99.0, agent_id=0, id=1, ts=0.0))
    assert book.reduce(1, -50) == 0
    assert book.reduce(1, 0) == 0
    assert book.reduce_at(Side.BUY, 99.0, -50) == 0
    assert book.depth(Side.BUY, 1) == [(99.0, 100)]
    assert book.reduce(1, 30) == 30
    assert book.depth(Side.BUY, 1) == [(99.0, 70)]
