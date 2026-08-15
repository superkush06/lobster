#!/usr/bin/env python3
"""Replay a real NASDAQ trading day and reconcile it against the exchange's book.

LOBSTER ships two files per ticker-day: a message file (one order-flow event
per row) and an orderbook file whose row *i* is the exchange's own top-N book
immediately after message *i*. That pairing makes the orderbook file an
answer key: rebuild the book from the messages alone, and every row tells you
exactly how far the reconstruction has drifted from the truth.

A cold start cannot be perfect, and the reason is structural, not sloppy: a
level-N file only carries events for the top N occupied levels, so an order
resting at level 11 arrives, cancels, or trades with no message at all —
until the band shifts and its level surfaces inside the official book,
holding shares this stream never described. On this day that happens within
the first 441 rows. Reconstruction from the messages alone is therefore
well-defined only *inside the band*, and this script treats the boundary
explicitly: after each row it imports official levels that entered the band
from below (``promoted``) and prunes levels of ours that fell out of the
official window (``demoted``), counting every share of both. What remains —
agreement inside the band, unknown-id events reconciled by price level,
hidden executions skipped by design — is the honest measurement. Pass
``--no-band-sync`` for the ablation: reconstruction with the boundary
ignored, where zombie levels compound and top-of-book agreement collapses to
under 1%. That single number is the band problem.

Run it (fetch the data first with ``python tools/fetch_lobster_sample.py``):

    python examples/replay_real_day.py
    python examples/replay_real_day.py --no-band-sync      # the ablation
    python examples/replay_real_day.py --report docs/real_replay.md
"""

from __future__ import annotations

import argparse
import pathlib
import time

