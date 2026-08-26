# lobster: validation against things outside itself

A simulator that only agrees with its own tests is a very elaborate way of
being wrong. This document is the other kind of check: every number below
came out of a process whose answer was fixed before the library saw it:
either a closed-form result, or a magnitude somebody else published.

Reproduce all of it with:

```sh
python examples/validate.py            # ~20 s
python examples/validate.py --quick    # ~4 s, coarser Monte Carlo
```

The raw output of the run this page was written from is pasted at the
bottom. Nothing here has been rounded in a flattering direction, and where
the library loses it says so. Three of the fourteen rows in Part 2 fail,
either outright or for one of the two agent mixes, and the failures are the
more useful half of the page.

**On the reference column.** Two kinds of number appear there. Some are
analytic: Roll's autocovariance identity, the impact exponent implied by a
depth profile, a Pareto tail index. Those are exact and the only question is
whether the estimator finds them. Others are empirical magnitudes from the
literature, cited by author and year at the bottom. Where a published figure
is a range or a rule of thumb it's written as one, and where I could not
vouch for a specific number in a specific paper I used the analytic ground
truth instead rather than invent a citation. Every source listed is one
whose result is stated in the text as attributed.

---

## Part 1: do the estimators find answers that are known in advance?

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
| mean VR(50), the finite-sample bias | 0.9779 | 1.0000 | Lo & MacKinlay (1988) |
| book-walk exponent, depth flat in distance | 1.0000 | 1.0000 | analytic |
| book-walk exponent, depth linear in distance | 0.5038 | 0.5000 | analytic |
| book-walk exponent, depth quadratic in distance | 0.3448 | 0.3333 | analytic |
| `SquareRootImpact`: impact(4Q)/impact(Q) | 2.000000000000 | 2 | analytic, exact |
| `SquareRootImpact`: impact(9Q)/impact(Q) | 3.000000000000 | 3 | analytic, exact |

Three things worth saying out loud about that table.

**Roll's estimator is unreasonably good.** Fed a process that's exactly
Roll's (an efficient price doing a random walk plus a half-spread times an
independent coin flip), `2*sqrt(-gamma1)` returns the spread it was given to
within 0.2% on 20,000 observations, across a factor of four in spread and
a factor of five in volatility. That's the whole content of the 1984 paper
and it survives contact with this implementation.

**The variance-ratio estimator here is biased low, and the bias grows with
the horizon.** At q=2 the mean over 1,500 random walks is 0.9997; at q=50 it
is 0.9779, more than two per cent below the null. This is expected and it's
not a defect of the random walks: `variance_ratio` uses plain population
variances with no small-sample correction, and the q-step differences
overlap, so roughly q/T of the variance is eaten by the end effects. Lo and
MacKinlay's own statistic carries a bias correction precisely for this. If
you're testing a null at long horizons on a short series, don't read a
`VR` of 0.98 as evidence of mean reversion. The *spread* of the sampling
distribution, on the other hand, matches their asymptotic formula to within
a few per cent at every horizon tested, which is the more delicate claim.

**The book walk finds the square-root law when the square-root law is
there.** Cumulative depth growing like distance-squared implies a price
displacement growing like sqrt(Q), and `cost_to_trade` measures 0.504
against the analytic 0.500. The residual is discretisation: the walk stops
at a level index, which is an integer. This matters for Part 2: when the
simulator's impact comes out at the wrong exponent, it isn't because the
exponent is being measured wrongly.

![impact](impact_law.png)

Panel (a) is that calibration. Panel (b) is the simulator, and the two
lines don't have the same slope.

---

## Part 2: does the simulator behave like a market?

Two agent mixes are scored: the bundled demo (two noise traders, a momentum
chaser, one market maker) and the same thing with the chaser removed, since
almost every disagreement below traces back to that one agent.

### Return distribution and volatility clustering

