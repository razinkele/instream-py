"""v0.44 probe: quantify the calibration-impact of the v0.29.0 batch-kernel
vs. scalar-fallback divergence found by tests/test_batch_select_habitat_parity.py
in v0.43.17.

Runs the example_a fixture twice with identical seed — once on the default
batch path, once with _HAS_NUMBA_BATCH=False forced — for N days, then
compares population-level outputs that drive calibration: alive count,
length distribution, outmigrant count, cell-occupancy entropy.

If the metrics agree within ~5%, the batch-path over-concentration
(observed at single-step resolution) self-corrects over multi-day
dynamics — Option C (hybrid config flag) is viable.

If they diverge materially, Arc E-I calibration work done on the batch
path is biased — Option A (revert to scalar) is needed.

Usage:
    micromamba run -n shiny python scripts/_probe_v044_batch_scalar_bias.py --days 30
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def run_path(force_scalar: bool, days: int, seed: int,
             config_path: str, data_dir: str, verbose: bool = False):
    """Run the given fixture for `days` with the given dispatch. Returns metrics dict."""
    from salmopy.model import SalmopyModel
    from salmopy.modules import behavior

    original_flag = behavior._HAS_NUMBA_BATCH
    if force_scalar:
        behavior._HAS_NUMBA_BATCH = False

    try:
        t0 = time.time()
        model = SalmopyModel(
            config_path=config_path,
            data_dir=data_dir,
        )
        model.rng = np.random.default_rng(seed)

        for d in range(days):
            model.step()
            if verbose and d % 10 == 0:
                n_alive = int(model.trout_state.alive.sum())
                print(f"  day {d+1:3d}: alive={n_alive}")

        elapsed = time.time() - t0
    finally:
        behavior._HAS_NUMBA_BATCH = original_flag

    alive = model.trout_state.alive
    n_alive = int(alive.sum())
    if n_alive == 0:
        return {
            "path": "scalar" if force_scalar else "batch",
            "elapsed_s": elapsed,
            "n_alive": 0,
            "length_mean": float("nan"),
            "length_std": float("nan"),
            "cell_entropy": float("nan"),
            "n_unique_cells": 0,
            "n_outmigrants": 0,
        }

    lengths = model.trout_state.length[alive]
    cells = model.trout_state.cell_idx[alive]

    # Cell-occupancy entropy: Shannon entropy of cell-count distribution.
    # Higher entropy = more dispersed; lower = over-concentrated.
    unique, counts = np.unique(cells, return_counts=True)
    probs = counts / counts.sum()
    entropy = -(probs * np.log2(probs + 1e-30)).sum()

    # Outmigrants: consult model.outmigrants list if present, else proxy 0.
    n_outmig = len(getattr(model, "outmigrants", []))

    return {
        "path": "scalar" if force_scalar else "batch",
        "elapsed_s": elapsed,
        "n_alive": n_alive,
        "length_mean": float(lengths.mean()),
        "length_std": float(lengths.std()),
        "cell_entropy": float(entropy),
        "n_unique_cells": int(len(unique)),
        "n_outmigrants": n_outmig,
    }


def fmt(x):
    if isinstance(x, float):
        if math.isnan(x):
            return "NaN"
        return f"{x:.3f}"
    return str(x)


def rel_diff(a, b):
    if a == 0 and b == 0:
        return 0.0
    if a == 0 or b == 0:
        return float("inf")
    return abs(a - b) / max(abs(a), abs(b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fixture", default="example_a",
                    help="example_a (small Chinook) or example_baltic (multi-reach salmon)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    config_path = f"configs/{args.fixture}.yaml"
    data_dir = f"tests/fixtures/{args.fixture}"

    print(f"v0.44 batch-vs-scalar calibration-bias probe")
    print(f"  fixture: {args.fixture} | days: {args.days} | seed: {args.seed}")
    print()

    print("Running batch path (default)...")
    batch = run_path(force_scalar=False, days=args.days, seed=args.seed,
                     config_path=config_path, data_dir=data_dir, verbose=args.verbose)

    print("Running scalar path (_HAS_NUMBA_BATCH=False)...")
    scalar = run_path(force_scalar=True, days=args.days, seed=args.seed,
                      config_path=config_path, data_dir=data_dir, verbose=args.verbose)

    print()
    print(f"{'metric':<25} {'batch':>15} {'scalar':>15} {'rel_diff':>10}")
    print("-" * 68)
    for key in ("elapsed_s", "n_alive", "length_mean", "length_std",
                "cell_entropy", "n_unique_cells", "n_outmigrants"):
        b = batch[key]
        s = scalar[key]
        d = rel_diff(b, s) if isinstance(b, (int, float)) and isinstance(s, (int, float)) else "—"
        d_str = f"{d*100:.1f}%" if isinstance(d, float) and not math.isinf(d) else str(d)
        print(f"{key:<25} {fmt(b):>15} {fmt(s):>15} {d_str:>10}")

    print()
    print("Verdict thresholds:")
    print("  < 5% rel_diff on n_alive, length_mean, n_outmigrants -> Option C viable")
    print("  > 10% rel_diff on any of the above -> Option A (revert) needed")
    print("  5-10% -> case-by-case judgment; probably need longer run")


if __name__ == "__main__":
    main()
