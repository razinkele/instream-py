"""Arc E growth-drift probe.

Runs example_a for 180 days and emits daily CH-S juvenile mean length
to stdout + CSV. Compares side-by-side with the cached NetLogo 7.3
`CH-S-juve-length` time series at `netlogo-models/insalmo_exampleA_results.csv`
to locate when/where Python's juvenile growth trajectory diverges from
NetLogo's ~32% faster curve.

Hypotheses to test (per v0.30.2 calibration-drift memory):
  1. `cmax_temp_table` interp mismatch — NetLogo may interpolate
     differently (step-wise vs linear) or use different breakpoints
  2. `search_prod` / `drift_conc` unit mismatch
  3. `prey_energy_density` x `max_meal_size` chain in
     `backends/numpy_backend/__init__.py:450-500`
  4. Condition-factor feedback on growth

Usage:
    micromamba run -n shiny python scripts/_probe_arc_e_growth.py
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
NETLOGO_CSV = (
    PROJECT.parent / "netlogo-models" / "insalmo_exampleA_results.csv"
)


def load_netlogo_daily_juv_length() -> pd.DataFrame:
    """Extract daily (or near-daily) CH-S juvenile mean length from NetLogo."""
    df = pd.read_csv(NETLOGO_CSV, skiprows=6, quotechar='"', on_bad_lines="skip")
    df["sim_dt"] = pd.to_datetime(
        df["formatted-sim-time"], format="%m/%d/%Y %H:%M", errors="coerce"
    )
    df["sim_date"] = df["sim_dt"].dt.date
    df["juv_length"] = pd.to_numeric(df["CH-S-juve-length"], errors="coerce")
    df["juv_abund"] = pd.to_numeric(df["CH-S-juve-abund"], errors="coerce")
    # NetLogo emits sub-daily ticks (day/dusk/night/dawn). Take the last
    # tick per sim_date as the end-of-day snapshot.
    daily = (
        df.dropna(subset=["sim_date"])
        .sort_values("sim_dt")
        .groupby("sim_date")
        .last()[["juv_length", "juv_abund"]]
        .reset_index()
    )
    return daily


def run_python_probe(n_days: int = 600) -> pd.DataFrame:
    """Run example_a daily mode and emit daily CH-S juvenile mean length."""
    start = datetime.date(2011, 4, 1)
    end = (start + datetime.timedelta(days=n_days)).isoformat()
    model = InSTREAMModel(
        CONFIGS / "example_a.yaml",
        data_dir=FIXTURES / "example_a",
        end_date_override=end,
    )

    records = []
    while not model.time_manager.is_done():
        model.step()
        if not model.time_manager.is_day_boundary:
            continue
        ts = model.trout_state
        alive = ts.alive_indices()
        # CH-S = Chinook-Spring (species index 0 in example_a)
        juv_mask = (
            (ts.species_idx[alive] == 0)
            & (
                (ts.life_history[alive] == int(LifeStage.FRY))
                | (ts.life_history[alive] == int(LifeStage.PARR))
            )
        )
        juv = alive[juv_mask]
        records.append({
            "sim_date": model.time_manager.current_date.date(),
            "juv_length": float(ts.length[juv].mean()) if len(juv) > 0 else float("nan"),
            "juv_abund": int(len(juv)),
        })

    return pd.DataFrame(records)


def main() -> None:
    print("Loading NetLogo reference ...")
    nl = load_netlogo_daily_juv_length()
    print(f"  NetLogo daily rows: {len(nl)}")

    print("Running Python example_a for 600 days (to capture natal cohort) ...")
    py = run_python_probe(600)
    print(f"  Python daily rows: {len(py)}")

    merged = py.merge(
        nl, on="sim_date", how="left", suffixes=("_py", "_nl")
    )
    merged["length_delta_cm"] = merged["juv_length_py"] - merged["juv_length_nl"]
    merged["length_ratio"] = merged["juv_length_py"] / merged["juv_length_nl"]

    out_csv = PROJECT / "scripts" / "_arc_e_growth_probe.csv"
    merged.to_csv(out_csv, index=False)
    print(f"  Wrote: {out_csv}")

    # Report summary: first divergence, peak drift
    non_null = merged.dropna(subset=["juv_length_py", "juv_length_nl"])
    non_null = non_null[non_null["juv_abund_py"] > 0]
    non_null = non_null[non_null["juv_abund_nl"] > 0]
    print("\nHead (first 10 days with both populations):")
    print(non_null.head(10).to_string(index=False))
    print("\nTail (last 10 days):")
    print(non_null.tail(10).to_string(index=False))

    # Locate first day where Python falls behind by >5%
    first_drift_idx = None
    for _, row in non_null.iterrows():
        if row["length_ratio"] < 0.95:
            first_drift_idx = row["sim_date"]
            break
    print(f"\nFirst day ratio < 0.95: {first_drift_idx}")

    # Aggregate by month
    non_null["month"] = pd.to_datetime(non_null["sim_date"]).dt.to_period("M")
    monthly = non_null.groupby("month").agg(
        py_len=("juv_length_py", "mean"),
        nl_len=("juv_length_nl", "mean"),
        ratio=("length_ratio", "mean"),
    )
    print("\nMonthly juvenile mean length (Python vs NetLogo):")
    print(monthly.round(3).to_string())


if __name__ == "__main__":
    main()