| claim | our value (demo / no chaser) | reference value | source | agrees |
|---|---|---|---|---|
| returns are heavy-tailed: excess kurtosis > 0 | 13.92 / 13.32 | positive, large | Cont (2001) | yes |
| tail index of \|r\| | 2.75 / 3.02 | 2 to 5 | Cont (2001) | yes |
| aggregational Gaussianity: kurtosis falls with aggregation | 2.70 vs 13.92 / 4.73 vs 13.32 | falls toward 0 | Cont (2001) | yes |
| returns are close to linearly uncorrelated | -0.0584 / -0.0586 | ~0 | Cont (2001) | no |
| volatility clustering: rho(\|r\|) at lag 1 | +0.1316 / +0.1154 | positive | Cont (2001) | yes |
| ... still positive at lag 100 | +0.0430 / +0.0399 | positive, slow decay | Cont (2001) | yes |
| decay exponent of rho(\|r\|) | 0.29 / 0.22 | below 1 | Cont (2001) | yes |

### Microstructure

| claim | our value (demo / no chaser) | reference value | source | agrees |
|---|---|---|---|---|
| bid-ask bounce: lag-1 autocorrelation of trade-price changes | -0.245 / -0.253 | in [-1/2, 0) | Roll (1984) | yes |
| order-flow sign memory: power-law exponent | 1.29 / 0.52 | ~0.5 | Bouchaud et al. (2004) | no / yes |
| order-flow memory horizon | 89 / 128 trades | thousands of trades | Bouchaud et al. (2004) | no |
| mean depth peaks away from the touch | 1.28 away, touch holds 5.2% / 5.4% of the peak | peak away from the touch | Bouchaud, Mezard & Potters (2002) | yes |
| a passive market maker is adversely selected | -0.01745 / -0.02974 | negative markout | Glosten & Milgrom (1985) | yes |
| metaorder cost exponent (net of half-spread) | 0.57 / 0.58 | 0.5 to 0.6 | Almgren et al. (2005); Gatheral (2010) | yes |
| metaorder peak-impact exponent | 0.54 / 0.60 | 0.5 to 0.6 | Almgren et al. (2005) | yes |

Across the two tables: eleven rows agree, two disagree outright, and one
agrees for one agent mix and not the other. The next section is about the
ones that aren't clean wins, because a validation document that only lists
its wins is a brochure.

---

## The row that used to fail, and what fixed it

Earlier versions of this document opened with a section titled *"Impact is
convex here and concave in the world. (The big one.)"* The metaorder cost
exponent came out between 1.23 and 1.47, meaning cost grew faster than
linearly in size, when the empirical square-root law puts it near 0.5. That
was the wrong sign of curvature, and Part 1c ruled out the estimator as the
culprit by recovering 0.504 from a book engineered to have a square-root law.

The diagnosis in that section was that nothing here replenished liquidity in
response to being consumed. Every agent quoted off the *mid*, so a parent
order that walked the book was chased by a market maker re-quoting around a
mid the parent had already moved. The section ended by naming the missing
piece: an informed trader with a view on value, who supplies liquidity into a
price it thinks is wrong.

`ValueAgent` is that trader. It ladders passive size around a fundamental
value, with size at each rung growing linearly with distance from it, and
tops the ladder up at a bounded rate. The shape is the whole mechanism:

    depth at distance d from value  ~  slope * d
    shares available within D       ~  slope * D^2 / 2
    so to buy Q you must walk       D ~ sqrt(2Q / slope)

which is the square-root law, and it's the same profile Part 1c already
showed the estimator scoring at 0.504. Partial resilience matters as much as
the shape. The ladder refills at `refill` shares per tick, so a parent that
consumes faster than that outruns replenishment and walks outward into the
thicker rungs. Cancel and replace the whole ladder every tick instead and the
book becomes perfectly elastic: price snaps back between children and impact
vanishes, which is as wrong as the convex answer in the other direction.
Raising `slope` or `refill` far enough does the same thing more gently, and
drives the exponent back toward 1.

Two measurement notes, because both change the answer:

* The fundamental random-walks (`value_drift`). Without it the price is
  pinned to a constant, `VR(100)` collapses to 0.04, excess kurtosis falls to
  4 and the tail index leaves the 2-to-5 band. Realistic returns need a
  moving efficient price.
* Once it moves, impact has to be measured against it. `execute_metaorder`
  takes a `reference` callable and reports cost net of wherever the efficient
  price wandered while the parent worked. Real studies do this against an
  index; a simulator can do it against the actual value the agents quote off.
  Skip the control and the same runs score 0.33 and -0.26 at a drift of 0.03,
  which is noise rather than a measurement.

