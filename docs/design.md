# lobster — design notes

## Modeling assumptions

- **Discrete event-time** simulation. Each step is one "tick" where every
  agent gets a chance to submit orders. Within a tick, agent submission
  order is shuffled to avoid systematic priority bias.
- **Price-time priority** matching. Within a price level, orders fill in
  FIFO order. Across price levels, best price wins.
- **No fees / taxes**. Agent P&L is cash + inventory * last_mid.
- **No partial cancels**. `cancel(order_id)` removes the entire resting order.
- **No iceberg/hidden orders**. All resting size is visible.
- **No exchange-side checks**. The book accepts any priced order; agents are
  responsible for sane pricing.
- **Latency models** are provided but not yet wired into the default
  `Simulation` step loop — they sit alongside `match()` for use in custom
  loops. (See `examples/` for a custom loop.)

## Invariants

- `OrderBook._index` is consistent with the per-side level structures:
  every id in `_index` corresponds to exactly one resting order in exactly
  one level on the side recorded in `_index[id]`.
- For bids, `_bid_prices` stores negated prices so that `bisect.insort`
  works ascending on both sides. The same idx maps to `_bids[idx]`.
- After every `match()`, no level has an empty `orders` deque (cleanup is
  done inside the matching loop).

## Numerics

- Prices are floats. Real exchanges use scaled integers (tick-size aware).
  Rounded to 2 decimals at agent boundaries to avoid float-precision
  artifacts in tests. A future revision may switch to `int` ticks.
- Latency uses `random.Random` (Mersenne-Twister); not cryptographically
  random but reproducible.

## Known limitations

- No iceberg/hidden orders, no STP, no self-trade prevention.
- No multi-symbol support; one book per `Simulation`.
- Greedy partial fills — no pro-rata allocation. Real exchanges may use
  pro-rata for some products; future work.
- No latency-aware order routing. Latency models exist but are not wired
  into the agent submission path.

## References

- Cont, Stoikov, Talreja — *A stochastic model for order book dynamics* (2010)
- Almgren, Chriss — *Optimal execution of portfolio transactions* (2001)
- Gould et al. — *Limit order books* (2013) — a comprehensive survey
