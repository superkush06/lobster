"""Draw the book-through-time figure as an animated SVG, by hand.

    python examples/make_animated_depth.py

Writes docs/book_depth_anim.svg and docs/book_depth_anim_dark.svg.

This is the same run as docs/book_depth.png: same agents, same seed, same
1,400 ticks, imported from make_figures so the two pictures cannot disagree.
The PNG is a snapshot of something temporal, so this version puts the clock
back in. A read head sweeps left to right at the simulation clock and the
depth field is uncovered behind it, so you watch the corridor of depth form
rather than arriving at it finished. Two dots ride the head at the current
best bid and ask. The loop holds at the end so the finished frame reads as a
still.

The technique is a moving curtain. Everything is drawn once, statically, and
a single opaque rectangle translates across the plot to hide the part of the
run that hasn't happened yet. That costs two animated elements instead of the
tens of thousands an element-per-order-per-tick approach would need. One
animateTransform drives both the curtain and the read head, so they can't
drift apart. The depth field underneath is run-length encoded along time into
one path per colour bucket, which is what keeps the file small enough for
GitHub to serve.

Constraints this file is written against: GitHub renders an SVG from
raw.githubusercontent.com under a sandbox CSP, so SMIL animates but
JavaScript does not run, and external fonts and images do not load. Hence
inline everything, and name a font stack rather than a font.
"""

from __future__ import annotations

import math
import pathlib
import sys

from lobster import Side, Simulation

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from make_figures import BIN, demo_agents  # noqa: E402

DOCS = pathlib.Path(__file__).resolve().parents[1] / "docs"

STEPS = 1400
SEED = 7

# ---- geometry, in user units; one unit of x is exactly one tick ------------
PX = 66            # plot left
PY = 78            # plot top
ROWH = 4           # user units per BIN-wide price bucket
GAP = 30           # between the depth panel and the spread panel
SPRH = 96          # spread panel height
RAMP_W = 15        # colour legend swatch width
RIGHT = 104        # right margin, holds the colour legend

# ---- animation -------------------------------------------------------------
DUR = 11.0         # seconds for one loop
REVEAL = 25 / 32   # fraction of the loop spent sweeping; the rest is the hold
DOT_EVERY = 4      # tick spacing of the samples the riding dots interpolate

# ---- colour ----------------------------------------------------------------
# Six log-spaced buckets of resting size. Monochrome on purpose: the depth
# field is the ground, and the two accents have to read on top of it.
NLEV = 6

THEMES = {
    "light": dict(
        page="#F7F4EF", panel="#FDFBF7", frame="#DAD4C9", ink="#35322C",
        quiet="#8B857A", bid="#1B6CA8", ask="#C05F1B", head="#35322C",
        ramp=["#EBE3D2", "#CFC2A6", "#AA9A7D", "#7C6E54", "#4E4433", "#231E17"],
    ),
    "dark": dict(
        page="#171613", panel="#1E1C18", frame="#3A362E", ink="#EDE8DE",
        quiet="#96907F", bid="#5AA6DE", ask="#E28844", head="#EDE8DE",
        ramp=["#37332B", "#554F41", "#7B7360", "#A49A82", "#CDC3A8", "#F0E8D4"],
    ),
}

MONO = ("'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace")
SERIF = "Newsreader,Georgia,'Times New Roman',serif"


# ---- the run ---------------------------------------------------------------

