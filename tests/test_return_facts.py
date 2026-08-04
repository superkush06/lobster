"""Unit tests for the return-distribution diagnostics."""

from __future__ import annotations

import math
import random

import pytest

from lobster.stylized import (
    ReturnFacts,
    aggregate,
    excess_kurtosis,
    hill_tail_index,
    log_returns,
)


def test_log_returns_are_log_price_differences():
    prices = [100.0, 101.0, 99.5]
    r = log_returns(prices)
    assert r == pytest.approx([math.log(101.0 / 100.0), math.log(99.5 / 101.0)])


def test_log_returns_skip_non_positive_prices():
    assert log_returns([100.0, 0.0, 100.0]) == []
    assert log_returns([]) == []
    assert log_returns([100.0]) == []


def test_aggregate_rejects_a_non_positive_block():
    with pytest.raises(ValueError):
        aggregate([1.0, 2.0], 0)


def test_excess_kurtosis_needs_four_points_and_some_variance():
    assert excess_kurtosis([1.0, 2.0, 3.0]) is None
    assert excess_kurtosis([2.0] * 50) is None
    assert excess_kurtosis([1.0, 2.0, 3.0, 4.0]) is not None


def test_hill_tail_index_needs_a_populated_tail():
    rng = random.Random(5)
    small = [rng.random() for _ in range(100)]
    assert hill_tail_index(small, tail_frac=0.05) is None   # only 5 in the tail
    assert hill_tail_index([0.0] * 5000) is None
    with pytest.raises(ValueError):
        hill_tail_index([1.0, 2.0], tail_frac=1.5)


def test_return_facts_reports_every_field():
    rng = random.Random(11)
    returns = [rng.gauss(0.0, 0.01) for _ in range(5000)]
    rf = ReturnFacts.measure(returns, max_lag=20, aggregation=(1, 10))
    assert rf.n == 5000
    assert len(rf.ret_acf) == 20
    assert len(rf.abs_ret_acf) == 20
    assert set(rf.aggregated_kurtosis) == {1, 10}
    assert rf.excess_kurtosis == pytest.approx(0.0, abs=0.25)
    # iid returns: no clustering to find, so the mean |r| autocorrelation
    # should sit inside the +-2/sqrt(N) noise band around zero.
    assert abs(rf.clustering) < 2.0 / math.sqrt(rf.n)


def test_return_facts_finds_clustering_when_it_is_there():
    """A two-state volatility switch has to show up in the |r| autocorrelation."""
    rng = random.Random(12)
    returns, vol = [], 0.005
    for _ in range(20_000):
        if rng.random() < 0.002:
            vol = 0.02 if vol == 0.005 else 0.005
        returns.append(rng.gauss(0.0, vol))
    rf = ReturnFacts.measure(returns, max_lag=50)
    band = 2.0 / math.sqrt(rf.n)
    assert rf.abs_ret_acf[0] > band
    assert rf.abs_ret_acf[49] > band
    assert abs(rf.ret_acf[0]) < band * 3
    assert rf.excess_kurtosis > 0.0
