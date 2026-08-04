"""Randomized property tests for the statistics.

`lobster.stylized` and `lobster.execution` exist to put numbers on a
simulation, so the first question about them is whether they return the right
number when the right number is known. Each test feeds a process with a
closed-form answer — Roll's model, a Pareto tail, an exact power law, a
Laplace distribution — and checks the estimator recovers it, or asserts an
algebraic identity that has to hold for any input at all.

Seeds are fixed. Tolerances are sized to the Monte Carlo error of the sample
they are computed on, not tightened until they pass.
"""

from __future__ import annotations

import math
import random

import pytest

from lobster import LinearImpact, SquareRootImpact
from lobster.execution import fit_power_law
from lobster.latency import ConstantLatency, JitteredLatency
from lobster.stylized import (
    aggregate,
    autocorrelation,
    decay_exponent,
    excess_kurtosis,
    hill_tail_index,
    variance_ratio,
)


def random_series(rng: random.Random, n: int) -> list[float]:
    return [rng.gauss(0.0, rng.uniform(0.5, 3.0)) for _ in range(n)]


# ---- algebraic identities -------------------------------------------------

def test_autocorrelation_is_bounded_and_affine_invariant():
    """|rho(l)| <= 1, and rho is unchanged by x -> a*x + b for a != 0.

    Correlation is scale- and location-free by construction. If it is not,
    the estimator is dividing by the wrong normalisation and every decay
    exponent fitted from it inherits the error.
    """
    rng = random.Random(2001)
    for _ in range(200):
        x = random_series(rng, rng.randint(50, 400))
        a = rng.uniform(-4.0, 4.0)
        while abs(a) < 0.1:
            a = rng.uniform(-4.0, 4.0)
        b = rng.uniform(-100.0, 100.0)
        base = autocorrelation(x, 10)
        moved = autocorrelation([a * v + b for v in x], 10)
        assert all(abs(r) <= 1.0 + 1e-12 for r in base)
        assert len(base) == len(moved)
        for r0, r1 in zip(base, moved, strict=True):
            assert r0 == pytest.approx(r1, abs=1e-9)


def test_variance_ratio_at_one_is_exactly_one_and_is_scale_free():
    """VR(1) == 1 for any price series, and VR(q) ignores an affine rescale.

    VR(1) is a ratio of a quantity to itself; anything other than 1.0 means
    the numerator and denominator are not the same estimator. Scale freedom
    matters because prices and log prices are compared on the same axis.
    """
    rng = random.Random(2002)
    for _ in range(200):
        prices = [100.0]
        for _ in range(rng.randint(60, 400)):
            prices.append(prices[-1] + rng.gauss(0.0, 0.5))
        assert variance_ratio(prices, 1) == 1.0
        a, b = rng.uniform(0.2, 5.0), rng.uniform(-50.0, 50.0)
        scaled = [a * p + b for p in prices]
        for q in (2, 5, 10):
            if len(prices) > q + 1:
                assert variance_ratio(prices, q) == pytest.approx(
                    variance_ratio(scaled, q), rel=1e-9)


def test_variance_ratio_matches_the_autocorrelation_identity():
    """VR(q) = 1 + 2 * sum_k (1 - k/q) rho_k over the one-step changes.

    The identity is exact in population and holds in sample up to end
    effects, so it is the cheapest independent check that the overlapping
    variance-ratio estimator is assembling the right sums.
    """
    rng = random.Random(2003)
    for _ in range(40):
        prices = [100.0]
        for _ in range(8000):
            prices.append(prices[-1] + rng.gauss(0.0, 1.0)
                          - 0.4 * (prices[-1] - 100.0) * 0.01)
        diffs = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        for q in (2, 5, 10):
            rho = autocorrelation(diffs, q - 1)
            identity = 1.0 + 2.0 * sum((1 - (k + 1) / q) * rho[k]
                                       for k in range(q - 1))
            assert variance_ratio(prices, q) == pytest.approx(identity, abs=0.02)


