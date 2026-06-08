"""Render the README hero image: mid-price path + live spread.

Run:  python examples/render_hero.py   ->  writes docs/demo.png
"""

from __future__ import annotations

import pathlib

import matplotlib

matplotlib.use("Agg")  # headless render
import matplotlib.pyplot as plt  # noqa: E402

from lobster import Simulation  # noqa: E402
from lobster.agents import (  # noqa: E402
    MarketMakerAgent,
    MomentumAgent,
    NoiseAgent,
)


def main() -> None:
    sim = Simulation(
        agents=[
            NoiseAgent(agent_id=1, intensity=0.6, market_order_rate=0.25),
            NoiseAgent(agent_id=2, intensity=0.5, market_order_rate=0.25),
            MomentumAgent(agent_id=3, lookback=20, threshold=0.35),
            MarketMakerAgent(agent_id=4, half_spread=0.4, qty=12),
        ],
        seed=7,
    )
    for _ in sim.run(3000):
        pass

    steps = [m.ts for m in sim.metrics]
    mids = [m.mid for m in sim.metrics]
    spreads = [m.spread for m in sim.metrics]

    plt.style.use("seaborn-v0_8-darkgrid")
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 6), height_ratios=[2, 1], sharex=True
    )

    ax1.plot(steps, mids, color="#1f77b4", lw=0.9)
    ax1.set_ylabel("mid price")
    ax1.set_title("lobster — 4-agent limit order book simulation "
                  "(2 noise · 1 momentum · 1 market maker)")

    ax2.plot(steps, spreads, color="#d62728", lw=0.7, alpha=0.8)
    ax2.set_ylabel("spread")
    ax2.set_xlabel("simulation step")
    ax2.set_ylim(bottom=0)

    fig.tight_layout()
    out = pathlib.Path(__file__).resolve().parents[1] / "docs" / "demo.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
