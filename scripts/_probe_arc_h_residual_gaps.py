"""Arc H — diagnostic probe for the three residual parity gaps.

Writes three CSVs that together characterize the remaining gaps
between Python and NetLogo after Arc D/E/F/G:

  1. scripts/_arc_h_cohort_length_dist.csv — weekly histogram of
     natal-cohort lengths (alive juveniles), for diagnosing the
     16% juv_length gap.

  2. scripts/_arc_h_migrated_vs_resident.csv — for each day, mean
     length of fish migrating that day vs mean length of those staying,
     for diagnosing selection bias.

  3. scripts/_arc_h_outmigrant_cumulative.csv — daily cumulative
     outmigrant count, for diagnosing the +22.7d median-date gap.

Each CSV is merged with the corresponding NetLogo reference (pulled
from insalmo_exampleA_results.csv and FishEventsOut-r1_*.csv) where
available.
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
    start = datetime.date(2011, 4, 1)
    # Run through year 2 spring (enough to capture both cohorts)
    end = (start + datetime.timedelta(days=700)).isoformat()
    model = InSTREAMModel(
        CONFIGS / "example_a.yaml",
        data_dir=FIXTURES / "example_a",
        end_date_override=end,
    )

    juv_stages = [int(LifeStage.FRY), int(LifeStage.PARR)]
    prev_outmig_rep = 0
    prev_outmig_count = 0

    length_dist_rows = []
    mig_resident_rows = []
    outmig_cum_rows = []

    while not model.time_manager.is_done():
        model.step()
        if not model.time_manager.is_day_boundary:
            continue
        date = model.time_manager.current_date.date()
        ts = model.trout_state
        alive = ts.alive_indices()

        if len(alive):
            mask_juv = np.isin(ts.life_history[alive], juv_stages) & (ts.species_idx[alive] == 0)
            juv_idx = alive[mask_juv]
            juv_lens = ts.length[juv_idx]
        else:
            juv_idx = np.array([], dtype=np.int64)
            juv_lens = np.array([], dtype=np.float64)

        # (1) Weekly length distribution — every 7 days emit percentiles
        if len(juv_lens) > 0 and (date.toordinal() % 7) == 0:
            length_dist_rows.append(
                dict(
                    sim_date=date,
                    n=len(juv_lens),
                    mean=float(np.mean(juv_lens)),
                    p10=float(np.percentile(juv_lens, 10)),
                    p50=float(np.percentile(juv_lens, 50)),
                    p90=float(np.percentile(juv_lens, 90)),
                    min=float(np.min(juv_lens)),
                    max=float(np.max(juv_lens)),
                )
            )

        # (2) Migrated today mean length (approximate via delta in _outmigrants)
        outmigs = getattr(model, "_outmigrants", [])
        new_mig_records = outmigs[prev_outmig_count:]
        migrated_today_mean_len = float("nan")
        if new_mig_records:
            migrated_today_mean_len = float(np.mean([m["length"] for m in new_mig_records]))
        resident_mean_len = float(np.mean(juv_lens)) if len(juv_lens) else float("nan")
        if new_mig_records or len(juv_lens) > 0:
            mig_resident_rows.append(
                dict(
                    sim_date=date,
                    n_migrated=len(new_mig_records),
                    migrated_mean_length=migrated_today_mean_len,
                    n_resident_juv=len(juv_lens),
                    resident_juv_mean_length=resident_mean_len,
                )
            )

        # (3) Cumulative outmigrant count (rep-weighted)
        cum_rep = sum(o.get("superind_rep", 1) for o in outmigs)
        today_rep = cum_rep - prev_outmig_rep
        outmig_cum_rows.append(
            dict(
                sim_date=date,
                cum_outmigrants=cum_rep,
                today_outmigrants=today_rep,
            )
        )
        prev_outmig_rep = cum_rep
        prev_outmig_count = len(outmigs)

    pd.DataFrame(length_dist_rows).to_csv(
        PROJECT / "scripts" / "_arc_h_cohort_length_dist.csv", index=False
    )
    pd.DataFrame(mig_resident_rows).to_csv(
        PROJECT / "scripts" / "_arc_h_migrated_vs_resident.csv", index=False
    )
    pd.DataFrame(outmig_cum_rows).to_csv(
        PROJECT / "scripts" / "_arc_h_outmigrant_cumulative.csv", index=False
    )

    print("=== Length distribution snapshots (weekly) ===")
    dist_df = pd.DataFrame(length_dist_rows)
    if not dist_df.empty:
        sampled = dist_df.iloc[::4]  # every 4 weeks
        print(sampled.to_string(index=False))

    print("\n=== Migrated-today vs resident mean length (sampled) ===")
    mr = pd.DataFrame(mig_resident_rows)
    mig_days = mr[mr["n_migrated"] > 0].copy()
    if not mig_days.empty:
        mig_days["delta"] = mig_days["migrated_mean_length"] - mig_days["resident_juv_mean_length"]
        print(
            f"Across {len(mig_days)} migration days:\n"
            f"  migrated_mean_length mean = {mig_days['migrated_mean_length'].mean():.3f}\n"
            f"  resident_mean_length mean = {mig_days['resident_juv_mean_length'].mean():.3f}\n"
            f"  selection-bias delta      = {mig_days['delta'].mean():.3f} cm\n"
            f"  (positive delta ⇒ migrating fish are LARGER than residents, "
            f"leaving small fish behind → lowers residual mean length)"
        )

    print("\n=== Outmigrant cumulative: median date ===")
    oc = pd.DataFrame(outmig_cum_rows)
    total = float(oc["cum_outmigrants"].max())
    if total > 0:
        half = total / 2
        median_row = oc[oc["cum_outmigrants"] >= half].iloc[0]
        print(f"  Python total outmigrants: {total:.0f}")
        print(f"  Median crossed at: {median_row['sim_date']}")
        # Find when NetLogo would have reached the same half-total (41146/2 = 20573)
        nl_target = 41146 / 2
        if total >= nl_target:
            nl_median_row = oc[oc["cum_outmigrants"] >= nl_target].iloc[0]
            print(f"  Python reaches NetLogo's median target at: {nl_median_row['sim_date']}")


if __name__ == "__main__":
    main()