The result is 0.57 and 0.58 for cost net of half-spread, 0.54 and 0.60 for
peak impact, across the two mixes. Those parameters were calibrated to land
there, which is worth saying plainly: the *mechanism* is what makes cost
concave at all, and `slope` and `refill` are what set where in the concave
range it lands.

Three other rows moved with it, none of them targeted. The tail index went
from 1.84 to 2.75 and entered Cont's band; aggregational Gaussianity started
holding for both mixes instead of one; and order-flow memory without the
chaser went from nothing at all to a decay exponent of 0.52, against the
0.5 the literature reports. That last one is the Lillo-Mike-Farmer mechanism
appearing by accident: a ladder consumed rung by rung is a split parent
order, which is exactly what they identify as the source of sign memory.

---

## Where this still doesn't match reality, and why

### 1. Order-flow memory is far too short.

Real trade signs stay positively autocorrelated out to thousands of trades,
decaying like a power law with exponent around 0.5 (Bouchaud, Gefen, Potters
and Wyart 2004). Lillo, Mike and Farmer (2005) show why: institutions split
parent orders, parent sizes are heavy-tailed with exponent alpha, and the
sign autocorrelation inherits gamma = alpha - 1.

Without the chaser the exponent is now 0.52, which is the right number. The
horizon is still wrong: memory is gone by lag 128, against thousands of
trades in real flow. And with the chaser in the mix the exponent is 1.29,
because a 20-trade lookback imposes its own timescale on top. The ladder
supplies persistence of the right shape at the wrong length, since its rungs
are consumed over tens of trades rather than the hours a real parent order
takes. Heavy-tailed parent sizes are the missing ingredient, and nothing here
draws one.

### 2. Returns are slightly negatively autocorrelated.

Cont's first stylized fact is that returns show no significant linear
autocorrelation. The lag-1 return autocorrelation here is -0.058 in both
mixes. It's small, and it's at least no longer the +0.098 the chaser used
to produce, but the sign is now systematic rather than absent: the value
trader pulls price back toward the fundamental, and that mean reversion shows
up at lag 1. `VR(100)` tells the same story from the other end, 0.45 and 0.43
against 1.0 for a random walk. The old failure was a price that trended too
much; this one is a price that reverts too much, and the honest reading is
that neither version has the balance right.

### 3. Volatility clustering is real here but for a thin reason.

The absolute-return autocorrelation is positive out to lag 100 with a decay
exponent of 0.29 (demo) and 0.22 (no chaser), which is the right shape and
the right order of magnitude. Don't read too much into it. There is no
stochastic-volatility mechanism in this simulator; the likeliest explanation
is that trading *activity* clusters, so bunched trades mean bunched price
changes. The empirical fact is generally attributed to something richer than
that, so this is the right answer arrived at by a shortcut, the same caveat
that applies to the humped depth profile in `theory.md` section 6.

### 4. Most returns are exactly zero.

About 61% of tick-to-tick mid returns in both mixes are exactly 0.0, because
the mid only moves when the touch does. This inflates kurtosis mechanically:
a distribution that's mostly a point mass at zero with occasional jumps has
enormous fourth moments regardless of what the jumps look like. The
excess-kurtosis figures in the first table should be read as "heavy-tailed,
directionally right, magnitude not comparable with a daily equity series".
Real tick data has the same property, which is one reason microstructure
work rarely quotes tick-return kurtosis without saying how it was sampled.

---

## What this means for using the package

The verdict hasn't changed since the scorecard in the README, it has just
got more precise. `lobster` is measurably sound as a **mechanism**: price-time
priority, queue position, spread and adverse-selection accounting, and the
cost of walking a book are all correct, and the estimators that measure them
recover known answers to within a per cent. It's measurably *not* a
realistic **price process**: order flow has no memory to speak of, the mid
trends when it should not, and impact curves the wrong way.

Use it for questions about the queue and about execution mechanics. Don't
use it to calibrate a cost model you intend to point at a real market.
`examples/execution_costs.py` shows the shape of that workflow deliberately
using the simulator's own convex exponent, and says in its own output that
the exponent isn't the one the literature reports.

