"""ParityTarget — ecologist-friendly target specifications.

Adapted from osmopy's `BiomassTarget` dataclass but generalized to any
scalar metric (outmigrant counts, mean lengths, peak abundance, etc.).

Targets carry a reference value + tolerance band. The loss functions in
`losses.py` consume ParityTarget to produce scalar error terms.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class ParityTarget:
    """One calibration target — a named metric, reference value, tolerance.

    Attributes
    ----------
    metric : str
        Name of the metric the model produces (e.g. "outmigrant_total").
    reference : float
        Target value (often from NetLogo or ICES field data).
    rtol : float, optional
        Relative tolerance: acceptable if |actual - ref| <= rtol * ref.
        Used by rmse_loss / relative_error_loss.
    atol : float, optional
        Absolute tolerance: acceptable if |actual - ref| <= atol.
    lower, upper : float, optional
        For banded_log_ratio_loss: zero penalty inside [lower, upper],
        squared log-distance outside.
    weight : float
        Multiplicative weight in a weighted multi-objective composition.
    source : str
        Free-form citation (e.g. "NetLogo InSALMO 7.3 seed=98").

    Notes
    -----
    Either (rtol/atol) or (lower/upper) should be set, depending on
    which loss you use downstream. rtol/atol compose with rmse_loss;
    lower/upper compose with banded_log_ratio_loss.
    """
    metric: str
    reference: float
    rtol: Optional[float] = None
    atol: Optional[float] = None
    lower: Optional[float] = None
    upper: Optional[float] = None
    weight: float = 1.0
    source: str = ""


def load_targets(path: Path) -> List[ParityTarget]:
    """Load ParityTarget rows from CSV.

    Columns (header row required):
      metric,reference,rtol,atol,lower,upper,weight,source

    Empty cells map to None; weight defaults to 1.0 if absent.
    Lines starting with '#' or '#!' are ignored (comments or
    osmopy-style metadata).
    """
    out: List[ParityTarget] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(line for line in f if not line.lstrip().startswith("#"))
        for row in reader:
            def _f(k: str) -> Optional[float]:
                v = row.get(k, "") or ""
                v = v.strip()
                return float(v) if v else None

            out.append(
                ParityTarget(
                    metric=row["metric"].strip(),
                    reference=float(row["reference"]),
                    rtol=_f("rtol"),
                    atol=_f("atol"),
                    lower=_f("lower"),
                    upper=_f("upper"),
                    weight=_f("weight") or 1.0,
                    source=(row.get("source") or "").strip(),
                )
            )
    return out
