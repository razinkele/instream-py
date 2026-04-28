"""v0.52.1/v0.52.2: replace Tornionjoki Lower/Middle/Upper depth +
velocity CSVs with realistic salmon-spawning-river values + per-cell
jitter to break suitability-score ties.

v0.52.1: depth values were Atmata copies 4-6 m, after m→cm conversion
became 500-700 cm. spawn_depth_table rejects > 204 cm so suitability=0
everywhere. Replaced with realistic 0.3-2.2 m base values.

v0.52.2: BUT all per-cell rows in the CSV were IDENTICAL — every Lower
cell had exactly the same depth + velocity, so every spawning female's
suitability score was identical and select_spawn_cell deterministically
picked the same cell (cell=425 in Middle). Each new redd then
superimposed on the existing pile via the legacy 50%-loss path
(spawn_defense_area=0). Result: 96.6% of eggs ended up in eggs_scour
(via the spawning.apply_superimposition path, NOT flow scour).

Fix: add ±10% per-cell jitter to depth + velocity profiles. This
breaks score ties so spawners distribute across cells, eliminating
superimposition mortality.

Per-flow base profiles:
- Lower:  0.50 → 2.20 m (per-cell jittered ±10%)
- Middle: 0.40 → 1.85 m (jittered)
- Upper:  0.30 → 1.55 m (jittered)
- Mouth:  unchanged (frac_spawn=0; salmon don't spawn here)

Velocity (from existing Atmata copy, per-flow profiles):
- Lower:  0.29 → 1.41 m/s (per-cell jittered ±10%)
- Middle: same base, jittered
- Upper:  same base, jittered

Same flow grid as before so TimeSeriesInputs.csv lookups still work.
Random jitter is seeded so output is deterministic across runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


# Per-reach (cell-uniform) BASE profiles. 10 entries matching the
# 0.8-350 flow grid. All values in METERS (the m→cm conversion happens
# in model_init.py:87).
DEPTH_BASE = {
    "Lower":  [0.50, 0.60, 0.72, 0.80, 0.92, 1.05, 1.18, 1.35, 1.65, 2.20],
    "Middle": [0.40, 0.48, 0.58, 0.65, 0.75, 0.85, 0.95, 1.10, 1.35, 1.85],
    "Upper":  [0.30, 0.36, 0.44, 0.50, 0.58, 0.66, 0.76, 0.90, 1.10, 1.55],
}

# Per-reach velocity BASE profiles (m/s). Inherited from the v0.45.0
# Atmata-copy values which are plausible for a Lapland salmon river.
VEL_BASE = {
    "Lower":  [0.29, 0.41, 0.54, 0.59, 0.66, 0.74, 0.82, 0.93, 1.12, 1.41],
    "Middle": [0.29, 0.41, 0.54, 0.59, 0.66, 0.74, 0.82, 0.93, 1.12, 1.41],
    "Upper":  [0.25, 0.35, 0.46, 0.50, 0.56, 0.63, 0.70, 0.79, 0.95, 1.20],
}

# v0.52.2: ±JITTER per-cell variation. Real river hydraulics vary at
# the 5-15% scale between adjacent cells (different cross-section,
# bed slope, vegetation). We use 10% to break suitability-score ties
# so spawners spread across cells instead of all picking the same one.
JITTER_FRAC = 0.10
RNG_SEED = 20260428  # deterministic across re-runs

# Flow grid matching the existing Lower-Depths.csv flow column header
# (preserved so TimeSeriesInputs.csv lookups continue to work).
LOWER_FLOWS = [0.8, 1.5, 3.0, 4.0, 6.0, 9.0, 14.0, 25.0, 70.0, 350.0]


def _per_cell_jittered(base: list[float], n_cells: int, rng: np.random.Generator) -> np.ndarray:
    """Return shape (n_cells, n_flows) with each cell ±jitter_frac of base.

    The jitter is per-cell uniform across all 10 flow values (a cell that
    is a bit deeper at low flow stays a bit deeper at high flow), so
    the per-cell character is consistent.
    """
    base_arr = np.array(base, dtype=np.float64)
    factors = rng.uniform(1.0 - JITTER_FRAC, 1.0 + JITTER_FRAC, size=n_cells)
    return base_arr[None, :] * factors[:, None]


def write_csv(
    path: Path, reach_name: str, kind: str, units: str,
    values: np.ndarray, base_range: tuple[float, float],
) -> None:
    """Write a hydraulic-table CSV with per-cell jittered values."""
    n_cells, n_flows = values.shape
    flow_str = ",".join(f"{f}" for f in LOWER_FLOWS)
    lines = [
        f"; {kind} for example_tornionjoki — {reach_name}",
        f"; v0.52.2: per-cell jittered ±{int(JITTER_FRAC*100)}% to break"
        " suitability-score ties (spawners spread across cells).",
        f"; CELL {kind.upper()} IN {units}",
        f"10,Number of flows in table,,,,,,,,,,,,,,,,,,",
        f",{flow_str}",
    ]
    for cell_idx in range(n_cells):
        row_str = ",".join(f"{v:.6f}" for v in values[cell_idx])
        lines.append(f"{cell_idx + 1},{row_str}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {path.name}: {n_cells} cells, "
          f"base {base_range[0]:.2f}-{base_range[1]:.2f} {units} "
          f"+ ±{int(JITTER_FRAC*100)}% per-cell jitter")


def main() -> int:
    fixture = ROOT / "tests/fixtures/example_tornionjoki"
    if not fixture.exists():
        print(f"missing {fixture}")
        return 1

    cell_counts = {"Lower": 1805, "Middle": 365, "Upper": 464}
    rng = np.random.default_rng(RNG_SEED)

    for reach, n_cells in cell_counts.items():
        d_base = DEPTH_BASE[reach]
        v_base = VEL_BASE[reach]
        d_vals = _per_cell_jittered(d_base, n_cells, rng)
        v_vals = _per_cell_jittered(v_base, n_cells, rng)
        write_csv(
            fixture / f"{reach}-Depths.csv", reach, "Depths", "METERS",
            d_vals, (d_base[0], d_base[-1]),
        )
        write_csv(
            fixture / f"{reach}-Vels.csv", reach, "Vels", "M/S",
            v_vals, (v_base[0], v_base[-1]),
        )

    print()
    print("Mouth-Depths.csv left unchanged (frac_spawn=0; salmon don't spawn there).")
    print("Mouth-Vels.csv left unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
