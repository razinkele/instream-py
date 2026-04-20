"""Apply WGBAST M74 yolk-sac-fry mortality as a one-time binomial cull
at egg→fry emergence.

M74 is a freshwater yolk-sac-fry mortality (pre-swim-up) driven by
thiamine deficiency inherited maternally. Wiring at marine stage would
compound an annual fraction as a daily hazard (0.5^365 ≈ 10⁻¹¹⁰ survival);
the correct life-stage is the egg→fry transition.

Reference: Vuorinen et al. 2021 (DOI 10.1080/10236244.2021.1941942);
WGBAST 2026 §3 (DOI 10.17895/ices.pub.29118545.v3).
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Tuple
import numpy as np

from instream.io.m74_forcing import load_m74_forcing, ysfm_for_year_river

_CACHE: Dict[Path, Dict[Tuple[int, str], float]] = {}


def apply_m74_cull(
    n_fry: int,
    year: int,
    river: str,
    forcing_csv: Path | str | None,
    rng: np.random.Generator,
) -> int:
    """Return the number of fry surviving M74 YSFM for (year, river).

    Binomial(n_fry, p_survive) where p_survive = 1 - YSFM_fraction.
    Returns `n_fry` unchanged if `forcing_csv` is None, or if the
    (year, river) tuple is not in the series.

    Negative/zero `n_fry` is returned as-is — the cull is a no-op for
    empty or invalid cohorts.
    """
    if forcing_csv is None or n_fry <= 0:
        return int(n_fry)
    path = Path(forcing_csv)
    if path not in _CACHE:
        _CACHE[path] = load_m74_forcing(path)
    ysfm = ysfm_for_year_river(_CACHE[path], year, river)
    if ysfm <= 0.0:
        return int(n_fry)
    p_survive = max(0.0, 1.0 - float(ysfm))
    return int(rng.binomial(int(n_fry), p_survive))
