"""lobster - limit order book microstructure simulator.

Top-level convenience imports. Direct submodule imports also work:

    from lobster.book import OrderBook
    from lobster.matching import match
"""

from .analytics import Analytics
from .book import OrderBook, PriceLevel
from .execution import (
    Metaorder,
    Sweep,
    cost_to_trade,
    execute_metaorder,
    fit_power_law,
)
from .impact import LinearImpact, SquareRootImpact
from .latency import ConstantLatency, JitteredLatency
from .matching import match
from .order import Order, OrderType, Side, next_order_id
from .replay import (
    Message,
    ReplayStats,
    UnknownOrderError,
    apply_message,
    parse_lobster_line,
    replay,
    replay_csv,
)
from .sim import Simulation
from .stylized import ReturnFacts, StylizedFacts, depth_profile, variance_ratio
from .tape import Tape, Trade

__version__ = "0.6.0"
__all__ = [
    "Side", "OrderType", "Order", "next_order_id",
    "PriceLevel", "OrderBook",
    "Trade", "Tape",
    "match",
    "ConstantLatency", "JitteredLatency",
    "LinearImpact", "SquareRootImpact",
    "Simulation",
    "Analytics",
    "StylizedFacts", "ReturnFacts", "depth_profile", "variance_ratio",
    "Sweep", "Metaorder", "cost_to_trade", "execute_metaorder", "fit_power_law",
    "Message", "parse_lobster_line", "apply_message", "replay", "replay_csv",
    "ReplayStats", "UnknownOrderError",
]
