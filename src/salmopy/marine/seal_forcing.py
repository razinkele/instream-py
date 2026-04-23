"""HELCOM grey-seal abundance forcing for marine hazard scaling.

Converts per-(year, sub_basin) seal abundance into a **Holling Type II**
saturating multiplier on the base `marine_mort_seal_max_daily` hazard.
Anchored so that `abundance == reference_abundance` produces multiplier
1.0 (preserves the pre-forcing calibration), and asymptotes at
`saturation_k_half + 1` as abundance → ∞ (bounds the extrapolation
across the 1988→2021 ≈ 15× abundance span).

Linear scaling would have projected `marine_mort_seal_max_daily × 15`
at 2021 levels — outright extinction. Holling Type II is the minimum
ecologically-defensible form that (a) returns 1.0 at the calibration
point and (b) saturates like real predator functional responses.

References:
  HELCOM. Grey seal abundance core indicator.
    https://indicators.helcom.fi/indicator/grey-seal-abundance/
  Lai, Lindroos & Grønbæk (2021). DOI 10.1007/s10640-021-00571-z
  Westphal et al. (2025). DOI 10.1002/aqc.70147
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, Tuple
import pandas as pd


def load_seal_abundance(path: Path | str) -> Dict[Tuple[int, str], float]:
    """Load (year, sub_basin) → population_estimate from CSV."""
    df = pd.read_csv(path, comment="#")
    required = {"year", "sub_basin", "population_estimate"}
    missing = required - set(df.columns)
    assert not missing, f"seal abundance CSV missing columns: {missing}"
    return {
        (int(r.year), str(r.sub_basin)): float(r.population_estimate)
        for r in df.itertuples()
    }


def abundance_for_year(
    series: Dict[Tuple[int, str], float],
    year: int,
    sub_basin: str,
) -> Optional[float]:
    """Return population estimate, or None if (year, sub_basin) unknown."""
    return series.get((int(year), str(sub_basin)))


def seal_hazard_multiplier(
    abundance: float,
    reference_abundance: float = 30000.0,
    saturation_k_half: float = 2.0,
) -> float:
    """Holling Type II saturating response, anchored to 1.0 at reference.

    mult(r) = (r / (1 + r/k)) / (1 / (1 + 1/k))
      where r = abundance / reference_abundance
            k = saturation_k_half (dimensionless, half-saturation point)

    Properties:
      r = 0 → mult = 0
      r = 1 → mult = 1.0 (calibration anchor)
      r = 2 → mult = 1.5  (sub-linear at 2× reference)
      r = 10 → mult ≈ 2.5
      r → ∞ → mult → k + 1 = 3.0 (asymptote for k=2)

    k=2 means half-saturation at 2× reference abundance. Tune via the
    `saturation_k_half` kwarg: larger k = more linear at high abundance.
    """
    if reference_abundance <= 0:
        return 1.0
    r = max(0.0, float(abundance) / float(reference_abundance))
    k = float(saturation_k_half)
    raw = r / (1.0 + r / k)
    anchor = 1.0 / (1.0 + 1.0 / k)
    return raw / anchor if anchor > 0 else 1.0
