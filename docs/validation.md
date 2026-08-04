# lobster — validation against things outside itself

A simulator that only agrees with its own tests is a very elaborate way of
being wrong. This document is the other kind of check: every number below
came out of a process whose answer was fixed before the library saw it —
either a closed-form result, or a magnitude somebody else published.

Reproduce all of it with:

```sh
python examples/validate.py            # ~20 s
python examples/validate.py --quick    # ~4 s, coarser Monte Carlo
```

The raw output of the run this page was written from is pasted at the
bottom. Nothing here has been rounded in a flattering direction, and where
the library loses it says so — seven of the fourteen rows in Part 2 fail,
either outright or for one of the two agent mixes, and the failures are the
more useful half of the page.

**On the reference column.** Two kinds of number appear there. Some are
analytic: Roll's autocovariance identity, the impact exponent implied by a
depth profile, a Pareto tail index. Those are exact and the only question is
whether the estimator finds them. Others are empirical magnitudes from the
literature, cited by author and year at the bottom. Where a published figure
is a range or a rule of thumb it is written as one, and where I could not
vouch for a specific number in a specific paper I used the analytic ground
truth instead rather than invent a citation. Every source listed is one
whose result is stated in the text as attributed.

---

## Part 1 — do the estimators find answers that are known in advance?

Nothing in Part 2 means anything if the measuring instruments are wrong, so
they are calibrated first, against processes built to have a specific answer.

| claim | our value | reference value | source |
|---|---|---|---|
| Roll's implied spread recovers a spread of 0.10 (sigma 0.01) | 0.09987 | 0.10000 | Roll (1984), analytic |
| ... a spread of 0.05 (sigma 0.02) | 0.05008 | 0.05000 | Roll (1984), analytic |
| ... a spread of 0.20 (sigma 0.05) | 0.19998 | 0.20000 | Roll (1984), analytic |
| lag-1 autocorrelation of a Roll process, s=0.10 sigma=0.01 | -0.48971 | -0.49020 | -c^2/(sigma^2+2c^2) |
| lag-1 autocorrelation of a Roll process, s=0.05 sigma=0.02 | -0.37967 | -0.37879 | -c^2/(sigma^2+2c^2) |
| lag-1 autocorrelation of a Roll process, s=0.20 sigma=0.05 | -0.44447 | -0.44444 | -c^2/(sigma^2+2c^2) |
| VR(2) on 1,500 Gaussian random walks, T=2000 | 0.9997 | 1.0000 | Lo & MacKinlay (1988) |
| sampling s.d. of VR(2) | 0.0224 | 0.0224 | sqrt(2(2q-1)(q-1)/3qT) |
| sampling s.d. of VR(5) | 0.0504 | 0.0490 | sqrt(2(2q-1)(q-1)/3qT) |
| sampling s.d. of VR(10) | 0.0758 | 0.0755 | sqrt(2(2q-1)(q-1)/3qT) |
| sampling s.d. of VR(50) | 0.1703 | 0.1798 | sqrt(2(2q-1)(q-1)/3qT) |
| mean VR(50) — the finite-sample bias | 0.9779 | 1.0000 | Lo & MacKinlay (1988) |
| book-walk exponent, depth flat in distance | 1.0000 | 1.0000 | analytic |
| book-walk exponent, depth linear in distance | 0.5038 | 0.5000 | analytic |
| book-walk exponent, depth quadratic in distance | 0.3448 | 0.3333 | analytic |
| `SquareRootImpact`: impact(4Q)/impact(Q) | 2.000000000000 | 2 | analytic, exact |
| `SquareRootImpact`: impact(9Q)/impact(Q) | 3.000000000000 | 3 | analytic, exact |

Three things worth saying out loud about that table.

**Roll's estimator is unreasonably good.** Fed a process that is exactly
Roll's — an efficient price doing a random walk plus a half-spread times an
independent coin flip — `2*sqrt(-gamma1)` returns the spread it was given to
within 0.2% on 20,000 observations, across a factor of four in spread and
a factor of five in volatility. That is the whole content of the 1984 paper
and it survives contact with this implementation.

