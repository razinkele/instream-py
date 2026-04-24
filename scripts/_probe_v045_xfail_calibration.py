"""v0.45 probe: diagnose the xfail'd `test_fish_size_correlates_with_depth`.

Test runs example_a for 912 days, then computes spearmanr(lengths, depths)
on alive fish and asserts |rho| > 0.01. Currently xfails because the test
reports `ConstantInputWarning: An input array is constant`.

This probe reproduces the simulation and prints the population state so
we can see which input is constant (lengths or depths) and by how much,
which informs the calibration direction.

Usage:
    micromamba run -n shiny python scripts/_probe_v045_xfail_calibration.py
"""
from __future__ import annotations

import logging
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Suppress the "capacity full; dropping eggs" noise — we know it happens.
logging.getLogger("salmopy.spawning").setLevel(logging.ERROR)


def main():
    import argparse
    import datetime as _dt

    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None,
                    help="run duration (default: use config end_date -> 912 days)")
    args = ap.parse_args()

    from salmopy.model import SalmopyModel

    CONFIGS = Path(__file__).resolve().parent.parent / "configs"
    FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

    end_date = None
    if args.days:
        start = _dt.date(2011, 4, 1)
        end_date = (start + _dt.timedelta(days=args.days)).isoformat()
        print(f"Running example_a ({args.days} days, ending {end_date})...")
    else:
        print("Running example_a (912 days, config default)...")

    model = SalmopyModel(
        CONFIGS / "example_a.yaml",
        data_dir=FIXTURES / "example_a",
        end_date_override=end_date,
    )
    model.run()

    ts = model.trout_state
    cs = model.fem_space.cell_state
    alive = ts.alive_indices()
    n_alive = len(alive)
    capacity = ts.alive.shape[0]

    print()
    print(f"{'=' * 60}")
    print(f"Population state after 912-day sim (example_a, default seed)")
    print(f"{'=' * 60}")
    print(f"n_alive      : {n_alive}")
    print(f"capacity     : {capacity}  ({100.0 * n_alive / capacity:.1f}% used)")

    if n_alive == 0:
        print("COHORT COLLAPSED — no alive fish. Calibration drift = total mortality.")
        return

    lengths = ts.length[alive]
    ages = ts.age[alive]
    cells = ts.cell_idx[alive]
    depths = cs.depth[cells]
    life_stages = ts.life_history[alive]

    # LifeStage enum values — import to decode
    from salmopy.state.life_stage import LifeStage

    print()
    print("--- Length distribution (cm) ---")
    print(f"  min      : {lengths.min():.3f}")
    print(f"  max      : {lengths.max():.3f}")
    print(f"  mean     : {lengths.mean():.3f}")
    print(f"  std      : {lengths.std():.3f}")
    print(f"  unique   : {len(np.unique(lengths))}")
    print(f"  variance : {lengths.var():.9f}")
    if lengths.var() < 1e-9:
        print(f"  *** CONSTANT *** — this is the NaN-rho cause")

    print()
    print("--- Depth distribution at chosen cells (m) ---")
    print(f"  min      : {depths.min():.3f}")
    print(f"  max      : {depths.max():.3f}")
    print(f"  mean     : {depths.mean():.3f}")
    print(f"  std      : {depths.std():.3f}")
    print(f"  unique   : {len(np.unique(depths))}")
    if depths.var() < 1e-9:
        print(f"  *** CONSTANT ***")

    print()
    print("--- Age distribution (years) ---")
    print(f"  min      : {ages.min()}")
    print(f"  max      : {ages.max()}")
    print(f"  mean     : {ages.mean():.2f}")
    print(f"  unique   : {len(np.unique(ages))}")

    print()
    print("--- Life-stage distribution ---")
    stages, counts = np.unique(life_stages, return_counts=True)
    for s, c in zip(stages, counts):
        try:
            name = LifeStage(int(s)).name
        except ValueError:
            name = f"UNKNOWN({s})"
        print(f"  {name:<20} {c:>6}  ({100.0 * c / n_alive:.1f}%)")

    # Compute Spearman rho explicitly to confirm it's NaN
    from scipy.stats import spearmanr
    rho, p = spearmanr(lengths, depths)
    print()
    print(f"--- Test assertion ---")
    print(f"  spearmanr(lengths, depths) = {rho} (p={p})")
    print(f"  |rho| > 0.01 ?  {abs(rho) > 0.01 if not np.isnan(rho) else 'NaN — test fails'}")


if __name__ == "__main__":
    main()