def test_aggregate_partitions_the_series():
    """Aggregated blocks sum to the total of the values they cover.

    Return aggregation must not drop or double-count observations; the only
    values allowed to go missing are the ragged tail past the last full block.
    """
    rng = random.Random(2004)
    for _ in range(200):
        x = random_series(rng, rng.randint(20, 300))
        k = rng.randint(1, 12)
        blocks = aggregate(x, k)
        assert len(blocks) == len(x) // k
        assert sum(blocks) == pytest.approx(sum(x[:len(blocks) * k]), abs=1e-9)


def test_fit_power_law_inverts_an_exact_power_law():
    """A noiseless y = k x^d is recovered with both parameters exact.

    Every impact exponent this package reports comes out of this fit, so it
    is worth knowing it is exact before trusting it on noisy data.
    """
    rng = random.Random(2005)
    for _ in range(200):
        k, d = rng.uniform(0.01, 10.0), rng.uniform(-2.0, 2.0)
        xs = [1.5 ** i for i in range(1, 12)]
        ys = [k * x ** d for x in xs]
        fit = fit_power_law(xs, ys)
        assert fit is not None
        assert fit[0] == pytest.approx(k, rel=1e-9)
        assert fit[1] == pytest.approx(d, rel=1e-9)


# ---- estimators against known distributions -------------------------------

def test_excess_kurtosis_recovers_textbook_values():
    """Gaussian -> 0, uniform -> -1.2, Laplace -> 3, on large samples.

    These are the three distributions whose fourth moment everyone knows, so
    they pin the estimator's normalisation without any appeal to the library.
    """
    rng = random.Random(2006)
    n = 400_000
    gauss = [rng.gauss(0.0, 1.0) for _ in range(n)]
    unif = [rng.uniform(-1.0, 1.0) for _ in range(n)]
    lap = []
    for _ in range(n):
        u = rng.random() - 0.5
        lap.append(-math.copysign(math.log(1 - 2 * abs(u)), u))
    assert excess_kurtosis(gauss) == pytest.approx(0.0, abs=0.08)
    assert excess_kurtosis(unif) == pytest.approx(-1.2, abs=0.02)
    assert excess_kurtosis(lap) == pytest.approx(3.0, abs=0.35)


def test_hill_estimator_recovers_a_known_pareto_tail():
    """Hill's estimate of alpha matches the alpha a Pareto sample was drawn with.

    The tail index is the number the fat-tail claim is made in, so it has to
    be checked against a distribution whose tail exponent is chosen, not
    inferred.
    """
    rng = random.Random(2007)
    for alpha in (1.5, 2.5, 4.0):
        sample = [(1.0 - rng.random()) ** (-1.0 / alpha) for _ in range(200_000)]
        est = hill_tail_index(sample, tail_frac=0.02)
        assert est is not None
        assert est == pytest.approx(alpha, rel=0.05)


def test_decay_exponent_recovers_a_known_power_law_decay():
    """A sequence rho(l) = c * l^-g is fitted back to g.

    `flow_memory` reports this exponent and compares it with the ~0.5 seen in
    real order flow, so a biased fit would make that comparison meaningless.
    """
    rng = random.Random(2008)
    for _ in range(100):
        c, g = rng.uniform(0.05, 0.5), rng.uniform(0.2, 1.5)
        acf = [c * (lag ** -g) for lag in range(1, 60)]
        assert decay_exponent(acf) == pytest.approx(g, rel=1e-9)


