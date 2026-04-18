"""One-time extract: Lithuanian Baltic coastline from the cached OSM PBF.

Nominatim's country polygon (relation 72596) includes ~20 km of territorial
waters — unusable as a land clip. `natural=coastline` ways in OSM are the
REAL coastline. Rather than hit Overpass (routinely times out on 504),
read them straight from the already-cached app/data/osm/lithuania-latest.osm.pbf.

Output:
  app/data/marineregions/lithuania_coastline.geojson   — MultiLineString
  app/data/marineregions/lithuania_land_real.geojson   — Polygon (land east
    of the coastline within the Klaipėda-Palanga bbox; used to clip
    BalticCoast).
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import osmium
import shapely.wkb as wkblib
from shapely.geometry import LineString, MultiLineString, box
from shapely.ops import linemerge, split, unary_union

CACHE = (
    Path(__file__).resolve().parent.parent
    / "app" / "data" / "marineregions" / "lithuania_coastline.geojson"
)
LAND_CACHE = (
    Path(__file__).resolve().parent.parent
    / "app" / "data" / "marineregions" / "lithuania_land_real.geojson"
)
PBF = (
    Path(__file__).resolve().parent.parent
    / "app" / "data" / "osm" / "lithuania-latest.osm.pbf"
)

# Extraction bbox is deliberately WIDER than the BalticCoast rectangle so
# the OSM coastline fully crosses the north and south edges. split() needs
# the cutter to span the polygon; a line that starts inside the bbox leaves
# the split piece as "bbox minus tiny fragments" (both land + sea merged).
BBOX_LAT_LO, BBOX_LAT_HI = 55.55, 56.20
BBOX_LON_LO, BBOX_LON_HI = 20.60, 21.30

_wkbfab = osmium.geom.WKBFactory()


class CoastlineHandler(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[LineString] = []

    def way(self, w) -> None:
        if w.tags.get("natural") != "coastline":
            return
        # Filter to our bbox by inspecting node coords directly.
        try:
            in_bbox = False
            for n in w.nodes:
                lat = n.location.lat
                lon = n.location.lon
                if (BBOX_LAT_LO <= lat <= BBOX_LAT_HI
                        and BBOX_LON_LO <= lon <= BBOX_LON_HI):
                    in_bbox = True
                    break
            if not in_bbox:
                return
            wkb = _wkbfab.create_linestring(w)
            geom = wkblib.loads(wkb, hex=True)
            if geom.is_valid and geom.length > 0:
                self.lines.append(geom)
        except (osmium.InvalidLocationError, RuntimeError):
            return


def main() -> None:
    if not PBF.exists():
        raise RuntimeError(
            f"PBF not found at {PBF}; regenerate the Baltic fixtures first "
            f"so create_model_osm.ensure_pbf downloads Lithuania."
        )
    print(f"Scanning {PBF.name} for natural=coastline ways...")

    handler = CoastlineHandler()
    handler.apply_file(str(PBF), locations=True)
    print(f"Got {len(handler.lines)} coastline ways in bbox")

    if not handler.lines:
        raise RuntimeError("No coastline ways in bbox (PBF stale?)")

    bbox_geom = box(BBOX_LON_LO, BBOX_LAT_LO, BBOX_LON_HI, BBOX_LAT_HI)
    in_bbox = [g.intersection(bbox_geom) for g in handler.lines]
    in_bbox = [g for g in in_bbox if not g.is_empty and g.length > 0]
    merged = linemerge(MultiLineString(
        [g for g in in_bbox if g.geom_type == "LineString"]
    ))
    if merged.geom_type == "LineString":
        merged = MultiLineString([merged])
    total_km = sum(g.length for g in merged.geoms) * 111
    print(f"After linemerge/clip: {len(merged.geoms)} segments, "
          f"~{total_km:.1f} km of coastline")

    # Coastline open endpoints (e.g. at the LT/LV border) must be extended
    # to the nearest bbox edge, otherwise split() leaves one piece that
    # contains BOTH sea and land. For each endpoint inside the bbox (not
    # already on an edge), drop a perpendicular to the closest edge.
    tol = 1e-4

    def _on_bbox_edge(pt) -> bool:
        x, y = pt
        return (abs(x - BBOX_LON_LO) < tol or abs(x - BBOX_LON_HI) < tol
                or abs(y - BBOX_LAT_LO) < tol or abs(y - BBOX_LAT_HI) < tol)

    def _project_to_edge(pt):
        x, y = pt
        dists = {
            (BBOX_LON_LO, y): x - BBOX_LON_LO,
            (BBOX_LON_HI, y): BBOX_LON_HI - x,
            (x, BBOX_LAT_LO): y - BBOX_LAT_LO,
            (x, BBOX_LAT_HI): BBOX_LAT_HI - y,
        }
        return min(dists, key=dists.get)

    extended = []
    for g in merged.geoms:
        coords = list(g.coords)
        start, end = coords[0], coords[-1]
        if not _on_bbox_edge(start):
            new_start = _project_to_edge(start)
            coords.insert(0, new_start)
            print(f"  extended start {start} → {new_start}")
        if not _on_bbox_edge(end):
            new_end = _project_to_edge(end)
            coords.append(new_end)
            print(f"  extended end   {end} → {new_end}")
        extended.append(LineString(coords))
    merged = MultiLineString(extended)

    gdf = gpd.GeoDataFrame(geometry=list(merged.geoms), crs="EPSG:4326")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(CACHE, driver="GeoJSON")
    print(f"Coastline cached to: {CACHE}")

    # Build land polygon = east side of the bbox split by coastline.
    coast_union = unary_union(list(merged.geoms))
    splits = split(bbox_geom, coast_union)
    print(f"bbox split into {len(splits.geoms)} pieces by coastline")

    land_pieces = [p for p in splits.geoms if p.centroid.x > 21.07]
    if not land_pieces:
        raise RuntimeError("No land pieces identified east of 21.07°E")
    land_geom = unary_union(land_pieces)
    land_km2 = gpd.GeoDataFrame(
        geometry=[land_geom], crs="EPSG:4326"
    ).to_crs("EPSG:3035").geometry.iloc[0].area / 1e6
    print(f"Land polygon area: {land_km2:.1f} km² "
          f"(bbox total ~{(BBOX_LON_HI - BBOX_LON_LO) * 111 * 0.58 * (BBOX_LAT_HI - BBOX_LAT_LO) * 111:.0f} km²)")

    gpd.GeoDataFrame(geometry=[land_geom], crs="EPSG:4326").to_file(
        LAND_CACHE, driver="GeoJSON"
    )
    print(f"Real land polygon cached to: {LAND_CACHE}")


if __name__ == "__main__":
    main()
