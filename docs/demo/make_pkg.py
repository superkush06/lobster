"""Bundle the package for the browser demo.

The demo ships `lobster` as a zip that Pyodide unpacks into its filesystem.
That bundle is a *copy*, which means it can silently fall behind the package
it was made from: add an agent, forget to rebuild, and the page keeps running
last month's engine while every claim on it cites this month's numbers.

    python docs/demo/make_pkg.py        # rewrites docs/demo/lobster-pkg.zip

`tests/test_demo_bundle.py` fails if the two ever disagree, so the drift is
caught rather than discovered.
"""

from __future__ import annotations

import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
PKG = ROOT / "lobster"
BUNDLE = ROOT / "docs" / "demo" / "lobster-pkg.zip"


def sources() -> list[pathlib.Path]:
    """Every .py in the package, in a stable order."""
    return sorted(p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)


def build(out: pathlib.Path = BUNDLE) -> int:
    files = sources()
    # Deterministic: fixed timestamps and no compression jitter, so rebuilding
    # an unchanged package produces an identical file and git stays quiet.
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            info = zipfile.ZipInfo(str(path.relative_to(ROOT)),
                                   date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, path.read_bytes())
    return len(files)


if __name__ == "__main__":
    n = build()
    print(f"wrote {BUNDLE.relative_to(ROOT)} ({n} modules, "
          f"{BUNDLE.stat().st_size:,} bytes)")
