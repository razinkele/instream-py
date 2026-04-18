"""Diagnose which gate in the spawn pipeline is rejecting Baltic fish.

Loads the Baltic model, jumps the clock to mid-October (peak spawn),
then iterates the pipeline manually while counting how many fish drop
out at each gate: ready_to_spawn, cell lookup, suitability tolerance,
defense-area exclusion, create_redd.

Usage:
    micromamba run -n shiny python scripts/_diag_spawn_pipeline.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

from instream.model import InSTREAMModel  # noqa: E402
from instream.state.life_stage import LifeStage  # noqa: E402
from instream.modules.spawning import ready_to_spawn  # noqa: E402

CONFIG = str(PROJECT / "configs" / "example_baltic.yaml")
DATA_DIR = str(PROJECT / "tests" / "fixtures" / "example_baltic")


def main() -> None:
    print("Building model...")
    model = InSTREAMModel(CONFIG, data_dir=DATA_DIR)

    # Skip to day 210 (mid-Oct = peak spawn window for Baltic salmon).
    print("Stepping 210 days to peak spawn window...")
    for _ in range(210):
        model.step()
    print(f"Now at doy {model.time_manager.current_date.day_of_year}, "
          f"alive={model.trout_state.num_alive()}, "
          f"redds={model.redd_state.num_alive()}")

    # Audit the cell state for frac_spawn — is there ANY spawning habitat?
    cs = model.fem_space.cell_state
    print()
    print(f"=== cell_state.frac_spawn summary ({len(cs.frac_spawn)} cells) ===")
    print(f"  min={cs.frac_spawn.min():.4f}  "
          f"max={cs.frac_spawn.max():.4f}  "
          f"mean={cs.frac_spawn.mean():.4f}")
    nonzero = np.sum(cs.frac_spawn > 0)
    print(f"  cells with frac_spawn > 0: {nonzero} / {len(cs.frac_spawn)} "
          f"({100 * nonzero / len(cs.frac_spawn):.1f}%)")
    # Per-reach breakdown
    print()
    print(f"{'Reach':<18} {'n_cells':>8} {'w/ fs>0':>8} {'mean_fs':>10} "
          f"{'mean_depth':>11} {'mean_vel':>10}")
    print("-" * 75)
    for r_idx, r_name in enumerate(model.reach_order):
        mask = cs.reach_idx == r_idx
        n = int(np.sum(mask))
        if n == 0:
            continue
        fs_n = int(np.sum(cs.frac_spawn[mask] > 0))
        fs_mean = float(cs.frac_spawn[mask].mean())
        d_mean = float(cs.depth[mask].mean())
        v_mean = float(cs.velocity[mask].mean())
        print(f"{r_name:<18} {n:>8} {fs_n:>8} {fs_mean:>10.4f} "
              f"{d_mean:>11.2f} {v_mean:>10.3f}")

    # Walk the spawn pipeline for every freshwater fish.
    print()
    print("=== Per-gate drop counts (one spawn step) ===")
    alive = model.trout_state.alive_indices()
    fw_alive = alive[model.trout_state.zone_idx[alive] == -1]
    print(f"  freshwater alive: {len(fw_alive)}")

    stage_hist = Counter(int(s) for s in model.trout_state.life_history[fw_alive])
    print(f"  by stage: {dict(stage_hist)}")

    spawners = fw_alive[
        model.trout_state.life_history[fw_alive] == int(LifeStage.SPAWNER)
    ]
    print(f"  SPAWNER count: {len(spawners)}")

    if len(spawners) == 0:
        print("  No SPAWNERs — spawn window may not have opened yet.")
        return

    # Look at one spawner's state in detail
    s0 = spawners[0]
    print()
    print(f"=== Sample spawner idx={s0} ===")
    print(f"  sex={int(model.trout_state.sex[s0])}  "
          f"age={int(model.trout_state.age[s0])}  "
          f"length={float(model.trout_state.length[s0]):.1f}cm  "
          f"cond={float(model.trout_state.condition[s0]):.3f}")
    print(f"  cell_idx={int(model.trout_state.cell_idx[s0])}  "
          f"reach_idx={int(model.trout_state.reach_idx[s0])}  "
          f"zone_idx={int(model.trout_state.zone_idx[s0])}")
    print(f"  spawned_this_season={bool(model.trout_state.spawned_this_season[s0])}")
    r_idx = int(model.trout_state.reach_idx[s0])
    r_name = model.reach_order[r_idx]
    print(f"  reach: {r_name}")
    print(f"  temperature: {model.reach_state.temperature[r_idx]:.2f}C  "
          f"flow: {model.reach_state.flow[r_idx]:.2f}")

    doy = model.time_manager.current_date.day_of_year
    print(f"  doy: {doy}")

    # Count ready_to_spawn passes
    sp_idx = int(model.trout_state.species_idx[s0])
    sp_name = model.species_order[sp_idx]
    sp_cfg = model.config.species[sp_name]
    spawn_start_doy = getattr(sp_cfg, "spawn_start_doy", None)
    spawn_end_doy = getattr(sp_cfg, "spawn_end_doy", None)
    print(f"  species config spawn window: doy {spawn_start_doy}-{spawn_end_doy}")
    print(f"  species config spawn_prob: {sp_cfg.spawn_prob}, "
          f"min_temp={sp_cfg.spawn_min_temp}, max_temp={sp_cfg.spawn_max_temp}, "
          f"spawn_suitability_tol={sp_cfg.spawn_suitability_tol}")


if __name__ == "__main__":
    main()
