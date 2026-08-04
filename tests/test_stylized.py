"""Stylized-facts estimators, and the facts the default sim must show.

The estimator tests use fixtures with an analytically known answer (a pure
Roll bounce, an exact power law, a hand-built book) so a regression points
at the estimator rather than at the simulator. The last two tests are the
behavioural ones: they pin the qualitative claims the README makes.
"""

from __future__ import annotations

import math
import random

import pytest

from lobster import Order, OrderBook, Side, Simulation, Tape, Trade
from lobster.agents import MarketMakerAgent, MomentumAgent, NoiseAgent
from lobster.stylized import (
    StylizedFacts,
    autocorrelation,
    bin_centers,
    decay_exponent,
    depth_profile,
    mean_depth_profile,
    trade_signs,
    variance_ratio,
)

BIN, MAXD = 0.05, 1.5


# ---- sequences ------------------------------------------------------------

def test_trade_signs_follow_the_aggressor():
    tape = [
        Trade(price=100.0, qty=1, buyer_id=1, seller_id=2, ts=0.0,
              aggressor=Side.BUY),
        Trade(price=100.0, qty=1, buyer_id=1, seller_id=2, ts=1.0,
              aggressor=Side.SELL),
    ]
    assert trade_signs(tape) == [1, -1]


# ---- autocorrelation ------------------------------------------------------

def test_alternating_series_flips_sign_every_lag():
    x = [1.0, -1.0] * 200
    acf = autocorrelation(x, max_lag=4)
    assert acf[0] == pytest.approx(-1.0, abs=0.01)
    assert acf[1] == pytest.approx(1.0, abs=0.01)
    assert acf[2] == pytest.approx(-1.0, abs=0.01)


def test_degenerate_series_give_no_autocorrelation():
    assert autocorrelation([5.0] * 50, max_lag=3) == []   # constant
    assert autocorrelation([1.0], max_lag=3) == []        # too short
    assert autocorrelation([1.0, 2.0, 3.0], max_lag=0) == []


def test_autocorrelation_stops_at_the_available_lags():
    assert len(autocorrelation([1.0, 2.0, 3.0, 4.0], max_lag=99)) == 3


def test_decay_exponent_recovers_a_planted_power_law():
    gamma = 0.62
    acf = [0.2 * (lag ** -gamma) for lag in range(1, 40)]
    assert decay_exponent(acf) == pytest.approx(gamma, abs=1e-9)


def test_decay_exponent_needs_three_positive_lags():
    assert decay_exponent([0.1, -0.2, 0.05]) is None
    assert decay_exponent([]) is None


# ---- variance ratio -------------------------------------------------------

def test_random_walk_has_unit_variance_ratio():
    rng = random.Random(4)
    p, walk = 100.0, [100.0]
    for _ in range(20_000):
        p += rng.gauss(0.0, 0.01)
        walk.append(p)
    for q in (2, 5, 20):
        assert variance_ratio(walk, q) == pytest.approx(1.0, abs=0.1)


def test_pure_roll_bounce_halves_the_two_step_variance_ratio():
    """p_t = m + (s/2) * q_t with m fixed and q_t iid +-1.

    Then Var(d_1 p) = s^2/2 and Var(d_2 p) = s^2/2, so VR(2) -> 1/2 and
    the lag-1 autocorrelation of price changes -> -1/2 exactly.
    """
    rng = random.Random(9)
    half_spread = 0.01
    prices = [100.0 + half_spread * rng.choice((-1, 1)) for _ in range(40_000)]
    assert variance_ratio(prices, 2) == pytest.approx(0.5, abs=0.02)
    dp = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    assert autocorrelation(dp, 1)[0] == pytest.approx(-0.5, abs=0.02)


def test_variance_ratio_rejects_impossible_horizons():
    with pytest.raises(ValueError):
        variance_ratio([1.0, 2.0, 3.0], 0)
    with pytest.raises(ValueError):
        variance_ratio([1.0, 2.0, 3.0], 5)
    with pytest.raises(ValueError):
        variance_ratio([1.0] * 20, 2)  # no variance to normalise by


# ---- depth profile --------------------------------------------------------

def _two_sided_book() -> OrderBook:
    book = OrderBook()
    book.add(Order(Side.BUY, qty=10, price=99.5))
    book.add(Order(Side.BUY, qty=20, price=99.0))
    book.add(Order(Side.SELL, qty=30, price=100.5))
    book.add(Order(Side.SELL, qty=5, price=101.0))
    return book


def test_depth_profile_bins_both_sides_by_distance_from_the_mid():
    book = _two_sided_book()
    assert book.mid == 100.0
    # distances 0.5, 1.0 on each side -> bins 2 and 4 at width 0.25
    assert depth_profile(book, bin_width=0.25, max_distance=1.25) == [
        0.0, 0.0, 40.0, 0.0, 25.0,
    ]


def test_depth_profile_drops_levels_beyond_max_distance():
    book = _two_sided_book()
    assert sum(depth_profile(book, bin_width=0.25, max_distance=0.75)) == 40.0


