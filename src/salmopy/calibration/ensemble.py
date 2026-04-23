"""Replicate ensemble aggregation.

Adapted from osmopy's top-level `ensemble.py`. For any stochastic
Salmopy-py simulation, a single seed produces one noisy trajectory.
Running N replicates under different seeds and aggregating gives
non-parametric 2.5/97.5 percentile confidence bands that reflect the
model's inherent variability.

Two entry points:

  - `aggregate_trajectories(per_seed_dfs, time_col, value_cols)` —
    stack per-seed pandas DataFrames sharing a time column, compute
    percentile bands per (time, value_col).

  - `aggregate_scalars(per_seed_dicts)` — aggregate end-of-run scalar
    metrics (e.g. outmigrant_total per seed) into
    {metric: {mean, std, p025, p50, p975, n}}.

Both return pandas DataFrames suitable for plotting or saving to CSV.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def aggregate_scalars(
    per_seed: Sequence[Dict[str, float]],
    percentiles: Tuple[float, float] = (2.5, 97.5),
) -> pd.DataFrame:
    """Aggregate end-of-run scalar metrics across replicates.

    Parameters
    ----------
    per_seed : sequence of dicts
        Each dict is {metric_name: value} from one replicate.
    percentiles : (low, high) tuple
        Lower and upper percentiles for CI band (default 95% CI).

    Returns
    -------
    DataFrame with one row per metric and columns
        [mean, std, p_low, p_median, p_high, n]
    """
    if not per_seed:
        return pd.DataFrame(
            columns=["mean", "std", "p_low", "p_median", "p_high", "n"]
        )
    metric_names = sorted(set().union(*(r.keys() for r in per_seed)))
    p_low, p_high = percentiles
    rows = []
    for m in metric_names:
        vals = np.asarray(
            [r[m] for r in per_seed if m in r and np.isfinite(r[m])],
            dtype=np.float64,
        )
        if len(vals) == 0:
            rows.append({
                "metric": m, "mean": np.nan, "std": 0.0,
                "p_low": np.nan, "p_median": np.nan, "p_high": np.nan, "n": 0,
            })
            continue
        rows.append({
            "metric": m,
            "mean": float(vals.mean()),
            "std": float(vals.std(ddof=0)),
            "p_low": float(np.percentile(vals, p_low)),
            "p_median": float(np.percentile(vals, 50.0)),
            "p_high": float(np.percentile(vals, p_high)),
            "n": int(len(vals)),
        })
    df = pd.DataFrame(rows).set_index("metric")
    return df


def aggregate_trajectories(
    per_seed: Sequence[pd.DataFrame],
    time_col: str = "date",
    value_cols: Optional[Sequence[str]] = None,
    percentiles: Tuple[float, float] = (2.5, 97.5),
) -> pd.DataFrame:
    """Aggregate per-seed time series into a single percentile-banded table.

    Parameters
    ----------
    per_seed : sequence of DataFrames
        Each DataFrame has `time_col` + value columns (shared schema).
    time_col : str
        Name of the time index column (default 'date').
    value_cols : list of str, optional
        Which value columns to aggregate. Default: all non-time columns
        in the first DataFrame.
    percentiles : (low, high) tuple
        Default (2.5, 97.5) = 95% non-parametric CI.

    Returns
    -------
    DataFrame with `time_col` as index and MultiIndex columns
        [(value_col, stat), ...] where stat ∈ {mean, p_low, p_median, p_high}.
    """
    if not per_seed:
        return pd.DataFrame()
    # Determine value columns from first DataFrame if not provided
    if value_cols is None:
        value_cols = [c for c in per_seed[0].columns if c != time_col]

    # Align on the intersection of time indices (replicates should have
    # the same time grid, but crashes may truncate some)
    time_sets = [set(df[time_col].tolist()) for df in per_seed]
    common_times = sorted(set.intersection(*time_sets))
    p_low, p_high = percentiles

    out: Dict[Tuple[str, str], List[float]] = {}
    for col in value_cols:
        out[(col, "mean")] = []
        out[(col, "p_low")] = []
        out[(col, "p_median")] = []
        out[(col, "p_high")] = []

    # For each common time, collect across replicates
    for t in common_times:
        for col in value_cols:
            vals = []
            for df in per_seed:
                row = df[df[time_col] == t]
                if not row.empty:
                    v = float(row.iloc[0][col])
                    if np.isfinite(v):
                        vals.append(v)
            if vals:
                arr = np.asarray(vals, dtype=np.float64)
                out[(col, "mean")].append(float(arr.mean()))
                out[(col, "p_low")].append(float(np.percentile(arr, p_low)))
                out[(col, "p_median")].append(float(np.percentile(arr, 50.0)))
                out[(col, "p_high")].append(float(np.percentile(arr, p_high)))
            else:
                for stat in ("mean", "p_low", "p_median", "p_high"):
                    out[(col, stat)].append(np.nan)

    df_out = pd.DataFrame(out, index=pd.Index(common_times, name=time_col))
    return df_out


def run_replicates(
    eval_fn,
    seeds: Sequence[int],
    return_trajectories: bool = False,
) -> List:
    """Execute eval_fn(seed) for each seed sequentially.

    Convenience wrapper; for parallel execution use
    concurrent.futures.ProcessPoolExecutor directly.

    Parameters
    ----------
    eval_fn : callable(seed) -> dict or DataFrame
    seeds : sequence of ints
    return_trajectories : bool
        If True, return raw per-seed outputs. If False, the caller
        must aggregate them with aggregate_scalars / aggregate_trajectories.

    Returns
    -------
    list of eval_fn(seed) outputs in seed order.
    """
    return [eval_fn(s) for s in seeds]
