"""Headless Baltic case-study runner with per-step timing + lifecycle
counts by life stage.

Used to establish performance baselines after geometry changes (e.g. v0.30.1
switched to 9 reaches / 1,591 cells) and to quickly inspect whether a
given `example_baltic` fixture still produces a realistic lifecycle (fry
emerge, smolts exit, adults return).

Usage:
    micromamba run -n shiny python benchmarks/bench_baltic.py [days]

`days` defaults to 14 (matches tests/e2e/test_baltic_e2e.py's
TestBalticSimulation window — fast enough for local runs). Longer windows
exercise more of the salmon lifecycle:

    14 days   — growth + early migration sanity
    90 days   — matches test_adult_arrives_as_returning_adult coverage
    210 days  — spawn (October) + winter egg development
    365 days  — full year: spawn + fry emergence in the next spring
"""
from __future__ import annotations

import statistics
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

from instream.model import InSTREAMModel  # noqa: E402
from instream.state.life_stage import LifeStage  # noqa: E402

CONFIG = str(PROJECT / "configs" / "example_baltic.yaml")
DATA_DIR = str(PROJECT / "tests" / "fixtures" / "example_baltic")

STAGE_NAMES = {int(s): s.name for s in LifeStage}


def _stage_histogram(model: InSTREAMModel) -> dict[str, int]:
    """Count living trout by life-history stage."""
    ts = model.trout_state
    alive = ts.alive_indices()
    if len(alive) == 0:
        return {}
    stages = ts.life_history[alive]
    counts = Counter(int(s) for s in stages)
    return {STAGE_NAMES.get(s, f"stage_{s}"): n for s, n in sorted(counts.items())}


def _format_stage_row(counts: dict[str, int]) -> str:
    if not counts:
        return "(no live fish)"
    return "  ".join(f"{name}={n}" for name, n in counts.items())


def main(days: int = 14) -> None:
    print(f"Building InSTREAMModel from {CONFIG}")
    print(f"  data dir: {DATA_DIR}")
    t0 = time.perf_counter()
    model = InSTREAMModel(CONFIG, data_dir=DATA_DIR)
    t_build = time.perf_counter() - t0
    print(f"  model built in {t_build:.1f}s; "
          f"initial population: {model.trout_state.num_alive()}")
    print(f"  initial stages: {_format_stage_row(_stage_histogram(model))}")
    print()

    print(f"Running {days} steps (1 step = 1 day)...")
    step_ms: list[float] = []
    milestones = [1, 7, 14, 30, 90, 180, 270, 365, 730, 1095]
    milestones = [m for m in milestones if m <= days]
    milestones_set = set(milestones)

    t_run = time.perf_counter()
    for step in range(1, days + 1):
        t_step = time.perf_counter()
        model.step()
        step_ms.append((time.perf_counter() - t_step) * 1000.0)
        if step in milestones_set:
            alive = model.trout_state.num_alive()
            counts = _stage_histogram(model)
            print(f"  day {step:>4d}: alive={alive:>5d}  "
                  f"{_format_stage_row(counts)}")
    wall = time.perf_counter() - t_run

    print()
    print(f"Completed {days} steps in {wall:.1f}s "
          f"({wall / days:.2f}s/step, {days / (wall / 60 or 1e-9):.1f} days/min)")
    if step_ms:
        print(f"  step timing (ms):  "
              f"median={statistics.median(step_ms):.0f}  "
              f"min={min(step_ms):.0f}  "
              f"max={max(step_ms):.0f}")
    print()
    print("Final lifecycle histogram:")
    print(f"  {_format_stage_row(_stage_histogram(model))}")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    main(days)
