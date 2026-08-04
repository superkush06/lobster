"""Randomized property tests for the engine.

The rest of the suite pins behaviour on hand-built fixtures: this file asserts
the things that have to hold for *every* input, on a few thousand random ones.
Each test names the invariant and why it is one. Seeds are fixed, so a failure
is reproducible from the test name alone; `random.Random` rather than an
external generator keeps the package's zero-dependency promise intact.

Where an invariant is a conservation law it is checked exactly, not to a
tolerance — share counts are integers and cash is a sum of the same products
on both sides of every trade, so anything but equality is a bug.
"""

from __future__ import annotations

import random

import pytest

from lobster import (
    Analytics,
    Order,
    OrderBook,
    OrderType,
    Side,
    Simulation,
    match,
)
from lobster.agents import MarketMakerAgent, MomentumAgent, NoiseAgent
from lobster.execution import cost_to_trade
from lobster.stylized import depth_profile

DRAWS = 300


def random_book(rng: random.Random, *, mid: float = 100.0,
                levels: int = 8, max_orders: int = 4) -> OrderBook:
    """A well-formed, uncrossed book with random depth on both sides."""
    book = OrderBook()
    for i in range(1, levels + 1):
        for side, price in ((Side.BUY, round(mid - i * 0.1, 2)),
                            (Side.SELL, round(mid + i * 0.1, 2))):
            for _ in range(rng.randint(1, max_orders)):
                book.add(Order(side=side, qty=rng.randint(1, 50), price=price,
                               agent_id=rng.randint(1, 5)))
    return book


def total_depth(book: OrderBook) -> int:
    return sum(lv.total_qty
               for side in (Side.BUY, Side.SELL)
               for lv in book.iter_levels(side))


def random_agents(rng: random.Random) -> list:
    agents = [
        NoiseAgent(agent_id=1, intensity=rng.uniform(0.3, 0.8),
                   spread_offset=rng.uniform(0.2, 0.8),
                   qty=rng.randint(4, 12),
                   market_order_rate=rng.uniform(0.1, 0.4)),
        NoiseAgent(agent_id=2, intensity=rng.uniform(0.3, 0.8),
                   spread_offset=rng.uniform(0.2, 0.8),
                   qty=rng.randint(4, 12),
                   market_order_rate=rng.uniform(0.1, 0.4)),
        MarketMakerAgent(agent_id=3, half_spread=rng.uniform(0.1, 0.6),
                         qty=rng.randint(5, 15),
                         inv_skew=rng.uniform(0.0, 0.05)),
    ]
    if rng.random() < 0.5:
        agents.append(MomentumAgent(agent_id=4, lookback=rng.randint(5, 30),
                                    threshold=rng.uniform(0.2, 0.7),
                                    qty=rng.randint(3, 8), max_position=100))
    return agents


# ---- conservation ---------------------------------------------------------

def test_match_conserves_the_taker_quantity():
    """filled + leaves == requested, for every order the engine ever sees.

    `match` mutates the taker down to its leaves quantity, so the only way to
    know a market order exhausted the book is that identity. If it can fail,
    quantity is being created or destroyed inside the loop.
    """
    rng = random.Random(1001)
    for _ in range(DRAWS):
        book = random_book(rng)
        qty = rng.randint(1, 400)
        kind = rng.choice([OrderType.MARKET, OrderType.LIMIT])
        price = None if kind is OrderType.MARKET else round(
            100.0 + rng.uniform(-1.0, 1.0), 2)
        taker = Order(side=rng.choice([Side.BUY, Side.SELL]), qty=qty,
                      price=price, type=kind, agent_id=99)
        trades = match(book, taker)
        assert sum(t.qty for t in trades) + taker.qty == qty


def test_match_conserves_resting_depth():
    """Book depth changes by exactly (rested remainder - filled).

    Every share that leaves the book leaves through a trade, and every share
    that joins it joins as an unfilled limit remainder. Nothing else may move.
    """
    rng = random.Random(1002)
    for _ in range(DRAWS):
        book = random_book(rng)
        before = total_depth(book)
        qty = rng.randint(1, 400)
        kind = rng.choice([OrderType.MARKET, OrderType.LIMIT])
        price = None if kind is OrderType.MARKET else round(
            100.0 + rng.uniform(-1.0, 1.0), 2)
        taker = Order(side=rng.choice([Side.BUY, Side.SELL]), qty=qty,
                      price=price, type=kind, agent_id=99)
        trades = match(book, taker)
        filled = sum(t.qty for t in trades)
        rested = taker.qty if kind is OrderType.LIMIT else 0
        assert total_depth(book) == before - filled + rested


