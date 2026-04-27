"""Smoke probe for the v0.51.0 example_baltic fixture with Danė + KlaipedaStrait.

Asserts 8 invariants on the merged fixture before commit. Run as:
    micromamba run -n shiny python scripts/_probe_baltic_with_dane.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "example_baltic"
SHP = FIXTURE_DIR / "Shapefile" / "BalticExample.shp"
YAML_PATH = ROOT / "configs" / "example_baltic.yaml"
ARRIVALS = FIXTURE_DIR / "BalticExample-AdultArrivals.csv"

EXPECTED_REACHES = {
    "Nemunas", "Atmata", "Minija", "Sysa", "Skirvyte", "Leite",
    "Gilija", "CuronianLagoon", "BalticCoast",
    "Dane_Upper", "Dane_Middle", "Dane_Lower", "Dane_Mouth", "KlaipedaStrait",
}
SEA_SINK_JUNCTION = 6


def _check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    msg = f"[{name}] {status}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return ok


def main() -> int:
    cfg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    reaches = cfg.get("reaches", {})

    a1 = _check(
        "1/8 YAML 14 reaches",
        set(reaches.keys()) == EXPECTED_REACHES,
        f"got {sorted(reaches.keys())}",
    )

    csvs_ok = True
    for r in EXPECTED_REACHES:
        for suffix in ("Depths", "Vels", "TimeSeriesInputs"):
            f = FIXTURE_DIR / f"{r}-{suffix}.csv"
            if not f.exists():
                csvs_ok = False
                print(f"   missing: {f.name}")
    a2 = _check("2/8 CSVs present (3 per reach)", csvs_ok)

    sys.path.insert(0, str(ROOT / "src"))
    try:
        from salmopy.io.hydraulics_reader import _parse_hydraulic_csv
        load_ok = True
        for r in EXPECTED_REACHES:
            for suffix in ("Depths", "Vels"):
                f = FIXTURE_DIR / f"{r}-{suffix}.csv"
                try:
                    # _parse_hydraulic_csv returns (flows, values) tuple,
                    # NOT a DataFrame. values shape: (n_cells, n_flows).
                    flows, values = _parse_hydraulic_csv(f)
                    if values.shape[1] != 10:
                        load_ok = False
                        print(f"   {f.name} has {values.shape[1]} flow cols, expected 10")
                except Exception as exc:
                    load_ok = False
                    print(f"   {f.name} parse error: {type(exc).__name__}: {exc}")
        a3 = _check("3/8 per-cell CSVs load via _parse_hydraulic_csv", load_ok)
    except ImportError as exc:
        a3 = _check("3/8 per-cell CSVs load via _parse_hydraulic_csv", False,
                    f"import failed: {exc}")

    upstreams = {r["upstream_junction"] for r in reaches.values()}
    downstreams = {r["downstream_junction"] for r in reaches.values()}
    sinks = downstreams - upstreams
    a4 = _check(
        "4/8 junction graph: unique sea sink",
        sinks == {SEA_SINK_JUNCTION},
        f"sinks={sorted(sinks)}, expected={SEA_SINK_JUNCTION}",
    )

    gdf = gpd.read_file(str(SHP))
    a5 = _check(
        "5/8 shapefile cell count >= existing baseline floor",
        len(gdf) >= 1500,
        f"got {len(gdf)} cells (expected >= 1500; ~2200-2400 typical)",
    )

    actual_reaches = set(gdf["REACH_NAME"].unique())
    a6 = _check(
        "6/8 shapefile REACH_NAME == EXPECTED_REACHES",
        actual_reaches == EXPECTED_REACHES,
        f"missing={EXPECTED_REACHES - actual_reaches}, extra={actual_reaches - EXPECTED_REACHES}",
    )

    per_reach_min = {
        r: 30 for r in ("Dane_Upper", "Dane_Middle", "Dane_Lower", "Dane_Mouth")
    }
    per_reach_min["KlaipedaStrait"] = 1  # single hand-written polygon
    a7_ok = True
    for r, min_cells in per_reach_min.items():
        n = int((gdf["REACH_NAME"] == r).sum())
        if n < min_cells:
            a7_ok = False
            print(f"   {r}: {n} cells < {min_cells} minimum")
    a7 = _check("7/8 per-reach minimum cell counts", a7_ok)

    a8_ok = True
    with ARRIVALS.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith(";") or not line.strip():
                continue
            cols = line.split(",")
            if len(cols) >= 3:
                reach = cols[2].strip()
                if reach not in EXPECTED_REACHES:
                    a8_ok = False
                    print(f"   AdultArrivals row references unknown reach: {reach!r}")
    a8 = _check("8/8 AdultArrivals reach names ⊆ EXPECTED_REACHES", a8_ok)

    all_ok = all([a1, a2, a3, a4, a5, a6, a7, a8])
    print()
    print("=" * 60)
    print(f"OVERALL: {'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
