"""v0.45 probe: diagnose the xfail'd `test_latitudinal_smolt_age_gradient`.

The test runs each Baltic river fixture for 5 years (2011-04-01 to
2016-03-31) and expects the modal age of outmigrating Smolts to match
WGBAST's latitudinal-gradient expectations:

    Tornionjoki, Simojoki (AU1)  -> 3-4 yr smolts (expected 3-4)
    Byskealven (AU2)             -> 2 yr smolts  (expected 2)
    Morrumsan (Southern Baltic)  -> 1-2 yr smolts (expected 2)

v0.43.16 xfail'd it because "All 4 rivers now report modal_age=0".

This probe runs one river at a time and prints:
 - Total outmigrants (by length_category)
 - Smolt age distribution (min/max/mean/mode)
 - Smolt length distribution
 - Per-year smolt count (year-over-year pattern)

Usage:
    micromamba run -n shiny python scripts/_probe_v045_smolt_age.py --river tornionjoki
"""
from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Suppress capacity-full spam
logging.getLogger("salmopy.spawning").setLevel(logging.ERROR)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--river", default="tornionjoki",
        choices=["tornionjoki", "simojoki", "byskealven", "morrumsan"],
    )
    ap.add_argument("--years", type=int, default=5)
    args = ap.parse_args()

    from salmopy.model import SalmopyModel

    REPO = Path(__file__).resolve().parent.parent
    cfg_path = REPO / "configs" / f"example_{args.river}.yaml"
    fixture_dir = REPO / "tests" / "fixtures" / f"example_{args.river}"

    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    cfg["simulation"]["end_date"] = f"{2011 + args.years}-03-31"
    cfg["simulation"]["seed"] = 42

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cfg_out = tmp / "cfg.yaml"
        with open(cfg_out, "w") as f:
            yaml.safe_dump(cfg, f)

        print(f"Running example_{args.river} for {args.years} years...")
        model = SalmopyModel(
            config_path=str(cfg_out),
            data_dir=str(fixture_dir),
            output_dir=str(tmp),
        )
        model.run()

        out_path = tmp / "outmigrants.csv"
        if not out_path.exists():
            print(f"No outmigrants.csv produced — check model run.")
            return

        df = pd.read_csv(out_path)
        print()
        print(f"=" * 60)
        print(f"example_{args.river} — {args.years}-year run, seed=42")
        print(f"=" * 60)
        print(f"Total outmigrant rows: {len(df)}")

        if len(df) == 0:
            print("NO OUTMIGRANTS — calibration drift = juveniles can't outmigrate.")
            return

        print()
        print("--- Outmigrants by length_category ---")
        print(df["length_category"].value_counts().to_string())

        smolts = df[df["length_category"] == "Smolt"]
        print()
        print(f"--- Smolts: {len(smolts)} ---")
        if len(smolts) == 0:
            print("ZERO SMOLTS — fish never promote to smolt stage.")
            print()
            print("Inspecting non-smolt outmigrants as proxy for age/length patterns:")
            print(df[["age_years", "length_cm"]].describe().to_string() if "age_years" in df.columns else df.describe().to_string())
            return

        print()
        print("--- Smolt age distribution (years) ---")
        ages = smolts["age_years"]
        print(f"  min  : {ages.min()}")
        print(f"  max  : {ages.max()}")
        print(f"  mean : {ages.mean():.2f}")
        print(f"  std  : {ages.std():.2f}")
        print(f"  mode : {int(ages.round().mode().iloc[0])}")
        print(f"  histogram:")
        hist = ages.round().astype(int).value_counts().sort_index()
        for age, count in hist.items():
            print(f"    age {age}: {count}")

        print()
        print("--- Smolt length distribution (cm) ---")
        lengths = smolts.get("length_cm", smolts.get("length"))
        if lengths is not None:
            print(f"  min  : {lengths.min():.2f}")
            print(f"  max  : {lengths.max():.2f}")
            print(f"  mean : {lengths.mean():.2f}")
            print(f"  std  : {lengths.std():.2f}")

        print()
        print("--- Smolts per year ---")
        if "date" in smolts.columns:
            smolts_copy = smolts.copy()
            smolts_copy["year"] = pd.to_datetime(smolts_copy["date"]).dt.year
            print(smolts_copy["year"].value_counts().sort_index().to_string())

        print()
        print(f"--- Test expectation ---")
        expected = {"tornionjoki": 4, "simojoki": 3, "byskealven": 2, "morrumsan": 2}[args.river]
        actual = int(ages.round().mode().iloc[0])
        ok = abs(actual - expected) <= 1
        print(f"  expected modal age: {expected}")
        print(f"  actual modal age  : {actual}")
        print(f"  tolerance ±1      : {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
