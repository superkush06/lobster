#!/usr/bin/env python3
"""Fetch the LOBSTER AAPL 2012-06-21 level-10 sample day into data/real/.

Provenance, honestly stated. LOBSTER (https://lobsterdata.com) distributed
these sample files freely for over a decade from
``lobsterdata.com/info/sample/``; the current site puts sample access behind
a request form, and the legacy paths now serve the new frontend. This script
therefore tries the legacy official URLs first and falls back to a public
mirror of the identical files. Either way the download only counts if its
SHA256 matches the checksums below, which pin the exact bytes every real-day
number in this repository was measured on. The files are written under
``data/real/``, which is gitignored: the data is LOBSTER's to distribute,
not this repository's.

Usage:
    python tools/fetch_lobster_sample.py            # fetch + verify
    python tools/fetch_lobster_sample.py --check    # verify existing files only
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "real"

MIRROR = "https://huggingface.co/datasets/totalorganfailure/lobster-data/resolve/main"
LEGACY = "https://lobsterdata.com/info/sample"

FILES = {
    "AAPL_2012-06-21_34200000_57600000_message_10.csv": {
        "sha256": "6562394b996138d5c4527b1282e77a1a385e844110550c34628fbd73bc5411e5",
        "mirror": f"{MIRROR}/LOBSTER_SampleFile_AAPL_2012-06-21_10/"
                  "AAPL_2012-06-21_34200000_57600000_message_10.csv",
    },
    "AAPL_2012-06-21_34200000_57600000_orderbook_10.csv": {
        "sha256": "ed75450031996e81bdc5fc985f6afe6851c81d7b2b39bccf13c56d845fe6ff5d",
        "mirror": f"{MIRROR}/LOBSTER_SampleFile_AAPL_2012-06-21_10/"
                  "AAPL_2012-06-21_34200000_57600000_orderbook_10.csv",
    },
}


def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: pathlib.Path) -> bool:
    try:
        print(f"  fetching {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "lobster-fetch/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        return True
    except (urllib.error.URLError, OSError) as e:
        print(f"    unavailable ({e})")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify checksums of already-downloaded files, fetch nothing")
    args = ap.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    ok = True
    for name, spec in FILES.items():
        path = DEST / name
        if path.exists() and sha256_of(path) == spec["sha256"]:
            print(f"{name}: present, checksum verified")
            continue
        if args.check:
            print(f"{name}: MISSING or checksum mismatch")
            ok = False
            continue
        print(f"{name}:")
        got = fetch(f"{LEGACY}/{name}", path) and sha256_of(path) == spec["sha256"]
        if not got:
            got = fetch(spec["mirror"], path) and sha256_of(path) == spec["sha256"]
        if got:
            print(f"  ok, sha256={spec['sha256'][:16]}…")
        else:
            print(f"  FAILED: could not obtain a copy matching {spec['sha256'][:16]}…")
            path.unlink(missing_ok=True)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
