"""One-time fetch: Curonian Spit (OSM relation 309762) polygon from Nominatim.

Cached to app/data/marineregions/curonian_spit.geojson. Used to clip the
BalticCoast reach polygon so the coast doesn't cross land.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import shape

CACHE = (
    Path(__file__).resolve().parent.parent
    / "app" / "data" / "marineregions" / "curonian_spit.geojson"
)

URL = "https://nominatim.openstreetmap.org/search.php"
PARAMS = {
    "q": "Curonian Spit",
    "format": "json",
    "polygon_geojson": "1",
    "limit": "1",
}
HEADERS = {"User-Agent": "Salmopy-py/0.30.0 (research)"}


def main() -> None:
    print(f"Fetching from {URL} ...")
    resp = requests.get(URL, params=PARAMS, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    hit = data[0]
    print(f"Matched: {hit.get('display_name', '?')}")
    print(f"OSM type={hit.get('osm_type')} id={hit.get('osm_id')}")
    print(f"Bbox: {hit.get('boundingbox')}")
    geom_json = hit.get("geojson")
    print(f"Geometry type: {geom_json.get('type')}")

    geom = shape(geom_json)
    if not geom.is_valid:
        from shapely.validation import make_valid
        geom = make_valid(geom)

    gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
    area_km2 = gdf.to_crs("EPSG:32634").geometry.iloc[0].area / 1e6
    print(f"Area: {area_km2:.0f} km² (real ~180 km² for the ~98 km × 0.4-4 km spit)")

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(CACHE, driver="GeoJSON")
    print(f"Cached to: {CACHE}")


if __name__ == "__main__":
    main()
