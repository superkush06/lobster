# lobster

[![ci](https://github.com/superkush06/lobster/actions/workflows/ci.yml/badge.svg)](https://github.com/superkush06/lobster/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A limit order book microstructure simulator with realistic price-time priority
matching, latency models, market impact, and pluggable agents.

## TL;DR

```python
from lobster import OrderBook, Order, Side, OrderType, match

book = OrderBook()
book.add(Order(Side.BUY, qty=100, price=99.5))
book.add(Order(Side.SELL, qty=50, price=100.5))
# Marketable buy sweeps the ask:
trades = match(book, Order(Side.BUY, qty=30, price=None, type=OrderType.MARKET))
print(trades[0].price)  # 100.5
print(book.spread)      # 1.0
```

## Why

The limit order book is the central data structure of every electronic market.
Most interesting questions in market microstructure — queue position, adverse
selection, market-maker P&L, optimal execution — can only be studied with a
realistic simulation. Off-the-shelf LOB packages are either toys (no real
matching) or proprietary trading-firm internals. `lobster` is a clean,
hackable middle ground.

## Features

- **Price-time priority** matching engine with limit, market, partial-fill
  and cancel semantics
- **Latency models**: constant + jittered (gamma) network/processing delays
- **Market-impact models**: linear and Almgren–Chriss-style square-root
- **Pluggable agents**: `NoiseAgent`, `MarketMakerAgent` (inventory-skewed),
  `MomentumAgent` (responds to tape imbalance)
- **Analytics**: spread, depth, queue position estimator, agent P&L
- **Deterministic** under a given seed — reproducible simulations

## Install

```sh
pip install -e ".[dev]"
```

## Quickstart

```sh
python examples/basic_book.py
python examples/market_maker_demo.py
```

## Math

The book exposes `mid`, `spread`, and `depth(side, k)` directly. Trade
arrivals are recorded on a `Tape`; the matching engine emits trades
price-time-priority. Market impact for an order of size $Q$ traded against a
liquidity parameter $\eta$ is modeled as:

- **Linear**: $\Delta p = \eta \cdot Q$
- **Square-root**: $\Delta p = \eta \cdot \sqrt{Q / V}$, where $V$ is
  the recent traded volume (Almgren-Chriss style).

The market-maker quotes around mid with a width that increases linearly in
inventory imbalance to avoid runaway position.

## Layout

```
lobster/
├── order.py       # Side, OrderType, Order
├── book.py        # PriceLevel, OrderBook
├── matching.py    # match() — price-time priority engine
├── tape.py        # Trade dataclass + Tape buffer
├── latency.py     # ConstantLatency, JitteredLatency
├── impact.py      # LinearImpact, SquareRootImpact
├── agents/        # Agent base + Noise/MM/Momentum
├── sim.py         # Simulation event loop
└── analytics.py   # Spread/depth/queue-position/P&L
```

## Design

See [`docs/design.md`](docs/design.md) for modeling assumptions, invariants,
and known limitations.

## Example output

Running `examples/market_maker_demo.py --steps 5000 --seed 7`:

```
Trades:        10000
Spread mean:   1.4299
Spread p95:    4.6100
Agent P&L:
  agent 1 (   noise): cash=-64686.61  inv=+1259  mtm=+36379.61
  agent 2 (   noise): cash=-30673.03  inv= +854  mtm=+37881.82
  agent 3 (momentum): cash=+57122.00  inv=-2277  mtm=-125664.18
  agent 4 (   maker): cash=+38237.64  inv= +164  mtm=+51402.74
```

Market maker earns the spread; momentum gets adverse-selected (typical).
Noise traders break even on the random walk + provide inventory float.

## Known limitations

- Market-maker agent does not cancel stale quotes, so the book accumulates
  old layers. This widens observed spread under sustained activity. A
  full cancel/replace cycle is on the roadmap.
- Latency model is applied per-agent but the matching engine itself is
  synchronous (no queue arbitration at sub-tick resolution).
- Greeks/risk are intentionally out of scope — see `optune` for those.

## License


MIT — see [LICENSE](LICENSE).
