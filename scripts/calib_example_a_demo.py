"""Calibration framework demo: target the NetLogo outmigrant total.

Runs a 3-candidate sweep on example_a's `drift_conc` (tuning food supply),
scores each candidate against the parity test's outmigrant_total target,
saves runs to `data/calibration_history/`, and prints the ranking.

This is the smallest end-to-end example using:
  - FreeParameter declaration
  - apply_overrides + evaluate_candidate
  - ParityTarget + score_against_targets
  - save_run for history persistence
"""
from __future__ import annotations

from pathlib import Path
import datetime
import time

from salmopy.calibration import (
    FreeParameter,
    Transform,
    ParityTarget,
    evaluate_candidate,
    save_run,
)
from salmopy.calibration.losses import score_against_targets
from salmopy.state.life_stage import LifeStage

PROJECT = Path(__file__).resolve().parent.parent
CONFIGS = PROJECT / "configs"
FIXTURES = PROJECT / "tests" / "fixtures"


def example_a_metrics(model) -> dict:
    """Extract the parity-relevant metrics from a completed model."""
    outmigs = getattr(model, "_outmigrants", [])
    outmig_total = sum(o.get("superind_rep", 1) for o in outmigs)
    ts = model.trout_state
    alive = ts.alive_indices()
    juv_stages = {int(LifeStage.FRY), int(LifeStage.PARR)}
    juv_count = 0
    if len(alive) > 0:
        import numpy as np
        juv_count = int(
            np.isin(ts.life_history[alive], list(juv_stages)).sum()
        )
    return {"outmigrant_total": float(outmig_total), "juv_count": float(juv_count)}


def main() -> None:
    # Shorten the run for demo speed (default example_a is 2.5 years = 25 min)
    start = datetime.date(2011, 4, 1)
    end = (start + datetime.timedelta(days=450)).isoformat()

    # One free parameter: example_a reach drift_conc
    param = FreeParameter(
        "reaches.ExampleA.drift_conc", 1.6e-10, 6.4e-10, Transform.LOG
    )

    # Target: the v0.31.0 Arc F baseline (NetLogo outmigrant_total scaled for
    # the 450-day window — roughly half of the 2.5-year 41146 total).
    targets = [
        ParityTarget(
            metric="outmigrant_total",
            reference=18000.0,
            rtol=0.30,
            source="Arc F baseline, 450-day example_a",
        ),
    ]

    # Candidates: test 3 values of drift_conc
    candidates = [
        {"reaches.ExampleA.drift_conc": 1.6e-10},
        {"reaches.ExampleA.drift_conc": 3.2e-10},  # current default
        {"reaches.ExampleA.drift_conc": 6.4e-10},
    ]

    print("=== Calibration demo: drift_conc sweep on example_a (450 days) ===")
    ranked = []
    for i, overrides in enumerate(candidates, 1):
        v = overrides["reaches.ExampleA.drift_conc"]
        print(f"\n[{i}/{len(candidates)}] drift_conc={v:.2e} ...")
        t0 = time.perf_counter()
        metrics = evaluate_candidate(
            CONFIGS / "example_a.yaml",
            FIXTURES / "example_a",
            overrides,
            example_a_metrics,
            end_date_override=end,
        )
        wall = time.perf_counter() - t0
        score = score_against_targets(metrics, targets)
        print(
            f"  outmigrant_total={metrics['outmigrant_total']:.0f} "
            f"juv_count={metrics['juv_count']:.0f} "
            f"score={score:.4f} wall={wall:.1f}s"
        )
        save_run(
            overrides, metrics,
            algorithm="demo_sweep", seed=0, wall_time_s=wall,
            meta={"targets": [t.metric for t in targets]},
        )
        ranked.append((overrides, score, metrics))

    ranked.sort(key=lambda r: r[1])
    print("\n=== Ranked by score (lower=better) ===")
    for overrides, score, metrics in ranked:
        v = overrides["reaches.ExampleA.drift_conc"]
        print(
            f"  drift_conc={v:.2e}  score={score:.4f}  "
            f"outmig={metrics['outmigrant_total']:.0f}"
        )

    print("\nRuns persisted under data/calibration_history/")


if __name__ == "__main__":
    main()
