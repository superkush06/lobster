# lobster: the reasoning behind the code

`design.md` says what the simulator does. This says why it's worth doing
that way, and what the numbers it prints actually mean. Every figure quoted
below comes from a run you can reproduce: `examples/scorecard.py` prints the
stylized-facts verdicts *and* the spread block (the lag-1 autocovariance of
trade-price changes, Roll's implied spread, the time-averaged and
at-the-trade quoted spreads, and the variance ratios), and
`examples/make_figures.py` draws the plots. `validation.md` is the separate
question of whether any of it matches published measurements, and
`examples/validate.py` produces those numbers.

---

## 1. The queue is the model

A limit order book isn't a price. It's two priority queues, and almost
everything interesting about electronic markets follows from how you get to
the front of one.

Under price-time priority a resting order is served after every order at a
better price, and after every order at the same price that arrived earlier.
So an order's fate is determined by one number: the volume resting ahead of
it at its own level, $Q_{\text{ahead}}$. If aggressive volume arrives and
the queue in front is never cancelled, the order fills once cumulative
incoming volume exceeds $Q_{\text{ahead}}$. Cancellations ahead help you;
new arrivals behind you don't.

This is why the book here stores a `deque` of individual `Order` objects per
`PriceLevel` rather than a single aggregated size. Aggregate depth is enough
to compute a mid, a spread or an imbalance; it isn't enough to answer *will
my order fill*, which is the question the package exists for.
`Analytics.queue_position` is the corresponding one-liner, and the
alternative, reconstructing queue position from L2 depth snapshots, is a
well-known source of quiet error in backtests.

Two consequences shape the rest of the design:

- **Matching must be the only path to a fill.** `OrderBook.add()` rejects an
  order that crosses the opposite side, because a book that's allowed to
  cross has a negative spread and a meaningless mid, and every statistic
  downstream inherits the nonsense. Marketable orders go through `match()`.
- **Trades must carry identity.** A `Trade` records `buyer_id` and
  `seller_id` (agent, not order) so P&L, markout and self-trade detection
  are all computable from the tape alone.

---

## 2. Latency is what makes queue position a question

Consider two market makers reacting to the same event at time $t$, both
wanting to quote at the same price. Maker A's order reaches the engine at
$t + \delta_A$, maker B's at $t + \delta_B$. If $\delta_A < \delta_B$ then A
is inserted into the FIFO queue first, at every level, on every re-quote,
and stays in front until it fills or cancels. Latency doesn't buy a better
price; it buys a place in line, and the value of that place is the whole
economics of passive trading.

A synchronous loop, in which every agent acts once per tick in shuffled
order, can't express this. Whoever the shuffle happens to pick goes first, so
"who re-quotes faster" isn't a variable of the model. That's why
`Simulation` keeps a `heapq` of arrival events keyed on
$t + \texttt{latency.sample(rng)}$ and drains it in timestamp order.
Agents with no latency model submit instantly, which reproduces the old
synchronous behaviour exactly; `ConstantLatency(0)` consumes no randomness
and is bit-identical to it.

`examples/latency_race.py` puts two identical makers on different wires
(constant 0.05 and 0.15 time units) and measures three things over 4,000
ticks:

| | front-of-queue share | passive volume | markout $h{=}10$ |
|---|---|---|---|
| fast (0.05) | 72.7% | 2,872 | $-0.00019$ |
| slow (0.15) | 27.3% | 698 | $-0.00422$ |

Three times the speed buys roughly four times the passive volume. The first
two columns replicate across seeds; the third does not, and §7 works through
why the single-seed ratio in it is not a result.

---

## 3. Roll (1984): what the bounce tells you

Write the observed transaction price as an efficient price plus a
half-spread paid to whoever provided liquidity:

$$p_t = m_t + c\,q_t, \qquad q_t = \pm 1 \ \text{iid}, \qquad c = s/2,$$

with $m_t$ a random walk of per-trade variance $\sigma^2$, independent of
the trade signs. Then

$$\Delta p_t = \Delta m_t + c\,(q_t - q_{t-1}),$$
$$\operatorname{Var}(\Delta p) = \sigma^2 + 2c^2, \qquad
\operatorname{Cov}(\Delta p_t, \Delta p_{t-1}) = -c^2,$$

and all higher-order autocovariances vanish. Two things fall out.

