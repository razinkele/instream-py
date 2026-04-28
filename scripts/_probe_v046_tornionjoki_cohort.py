"""v0.46 probe: per-cohort survival + life-stage breakdown for example_tornionjoki.

Runs example_tornionjoki for N years (default 5), captures snapshots
every 180 days, and reports both:

1. Per-age-class cohort histogram (across ALL alive states)
2. Per-life-stage breakdown (FRY/PARR/SMOLT/OCEAN_JUVENILE/OCEAN_ADULT/RETURNING_ADULT)
3. End-of-run smolt-age distribution from model._outmigrants — the
   smoking-gun metric for the test_latitudinal_smolt_age_gradient xfail
   (test expects modal age 4 for Tornionjoki; currently modal=2).

The age histogram alone is ambiguous because it counts ALL alive fish
regardless of state — a fish that smolted at age 2 and is now in
OCEAN_JUVENILE still appears as "age 2 alive". The life-stage
breakdown disambiguates, and outmigrants.csv-style records give the
authoritative smolt-age distribution.

Usage:
    micromamba run -n shiny python scripts/_probe_v046_tornionjoki_cohort.py --years 3
"""
from __future__ import annotations

import argparse
import datetime as _dt
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
logging.getLogger("salmopy.spawning").setLevel(logging.ERROR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=5)
    args = ap.parse_args()

    from salmopy.model import SalmopyModel

    start = _dt.date(2011, 4, 1)
    end = (start + _dt.timedelta(days=365 * args.years)).isoformat()
    print(f"Running example_tornionjoki for {args.years} years (end {end})...")
    model = SalmopyModel(
        config_path=str(ROOT / "configs/example_tornionjoki.yaml"),
        data_dir=str(ROOT / "tests/fixtures/example_tornionjoki"),
        end_date_override=end,
    )
    # Pin the seed for reproducibility — matches what
    # tests/test_multi_river_baltic.py uses.
    model.rng = np.random.default_rng(42)
    from salmopy.state.life_stage import LifeStage

    snapshots = []
    next_snapshot = start
    while not model.time_manager.is_done():
        model.step()
        cur = model.time_manager.current_date
        cur_date = cur.date() if hasattr(cur, "date") else cur
        if cur_date >= next_snapshot:
            # Defensive copy — trout_state arrays mutate in place.
            alive = model.trout_state.alive_indices()
            ages_snapshot = model.trout_state.age[alive].copy()
            stages_snapshot = model.trout_state.life_history[alive].copy()

            # Redd-state snapshot for the natal-recruitment diagnosis.
            # B5: track whether redds get created at all, and where eggs go.
            redd_state = getattr(model, "redd_state", None)
            if redd_state is not None and getattr(redd_state, "alive", None) is not None:
                redd_alive_mask = redd_state.alive
                n_redds = int(redd_alive_mask.sum())
                if n_redds > 0:
                    eggs_now = int(redd_state.num_eggs[redd_alive_mask].sum())
                    frac_dev_mean = float(redd_state.frac_developed[redd_alive_mask].mean())
                else:
                    eggs_now = 0
                    frac_dev_mean = 0.0
                # Cumulative loss counters (across ALL slots ever used,
                # alive or recycled — these are tracking arrays not zeroed
                # on death; sums over the full capacity give cumulative
                # losses for redds that have ever existed).
                eggs_initial_cum = int(redd_state.eggs_initial.sum())
                eggs_lo_temp_cum = int(redd_state.eggs_lo_temp.sum())
                eggs_hi_temp_cum = int(redd_state.eggs_hi_temp.sum())
                eggs_dewater_cum = int(redd_state.eggs_dewatering.sum())
                eggs_scour_cum = int(redd_state.eggs_scour.sum())
                redd_summary = (n_redds, eggs_now, frac_dev_mean,
                                eggs_initial_cum, eggs_lo_temp_cum,
                                eggs_hi_temp_cum, eggs_dewater_cum,
                                eggs_scour_cum)
            else:
                redd_summary = None

            snapshots.append((cur_date, ages_snapshot, stages_snapshot, redd_summary))
            next_snapshot = next_snapshot + _dt.timedelta(days=180)

    # ----- Section 1: age histogram (all alive states) -----
    print()
    print("=== AGE HISTOGRAM (all alive states) ===")
    print(f"{'date':<12} {'n_alive':>8} {'cohort histogram (age_years -> count)'}")
    print("-" * 70)
    for date, ages_snapshot, _, _ in snapshots:
        hist = Counter(int(a) for a in ages_snapshot)
        hist_str = ", ".join(f"{a}:{n}" for a, n in sorted(hist.items()))
        print(f"{date.isoformat():<12} {len(ages_snapshot):>8} {hist_str}")

    # ----- Section 2: life-stage breakdown -----
    print()
    print("=== LIFE-STAGE BREAKDOWN ===")
    stage_names = {s.value: s.name for s in LifeStage}
    print(f"{'date':<12} " + " ".join(f"{stage_names.get(i, str(i))[:6]:>7}" for i in sorted(stage_names)))
    print("-" * 70)
    for date, _, stages_snapshot, _ in snapshots:
        stage_hist = Counter(int(s) for s in stages_snapshot)
        row = " ".join(f"{stage_hist.get(i, 0):>7}" for i in sorted(stage_names))
        print(f"{date.isoformat():<12} {row}")

    # ----- Section 4: redd state (B5: natal-recruitment pathway) -----
    print()
    print("=== REDD STATE (natal recruitment) ===")
    print(f"{'date':<12} {'n_redds':>8} {'eggs_now':>9} {'frac_dev':>9} "
          f"{'init_cum':>9} {'lo_T':>7} {'hi_T':>7} {'dewat':>7} {'scour':>7}")
    print("-" * 90)
    have_redd_data = False
    for date, _, _, rs in snapshots:
        if rs is None:
            print(f"{date.isoformat():<12}  (model.redd_state not available)")
            continue
        have_redd_data = True
        n_redds, eggs_now, frac_dev, init_cum, lo_T, hi_T, dewat, scour = rs
        print(f"{date.isoformat():<12} {n_redds:>8} {eggs_now:>9} {frac_dev:>9.3f} "
              f"{init_cum:>9} {lo_T:>7} {hi_T:>7} {dewat:>7} {scour:>7}")
    if have_redd_data:
        print()
        print("Interpretation:")
        print("  init_cum > 0 + n_redds == 0 → redds existed but all eggs hatched/died")
        print("  init_cum == 0              → spawning never produced eggs (fix delivery)")
        print("  lo_T high                  → winter freezing kills eggs (Tornionjoki cold)")
        print("  hi_T high                  → summer overheating kills eggs (unlikely at 65°N)")
        print("  dewat / scour high         → flow regime kills eggs")

    # ----- Section 3: smolt-age distribution from outmigrants -----
    print()
    print("=== SMOLT-AGE DISTRIBUTION (from model._outmigrants) ===")
    outmigrants = getattr(model, "_outmigrants", []) or []
    if not outmigrants:
        print("(no outmigrants recorded — model._outmigrants is empty)")
    else:
        smolt_ages = [int(om["age_years"]) for om in outmigrants
                      if "age_years" in om]
        if smolt_ages:
            hist = Counter(smolt_ages)
            modal = hist.most_common(1)[0][0]
            total = sum(hist.values())
            print(f"total outmigrants: {total}")
            print(f"modal smolt age: {modal}")
            print("distribution:")
            for age in sorted(hist):
                pct = 100.0 * hist[age] / total
                bar = "#" * int(pct / 2)
                print(f"  age {age}: {hist[age]:>5} ({pct:>5.1f}%)  {bar}")
        else:
            print(f"(have {len(outmigrants)} outmigrant records but none had age_years)")


if __name__ == "__main__":
    main()
