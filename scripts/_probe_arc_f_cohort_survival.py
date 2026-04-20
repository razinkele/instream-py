"""Arc F natal cohort survival curve.

Context: after Arc E, juvenile mean length @ 2012-09-30 is still 0 —
the natal cohort (emerged Jan 2012) has disappeared by autumn. This
probe instruments model steps to count natal cohort additions,
migrations, and deaths per day, building a daily life-table.

Output: scripts/_arc_f_cohort_survival.csv with columns
  sim_date, natal_alive, natal_migrated_today, natal_died_today
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

JUVE_STAGES = {int(LifeStage.FRY), int(LifeStage.PARR)}


def main() -> None:
    # Run past natal emergence (2012-01-20) + 300 days = through Nov 2012
    start = datetime.date(2011, 4, 1)
    end = (start + datetime.timedelta(days=600)).isoformat()
    model = InSTREAMModel(
        CONFIGS / "example_a.yaml",
        data_dir=FIXTURES / "example_a",
        end_date_override=end,
    )

    # Natal cohort signature: age == 0 AND life_history in juve stages
    prev_alive_mask = np.zeros(model.trout_state.alive.shape, dtype=bool)
    prev_outmig_count = 0
    records = []

    while not model.time_manager.is_done():
        model.step()
        if not model.time_manager.is_day_boundary:
            continue
        ts = model.trout_state
        alive = ts.alive
        is_natal_juv = (
            alive
            & (ts.age == 0)
            & np.isin(ts.life_history, list(JUVE_STAGES))
            & (ts.species_idx == 0)
        )
        # Count rep-weighted fish in natal cohort
        natal_rep = int(ts.superind_rep[is_natal_juv].sum())
        natal_agents = int(is_natal_juv.sum())

        # Who died since last day? slots that were alive & natal yesterday
        # but not alive today
        died_mask = prev_alive_mask & ~alive
        died_natal = int(died_mask.sum())

        # Outmigrated today (rep-weighted)
        outmigs = getattr(model, "_outmigrants", [])
        outmig_total = sum(o.get("superind_rep", 1) for o in outmigs)
        outmig_today = outmig_total - prev_outmig_count

        records.append(
            dict(
                sim_date=model.time_manager.current_date.date(),
                day=len(records) + 1,
                natal_agents=natal_agents,
                natal_rep=natal_rep,
                died_today=died_natal,
                outmig_today=outmig_today,
            )
        )
        prev_alive_mask = alive.copy()
        prev_outmig_count = outmig_total

    df = pd.DataFrame(records)
    out_csv = PROJECT / "scripts" / "_arc_f_cohort_survival.csv"
    df.to_csv(out_csv, index=False)
    print(f"Wrote {len(df)} rows: {out_csv}")

    # Focus on natal emergence window onward (day ~294)
    natal = df[df["day"] >= 280].reset_index(drop=True)
    print("\n=== Natal cohort emergence window (day 280+) ===")
    print(natal.head(20).to_string(index=False))
    print("...")
    print(natal.tail(20).to_string(index=False))

    # Total deaths / migrations in the natal cohort window
    total_died = int(natal["died_today"].sum())
    total_outmig = int(natal["outmig_today"].sum())
    peak_agents = int(natal["natal_agents"].max())
    peak_rep = int(natal["natal_rep"].max())
    print(
        f"\nPeak natal agents: {peak_agents}, peak rep-weighted: {peak_rep}"
    )
    print(f"Total deaths since day 280: {total_died}")
    print(f"Total outmigrations since day 280 (all fish, not just natal): {total_outmig}")


if __name__ == "__main__":
    main()