def test_depth_profile_of_a_one_sided_book_is_all_zeros():
    book = OrderBook()
    book.add(Order(Side.BUY, qty=10, price=99.5))
    assert depth_profile(book, 0.25, 1.0) == [0.0] * 4


def test_depth_profile_rejects_nonsense_bins():
    with pytest.raises(ValueError):
        depth_profile(OrderBook(), bin_width=0.0, max_distance=1.0)


def test_mean_depth_profile_averages_elementwise():
    assert mean_depth_profile([[1.0, 3.0], [3.0, 5.0]]) == [2.0, 4.0]
    assert mean_depth_profile([]) == []
    with pytest.raises(ValueError):
        mean_depth_profile([[1.0], [1.0, 2.0]])


def test_bin_centers_sit_in_the_middle_of_each_bin():
    assert bin_centers(0.5, 3) == [0.25, 0.75, 1.25]


# ---- the facts the simulator is claimed to reproduce ----------------------

def _measure(steps: int, *, momentum: bool, seed: int = 7) -> StylizedFacts:
    agents = [
        NoiseAgent(agent_id=1, intensity=0.6, spread_offset=0.6, qty=8,
                   market_order_rate=0.25),
        NoiseAgent(agent_id=2, intensity=0.5, spread_offset=0.6, qty=8,
                   market_order_rate=0.25),
    ]
    if momentum:
        agents.append(MomentumAgent(agent_id=3, lookback=20, threshold=0.5,
                                    qty=5, max_position=100))
    agents.append(MarketMakerAgent(agent_id=4, half_spread=0.4, qty=12,
                                   inv_skew=0.02))
    sim = Simulation(agents=agents, seed=seed)
    profiles = []
    for k, m in enumerate(sim.run(steps)):
        if k % 10 == 0 and m.mid is not None:
            profiles.append(depth_profile(sim.book, BIN, MAXD))
    mids = [m.mid for m in sim.metrics if m.mid is not None]
    return StylizedFacts.measure(sim.tape, mids, profiles, max_lag=64,
                                 vr_qs=(1, 2, 5, 10, 20, 50),
                                 depth_bin_width=BIN)


def test_the_tape_bounces_and_the_book_is_humped():
    """Two facts the default configuration does reproduce."""
    sf = _measure(20_000, momentum=True)
    # bid-ask bounce: trade-price changes flip sign, bounded below by Roll's -1/2
    assert -0.5 <= sf.bounce < -0.15
    # the queue is thinnest at the touch and peaks a few ticks out
    assert sf.depth[0] < 0.1 * max(sf.depth)
    assert 0.2 <= sf.depth_peak <= 0.7


def test_the_trend_chaser_is_what_breaks_the_martingale():
    """The fact the default configuration does *not* reproduce, and why."""
    with_chaser = _measure(20_000, momentum=True)
    without = _measure(20_000, momentum=False)
    q50 = with_chaser.vr_qs.index(50)
    # mid super-diffuses when a momentum agent trades its own footprint...
    assert with_chaser.vr_mid[q50] > 2.5
    # ...and sits close to a random walk when it does not.
    assert without.vr_mid[q50] < 2.5
    # meanwhile the bounce survives either way
    assert without.bounce < -0.15
    # and only the chaser leaves a footprint in the order-flow signs
    assert with_chaser.memory_horizon() > without.memory_horizon()


def test_memory_horizon_is_zero_for_coin_flip_flow():
    rng = random.Random(1)
    tape = Tape()
    for i in range(5_000):
        side = Side.BUY if rng.random() < 0.5 else Side.SELL
        tape.record(Trade(price=100.0 + rng.gauss(0, 0.01), qty=1, buyer_id=1,
                          seller_id=2, ts=float(i), aggressor=side))
    sf = StylizedFacts.measure(tape, [100.0 + 0.01 * i for i in range(200)],
                               [], max_lag=64, vr_qs=(1, 2, 5))
    assert sf.memory_horizon() == 0
    assert sf.memory_horizon(window=0) == 0


def test_summary_reports_every_headline_number():
    sf = _measure(3_000, momentum=True)
    s = sf.summary()
    assert set(s) == {
        "n_trades", "bounce_acf1", "sign_acf1", "flow_memory_gamma",
        "memory_horizon", "vr_trades_10", "vr_mid_10", "vr_mid_100",
        "depth_peak_distance",
    }
    assert s["n_trades"] == float(sf.n_trades)
    assert s["vr_mid_100"] is None  # not among the horizons measured here
    assert math.isfinite(s["bounce_acf1"])


def test_measure_survives_an_empty_tape():
    sf = StylizedFacts.measure(Tape(), [100.0, 100.5, 101.0, 100.0, 99.0],
                               [[1.0, 2.0]], vr_qs=(1, 2))
    assert sf.n_trades == 0
    assert sf.sign_acf == []
    assert sf.bounce == 0.0
    assert sf.flow_memory is None
    assert sf.depth == [1.0, 2.0]
