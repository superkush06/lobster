"""Re-derive every number README.md prints, and fail if any of them moved.

The README quotes example output verbatim — agent P&L, the stylized-facts
scorecard, the latency race, the cost-curve table, the replay snapshot, the
validation table. Prose like that rots silently: a one-line change to the
quoting kernel shifts the scorecard and nobody notices, and then the front
page of the repository is quietly making claims the code no longer supports.

So the blocks are extracted from README.md itself and diffed against a live
run. Retyping `1524` as `1525`, or `-0.370` as `-0.371`, fails this module.

Two shapes of block:

* whole-output blocks (`market_maker_demo`, `latency_race`) are compared for
  exact equality against the script's stdout;
* excerpt blocks (the scorecard, the cost table, the validation table) are
  hand-assembled slices, so each of their lines must appear in the output.

The heavy runs here are the reason this module costs ~16 s. That is the
price of the README being true.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
EXAMPLES = ROOT / "examples"

_FENCE = re.compile(r"^```(\w*)\n(.*?)^```", re.S | re.M)


def blocks() -> list[tuple[str, str]]:
    return [(lang, body) for lang, body in _FENCE.findall(README.read_text())]


def block_starting(prefix: str) -> str:
    """The one fenced block whose body starts with `prefix`."""
    hits = [body for _, body in blocks() if body.startswith(prefix)]
    assert len(hits) == 1, f"expected exactly one README block starting {prefix!r}, got {len(hits)}"
    return hits[0].rstrip("\n")


def run_example(name: str, *args: str) -> str:
    """Run examples/<name>.py from the repository root and return stdout."""
    proc = subprocess.run(
        [sys.executable, str(EXAMPLES / f"{name}.py"), *args],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return proc.stdout


def exec_block(src: str) -> str:
    """Execute a README python block from the repo root, returning its stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(src, "<readme>", "exec"), {"__name__": "__readme__"})
    return buf.getvalue()


def assert_lines_present(block: str, output: str) -> None:
    missing = [ln for ln in block.splitlines() if ln.strip() and ln not in output]
    assert not missing, "README lines absent from live output:\n" + "\n".join(missing)


# --------------------------------------------------------------------------
# the two blocks the README presents as complete program output
# --------------------------------------------------------------------------

def test_market_maker_demo_output_is_verbatim():
    block = block_starting("Trades:")
    assert run_example("market_maker_demo").strip() == block.strip()


def test_latency_race_output_is_verbatim():
    block = block_starting("Latency race:")
    assert run_example("latency_race").strip() == block.strip()


# --------------------------------------------------------------------------
# excerpts
# --------------------------------------------------------------------------

def test_scorecard_block_matches():
    block = block_starting("Stylized-facts scorecard")
    assert_lines_present(block, run_example("scorecard"))


def test_execution_cost_table_matches():
    block = block_starting("  cost per share =")
    assert_lines_present(block, run_example("execution_costs"))


VALIDATION_ROWS = [
    # (README table cell, anchor in validate.py output)
    ("0.09987", "s=0.10 sigma=0.01: implied spread"),
    ("0.0224", "q=2: sd of VR"),
    ("0.5038", "depth linear in distance"),
    ("2.000000000000", "impact(4Q) / impact(Q)"),
]


def test_validation_table_matches_validate_py():
    """The four-row table under 'Does it agree with anything outside itself?'."""
    table = "\n".join(ln for ln in README.read_text().splitlines() if ln.startswith("|"))
    out = run_example("validate", "--part", "1")
    for cell, anchor in VALIDATION_ROWS:
        assert f"| {cell} |" in table, f"README table no longer quotes {cell}"
        line = next((ln for ln in out.splitlines() if anchor in ln), None)
        assert line is not None, f"validate.py no longer prints {anchor!r}"
        assert cell in line, f"README says {cell} for {anchor!r}; validate.py printed:\n{line}"


# --------------------------------------------------------------------------
# the inline python the README asks the reader to paste
# --------------------------------------------------------------------------

def test_thirty_seconds_block_prints_its_comments():
    """`print(x)   # 100.5` — the comment is the assertion."""
    src = block_starting("from lobster import OrderBook, Order, Side, OrderType, match")
    expected = re.findall(r"^print\(.*?\)\s*#\s*(\S+)\s*$", src, re.M)
    assert len(expected) == 2, "the Thirty seconds block changed shape"
    got = exec_block(src).split()
    assert got == expected


def test_replay_block_reproduces_its_output():
    src = block_starting("from lobster import OrderBook, ReplayStats, replay_csv")
    expected = block_starting("{'bids':")
    assert exec_block(src).strip() == expected.strip()


# --------------------------------------------------------------------------
# claims about the repository itself
# --------------------------------------------------------------------------

def _readme_flat() -> str:
    """README text with line wrapping removed, so claims split across lines match."""
    return re.sub(r"\s+", " ", README.read_text())


def test_readme_test_count_is_the_real_test_count():
    """'2,500 lines of tests (173 of them)' — the 173 is checked here."""
    proc = subprocess.run([sys.executable, "-m", "pytest", "--collect-only",
                           "-p", "no:cacheprovider"],
                          cwd=ROOT, capture_output=True, text=True, check=True)
    collected = int(re.search(r"(\d+) tests? collected", proc.stdout).group(1))
    stated = int(re.search(r"\((\d[\d,]*) of them\)", _readme_flat()).group(1).replace(",", ""))
    assert stated == collected, f"README says {stated} tests; the suite collects {collected}"


@pytest.mark.parametrize("pkg,label", [("lobster", "Python"), ("tests", "tests")])
def test_readme_line_counts_are_within_five_percent(pkg, label):
    actual = sum(len(p.read_text().splitlines()) for p in sorted((ROOT / pkg).rglob("*.py")))
    stated = int(re.search(rf"([\d,]+) lines of (?:dependency-free )?{label}",
                           _readme_flat()).group(1).replace(",", ""))
    assert abs(actual - stated) / actual < 0.05, f"README says {stated} lines of {label}; found {actual}"


def test_every_script_the_readme_names_exists():
    text = README.read_text()
    for rel in sorted(set(re.findall(r"(?:examples|benchmarks)/[\w./]+\.(?:py|ipynb)", text))):
        assert (ROOT / rel).exists(), f"README references missing file {rel}"


def test_module_tree_block_matches_the_package():
    """The `What's in the box` tree must name files that are actually there."""
    tree = block_starting("lobster/")
    for line in tree.splitlines()[1:]:
        name = line.split("#")[0].strip().lstrip("├└─│ ").strip()
        if not name:
            continue
        assert (ROOT / "lobster" / name).exists(), f"tree names missing {name}"
