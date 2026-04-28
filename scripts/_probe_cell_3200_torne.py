"""Inspect Tornionjoki cell 3200 — which reach is it in, and is the
reach_cells map correctly populated?"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from salmopy.model import SalmopyModel

model = SalmopyModel(
    config_path=str(ROOT / "configs/example_tornionjoki.yaml"),
    data_dir=str(ROOT / "tests/fixtures/example_tornionjoki"),
    end_date_override="2011-04-02",
)

print("model.reach_order:", model.reach_order)
print()
print("Cell 3200:")
cs = model.fem_space.cell_state
print(f"  reach_idx (per-cell): {cs.reach_idx[3200] if hasattr(cs, 'reach_idx') else 'N/A'}")
print(f"  area: {cs.area[3200]}")
print(f"  frac_spawn: {cs.frac_spawn[3200]}")

# Also dump the reach_cells map
print("\n_reach_cells map (reach_idx → first 5 cells, total count):")
rc = getattr(model, "_reach_cells", None)
if rc is None:
    print("  (model._reach_cells not present)")
else:
    for r_idx, cells in sorted(rc.items()):
        rname = model.reach_order[r_idx] if 0 <= r_idx < len(model.reach_order) else "INVALID"
        cells_list = list(cells) if cells is not None else []
        head = cells_list[:5]
        print(f"  reach_idx={r_idx} ({rname}): {len(cells_list)} cells, first 5 = {head}")
