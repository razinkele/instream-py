"""WGBAST M74 (thiamine-deficiency yolk-sac-fry mortality) forcing loader.

Reference: Vuorinen et al. 2021 (DOI 10.1080/10236244.2021.1941942),
Simojoki + Tornionjoki + Kemijoki annual YSFM 1985/86-2019/20, extended
through 2024 from WGBAST 2026 §3 (DOI 10.17895/ices.pub.29118545.v3).

M74 is a freshwater yolk-sac-fry mortality (pre-swim-up). This module's
output feeds into `src/instream/modules/egg_emergence_m74.py`, which
applies the fraction as a one-time binomial cull at egg->fry emergence,
NOT into the marine survival kernel.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Tuple
import pandas as pd


def load_m74_forcing(path: Path | str) -> Dict[Tuple[int, str], float]:
    """Load a (year, river) -> YSFM fraction dict from CSV.

    CSV must have columns `year`, `river`, `ysfm_fraction` (plus any
    other columns, which are ignored). Lines beginning with `#` are
    treated as comments.
    """
    df = pd.read_csv(path, comment="#")
    required = {"year", "river", "ysfm_fraction"}
    missing = required - set(df.columns)
    assert not missing, f"M74 CSV missing columns: {missing}"
    return {
        (int(r.year), str(r.river)): float(r.ysfm_fraction)
        for r in df.itertuples()
    }


def ysfm_for_year_river(
    series: Dict[Tuple[int, str], float],
    year: int,
    river: str,
) -> float:
    """Return the YSFM fraction, or 0.0 if (year, river) is unknown."""
    return float(series.get((int(year), str(river)), 0.0))
