"""The browser demo ships a copy of the package. Keep it honest.

`docs/demo/lobster-pkg.zip` is what Pyodide unpacks and imports, so it is the
engine the published page actually runs. Nothing forces it to match the source
tree, and when it does not the failure is quiet in the worst way: the page
keeps working, on last month's code, while its prose cites this month's
numbers. That happened once already, with a bundle that predated `ValueAgent`.

Rebuild with `python docs/demo/make_pkg.py`.
"""

from __future__ import annotations

import pathlib
import sys
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "docs" / "demo" / "lobster-pkg.zip"

sys.path.insert(0, str(ROOT / "docs" / "demo"))
from make_pkg import sources  # noqa: E402

REBUILD = "stale bundle; rebuild with `python docs/demo/make_pkg.py`"


@pytest.fixture(scope="module")
def bundled() -> dict[str, bytes]:
    with zipfile.ZipFile(BUNDLE) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_bundle_holds_every_module(bundled):
    want = {str(p.relative_to(ROOT)) for p in sources()}
    assert want - set(bundled) == set(), REBUILD


def test_bundle_holds_nothing_extra(bundled):
    want = {str(p.relative_to(ROOT)) for p in sources()}
    assert set(bundled) - want == set(), REBUILD


@pytest.mark.parametrize("path", sources(), ids=lambda p: p.name)
def test_bundled_source_is_byte_identical(bundled, path):
    name = str(path.relative_to(ROOT))
    assert bundled.get(name) == path.read_bytes(), f"{name}: {REBUILD}"


def test_the_demo_driver_imports_only_what_is_bundled():
    """sim.py may import `lobster` and the standard library, nothing else.

    Pyodide gets exactly two things: the bundle above and whatever CPython
    ships with. A third-party import here would import fine on a developer's
    machine and fail only in the browser, which is the worst place to find out.
    """
    import ast
    tree = ast.parse((ROOT / "docs" / "demo" / "sim.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
    allowed = set(sys.stdlib_module_names) | {"lobster", "__future__"}
    assert imported <= allowed, (
        f"sim.py imports {sorted(imported - allowed)}, which Pyodide will not have"
    )


def test_bundle_stamp_matches_the_bundle():
    """bundle.json must name the bytes the page will actually fetch.

    The page hangs a cache-busting version on the asset URL from this file. If
    the stamp goes stale the URL stops changing, a CDN keeps serving the old
    zip against new HTML, and the failure is an ImportError deep in Pyodide
    with nothing pointing at the cause.
    """
    import hashlib
    import json
    demo = ROOT / "docs" / "demo"
    stamp = json.loads((demo / "bundle.json").read_text())
    raw = (demo / "lobster-pkg.zip").read_bytes()
    assert stamp["sha"] == hashlib.sha256(raw).hexdigest()[:12], REBUILD
    assert stamp["modules"] == len(sources()), REBUILD
    # sim.py ships outside the zip and is versioned separately, so a
    # driver-only edit has to move a hash of its own.
    driver = (demo / "sim.py").read_bytes()
    assert stamp["driver"] == hashlib.sha256(driver).hexdigest()[:12], REBUILD