def test_a_closed_simulation_creates_no_cash_and_no_shares():
    """Sum of agent inventories is 0 and sum of agent cash is 0.

    A `Simulation` is a closed system: every trade has one buyer and one
    seller, both of them agents, and the cash leg is the same price times the
    same quantity on each side. Any drift means P&L attribution has picked up
    a counterparty that does not exist.
    """
    rng = random.Random(1003)
    for _ in range(12):
        sim = Simulation(agents=random_agents(rng), seed=rng.randint(0, 10_000))
        for _ in sim.run(300):
            pass
        assert sum(a.inventory for a in sim.agents) == 0
        assert sum(a.cash for a in sim.agents) == pytest.approx(0.0, abs=1e-6)


# ---- book structure -------------------------------------------------------

def test_the_public_api_never_leaves_a_crossed_book():
    """best_bid < best_ask after any sequence of add / match / cancel.

    `add` rejects crossing orders and `match` consumes them, so the two
    together can never produce a negative spread. Everything that reads the
    mid depends on this.
    """
    rng = random.Random(1004)
    for _ in range(60):
        book = random_book(rng)
        for _ in range(40):
            roll = rng.random()
            if roll < 0.4:
                side = rng.choice([Side.BUY, Side.SELL])
                inside = rng.random() < 0.5
                ref = book.best_bid if side is Side.BUY else book.best_ask
                if ref is None:
                    continue
                price = round(ref + (0.05 if inside else -0.5) *
                              (1 if side is Side.BUY else -1), 2)
                order = Order(side=side, qty=rng.randint(1, 30), price=price,
                              agent_id=rng.randint(1, 5))
                try:
                    book.add(order)
                except ValueError:
                    match(book, order)
            elif roll < 0.8:
                match(book, Order(side=rng.choice([Side.BUY, Side.SELL]),
                                  qty=rng.randint(1, 60),
                                  type=OrderType.MARKET, agent_id=99))
            else:
                ids = list(book._index)
                if ids:
                    book.cancel(rng.choice(ids))
            bb, ba = book.best_bid, book.best_ask
            if bb is not None and ba is not None:
                assert bb < ba


def test_the_id_index_agrees_with_the_levels():
    """`_index` is exactly the set of resting orders, with the right side/price.

    design.md states this as an invariant; cancels and partial reductions are
    the two places it could silently rot, and both are exercised here.
    """
    rng = random.Random(1005)
    for _ in range(120):
        book = random_book(rng)
        for _ in range(25):
            ids = list(book._index)
            if ids and rng.random() < 0.5:
                oid = rng.choice(ids)
                if rng.random() < 0.5:
                    book.cancel(oid)
                else:
                    book.reduce(oid, rng.randint(1, 30))
            else:
                match(book, Order(side=rng.choice([Side.BUY, Side.SELL]),
                                  qty=rng.randint(1, 40),
                                  type=OrderType.MARKET, agent_id=99))
        resting = {}
        for side in (Side.BUY, Side.SELL):
            for lv in book.iter_levels(side):
                assert lv.orders, "empty level left on the book"
                assert lv.total_qty == sum(o.qty for o in lv.orders)
                for o in lv.orders:
                    resting[o.id] = (side, lv.price)
        assert resting == book._index


def test_fills_follow_price_time_priority():
    """Fills arrive best-price-first, and within a price in arrival order.

    Each resting order is given a unique agent id in submission order, so the
    tape spells out the queue it consumed. This is the one rule the whole
    package is about.
    """
    rng = random.Random(1006)
    for _ in range(DRAWS):
        book = OrderBook()
        agent = 0
        expected: list[tuple[float, int]] = []
        for i in range(1, 5):
            price = round(100.0 + i * 0.1, 2)
            for _ in range(rng.randint(1, 3)):
                agent += 1
                book.add(Order(Side.SELL, qty=rng.randint(1, 20), price=price,
                               agent_id=agent))
                expected.append((price, agent))
        taker = Order(Side.BUY, qty=rng.randint(1, 200), type=OrderType.MARKET,
                      agent_id=999)
        trades = match(book, taker)
        seen = [(t.price, t.seller_id) for t in trades]
        assert seen == expected[:len(seen)]


def test_queue_position_counts_the_orders_ahead():
    """`queue_position` equals the number of earlier orders at the same price.

    Fill probability is a function of exactly this number, so an off-by-one
    here silently biases every queue study built on the package.
    """
    rng = random.Random(1007)
    for _ in range(DRAWS):
        book = OrderBook()
        price = 100.0
        orders = [Order(Side.BUY, qty=rng.randint(1, 20), price=price,
                        agent_id=i) for i in range(rng.randint(1, 8))]
        for o in orders:
            book.add(o)
        level = next(book.iter_levels(Side.BUY))
        for i, o in enumerate(orders):
            ahead = list(level.orders)[:i]
            assert Analytics.queue_position(o, ahead) == i


# ---- cost estimation ------------------------------------------------------

def test_average_fill_price_is_monotone_in_size():
    """A larger market order never gets a better average price.

    Walking further into the book can only reach worse prices, so the average
    is monotone in size — the convexity that makes execution cost a real cost.
    """
    rng = random.Random(1008)
    for _ in range(DRAWS):
        book = random_book(rng)
        side = rng.choice([Side.BUY, Side.SELL])
        prev = None
        for qty in (1, 5, 20, 60, 150):
            sweep = cost_to_trade(book, side, qty)
            if sweep is None or not sweep.complete:
                break
            avg = sweep.avg_price
            if prev is not None:
                if side is Side.BUY:
                    assert avg >= prev - 1e-12
                else:
                    assert avg <= prev + 1e-12
            prev = avg


