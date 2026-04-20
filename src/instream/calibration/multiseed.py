"""Multi-seed candidate validation.

Adapted from osmopy's `calibration/multiseed.py`. Re-runs any
evaluate-candidate call across a fixed seed list and returns
mean/std/CV/worst-seed metrics, so optimizers can rank stochastic
candidates robustly.
"""
from __future__ import annotations

import math
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable, Dict, Iterable, List, Sequence, Tuple


DEFAULT_SEEDS: Tuple[int, ...] = (42, 123, 7, 999, 2024)


def validate_multiseed(
    eval_fn: Callable[[int], Dict[str, float]],
    seeds: Sequence[int] = DEFAULT_SEEDS,
    parallel: bool = False,
) -> Dict[str, Dict[str, float]]:
    """Run eval_fn(seed) over a set of seeds and aggregate per-metric stats.

    Parameters
    ----------
    eval_fn : callable(seed) -> dict
        Evaluates one candidate at the given seed, returning named metrics.
    seeds : sequence of ints
        Seed list. Default 5 seeds — enough for CV estimate, cheap to run.
    parallel : bool
        If True, use ProcessPoolExecutor (each seed in its own process to
        dodge the Numba JIT cache singleton and any numpy random-state
        global state). If False, sequential.

    Returns
    -------
    dict
        Per-metric {metric: {mean, std, cv, worst, best, n}}.
    """
    per_seed: List[Dict[str, float]] = []
    if parallel:
        with ProcessPoolExecutor() as ex:
            futures = {ex.submit(eval_fn, s): s for s in seeds}
            for fut in as_completed(futures):
                per_seed.append(fut.result())
    else:
        for s in seeds:
            per_seed.append(eval_fn(s))

    if not per_seed:
        return {}
    metric_names = set().union(*(r.keys() for r in per_seed))
    out: Dict[str, Dict[str, float]] = {}
    for m in metric_names:
        vals = [r[m] for r in per_seed if m in r and not math.isnan(r[m])]
        if not vals:
            out[m] = {
                "mean": float("nan"), "std": 0.0, "cv": 0.0,
                "worst": float("nan"), "best": float("nan"), "n": 0,
            }
            continue
        mean = sum(vals) / len(vals)
        std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        cv = std / abs(mean) if abs(mean) > 1e-12 else 0.0
        out[m] = {
            "mean": mean,
            "std": std,
            "cv": cv,
            "worst": max(vals),
            "best": min(vals),
            "n": len(vals),
        }
    return out


def rank_candidates_multiseed(
    candidates: Iterable[Dict[str, float]],
    eval_fn: Callable[[Dict[str, float], int], Dict[str, float]],
    score_fn: Callable[[Dict[str, float]], float],
    seeds: Sequence[int] = DEFAULT_SEEDS,
) -> List[Tuple[Dict[str, float], float, float]]:
    """Rank candidates by (mean_score + std_score) across seeds.

    Returns list of (candidate_overrides, mean_score, std_score) sorted
    by mean_score ascending (lower = better).
    """
    ranked: List[Tuple[Dict[str, float], float, float]] = []
    for c in candidates:
        def _one_seed(s: int, _c: Dict[str, float] = c) -> Dict[str, float]:
            m = eval_fn(_c, s)
            return {"_score": score_fn(m), **m}
        stats = validate_multiseed(_one_seed, seeds)
        score_stats = stats.get("_score", {"mean": float("inf"), "std": 0.0})
        ranked.append((c, score_stats["mean"], score_stats["std"]))
    ranked.sort(key=lambda r: (r[1] + r[2], r[1]))
    return ranked