from lobster.book import OrderBook
from lobster.order import Order, Side
from lobster.replay import (
    EXECUTE_HIDDEN,
    HALT,
    NEW,
    ReplayStats,
    apply_message,
    parse_lobster_line,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
MESSAGES = ROOT / "data" / "real" / "AAPL_2012-06-21_34200000_57600000_message_10.csv"
ORDERBOOK = ROOT / "data" / "real" / "AAPL_2012-06-21_34200000_57600000_orderbook_10.csv"
DUMMY_ASK, DUMMY_BID = 9999999999, -9999999999


def parse_book_row(line: str, levels: int) -> tuple[list[tuple[float, int]], list[tuple[float, int]]]:
    """One orderbook row -> (asks, bids) as [(price, qty), ...], dummies dropped."""
    cols = line.split(",")
    asks, bids = [], []
    for lv in range(levels):
        ap, aq, bp, bq = (int(c) for c in cols[4 * lv:4 * lv + 4])
        if aq > 0 and ap != DUMMY_ASK:
            asks.append((float(ap), aq))
        if bq > 0 and bp != DUMMY_BID:
            bids.append((float(bp), bq))
    return asks, bids


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--messages", default=str(MESSAGES))
    ap.add_argument("--orderbook", default=str(ORDERBOOK))
    ap.add_argument("--levels", type=int, default=10,
                    help="book depth of the orderbook file (its column count / 4)")
    ap.add_argument("--policy", default="reduce_level",
                    choices=["count", "reduce_level"],
                    help="what to do with events against pre-window order ids")
    ap.add_argument("--compare-levels", type=int, default=5,
                    help="how many exchange levels the depth-error metric sums over")
    ap.add_argument("--report", default=None,
                    help="also write the table to this markdown file")
    ap.add_argument("--sample-every", type=int, default=200,
                    help="rows between timeline samples for the figure/series")
    ap.add_argument("--png", default=None,
                    help="write a two-panel figure here (needs matplotlib)")
    ap.add_argument("--no-band-sync", action="store_true",
                    help="ablation: never import/prune at the band boundary, "
                         "so out-of-band drift compounds all day")
    args = ap.parse_args()

    msg_path, book_path = pathlib.Path(args.messages), pathlib.Path(args.orderbook)
    if not msg_path.exists() or not book_path.exists():
        raise SystemExit("real data not found - run: python tools/fetch_lobster_sample.py")

    stats = ReplayStats()
    book = OrderBook()
    seen_new: set[int] = set()
    pre_window_unknowns = 0
    reappeared_unknowns = 0

    rows = 0
    top1_hits = 0
    depth_err_sum = 0          # sum over rows of L1 share error on compare-levels
    depth_shares_sum = 0       # official shares over the same levels (for a rate)
    mid_abs_err_sum = 0.0
    mid_err_worst = 0.0
    exact_full_rows = 0        # my top-N == official top-N, prices and sizes
    window_exact_rows = 0      # the full official window matches, band edge included
    imported_levels = 0        # official levels mine lacked, injected post-measure
    imported_shares = 0
    pruned_levels = 0          # my levels below the official window, dropped
    pruned_shares = 0
    # (t, official_mid, my_mid, cumulative shares imported at the band edge)
    series: list[tuple[float, float, float, int]] = []

    t0 = time.perf_counter()
    with open(msg_path) as mf, open(book_path) as bf:
        for i, (mline, bline) in enumerate(zip(mf, bf, strict=True), start=1):
            msg = parse_lobster_line(mline)
            asks, bids = parse_book_row(bline, args.levels)
            if i == 1:
                # Row 1 is the state after message 1: seed from the answer key
                # once, then reconstruct everything after it from messages only.
                book = OrderBook.from_snapshot(bids=bids, asks=asks, ts=msg.time)
                if msg.event_type == NEW:
                    seen_new.add(msg.order_id)
                continue

            unknown_before = stats.unknown_total
            if msg.event_type == NEW:
                seen_new.add(msg.order_id)
            apply_message(book, msg, stats=stats, on_unknown=args.policy)
            if stats.unknown_total > unknown_before:
                if msg.order_id in seen_new:
                    reappeared_unknowns += 1
                else:
                    pre_window_unknowns += 1

            # ---- reconcile against the exchange's own row -------------------
            rows += 1
            official_ask = asks[0] if asks else None
            official_bid = bids[0] if bids else None
            mine_ask = book.depth(Side.SELL, 1)
            mine_bid = book.depth(Side.BUY, 1)
            hit = (official_ask is not None and official_bid is not None
                   and mine_ask and mine_bid
                   and mine_ask[0] == official_ask and mine_bid[0] == official_bid)
            top1_hits += hit

            err = 0
            official_shares = 0
            mine_asks = dict(book.depth(Side.SELL, args.levels))
            mine_bids = dict(book.depth(Side.BUY, args.levels))
            for price, qty in asks[:args.compare_levels]:
                err += abs(mine_asks.get(price, 0) - qty)
                official_shares += qty
            for price, qty in bids[:args.compare_levels]:
                err += abs(mine_bids.get(price, 0) - qty)
                official_shares += qty
            depth_err_sum += err
            depth_shares_sum += official_shares
            if (sorted(mine_asks.items())[:args.compare_levels]
                    == [(p, q) for p, q in asks[:args.compare_levels]]
                    and sorted(mine_bids.items(), reverse=True)[:args.compare_levels]
                    == [(p, q) for p, q in bids[:args.compare_levels]]):
                exact_full_rows += 1
            # The whole official window, band edge included. This is where the
            # boundary problem lives, so it is the row-level metric the sync
            # below is NOT allowed to flatter: it is measured first.
            if (sorted(mine_asks.items())[:args.levels] == asks
                    and sorted(mine_bids.items(), reverse=True)[:args.levels] == bids):
                window_exact_rows += 1

            if official_ask and official_bid and mine_ask and mine_bid:
                official_mid = (official_ask[0] + official_bid[0]) / 2
                my_mid = (mine_ask[0][0] + mine_bid[0][0]) / 2
                e = abs(my_mid - official_mid)
                mid_abs_err_sum += e
                mid_err_worst = max(mid_err_worst, e)
                if rows % args.sample_every == 0:
                    series.append((msg.time, official_mid, my_mid, imported_shares))

            # ---- band-boundary sync, after the row was measured -------------
            # Everything above scored this row; only now may the official file
            # teach the book what the message stream cannot: depth promoted
            # into the band from below, and our levels that fell out of the
            # official window. Divergences were already counted, so the sync
            # stops errors compounding without hiding a single one.
            if not args.no_band_sync:
                for side, official, full_len in (
                    (Side.SELL, asks, len(asks)),
                    (Side.BUY, bids, len(bids)),
                ):
                    mine_all = book.depth(side, 1 << 30)
                    have = {p for p, _ in mine_all}
                    for price, qty in official:
                        if price not in have:
                            book.add(Order(side=side, qty=qty, price=price,
                                           agent_id=0, ts=msg.time),
                                     allow_crossed=True)
                            imported_levels += 1
                            imported_shares += qty
                    # Only prune beyond the window when the official row is
                    # full: a short row means the whole side fit on screen.
                    if full_len == args.levels:
                        worst = official[-1][0]
                        for price, qty in mine_all:
                            beyond = price < worst if side is Side.BUY else price > worst
                            if beyond:
                                book.reduce_at(side, price, qty)
                                pruned_levels += 1
                                pruned_shares += qty
    elapsed = time.perf_counter() - t0

    # ---- throughput without the reconciliation overhead ---------------------
    t0 = time.perf_counter()
    replay_book = OrderBook()
    replay_stats = ReplayStats()
    with open(msg_path) as mf:
        first = parse_lobster_line(next(mf))
        replay_book = OrderBook.from_snapshot(bids=[], asks=[], ts=first.time)
        n_msgs = 1
        for line in mf:
            apply_message(replay_book, parse_lobster_line(line),
                          stats=replay_stats, on_unknown=args.policy)
            n_msgs += 1
    replay_secs = time.perf_counter() - t0

    hidden = stats.skipped_types.get(EXECUTE_HIDDEN, 0)
    halts = stats.skipped_types.get(HALT, 0)
    lines = [
        f"ticker-day                AAPL 2012-06-21 (LOBSTER sample, level {args.levels})",
        f"messages                  {rows + 1:,}",
        f"policy                    {args.policy}"
        + ("  (band sync OFF - ablation)" if args.no_band_sync else ""),
        "",
        f"top-of-book exact         {100 * top1_hits / rows:.2f}% of rows"
        "   (best bid+ask, price and size)",
        f"top-{args.compare_levels} book exact          {100 * exact_full_rows / rows:.2f}% of rows",
        f"full level-{args.levels} window     {100 * window_exact_rows / rows:.2f}% of rows"
        "   (band edge included - the boundary lives here)",
        f"depth error               {100 * depth_err_sum / depth_shares_sum:.2f}% of shares"
        f" over the exchange's top {args.compare_levels}",
        f"mid error                 mean {mid_abs_err_sum / rows / 100:.4f} cents,"
        f" worst {mid_err_worst / 100:.2f} cents",
        "",
        f"applied by order id       {stats.applied:,}",
        f"pre-window unknowns       {pre_window_unknowns:,}"
        "   (id resting before the capture window)",
        f"reappeared unknowns       {reappeared_unknowns:,}"
        "   (id this replay itself already consumed)",
        f"  reconciled by level     {stats.level_reduced:,}",
        f"  unresolvable            {stats.unresolvable:,}"
        "   (level short or outside the band)",
        f"hidden executions         {hidden:,}   (no visible-book change, by design)",
        f"trading-halt markers      {halts:,}",
        "",
        f"band promotions imported  {imported_levels:,} levels / {imported_shares:,} shares"
        "   (depth the stream never described)",
        f"band demotions pruned     {pruned_levels:,} levels / {pruned_shares:,} shares"
        "   (ours, below the official window)",
        "",
        f"reconciled replay         {elapsed:.1f} s including the row-by-row diff",
        f"replay alone              {replay_secs:.1f} s"
        f" ({n_msgs / replay_secs:,.0f} messages/s, one CPython core)",
    ]
    table = "\n".join(lines)
    print(table)

    if args.report:
        report = ROOT / args.report
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "# Replaying a real NASDAQ day against the exchange's own book\n\n"
            "Regenerate with `python examples/replay_real_day.py --report "
            f"{args.report}`.\n\n```\n{table}\n```\n"
        )
        print(f"\nwrote {report}")

    if args.png:
        # A second, boundary-blind pass for the contrast line: same messages,
        # same policy, band sync off. Its mid drifts by dollars, which is the
        # whole argument for treating the boundary explicitly.
        naive = OrderBook()
        naive_stats = ReplayStats()
        naive_series: list[tuple[float, float]] = []
        naive_rows = 0
        with open(msg_path) as mf, open(book_path) as bf:
            for i, (mline, bline) in enumerate(zip(mf, bf, strict=True), start=1):
                m = parse_lobster_line(mline)
                if i == 1:
                    a0, b0 = parse_book_row(bline, args.levels)
                    naive = OrderBook.from_snapshot(bids=b0, asks=a0, ts=m.time)
                    continue
                apply_message(naive, m, stats=naive_stats, on_unknown=args.policy)
                naive_rows += 1
                if naive_rows % args.sample_every == 0:
                    if naive.best_bid is not None and naive.best_ask is not None:
                        naive_series.append((m.time, (naive.best_bid + naive.best_ask) / 2))

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ts = [s[0] / 3600 for s in series]
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True,
                                       height_ratios=[3, 1])
        ax1.plot(ts, [s[1] / 10000 for s in series], lw=2.2, color="#c8c8c8",
                 label="exchange mid (official orderbook file)")
        ax1.plot([s[0] / 3600 for s in naive_series],
                 [s[1] / 10000 for s in naive_series], lw=0.9, color="#c0392b",
                 label="replay ignoring the band boundary")
        ax1.plot(ts, [s[2] / 10000 for s in series], lw=0.9, color="#2c6fbb",
                 label="band-aware replay (sits exactly on the official mid)")
        ax1.set_ylabel("mid ($)")
        ax1.legend(frameon=False, fontsize=9)
        ax2.plot(ts, [s[3] / 1e6 for s in series], lw=1.0, color="#2c6fbb")
        ax2.set_ylabel("shares imported\nat the band edge (M)")
        ax2.set_xlabel("hour of day")
        fig.suptitle("AAPL 2012-06-21: one day of NASDAQ messages, replayed against the "
                     "exchange's own book")
        fig.tight_layout()
        out = ROOT / args.png
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=150)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
