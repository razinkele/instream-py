"""Inspect what the depth-table interpolation actually produces.

Compares CSV raw values against cs.depth after a single step. If they
diverge, there's a unit conversion happening — find it.
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from salmopy.model import SalmopyModel  # noqa: E402
from salmopy.io.hydraulics_reader import read_depth_table  # noqa: E402

# Read raw CSV
flows, values = read_depth_table(
    ROOT / "tests/fixtures/example_tornionjoki/Lower-Depths.csv"
)
print(f"Lower-Depths.csv:")
print(f"  flows ({len(flows)}): {flows}")
print(f"  values shape: {values.shape}")
print(f"  values[0]: {values[0]}")
print(f"  values min/max: {values.min():.4f} / {values.max():.4f}")

# Load model and step once
model = SalmopyModel(
    config_path=str(ROOT / "configs/example_tornionjoki.yaml"),
    data_dir=str(ROOT / "tests/fixtures/example_tornionjoki"),
    end_date_override="2011-04-03",
)
model.step()

cs = model.fem_space.cell_state
print(f"\nAfter step 1 (date={model.time_manager.current_date}):")

# Find Lower cells
r_idx = model.reach_order.index("Lower")
lower_cells = np.where(cs.reach_idx == r_idx)[0]
sample = lower_cells[:5]
print(f"  Lower reach has {len(lower_cells)} cells. Sample first 5:")
for c in sample:
    print(f"    cell {c}: cs.depth = {cs.depth[c]} (raw value)")

# What flow is in reach_state?
rs = model.reach_state
print(f"\n  reach_state.flow shape: {rs.flow.shape}")
print(f"  reach_state.flow[Lower (idx={r_idx})] = {rs.flow[r_idx]}")
print(f"  reach_state.temperature[Lower] = {rs.temperature[r_idx]}")

# Manually interp depth at this flow for cell 0 of CSV
csv_idx = 0
expected_depth = float(np.interp(rs.flow[r_idx], flows, values[csv_idx]))
print(f"\n  Manual interp(flow={rs.flow[r_idx]}, values[{csv_idx}]={values[csv_idx]}) = {expected_depth}")

# Print depth_table_values stored in cell_state
if hasattr(cs, "depth_table_values"):
    print(f"  cs.depth_table_values shape: {cs.depth_table_values.shape}")
    print(f"  cs.depth_table_values[lower_cells[0]={lower_cells[0]}]: {cs.depth_table_values[lower_cells[0]]}")
    print(f"  cs.depth_table_flows: {cs.depth_table_flows}")
