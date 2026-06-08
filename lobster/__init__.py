"""lobster - limit order book microstructure simulator.

Top-level convenience imports. Direct submodule imports also work:

    from lobster.book import OrderBook
    from lobster.matching import match
"""

from .analytics import Analytics
from .book import OrderBook, PriceLevel
from .impact import LinearImpact, SquareRootImpact
from .latency import ConstantLatency, JitteredLatency
from .matching import match
from .order import Order, OrderType, Side, next_order_id
from .sim import Simulation
from .tape import Tape, Trade

__version__ = "0.1.0"
__all__ = [
    "Side", "OrderType", "Order", "next_order_id",
    "PriceLevel", "OrderBook",
    "Trade", "Tape",
    "match",
    "ConstantLatency", "JitteredLatency",
    "LinearImpact", "SquareRootImpact",
    "Simulation",
    "Analytics",
]
