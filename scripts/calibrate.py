"""End-to-end calibration CLI for inSTREAM-py.

Ties together the calibration framework into one runnable script:

  1. Auto-discover FreeParameters via regex rules (YAML-configured).
  2. Preflight screen to flag negligible / flat / bound-tight params.
  3. Optional multi-phase scipy optimization on survivors.
  4. Multi-seed validation of the best candidate.
  5. Persist final result to data/calibration_history/.

Usage:
    micromamba run -n shiny python scripts/calibrate.py \\
        --config configs/example_a.yaml \\
        --data-dir tests/fixtures/example_a \\
        --end-date 2011-07-30 \\
        --targets targets.csv \\
        --skip-preflight   # optional: jump straight to optimization
        --preflight-only   # optional: stop after preflight screen

Rules and targets are loaded from simple formats:
  - rules.yaml:
        - pattern: "reaches.*.drift_conc"
          transform: LOG
          factor: 3.0
  - targets.csv (CSV columns: metric,reference,rtol,atol,lower,upper,weight,source)

A short end_date_override keeps eval cost low while iterating. Users
should rerun with the full simulation span for a final calibration.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

import numpy as np

from instream.calibration import (
    FreeParameter,
    Transform,
    DiscoveryRule,
    discover_parameters,
    preflight_screen,
    format_issues,
    IssueSeverity,
    CalibrationPhase,
    MultiPhaseCalibrator,
    ParityTarget,
    load_targets,
    validate_multiseed,
    save_run,
)
from instream.calibration.losses import score_against_targets
from instream.state.life_stage import LifeStage


def metrics_from_model(model: Any) -> Dict[str, float]:
    """Extract the canonical parity metrics from a finished model."""
    ts = model.trout_state
    alive = ts.alive_indices()
    juv_stages = [int(LifeStage.FRY), int(LifeStage.PARR)]
    outmigs = getattr(model, "_outmigrants", [])
    outmig_total = sum(o.get("superind_rep", 1) for o in outmigs)
    if len(alive) > 0:
        juv_mask = np.isin(ts.life_history[alive], juv_stages)
        juv_count = int(juv_mask.sum())
        juv_mean_len = float(ts.length[alive][juv_mask].mean()) if juv_count else 0.0
    else:
        juv_count = 0
        juv_mean_len = 0.0
    return {
        "outmigrant_total": float(outmig_total),
        "juv_count": float(juv_count),
        "juv_mean_length": juv_mean_len,
    }


def build_eval_fn(
    config_path: Path,
    data_dir: Path,
    end_date: str,
    targets: List[ParityTarget],
) -> Callable[[Dict[str, float]], float]:
    """Wrap evaluate_candidate + score_against_targets into a scalar loss."""
    from instream.calibration import evaluate_candidate

    def eval_fn(overrides: Dict[str, float]) -> float:
        try:
            metrics = evaluate_candidate(
                config_path=config_path,
                data_dir=data_dir,
                overrides=overrides,
                metric_fn=metrics_from_model,
                end_date_override=end_date,
            )
        except Exception as e:
            print(f"[eval error] {e}", file=sys.stderr)
            return float("inf")
        return score_against_targets(metrics, targets)

    return eval_fn


def load_rules_yaml(path: Path) -> List[DiscoveryRule]:
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    rules: List[DiscoveryRule] = []
    for r in data:
        transform = Transform.LOG if str(r.get("transform", "LINEAR")).upper() == "LOG" else Transform.LINEAR
        rules.append(
            DiscoveryRule(
                pattern=r["pattern"],
                transform=transform,
                factor=float(r.get("factor", 3.0)),
                min_lower=r.get("min_lower"),
                max_upper=r.get("max_upper"),
            )
        )
    return rules


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--config", required=True, type=Path)
    p.add_argument("--data-dir", required=True, type=Path)
    p.add_argument("--end-date", required=True, type=str,
                   help="YYYY-MM-DD — cap simulation length for fast iteration")
    p.add_argument("--rules", type=Path, default=None,
                   help="YAML file of DiscoveryRules (optional)")
    p.add_argument("--targets", required=True, type=Path,
                   help="CSV file of ParityTargets")
    p.add_argument("--skip-preflight", action="store_true")
    p.add_argument("--preflight-only", action="store_true")
    p.add_argument("--algorithm", default="nelder-mead",
                   choices=["nelder-mead", "differential-evolution"])
    p.add_argument("--max-iter", type=int, default=50)
    p.add_argument("--multiseed", type=int, default=3,
                   help="Number of seeds for final validation (0 to skip)")
    args = p.parse_args(argv)

    # 1. Load config + targets
    from instream.io.config import load_config

    cfg = load_config(args.config)
    targets = load_targets(args.targets)
    print(f"Loaded {len(targets)} target(s) from {args.targets}")

    # 2. Discover FreeParameters
    if args.rules:
        rules = load_rules_yaml(args.rules)
        params = discover_parameters(cfg, rules)
        print(f"Auto-discovered {len(params)} FreeParameter(s) from {args.rules}")
    else:
        print("No --rules given; using hand-coded demo param list")
        params = [
            FreeParameter("reaches.ExampleA.drift_conc", 1e-10, 1e-9, Transform.LOG),
        ]

    if not params:
        print("ERROR: zero FreeParameters after discovery.")
        return 1
    for fp in params:
        print(f"  • {fp.key:<40} [{fp.lower:.3g}, {fp.upper:.3g}] {fp.transform.value}")

    eval_fn = build_eval_fn(args.config, args.data_dir, args.end_date, targets)

    # 3. Preflight
    if not args.skip_preflight:
        print("\n=== Preflight screen ===")
        t0 = time.perf_counter()

        def screen_eval(X):
            Y = np.empty(len(X))
            for i, x in enumerate(X):
                overrides = {
                    p.key: p.to_physical(float(xi))
                    for p, xi in zip(params, x)
                }
                Y[i] = eval_fn(overrides)
            return Y.reshape(-1, 1)

        issues = preflight_screen(params, screen_eval, morris_trajectories=10, sobol_n_base=8)
        wall = time.perf_counter() - t0
        print(format_issues(issues))
        print(f"(preflight took {wall:.1f}s)")

        # Drop auto-fixable NEGLIGIBLE params
        to_drop = {i.param for i in issues if i.auto_fixable and i.param}
        if to_drop:
            kept = [p for p in params if p.key not in to_drop]
            print(f"Dropping {len(to_drop)} auto-fixable param(s): {to_drop}")
            params = kept
        errors = [i for i in issues if i.severity == IssueSeverity.ERROR]
        if errors:
            print("ERROR-severity issues present — aborting.")
            return 2

    if args.preflight_only:
        print("--preflight-only: stopping before optimization.")
        return 0

    # 4. Multi-phase optimization
    print("\n=== Optimization ===")
    t0 = time.perf_counter()
    phase = CalibrationPhase(
        name="main", free_params=list(params),
        algorithm=args.algorithm, max_iter=args.max_iter,
    )
    cal = MultiPhaseCalibrator([phase], eval_fn, verbose=True)
    results = cal.run()
    wall = time.perf_counter() - t0
    best = results[0]
    print(f"Best score: {best.best_score:.4f} ({best.n_evals} evals, {wall:.1f}s)")
    for k, v in best.best_overrides.items():
        print(f"  {k} = {v:.4g}")

    # 5. Multi-seed validation
    if args.multiseed > 0:
        print(f"\n=== Multi-seed validation ({args.multiseed} seeds) ===")
        from instream.calibration.problem import evaluate_candidate

        seeds = list(range(42, 42 + args.multiseed))

        def eval_with_seed(seed: int) -> Dict[str, float]:
            metrics = evaluate_candidate(
                args.config, args.data_dir, best.best_overrides,
                metrics_from_model,
                end_date_override=args.end_date, seed=seed,
            )
            return {**metrics, "_score": score_against_targets(metrics, targets)}

        stats = validate_multiseed(eval_with_seed, seeds=seeds)
        for m, s in sorted(stats.items()):
            print(
                f"  {m:<20} mean={s['mean']:.4g} std={s['std']:.3g} cv={s['cv']:.3f} "
                f"best={s['best']:.4g} worst={s['worst']:.4g}"
            )

    # 6. Persist
    path = save_run(
        best.best_overrides,
        {"final_score": best.best_score},
        algorithm=args.algorithm,
        wall_time_s=wall,
        meta={
            "n_evals": best.n_evals,
            "end_date_override": args.end_date,
            "n_params": len(params),
            "n_targets": len(targets),
        },
    )
    print(f"\nSaved: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