**The spread is observable from trade prices alone.** The first
autocovariance doesn't depend on $\sigma^2$ at all, so
$\hat{s} = 2\sqrt{-\gamma_1}$ estimates the spread even when you never saw a
quote. On the demo mix over 100,000 ticks, $\gamma_1 = -0.003319$, giving
$\hat{s} = 0.1152$. The book's own time-averaged quoted spread over the same
run is $0.1915$, and the mean spread *at the ticks where a trade printed*
is $0.2117$: crossing flow still arrives preferentially when the book is
wide. Roll recovers roughly half of the spread actually paid, and the
shortfall is instructive rather than embarrassing. The estimator prices the
*alternation*, and with trade signs as persistent as §5 measures,
consecutive prints on the same side contribute no bounce to $\gamma_1$,
while a chunk of the quoted spread is never crossed at all. An estimator
imported with its assumptions attached measures its model, not the book.

**The autocorrelation is bounded.**

$$\rho_1 = \frac{-c^2}{\sigma^2 + 2c^2} \in [-\tfrac12, 0],$$

reaching $-1/2$ only when the efficient price doesn't move between trades.
Measured: $-0.253$ without the momentum agent, $-0.245$ with it. That gap
used to be wide, and its collapse is informative. Inverting the formula,
both mixes now carry about the same genuine price innovation per trade,
$\sigma \approx 0.70\,s$ and $0.72\,s$: the fundamental's own random walk,
which the value ladder transmits into the book, dominates the efficient
price in either mix, and the chaser's contribution on top of it is
marginal.

None of this is a property of a simulator. It's why a trade-price series
sampled tick-by-tick is a terrible estimate of volatility, and why
microstructure work almost always uses mid prices.

---

## 4. Variance ratios: mean reversion at one horizon, trends at another

$$VR(q) = \frac{\operatorname{Var}(p_t - p_{t-q})}{q \operatorname{Var}(p_t - p_{t-1})}
        = 1 + 2\sum_{k=1}^{q-1}\Big(1 - \frac{k}{q}\Big)\rho_k .$$

A random walk gives $VR \equiv 1$. Below 1 means mean reversion, above 1
means trending, and the identity says the whole curve is just a weighted
sum of autocorrelations, so §3 already determines its left end. With
$\rho_1 = -0.245$ and $\rho_{k>1} \approx 0$, the model predicts
$VR(2) = 1 + \rho_1 = 0.755$; the measured value is $0.755$.

The full curves say something the single number cannot:

- **Trade prices** start at $0.755$ and only fall: $0.41$ by $q = 5$,
  $0.14$ by $q = 20$, $0.06$ by $q = 100$. Bounce dominates the short end,
  and instead of a drift taking over at long horizons, the value anchor's
  mean reversion compounds on top of it, so the curve never climbs back
  through 1. Nothing in this market trends.
- **Mid prices** have no bounce in them, and they sub-diffuse:
  $VR(100) = 0.45$ with the momentum agent and $0.43$ without it. The value
  trader pulls price back toward its fundamental, so the mid mean reverts.

$VR(100) = 0.45$ is a failing grade, and it is worth being blunt about why.
An earlier version of this package scored $10.6$, badly *super*-diffusive:
the chaser read imbalance off the tape and printed on the same tape, and
nothing pushed back. `ValueAgent` is that pushback, and it overshot. Real
markets have it in a measure this one does not: statistical
arbitrageurs, informed traders with a level in mind, hedgers
selling into strength. This one does not. See §10.

---

## 5. Long memory of order flow

The sequence of trade signs is one of the most robustly autocorrelated
series in finance: $\rho(\ell) \sim \ell^{-\gamma}$ with $\gamma \approx
0.5$, positive out to thousands of trades, on every liquid instrument
anyone has looked at. $\gamma < 1$ makes the sum $\sum_\ell \rho(\ell)$
divergent, which is the textbook definition of long memory.

The mechanism is not herding. It is **order splitting**: a fund with a
million shares to buy does not send a million-share order, it sends
thousands of small ones over hours, all with the same sign. Lillo, Mike and
Farmer showed that if parent-order sizes follow a power law with exponent
$\alpha$, the resulting sign autocorrelation inherits $\gamma = \alpha - 1$.
Long memory in the tape is the shadow of a heavy-tailed distribution of
trading intentions.

