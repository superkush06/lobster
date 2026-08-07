"""The animated depth figure has to survive being served by GitHub.

`docs/book_depth_anim.svg` and its dark twin are on the front page, fetched
from raw.githubusercontent.com, which serves them under
`default-src 'none'; style-src 'unsafe-inline'; sandbox`. Under that policy
SMIL runs, JavaScript does not, and nothing external loads: no fonts, no
images, not even a data: URI. A figure that breaks one of those rules does
not fail loudly, it just renders as a still frame, or as a blank box, on the
first page anyone sees.

So this module checks the properties the renderer cares about rather than
the picture. It reads the committed files and never runs the generator,
which needs matplotlib for the shared simulation config.

Regenerate with `python examples/make_animated_depth.py`.
"""

from __future__ import annotations

import pathlib
import re
import xml.etree.ElementTree as ET

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
README = ROOT / "README.md"
FIGURES = ("book_depth_anim.svg", "book_depth_anim_dark.svg")
SVGNS = "{http://www.w3.org/2000/svg}"

# Platane's contribution snake is 97 KB and is the largest animated SVG in
# common use on a profile page. Half of that is a comfortable ceiling.
SIZE_CAP = 60 * 1024

REGEN = "regenerate with `python examples/make_animated_depth.py`"


@pytest.fixture(params=FIGURES)
def svg(request) -> str:
    return (DOCS / request.param).read_text()


def test_parses_as_xml(svg):
    ET.fromstring(svg)


def test_fits_in_the_size_budget(svg):
    assert len(svg.encode()) < SIZE_CAP, REGEN


def test_actually_animates(svg):
    root = ET.fromstring(svg)
    tags = {e.tag.split("}")[-1] for e in root.iter()}
    assert tags & {"animate", "animateTransform", "animateMotion"}, REGEN


def test_carries_no_script(svg):
    assert "<script" not in svg.lower()
    assert not re.search(r'\son\w+\s*=', svg), "no inline event handlers"


def test_fetches_nothing_from_outside(svg):
    """Every url() and href must be a same-document fragment."""
    for ref in re.findall(r'url\(([^)]*)\)', svg) + re.findall(r'href="([^"]*)"', svg):
        assert ref.startswith("#"), f"external reference {ref!r}"
    assert "data:" not in svg
    assert "@font-face" not in svg


def test_names_a_font_stack_not_a_font(svg):
    """GitHub blocks webfonts, so every family has to end in a generic."""
    families = re.findall(r'font-family="([^"]*)"', svg)
    assert families
    for fam in families:
        last = fam.rsplit(",", 1)[-1].strip().strip("'\"")
        assert last in {"serif", "sans-serif", "monospace"}, fam


def test_the_two_themes_differ_only_in_colour():
    light, dark = (ET.fromstring((DOCS / f).read_text()) for f in FIGURES)
    shape = [e.tag for e in light.iter()]
    assert shape == [e.tag for e in dark.iter()], REGEN


# --------------------------------------------------------------------------
# the caption has to describe the motion that is actually in the file
# --------------------------------------------------------------------------
#
# The README paragraph beside the figure quotes three numbers off it: where
# the step-down starts and ends, how far the mid falls, and how long the
# sweep and the hold take. A reader who arrives mid-loop reads the caption
# before they read the picture, so a caption describing motion the file does
# not perform is worse than no caption. Nothing else in the suite ties those
# words to the artifact, because regenerating the figure needs matplotlib and
# CI installs only the `dev` extra. These two compare the committed prose
# against the committed SVG, which needs neither.


def _readme_flat() -> str:
    return re.sub(r"\s+", " ", README.read_text())


def test_the_readme_quotes_the_figures_own_annotation(svg):
    """The step-down the caption describes is the one the figure brackets."""
    root = ET.fromstring(svg)
    drawn = next(
        m for m in (
            re.search(
                r"ticks (\d+)–(\d+): the bid queues stop being replaced, "
                r"the mid falls ([\d.]+)",
                "".join(e.itertext()),
            )
            for e in root.iter(f"{SVGNS}text")
        ) if m
    )
    said = re.search(
        r"ticks (\d+) to (\d+) the bid queues stop being replaced and "
        r"the mid falls (\d+\.\d+)",
        _readme_flat(),
    )
    assert said, "the README no longer describes the step-down in the figure"
    assert said.groups() == drawn.groups(), REGEN


def test_the_readme_quotes_the_real_sweep_and_hold(svg):
    """The seconds in the caption come off the SMIL clock, not off a guess."""
    move = next(iter(ET.fromstring(svg).iter(f"{SVGNS}animateTransform")))
    dur = float(move.get("dur").rstrip("s"))
    reveal = float(move.get("keyTimes").split(";")[1])
    said = re.search(
        r"sweep takes (\d+\.\d+) seconds and the loop then holds for (\d+\.\d+)",
        _readme_flat(),
    )
    assert said, "the README no longer states the sweep and hold"
    assert float(said.group(1)) == round(dur * reveal, 1)
    assert float(said.group(2)) == round(dur * (1 - reveal), 1)
