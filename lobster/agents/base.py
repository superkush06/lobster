"""Base agent class and shared context object."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..book import OrderBook
    from ..order import Order
    from ..tape import Tape


@dataclass
class AgentContext:
    book: OrderBook
    tape: Tape
    rng: random.Random
    ts: float


class Agent(ABC):
    def __init__(self, agent_id: int) -> None:
        self.id = agent_id
        self.inventory: int = 0
        self.cash: float = 0.0

    def on_fill(self, side_sign: int, price: float, qty: int) -> None:
        # +1 for buy fills (we paid), -1 for sells (we received)
        self.cash -= side_sign * price * qty
        self.inventory += side_sign * qty

    @abstractmethod
    def step(self, ctx: AgentContext) -> list[Order]:
        """Return a (possibly empty) list of new orders to submit this tick."""
