"""v0.52.1: replace Tornionjoki Lower/Middle/Upper depth CSVs with
realistic salmon-spawning-river values.

The current CSVs are copies of example_baltic Atmata-Depths.csv with
values 4.2-6.6 m. After the model's m→cm conversion (model_init.py:87),
these become 420-660 cm cell depths. The species spawn_depth_table
rejects any depth > 204 cm (2.04 m), so suitability=0 across every
reach. No fish can spawn — root cause of init_cum=0 in the v0.52.0
B5 probe.

Real Tornionjoki spawning habitat is 30-100 cm deep at typical flow.
This script writes realistic per-flow depth tables:

- Lower (1805 cells):  base ~80 cm at flow=8 m³/s, scaling 50-150 cm
- Middle (365 cells):  base ~70 cm
- Upper (464 cells):   base ~50 cm
- Mouth (566 cells):   keeps current ~5 m (river-mouth + Bothnian Bay
                       transition; salmon don't spawn here per
                       frac_spawn=0)

Same flow grid as before so existing TimeSeriesInputs.csv lookups still
work. Per-cell values uniform within each reach (the v0.45.0 template
already did this — preserves the only-currently-shipped variation).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# Realistic spawning-river depth profiles (m). Index = flow in m³/s.
# Tornionjoki at gauging stations:
#   - Lower (Pello): mean 200-400 m³/s, depth 1-2 m
#   - Middle (Tornio): mean ~200 m³/s, depth 0.8-1.5 m
#   - Upper (Kaaresuvanto): mean ~100 m³/s, depth 0.5-1.0 m
# But the model uses synthetic flow units; calibration of the flow scale
# is out of scope. Just give shallow values that match the synthetic flow.

# Per-reach (cell-uniform) depths: 10 entries matching the 0.8-350 flow grid.
# All values in METERS (the m→cm conversion happens in model_init.py).
DEPTH_TABLES = {
    "Lower":  [0.50, 0.60, 0.72, 0.80, 0.92, 1.05, 1.18, 1.35, 1.65, 2.20],
    "Middle": [0.40, 0.48, 0.58, 0.65, 0.75, 0.85, 0.95, 1.10, 1.35, 1.85],
    "Upper":  [0.30, 0.36, 0.44, 0.50, 0.58, 0.66, 0.76, 0.90, 1.10, 1.55],
}

# Flow grid matching the existing Lower-Depths.csv flow column header
# (preserved so TimeSeriesInputs.csv lookups continue to work). The
# existing Mouth-Depths.csv has the Nemunas flow grid [1, 2, 4, ...] which
# we keep separately.
LOWER_FLOWS = [0.8, 1.5, 3.0, 4.0, 6.0, 9.0, 14.0, 25.0, 70.0, 350.0]


def write_depth_csv(path: Path, reach_name: str, n_cells: int, depths: list[float]) -> None:
    flow_str = ",".join(f"{f}" for f in LOWER_FLOWS)
    depth_str = ",".join(f"{d:.6f}" for d in depths)
    lines = [
        f"; Depths for example_tornionjoki — {reach_name}",
        "; v0.52.1: replaced Atmata-copy values (4.2-6.6 m) with realistic",
        ";   shallow-river spawning-habitat depths (0.3-2.2 m).",
        "; CELL DEPTHS IN METERS",
        "10,Number of flows in table,,,,,,,,,,,,,,,,,,",
        f",{flow_str}",
    ]
    for cell_idx in range(1, n_cells + 1):
        lines.append(f"{cell_idx},{depth_str}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {path.name}: {n_cells} cells, depth range "
          f"{depths[0]:.2f}-{depths[-1]:.2f} m")


def main() -> int:
    fixture = ROOT / "tests/fixtures/example_tornionjoki"
    if not fixture.exists():
        print(f"missing {fixture}")
        return 1

    # Cell counts must match the existing shapefile to keep CSV-row count
    # in sync. These values are observed from the v0.51.6 fixture.
    cell_counts = {
        "Lower": 1805,
        "Middle": 365,
        "Upper": 464,
    }

    for reach, n_cells in cell_counts.items():
        depths = DEPTH_TABLES[reach]
        out_path = fixture / f"{reach}-Depths.csv"
        write_depth_csv(out_path, reach, n_cells, depths)

    print()
    print("Mouth-Depths.csv left unchanged (frac_spawn=0; salmon don't spawn there).")
    print("Velocity files left unchanged (existing values 50-90 cm/s match real river velocities).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
