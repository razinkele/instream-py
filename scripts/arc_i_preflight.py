"""Arc I: Morris preflight for juv_length parity gap.

Runs a minimal Morris sensitivity screen over 5 candidate parameters,
writes ranked mu_star + 95% CI to scripts/_arc_i_morris_result.csv.

Truncated to example_a 2011-04-01 → 2012-05-15 (410 days) to keep
per-eval cost at ~5 min. Morris with 4 trajectories × 6 = 24 evals
→ ~2 hours total.

Reports ranked influence on juv_mean_length at 2012-05-15.
"""
from __future__ import annotations

from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

from instream.calibration import (
    DiscoveryRule,
    Transform,
    discover_parameters,
    evaluate_candidate,
    MorrisAnalyzer,
)
from instream.calibration.configure import _walk  # for debug
from instream.state.life_stage import LifeStage


PROJECT = Path(__file__).resolve().parent.parent
CONFIGS = PROJECT / "configs"
FIXTURES = PROJECT / "tests" / "fixtures"


def juv_mean_length_at_end(model) -> dict:
    """Last valid juv_mean_length on or before end of run."""
    ts = model.trout_state
    alive = ts.alive_indices()
    juv_stages = [int(LifeStage.FRY), int(LifeStage.PARR)]
    if len(alive) > 0:
        juv_mask = np.isin(ts.life_history[alive], juv_stages) & (ts.species_idx[alive] == 0)
        if juv_mask.sum() > 0:
            return {"juv_mean_length": float(ts.length[alive][juv_mask].mean())}
    return {"juv_mean_length": 0.0}


def main() -> int:
    from instream.io.config import load_config
    import yaml

    # Load rules + discover params
    with open(PROJECT / "data" / "calibration" / "arc_i_rules.yaml") as f:
        rules_data = yaml.safe_load(f)
    rules = [
        DiscoveryRule(
            pattern=r["pattern"],
            transform=Transform[str(r.get("transform", "LINEAR")).upper()],
            factor=float(r.get("factor", 3.0)),
            min_lower=r.get("min_lower"),
            max_upper=r.get("max_upper"),
        )
        for r in rules_data
    ]
    cfg = load_config(CONFIGS / "example_a.yaml")
    params = discover_parameters(cfg, rules)
    print(f"Discovered {len(params)} params:")
    for p in params:
        print(f"  • {p.key:<50} [{p.lower:.3g}, {p.upper:.3g}]")

    if not params:
        print("ERROR: no params discovered.")
        return 1

    # Morris screen — small trajectory count for tractable runtime
    morris = MorrisAnalyzer(params, num_trajectories=4, num_levels=4, seed=42)
    X = morris.generate_samples()
    print(f"\nMorris matrix: {X.shape} ({X.shape[0]} model evaluations needed)")
    print(f"Estimated total: ~{X.shape[0] * 5} min at 5 min/eval\n")

    # Eval each sample
    Y = np.empty(X.shape[0], dtype=np.float64)
    t0 = time.perf_counter()
    end_date = "2012-05-15"
    target = 6.19
    for i, x in enumerate(X):
        overrides = {p.key: p.to_physical(float(xi)) for p, xi in zip(params, x)}
        t_i = time.perf_counter()
        try:
            metrics = evaluate_candidate(
                CONFIGS / "example_a.yaml",
                FIXTURES / "example_a",
                overrides,
                juv_mean_length_at_end,
                end_date_override=end_date,
            )
            juv = float(metrics["juv_mean_length"])
        except Exception as e:
            print(f"  [{i+1}/{len(X)}] FAILED: {e}")
            juv = 0.0
        # Objective: |juv - target|; we minimize, so Morris sees this as the
        # response surface to screen for influence.
        Y[i] = abs(juv - target)
        elapsed = time.perf_counter() - t0
        print(
            f"  [{i+1}/{len(X)}] juv={juv:.3f} err={Y[i]:.3f} "
            f"(cumulative {elapsed/60:.1f} min)"
        )

    # Morris analyze
    result = morris.analyze(X, Y)["obj_0"]
    mu_star = result["mu_star"]
    sigma = result["sigma"]
    conf = result["mu_star_conf"]

    df = pd.DataFrame({
        "param": [p.key for p in params],
        "mu_star": mu_star,
        "sigma": sigma,
        "mu_star_conf": conf,
    }).sort_values("mu_star", ascending=False)

    out_csv = PROJECT / "scripts" / "_arc_i_morris_result.csv"
    df.to_csv(out_csv, index=False)
    print(f"\n=== Morris ranking (written to {out_csv}) ===")
    print(df.to_string(index=False))

    print(f"\nTotal wall time: {(time.perf_counter() - t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