---

## The run this document was written from

```
lobster: validation against external ground truth
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

  [demo mix]  99,999 tick returns, 60.7% of them exactly zero
  excess kurtosis of tick returns                            13.92   vs > 0 (heavy tailed)        yes
  Hill tail index of |r|, top 5%                              2.75   vs 2 to 5                    yes
  excess kurtosis, 100-tick aggregation                       2.70   vs < 13.92 (toward 0)        yes
  lag-1 autocorrelation of tick returns                    -0.0584   vs ~0 (Cont 2001)            no
  rho(|r|) at lag 1                                        +0.1316   vs > 0                       yes
  rho(|r|) at lag 100                                      +0.0430   vs > 0, slow decay           yes
  decay exponent of rho(|r|)                                  0.29   vs < 1 (long memory)         yes

  [no chaser]  99,999 tick returns, 63.3% of them exactly zero
  excess kurtosis of tick returns                            13.32   vs > 0 (heavy tailed)        yes
  Hill tail index of |r|, top 5%                              3.02   vs 2 to 5                    yes
  excess kurtosis, 100-tick aggregation                       4.73   vs < 13.32 (toward 0)        yes
  lag-1 autocorrelation of tick returns                    -0.0586   vs ~0 (Cont 2001)            no
  rho(|r|) at lag 1                                        +0.1154   vs > 0                       yes
  rho(|r|) at lag 100                                      +0.0399   vs > 0, slow decay           yes
  decay exponent of rho(|r|)                                  0.22   vs < 1 (long memory)         yes

2b. Microstructure facts (Roll 1984; Bouchaud et al. 2002, 2004)
----------------------------------------------------------------

  [demo mix]  80,706 trades
  lag-1 autocorrelation of trade-price changes              -0.245   vs in [-0.5, 0)              yes
  order-flow sign memory: decay exponent gamma                1.29   vs ~0.5                      no
  order-flow memory horizon, in trades                          89   vs thousands of trades       no
  depth peaks away from the touch             1.28 (5.2% at touch)   vs > 0 (humped)              yes
  market maker's passive markout, h=10                    -0.01745   vs < 0 (adversely selected)  yes

  [no chaser]  61,212 trades
  lag-1 autocorrelation of trade-price changes              -0.253   vs in [-0.5, 0)              yes
  order-flow sign memory: decay exponent gamma                0.52   vs ~0.5                      yes
  order-flow memory horizon, in trades                         128   vs thousands of trades       no
  depth peaks away from the touch             1.28 (5.4% at touch)   vs > 0 (humped)              yes
  market maker's passive markout, h=10                    -0.02974   vs < 0 (adversely selected)  yes

2c. The impact of a metaorder (Almgren et al. 2005; Gatheral 2010)
------------------------------------------------------------------
     a parent order worked in 8-lot children every other tick

  [demo mix]
    Q=   20  shortfall=+0.0577  net of half-spread=+0.0238  peak impact=+0.0309
    Q=   40  shortfall=+0.0768  net of half-spread=+0.0428  peak impact=+0.0526
    Q=   80  shortfall=+0.1047  net of half-spread=+0.0707  peak impact=+0.0805
    Q=  160  shortfall=+0.1384  net of half-spread=+0.1044  peak impact=+0.1164
    Q=  320  shortfall=+0.1847  net of half-spread=+0.1507  peak impact=+0.1433
    Q=  640  shortfall=+0.2325  net of half-spread=+0.1985  peak impact=+0.2395
    Q= 1280  shortfall=+0.3056  net of half-spread=+0.2716  peak impact=+0.3120
  exponent of shortfall incl. half-spread                     0.40   vs 0.5 to 0.6                yes
  exponent of shortfall net of half-spread                    0.57   vs 0.5 to 0.6                yes
  exponent of peak mid impact                                 0.54   vs 0.5 to 0.6                yes

  [no chaser]
    Q=   20  shortfall=+0.0565  net of half-spread=+0.0242  peak impact=+0.0291
    Q=   40  shortfall=+0.0672  net of half-spread=+0.0349  peak impact=+0.0334
    Q=   80  shortfall=+0.0836  net of half-spread=+0.0513  peak impact=+0.0492
    Q=  160  shortfall=+0.1099  net of half-spread=+0.0776  peak impact=+0.0936
    Q=  320  shortfall=+0.1585  net of half-spread=+0.1262  peak impact=+0.1504
    Q=  640  shortfall=+0.2149  net of half-spread=+0.1826  peak impact=+0.2198
    Q= 1280  shortfall=+0.2853  net of half-spread=+0.2530  peak impact=+0.2775
  exponent of shortfall incl. half-spread                     0.40   vs 0.5 to 0.6                yes
  exponent of shortfall net of half-spread                    0.58   vs 0.5 to 0.6                yes
  exponent of peak mid impact                                 0.60   vs 0.5 to 0.6                yes
```

