"""Rebuild the OSM-input polygon sidecars with unclipped polygons.

The v0.56.4 extenders saved each OSM `natural=water` polygon clipped
to a 100 m buffer around the reach's centerline. That made the
polygons faithful to "what generate_cells used" but tiny on a map
(average ~1,300 m² per fragment = 36 m square — invisible at basin
zoom). The user reported only seeing centerlines + cells, no area
features.

This script regenerates the polygon sidecars from the cached OSM
basin polygons (`tests/fixtures/_osm_cache/minija_*_polygons.json`)
WITHOUT clipping to the centerline buffer. Each polygon retains its
true OSM shape (oxbows, pools, riverbank polygons). Filter logic:

* Tributaries (4 reaches): a polygon is assigned to a tributary if
  it intersects any of that tributary's OSM centerlines (no
  proximity buffer needed since unclipped polygons already extend
  to the river bank). Each polygon goes to exactly one reach
  (the first match). Polygons that don't intersect any centerline
  are dropped — keeps the sidecar focused on river-area features
  rather than every lake/pond in the basin.
* Mainstem (Minija): a polygon is included if it intersects any
  Minija centerline (same logic).

Centerlines remain unchanged — only polygon sidecars are rewritten.

Idempotent: re-runs simply overwrite the polygon sidecars.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import geopandas as gpd
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "example_minija_basin" / "Shapefile"
OSM_CACHE_DIR = ROOT / "tests" / "fixtures" / "_osm_cache"
TARGET_CRS_EPSG = 3035  # match the rest of the fixture (LAEA Europe)
UTM_EPSG = 32634        # for meter-accurate buffering
PROXIMITY_BUFFER_M = 100.0  # match v0.56.4 extender's centerline-buffer width

# Tributary names — matches `_extend_minija_with_tributaries.py`
TRIBUTARIES = ["Babrungas", "Salantas", "Salpe", "Veivirzas"]


def load_basin_polygons() -> "gpd.GeoDataFrame":
    """Load the cached basin OSM water polygons (1351 features in WGS84)."""
    cache = OSM_CACHE_DIR / "minija_tributaries_polygons.json"
    data = json.loads(cache.read_text(encoding="utf-8"))
    geoms = []
    for w in data:
        try:
            g = shape(w["geometry"])
            if g.is_valid and not g.is_empty:
                geoms.append(g)
        except Exception:
            continue
    gdf = gpd.GeoDataFrame(geometry=geoms, crs="EPSG:4326")
    log.info("Loaded %d basin OSM water polygons from cache", len(gdf))
    return gdf


def _buffer_in_utm(geom_wgs84, buffer_m: float):
    """Buffer a WGS84 geometry by N meters via a round-trip through UTM."""
    g_utm = (
        gpd.GeoSeries([geom_wgs84], crs="EPSG:4326").to_crs(epsg=UTM_EPSG).iloc[0]
    )
    g_utm_buf = g_utm.buffer(buffer_m)
    return (
        gpd.GeoSeries([g_utm_buf], crs=f"EPSG:{UTM_EPSG}")
        .to_crs("EPSG:4326")
        .iloc[0]
    )


def load_centerlines_per_tributary() -> dict:
    """Read the existing tributary centerlines sidecar; group by REACH_NAME
    and pre-buffer each by PROXIMITY_BUFFER_M for intersection tests."""
    cl_path = FIXTURE_DIR / "MinijaBasinExample-tributaries-osm-centerlines.shp"
    cl = gpd.read_file(cl_path).to_crs("EPSG:4326")
    out: dict = {}
    for name, grp in cl.groupby("REACH_NAME"):
        u = grp.geometry.union_all()
        out[str(name)] = _buffer_in_utm(u, PROXIMITY_BUFFER_M)
    log.info("Tributary centerline buffers: %s", list(out.keys()))
    return out


def load_minija_centerline_union():
    """Read the mainstem centerlines sidecar and return its
    ``PROXIMITY_BUFFER_M``-buffered union."""
    cl_path = FIXTURE_DIR / "MinijaBasinExample-mainstem-osm-centerlines.shp"
    cl = gpd.read_file(cl_path).to_crs("EPSG:4326")
    log.info("Mainstem centerlines: %d features", len(cl))
    return _buffer_in_utm(cl.geometry.union_all(), PROXIMITY_BUFFER_M)


def _write_polygons(rows: list, out_path: Path) -> None:
    if not rows:
        log.warning("No rows to write for %s", out_path.name)
        return
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").to_crs(
        epsg=TARGET_CRS_EPSG
    )
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        stale = out_path.with_suffix(ext)
        if stale.exists():
            stale.unlink()
    gdf.to_file(out_path, driver="ESRI Shapefile")
    log.info("Wrote %s (%d polygons)", out_path.relative_to(ROOT), len(gdf))


def regenerate_tributaries(polys: gpd.GeoDataFrame, centerlines: dict) -> None:
    """Assign each polygon to the FIRST tributary whose centerline it
    intersects (deterministic by TRIBUTARIES order). Polygons that touch
    no centerline are dropped.
    """
    rows = []
    counts = {t: 0 for t in TRIBUTARIES}
    for _, prow in polys.iterrows():
        g = prow.geometry
        for trib in TRIBUTARIES:
            cl = centerlines.get(trib)
            if cl is None:
                continue
            if g.intersects(cl):
                rows.append({"REACH_NAME": trib, "geometry": g})
                counts[trib] += 1
                break
    log.info("Tributary polygon assignment: %s", counts)
    out = FIXTURE_DIR / "MinijaBasinExample-tributaries-osm-polygons.shp"
    _write_polygons(rows, out)


def regenerate_mainstem(polys: gpd.GeoDataFrame, minija_cl) -> None:
    rows = []
    for _, prow in polys.iterrows():
        if prow.geometry.intersects(minija_cl):
            rows.append({"REACH_NAME": "Minija", "geometry": prow.geometry})
    log.info("Mainstem polygons that intersect Minija centerline: %d", len(rows))
    out = FIXTURE_DIR / "MinijaBasinExample-mainstem-osm-polygons.shp"
    _write_polygons(rows, out)


def main() -> None:
    polys = load_basin_polygons()
    centerlines = load_centerlines_per_tributary()
    minija_cl = load_minija_centerline_union()
    regenerate_tributaries(polys, centerlines)
    regenerate_mainstem(polys, minija_cl)
    log.info("OK: polygon sidecars regenerated with unclipped OSM geometry.")


if __name__ == "__main__":
    main()