`lobster` reproduces the shape over a horizon far shorter than the real one.
Without the momentum agent the fitted decay exponent is $0.52$, against the
$\gamma \approx 0.5$ of real flow, and the sign autocorrelation stays
positive out to lag 128. The source is `ValueAgent`: a ladder eaten rung by
rung is a split parent order, which is the Lillo-Mike-Farmer mechanism. Add
the chaser back and its 20-trade window imposes its own timescale, pushing
the exponent to $1.29$ and killing the memory by lag 89.

That is the correct diagnosis of a modelling gap. Memory here comes from one
agent with a 20-trade window, so it necessarily dies at a horizon set by
that window. Getting the real thing requires an agent with a *parent
order*: a target quantity drawn from a heavy-tailed distribution, worked in
child slices over many ticks. That is the single highest-value agent this package
does not have.

---

## 6. The shape of the book

Average resting size is not largest at the touch. It rises with distance
from the mid, peaks a few ticks out, and decays, a shape Bouchaud, Mézard
and Potters derived and measured in 2002. The intuition is adverse
selection: sitting at the touch is where you get run over, so liquidity
providers post size where the price has to travel to reach them.

The measured profile is humped, peaking $1.28$ away from the mid while the
mean half-spread is only $0.0957$; the innermost bin holds about 5% of the
peak's size. But be careful what that buys. Here the hump's *location* is
set by the quoting kernels: `NoiseAgent(spread_offset=0.6)` sampling a
uniform offset, `MarketMakerAgent(half_spread=0.4)` posting at a fixed
distance, and the value ladder refilling rungs every $0.05$ out to $2.0$
with size growing in the rung index. It is a property of those parameters,
not an emergent response to adverse
selection. Change them and the peak moves with them. The right
shape for the wrong reason is still worth knowing; it is not worth
overselling.

---

## 7. Adverse selection and markout

Glosten and Milgrom: a market maker quoting to an anonymous flow that
contains some informed traders loses to the informed and must charge
everyone else for it. The spread is not a fee, it is compensation.

The empirical handle is the **markout**. For each fill, take the signed mid
move over the next $h$ observations:

$$\text{markout}(h) = \frac{1}{N}\sum_{i} \epsilon_i\,(m_{t_i + h} - m_{t_i}),
\qquad \epsilon_i = +1 \text{ if the agent bought}.$$

Negative means the price systematically moves against the maker right after
it trades, which is what being picked off means. `Analytics.markout` defaults to
`passive_only=True` because only the fills where the agent *provided*
liquidity are the ones the spread is supposed to pay for; including its own
aggressive trades measures a different thing entirely.

Two details matter in implementation. Fills are anchored to the latest
metrics row at or before the fill timestamp, so latency-delayed arrivals
landing between ticks are still counted rather than silently dropped. And
the horizon is in metric samples, not trades, so it is comparable across
runs with different trade intensity.

In the latency race the fast maker's markout is $-0.00019$ against the slow
maker's $-0.00422$, which reads as a factor of twenty. It is one seed. Over
seeds 1 to 12 at the same configuration
(`examples/latency_race.py --steps 4000 --seeds 1-12`) the means are
$-0.0134$ and $-0.0122$, the fast maker is ahead in 6 runs of 12, and the
gap has a standard deviation of $0.0265$ against a mean of $-0.0012$, so
$t = -0.16$ on 11 degrees of freedom: twelve seeds cannot call it. Sixty
seeds can, and they call it against the fast maker: gap mean $-0.0092$,
standard deviation $0.0223$, $t = -3.19$.

That sign is the interesting one. The standard story says the fast maker
holds the front of the queue in ordinary conditions, while the slow maker
fills mainly once the queue ahead of it has been consumed, which is exactly
when something large is walking the book. What the sweep measures is the
queue half (unambiguous: the fast maker holds 70% to 77% of front-of-queue
ticks and five times the passive volume) and a markout that is worse for
the maker who stands at the front: first in queue is first to be filled by
the flow that moves the price. Separating how much of that is adverse
selection against the front of the queue, rather than volume composition,
would need an agent whose informed flow is labelled.

---

## 8. Impact: linear is not the same as square-root

Two impact estimators ship here, and they answer different questions.

**Linear**, $\Delta p = \eta Q$. This is the form in Almgren–Chriss (2001),
where temporary impact is linear in the *trading rate* and the resulting
optimal-execution problem has a closed-form solution. Linearity is a
modelling convenience that makes the mathematics tractable, not an empirical
claim.

