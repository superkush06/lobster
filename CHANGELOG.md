# Changelog

## [0.5.0] - 2026-07-27

### Added
- **`docs/validation.md`**: the library checked against answers fixed
  outside it. Part 1 feeds the estimators processes with closed-form
  answers. Roll's implied spread recovers a spread of 0.10 as 0.09987, the
  variance-ratio sampling s.d. matches Lo and MacKinlay's asymptotic formula
  to 0.07% at q=2, and the book walk recovers an exponent of 0.5038 from a
  book built to have a square-root impact law. Part 2 scores the simulator
  against published stylized facts and reports the seven rows that fail
  alongside the seven that pass.
- **`examples/validate.py`**: produces every number in that document, in
  about twenty seconds (`--quick` for four). The doc pastes its output
  verbatim.
- **`lobster.execution`**: `cost_to_trade` walks the resting book read-only
  and reports what a market order would pay and the mid it would leave
  behind; `execute_metaorder` works a parent order into a running simulation
  in child slices and reports implementation shortfall, peak and permanent
  impact; `fit_power_law` is the log-log OLS both are summarised by.
- **`lobster.stylized` return diagnostics**: `log_returns`, `aggregate`,
  `excess_kurtosis`, `hill_tail_index` and a `ReturnFacts` report covering
  heavy tails, aggregational Gaussianity and volatility clustering.
- **`examples/execution_costs.py`**: calibrates a participation-based cost
  curve off simulated metaorders and hands it to an inlined three-asset
  mean-variance problem, which then declines to rebalance the whole way.
  Nothing is imported from the sibling repos; the upstream inputs are
  written out in the file.
- **`docs/impact_law.png`**: the estimator recovering known exponents beside
  the simulator missing the published one. Rendered by
  `examples/make_figures.py impact`.
- **Randomized property tests** (`tests/test_properties.py`,
  `tests/test_estimator_properties.py`): conservation of quantity and cash,
  price-time priority, index consistency, monotone fill prices, STP and TTL
  guarantees, seed determinism, and the estimators against Pareto, Laplace
  and exact power-law ground truth.

### Changed
- `examples/scorecard.py` now prints the spread block `docs/theory.md`
  quotes (gamma_1, Roll's implied spread, the time-averaged and
  at-the-trade quoted spreads, and the variance ratios), so every statistic
  in the docs comes from a shipped command.
- README no longer quotes machine-specific throughput figures; run
  `benchmarks/throughput.py` for yours. The panel-by-panel section is plain
  text rather than inline LaTeX.
- `docs/theory.md` §5 states how closely the sign autocorrelation actually
  tracks the empirical reference (about half of it at short lags) instead of
  saying "closely", and §8 records the measured emergent impact exponent.

## [0.4.0] - 2026-07-27

### Added
- **`lobster.stylized`**: four canonical microstructure diagnostics measured
  off a finished run: bid-ask bounce (lag-1 autocorrelation of trade-price
  changes), long memory of order flow (trade-sign autocorrelation, its
  power-law exponent and the lag at which it dies), variance ratios for
  both trade and mid prices, and the mean depth profile as a function of
  distance from the mid. `StylizedFacts.measure()` returns all four;
  `summary()` reduces them to headline numbers.
- **`examples/scorecard.py`**: grades the bundled demo config against those
  four facts, twice, with and without the momentum agent, so each verdict
  comes with the ablation that explains it. Two of the four fail, which is
  reported rather than tuned away.
- **`examples/make_figures.py`**: renders every figure in the README from
  live simulations: the depth-through-time heatmap, the stylized-facts
  scorecard, and the latency race. Replaces `render_hero.py`.
- **`docs/theory.md`**: derivations behind the code. Queue position and fill
  probability, why latency buys time priority, Roll's bounce and the
  implied-spread estimator (which recovers 0.4230 against a measured
  trade-time spread of 0.4505), the variance-ratio identity, order splitting
  as the source of long memory, Glosten-Milgrom and markout, and why linear
  impact is not the square-root law.