def test_roll_estimator_recovers_the_spread_it_was_given():
    """2*sqrt(-gamma1) returns the spread of a synthetic Roll process.

    Roll (1984): p_t = m_t + (s/2) q_t with m a random walk and q iid +-1
    gives Cov(dp_t, dp_{t-1}) = -(s/2)^2, independent of the volatility of m.
    Recovering s from trade prices alone is the whole content of the result.

    rho1 is checked against its population value -c^2/(sigma^2 + 2c^2) with a
    four-standard-error allowance rather than against Roll's [-1/2, 0) bound.
    The bound holds for the population quantity; when sigma is small the
    population value sits within a standard error of the -1/2 floor and the
    *sample* autocorrelation lands below it perfectly legitimately.
    """
    rng = random.Random(2009)
    length = 20_000
    for spread, sigma in ((0.10, 0.01), (0.05, 0.02), (0.20, 0.05)):
        c = spread / 2.0
        rho_theory = -c * c / (sigma * sigma + 2 * c * c)
        estimates = []
        for _ in range(12):
            m = 100.0
            px = []
            for _ in range(length):
                m += rng.gauss(0.0, sigma)
                px.append(m + c * (1 if rng.random() < 0.5 else -1))
            d = [px[i] - px[i - 1] for i in range(1, len(px))]
            n = len(d)
            mu = sum(d) / n
            g1 = sum((d[i] - mu) * (d[i + 1] - mu) for i in range(n - 1)) / n
            assert g1 < 0, "Roll's first autocovariance must be negative"
            estimates.append(2.0 * math.sqrt(-g1))
            rho1 = autocorrelation(d, 1)[0]
            assert rho1 < 0.0
            assert rho1 == pytest.approx(rho_theory, abs=4.0 / math.sqrt(n))
        mean_est = sum(estimates) / len(estimates)
        assert mean_est == pytest.approx(spread, rel=0.02)


# ---- models ---------------------------------------------------------------

def test_impact_models_scale_as_their_names_promise():
    """Linear impact is homogeneous of degree 1; square-root, of degree 1/2.

    Both are also strictly increasing in size, and the square-root model is
    strictly concave — that concavity is the entire empirical content of the
    square-root law, so it is asserted rather than assumed.
    """
    rng = random.Random(2010)
    for _ in range(200):
        lin = LinearImpact(eta=rng.uniform(1e-5, 1e-2))
        sqrt = SquareRootImpact(eta=rng.uniform(0.01, 1.0),
                                daily_volume=rng.uniform(1e5, 1e8))
        q = rng.randint(1, 10_000)
        c = rng.randint(2, 9)
        assert lin.impact(1, c * q) == pytest.approx(c * lin.impact(1, q),
                                                     rel=1e-12)
        assert sqrt.impact(1, c * q) == pytest.approx(
            math.sqrt(c) * sqrt.impact(1, q), rel=1e-12)
        for model in (lin, sqrt):
            assert model.impact(1, q + 1) > model.impact(1, q)
            assert model.impact(-1, q) == pytest.approx(-model.impact(1, q))
        # concavity: the midpoint of the chord sits below the curve
        lo, hi = q, 4 * q
        chord = 0.5 * (sqrt.impact(1, lo) + sqrt.impact(1, hi))
        assert sqrt.impact(1, (lo + hi) // 2) > chord


def test_latency_samples_are_non_negative_with_the_advertised_mean():
    """Every delay is >= 0, and a jittered model's sample mean is its mean.

    A negative delay would let an order arrive before it was decided, which
    would break arrival ordering silently rather than loudly.
    """
    rng = random.Random(2011)
    for _ in range(30):
        delay = rng.uniform(0.0, 5.0)
        const = ConstantLatency(delay)
        assert all(const.sample(rng) == delay for _ in range(50))
        mean, shape = rng.uniform(0.2, 4.0), rng.uniform(1.0, 6.0)
        model = JitteredLatency(mean=mean, shape=shape)
        draws = [model.sample(rng) for _ in range(20_000)]
        assert all(d >= 0.0 for d in draws)
        sample_mean = sum(draws) / len(draws)
        # sd of the mean is mean/sqrt(shape*n); allow five of them.
        tol = 5.0 * mean / math.sqrt(shape * len(draws))
        assert sample_mean == pytest.approx(mean, abs=tol)
