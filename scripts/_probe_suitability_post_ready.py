"""v0.52.1 diagnostic: run example_tornionjoki to mid-spawn-window
(Nov 1 year 1) and check WHY no redds get created. Inspects per-fish
suitability gates downstream of ready_to_spawn:

1. Cell depth + velocity values for the fish's location
2. spawn_depth_table + spawn_vel_table interpolations
3. frac_spawn × area
4. Final suitability score vs spawn_suitability_tol

Also reports cumulative redd creation up to this point.
"""
from __future__ import annotations
import datetime as _dt
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
logging.getLogger("salmopy.spawning").setLevel(logging.ERROR)


def main() -> int:
    from salmopy.model import SalmopyModel
    from salmopy.state.life_stage import LifeStage

    end = _dt.date(2011, 11, 1)
    print(f"Running example_tornionjoki to {end}...")
    model = SalmopyModel(
        config_path=str(ROOT / "configs/example_tornionjoki.yaml"),
        data_dir=str(ROOT / "tests/fixtures/example_tornionjoki"),
        end_date_override=end.isoformat(),
    )
    model.rng = np.random.default_rng(42)
    while not model.time_manager.is_done():
        model.step()

    ts = model.trout_state
    cs = model.fem_space.cell_state
    sp_cfg = model.config.species["BalticAtlanticSalmon"]

    # Convert spawn_depth_table dict -> sorted x/y arrays
    depth_table = sp_cfg.spawn_depth_table
    depth_xs = np.array(sorted(depth_table.keys()), dtype=float)
    depth_ys = np.array([depth_table[k] for k in depth_xs], dtype=float)
    vel_table = sp_cfg.spawn_vel_table
    vel_xs = np.array(sorted(vel_table.keys()), dtype=float)
    vel_ys = np.array([vel_table[k] for k in vel_xs], dtype=float)

    print(f"\nspawn_depth_table x: {depth_xs}")
    print(f"spawn_depth_table y: {depth_ys}")
    print(f"spawn_vel_table x:   {vel_xs}")
    print(f"spawn_vel_table y:   {vel_ys}")
    print(f"spawn_suitability_tol: {sp_cfg.spawn_suitability_tol}")

    # Sample some cells from each spawning reach
    print("\n=== Cell depth + velocity samples ===")
    for reach_name in ["Lower", "Middle", "Upper"]:
        if reach_name not in model.reach_order:
            continue
        r_idx = model.reach_order.index(reach_name)
        reach_cells_arr = model._reach_cells.get(r_idx, np.array([]))
        if len(reach_cells_arr) == 0:
            continue
        sample = reach_cells_arr[:5]
        print(f"\n{reach_name} (reach_idx={r_idx}, frac_spawn={cs.frac_spawn[sample[0]]:.3f}):")
        for c in sample:
            d = float(cs.depth[c])
            v = float(cs.velocity[c])
            d_score = float(np.interp(d, depth_xs, depth_ys))
            v_score = float(np.interp(v, vel_xs, vel_ys))
            fs = float(cs.frac_spawn[c])
            area = float(cs.area[c])
            score = d_score * v_score * fs * area
            print(f"  cell {int(c)}: depth={d:.3f}, vel={v:.4f}, "
                  f"d_score={d_score:.3f}, v_score={v_score:.3f}, "
                  f"frac_spawn={fs:.3f}, area={area:.0f}, "
                  f"suitability={score:.3f}")

    # Stats on RA fish
    alive = ts.alive_indices()
    is_ra = ts.life_history[alive] == int(LifeStage.RETURNING_ADULT)
    ra = alive[is_ra]
    print(f"\nRETURNING_ADULTs: {len(ra)}")

    # For each RA fish, compute hypothetical max suitability score
    # within search radius
    search_r = (
        getattr(sp_cfg, "spawn_search_radius_m", 0.0) or sp_cfg.move_radius_max * 0.1
    )
    print(f"spawn search radius: {search_r:.0f} m")

    n_pass_suit = 0
    n_fail_suit = 0
    sample_pass = []
    sample_fail = []
    for i in ra:
        cell = int(ts.cell_idx[i])
        if cell < 0:
            continue
        candidates = model.fem_space.cells_in_radius(cell, search_r)
        if len(candidates) == 0:
            candidates = np.array([cell])
        s_d = cs.depth[candidates]
        s_v = cs.velocity[candidates]
        scores = (
            np.interp(s_d, depth_xs, depth_ys)
            * np.interp(s_v, vel_xs, vel_ys)
            * cs.frac_spawn[candidates]
            * cs.area[candidates]
        )
        max_score = float(np.max(scores))
        if max_score > sp_cfg.spawn_suitability_tol:
            n_pass_suit += 1
            if len(sample_pass) < 3:
                sample_pass.append((int(i), cell, max_score, len(candidates)))
        else:
            n_fail_suit += 1
            if len(sample_fail) < 3:
                sample_fail.append((int(i), cell, max_score, len(candidates), s_d.max(), s_v.max()))

    print(f"\nPer-RA suitability gate (max score across search radius):")
    print(f"  pass (max_score > {sp_cfg.spawn_suitability_tol}): {n_pass_suit}")
    print(f"  fail: {n_fail_suit}")
    print("\nSample passing:")
    for f, c, s, n in sample_pass:
        print(f"  fish[{f}] cell={c} max_suit={s:.2f} (over {n} candidate cells)")
    print("\nSample failing:")
    for f, c, s, n, dmax, vmax in sample_fail:
        print(f"  fish[{f}] cell={c} max_suit={s:.2f} (over {n} candidate cells, "
              f"max depth={dmax:.2f}, max vel={vmax:.4f})")

    # Also check redd counts to date
    redd_state = model.redd_state
    n_alive_redds = int(redd_state.alive.sum())
    init_cum = int(redd_state.eggs_initial.sum())
    print(f"\nRedd state at {end}: n_alive_redds={n_alive_redds}, init_cum={init_cum}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
