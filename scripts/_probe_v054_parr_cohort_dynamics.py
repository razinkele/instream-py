"""v0.54 probe: PARR cohort-age dynamics for example_tornionjoki.

The v0.53.5 5-yr smolt-age test (commit 05d028b, 4h 2m walltime) confirms
modal smolt age = 2 even with v0.53.1's `is_natal` filter active. That
means the residual gap is calibration, not measurement methodology. Two
hypotheses:

  H1: GROWTH TOO FAST — fish reach smolt-length threshold by age 2 even
      though real Tornionjoki Atlantic salmon need 4 years for it.
      → Length-at-age would track ABOVE the real curve; smolting happens
        at age 2 because the size criterion fires.
  H2: COHORTS COLLAPSE — natal cohorts die from mortality before they
      reach age 4, so the survivors that DO smolt are necessarily young.
      → Cohort size by age would crash between year 2 and year 4;
        fewer survivors at older ages even when length is below threshold.

This probe runs example_tornionjoki for N years and tracks each natal
cohort over time, snapshotting weekly:
  * Cohort identity: round(age_years) at emergence year
  * Cohort size: count of natal alive agents per age bin (super-rep
    weighted)
  * Length distribution: mean + p10/p50/p90 length per age bin
  * Smolt outcome: from `model._outmigrants`, count smolts per
    natal-birth-year + report age at smolt

The smoking gun:
  * If H1 holds: mean length at age 2 > 14 cm (Tornionjoki smolt
    threshold) → fish smolt because they're "too big for parr".
    Compare to NetLogo / real curve: Tornionjoki age-2 parr should be
    ~10-12 cm, not 14+.
  * If H2 holds: mean length at age 2-3 stays in juvenile range, but
    cohort size drops by 90%+ between age 2 and 3 → mortality is the
    constraint, not growth.
  * Combined: probably some of each.

Either way, this probe gives a clear diagnostic signal that distinguishes
"calibrate growth params" from "calibrate mortality params" as the
v0.54.x next step.

Usage:
    micromamba run -n shiny python scripts/_probe_v054_parr_cohort_dynamics.py --years 5

The 5-yr run takes ~75-90 min on a quiet system (~115+ min if anything
else is competing). Use --years 1 for a quick smoke (~5 min).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
logging.getLogger("salmopy.spawning").setLevel(logging.ERROR)


def _percentiles(arr: np.ndarray, ps=(10, 50, 90)) -> dict[int, float]:
    if len(arr) == 0:
        return {p: float("nan") for p in ps}
    return {int(p): float(np.percentile(arr, p)) for p in ps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=5,
                    help="Sim length in years (default 5; matches the xfail'd test).")
    ap.add_argument("--config", type=str,
                    default="configs/example_tornionjoki.yaml")
    ap.add_argument("--data-dir", type=str,
                    default="tests/fixtures/example_tornionjoki")
    ap.add_argument("--snapshot-days", type=int, default=14,
                    help="Snapshot interval in days (default 14 = biweekly).")
    args = ap.parse_args()

    from salmopy.model import SalmopyModel
    from salmopy.state.life_stage import LifeStage

    parr_value = LifeStage.PARR.value
    fry_value = LifeStage.FRY.value
    smolt_value = LifeStage.SMOLT.value

    start = _dt.date(2011, 4, 1)
    end = (start + _dt.timedelta(days=365 * args.years)).isoformat()
    print(f"Running {Path(args.config).stem} for {args.years} years (end {end})...")

    model = SalmopyModel(
        config_path=str(ROOT / args.config),
        data_dir=str(ROOT / args.data_dir),
        end_date_override=end,
    )
    model.rng = np.random.default_rng(42)

    # Snapshots: list of dicts {date, by_age: {age_bin: {n_super, n_indiv,
    #   length_mean, length_p10, length_p50, length_p90, life_stage_hist}}}
    snapshots = []
    next_snapshot = start
    snap_dt = _dt.timedelta(days=args.snapshot_days)

    while not model.time_manager.is_done():
        model.step()
        cur = model.time_manager.current_date
        cur_date = cur.date() if hasattr(cur, "date") else cur
        if cur_date < next_snapshot:
            continue

        ts = model.trout_state
        alive = ts.alive_indices()
        is_natal = getattr(ts, "is_natal", None)
        if is_natal is None:
            print("ERROR: trout_state has no is_natal attribute. "
                  "v0.53.1 added it; this probe requires v0.53.1+.")
            return
        natal_alive = alive[is_natal[alive]]
        if len(natal_alive) == 0:
            next_snapshot = cur_date + snap_dt
            continue

        ages = ts.age[natal_alive]
        lengths = ts.length[natal_alive]
        reps = ts.superind_rep[natal_alive]
        stages = ts.life_history[natal_alive]
        # Bin by integer age
        age_bins = np.floor(ages).astype(int)
        snap = {"date": cur_date, "by_age": {}}
        for age in sorted(set(age_bins.tolist())):
            mask = age_bins == age
            n_super = int(mask.sum())
            n_indiv = int(reps[mask].sum())
            ls = lengths[mask]
            stage_counts = {}
            for s_val, s_name in [
                (fry_value, "FRY"), (parr_value, "PARR"), (smolt_value, "SMOLT"),
            ]:
                stage_counts[s_name] = int((stages[mask] == s_val).sum())
            snap["by_age"][age] = {
                "n_super": n_super,
                "n_indiv": n_indiv,
                "length_mean": float(ls.mean()) if len(ls) > 0 else float("nan"),
                **_percentiles(ls),
                "stage_hist": stage_counts,
            }
        snapshots.append(snap)
        next_snapshot = cur_date + snap_dt

    # ----- Section 1: cohort-size-by-age timeline -----
    print()
    print("=== COHORT SIZE BY AGE (super-individuals; natal alive only) ===")
    all_ages = sorted({a for snap in snapshots for a in snap["by_age"]})
    if not all_ages:
        print("(no natal cohorts seen — check that recruitment is firing)")
        return
    header = "date          " + " ".join(f"{f'age{a}':>7}" for a in all_ages) + "  total"
    print(header)
    print("-" * len(header))
    for snap in snapshots:
        row = []
        total = 0
        for a in all_ages:
            n = snap["by_age"].get(a, {}).get("n_super", 0)
            total += n
            row.append(f"{n:>7}")
        print(f"{snap['date'].isoformat():<12} " + " ".join(row) + f"  {total:>5}")

    # ----- Section 2: mean length by age (winter/summer of each year) -----
    print()
    print("=== MEAN LENGTH BY AGE (cm; natal alive, super-rep weighted view) ===")
    print(header)
    print("-" * len(header))
    for snap in snapshots:
        row = []
        for a in all_ages:
            entry = snap["by_age"].get(a)
            if entry is None or entry["n_super"] == 0:
                row.append("    ---")
            else:
                row.append(f"{entry['length_mean']:>7.2f}")
        print(f"{snap['date'].isoformat():<12} " + " ".join(row))

    # ----- Section 3: smolt outmigrants by age -----
    print()
    print("=== NATAL SMOLT OUTMIGRANTS BY AGE (from model._outmigrants) ===")
    outm = getattr(model, "_outmigrants", []) or []
    natal_outm = [
        om for om in outm
        if om.get("is_natal", False) and om.get("length_category") == "Smolt"
    ]
    if not natal_outm:
        print("(no natal smolt outmigrants — natal cohorts didn't reach smolt stage "
              "in the test window, OR the is_natal flag isn't propagating)")
    else:
        from collections import Counter
        ages = [int(round(om.get("age_years", 0))) for om in natal_outm]
        hist = Counter(ages)
        total = sum(hist.values())
        modal = hist.most_common(1)[0][0]
        print(f"total natal smolts: {total}")
        print(f"modal smolt age: {modal}")
        for age in sorted(hist):
            pct = 100.0 * hist[age] / total
            bar = "#" * int(pct / 2)
            print(f"  age {age}: {hist[age]:>5} ({pct:>5.1f}%)  {bar}")

    # ----- Section 4: H1 vs H2 readout -----
    print()
    print("=== HYPOTHESIS READOUT ===")
    print("H1 (growth too fast): mean length at age 2 vs 14 cm smolt threshold.")
    print("H2 (cohorts collapse): cohort retention age-2 → age-3.")
    # Compute mean age-2 length across all snapshots that had age-2 data
    age2_means = [s["by_age"][2]["length_mean"]
                  for s in snapshots if 2 in s["by_age"]
                  and s["by_age"][2]["n_super"] > 0]
    if age2_means:
        print(f"  mean age-2 length (across {len(age2_means)} snapshots): "
              f"{np.mean(age2_means):.2f} cm  "
              f"({'>' if np.mean(age2_means) > 14 else '<='} 14 cm threshold)")
    age2_to_age3 = []
    for s in snapshots:
        n2 = s["by_age"].get(2, {}).get("n_super", 0)
        n3 = s["by_age"].get(3, {}).get("n_super", 0)
        if n2 + n3 > 0:
            age2_to_age3.append((s["date"], n2, n3))
    if age2_to_age3:
        # Take peak age-2 and contemporaneous age-3 a year later
        peak = max(age2_to_age3, key=lambda r: r[1])
        peak_date, n2_peak, _ = peak
        target = peak_date + _dt.timedelta(days=365)
        next_yr = min(age2_to_age3, key=lambda r: abs((r[0] - target).days))
        if abs((next_yr[0] - target).days) < 90:
            n3_next = next_yr[2]
            retention = (n3_next / n2_peak) if n2_peak > 0 else float("nan")
            print(f"  age-2→age-3 retention: peak age-2={n2_peak} on {peak_date}, "
                  f"age-3 a year later={n3_next} ({retention*100:.1f}%)")
            if retention < 0.3:
                print("    → H2 evidence: large age-2→age-3 collapse")
            else:
                print("    → H2 weak: most age-2 fish survive to age 3")


if __name__ == "__main__":
    main()