The exponents in section 2c are fitted on parent orders held to a fixed
child size and a fixed cadence, so the execution horizon grows with the
parent: that is the size law, and it comes out concave at 0.57 and 0.58,
inside the published 0.5 to 0.6 band. `examples/execution_costs.py` fits
the other law, at a fixed horizon with a varying participation rate, and
gets 1.39: convex, because a bigger parent there means trading faster
rather than trading for longer. One simulator, two curves, and the sign of
the curvature depends on which one you asked for.

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
- VR(q) equals 1 + 2*sum_k (1-k/q) rho_k, the identity it's defined by
- excess kurtosis returns 0 for a Gaussian, -1.2 for a uniform, 3 for a Laplace
- Hill's estimator recovers the alpha a Pareto sample was drawn with
- a power-law fit inverts an exact power law
- linear impact is homogeneous of degree 1, square-root of degree 1/2,
  and the square-root model is strictly concave
- latency samples are non-negative with the advertised mean

---

## References

- Roll, R. (1984). *A simple implicit measure of the effective bid-ask
  spread in an efficient market.* Journal of Finance 39(4), 1127-1139. The
  serial-covariance identity and the implied-spread estimator.
- Glosten, L. and Milgrom, P. (1985). *Bid, ask and transaction prices in a
  specialist market with heterogeneously informed traders.* Journal of
  Financial Economics 14(1), 71-100. The spread as compensation for
  adverse selection.
- Lo, A. W. and MacKinlay, A. C. (1988). *Stock market prices don't follow
  random walks: evidence from a simple specification test.* Review of
  Financial Studies 1(1), 41-66. The variance-ratio statistic and its
  sampling distribution under the random-walk null.
- Cont, R. (2001). *Empirical properties of asset returns: stylized facts
  and statistical issues.* Quantitative Finance 1(2), 223-236. Heavy
  tails with a tail index between 2 and 5, absence of linear
  autocorrelation, aggregational Gaussianity, and volatility clustering.
- Bouchaud, J.-P., Mezard, M. and Potters, M. (2002). *Statistical
  properties of stock order books: empirical results and models.*
  Quantitative Finance 2(4), 251-256. The mean book shape peaking away
  from the touch.
- Bouchaud, J.-P., Gefen, Y., Potters, M. and Wyart, M. (2004).
  *Fluctuations and response in financial markets: the subtle nature of
  "random" price changes.* Quantitative Finance 4(2), 176-190. Order-sign
  autocorrelation decaying as a power law with exponent near 0.5.
- Almgren, R., Thum, C., Hauptmann, E. and Li, H. (2005). *Direct
  estimation of equity market impact.* Risk 18(7), 57-62. Temporary
  impact with an exponent near 3/5, estimated from institutional orders.
- Lillo, F., Mike, S. and Farmer, J. D. (2005). *Theory for long memory in
  supply and demand.* Physical Review E 71, 066122. Order splitting as
  the mechanism, with gamma = alpha - 1.
- Gatheral, J. (2010). *No-dynamic-arbitrage and market impact.*
  Quantitative Finance 10(7), 749-759. The constraint linking the impact
  exponent to the decay kernel, with the square-root law as the
  empirically relevant case.
- Hill, B. M. (1975). *A simple general approach to inference about the tail
  of a distribution.* Annals of Statistics 3(5), 1163-1174. The tail-index
  estimator used above.
