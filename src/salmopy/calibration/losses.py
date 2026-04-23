"""Ecologist-friendly loss functions.

Adapted from osmopy's `calibration/losses.py` + `objectives.py`. Each
function returns a scalar (lower = better); compose with weighted sum
for multi-objective optimization.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, Sequence

from salmopy.calibration.targets import ParityTarget


def banded_log_ratio_loss(actual: float, lower: float, upper: float) -> float:
    """Zero penalty when lower <= actual <= upper; else (log10 ratio)**2.

    For values below `lower`, penalty = (log10(lower/actual))**2.
    For values above `upper`, penalty = (log10(actual/upper))**2.

    This is the osmopy banded loss: ecologists know order-of-magnitude
    bands but not point estimates for many life-history metrics.
    """
    if actual <= 0.0:
        return float("inf")
    if lower <= actual <= upper:
        return 0.0
    if actual < lower:
        return math.log10(lower / actual) ** 2
    return math.log10(actual / upper) ** 2


def rmse_loss(actual: Sequence[float], reference: Sequence[float]) -> float:
    """sqrt(mean((a-r)**2)). NaN pair skipped; all-NaN or empty returns NaN.

    Returning NaN on no finite pairs prevents optimizers from ranking a
    crashed run (all-NaN output) as a perfect match. Callers should decide
    whether to treat NaN as `inf` (penalty), skip, or propagate.
    """
    pairs = [
        (a, r) for a, r in zip(actual, reference)
        if not (math.isnan(a) or math.isnan(r))
    ]
    if not pairs:
        return float("nan")
    s = sum((a - r) ** 2 for a, r in pairs)
    return math.sqrt(s / len(pairs))


def relative_error_loss(actual: float, reference: float) -> float:
    """|actual - reference| / max(|reference|, 1e-12)."""
    return abs(actual - reference) / max(abs(reference), 1e-12)


def stability_penalty(trajectory: Sequence[float]) -> float:
    """CV + normalized trend. Small for stable time series.

    Returns 1.0 if trajectory is empty or zero-mean.
    """
    xs = [x for x in trajectory if not math.isnan(x)]
    if len(xs) < 2:
        return 1.0
    mean = sum(xs) / len(xs)
    if abs(mean) < 1e-12:
        return 1.0
    var = sum((x - mean) ** 2 for x in xs) / len(xs)
    cv = math.sqrt(var) / abs(mean)
    # Trend: slope of linear fit / mean
    n = len(xs)
    sx = sum(range(n))
    sy = sum(xs)
    sxx = sum(i * i for i in range(n))
    sxy = sum(i * xs[i] for i in range(n))
    denom = n * sxx - sx * sx
    slope = (n * sxy - sx * sy) / denom if denom != 0 else 0.0
    trend = abs(slope * (n - 1) / mean)
    return cv + trend


def score_against_targets(
    metrics: Dict[str, float],
    targets: Iterable[ParityTarget],
) -> float:
    """Weighted multi-target loss. Each target contributes
    weight × (banded loss if lower/upper set, else relative error).

    Missing metrics are penalized as inf on the target.
    """
    total = 0.0
    for t in targets:
        if t.metric not in metrics:
            return float("inf")
        actual = metrics[t.metric]
        if t.lower is not None and t.upper is not None:
            loss = banded_log_ratio_loss(actual, t.lower, t.upper)
        else:
            loss = relative_error_loss(actual, t.reference)
            # If rtol is set, zero the loss when within tolerance
            if t.rtol is not None and loss <= t.rtol:
                loss = 0.0
            elif t.atol is not None and abs(actual - t.reference) <= t.atol:
                loss = 0.0
        total += t.weight * loss
    return total