class Run:
    """One pass of the simulator, reduced to what the picture needs."""

    def __init__(self, steps: int, seed: int) -> None:
        sim = Simulation(agents=demo_agents(), seed=seed)
        grid: list[dict[int, int]] = []
        touch: list[tuple[float, float]] = []
        prints: list[tuple[int, float, Side]] = []
        seen = 0
        for k, m in enumerate(sim.run(steps)):
            col: dict[int, int] = {}
            for side in (Side.BUY, Side.SELL):
                for lv in sim.book.iter_levels(side):
                    b = round(lv.price / BIN)
                    col[b] = col.get(b, 0) + lv.total_qty
            grid.append(col)
            assert m.best_bid is not None and m.best_ask is not None
            touch.append((m.best_bid, m.best_ask))
            for t in list(sim.tape)[seen:]:
                prints.append((k, t.price, t.aggressor))
            seen = len(sim.tape)

        self.grid = grid
        self.touch = touch
        self.prints = prints
        bins = sorted({b for c in grid for b in c})
        self.lo, self.hi = bins[0], bins[-1]
        self.qmin = min(q for c in grid for q in c.values())
        self.qmax = max(q for c in grid for q in c.values())

    @property
    def rows(self) -> int:
        return self.hi - self.lo + 1

    def bucket(self, q: int) -> int:
        """Which of NLEV log-spaced size buckets a resting queue falls in."""
        t = math.log(q / self.qmin) / math.log(self.qmax / self.qmin)
        return min(NLEV - 1, int(t * NLEV))

    def edges(self) -> list[float]:
        r = self.qmax / self.qmin
        return [self.qmin * r ** (i / NLEV) for i in range(NLEV + 1)]

    def worst_drop(self, window: int = 200) -> tuple[int, int, float]:
        """The steepest sustained fall in the mid, and where it happens."""
        mid = [(b + a) / 2.0 for b, a in self.touch]
        s = max(range(len(mid) - window), key=lambda i: mid[i] - mid[i + window])
        return s, s + window, mid[s] - mid[s + window]


# ---- number formatting; every byte of these ends up in the file ------------

def n(v: float) -> str:
    """Shortest faithful spelling of a coordinate."""
    r = round(v, 1)
    if r == int(r):
        return str(int(r))
    return f"{r:.1f}"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- the depth field: run-length encoded along time ------------------------

def depth_paths(run: Run) -> list[str]:
    """One path per colour bucket. Each resting queue is a horizontal stroke
    of ROWH width, and adjacent ticks at the same bucket merge into one."""
    cell = [[-1] * len(run.grid) for _ in range(run.rows)]
    for x, col in enumerate(run.grid):
        for b, q in col.items():
            cell[run.hi - b][x] = run.bucket(q)

    out = []
    for lvl in range(NLEV):
        parts: list[str] = []
        px, py = 0.0, 0.0
        for r in range(run.rows):
            yc = PY + r * ROWH + ROWH / 2
            x = 0
            while x < len(run.grid):
                if cell[r][x] != lvl:
                    x += 1
                    continue
                x1 = x
                while x1 < len(run.grid) and cell[r][x1] == lvl:
                    x1 += 1
                sx = PX + x
                parts.append(f"m{n(sx - px)},{n(yc - py)}h{x1 - x}")
                px, py = sx + (x1 - x), yc
                x = x1
        out.append("".join(parts))
    return out


# ---- stepped series --------------------------------------------------------

def step_path(ys: list[float], close_to: float | None = None) -> str:
    """A price series is a step function, so draw it as one: only emit a
    corner where the value actually changes."""
    parts = [f"M{PX},{n(ys[0])}"]
    cur = ys[0]
    run_len = 0
    for i in range(1, len(ys)):
        run_len += 1
        if ys[i] != cur:
            parts.append(f"h{run_len}v{n(ys[i] - cur)}")
            cur = ys[i]
            run_len = 0
    if run_len:
        parts.append(f"h{run_len}")
    if close_to is not None:
        parts.append(f"V{n(close_to)}H{PX}z")
    return "".join(parts)


def print_path(pts: list[tuple[float, float]], up: bool) -> str:
    """All the prints on one side as a single path of little triangles."""
    parts: list[str] = []
    px, py = 0.0, 0.0
    tail = "l5,8h-10z" if up else "l5,-8h-10z"
    for x, y in pts:
        ax, ay = x, (y - 4 if up else y + 4)
        parts.append(f"m{n(ax - px)},{n(ay - py)}{tail}")
        px, py = ax, ay
    return "".join(parts)


# ---- the read head's vertical samples --------------------------------------