def test_cost_to_trade_agrees_with_actually_trading():
    """The read-only estimate equals what `match` charges for the same order.

    `cost_to_trade` re-implements the book walk without mutating; if the two
    ever disagree, pre-trade cost estimates are lying about the engine they
    claim to model.
    """
    rng = random.Random(1009)
    for _ in range(DRAWS):
        seed = rng.randint(0, 10**6)
        book = random_book(random.Random(seed))
        twin = random_book(random.Random(seed))
        side = rng.choice([Side.BUY, Side.SELL])
        qty = rng.randint(1, 300)
        sweep = cost_to_trade(book, side, qty)
        assert sweep is not None
        trades = match(twin, Order(side=side, qty=qty, type=OrderType.MARKET,
                                   agent_id=99))
        filled = sum(t.qty for t in trades)
        assert sweep.filled == filled
        if filled:
            vwap = sum(t.price * t.qty for t in trades) / filled
            assert sweep.avg_price == pytest.approx(vwap, rel=1e-12)
        if sweep.complete and twin.mid is not None:
            assert sweep.mid_after == pytest.approx(twin.mid, rel=1e-12)


def test_depth_profile_is_translation_invariant():
    """Shifting every price by a constant leaves the depth profile unchanged.

    The profile is a function of distance from the mid, so it must not know
    what the price level is. If it does, comparing profiles across a run that
    drifted is meaningless.

    The bin width (0.077) is deliberately incommensurate with the 0.10 level
    spacing over the measured range: a level sitting exactly on a bin edge can
    fall either side of it once the price difference has been through a float
    subtraction, and that is arithmetic rather than a property of the profile.
    """
    rng = random.Random(1010)
    for _ in range(80):
        seed = rng.randint(0, 10**6)
        shift = round(rng.uniform(-40.0, 40.0), 2)
        base = random_book(random.Random(seed), mid=100.0)
        moved = random_book(random.Random(seed), mid=100.0 + shift)
        assert depth_profile(base, 0.077, 1.0) == depth_profile(moved, 0.077, 1.0)


# ---- simulation hygiene ---------------------------------------------------

def test_self_trade_prevention_leaves_no_wash_trades():
    """With STP on, no trade has buyer_id == seller_id. For any agent mix.

    A venue that lets an agent trade with itself manufactures volume and
    imbalance out of nothing, and every tape statistic inherits it.
    """
    rng = random.Random(1011)
    for _ in range(12):
        sim = Simulation(agents=random_agents(rng), seed=rng.randint(0, 10_000),
                         stp="cancel_resting")
        for _ in sim.run(400):
            pass
        an = Analytics(metrics=sim.metrics, tape=sim.tape, agents=sim.agents)
        assert an.wash_trade_fraction() == 0.0


def test_ttl_orders_never_outlive_their_ttl():
    """No order rests on the book more than `ttl` after it was submitted.

    TTL is what stops passive flow from thickening the book without bound, so
    an order that slips past the sweep is a slow leak rather than a loud bug.
    """
    rng = random.Random(1012)
    for _ in range(10):
        ttl = float(rng.randint(5, 40))
        agents = [
            NoiseAgent(agent_id=1, intensity=0.7, qty=6,
                       market_order_rate=0.2, ttl=ttl),
            NoiseAgent(agent_id=2, intensity=0.6, qty=6,
                       market_order_rate=0.2, ttl=ttl),
        ]
        sim = Simulation(agents=agents, seed=rng.randint(0, 10_000))
        for ts, _ in enumerate(sim.run(200)):
            for side in (Side.BUY, Side.SELL):
                for lv in sim.book.iter_levels(side):
                    for o in lv.orders:
                        assert ts - o.ts <= ttl


def test_a_simulation_is_a_deterministic_function_of_its_seed():
    """Same seed, same tape — every price, quantity, side and timestamp.

    Reproducibility is the only reason any number in the docs can be checked,
    so it is asserted rather than assumed.
    """
    rng = random.Random(1013)
    for _ in range(8):
        seed = rng.randint(0, 10_000)
        tapes = []
        for _ in range(2):
            # Rebuild the agents from the same spec seed too: the point is
            # that the whole run is a function of the seeds, not of state
            # left behind by the previous one.
            sim = Simulation(agents=random_agents(random.Random(seed * 7 + 1)),
                             seed=seed)
            for _ in sim.run(250):
                pass
            tapes.append([(t.price, t.qty, t.buyer_id, t.seller_id, t.ts,
                           t.aggressor) for t in sim.tape])
        assert tapes[0] == tapes[1]
        assert tapes[0], "a 250-tick run should print at least one trade"