**The variance-ratio estimator here is biased low, and the bias grows with
the horizon.** At q=2 the mean over 1,500 random walks is 0.9997; at q=50 it
is 0.9779, more than two per cent below the null. This is expected and it is
not a defect of the random walks: `variance_ratio` uses plain population
variances with no small-sample correction, and the q-step differences
overlap, so roughly q/T of the variance is eaten by the end effects. Lo and
MacKinlay's own statistic carries a bias correction precisely for this. If
you are testing a null at long horizons on a short series, do not read a
`VR` of 0.98 as evidence of mean reversion. The *spread* of the sampling
distribution, on the other hand, matches their asymptotic formula to within
a few per cent at every horizon tested, which is the more delicate claim.

**The book walk finds the square-root law when the square-root law is
there.** Cumulative depth growing like distance-squared implies a price
displacement growing like sqrt(Q), and `cost_to_trade` measures 0.504
against the analytic 0.500. The residual is discretisation: the walk stops
at a level index, which is an integer. This matters for Part 2 — when the
simulator's impact comes out at the wrong exponent, it is not because the
exponent is being measured wrongly.

![impact](impact_law.png)

Panel (a) is that calibration. Panel (b) is the simulator, and the two
lines do not have the same slope.

---

## Part 2 — does the simulator behave like a market?

Two agent mixes are scored: the bundled demo (two noise traders, a momentum
chaser, one market maker) and the same thing with the chaser removed, since
almost every disagreement below traces back to that one agent.

### Return distribution and volatility clustering

| claim | our value (demo / no chaser) | reference value | source | agrees |
|---|---|---|---|---|
| returns are heavy-tailed: excess kurtosis > 0 | 256.75 / 10.89 | positive, large | Cont (2001) | yes |
| tail index of \|r\| | 1.84 / 3.29 | 2 to 5 | Cont (2001) | no / yes |
| aggregational Gaussianity: kurtosis falls with aggregation | 92.21 vs 256.75 / 16.14 vs 10.89 | falls toward 0 | Cont (2001) | yes / no |
| returns are close to linearly uncorrelated | +0.0982 / +0.0279 | ~0 | Cont (2001) | no / yes |
| volatility clustering: rho(\|r\|) at lag 1 | +0.2675 / +0.1305 | positive | Cont (2001) | yes |
| ... still positive at lag 100 | +0.0520 / +0.0098 | positive, slow decay | Cont (2001) | yes |
| decay exponent of rho(\|r\|) | 0.55 / 0.83 | below 1 | Cont (2001) | yes |

### Microstructure

| claim | our value (demo / no chaser) | reference value | source | agrees |
|---|---|---|---|---|
| bid-ask bounce: lag-1 autocorrelation of trade-price changes | -0.370 / -0.461 | in [-1/2, 0) | Roll (1984) | yes |
| order-flow sign memory: power-law exponent | 0.94 / no memory | ~0.5 | Bouchaud et al. (2004) | no |
| order-flow memory horizon | 69 trades / 0 | thousands of trades | Bouchaud et al. (2004) | no |
| mean depth peaks away from the touch | 0.43 away, touch holds 2.1% / 1.6% of the peak | peak away from the touch | Bouchaud, Mezard & Potters (2002) | yes |
| a passive market maker is adversely selected | -0.42518 / -0.05490 | negative markout | Glosten & Milgrom (1985) | yes |
| metaorder cost exponent (net of half-spread) | 1.30 / 1.23 | 0.5 to 0.6 | Almgren et al. (2005); Gatheral (2010) | no |
| metaorder peak-impact exponent | 1.47 / 1.28 | 0.5 to 0.6 | Almgren et al. (2005) | no |

Across the two tables: seven rows agree, four disagree outright, and three
agree for one agent mix and not the other. The next section is about the
seven that are not clean wins, because a validation document that only lists
its wins is a brochure.

---

## Where this does not match reality, and why

### 1. Impact is convex here and concave in the world. (The big one.)

The square-root law — the cost of a metaorder growing like the square root
of its size relative to volume — is about as robust as empirical finance
gets. Almgren, Thum, Hauptmann and Li (2005) estimate a temporary-impact
exponent near 3/5 directly from institutional order data; Gatheral (2010)
works out what decay kernel an exponent of 1/2 has to be paired with for the
model to be free of dynamic arbitrage. Either way the number is well below
one, and the practical consequence is that splitting a large order helps
less than a linear model promises.

