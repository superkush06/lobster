"""Market-maker demo: NoiseAgents (with crossing flow) + MarketMakerAgent.

Posts symmetric quotes; noise agents send marketable orders ~25% of the time,
so the market maker actually accumulates inventory and earns the spread.

Run:  PYTHONPATH=. python3 examples/market_maker_demo.py --steps 5000
"""

import argparse

from lobster.agents import MarketMakerAgent, MomentumAgent, NoiseAgent
from lobster.analytics import Analytics
from lobster.sim import Simulation


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--plot", action="store_true")
    args = ap.parse_args()

    sim = Simulation(
        agents=[
            NoiseAgent(agent_id=1, intensity=0.6, spread_offset=0.6,
                       qty=8, market_order_rate=0.25),
            NoiseAgent(agent_id=2, intensity=0.5, spread_offset=0.6,
                       qty=8, market_order_rate=0.25),
            MomentumAgent(agent_id=3, lookback=20, threshold=0.35, qty=5),
            MarketMakerAgent(agent_id=4, half_spread=0.4, qty=12,
                             inv_skew=0.02),
        ],
        seed=args.seed,
    )
    for _ in sim.run(steps=args.steps):
        pass

    an = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
    stats = an.spread_stats()
    print(f"Trades:        {len(sim.tape)}")
    print(f"Spread mean:   {stats['mean']:.4f}")
    print(f"Spread p95:    {stats['p95']:.4f}")
    print("Agent P&L:")
    role = {1: "noise", 2: "noise", 3: "momentum", 4: "maker"}
    for aid, pnl in an.agent_pnl().items():
        print(f"  agent {aid} ({role.get(aid, '?'):>8}): "
              f"cash={pnl['cash']:+9.2f}  "
              f"inv={pnl['inventory']:+5.0f}  "
              f"mtm={pnl['pnl_mtm']:+9.2f}")

    if args.plot:
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("\n(install matplotlib to use --plot)")
            return
        mids = [m.mid for m in sim.metrics if m.mid is not None]
        plt.plot(mids)
        plt.title(f"Mid price over {args.steps} ticks")
        plt.xlabel("tick")
        plt.ylabel("mid")
        plt.tight_layout()
        plt.show()


if __name__ == "__main__":
    main()
