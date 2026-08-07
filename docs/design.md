# lobster — design notes

What the simulator does and the invariants it holds. For *why* — the
derivations, the estimators and the honest reading of what the dynamics do
and do not reproduce — see [`theory.md`](theory.md).

## Modeling assumptions

- **Discrete decision-time, continuous arrival-time.** Each step is one
  "tick" where every agent gets a chance to decide. Within a tick, agent
  decision order is shuffled to avoid systematic priority bias. Orders from
  agents *with a latency model* are then queued and delivered to the
  matching engine at `decision_ts + latency.sample(rng)`, processed in
  arrival-timestamp order from a heap — so two agents reacting to the same
  tick race to the book, and time priority goes to the faster one. Agents
  without a latency model submit instantly (the synchronous degenerate
  case; `ConstantLatency(0)` is bit-identical to it). See
  `examples/latency_race.py` for the canonical two-maker race.
- **Price-time priority** matching. Within a price level, orders fill in
  FIFO order. Across price levels, best price wins.
- **Self-trade prevention** (`Simulation(stp="cancel_resting")`, default):
  an agent whose marketable order would cross its own resting quote cancels
  the resting quote instead of printing a wash trade, the way real venues
  do. `stp="cancel_taker"` discards the incoming remainder instead;
  `stp=None` disables prevention (match() alone also defaults to none).
- **Order TTL**: `Order.ttl` is an optional lifetime; the sim cancels the
  resting remainder once it expires. `NoiseAgent` quotes default to
  `ttl=50` ticks so passive flow does not thicken the book without bound.
- **No fees / taxes**. Agent P&L is cash + inventory * last_mid.
- **Partial cancels** are supported via `OrderBook.reduce(order_id, qty)`
  (used by replay for LOBSTER type-2/type-4 events); `cancel(order_id)`
  removes the entire resting order.
- **No iceberg/hidden orders**. All resting size is visible.
- **Crossed books are rejected**: `OrderBook.add()` raises on an order that
  crosses the opposite side — route marketable orders through `match()`.
  Replay opts out (`allow_crossed=True`) because an externally observed
  feed with incomplete pre-window context can transiently look crossed.
- **Impact models are standalone estimators** (pre-trade analysis); the
  matching engine never applies them. Impact in the simulator is emergent
  from orders eating through book depth.

## Invariants

- `OrderBook._index` is consistent with the per-side level structures:
  every id in `_index` corresponds to exactly one resting order in exactly
  one level on the side recorded in `_index[id]`.
- For bids, `_bid_prices` stores negated prices so that `bisect.insort`
  works ascending on both sides. The same idx maps to `_bids[idx]`.
- After every `match()`, no level has an empty `orders` deque (cleanup is
  done inside the matching loop).
- With `stp` enabled, no trade on the tape has `buyer_id == seller_id`
  (asserted in tests via `Analytics.wash_trade_fraction() == 0`).

## Numerics

- Prices are floats. Real exchanges use scaled integers (tick-size aware).
  Rounded to 2 decimals at agent boundaries to avoid float-precision
  artifacts in tests. A future revision may switch to `int` ticks.
- Latency uses `random.Random` (Mersenne-Twister); not cryptographically
  random but reproducible. Constant latencies consume no randomness, so
  `ConstantLatency(0)` runs are bit-identical to latency-free runs.

## Replay fidelity

- A cold-start replay of a real LOBSTER message file references orders
  resting before the capture window. Those events are **counted** in
  `ReplayStats` (`unknown_execs` / `unknown_cancels` / `unknown_deletes`)
  rather than silently dropped; `strict=True` raises on the first one.
  If any unknown counter is non-zero, reconstructed depth has drifted.
- Seed the opening book from the companion orderbook file with
  `OrderBook.from_snapshot(bids, asks)` (one synthetic order per level).
  Note that snapshot seeding fixes opening *depth* but pre-window order
  ids still cannot be matched individually.
- Replay reconstructs the *visible* book only; hidden-order executions
  (type 5) and auction crosses (type 6) do not change the visible book.

## Stylized facts

`lobster/stylized.py` measures four canonical microstructure diagnostics off
a finished run, and `examples/scorecard.py` grades them against stated
thresholds. Over 100,000 ticks of the bundled demo config:

