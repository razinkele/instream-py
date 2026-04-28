"""v0.46: per-day diff of TimeSeriesInputs between Baltic and Tornionjoki.

Reports mean temperature, mean flow, and min/max for matching reach files.
Tornionjoki was scaffolded with -6°C offset and 0.8x flow multiplier;
this lets us see whether those offsets produce a winter-too-cold regime
that would compound the growth-too-fast picture from B1.

Usage:
    micromamba run -n shiny python scripts/_compare_timeseries_baltic_vs_tornionjoki.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BALTIC = ROOT / "tests/fixtures/example_baltic"
TORNE = ROOT / "tests/fixtures/example_tornionjoki"

# Map prototype Baltic reach names to the new WGBAST physical-domain
# reach names (Mouth/Lower/Middle/Upper). The pairs aren't perfect but
# match approximate downstream-to-upstream order.
PAIRS = [
    ("Nemunas", "Mouth"),
    ("Atmata", "Lower"),
    ("Minija", "Middle"),
    ("Sysa", "Upper"),
]


def _read_ts(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, comment=";", header=0)


def main() -> int:
    print(f"{'reach pair':<25} {'metric':<14} {'baltic':>10} {'tornionjoki':>12} {'diff':>10}")
    print("-" * 75)
    for proto, new_name in PAIRS:
        bp = BALTIC / f"{proto}-TimeSeriesInputs.csv"
        tp = TORNE / f"{new_name}-TimeSeriesInputs.csv"
        if not bp.exists() or not tp.exists():
            print(f"{proto:>10} → {new_name:<10}  one of the files missing; skipping")
            continue
        b = _read_ts(bp)
        t = _read_ts(tp)
        for col in ("temperature", "flow"):
            if col not in b.columns or col not in t.columns:
                continue
            for stat in ("mean", "min", "max"):
                bv = float(getattr(b[col], stat)())
                tv = float(getattr(t[col], stat)())
                print(
                    f"{proto + ' -> ' + new_name:<25} {col + ' ' + stat:<14} "
                    f"{bv:>10.3f} {tv:>12.3f} {tv - bv:>10.3f}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
