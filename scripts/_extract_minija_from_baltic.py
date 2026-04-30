"""Extract Minija + downstream reaches from example_baltic into example_minija_basin.

Replaces the v0.54.0 synthetic-geometry fixture (waypoints + buffered
centerline) with a faithful extraction from example_baltic, which uses
real OSM-fetched polygon geometry from the v0.51.0 work.

Reach selection (3 reaches forming the Minija anadromous pathway):
  Minija          425 cells — main freshwater stem (real OSM polygon)
  CuronianLagoon  120 cells — downstream lagoon (where Minija mouths)
  BalticCoast      97 cells — open Baltic, marine habitat for ocean phase

Total: 642 cells — much smaller than the v0.54.0 synthetic fixture
(3979 cells) but faithful to real Minija geography.

Side effects: rewrites
  tests/fixtures/example_minija_basin/Shapefile/MinijaBasinExample.{shp,dbf,prj,shx,cpg}
  tests/fixtures/example_minija_basin/{Minija,CuronianLagoon,BalticCoast}-{Depths,Vels,TimeSeriesInputs}.csv
  tests/fixtures/example_minija_basin/MinijaBasinExample-InitialPopulations.csv
  tests/fixtures/example_minija_basin/MinijaBasinExample-AdultArrivals.csv

Removes stale files from the v0.54.0 fixture (Mouth/Lower/Middle/Upper-*.csv
and the inherited Atmata/Nemunas/Sysa-* CSVs that came from byskealven copy).
"""
from __future__ import annotations
from pathlib import Path
import shutil
import csv
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "tests" / "fixtures" / "example_baltic"
DST_DIR = ROOT / "tests" / "fixtures" / "example_minija_basin"

# Reaches to keep — Minija anadromous pathway
KEEP_REACHES = ("Minija", "CuronianLagoon", "BalticCoast")


def main() -> None:
    # 1. Extract shapefile subset
    print(f"Reading {SRC_DIR.name} shapefile...")
    g = gpd.read_file(SRC_DIR / "Shapefile" / "BalticExample.shp")
    sub = g[g["REACH_NAME"].isin(KEEP_REACHES)].copy()
    counts = sub["REACH_NAME"].value_counts().to_dict()
    print(f"Extracted {len(sub)} cells:")
    for r in KEEP_REACHES:
        print(f"  {r:>15}: {counts.get(r, 0):>4} cells")

    # 2. Wipe stale files in dst
    print(f"\nWiping stale files in {DST_DIR.name}/")
    for f in DST_DIR.glob("*.csv"):
        f.unlink()
    for f in (DST_DIR / "Shapefile").glob("*"):
        f.unlink()

    # 3. Write new shapefile
    out_shp = DST_DIR / "Shapefile" / "MinijaBasinExample.shp"
    sub.to_file(out_shp, driver="ESRI Shapefile")
    print(f"Wrote {out_shp.relative_to(ROOT)} ({len(sub)} cells, CRS {sub.crs})")

    # 4. Copy hydraulic CSVs for the 3 reaches
    print(f"\nCopying hydraulic CSVs:")
    for reach in KEEP_REACHES:
        for suffix in ("Depths", "Vels", "TimeSeriesInputs"):
            src = SRC_DIR / f"{reach}-{suffix}.csv"
            if src.exists():
                dst = DST_DIR / f"{reach}-{suffix}.csv"
                shutil.copy2(src, dst)
                print(f"  {src.name}  ({src.stat().st_size:>7} B)")

    # 5. Build InitialPopulations + AdultArrivals filtered to Minija
    # (CuronianLagoon and BalticCoast aren't natal reaches → no initial fish there)
    print(f"\nFiltering population/arrival CSVs to natal reaches:")
    for csv_name in (
        "BalticExample-InitialPopulations.csv",
        "BalticExample-AdultArrivals.csv",
    ):
        src = SRC_DIR / csv_name
        dst_name = csv_name.replace("BalticExample", "MinijaBasinExample")
        dst = DST_DIR / dst_name
        with open(src, encoding="utf-8") as f_in:
            lines = f_in.readlines()
        # Preserve comment header lines (start with ';'), filter data rows
        comments = [ln for ln in lines if ln.startswith(";") or ln.strip() == ""]
        data_lines = [ln for ln in lines if not ln.startswith(";") and ln.strip()]
        if not data_lines:
            print(f"  {src.name}: no data rows")
            continue
        # First non-comment line might be the column header (no Reach in row[1] like "Species,Reach,Age,...")
        # InitialPopulations: Species,Reach,Age,Number,Length min,Length mode,Length max
        # AdultArrivals: Year,Species,Reach,Number,...
        # Both have Reach as a column; filter where Reach == "Minija"
        # We don't have a header row in the data — comments specify column order.
        # Assume index of "Reach" column based on file:
        if "InitialPopulations" in csv_name:
            reach_col_idx = 1   # Species,Reach,Age,...
        else:
            reach_col_idx = 2   # Year,Species,Reach,...
        kept = []
        for ln in data_lines:
            row = ln.strip().split(",")
            if len(row) > reach_col_idx and row[reach_col_idx] == "Minija":
                kept.append(ln)
        with open(dst, "w", encoding="utf-8", newline="") as f_out:
            f_out.writelines(comments)
            f_out.writelines(kept)
        print(f"  {dst.name}: {len(kept)} Minija rows (was {len(data_lines)} total)")

    print(f"\nOK: rebuilt {DST_DIR.name} from example_baltic Minija + downstream.")


if __name__ == "__main__":
    main()