def dot_values(ys: list[float]) -> str:
    """Sample the touch every DOT_EVERY ticks, then pad the list with copies
    of the last value so that the evenly spaced values finish exactly when the
    sweep does. That buys the hold without spending bytes on keyTimes."""
    motion = [ys[i] for i in range(0, len(ys), DOT_EVERY)] + [ys[-1]]
    intervals = len(motion) - 1
    total = round(intervals / REVEAL)
    assert abs(intervals / total - REVEAL) < 1e-12, "pick a divisible DOT_EVERY"
    return ";".join(n(v) for v in motion + [ys[-1]] * (total + 1 - len(motion)))


# ---- the drawing -----------------------------------------------------------

def build(run: Run, theme: str) -> str:
    t = THEMES[theme]
    w = PX + STEPS + RIGHT
    plot_b = PY + run.rows * ROWH
    spr_t = plot_b + GAP
    spr_b = spr_t + SPRH
    h = spr_b + 62

    top_price = (run.hi + 0.5) * BIN

    def ypx(price: float) -> float:
        return PY + (top_price - price) / BIN * ROWH

    spreads = [a - b for b, a in run.touch]
    spr_max = math.ceil(max(spreads) * 10) / 10

    def yspr(s: float) -> float:
        return spr_b - s / spr_max * SPRH

    o: list[str] = []
    o.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{MONO}">'
    )
    o.append(
        f'<defs><clipPath id="pa"><rect x="{PX}" y="{PY}" width="{STEPS}" '
        f'height="{spr_b - PY}"/></clipPath>'
        f'<linearGradient id="gl">'
        f'<stop offset="0" stop-color="{t["head"]}" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="{t["head"]}" stop-opacity=".13"/>'
        f'<stop offset="1" stop-color="{t["head"]}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
    )
    o.append(f'<rect width="{w}" height="{h}" fill="{t["page"]}"/>')

    # --- titles
    o.append(
        f'<text x="{PX}" y="34" font-family="{SERIF}" font-size="21" '
        f'fill="{t["ink"]}">Every resting order, every level, every tick, '
        f'colour is queue depth on a log scale</text>'
    )
    lo_p, hi_p = (run.lo - 0.5) * BIN, top_price
    o.append(
        f'<text x="{PX}" y="57" font-size="13" fill="{t["quiet"]}">'
        f'{STEPS:,} ticks &#183; seed {SEED} &#183; {len(run.prints)} prints '
        f'&#183; {run.rows} price levels from {lo_p:.2f} to {hi_p:.2f} '
        f'&#183; the head is the simulation clock</text>'
    )

    # --- panels
    for y0, hh in ((PY, plot_b - PY), (spr_t, SPRH)):
        o.append(
            f'<rect x="{PX}" y="{y0}" width="{STEPS}" height="{hh}" '
            f'fill="{t["panel"]}" stroke="{t["frame"]}"/>'
        )

    # --- everything that gets revealed
    o.append('<g clip-path="url(#pa)">')

    paths = depth_paths(run)
    for lvl, d in enumerate(paths):
        o.append(
            f'<path d="{d}" stroke="{t["ramp"][lvl]}" stroke-width="{ROWH}" '
            f'fill="none" shape-rendering="crispEdges"/>'
        )

    bid = step_path([round(ypx(b) * 2) / 2 for b, _ in run.touch])
    ask = step_path([round(ypx(a) * 2) / 2 for _, a in run.touch])
    o.append(f'<path d="{bid}" stroke="{t["bid"]}" stroke-width="1.6" fill="none"/>')
    o.append(f'<path d="{ask}" stroke="{t["ask"]}" stroke-width="1.6" fill="none"/>')

    for side, colour, up in ((Side.BUY, t["bid"], True), (Side.SELL, t["ask"], False)):
        pts = [(PX + k, round(ypx(p))) for k, p, s in run.prints if s is side]
        o.append(
            f'<path d="{print_path(pts, up)}" fill="{colour}" '
            f'stroke="{t["panel"]}" stroke-width="1" stroke-linejoin="round"/>'
        )

    area = step_path([round(yspr(s)) for s in spreads], close_to=spr_b)
    o.append(
        f'<path d="{area}" fill="{t["bid"]}" fill-opacity=".28" '
        f'stroke="{t["bid"]}" stroke-width=".8" stroke-opacity=".85"/>'
    )

    # --- the curtain and the read head, moved by one transform
    o.append(
        f'<g><animateTransform attributeName="transform" type="translate" '
        f'values="0 0;{STEPS} 0;{STEPS} 0" keyTimes="0;{REVEAL};1" '
        f'dur="{DUR}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="1;1;0;0" '
        f'keyTimes="0;{REVEAL};{REVEAL + 0.055};1" dur="{DUR}s" '
        f'repeatCount="indefinite"/>'
    )
    o.append(
        f'<rect x="{PX}" y="{PY}" width="{STEPS + 40}" height="{spr_b - PY}" '
        f'fill="{t["panel"]}"/>'
    )
    o.append(f'<rect x="{PX - 26}" y="{PY}" width="52" height="{plot_b - PY}" fill="url(#gl)"/>')
    for y0, y1 in ((PY, plot_b), (spr_t, spr_b)):
        o.append(
            f'<rect x="{PX - 0.9}" y="{y0}" width="1.8" height="{y1 - y0}" '
            f'fill="{t["head"]}" fill-opacity=".75"/>'
        )
    for ys, colour in (
        ([ypx(b) for b, _ in run.touch], t["bid"]),
        ([ypx(a) for _, a in run.touch], t["ask"]),
    ):
        o.append(
            f'<circle cx="{PX}" r="4.2" fill="{colour}" stroke="{t["panel"]}" '
            f'stroke-width="1.4"><animate attributeName="cy" '
            f'values="{dot_values(ys)}" dur="{DUR}s" repeatCount="indefinite"/>'
            f'</circle>'
        )
    o.append("</g>")

    # --- the annotation, faded in over the hold
    s0, s1, drop = run.worst_drop()
    ay = ypx(top_price - 0.42)
    o.append(
        f'<g opacity="0" fill="{t["ask"]}"><animate attributeName="opacity" '
        f'values="0;0;1;1" keyTimes="0;{REVEAL + 0.02};{REVEAL + 0.09};1" '
        f'dur="{DUR}s" repeatCount="indefinite"/>'
        f'<path d="M{PX + s0},{n(ay - 6)}v12M{PX + s0},{n(ay)}H{PX + s1}'
        f'M{PX + s1},{n(ay - 6)}v12" stroke="{t["ask"]}" stroke-width="1.4" fill="none"/>'
        f'<text x="{PX + s1}" y="{n(ay - 12)}" font-size="13" text-anchor="end">'
        f'ticks {s0}&#8211;{s1}: the bid queues stop being replaced, '
        f'the mid falls {drop:.2f}</text></g>'
    )
    o.append("</g>")

    # --- axes, always visible, drawn over the curtain
    for p in range(math.ceil(lo_p), int(hi_p) + 1):
        y = ypx(p)
        o.append(
            f'<path d="M{PX - 6},{n(y)}h6" stroke="{t["frame"]}"/>'
            f'<text x="{PX - 10}" y="{n(y + 4)}" font-size="13" '
            f'text-anchor="end" fill="{t["quiet"]}">{p}</text>'
        )
    o.append(
        f'<text transform="translate({PX - 46},{(PY + plot_b) / 2}) rotate(-90)" '
        f'font-size="13" text-anchor="middle" fill="{t["quiet"]}">price</text>'
    )
    # Two decimals, always. The middle gridline is spr_max/2, which lands on a
    # half-cent whenever spr_max is an odd number of cents, and one decimal
    # would print that 0.45 line as "0.5" and put the label 11% off the rule
    # it's labelling.
    for i in range(3):
        s = spr_max * i / 2
        y = yspr(s)
        o.append(
            f'<path d="M{PX},{n(y)}h{STEPS}" stroke="{t["frame"]}" '
            f'stroke-opacity=".55"/>'
            f'<text x="{PX - 10}" y="{n(y + 4)}" font-size="12" '
            f'text-anchor="end" fill="{t["quiet"]}">{s:.2f}</text>'
        )
    o.append(
        f'<text transform="translate({PX - 46},{(spr_t + spr_b) / 2}) rotate(-90)" '
        f'font-size="13" text-anchor="middle" fill="{t["quiet"]}">spread</text>'
    )
    for k in range(0, STEPS + 1, 200):
        o.append(
            f'<path d="M{PX + k},{spr_b}v6" stroke="{t["frame"]}"/>'
            f'<text x="{PX + k}" y="{spr_b + 21}" font-size="13" '
            f'text-anchor="middle" fill="{t["quiet"]}">{k}</text>'
        )
    o.append(
        f'<text x="{PX + STEPS // 2}" y="{spr_b + 43}" font-size="13" '
        f'text-anchor="middle" fill="{t["quiet"]}">tick</text>'
    )

    # --- legend: the two touch lines and the two print markers
    lx, ly = PX + 16, plot_b - 22
    o.append(
        f'<rect x="{lx - 10}" y="{ly - 21}" width="512" height="30" rx="3" '
        f'fill="{t["panel"]}" fill-opacity=".9" stroke="{t["frame"]}"/>'
    )
    o.append(
        f'<path d="M{lx},{ly - 4}h18" stroke="{t["bid"]}" stroke-width="1.6"/>'
        f'<text x="{lx + 24}" y="{ly}" font-size="12" fill="{t["quiet"]}">best bid</text>'
        f'<path d="M{lx + 92},{ly - 4}h18" stroke="{t["ask"]}" stroke-width="1.6"/>'
        f'<text x="{lx + 116}" y="{ly}" font-size="12" fill="{t["quiet"]}">best ask</text>'
        f'<path d="M{lx + 188},{ly - 8}l5,8h-10z" fill="{t["bid"]}"/>'
        f'<path d="M{lx + 206},{ly}l5,-8h-10z" fill="{t["ask"]}"/>'
        f'<text x="{lx + 218}" y="{ly}" font-size="12" fill="{t["quiet"]}">'
        f'prints, buyer- and seller-initiated</text>'
    )

    # --- colour legend for the depth ramp
    rx = PX + STEPS + 20
    rh = 26
    ry0 = PY + 6
    edges = run.edges()
    for i in range(NLEV):
        o.append(
            f'<rect x="{rx}" y="{ry0 + (NLEV - 1 - i) * rh}" width="{RAMP_W}" '
            f'height="{rh}" fill="{t["ramp"][i]}"/>'
        )
    for i, e in enumerate(edges):
        y = ry0 + (NLEV - i) * rh
        o.append(
            f'<text x="{rx + RAMP_W + 6}" y="{n(y + 4)}" font-size="11" '
            f'fill="{t["quiet"]}">{round(e)}</text>'
        )
    o.append(
        f'<text transform="translate({rx + RAMP_W + 44},{ry0 + NLEV * rh / 2}) rotate(90)" '
        f'font-size="12" text-anchor="middle" fill="{t["quiet"]}">resting shares</text>'
    )

    o.append("</svg>")
    return "".join(o)


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    run = Run(STEPS, SEED)
    s0, s1, drop = run.worst_drop()
    for theme in THEMES:
        name = "book_depth_anim.svg" if theme == "light" else "book_depth_anim_dark.svg"
        out = DOCS / name
        svg = build(run, theme)
        out.write_text(svg)
        print(f"wrote {out}  {len(svg.encode()):,} bytes")
    print(f"  {STEPS} ticks, {len(run.prints)} prints, "
          f"queues {run.qmin}-{run.qmax} shares over {run.rows} levels")
    print(f"  steepest fall: ticks {s0}-{s1}, mid down {drop:.3f}")
    print(f"  loop {DUR}s, sweep {DUR * REVEAL:.2f}s, hold {DUR * (1 - REVEAL):.2f}s")


if __name__ == "__main__":
    main()