### Changed
- README leads with the order book itself rather than a price line, and
  every claim about realism now carries the measurement behind it.
- `docs/design.md` gains a stylized-facts section and points at `theory.md`
  for the reasoning.

## [0.3.0] - 2026-07-20

### Added
- **Event-driven latency**: agents accept a `latency` model; orders arrive
  `latency.sample(rng)` after the decision and are matched in arrival-time
  order from an event heap. `ConstantLatency(0)` is bit-identical to the
  synchronous loop. New `examples/latency_race.py` reproduces the canonical
  result: a 3x-faster market maker takes ~73% front-of-queue share, ~4x the
  passive volume, and materially better markout.
- **Self-trade prevention**: `match(..., stp=...)` with `cancel_resting` /
  `cancel_taker` policies; `Simulation` defaults to `cancel_resting`.
  `Analytics.wash_trade_fraction()` audits the tape (previously a
  double-digit share of default-config trades were an agent trading with
  itself).
- **Order TTL**: `Order.ttl` + sim-side expiry sweep; `NoiseAgent` quotes
  default to `ttl=50` so long runs no longer thicken the book without bound.
- **Replay fidelity accounting**: `ReplayStats` counts executions/cancels
  that reference unknown (pre-window) order ids instead of silently
  dropping them; `strict=True` raises `UnknownOrderError`;
  `OrderBook.from_snapshot(bids, asks)` seeds the opening book from a
  LOBSTER orderbook-file row.
- `MomentumAgent(max_position=...)` position cap (on a wash-free tape an
  uncapped imbalance chaser feeds back into its own signal).

### Changed
- `OrderBook.add()` rejects orders that would cross the opposite side
  (`allow_crossed=True` to opt out, e.g. in replays).
- `Tape` is unbounded by default; bounded tapes expose `evicted` /
  `truncated` so silently windowed analytics are detectable.
- Agents anchor to their last-observed mid when the book has no mid
  (previously a hardcoded 100.0, which injected artificial jumps).
- `Analytics.markout` anchors fills to the latest metrics row at or before
  the fill time, so latency-delayed fills between ticks are counted.
- Corrected attributions: `microprice` is the size-weighted mid (not
  Stoikov's micro-price estimator); `SquareRootImpact` is the empirical
  square-root law (not Almgren–Chriss, which is linear).


## [0.2.0] - 2026-06-07

### Added
- **LOBSTER-format message replay** (`replay`, `replay_csv`, `Message`):
  reconstruct the visible book from real NASDAQ-style order-flow messages.
- `OrderBook.reduce()` / `PriceLevel.reduce()` for partial executions.
- Market-maker **cancel/replace** (`cancel_replace=True`): pulls stale quotes
  each tick so the book no longer accumulates layers. Spread mean drops from
  ≈1.43 to ≈0.28 in the bundled demo.
- **Adverse-selection markout** metric (`Analytics.markout`).
- Throughput benchmark (`benchmarks/throughput.py`).
- Executable Jupyter walkthrough (`examples/walkthrough.ipynb`) and a
  reproducible README chart script.

### Changed
- Library invariants now raise `ValueError` instead of `assert` (asserts are
  stripped under `python -O`).

### Fixed
- Resolved the documented stale-quote limitation via cancel/replace.

## [0.1.0] - 2026-05-27

### Added
- Core `OrderBook` with price-time priority and microprice
- `match()` engine with limit, market, and partial-fill semantics
- `Trade` and `Tape` for execution recording
- Latency models: `ConstantLatency`, `JitteredLatency`
- Impact models: `LinearImpact`, `SquareRootImpact`
- Agents: `NoiseAgent`, `MarketMakerAgent` (inventory-skewed), `MomentumAgent`
- `Simulation` event loop + `Analytics` post-sim metrics
- Examples: `basic_book.py`, `market_maker_demo.py`
- CI workflow (`pytest` + `ruff`)
