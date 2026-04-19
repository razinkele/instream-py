"""Diff two bench_baltic JSON baselines side-by-side.

Usage:
    python benchmarks/compare_baseline.py old.json new.json

Prints a table of milestone-day populations plus key deltas: build time,
throughput, final histogram, first-appearance shifts. Useful for spotting
calibration drift between releases (e.g. "did v0.30.3 change when natal
FRY appear?") and performance regressions (e.g. "did the days/min number
drop?").
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _fmt_stages(stages: dict) -> str:
    return "  ".join(f"{k}={v}" for k, v in stages.items())


def main(old_path: str, new_path: str) -> None:
    old = _load(old_path)
    new = _load(new_path)

    print(f"OLD: {old.get('inSTREAM_version')}  ({Path(old_path).name})")
    print(f"NEW: {new.get('inSTREAM_version')}  ({Path(new_path).name})")
    print()

    # Performance
    print("=== Performance ===")
    print(f"  build_seconds:    {old['build_seconds']}s → {new['build_seconds']}s")
    print(f"  days/min:         {old['days_per_minute']}  → {new['days_per_minute']}")
    if old.get("step_ms") and new.get("step_ms"):
        print(f"  step_ms median:   {old['step_ms']['median']}  → {new['step_ms']['median']}")
    print()

    # First-appearance shifts
    print("=== Lifecycle milestones (first appearance, day) ===")
    all_stages = sorted(set(old["first_seen_day"]) | set(new["first_seen_day"]))
    for stage in all_stages:
        a = old["first_seen_day"].get(stage, "—")
        b = new["first_seen_day"].get(stage, "—")
        flag = " ⚠" if a != b and isinstance(a, int) and isinstance(b, int) else ""
        print(f"  {stage:<18} {str(a):>6} → {str(b):<6}{flag}")
    print()

    # Milestone-day populations
    print("=== Milestone populations ===")
    days_a = {m["day"]: m for m in old["milestones"]}
    days_b = {m["day"]: m for m in new["milestones"]}
    all_days = sorted(set(days_a) | set(days_b))
    for d in all_days:
        ma = days_a.get(d)
        mb = days_b.get(d)
        alive_a = ma["alive"] if ma else "—"
        alive_b = mb["alive"] if mb else "—"
        print(f"  day {d:>4d}  alive {str(alive_a):>6}  →  {str(alive_b):<6}")
        if ma:
            print(f"            OLD  {_fmt_stages(ma['stages'])}")
        if mb:
            print(f"            NEW  {_fmt_stages(mb['stages'])}")
    print()

    # Final histogram
    print("=== Final histogram ===")
    print(f"  OLD  {_fmt_stages(old['final_histogram'])}")
    print(f"  NEW  {_fmt_stages(new['final_histogram'])}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: compare_baseline.py old.json new.json", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
