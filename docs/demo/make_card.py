"""Render the demo's link-preview card.

The image a scanner shows when the demo URL is pasted into Slack, LinkedIn or
a message is the only thing most people will ever see of the page, so it
should be the page rather than a mock-up of it. This runs the same simulation
the demo runs, picks a frame where both makers are queued at the same price,
and draws that frame in the page's own palette.

    python docs/demo/make_card.py        # writes docs/demo/card.png

Needs the `plot` extra (matplotlib). Open Graph wants 1200x630.
"""

from __future__ import annotations

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sim  # noqa: E402

W, H = 1200, 630
PAPER, INK, QUIET, HAIR = "#F7F4EF", "#35322C", "#8B857A", "#DAD4C9"
FAST, SLOW, OTHER, TROUGH = "#1B6CA8", "#C05F1B", "#D3CCC0", "#EAE3D6"
SERIF = ["Newsreader", "Georgia", "Iowan Old Style", "DejaVu Serif"]
MONO = ["IBM Plex Mono", "Menlo", "DejaVu Sans Mono"]


def hero_frame():
    """A frame with both makers resting at one price, which is the argument."""
    d = sim.run(0.05, 0.15)
    best, chosen = -1, None
    for f in d["frames"]:
        owners = [{o for o, _ in lvl["q"]} for lvl in f]
        if not any({1, 2} <= s for s in owners):
            continue
        if len(f) > best:          # prefer a deep book, it reads better
            best, chosen = len(f), f
    if chosen is None:
        raise SystemExit("no frame had both makers at one level")
    qmax = max(sum(q for _, q in lvl["q"]) for f in d["frames"] for lvl in f)
    return chosen, qmax


def main() -> None:
    frame, qmax = hero_frame()
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=PAPER)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    ax.set_xlim(0, W); ax.set_ylim(H, 0)

    ax.text(72, 74, "L O B S T E R   ::   S T O C K   E X C H A N G E   S I M U L A T I O N",
            family=MONO, fontsize=12.5, color=QUIET, va="center")
    ax.text(70, 148, "A stock exchange you can take apart", family=SERIF,
            fontsize=50, color=INK, va="center")
    ax.text(72, 206, "A live order book, four experiments, and a matching engine in your browser.",
            family=SERIF, fontsize=20, color="#5E594F", va="center")

    rows = frame[:8]
    top, rh, bh = 262, 36, 23
    padL, padR = 190, 72
    span = W - padL - padR

    ax.text(padL, top - 22, "F I L L E D   F I R S T", family=MONO,
            fontsize=11, color=QUIET, va="center")
    ax.text(W - padR, top - 22, "R E S T I N G   S I Z E", family=MONO,
            fontsize=11, color=QUIET, va="center", ha="right")

    for i in range(8):
        y = top + i * rh + rh / 2
        if i >= len(rows):
            continue
        lvl = rows[i]
        owners = {o for o, _ in lvl["q"]}
        shared = {1, 2} <= owners
        if shared:
            ax.add_patch(mpatches.Rectangle((padL - 118, y - rh / 2 + 2),
                                            span + 118 + padR - 8, rh - 4,
                                            facecolor=TROUGH, edgecolor="none"))
        ax.text(padL - 22, y, f"{lvl['px']:.2f}", family=MONO, fontsize=15,
                color=INK if shared else QUIET, va="center", ha="right")
        x = padL
        for owner, qty in lvl["q"]:
            bw = max(4.0, (qty / qmax) * span - 2)
            ax.add_patch(mpatches.Rectangle((x, y - bh / 2), bw, bh,
                                            facecolor={1: FAST, 2: SLOW}.get(owner, OTHER),
                                            edgecolor="none"))
            if owner and bw > 62:
                ax.text(x + 11, y, {1: "FAST", 2: "SLOW"}[owner], family=MONO,
                        fontsize=11.5, color="#FFFFFF", va="center")
            x += bw + 2
        if shared:
            ax.text(x + 14, y, "BOTH MAKERS AT THIS PRICE", family=MONO,
                    fontsize=11.5, color="#6F6858", va="center")

    ax.plot([padL, padL], [top, top + 8 * rh], color=HAIR, lw=1.2)
    ax.plot([72, W - 72], [H - 66, H - 66], color=HAIR, lw=1)
    ax.text(72, H - 40, "superkush06.github.io/lobster/demo", family=MONO,
            fontsize=13, color=QUIET, va="center")
    ax.text(W - 72, H - 40, "RUNS A REAL MATCHING ENGINE IN THE BROWSER",
            family=MONO, fontsize=13, color=QUIET, va="center", ha="right")

    out = pathlib.Path(__file__).resolve().parent / "card.png"
    fig.savefig(out, facecolor=PAPER)
    print(f"wrote {out} ({W}x{H})")


if __name__ == "__main__":
    main()
