"""Arc E per-fish growth trace — daily (length, weight, condition, growth_rate,
activity, cell_temp, cell_velocity, cell_depth) for 5 sample Chinook-Spring
FRY/PARR over 40 days post-emergence.

Context: the 600-day probe showed juvenile mean length stalls at 3.95-4.04 cm
while NetLogo's same cohort grows to 5.4-6.2 cm by May 2012. Function-level
growth tests pass (growth_rate_for matches NetLogo on a 300k-row reference).
So the problem must be in the INTEGRATION — either (a) last_growth_rate is
actually near zero every day because resource depletion starves fish in-sim,
or (b) weight grows but length doesn't (condition factor feedback: length
only updates when weight > healthy_weight).

This probe tags 5 fish at the 2012-01-20 FRY emergence and dumps their per-day
state + environment for 40 days. The expected-to-see pattern:

  - If growth_rate ~ 0 consistently: food-limited (density → cell depletion)
  - If growth_rate > 0 but length flat: condition-factor length-lock
    (weight grows back after loss but length never increases)
  - If growth_rate varies wildly: cell switching / habitat instability

Output: scripts/_arc_e_fish_trace.csv with one row per (fish, day) tuple.
"""
from __future__ import annotations

from pathlib import Path
import datetime

import numpy as np
import pandas as pd

from instream.model import InSTREAMModel
from instream.state.life_stage import LifeStage

PROJECT = Path(__file__).resolve().parent.parent
CONFIGS = PROJECT / "configs"
FIXTURES = PROJECT / "tests" / "fixtures"


def main() -> None:
    # Tag ≥5 NATAL-cohort FRY (length < 4.5 cm, age 0) at first emergence
    # after day 280 (2012-01-06) — the initial pop is all >4cm from the
    # ExampleA-InitialPopulations.csv fixture.
    start = datetime.date(2011, 4, 1)
    end = (start + datetime.timedelta(days=360)).isoformat()
    model = InSTREAMModel(
        CONFIGS / "example_a.yaml",
        data_dir=FIXTURES / "example_a",
        end_date_override=end,
    )

    tagged_ids = None
    tagged_initial_length = None  # guard against slot reuse
    records = []
    day = 0
    while not model.time_manager.is_done():
        model.step()
        if not model.time_manager.is_day_boundary:
            continue
        day += 1
        ts = model.trout_state
        cs = model.fem_space.cell_state
        rs = model.reach_state
        alive = ts.alive_indices()
        # CH-S natal juveniles: species 0, FRY, length <4.5 cm (excludes
        # initial-pop fish which emerge at 4-7 cm)
        juv_mask = (
            (ts.species_idx[alive] == 0)
            & (ts.life_history[alive] == int(LifeStage.FRY))
            & (ts.length[alive] < 4.5)
            & (ts.age[alive] == 0)
        )
        juv = alive[juv_mask]

        # Tag on first day after day 280 (mid-Jan 2012 emergence window)
        if tagged_ids is None and day >= 280 and len(juv) >= 5:
            tagged_ids = juv[:5].tolist()
            tagged_initial_length = ts.length[tagged_ids].copy()
            print(
                f"Tagged natal FRY {tagged_ids} on {model.time_manager.current_date.date()} (day {day})"
            )
            print(
                f"  initial lengths: {ts.length[tagged_ids].tolist()}"
            )
            print(
                f"  initial weights: {ts.weight[tagged_ids].tolist()}"
            )

        if tagged_ids is not None:
            for k, fid in enumerate(tagged_ids):
                if not ts.alive[fid]:
                    continue
                # Slot-reuse guard: a tagged fish cannot suddenly grow
                # >2x in length. Drop it from the trace if so.
                if ts.length[fid] > tagged_initial_length[k] * 2.0:
                    continue
                cell = int(ts.cell_idx[fid])
                reach = int(ts.reach_idx[fid])
                records.append(
                    dict(
                        sim_date=model.time_manager.current_date.date(),
                        day=day,
                        fish=fid,
                        life_stage=int(ts.life_history[fid]),
                        length=float(ts.length[fid]),
                        weight=float(ts.weight[fid]),
                        condition=float(ts.condition[fid]),
                        last_growth_rate=float(ts.last_growth_rate[fid]),
                        activity=int(ts.activity[fid]),
                        cell=cell,
                        reach=reach,
                        depth=float(cs.depth[cell]) if cell >= 0 else np.nan,
                        velocity=float(cs.velocity[cell]) if cell >= 0 else np.nan,
                        light=float(cs.light[cell]) if cell >= 0 else np.nan,
                        avail_drift=float(cs.available_drift[cell]) if cell >= 0 else np.nan,
                        avail_search=float(cs.available_search[cell]) if cell >= 0 else np.nan,
                        temperature=float(rs.temperature[reach]) if reach >= 0 else np.nan,
                    )
                )

        # Stop 40 days after tagging
        if tagged_ids is not None and day - records[0]["day"] > 40:
            break

    if not records:
        print("ERROR: never reached ≥5 juveniles — cohort may have crashed")
        return

    df = pd.DataFrame(records)
    out_csv = PROJECT / "scripts" / "_arc_e_fish_trace.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nWrote {len(df)} rows: {out_csv}")

    # Per-fish summary: net length/weight gain, avg daily growth
    print("\n=== Per-fish summary (40-day window) ===")
    for fid in tagged_ids:
        f = df[df["fish"] == fid]
        if len(f) < 2:
            print(f"fish {fid}: died early ({len(f)} days)")
            continue
        dL = f["length"].iloc[-1] - f["length"].iloc[0]
        dW = f["weight"].iloc[-1] - f["weight"].iloc[0]
        mean_gr = f["last_growth_rate"].mean()
        mean_cond = f["condition"].mean()
        print(
            f"fish {fid}: days={len(f)} "
            f"dL={dL:+.3f}cm dW={dW:+.4f}g "
            f"mean_growth={mean_gr:+.4f}g/day mean_cond={mean_cond:.3f}"
        )

    # Aggregate: per-day across all tagged fish
    print("\n=== Daily aggregate (mean over 5 fish) ===")
    daily = (
        df.groupby("day")
        .agg(
            length=("length", "mean"),
            weight=("weight", "mean"),
            cond=("condition", "mean"),
            growth=("last_growth_rate", "mean"),
            avail_drift=("avail_drift", "mean"),
            n=("fish", "count"),
        )
        .round(4)
    )
    print(daily.head(15).to_string())
    print("...")
    print(daily.tail(15).to_string())


if __name__ == "__main__":
    main()