| fact | verdict | evidence |
|---|---|---|
| bid-ask bounce in trade prices | reproduced | lag-1 autocorrelation of trade-price changes = -0.245, against Roll's floor of -1/2 |
| humped depth profile | reproduced | mean depth peaks 1.28 from the mid; the innermost bin holds 5.2% of the peak |
| long memory of order flow | partial | decay exponent 0.52 without the chaser, against a published 0.5, but gone by lag 128 where real flow lasts thousands of trades |
| mid price is a martingale | fails | VR(100) = 0.45 with the momentum agent, 0.43 without it |

An earlier version of this table named the common cause of its failures:
there was no agent with a *view*, so nothing anchored the price and nothing
worked a parent order over many ticks. `ValueAgent` supplies the first half
of that. It ladders passive size around a fundamental with depth growing
linearly in distance, which is what turned metaorder cost from convex to
concave, and being consumed rung by rung it also gives order-flow memory the
right decay exponent.

It overshot on the price process. The martingale row failed super-diffusively
before (VR 10.6) and now fails sub-diffusively (0.45), because the ladder
pulls price back toward its fundamental harder than a real book does. A
metaorder agent drawing heavy-tailed parent sizes is the remaining addition,
and it is what the memory *horizon* needs.

The depth hump deserves the same caution. Its location tracks
`NoiseAgent(spread_offset=...)` and `MarketMakerAgent(half_spread=...)`
rather than emerging from adverse selection, so it is the right shape
obtained the wrong way.

Figures: `python examples/make_figures.py` writes `docs/book_depth.png`,
`docs/stylized_facts.png`, `docs/latency_race.png` and `docs/impact_law.png`,
all from live runs.

## Validation

The table above is the simulator grading itself. [`validation.md`](validation.md)
is the separate exercise of grading it against answers fixed elsewhere:
closed-form results (Roll's autocovariance identity, the impact exponent a
given depth profile implies, a Pareto tail index) and published empirical
magnitudes. `examples/validate.py` produces every number in it.

Two results from there bear on the design directly. The estimators in
`stylized.py` and `execution.py` recover known answers to within a per cent,
except `variance_ratio`, which is biased low by roughly q/T because it uses
population variances with no small-sample correction — read `VR` at long
horizons on short series with that in mind. And emergent impact in this
simulator is concave in size at a fitted exponent of 0.57, against published
metaorder estimates of 0.5 to 0.6. That depends on `ValueAgent` being in the
mix: it is the only thing here that replenishes liquidity in response to
being consumed, and without it the exponent is 1.2 to 1.5.

## Execution costs

`execution.py` sits beside the analytics rather than inside the engine.

- `cost_to_trade(book, side, qty)` walks the resting book **without
  mutating it** and reports what a market order would pay, the mid it would
  leave behind, and whether the book had enough depth. It is asserted in the
  property tests to agree exactly with running the same order through
  `match()`.
- `execute_metaorder(sim, ...)` works a parent order into a *running*
  simulation in child slices, so the book refills between children and the
  other agents react. This is the object comparable with the empirical
  impact literature; a single sweep of a static book is not.
- `fit_power_law(xs, ys)` is the log-log OLS both are summarised by.

## Known limitations

- No iceberg/hidden orders.
- Cancels are instantaneous (only order *submissions* pay latency); a
  fully latency-faithful cancel path would also delay cancel-replace.
- No multi-symbol support; one book per `Simulation`.
- Greedy partial fills — no pro-rata allocation. Real exchanges may use
  pro-rata for some products; future work.
- `microprice` is the size-weighted mid, a proxy — not Stoikov's
  Markov-chain micro-price estimator.
- No tick size: prices are floats rounded to two decimals at agent
  boundaries, so queue dynamics at the touch are less granular than a real
  venue's.
- No agent trades on a view of value, and none works a parent order over
  time. See the stylized-facts table above for what that costs.

## References

Fuller discussion and derivations in [`theory.md`](theory.md).

- Roll — *A simple implicit measure of the effective bid-ask spread* (1984)
- Bouchaud, Mezard, Potters — *Statistical properties of stock order books*
  (2002) — the humped depth profile
- Lillo, Mike, Farmer — *Theory for long memory in supply and demand* (2005)
- Cont, Stoikov, Talreja — *A stochastic model for order book dynamics* (2010)
- Almgren, Chriss — *Optimal execution of portfolio transactions* (2001) —
  linear-impact optimal execution (contrast with the square-root law)
- Gatheral — *No-dynamic-arbitrage and market impact* (2010) — the
  square-root impact law
- Stoikov — *The micro-price: a high-frequency estimator of future prices*
  (2018)
- Gould et al. — *Limit order books* (2013) — a comprehensive survey
