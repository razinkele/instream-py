"""Read initial trout population CSV and build TroutState."""
from pathlib import Path
from typing import List, Dict, Any

import numpy as np


def read_initial_populations(path: Path) -> List[Dict[str, Any]]:
    """Read initial populations CSV. Returns list of dicts.

    Skips comment lines starting with ';'.
    Expects columns: Species, Reach, Age, Number, Length min, Length mode, Length max
    """
    populations = []
    with open(path, "r") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith(";"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 7:
                raise ValueError(
                    f"Population file {path}, line {lineno}: expected 7 "
                    f"comma-separated columns (Species, Reach, Age, Number, "
                    f"Length min/mode/max), got {len(parts)}: {line!r}"
                )
            populations.append({
                "species": parts[0],
                "reach": parts[1],
                "age": int(parts[2]),
                "number": int(parts[3]),
                "length_min": float(parts[4]),
                "length_mode": float(parts[5]),
                "length_max": float(parts[6]),
            })
    return populations


def random_triangular(
    low: float, mode: float, high: float, size: int, rng: np.random.Generator
) -> np.ndarray:
    """Generate triangular-distributed random values."""
    return rng.triangular(low, mode, high, size)


def build_initial_trout_state(
    populations: List[Dict[str, Any]],
    capacity: int,
    weight_A: float,
    weight_B: float,
    species_index: int,
    seed: int,
) -> "TroutState":
    """Build a TroutState from population specs.

    Parameters
    ----------
    populations : list of dicts from read_initial_populations
    capacity : max number of trout slots
    weight_A, weight_B : allometric weight parameters (W = A * L^B)
    species_index : integer species identifier
    seed : RNG seed for reproducibility
    """
    from salmopy.state.trout_state import TroutState

    total = sum(p["number"] for p in populations)
    if total > capacity:
        raise ValueError(
            f"Total fish ({total}) exceeds capacity ({capacity}). "
            f"Increase trout_capacity in config."
        )

    ts = TroutState.zeros(capacity)
    rng = np.random.default_rng(seed)
    idx = 0
    for pop in populations:
        n = pop["number"]
        lengths = random_triangular(
            pop["length_min"], pop["length_mode"], pop["length_max"], n, rng
        )
        weights = weight_A * lengths ** weight_B
        end = idx + n
        ts.alive[idx:end] = True
        ts.species_idx[idx:end] = species_index
        ts.age[idx:end] = pop["age"]
        ts.length[idx:end] = lengths
        ts.initial_length[idx:end] = lengths
        ts.weight[idx:end] = weights
        ts.condition[idx:end] = 1.0
        ts.superind_rep[idx:end] = 1
        ts.sex[idx:end] = rng.integers(0, 2, size=n, dtype=np.int32)
        idx = end
    return ts
