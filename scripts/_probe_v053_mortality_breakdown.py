"""v0.53 probe: per-source mortality breakdown for example_tornionjoki PARR.

The v0.52.2 fixes deliver natal cohorts (11k+ PARR peak), but the 5-year
probe in scripts/_v053_smolt_verification.log shows summer parr survival of
~0.3% (vs real ~30-50%/yr). The xfail message blames mort_high_temp_T*, but
those params (T1=28/T9=24) cannot be triggered at subarctic temps.

This probe enables the mortality-breakdown hook in
``ModelEnvironmentMixin._do_survival`` (v0.53), runs the simulation, and
aggregates per-source daily survival across PARR by season:

  Summer  : May 1 – Sep 30
  Winter  : Oct 1 – Apr 30

For each source (ht, str, cond, fp, tp) we report:
  * mean daily survival probability (PARR-weighted by superind_rep)
  * implied annualized survival assuming 365 daily evaluations
  * cumulative summer / winter survival over the season

This gives the smoking gun: whichever source has lowest seasonal survival
is the dominant kill mechanism. ``cumulative summer survival`` for the
incumbent must match the observed 0.3% (Mar→Sep 2013) or the diagnostic is
incomplete.

Usage:
    micromamba run -n shiny python scripts/_probe_v053_mortality_breakdown.py --years 3
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


SOURCES = ["ht", "str", "cond", "fp", "tp"]
SOURCE_LABELS = {
    "ht": "high-temp",
    "str": "stranding",
    "cond": "condition (starvation)",
    "fp": "fish predation",
    "tp": "terrestrial predation",
}


def _is_summer(d: _dt.date) -> bool:
    return 5 <= d.month <= 9


def _agg_parr(record, parr_value: int):
    """Per-source PARR-weighted mean survival from one daily record.

    Returns (n_parr_super, mean_survival_dict_or_None).
    """
    is_parr = record["life_history"] == parr_value
    n_super = int(is_parr.sum())
    if n_super == 0:
        return 0, None
    weights = record["superind_rep"][is_parr].astype(np.float64)
    total_w = float(weights.sum())
    if total_w <= 0:
        return n_super, None
    means = {}
    for src in SOURCES:
        s = record["components"][src][is_parr]
        means[src] = float((s * weights).sum() / total_w)
    return n_super, means


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=3,
                    help="Sim length in years (default 3 for faster iteration; "
                         "5 matches the xfail'd test_latitudinal_smolt_age_gradient).")
    ap.add_argument("--config", type=str,
                    default="configs/example_tornionjoki.yaml")
    ap.add_argument("--data-dir", type=str,
                    default="tests/fixtures/example_tornionjoki")
    args = ap.parse_args()

    from salmopy.model import SalmopyModel
    from salmopy.state.life_stage import LifeStage

    parr_value = LifeStage.PARR.value

    start = _dt.date(2011, 4, 1)
    end = (start + _dt.timedelta(days=365 * args.years)).isoformat()
    print(f"Running {Path(args.config).stem} for {args.years} years (end {end})...")

    model = SalmopyModel(
        config_path=str(ROOT / args.config),
        data_dir=str(ROOT / args.data_dir),
        end_date_override=end,
    )
    model.rng = np.random.default_rng(42)

    # Enable v0.53 breakdown hook — see _do_survival in model_environment.py
    model._mortality_breakdown_log = []

    while not model.time_manager.is_done():
        model.step()

    log = model._mortality_breakdown_log
    if not log:
        print("(no breakdown records — instrumentation not engaged)")
        return

    # Aggregate by season-year
    bins = {}  # (season, year) -> {n_days, total_super, sum_per_source}
    monthly = {}  # (year, month) -> same shape, for finer-grained view

    for rec in log:
        date = rec["date"]
        date = date.date() if hasattr(date, "date") else date
        n_super, means = _agg_parr(rec, parr_value)
        if means is None:
            continue
        season = "summer" if _is_summer(date) else "winter"
        key = (season, date.year if season == "summer" else
               (date.year if date.month >= 10 else date.year - 1))
        bin_ = bins.setdefault(key, {
            "n_days": 0, "n_super_total": 0,
            "sum_per_source": {s: 0.0 for s in SOURCES},
        })
        bin_["n_days"] += 1
        bin_["n_super_total"] += n_super
        for src in SOURCES:
            bin_["sum_per_source"][src] += means[src]

        mkey = (date.year, date.month)
        mbin = monthly.setdefault(mkey, {
            "n_days": 0, "n_super_total": 0,
            "sum_per_source": {s: 0.0 for s in SOURCES},
        })
        mbin["n_days"] += 1
        mbin["n_super_total"] += n_super
        for src in SOURCES:
            mbin["sum_per_source"][src] += means[src]

    print()
    print("=== SEASON x YEAR — mean daily survival across PARR (super-weighted) ===")
    print(f"{'season':<8} {'year':>5} {'days':>5} {'avg_PARR':>10} "
          + " ".join(f"{SOURCE_LABELS[s][:14]:>15}" for s in SOURCES)
          + f" {'cum_combined':>14}")
    print("-" * 130)
    for key in sorted(bins):
        season, year = key
        b = bins[key]
        if b["n_days"] == 0:
            continue
        avg_parr = b["n_super_total"] / b["n_days"]
        means = {s: b["sum_per_source"][s] / b["n_days"] for s in SOURCES}
        cum_combined = 1.0
        for s in SOURCES:
            cum_combined *= means[s] ** b["n_days"]
        print(f"{season:<8} {year:>5} {b['n_days']:>5} {avg_parr:>10,.0f} "
              + " ".join(f"{means[s]:>15.6f}" for s in SOURCES)
              + f" {cum_combined:>14.4e}")

    print()
    print("=== INTERPRETATION ===")
    print("  * 'mean daily survival' is averaged across days in the bin.")
    print("    Lower = bigger killer. 1.000 = no kills from that source.")
    print("  * 'cum_combined' = product of all 5 sources^n_days.")
    print("    Should match the observed PARR collapse if the kernel is the")
    print("    sole sink (excludes ED-starvation and migration).")
    print("  * Whichever column drops below ~0.99 is the dominant suspect.")
    print()
    print("=== BY MONTH (PARR-weighted mean daily survival) ===")
    print(f"{'year':>5} {'mo':>3} {'days':>5} {'avg_PARR':>10} "
          + " ".join(f"{SOURCE_LABELS[s][:14]:>15}" for s in SOURCES))
    print("-" * 120)
    for key in sorted(monthly):
        year, month = key
        m = monthly[key]
        if m["n_days"] == 0:
            continue
        avg_parr = m["n_super_total"] / m["n_days"]
        means = {s: m["sum_per_source"][s] / m["n_days"] for s in SOURCES}
        print(f"{year:>5} {month:>3} {m['n_days']:>5} {avg_parr:>10,.0f} "
              + " ".join(f"{means[s]:>15.6f}" for s in SOURCES))


if __name__ == "__main__":
    main()
