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

DOCS = pathlib.Path(__file__).resolve().parents[1] / "docs"
FIGURES = ("book_depth_anim.svg", "book_depth_anim_dark.svg")

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
