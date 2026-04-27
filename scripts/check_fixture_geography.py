"""CLI report: per-reach geographic conformance for habitat-cell fixtures.

Run before committing a new fixture or after regenerating cells. Mirrors
the rules in ``tests/test_geographic_conformance.py``: river reaches
should have ``effective_width = area / mrr_length`` under the threshold
(default 350 m); marine/lagoon reaches should have at least 5 cells
and not be a single hand-traced mega-cell.

Usage:
    python scripts/check_fixture_geography.py            # all fixtures
    python scripts/check_fixture_geography.py example_baltic
    python scripts/check_fixture_geography.py --width 500  # custom threshold
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from modules.geographic_conformance import (  # noqa: E402
    DEFAULT_MAX_RIVER_EFFECTIVE_WIDTH_M,
    DEFAULT_MIN_MARINE_CELLS,
    check_fixture_geography,
)


def _ansi(code: str) -> str:
    """ANSI color code, suppressed when stdout is not a tty."""
    return code if sys.stdout.isatty() else ""


GREEN = _ansi("\033[32m")
RED = _ansi("\033[31m")
DIM = _ansi("\033[90m")
RESET = _ansi("\033[0m")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fixtures", nargs="*",
        help="fixture names (e.g. example_baltic). Default: all.",
    )
    parser.add_argument(
        "--width", type=float, default=DEFAULT_MAX_RIVER_EFFECTIVE_WIDTH_M,
        help=f"max river effective_width in meters (default {DEFAULT_MAX_RIVER_EFFECTIVE_WIDTH_M})",
    )
    parser.add_argument(
        "--min-marine-cells", type=int, default=DEFAULT_MIN_MARINE_CELLS,
        help=f"min cells for marine reaches (default {DEFAULT_MIN_MARINE_CELLS})",
    )
    args = parser.parse_args()

    fixtures_dir = ROOT / "tests" / "fixtures"
    if args.fixtures:
        fixture_dirs = [fixtures_dir / name for name in args.fixtures]
    else:
        fixture_dirs = sorted(
            d for d in fixtures_dir.iterdir()
            if d.is_dir() and not d.name.startswith("_")
            and (d / "Shapefile").exists()
        )

    total_issues = 0
    print(f"{'fixture':<24} {'reach':<22} {'class':<8} {'cells':>6} {'eff_width_m':>12}")
    print("-" * 80)
    for fx in fixture_dirs:
        if not fx.exists():
            print(f"{RED}MISSING{RESET}: {fx}")
            continue
        results = check_fixture_geography(
            fx,
            max_river_effective_width_m=args.width,
            min_marine_cells=args.min_marine_cells,
        )
        if not results:
            print(f"{DIM}{fx.name}{RESET}: no shapefile / no reach column")
            continue

        for reach, (metrics, cls, issues) in results.items():
            color = RED if issues else GREEN
            mark = "FAIL" if issues else "ok"
            print(
                f"{fx.name:<24} {reach:<22} {cls:<8} {metrics.cells:>6} "
                f"{metrics.effective_width_m:>12.0f}  "
                f"{color}{mark}{RESET}"
            )
            for issue in issues:
                total_issues += 1
                print(f"{' ' * 56}  {RED}↳ {issue.code}: {issue.message}{RESET}")

    if total_issues:
        print(f"\n{RED}{total_issues} issue(s) found.{RESET}")
        return 1
    print(f"\n{GREEN}All reaches geographically plausible.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
