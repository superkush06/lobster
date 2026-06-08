# Changelog

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
