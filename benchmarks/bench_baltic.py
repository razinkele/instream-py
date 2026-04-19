"""Headless Baltic case-study runner with per-step timing + lifecycle
counts by life stage.

Used to establish performance baselines after geometry changes (e.g. v0.30.1
switched to 9 reaches / 1,591 cells) and to quickly inspect whether a
given `example_baltic` fixture still produces a realistic lifecycle (fry
emerge, smolts exit, adults return).

Usage:
    micromamba run -n shiny python benchmarks/bench_baltic.py [days] [out.json]

`days` defaults to 14 (matches tests/e2e/test_baltic_e2e.py's
TestBalticSimulation window — fast enough for local runs). Longer windows
exercise more of the salmon lifecycle:

    14 days   — growth + early migration sanity
    90 days   — matches test_adult_arrives_as_returning_adult coverage
    210 days  — spawn (October) + winter egg development
    365 days  — full year: spawn + fry emergence in the next spring

The optional `out.json` path saves the full milestone table + timing +
first-appearance dict for later version-over-version comparison. See
benchmarks/baselines/ for baseline snapshots committed at each release.
"""
from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

from instream.model import InSTREAMModel  # noqa: E402
from instream.state.life_stage import LifeStage  # noqa: E402

CONFIG = str(PROJECT / "configs" / "example_baltic.yaml")
DATA_DIR = str(PROJECT / "tests" / "fixtures" / "example_baltic")

STAGE_NAMES = {int(s): s.name for s in LifeStage}


def _stage_histogram(model: InSTREAMModel) -> dict[str, int]:
    """Count living trout by life-history stage. Also includes live redds
    (as REDD) and total eggs across them (as EGGS) — these live in a
    separate state container from trout_state, so they'd otherwise be
    invisible to a stage-only dump."""
    ts = model.trout_state
    alive = ts.alive_indices()
    counts: Counter[int | str] = Counter()
    if len(alive) > 0:
        for s in ts.life_history[alive]:
            counts[int(s)] += 1
    # Redds + eggs (if the model has a redd_state — InSALMON does, older
    # configs might not).
    redd_state = getattr(model, "redd_state", None)
    if redd_state is not None and redd_state.num_alive() > 0:
        import numpy as np
        live = redd_state.alive
        counts["REDD"] = int(np.sum(live))
        counts["EGGS"] = int(np.sum(redd_state.num_eggs[live]))
    out: dict[str, int] = {}
    for k, n in counts.items():
        if isinstance(k, int):
            out[STAGE_NAMES.get(k, f"stage_{k}")] = n
        else:
            out[k] = n
    return out


def _format_stage_row(counts: dict[str, int]) -> str:
    if not counts:
        return "(no live fish)"
    return "  ".join(f"{name}={n}" for name, n in counts.items())


def _get_version() -> str:
    """Best-effort package version; falls back to 'unknown' if unreadable."""
    try:
        from instream import __version__  # type: ignore[import-not-found]
        return str(__version__)
    except Exception:
        return "unknown"


def main(days: int = 14, out_path: str | None = None) -> dict:
    print(f"Building InSTREAMModel from {CONFIG}")
    print(f"  data dir: {DATA_DIR}")
    t0 = time.perf_counter()
    model = InSTREAMModel(CONFIG, data_dir=DATA_DIR)
    t_build = time.perf_counter() - t0
    initial_alive = model.trout_state.num_alive()
    print(f"  model built in {t_build:.1f}s; "
          f"initial population: {initial_alive}")
    print(f"  initial stages: {_format_stage_row(_stage_histogram(model))}")
    print()

    print(f"Running {days} steps (1 step = 1 day)...")
    step_ms: list[float] = []
    milestones = [1, 7, 14, 30, 90, 180, 270, 365, 730, 1095]
    milestones = [m for m in milestones if m <= days]
    milestones_set = set(milestones)

    # First-appearance tracking per stage — shows when new cohorts emerge
    # (e.g. first SPAWNER at spawn season, first natal FRY ~6 months after
    # spawning). Invaluable for verifying the lifecycle pipeline end-to-end.
    first_seen: dict[str, int] = {}

    # Milestone snapshots — captured so we can serialize them to JSON
    # later for version-over-version comparison.
    milestone_rows: list[dict] = []

    t_run = time.perf_counter()
    for step in range(1, days + 1):
        t_step = time.perf_counter()
        model.step()
        step_ms.append((time.perf_counter() - t_step) * 1000.0)
        counts = _stage_histogram(model)
        for name in counts:
            if name not in first_seen:
                first_seen[name] = step
        if step in milestones_set:
            alive = model.trout_state.num_alive()
            print(f"  day {step:>4d}: alive={alive:>5d}  "
                  f"{_format_stage_row(counts)}")
            milestone_rows.append({
                "day": step,
                "alive": alive,
                "stages": dict(counts),
            })
    wall = time.perf_counter() - t_run

    print()
    print(f"Completed {days} steps in {wall:.1f}s "
          f"({wall / days:.2f}s/step, {days / (wall / 60 or 1e-9):.1f} days/min)")
    step_ms_stats = {
        "median": round(statistics.median(step_ms), 1),
        "min": round(min(step_ms), 1),
        "max": round(max(step_ms), 1),
    } if step_ms else {}
    if step_ms_stats:
        print(f"  step timing (ms):  "
              f"median={step_ms_stats['median']:.0f}  "
              f"min={step_ms_stats['min']:.0f}  "
              f"max={step_ms_stats['max']:.0f}")
    print()
    print("First-appearance day per stage (lifecycle milestones):")
    for name, day in sorted(first_seen.items(), key=lambda kv: kv[1]):
        print(f"  day {day:>4d}: {name}")
    print()
    final_hist = _stage_histogram(model)
    print("Final lifecycle histogram:")
    print(f"  {_format_stage_row(final_hist)}")

    report = {
        "inSTREAM_version": _get_version(),
        "host": platform.node(),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "config": str(Path(CONFIG).name),
        "days": days,
        "initial_population": initial_alive,
        "build_seconds": round(t_build, 2),
        "wall_seconds": round(wall, 2),
        "days_per_minute": round(days / (wall / 60 or 1e-9), 2),
        "step_ms": step_ms_stats,
        "milestones": milestone_rows,
        "first_seen_day": dict(sorted(first_seen.items(), key=lambda kv: kv[1])),
        "final_histogram": dict(final_hist),
    }
    if out_path is not None:
        out_p = Path(out_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(report, indent=2))
        print()
        print(f"Saved baseline JSON: {out_p}")
    return report


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    out = sys.argv[2] if len(sys.argv) > 2 else None
    main(days, out)