This simulator produces an exponent of **1.23 to 1.47**, i.e. cost that is
*convex* in size. Trading twice as much costs more than twice as much. That
is the opposite sign of curvature, and it is not a measurement artifact —
Part 1c shows the same estimator recovering 0.504 from a book engineered to
have a square-root law.

The reason is that nothing here replenishes liquidity in response to being
consumed. In a real book the resting quantity is the visible tip of a much
larger reservoir of latent intentions, and a metaorder that walks the book
pulls fresh liquidity in behind it — the mechanism the modern literature
credits for the concavity. Here there are two noise traders and a market
maker quoting a fixed half-spread off the mid: as the parent eats depth, the
maker re-quotes around a mid that has already moved, so the parent chases
its own footprint. Add the momentum agent and it is worse, because that
agent trades *with* the footprint.

An informed trader — one with a view on value, who supplies liquidity into a
price it thinks is wrong — is the missing piece, and it is the same missing
piece as in items 2 and 3.

### 2. Order-flow memory dies at the chaser's lookback.

Real trade signs stay positively autocorrelated out to thousands of trades,
decaying like a power law with exponent around 0.5 (Bouchaud, Gefen, Potters
and Wyart 2004). Lillo, Mike and Farmer (2005) show why: institutions split
parent orders, parent sizes are heavy-tailed with exponent alpha, and the
sign autocorrelation inherits gamma = alpha - 1.

Here the exponent is 0.94 and the memory is gone by lag 69 — and remove the
momentum agent and there is no memory at all, signs are coin flips from lag
1. That is exactly the diagnosis the Lillo-Mike-Farmer mechanism predicts
for a simulator with no parent orders in it: the only source of persistence
is one agent with a 20-trade window, so the memory necessarily expires at a
horizon that window sets.

### 3. The mid is not a martingale, and the tail is too fat.

With the chaser in the mix the lag-1 return autocorrelation is +0.098 and
`VR(100)` is 10.6 (see `docs/theory.md` §4). Cont's first stylized fact is
that returns show *no* significant linear autocorrelation beyond a few
minutes; ours show plenty, in the same direction, at every horizon. The tail
index falls to 1.84, below the 2-to-5 band Cont reports and low enough to
imply infinite variance, which is not a claim anybody makes about equity
returns.

Take the chaser out and both go away: lag-1 autocorrelation +0.028, tail
index 3.29, `VR(100)` 1.54. So this failure is one agent's, and it is a
trend-follower with nothing on the other side of it. Real markets have
mean-reverting flow — statistical arbitrage, hedgers selling into strength —
and this agent set has none.

### 4. Volatility clustering is real here but for a thin reason.

The absolute-return autocorrelation is positive out to lag 100 with a decay
exponent of 0.55 (demo) and 0.83 (no chaser), which is the right shape and
the right order of magnitude. Do not read too much into it. There is no
stochastic-volatility mechanism in this simulator; the likeliest explanation
is that trading *activity* clusters — the market maker's cancel-replace and
the noise traders' arrival process bunch trades together, and bunched trades
mean bunched price changes. The empirical fact is generally attributed to something
richer than that, so this is the right answer arrived at by a shortcut — the
same caveat that applies to the humped depth profile in `theory.md` §6.

### 5. Aggregational Gaussianity fails once the chaser is gone.

Cont (2001) notes that as returns are aggregated over longer intervals, the
distribution moves toward Gaussian and excess kurtosis falls. In the demo
mix it does — 256.75 at one tick, 92.21 at a hundred. Without the chaser it
goes the wrong way, 10.89 to 16.14. With no trend to smooth out, the
aggregate is dominated by rare multi-tick moves and gets *less* Gaussian.
It is a small sample of a small effect and it is reported as a failure
rather than dropped.

### 6. Half the returns are exactly zero.

About 54% of tick-to-tick mid returns in both mixes are exactly 0.0, because
the mid only moves when the touch does. This inflates kurtosis mechanically
— a distribution that is mostly a point mass at zero with occasional jumps
has enormous fourth moments regardless of what the jumps look like. The
excess-kurtosis figures in the first table should be read as "heavy-tailed,
directionally right, magnitude not comparable with a daily equity series".
Real tick data has the same property, which is one reason microstructure
work rarely quotes tick-return kurtosis without saying how it was sampled.

