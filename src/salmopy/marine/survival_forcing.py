"""WGBAST post-smolt survival forcing loader.

Converts an annual-survival series into a per-day hazard override that is
substituted for `background_hazard` in `marine_survival` for fish in the
post-smolt window (days_since_ocean_entry < 365).

Reference: ICES (2023) WGBAST §2.5, published 3-12% post-smolt survival
envelope; Olmos et al. 2018 DOI 10.1111/faf.12345 for the declining
Atlantic trend.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Tuple
import pandas as pd


def load_post_smolt_forcing(path: Path | str) -> Dict[Tuple[int, str], float]:
    """Load (year, stock_unit) -> annual_survival from CSV."""
    df = pd.read_csv(path, comment="#")
    required = {"year", "stock_unit", "survival_pct"}
    missing = required - set(df.columns)
    assert not missing, f"post-smolt CSV missing columns: {missing}"
    return {
        (int(r.year), str(r.stock_unit)): float(r.survival_pct)
        for r in df.itertuples()
    }


def annual_survival_for_year(
    series: Dict[Tuple[int, str], float],
    year: int,
    stock_unit: str,
) -> Optional[float]:
    """Return annual survival fraction (0-1), or None if unknown."""
    return series.get((int(year), str(stock_unit)))


def daily_hazard_multiplier(
    annual_survival: float,
    days_per_year: int = 365,
) -> float:
    """Convert annual survival → daily hazard.

    Solve (1 - h_daily)^days_per_year = S_annual → h_daily = 1 - S^(1/days_per_year).
    """
    s = max(0.0, min(1.0, float(annual_survival)))
    if s <= 0.0:
        return 1.0
    if s >= 1.0:
        return 0.0
    return 1.0 - s ** (1.0 / float(days_per_year))
