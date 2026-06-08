"""Throughput benchmark for the lobster order book + matching engine.

Run:  python benchmarks/throughput.py

Reports operations/second for the three hot paths: resting limit orders,
crossing (matching) marketable orders, and replaying LOBSTER messages. Pure
stdlib timing (time.perf_counter); numbers are indicative, not a promise.
"""

from __future__ import annotations

import random
import time

from lobster.book import OrderBook
from lobster.matching import match
from lobster.order import Order, OrderType, Side
from lobster.replay import Message, apply_message


def bench_add(n: int = 200_000, seed: int = 0) -> float:
    rng = random.Random(seed)
    book = OrderBook()
    t0 = time.perf_counter()
    for _ in range(n):
        side = Side.BUY if rng.random() < 0.5 else Side.SELL
        price = round(100.0 + rng.gauss(0.0, 2.0), 2)
        book.add(Order(side=side, qty=10, price=price))
    return n / (time.perf_counter() - t0)


def bench_match(n: int = 100_000, seed: int = 0) -> float:
    rng = random.Random(seed)
    book = OrderBook()
    # Pre-seed a deep book so marketable orders always have something to hit.
    for i in range(2000):
        book.add(Order(Side.BUY, qty=100, price=round(99.0 - i * 0.01, 2)))
        book.add(Order(Side.SELL, qty=100, price=round(101.0 + i * 0.01, 2)))
    tape_sink = []
    t0 = time.perf_counter()
    for _ in range(n):
        side = Side.BUY if rng.random() < 0.5 else Side.SELL
        match(book, Order(side=side, qty=5, type=OrderType.MARKET),
              on_trade=tape_sink.append)
        # top the book back up so it never empties
        book.add(Order(side.opposite, qty=5,
                       price=99.0 if side is Side.SELL else 101.0))
    return n / (time.perf_counter() - t0)


def bench_replay(n: int = 200_000, seed: int = 0) -> float:
    rng = random.Random(seed)
    book = OrderBook()
    msgs = []
    live: list[int] = []
    for oid in range(1, n + 1):
        if live and rng.random() < 0.3:
            msgs.append(Message(0.0, 3, live.pop(), 0, 0.0, 1))  # delete
        else:
            d = 1 if rng.random() < 0.5 else -1
            price = round(100.0 + rng.gauss(0.0, 2.0), 2)
            msgs.append(Message(0.0, 1, oid, 10, price, d))       # new
            live.append(oid)
    t0 = time.perf_counter()
    for m in msgs:
        apply_message(book, m)
    return len(msgs) / (time.perf_counter() - t0)


def main() -> None:
    print("lobster throughput benchmark")
    print("-" * 40)
    print(f"  limit-order inserts : {bench_add():>12,.0f} ops/s")
    print(f"  marketable matches  : {bench_match():>12,.0f} ops/s")
    print(f"  message replay      : {bench_replay():>12,.0f} msg/s")


if __name__ == "__main__":
    main()
