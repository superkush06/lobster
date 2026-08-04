from lobster.order import Side
from lobster.tape import Tape, Trade


def _t(p, q, ts=0.0, agg=Side.BUY) -> Trade:
    return Trade(price=p, qty=q, buyer_id=1, seller_id=2, ts=ts, aggressor=agg)


def test_tape_records():
    tape = Tape()
    tape.record(_t(100.0, 10))
    tape.record(_t(101.0, 5))
    assert len(tape) == 2


def test_recent_returns_tail():
    tape = Tape()
    for p in range(10):
        tape.record(_t(100.0 + p, 1))
    r = tape.recent(3)
    assert len(r) == 3
    assert r[-1].price == 109.0


def test_vwap():
    tape = Tape()
    tape.record(_t(100.0, 10))
    tape.record(_t(102.0, 10))
    # vwap = (100*10 + 102*10) / 20 = 101.0
    assert tape.vwap() == 101.0


def test_bounded_buffer():
    tape = Tape(maxlen=5)
    for p in range(10):
        tape.record(_t(100.0 + p, 1))
    assert len(tape) == 5
    assert list(tape)[0].price == 105.0  # oldest 5 dropped


def test_default_tape_is_unbounded():
    """Long runs (README demo already logs >5k trades in 5k steps) must not
    silently window markout/imbalance: the default tape keeps everything."""
    tape = Tape()
    for i in range(12_000):
        tape.record(_t(100.0, 1, ts=float(i)))
    assert len(tape) == 12_000
    assert not tape.truncated
    assert tape.evicted == 0


def test_bounded_tape_reports_truncation():
    tape = Tape(maxlen=5)
    for i in range(8):
        tape.record(_t(100.0 + i, 1))
    assert len(tape) == 5
    assert tape.truncated
    assert tape.evicted == 3
