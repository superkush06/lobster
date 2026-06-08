"""Post-simulation analytics — spread/depth time series, P&L, queue position."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from statistics import mean, pstdev

from .agents.base import Agent
from .order import Order, Side
from .sim import StepMetrics
from .tape import Tape


@dataclass
class Analytics:
    metrics: list[StepMetrics]
    tape: Tape
    agents: list[Agent]

    # ---- top-of-book statistics ---------------------------------------------

    def spread_stats(self) -> dict[str, float]:
        spreads = [m.spread for m in self.metrics if m.spread is not None]
        if not spreads:
            return {"mean": 0.0, "std": 0.0, "p50": 0.0, "p95": 0.0}
        sorted_s = sorted(spreads)
        return {
            "mean": mean(spreads),
            "std": pstdev(spreads) if len(spreads) > 1 else 0.0,
            "p50": sorted_s[len(sorted_s) // 2],
            "p95": sorted_s[int(len(sorted_s) * 0.95)],
        }

    def mid_returns(self) -> list[float]:
        mids = [m.mid for m in self.metrics if m.mid is not None]
        return [(mids[i] - mids[i - 1]) / mids[i - 1] for i in range(1, len(mids))]

    # ---- queue position -----------------------------------------------------

    @staticmethod
    def queue_position(order: Order, level_orders_before: Iterable[Order]) -> int:
        """Number of orders ahead of `order` in its level's FIFO queue.

        Helpful for estimating fill probability before trading.
        """
        return sum(1 for o in level_orders_before if o.id != order.id)

    # ---- agent P&L ----------------------------------------------------------

    def agent_pnl(self) -> dict[int, dict[str, float]]:
        """Cash + inventory marked at last mid."""
        last_mid = next(
            (m.mid for m in reversed(self.metrics) if m.mid is not None), None
        )
        out: dict[int, dict[str, float]] = {}
        for a in self.agents:
            mark = last_mid if last_mid is not None else 0.0
            mtm = a.cash + a.inventory * mark
            out[a.id] = {
                "cash": a.cash,
                "inventory": float(a.inventory),
                "mark": mark,
                "pnl_mtm": mtm,
            }
        return out

    def pnl_conservation(self) -> float:
        """Sum of all agents' MTM P&L. With a closed-book sim this is ~0,
        but inventory carry @ last mid creates small non-zero residue."""
        return sum(v["pnl_mtm"] for v in self.agent_pnl().values())

    # ---- tape side imbalance ------------------------------------------------

    def buy_sell_imbalance(self, n: int = 200) -> float:
        recent = self.tape.recent(n)
        if not recent:
            return 0.0
        buy = sum(t.qty for t in recent if t.aggressor is Side.BUY)
        sell = sum(t.qty for t in recent if t.aggressor is Side.SELL)
        total = buy + sell
        return (buy - sell) / total if total else 0.0
