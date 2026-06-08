# Changelog

## [0.2.0] - 2026-06-XX

### Added
- **LOBSTER-format message replay** (`replay`, `replay_csv`, `Message`):
  reconstruct the visible book from real NASDAQ-style order-flow messages.
- `OrderBook.reduce()` / `PriceLevel.reduce()` for partial executions.
- Market-maker **cancel/replace** (`cancel_replace=True`): pulls stale quotes
  each tick so the book no longer accumulates layers — spread mean drops from
  ≈1.43 to ≈0.28 in the bundled demo.
- **Adverse-selection markout** metric (`Analytics.markout`).
- Throughput benchmark (`benchmarks/throughput.py`).
- Executable Jupyter walkthrough (`examples/walkthrough.ipynb`) and a
  reproducible README hero chart (`examples/render_hero.py`).

### Changed
- Library invariants now raise `ValueError` instead of `assert` (asserts are
  stripped under `python -O`).

### Fixed
- Resolved the documented stale-quote limitation via cancel/replace.

## [0.1.0] - 2026-06-XX

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
