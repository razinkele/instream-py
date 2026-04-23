"""Arc I follow-up: Nelder-Mead optimization on top-ranked Morris params.

Reads scripts/_arc_i_morris_result.csv (from arc_i_preflight.py), picks
the top N params by mu_star, and runs a Nelder-Mead calibration against
the juv_length target.

Usage:
    # Default: top 2 params, 40 iterations, 410-day sim
    micromamba run -n shiny python scripts/arc_i_optimize.py

    # Top-3 params, longer budget
    micromamba run -n shiny python scripts/arc_i_optimize.py --top 3 --max-iter 80
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from salmopy.calibration import (
    DiscoveryRule,
    Transform,
    discover_parameters,
    evaluate_candidate,
    CalibrationPhase,
    MultiPhaseCalibrator,
    ParityTarget,
    load_targets,
    save_run,
    validate_multiseed,
)
from salmopy.calibration.losses import score_against_targets
from salmopy.state.life_stage import LifeStage


PROJECT = Path(__file__).resolve().parent.parent
CONFIGS = PROJECT / "configs"
FIXTURES = PROJECT / "tests" / "fixtures"


def juv_mean_length_at_end(model) -> dict:
    ts = model.trout_state
    alive = ts.alive_indices()
    juv_stages = [int(LifeStage.FRY), int(LifeStage.PARR)]
    if len(alive) > 0:
        mask = np.isin(ts.life_history[alive], juv_stages) & (ts.species_idx[alive] == 0)
        if mask.sum() > 0:
            return {"juv_mean_length": float(ts.length[alive][mask].mean())}
    return {"juv_mean_length": 0.0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--top", type=int, default=2,
                        help="Number of top-ranked params to optimize")
    parser.add_argument("--max-iter", type=int, default=40)
    parser.add_argument("--end-date", default="2012-05-15")
    parser.add_argument("--multiseed", type=int, default=3)
    args = parser.parse_args()

    # Load Morris result
    morris_path = PROJECT / "scripts" / "_arc_i_morris_result.csv"
    if not morris_path.exists():
        print(f"ERROR: {morris_path} not found. Run arc_i_preflight.py first.")
        return 1
    morris = pd.read_csv(morris_path)
    print(f"Loaded Morris ranking from {morris_path}")
    print(morris.to_string(index=False))

    # Pick top N params
    top_params = morris.head(args.top)["param"].tolist()
    print(f"\nOptimizing top-{args.top} params: {top_params}")

    # Rebuild FreeParameter list from the rules file (for bounds)
    from salmopy.io.config import load_config

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
    all_params = discover_parameters(cfg, rules)
    params_to_opt = [p for p in all_params if p.key in top_params]

    # Load target
    targets = load_targets(PROJECT / "data" / "calibration" / "arc_i_targets.csv")
    print(f"Loaded {len(targets)} target(s)")

    # Build eval_fn
    def eval_fn(overrides):
        try:
            metrics = evaluate_candidate(
                CONFIGS / "example_a.yaml",
                FIXTURES / "example_a",
                overrides,
                juv_mean_length_at_end,
                end_date_override=args.end_date,
            )
        except Exception as e:
            print(f"  eval error: {e}", file=sys.stderr)
            return float("inf")
        return score_against_targets(metrics, targets)

    # Nelder-Mead
    print(f"\n=== Nelder-Mead optimization ({args.max_iter} max iter) ===")
    phase = CalibrationPhase(
        name="juv_length_nm",
        free_params=params_to_opt,
        algorithm="nelder-mead",
        max_iter=args.max_iter,
    )
    cal = MultiPhaseCalibrator([phase], eval_fn, verbose=True)
    t0 = time.perf_counter()
    result = cal.run()[0]
    wall = time.perf_counter() - t0
    print(
        f"\nBest score: {result.best_score:.4f} "
        f"({result.n_evals} evals, {wall/60:.1f} min)"
    )
    for k, v in result.best_overrides.items():
        print(f"  {k} = {v:.4g}")

    # Multi-seed validation
    if args.multiseed > 0:
        print(f"\n=== Multi-seed validation ({args.multiseed} seeds) ===")
        seeds = list(range(42, 42 + args.multiseed))

        def eval_seed(s):
            m = evaluate_candidate(
                CONFIGS / "example_a.yaml",
                FIXTURES / "example_a",
                result.best_overrides,
                juv_mean_length_at_end,
                end_date_override=args.end_date,
                seed=s,
            )
            return {**m, "_score": score_against_targets(m, targets)}

        stats = validate_multiseed(eval_seed, seeds=seeds)
        for m, s in sorted(stats.items()):
            print(
                f"  {m:<25} mean={s['mean']:.4g} std={s['std']:.3g} "
                f"cv={s['cv']:.3f}"
            )

    # Persist
    path = save_run(
        result.best_overrides,
        {"final_score": result.best_score},
        algorithm="nelder-mead",
        wall_time_s=wall,
        meta={
            "arc": "I",
            "n_params_optimized": len(params_to_opt),
            "end_date_override": args.end_date,
            "n_evals": result.n_evals,
        },
    )
    print(f"\nSaved: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
