"""Scaffold WGBAST-assessment-ready Baltic river fixtures from example_baltic.

Generates tests/fixtures/example_{tornionjoki,simojoki,byskealven,morrumsan}/ by:
  1. Copying the example_baltic fixture directory verbatim (keeps Shapefile
     and all 9 Nemunas-basin reach hydrology CSVs).
  2. Rewriting each reach's TimeSeriesInputs.csv with a per-river
     temperature offset and flow multiplier (latitudinal + discharge scaling).
  3. Renaming BalticExample-InitialPopulations.csv and BalticExample-AdultArrivals.csv
     to <RiverStem>Example-*.csv (the Shapefile stays BalticExample — the
     reach-name topology is reused; what makes each fixture a WGBAST
     river is the configured `river_name` + PSPC + latitude in the YAML).

Run: micromamba run -n shiny python scripts/_scaffold_wgbast_rivers.py

See docs/superpowers/plans/2026-04-20-arc-M-to-Q-expanded.md Arc M.
"""
from __future__ import annotations
import shutil
from pathlib import Path
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "tests" / "fixtures" / "example_baltic"


RIVERS = {
    "example_tornionjoki": {
        "stem": "TornionjokiExample",
        "temperature_offset_c": -6.0,   # Gulf of Bothnia ~6C colder than Nemunas
        "mean_flow_multiplier": 0.8,    # Torne ~400 m3/s vs Nemunas ~500
        "river_name": "Tornionjoki",
    },
    "example_simojoki": {
        "stem": "SimojokiExample",
        "temperature_offset_c": -5.5,
        "mean_flow_multiplier": 0.09,   # Simo ~45 m3/s
        "river_name": "Simojoki",
    },
    "example_byskealven": {
        "stem": "ByskealvenExample",
        "temperature_offset_c": -3.5,
        "mean_flow_multiplier": 0.08,   # ~40 m3/s
        "river_name": "Byskealven",
    },
    "example_morrumsan": {
        "stem": "MorrumsanExample",
        "temperature_offset_c": +3.0,   # southern warmer
        "mean_flow_multiplier": 0.05,   # ~25 m3/s
        "river_name": "Morrumsan",
    },
}

# Baltic-basin reaches that receive the temperature/flow offset (all except
# the marine zones, which use their own seasonal static_driver in the
# `marine` config block)
NEMUNAS_FRESHWATER_REACHES = [
    "Nemunas", "Atmata", "Minija", "Sysa", "Skirvyte", "Leite", "Gilija",
]


def scaffold_river(short_name: str, spec: dict) -> None:
    """Build a fixture directory for one WGBAST river."""
    out_dir = ROOT / "tests" / "fixtures" / short_name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    print(f"[{short_name}] copying template...")
    shutil.copytree(TEMPLATE, out_dir)

    # v0.48.0: strip prototype Depths/Vels — wire script reads these from
    # example_baltic directly. Keep PROTO TimeSeriesInputs (Mouth/Lower/
    # Middle/Upper sources for per-river T/Q calibration applied below).
    # Fully drop FULLY_ORPHAN reaches (Lithuanian distributary names that
    # have no WGBAST counterpart) — their TimeSeriesInputs were git-deleted
    # in v0.47.0 (fc08578) and must not be re-introduced by re-runs.
    PROTO = ("Nemunas", "Atmata", "Minija", "Sysa")
    FULLY_ORPHAN = ("Skirvyte", "Leite", "Gilija", "CuronianLagoon")
    for proto in PROTO:
        for suffix in ("Depths", "Vels"):
            (out_dir / f"{proto}-{suffix}.csv").unlink(missing_ok=True)
    for orphan in FULLY_ORPHAN:
        for suffix in ("Depths", "Vels", "TimeSeriesInputs"):
            (out_dir / f"{orphan}-{suffix}.csv").unlink(missing_ok=True)

    # 1. Apply temperature offset + flow multiplier to each freshwater-reach
    #    TimeSeriesInputs.csv
    for reach in NEMUNAS_FRESHWATER_REACHES:
        ts_path = out_dir / f"{reach}-TimeSeriesInputs.csv"
        if not ts_path.exists():
            continue
        ts = pd.read_csv(ts_path, comment=";", header=0)
        ts["temperature"] = (
            ts["temperature"] + spec["temperature_offset_c"]
        ).clip(lower=0.5)
        ts["flow"] = ts["flow"] * spec["mean_flow_multiplier"]
        header = (
            f"; Time series for {spec['river_name']} — {reach} reach\n"
            f"; Adapted from example_baltic Nemunas-basin template with\n"
            f";   temperature_offset: {spec['temperature_offset_c']:+.1f}C\n"
            f";   flow multiplier: {spec['mean_flow_multiplier']}\n"
            f"; Plan: docs/superpowers/plans/2026-04-20-arc-M-to-Q-expanded.md Arc M\n"
        )
        with open(ts_path, "w", encoding="utf-8") as f:
            f.write(header)
            ts.to_csv(f, index=False, lineterminator="\n")

    # 2. Rename InitialPopulations + AdultArrivals so the stem matches the
    #    config. Content is preserved verbatim — all reach names still
    #    reference Nemunas-basin reaches, which matches the shapefile.
    pop_old = out_dir / "BalticExample-InitialPopulations.csv"
    pop_new = out_dir / f"{spec['stem']}-InitialPopulations.csv"
    if pop_old.exists():
        pop_old.rename(pop_new)

    aa_old = out_dir / "BalticExample-AdultArrivals.csv"
    aa_new = out_dir / f"{spec['stem']}-AdultArrivals.csv"
    if aa_old.exists():
        aa_old.rename(aa_new)

    print(f"[{short_name}] scaffolded {len(list(out_dir.iterdir()))} entries")


def main() -> None:
    for short_name, spec in RIVERS.items():
        scaffold_river(short_name, spec)
    print("done.")


if __name__ == "__main__":
    main()