---

## What this means for using the package

The verdict has not changed since the scorecard in the README, it has just
got more precise. `lobster` is measurably sound as a **mechanism**: price-time
priority, queue position, spread and adverse-selection accounting, and the
cost of walking a book are all correct, and the estimators that measure them
recover known answers to within a per cent. It is measurably *not* a
realistic **price process**: order flow has no memory to speak of, the mid
trends when it should not, and impact curves the wrong way.

Use it for questions about the queue and about execution mechanics. Do not
use it to calibrate a cost model you intend to point at a real market —
`examples/execution_costs.py` shows the shape of that workflow deliberately
using the simulator's own convex exponent, and says in its own output that
the exponent is not the one the literature reports.

---

## The run this document was written from

```
lobster — validation against external ground truth
==================================================================
Part 1: estimators against closed-form answers

1a. Roll's implied spread against a process with a known spread
---------------------------------------------------------------
     rho1 = -c^2 / (sigma^2 + 2c^2),  s_hat = 2*sqrt(-gamma1)
  s=0.10 sigma=0.01: implied spread                        0.09987   vs 0.10000                   -0.13%
  s=0.10 sigma=0.01: rho1                                 -0.48971   vs -0.49020                  +0.10%
  s=0.05 sigma=0.02: implied spread                        0.05008   vs 0.05000                   +0.17%
  s=0.05 sigma=0.02: rho1                                 -0.37967   vs -0.37879                  -0.23%
  s=0.20 sigma=0.05: implied spread                        0.19998   vs 0.20000                   -0.01%
  s=0.20 sigma=0.05: rho1                                 -0.44447   vs -0.44444                  -0.01%

1b. Variance-ratio null against Lo and MacKinlay's asymptotics
--------------------------------------------------------------
     under a random walk VR(q) -> 1 with sd sqrt(2(2q-1)(q-1)/(3qT))
  q=2: mean VR over 1500 paths                              0.9997   vs 1.0000                    -0.03%
  q=2: sd of VR                                             0.0224   vs 0.0224                    +0.07%
  q=5: mean VR over 1500 paths                              0.9989   vs 1.0000                    -0.11%
  q=5: sd of VR                                             0.0504   vs 0.0490                    +2.87%
  q=10: mean VR over 1500 paths                             0.9969   vs 1.0000                    -0.31%
  q=10: sd of VR                                            0.0758   vs 0.0755                    +0.38%
  q=50: mean VR over 1500 paths                             0.9779   vs 1.0000                    -2.21%
  q=50: sd of VR                                            0.1703   vs 0.1798                    -5.28%

1c. Book-walk impact exponent against depth profiles solvable on paper
----------------------------------------------------------------------
     cumulative depth ~ d^(1+a) implies price impact ~ Q^(1/(1+a))
  flat depth, q(i) = 100                                    1.0000   vs 1.0000                    +0.00%
  depth linear in distance, q(i) = 2i                       0.5038   vs 0.5000                    +0.76%
  depth quadratic, q(i) = 3i^2                              0.3448   vs 0.3333                    +3.45%

1d. SquareRootImpact is exactly a half-power law
------------------------------------------------
  impact(4Q) / impact(Q)                            2.000000000000   vs 2.000000000000            exact
  impact(9Q) / impact(Q)                            3.000000000000   vs 3.000000000000            exact
  impact(16Q) / impact(Q)                           4.000000000000   vs 4.000000000000            exact

==================================================================
Part 2: the simulator against published stylized facts

2a. Return distribution and volatility clustering (Cont 2001)
-------------------------------------------------------------

  [demo mix]  99,966 tick returns, 53.9% of them exactly zero
  excess kurtosis of tick returns                           256.75   vs > 0 (heavy tailed)        yes
  Hill tail index of |r|, top 5%                              1.84   vs 2 to 5                    outside the band
  excess kurtosis, 100-tick aggregation                      92.21   vs < 256.75 (toward 0)       yes
  lag-1 autocorrelation of tick returns                    +0.0982   vs ~0 (Cont 2001)            no
  rho(|r|) at lag 1                                        +0.2675   vs > 0                       yes
  rho(|r|) at lag 100                                      +0.0520   vs > 0, slow decay           yes
  decay exponent of rho(|r|)                                  0.55   vs < 1 (long memory)         yes

  [no chaser]  99,992 tick returns, 54.9% of them exactly zero
  excess kurtosis of tick returns                            10.89   vs > 0 (heavy tailed)        yes
  Hill tail index of |r|, top 5%                              3.29   vs 2 to 5                    yes
  excess kurtosis, 100-tick aggregation                      16.14   vs < 10.89 (toward 0)        no
  lag-1 autocorrelation of tick returns                    +0.0279   vs ~0 (Cont 2001)            yes
  rho(|r|) at lag 1                                        +0.1305   vs > 0                       yes
  rho(|r|) at lag 100                                      +0.0098   vs > 0, slow decay           yes
  decay exponent of rho(|r|)                                  0.83   vs < 1 (long memory)         yes

2b. Microstructure facts (Roll 1984; Bouchaud et al. 2002, 2004)
----------------------------------------------------------------

  [demo mix]  29,882 trades
  lag-1 autocorrelation of trade-price changes              -0.370   vs in [-0.5, 0)              yes
  order-flow sign memory: decay exponent gamma                0.94   vs ~0.5                      no
  order-flow memory horizon, in trades                          69   vs thousands of trades       no
  depth peaks away from the touch             0.43 (2.1% at touch)   vs > 0 (humped)              yes
  market maker's passive markout, h=10                    -0.42518   vs < 0 (adversely selected)  yes

  [no chaser]  27,612 trades
  lag-1 autocorrelation of trade-price changes              -0.461   vs in [-0.5, 0)              yes
  order-flow sign memory: decay exponent gamma    no memory to fit   vs ~0.5                      no
  order-flow memory horizon, in trades                           0   vs thousands of trades       no
  depth peaks away from the touch             0.43 (1.6% at touch)   vs > 0 (humped)              yes
  market maker's passive markout, h=10                    -0.05490   vs < 0 (adversely selected)  yes

2c. The impact of a metaorder (Almgren et al. 2005; Gatheral 2010)
------------------------------------------------------------------
     a parent order worked in 8-lot children every other tick

  [demo mix]
    Q=   20  shortfall=+0.2520  net of half-spread=+0.0741  peak impact=+0.0773
    Q=   40  shortfall=+0.2902  net of half-spread=+0.1123  peak impact=+0.1142
    Q=   80  shortfall=+0.4265  net of half-spread=+0.2486  peak impact=+0.4910
    Q=  160  shortfall=+0.9325  net of half-spread=+0.7546  peak impact=+1.9115
    Q=  320  shortfall=+2.7936  net of half-spread=+2.6156  peak impact=+6.0263
    Q=  640  shortfall=+5.9928  net of half-spread=+5.8148  peak impact=+11.5813
    Q= 1280  shortfall=+11.0756  net of half-spread=+10.8977  peak impact=+20.2060
  exponent of shortfall incl. half-spread                     0.99   vs 0.5 to 0.6                no
  exponent of shortfall net of half-spread                    1.30   vs 0.5 to 0.6                no
  exponent of peak mid impact                                 1.47   vs 0.5 to 0.6                no

  [no chaser]
    Q=   20  shortfall=+0.2015  net of half-spread=+0.0351  peak impact=+0.0754
    Q=   40  shortfall=+0.2547  net of half-spread=+0.0883  peak impact=+0.1642
    Q=   80  shortfall=+0.3504  net of half-spread=+0.1840  peak impact=+0.3408
    Q=  160  shortfall=+0.6044  net of half-spread=+0.4379  peak impact=+0.8508
    Q=  320  shortfall=+1.0759  net of half-spread=+0.9094  peak impact=+1.7952
    Q=  640  shortfall=+2.5626  net of half-spread=+2.3961  peak impact=+6.1096
    Q= 1280  shortfall=+6.7715  net of half-spread=+6.6051  peak impact=+15.7158
  exponent of shortfall incl. half-spread                     0.84   vs 0.5 to 0.6                no
  exponent of shortfall net of half-spread                    1.23   vs 0.5 to 0.6                no
  exponent of peak mid impact                                 1.28   vs 0.5 to 0.6                no
```

