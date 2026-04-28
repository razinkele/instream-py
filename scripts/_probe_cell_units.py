"""Quick: inspect cs.depth / cs.velocity / cs.area / cs.frac_spawn at
spawn-window flow conditions. Cheap (<1 min). Tells us whether spawn
table units (cm) match cs.depth/velocity units."""
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from salmopy.model import SalmopyModel  # noqa: E402

# Use a 2-day end_date so the model loads + steps once but doesn't run long
model = SalmopyModel(
    config_path=str(ROOT / "configs/example_tornionjoki.yaml"),
    data_dir=str(ROOT / "tests/fixtures/example_tornionjoki"),
    end_date_override="2011-04-03",
)
# Step once to populate cell_state from initial flow
model.step()

cs = model.fem_space.cell_state
sp_cfg = model.config.species["BalticAtlanticSalmon"]

print(f"cs.depth dtype: {cs.depth.dtype}, n_cells: {len(cs.depth)}")
print(f"cs.velocity dtype: {cs.velocity.dtype}")
print(f"cs.area dtype: {cs.area.dtype}")
print()

# Stats per reach
for reach_name in ["Mouth", "Lower", "Middle", "Upper", "BalticCoast"]:
    if reach_name not in model.reach_order:
        continue
    r_idx = model.reach_order.index(reach_name)
    reach_mask = cs.reach_idx == r_idx
    if not reach_mask.any():
        continue
    d = cs.depth[reach_mask]
    v = cs.velocity[reach_mask]
    a = cs.area[reach_mask]
    f = cs.frac_spawn[reach_mask]
    print(f"{reach_name} ({reach_mask.sum()} cells):")
    print(f"  depth:      min={d.min():.4f}, mean={d.mean():.4f}, max={d.max():.4f}")
    print(f"  velocity:   min={v.min():.4f}, mean={v.mean():.4f}, max={v.max():.4f}")
    print(f"  area:       min={a.min():.0f},     mean={a.mean():.0f},     max={a.max():.0f}")
    print(f"  frac_spawn: min={f.min():.3f}, mean={f.mean():.3f}, max={f.max():.3f}")

print()
print(f"spawn_depth_table:  {dict(sp_cfg.spawn_depth_table)}")
print(f"spawn_vel_table:    {dict(sp_cfg.spawn_vel_table)}")
print(f"spawn_suitability_tol: {sp_cfg.spawn_suitability_tol}")

# Compute suitability under both unit hypotheses
print()
print("=== Suitability check using values AS-IS ===")
r_idx = model.reach_order.index("Lower")
sample = np.where(cs.reach_idx == r_idx)[0][:1]
if len(sample) > 0:
    c = sample[0]
    d = float(cs.depth[c])
    v = float(cs.velocity[c])
    a = float(cs.area[c])
    f = float(cs.frac_spawn[c])
    depth_xs = np.array(sorted(sp_cfg.spawn_depth_table.keys()), dtype=float)
    depth_ys = np.array([sp_cfg.spawn_depth_table[k] for k in depth_xs], dtype=float)
    vel_xs = np.array(sorted(sp_cfg.spawn_vel_table.keys()), dtype=float)
    vel_ys = np.array([sp_cfg.spawn_vel_table[k] for k in vel_xs], dtype=float)
    print(f"Lower cell {c}: depth={d}, vel={v}, area={a}, fs={f}")
    print(f"  AS-IS:   d_score={np.interp(d, depth_xs, depth_ys):.3f}, v_score={np.interp(v, vel_xs, vel_ys):.3f}")
    print(f"           total={np.interp(d, depth_xs, depth_ys)*np.interp(v, vel_xs, vel_ys)*f*a:.3f}")
    # If tables are cm but cs is m, multiply by 100
    print(f"  IF cs is m and tables are cm (need to ×100):")
    print(f"           d*100={d*100:.1f} cm → d_score={np.interp(d*100, depth_xs, depth_ys):.3f}")
    print(f"           v*100={v*100:.1f} cm/s → v_score={np.interp(v*100, vel_xs, vel_ys):.3f}")
    print(f"           total={np.interp(d*100, depth_xs, depth_ys)*np.interp(v*100, vel_xs, vel_ys)*f*a:.3f}")
