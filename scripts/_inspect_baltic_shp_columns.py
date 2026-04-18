"""Inspect the Baltic fixture shapefile columns + value ranges."""
from pathlib import Path

import geopandas as gpd

SHP = (
    Path(__file__).resolve().parent.parent
    / "tests" / "fixtures" / "example_baltic" / "Shapefile" / "BalticExample.shp"
)


def main() -> None:
    gdf = gpd.read_file(str(SHP))
    print(f"Columns: {list(gdf.columns)}")
    print(f"dtypes:\n{gdf.dtypes}")
    print()
    for col in gdf.columns:
        if col == "geometry":
            continue
        s = gdf[col]
        if s.dtype.kind in "iufc":
            print(f"  {col:<20} min={s.min():>12}  max={s.max():>12}  "
                  f"mean={s.mean():>12.4f}  nonzero={int((s != 0).sum())}/{len(s)}")
        else:
            uniq = s.nunique()
            print(f"  {col:<20} {uniq} unique values, e.g. {s.iloc[0]!r}")


if __name__ == "__main__":
    main()