The exponents in section 2c are fitted on parent orders held to a fixed
child size and a fixed cadence, so the execution horizon grows with the
parent. `examples/execution_costs.py` fits the same law the other way round
— fixed horizon, varying rate, expressed as a participation rate — and gets
1.75. Both are convex; neither is 0.5.

---

## Invariants asserted for every input

Separately from the numbers above, `tests/test_properties.py` and
`tests/test_estimator_properties.py` assert the things that must hold for
*all* inputs rather than for a fixture, on a few thousand randomly generated
cases each with a fixed seed:

- filled + leaves == requested, for every order the engine sees
- book depth changes by exactly (rested remainder - filled)
- agent inventories sum to zero and agent cash sums to zero in a closed sim
- best bid < best ask after any sequence of add / match / cancel
- the order-id index is exactly the set of resting orders
- fills arrive best-price-first, and within a price in arrival order
- a larger market order never gets a better average price
- `cost_to_trade` equals what `match` actually charges
- the depth profile is invariant to translating every price
- self-trade prevention leaves no trade with buyer_id == seller_id
- no order rests longer than its TTL
- a simulation is a deterministic function of its seed
- autocorrelation is bounded by 1 and invariant to affine rescaling
- VR(1) is exactly 1, and VR(q) is scale-free
- VR(q) equals 1 + 2*sum_k (1-k/q) rho_k, the identity it is defined by
- excess kurtosis returns 0 for a Gaussian, -1.2 for a uniform, 3 for a Laplace
- Hill's estimator recovers the alpha a Pareto sample was drawn with
- a power-law fit inverts an exact power law
- linear impact is homogeneous of degree 1, square-root of degree 1/2,
  and the square-root model is strictly concave
