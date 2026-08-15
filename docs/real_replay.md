# Replaying a real NASDAQ day against the exchange's own book

Regenerate with `python examples/replay_real_day.py --report docs/real_replay.md`.

```
ticker-day                AAPL 2012-06-21 (LOBSTER sample, level 10)
messages                  400,391
policy                    reduce_level

top-of-book exact         100.00% of rows   (best bid+ask, price and size)
top-5 book exact          100.00% of rows
full level-10 window     73.88% of rows   (band edge included - the boundary lives here)
depth error               0.00% of shares over the exchange's top 5
mid error                 mean 0.0000 cents, worst 0.00 cents

applied by order id       372,074
pre-window unknowns       8,381   (id resting before the capture window)
reappeared unknowns       8,603   (id this replay itself already consumed)
  reconciled by level     16,984
  unresolvable            0   (level short or outside the band)
hidden executions         11,332   (no visible-book change, by design)
trading-halt markers      0

band promotions imported  104,562 levels / 19,829,292 shares   (depth the stream never described)
band demotions pruned     106,380 levels / 19,668,918 shares   (ours, below the official window)

reconciled replay         4.9 s including the row-by-row diff
replay alone              0.6 s (649,482 messages/s, one CPython core)
```
