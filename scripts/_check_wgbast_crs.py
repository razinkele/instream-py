"""Check the CRS of all WGBAST and example_baltic shapefiles."""
from pathlib import Path
import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]

for fixture in ["example_baltic", "example_tornionjoki", "example_simojoki",
                "example_byskealven", "example_morrumsan"]:
    shps = list((ROOT / "tests/fixtures" / fixture / "Shapefile").glob("*.shp"))
    if not shps:
        print(f"{fixture}: no shapefile")
        continue
    gdf = gpd.read_file(shps[0])
    print(f"{fixture}: CRS={gdf.crs}, n_cells={len(gdf)}, "
          f"bbox={tuple(round(b, 2) for b in gdf.total_bounds)}")