- latency samples are non-negative with the advertised mean

---

## References

- Roll, R. (1984). *A simple implicit measure of the effective bid-ask
  spread in an efficient market.* Journal of Finance 39(4), 1127-1139. —
  the serial-covariance identity and the implied-spread estimator.
- Glosten, L. and Milgrom, P. (1985). *Bid, ask and transaction prices in a
  specialist market with heterogeneously informed traders.* Journal of
  Financial Economics 14(1), 71-100. — the spread as compensation for
  adverse selection.
- Lo, A. W. and MacKinlay, A. C. (1988). *Stock market prices do not follow
  random walks: evidence from a simple specification test.* Review of
  Financial Studies 1(1), 41-66. — the variance-ratio statistic and its
  sampling distribution under the random-walk null.
- Cont, R. (2001). *Empirical properties of asset returns: stylized facts
  and statistical issues.* Quantitative Finance 1(2), 223-236. — heavy
  tails with a tail index between 2 and 5, absence of linear
  autocorrelation, aggregational Gaussianity, and volatility clustering.
- Bouchaud, J.-P., Mezard, M. and Potters, M. (2002). *Statistical
  properties of stock order books: empirical results and models.*
  Quantitative Finance 2(4), 251-256. — the mean book shape peaking away
  from the touch.
- Bouchaud, J.-P., Gefen, Y., Potters, M. and Wyart, M. (2004).
  *Fluctuations and response in financial markets: the subtle nature of
  "random" price changes.* Quantitative Finance 4(2), 176-190. — order-sign
  autocorrelation decaying as a power law with exponent near 0.5.
- Almgren, R., Thum, C., Hauptmann, E. and Li, H. (2005). *Direct
  estimation of equity market impact.* Risk 18(7), 57-62. — temporary
  impact with an exponent near 3/5, estimated from institutional orders.
- Lillo, F., Mike, S. and Farmer, J. D. (2005). *Theory for long memory in
  supply and demand.* Physical Review E 71, 066122. — order splitting as
  the mechanism, with gamma = alpha - 1.
- Gatheral, J. (2010). *No-dynamic-arbitrage and market impact.*
  Quantitative Finance 10(7), 749-759. — the constraint linking the impact
  exponent to the decay kernel, with the square-root law as the
  empirically relevant case.
- Hill, B. M. (1975). *A simple general approach to inference about the tail
  of a distribution.* Annals of Statistics 3(5), 1163-1174. — the tail-index
  estimator used above.
