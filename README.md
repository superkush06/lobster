# lobster

A limit order book (LOB) microstructure simulator with realistic price-time
priority matching, latency models, market impact, and pluggable agents.

## Why

The limit order book is the central data structure of every electronic market,
and most of the interesting questions in market microstructure — queue
position, adverse selection, market-maker P&L, optimal execution — can only be
studied with a realistic simulation. Off-the-shelf LOB packages tend to be
either toys (no real matching) or trading-firm internals (proprietary).
`lobster` is a clean, hackable middle ground.

## Status

Pre-release. See `docs/design.md` for assumptions.