**Square-root**, $\Delta p = \eta \sqrt{Q/V}$. This is an empirical
regularity: the impact of a metaorder of size $Q$ against daily volume $V$
scales as $\sqrt{Q/V}$, remarkably stably across markets, decades and asset
classes. In full-strength form it carries a volatility scale,
$\Delta p \approx Y \sigma \sqrt{Q/V}$ with $Y = O(1)$; here $\eta$ absorbs
$Y\sigma$ and is left as a free parameter. Doubling size raises impact by
$\sqrt2$, not 2, which is why splitting a parent order across venues does
not help nearly as much as a linear model suggests.

Neither model is applied by the matching engine. Impact inside the simulator
is *emergent*: a market order eats through resting depth and the touch moves
because the levels it consumed are gone. These estimators are for pre-trade
sizing, and keeping them out of the engine keeps the engine honest.

The emergent impact is measurable, and it comes out concave.
`lobster.execution` walks the book read-only (`cost_to_trade`) and works
parent orders into a live run (`execute_metaorder`); fitting a power law to
the resulting shortfall gives an exponent of $0.57$, against the $0.5$ to
$0.6$ of published metaorder studies. It depends entirely on `ValueAgent`
being in the mix. Take the value trader out and the same fit returns 1.2 to
1.5, convex, because nothing then regenerates liquidity in response to being
consumed. `validation.md` has the numbers, the mechanism and the
calibration.

---

## 9. What the microprice is, and what it is not

`OrderBook.microprice` is the size-weighted mid: each side's price weighted
by the *opposite* side's top-of-book size, so a heavy bid pulls the estimate
toward the ask.

$$p_{\text{micro}} = \frac{P_b V_a + P_a V_b}{V_a + V_b}.$$

It's a useful one-line imbalance proxy and it is *not* Stoikov's
micro-price. Stoikov (2018) constructs a Markov-chain estimator of
$\lim_{t\to\infty}\mathbb{E}[m_{t}]$ precisely because the weighted mid is a
biased predictor of the future mid, over-reacting to imbalance when the
spread is wide. Calling the weighted mid "the microprice" is a common
mislabelling and it's worth not repeating.

---

## 10. What this simulator isn't

Stated plainly, because the scorecard makes it measurable:

- **One informed trader, and only by another name.** `ValueAgent` has a
  level in mind and anchors the price to it, too hard: the mid mean reverts
  ($VR(100) \approx 0.45$, §4) instead of following a random walk. No agent
  carries private information about a *future* price, because no such
  future exists here to know about; markout comes from momentum and the
  anchor, not information.
- **Parent orders only by another name.** The value ladder's refill is a
  split parent order in effect, which is why order-flow memory has the
  right sign without the published thousands-of-trades horizon (§5).
- **No tick size.** Prices are floats rounded to two decimals at agent
  boundaries. Real venues quantise to a tick, and queue dynamics at the
  touch depend on it heavily.
- **Cancels are instantaneous.** Only submissions pay latency, so the
  cancel-race, pulling a stale quote before it's picked off, isn't
  modelled. This flatters fast agents.
- **One symbol.** No cross-asset flow, no lead-lag.

---

## References

- Roll, *A simple implicit measure of the effective bid–ask spread in an
  efficient market* (1984)
- Glosten, Milgrom, *Bid, ask and transaction prices in a specialist market
  with heterogeneously informed traders* (1985)
- Lo, MacKinlay, *Stock market prices don't follow random walks: evidence
  from a simple specification test* (1988)
- Cont, *Empirical properties of asset returns: stylized facts and
  statistical issues* (2001)
- Bouchaud, Mézard, Potters, *Statistical properties of stock order books*
  (2002)
- Bouchaud, Gefen, Potters, Wyart, *Fluctuations and response in financial
  markets: the subtle nature of "random" price changes* (2004)
- Lillo, Mike, Farmer, *Theory for long memory in supply and demand* (2005)
- Almgren, Chriss, *Optimal execution of portfolio transactions* (2001)
- Almgren, Thum, Hauptmann, Li, *Direct estimation of equity market impact*
  (2005)
- Gatheral, *No-dynamic-arbitrage and market impact* (2010)
- Cont, Stoikov, Talreja, *A stochastic model for order book dynamics* (2010)
- Stoikov, *The micro-price: a high-frequency estimator of future prices*
  (2018)
- Gould, Porter, Williams, McDonald, Fenn, Howison, *Limit order books*
  (2013), a survey
- Bouchaud, Bonart, Donier, Gould, *Trades, Quotes and Prices* (2018)
