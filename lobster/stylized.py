"""Stylized facts: does the simulated tape look anything like a real one?

A simulator is only worth reasoning with if its output has the statistical
shape of the thing it imitates. Microstructure has a short list of facts
that hold across venues, decades and asset classes, and they are cheap to
measure. This module computes three of them straight off a finished run:

1. **Bid-ask bounce.** Consecutive trade prices alternate between the bid
   and the ask, so *transaction*-price changes are strongly negatively
   autocorrelated at lag 1. Roll (1984) puts the floor at -1/2, reached
   when the efficient price does not move at all between trades.

2. **Long memory of order flow.** The sequence of trade signs (+1 buyer-
   initiated, -1 seller-initiated) is positively autocorrelated over
   surprisingly long horizons, decaying like a power law rho(l) ~ l^-gamma
   with gamma well under 1 (Bouchaud et al. 2004; Lillo & Farmer 2004).
   Order splitting, not herding, is the usual explanation.

3. **The depth profile is humped.** Average resting size is *not* largest
   at the touch: it rises with distance from the mid, peaks a few ticks
   out, then decays (Bouchaud, Mezard & Potters 2002).

Plus a fourth diagnostic that is really a sanity check on the *mid*: over
horizons longer than the bounce, an efficient price is close to a
martingale, so its variance ratio should sit near 1.

`ReturnFacts` covers the other end of the same question: the unconditional
distribution rather than the book. Cont (2001) lists the properties any
return series is expected to have: heavy tails with a finite tail index,
almost no linear autocorrelation, a distribution that becomes more Gaussian
as returns are aggregated, and *absolute* returns that stay positively
autocorrelated for a long time (volatility clustering).

Everything here is deliberately plain: overlapping-window variance ratios,
an unbiased-mean autocorrelation, Hill's estimator for the tail index,
log-log OLS for decay exponents. No dependencies, no estimator cleverness
that would need its own tests.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .book import OrderBook
from .order import Side
from .tape import Tape, Trade

# ---- sequences ------------------------------------------------------------

def trade_signs(tape: Iterable[Trade]) -> list[int]:
    """+1 for buyer-initiated trades, -1 for seller-initiated."""
    return [1 if t.aggressor is Side.BUY else -1 for t in tape]


def trade_prices(tape: Iterable[Trade]) -> list[float]:
    return [t.price for t in tape]


# ---- autocorrelation ------------------------------------------------------

def autocorrelation(x: Sequence[float], max_lag: int) -> list[float]:
    """Sample autocorrelation at lags 1..max_lag (single mean, as usual).

    Returns an empty list if the series is too short or constant.
    """
    n = len(x)
    if n < 2 or max_lag < 1:
        return []
    mu = sum(x) / n
    dev = [v - mu for v in x]
    denom = sum(d * d for d in dev)
    if denom == 0.0:
        return []
    out: list[float] = []
    for lag in range(1, min(max_lag, n - 1) + 1):
        num = sum(dev[i] * dev[i + lag] for i in range(n - lag))
        out.append(num / denom)
    return out


def decay_exponent(acf: Sequence[float], first_lag: int = 1) -> float | None:
    """Fit rho(l) = c * l**-gamma by OLS on the log-log of the positive lags.

    Returns gamma (positive = decaying), or None if fewer than three lags
    are positive. Real order flow sits around gamma ~ 0.5; a value near or
    above 1 means the memory dies within a handful of trades.
    """
    pts = [(math.log(first_lag + i), math.log(r))
           for i, r in enumerate(acf) if r > 0.0]
    if len(pts) < 3:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if sxx == 0.0:
        return None
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    return -(sxy / sxx)


# ---- variance ratio -------------------------------------------------------

def variance_ratio(prices: Sequence[float], q: int) -> float:
    """Var(q-step price change) / (q * Var(1-step change)), overlapping.

    1.0 = random walk. Below 1 = mean reversion (bid-ask bounce dominates
    at short q). Above 1 = trending / super-diffusion.
    """
    if q < 1:
        raise ValueError(f"q must be >= 1, got {q}")
    if len(prices) <= q + 1:
        raise ValueError(f"need more than {q + 1} prices for q={q}")
    one = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    v1 = _pvar(one)
    if v1 == 0.0:
        raise ValueError("one-step price changes have zero variance")
    many = [prices[i] - prices[i - q] for i in range(q, len(prices))]
    return _pvar(many) / (q * v1)


def variance_ratio_curve(prices: Sequence[float],
                         qs: Sequence[int]) -> list[float]:
    """`variance_ratio` at each horizon in `qs`; [] if the series is too short."""
    if not qs or len(prices) <= max(qs) + 1:
        return []
    return [variance_ratio(prices, q) for q in qs]


def _pvar(x: Sequence[float]) -> float:
    n = len(x)
    if n == 0:
        return 0.0
    mu = sum(x) / n
    return sum((v - mu) ** 2 for v in x) / n


# ---- depth profile --------------------------------------------------------

def depth_profile(book: OrderBook, bin_width: float = 0.05,
                  max_distance: float = 1.0) -> list[float]:
    """Resting size binned by absolute distance from the mid, both sides.

    Bin `i` covers distances [i*bin_width, (i+1)*bin_width). Returns a
    fixed-length list of `ceil(max_distance / bin_width)` totals so that
    profiles from different moments can be averaged elementwise. An empty
    or one-sided book (no mid) contributes all zeros.
    """
    if bin_width <= 0 or max_distance <= 0:
        raise ValueError("bin_width and max_distance must be positive")
    nbins = math.ceil(max_distance / bin_width)
    bins = [0.0] * nbins
    mid = book.mid
    if mid is None:
        return bins
    for side in (Side.BUY, Side.SELL):
        for level in book.iter_levels(side):
            d = abs(level.price - mid)
            i = int(d / bin_width)
            if 0 <= i < nbins:
                bins[i] += level.total_qty
    return bins


def mean_depth_profile(profiles: Sequence[Sequence[float]]) -> list[float]:
    """Elementwise mean of profiles produced by `depth_profile`."""
    if not profiles:
        return []
    n = len(profiles[0])
    if any(len(p) != n for p in profiles):
        raise ValueError("profiles must all have the same number of bins")
    return [sum(p[i] for p in profiles) / len(profiles) for i in range(n)]


def bin_centers(bin_width: float, nbins: int) -> list[float]:
    return [(i + 0.5) * bin_width for i in range(nbins)]


# ---- report ---------------------------------------------------------------

@dataclass
class StylizedFacts:
    """The three diagnostics plus the mid-price martingale check.

    `sign_acf` is indexed from lag 1. `vr_qs` are the horizons at which
    `vr_trades` (transaction prices) and `vr_mid` (mid prices) are
    evaluated. `depth` is the mean profile, `depth_bin_width` its bin size.
    """

    sign_acf: list[float]
    price_change_acf: list[float]
    vr_qs: list[int]
    vr_trades: list[float]
    vr_mid: list[float]
    depth: list[float]
    depth_bin_width: float
    n_trades: int

    @classmethod
    def measure(cls, tape: Tape, mids: Sequence[float],
                depth_profiles: Sequence[Sequence[float]],
                *, max_lag: int = 64,
                vr_qs: Sequence[int] = (1, 2, 5, 10, 20, 50, 100),
                depth_bin_width: float = 0.05) -> StylizedFacts:
        px = trade_prices(tape)
        dpx = [px[i] - px[i - 1] for i in range(1, len(px))]
        return cls(
            sign_acf=autocorrelation(trade_signs(tape), max_lag),
            price_change_acf=autocorrelation(dpx, max_lag),
            vr_qs=list(vr_qs),
            vr_trades=variance_ratio_curve(px, vr_qs),
            vr_mid=variance_ratio_curve(mids, vr_qs),
            depth=mean_depth_profile(depth_profiles),
            depth_bin_width=depth_bin_width,
            n_trades=len(px),
        )

    @property
    def bounce(self) -> float:
        """Lag-1 autocorrelation of transaction-price changes (Roll)."""
        return self.price_change_acf[0] if self.price_change_acf else 0.0

    @property
    def flow_memory(self) -> float | None:
        """Power-law decay exponent of the trade-sign autocorrelation."""
        return decay_exponent(self.sign_acf)

    def memory_horizon(self, window: int = 10) -> int:
        """How many trades order-flow memory survives, in lags.

        The largest lag whose trailing `window`-lag mean of the sign
        autocorrelation still clears the +-2/sqrt(N) noise band; 0 when the
        signs are indistinguishable from coin flips. Smoothing matters:
        individual lags rattle around the band long after the signal is
        gone. Real equity order flow does not reach 0 within any window
        anyone has been able to measure.
        """
        if not self.sign_acf or self.n_trades <= 0 or window < 1:
            return 0
        band = 2.0 / math.sqrt(self.n_trades)
        horizon = 0
        for i in range(len(self.sign_acf) - window + 1):
            if sum(self.sign_acf[i:i + window]) / window > band:
                horizon = i + window
        return horizon

    @property
    def depth_peak(self) -> float:
        """Distance from the mid at which mean resting size is largest."""
        if not self.depth:
            return 0.0
        i = max(range(len(self.depth)), key=lambda k: self.depth[k])
        return (i + 0.5) * self.depth_bin_width

    def summary(self) -> dict[str, float | None]:
        return {
            "n_trades": float(self.n_trades),
            "bounce_acf1": self.bounce,
            "sign_acf1": self.sign_acf[0] if self.sign_acf else 0.0,
            "flow_memory_gamma": self.flow_memory,
            "memory_horizon": float(self.memory_horizon()),
            "vr_trades_10": self._vr(self.vr_trades, 10),
            "vr_mid_10": self._vr(self.vr_mid, 10),
            "vr_mid_100": self._vr(self.vr_mid, 100),
            "depth_peak_distance": self.depth_peak,
        }

    def _vr(self, curve: list[float], q: int) -> float | None:
        if q not in self.vr_qs or len(curve) != len(self.vr_qs):
            return None
        return curve[self.vr_qs.index(q)]


# ---- return distribution --------------------------------------------------

def log_returns(prices: Sequence[float]) -> list[float]:
    """Log returns of a strictly positive price series."""
    out: list[float] = []
    for i in range(1, len(prices)):
        a, b = prices[i - 1], prices[i]
        if a > 0 and b > 0:
            out.append(math.log(b / a))
    return out


def aggregate(x: Sequence[float], k: int) -> list[float]:
    """Non-overlapping sums of `k` consecutive values (return aggregation)."""
    if k < 1:
        raise ValueError("k must be >= 1")
    return [sum(x[i:i + k]) for i in range(0, len(x) - k + 1, k)]


def excess_kurtosis(x: Sequence[float]) -> float | None:
    """Sample excess kurtosis `m4 / m2**2 - 3` (0 for a Gaussian).

    None when there are fewer than four points or the sample is constant.
    """
    n = len(x)
    if n < 4:
        return None
    mu = sum(x) / n
    m2 = sum((v - mu) ** 2 for v in x) / n
    if m2 == 0.0:
        return None
    m4 = sum((v - mu) ** 4 for v in x) / n
    return m4 / (m2 * m2) - 3.0


def hill_tail_index(x: Sequence[float], tail_frac: float = 0.05) -> float | None:
    """Hill (1975) estimate of the tail index of |x|, from its largest values.

    Uses the top `tail_frac` of the sample. The tail index alpha is the
    power-law exponent of the survival function, P(|X| > u) ~ u**-alpha, so
    moments of order >= alpha do not exist. Returns None if fewer than 20
    order statistics land in the tail or the threshold is zero.
    """
    if not 0.0 < tail_frac < 1.0:
        raise ValueError("tail_frac must be in (0, 1)")
    mags = sorted((abs(v) for v in x), reverse=True)
    k = int(len(mags) * tail_frac)
    if k < 20 or k >= len(mags):
        return None
    threshold = mags[k]
    if threshold <= 0.0:
        return None
    s = sum(math.log(mags[i] / threshold) for i in range(k))
    if s <= 0.0:
        return None
    return k / s


@dataclass
class ReturnFacts:
    """Unconditional and second-order properties of a return series.

    The three things Cont (2001) singles out for asset returns: the
    distribution is heavy-tailed (positive excess kurtosis, finite tail
    index), returns themselves are close to uncorrelated, and *absolute*
    returns are positively autocorrelated over long horizons, which is volatility
    clustering.
    """

    n: int
    excess_kurtosis: float | None
    tail_index: float | None
    ret_acf: list[float]
    abs_ret_acf: list[float]
    aggregated_kurtosis: dict[int, float | None]

    @classmethod
    def measure(cls, returns: Sequence[float], *, max_lag: int = 100,
                tail_frac: float = 0.05,
                aggregation: Sequence[int] = (1, 10, 100)) -> ReturnFacts:
        absr = [abs(r) for r in returns]
        return cls(
            n=len(returns),
            excess_kurtosis=excess_kurtosis(returns),
            tail_index=hill_tail_index(returns, tail_frac),
            ret_acf=autocorrelation(returns, max_lag),
            abs_ret_acf=autocorrelation(absr, max_lag),
            aggregated_kurtosis={k: excess_kurtosis(aggregate(returns, k))
                                 for k in aggregation},
        )

    @property
    def clustering(self) -> float | None:
        """Mean autocorrelation of |r| over the measured lags.

        Positive and slowly decaying is the empirical signature; a value at
        or below zero means the series has no volatility clustering to find.
        """
        if not self.abs_ret_acf:
            return None
        return sum(self.abs_ret_acf) / len(self.abs_ret_acf)

    @property
    def clustering_decay(self) -> float | None:
        """Power-law exponent of the |r| autocorrelation (see `decay_exponent`)."""
        return decay_exponent(self.abs_ret_acf)
