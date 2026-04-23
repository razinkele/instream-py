"""Arc G cohort comparison: NetLogo vs Python year-1 natal cohort.

Goal: understand why Python's year-1 cohort vanishes by May while
NetLogo's persists to Sep 30 with ~6 juveniles at 6.23 cm mean length.

Extracts end-of-day snapshots of CH-S-juve-abund + CH-S-juve-length
from both sources for the window 2012-01-15 → 2012-10-01.

Writes scripts/_arc_g_cohort_compare.csv with columns:
    sim_date, py_abund, py_length, nl_abund, nl_length
"""
from __future__ import annotations

from pathlib import Path
import datetime

import numpy as np
import pandas as pd

from salmopy.model import SalmopyModel
from salmopy.state.life_stage import LifeStage

PROJECT = Path(__file__).resolve().parent.parent
CONFIGS = PROJECT / "configs"
FIXTURES = PROJECT / "tests" / "fixtures"
NETLOGO_CSV = PROJECT.parent / "netlogo-models" / "insalmo_exampleA_results.csv"


def load_netlogo_daily() -> pd.DataFrame:
    df = pd.read_csv(NETLOGO_CSV, skiprows=6, quotechar='"', on_bad_lines="skip")
    df["dt"] = pd.to_datetime(df["formatted-sim-time"], format="%m/%d/%Y %H:%M", errors="coerce")
    df["sim_date"] = df["dt"].dt.date
    df["abund"] = pd.to_numeric(df["CH-S-juve-abund"], errors="coerce")
    df["length"] = pd.to_numeric(df["CH-S-juve-length"], errors="coerce")
    # Last tick per day
    daily = df.dropna(subset=["sim_date"]).sort_values("dt").groupby("sim_date").last()[["abund", "length"]]
    return daily.reset_index()


def run_python_daily(n_days: int = 550) -> pd.DataFrame:
    start = datetime.date(2011, 4, 1)
    end = (start + datetime.timedelta(days=n_days)).isoformat()
    model = SalmopyModel(
        CONFIGS / "example_a.yaml",
        data_dir=FIXTURES / "example_a",
        end_date_override=end,
    )

    juv_stages = [int(LifeStage.FRY), int(LifeStage.PARR)]
    rows = []
    while not model.time_manager.is_done():
        model.step()
        if not model.time_manager.is_day_boundary:
            continue
        ts = model.trout_state
        alive = ts.alive_indices()
        if len(alive):
            stages = ts.life_history[alive]
            juv_mask = np.isin(stages, juv_stages) & (ts.species_idx[alive] == 0)
            juv_count = int(juv_mask.sum())
            juv_len = float(ts.length[alive][juv_mask].mean()) if juv_count else 0.0
        else:
            juv_count, juv_len = 0, 0.0
        rows.append({
            "sim_date": model.time_manager.current_date.date(),
            "py_abund": juv_count,
            "py_length": juv_len,
        })
    return pd.DataFrame(rows)


def main() -> None:
    print("Loading NetLogo reference...")
    nl = load_netlogo_daily()
    print(f"  NetLogo daily rows: {len(nl)}")

    print("Running Python 550-day simulation...")
    py = run_python_daily(550)
    print(f"  Python daily rows: {len(py)}")

    merged = py.merge(
        nl.rename(columns={"abund": "nl_abund", "length": "nl_length"}),
        on="sim_date", how="left",
    )
    out = PROJECT / "scripts" / "_arc_g_cohort_compare.csv"
    merged.to_csv(out, index=False)
    print(f"Wrote: {out}")

    # Focus on the natal cohort window
    window = merged[
        (merged["sim_date"] >= datetime.date(2012, 1, 20))
        & (merged["sim_date"] <= datetime.date(2012, 10, 1))
    ]
    # Sample every 15 days
    sampled = window.iloc[::15]
    print("\n=== Year-1 natal cohort, Jan 20 → Oct 1 2012 (every 15 days) ===")
    print(sampled.to_string(index=False))

    # Key milestones
    print("\n=== Milestones ===")
    nl_nonzero = window[window["nl_abund"] > 0]
    py_nonzero = window[window["py_abund"] > 0]
    if not nl_nonzero.empty:
        last_nl = nl_nonzero.iloc[-1]
        print(f"NetLogo last nonzero juv: {last_nl['sim_date']} abund={last_nl['nl_abund']:.0f} length={last_nl['nl_length']:.2f}")
    if not py_nonzero.empty:
        last_py = py_nonzero.iloc[-1]
        print(f"Python  last nonzero juv: {last_py['sim_date']} abund={last_py['py_abund']:.0f} length={last_py['py_length']:.2f}")


if __name__ == "__main__":
    main()
