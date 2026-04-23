"""JSON run history persistence.

Adapted from osmopy's `calibration/history.py`. Each calibration run
gets one JSON file under a timestamped filename. File contains
overrides, metrics, seed, wall_time, and free-form metadata.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_HISTORY_DIR = Path("data/calibration_history")


def save_run(
    overrides: Dict[str, float],
    metrics: Dict[str, float],
    *,
    algorithm: str = "manual",
    seed: Optional[int] = None,
    wall_time_s: Optional[float] = None,
    meta: Optional[Dict[str, Any]] = None,
    history_dir: Path = DEFAULT_HISTORY_DIR,
) -> Path:
    """Save one run record to history_dir/<timestamp>_<algo>.json.

    Atomic write via tempfile + rename to avoid partial writes.
    """
    history_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_path = history_dir / f"{ts}_{algorithm}.json"

    record = {
        "timestamp": ts,
        "algorithm": algorithm,
        "seed": seed,
        "wall_time_s": wall_time_s,
        "overrides": overrides,
        "metrics": metrics,
        "meta": meta or {},
    }
    tmp_path = out_path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, default=str)
    os.replace(tmp_path, out_path)
    return out_path


def load_run(path: Path) -> Dict[str, Any]:
    """Load one run record from its JSON path."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_runs(history_dir: Path = DEFAULT_HISTORY_DIR) -> List[Path]:
    """List run JSON paths in history_dir, sorted by filename (timestamp)."""
    if not history_dir.exists():
        return []
    return sorted(history_dir.glob("*.json"))
