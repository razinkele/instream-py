"""Phase-3 hypothesis test: does setting FRACSPWN > 0 unblock redd creation?

Temporarily patches the Baltic fixture shapefile to give Leite cells
(shallowest reach in the fixture) a nonzero FRACSPWN, runs a 220-day
simulation, and reports redd counts. If hypothesis is correct, redds
appear. Then restores the original shapefile.

Usage:
    micromamba run -n shiny python scripts/_test_fracspawn_hypothesis.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

SHP = (
    PROJECT / "tests" / "fixtures" / "example_baltic"
    / "Shapefile" / "BalticExample.shp"
)


def main() -> None:
    # Backup all shapefile components
    backup = {}
    for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
        f = SHP.with_suffix(ext)
        if f.exists():
            backup[ext] = f.read_bytes()

    try:
        # Patch FRACSPWN: 0.10 for small-tributary cells most likely to have
        # viable spawning depths, 0.0 elsewhere.
        gdf = gpd.read_file(str(SHP))
        print(f"Original FRACSPWN nonzero: {int((gdf['FRACSPWN'] > 0).sum())} / {len(gdf)}")

        target_reaches = ["Leite", "Minija", "Sysa", "Atmata", "Nemunas"]
        mask = gdf["REACH_NAME"].isin(target_reaches)
        gdf.loc[mask, "FRACSPWN"] = 0.10
        print(f"Patched FRACSPWN nonzero: {int((gdf['FRACSPWN'] > 0).sum())} / {len(gdf)}")

        # Write back
        gdf.to_file(str(SHP))

        # Now run the sim
        from instream.model import InSTREAMModel  # noqa: E402
        model = InSTREAMModel(
            str(PROJECT / "configs" / "example_baltic.yaml"),
            data_dir=str(PROJECT / "tests" / "fixtures" / "example_baltic"),
        )
        print(f"\nModel built. Initial pop: {model.trout_state.num_alive()}")

        # Step to day 220 (past spawn season start + 10 days)
        redd_milestones = [90, 150, 200, 210, 215, 220]
        for d in range(1, 221):
            model.step()
            if d in redd_milestones:
                n_redds = model.redd_state.num_alive()
                alive = model.trout_state.num_alive()
                from instream.state.life_stage import LifeStage
                alive_idx = model.trout_state.alive_indices()
                if len(alive_idx) > 0:
                    spawners = int(np.sum(
                        model.trout_state.life_history[alive_idx] == int(LifeStage.SPAWNER)
                    ))
                else:
                    spawners = 0
                total_eggs = (
                    int(model.redd_state.num_eggs[model.redd_state.alive].sum())
                    if n_redds > 0 else 0
                )
                print(f"  day {d:>3d}: alive={alive:>5d}  "
                      f"SPAWNER={spawners:>4d}  REDDS={n_redds:>4d}  "
                      f"total_eggs={total_eggs:>7d}")

        print()
        if model.redd_state.num_alive() > 0:
            print("HYPOTHESIS CONFIRMED: redds created after setting FRACSPWN > 0")
            # Show per-reach redd distribution
            alive_mask = model.redd_state.alive
            r_idx = model.redd_state.reach_idx[alive_mask]
            print("  Redds per reach:")
            for ri in sorted(set(int(x) for x in r_idx)):
                r_name = model.reach_order[ri]
                n = int(np.sum(r_idx == ri))
                print(f"    {r_name}: {n}")
        else:
            print("HYPOTHESIS REJECTED: 0 redds even with FRACSPWN=0.10")
            print("  → frac_spawn is necessary but not sufficient; check depths")

    finally:
        # Restore backup
        for ext, contents in backup.items():
            SHP.with_suffix(ext).write_bytes(contents)
        print(f"\nRestored original fixture from backup.")


if __name__ == "__main__":
    main()
