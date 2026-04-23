"""FreeParameter declarations and candidate evaluation driver.

Adapted from razinkele/osmopy's `calibration/problem.py`:
  - Same FreeParameter / Transform dataclass API
  - Replaces osmopy's Java subprocess runner with an in-process
    `SalmopyModel` call (no subprocess; Salmopy-py is pure Python).
  - apply_overrides() patches Pydantic species/reach configs by key path
    (e.g. "species.Chinook-Spring.cmax_A") before constructing the model.

Design: minimal, dataclass-only, no Pydantic. Upstream osmopy chose
dataclasses for its FreeParameter layer, so we match.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import math


class Transform(str, Enum):
    """Parameter-space transform between optimizer X and physical value."""
    LINEAR = "linear"
    LOG = "log"


@dataclass
class FreeParameter:
    """One free decision variable.

    Attributes
    ----------
    key : str
        Dot-delimited path into the loaded config. Examples:
          "species.Chinook-Spring.cmax_A"
          "reaches.ExampleA.drift_conc"
    lower, upper : float
        Bounds in physical (not transformed) space.
    transform : Transform
        If LOG, the optimizer searches log10(value); X is transformed
        back to the physical value via 10**X before applying.

    Example:
        FreeParameter("species.Chinook-Spring.cmax_A", 0.1, 2.0, Transform.LOG)
    """
    key: str
    lower: float
    upper: float
    transform: Transform = Transform.LINEAR

    def to_physical(self, x: float) -> float:
        """Convert an optimizer-space value x to physical value."""
        if self.transform is Transform.LOG:
            return 10.0 ** x
        return float(x)

    def to_optimizer(self, v: float) -> float:
        """Convert a physical value to optimizer-space (inverse of to_physical)."""
        if self.transform is Transform.LOG:
            if v <= 0.0:
                raise ValueError(f"cannot LOG-transform non-positive value {v}")
            return math.log10(v)
        return float(v)

    def bounds_optimizer(self) -> tuple[float, float]:
        """Bounds in optimizer space (log-space if LOG transform)."""
        return (self.to_optimizer(self.lower), self.to_optimizer(self.upper))


def apply_overrides(config: Any, overrides: Dict[str, float]) -> None:
    """Apply parameter overrides in-place to a loaded config object.

    Supports dot-delimited keys like:
      "species.Chinook-Spring.cmax_A"   (species dict by name)
      "reaches.ExampleA.drift_conc"     (reaches dict by name)
      "simulation.seed"                  (simulation attribute)

    Only keys that already resolve to a numeric attribute are allowed —
    no new fields are created. Raises KeyError if the key is invalid.
    """
    for key, value in overrides.items():
        parts = key.split(".")
        obj: Any = config
        for part in parts[:-1]:
            if isinstance(obj, dict):
                if part not in obj:
                    raise KeyError(
                        f"override key {key!r}: dict has no entry {part!r}"
                    )
                obj = obj[part]
            else:
                if not hasattr(obj, part):
                    raise KeyError(
                        f"override key {key!r}: object has no attribute {part!r}"
                    )
                obj = getattr(obj, part)
        last = parts[-1]
        if isinstance(obj, dict):
            if last not in obj:
                raise KeyError(
                    f"override key {key!r}: terminal dict has no entry {last!r}"
                )
            obj[last] = value
        else:
            if not hasattr(obj, last):
                raise KeyError(
                    f"override key {key!r}: terminal object has no attribute {last!r}"
                )
            setattr(obj, last, value)


def evaluate_candidate(
    config_path: Path,
    data_dir: Path,
    overrides: Dict[str, float],
    metric_fn: Callable[[Any], Dict[str, float]],
    end_date_override: Optional[str] = None,
    seed: Optional[int] = None,
) -> Dict[str, float]:
    """Run one InSTREAM-py simulation with parameter overrides, return metrics.

    Parameters
    ----------
    config_path : Path
        YAML config to load as baseline.
    data_dir : Path
        Fixture directory (adult arrivals, initial pop, shapefile, etc.).
    overrides : dict
        Key-path → physical value. Applied via apply_overrides() after
        config load, before model construction.
    metric_fn : callable
        Takes a completed `SalmopyModel` and returns a dict of named
        metrics (e.g. {"outmigrant_total": 20117, "juv_peak": 355}).
    end_date_override : str, optional
        YYYY-MM-DD shortening for faster calibration cycles.
    seed : int, optional
        Override the simulation seed for multi-seed robustness checks.

    Returns
    -------
    dict
        Metrics from metric_fn applied to the completed model.

    Notes
    -----
    This is the inner loop of every calibration algorithm — keep it cheap.
    Catches and re-raises exceptions; the caller decides whether to treat
    a failed candidate as +inf objective.
    """
    from salmopy.io.config import load_config
    from salmopy.model import SalmopyModel

    cfg = load_config(config_path)
    if seed is not None:
        if hasattr(cfg.simulation, "seed"):
            cfg.simulation.seed = int(seed)
    apply_overrides(cfg, overrides)
    model = SalmopyModel(
        cfg,
        data_dir=data_dir,
        end_date_override=end_date_override,
    )
    model.run()
    return metric_fn(model)
