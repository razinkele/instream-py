"""Replace example_minija_basin's Minija reach with full-OSM 20m cells.

v0.56.2 added upper Minija cells (above 55.75°N) at 30 m resolution,
appending to the baltic-derived ~50 m lower Minija. The fixture had
mixed cell sizes across the same reach.

v0.56.3 unifies the Minija reach at 20 m resolution by replacing ALL
Minija cells with OSM-fetched polyline-buffer cells. Tributaries are
also bumped to 20 m (in `_extend_minija_with_tributaries.py`).
Atmata / CuronianLagoon / BalticCoast keep their existing baltic-
derived resolution — the user's "rest of example resolution intact"
contract.

Implementation note: cell generation is CHUNKED per OSM polyline
because a single generate_cells call over the full ~200 km of
Minija polylines at 20 m hex cells produces a ~6M-cell raw grid
(bbox ~57×62 km / cell area). Per-polyline chunking shrinks each
call's bbox to a few km, so each completes in seconds.

Idempotent: re-runs detect and remove ALL Minija cells before regen.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import LineString, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

from modules.create_model_grid import generate_cells  # noqa: E402
from modules.create_model_utils import detect_utm_epsg  # noqa: E402
from _wire_wgbast_physical_configs import _expand_per_cell_csv  # noqa: E402

OSM_CACHE = ROOT / "tests" / "fixtures" / "_osm_cache" / "minija_mainstem.json"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "example_minija_basin"
SHP_PATH = FIXTURE_DIR / "Shapefile" / "MinijaBasinExample.shp"

# Minija basin bbox — covers full river from mouth (55.35°N) to source (55.93°N)
MINIJA_BBOX = (55.30, 21.10, 56.00, 22.10)  # S, W, N, E

# v0.56.3: 20 m cells across all freshwater (matches tributary refactor).
CELL_SIZE_M = 20.0
BUFFER_FACTOR = 0.5
FRAC_SPAWN_MAINSTEM = 0.12  # was 0.12 in baltic-extracted Minija (matches existing)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]


def fetch_minija_polylines(refresh: bool = False) -> list[LineString]:
    """Fetch (or load cached) Minija main-stem polylines."""
    if OSM_CACHE.exists() and not refresh:
        log.info("Loading cached Minija polylines from %s", OSM_CACHE.relative_to(ROOT))
        data = json.loads(OSM_CACHE.read_text(encoding="utf-8"))
        return [shape(w["geometry"]) for w in data
                if shape(w["geometry"]).is_valid]

    s, w, n, e = MINIJA_BBOX
    query = (
        f'[out:json][timeout:180];\n'
        f'way["waterway"~"^(river|stream)$"]["name"="Minija"]'
        f'({s:.4f},{w:.4f},{n:.4f},{e:.4f});\n'
        f'out geom;'
    )
    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            log.info("Querying %s for Minija polylines...", endpoint)
            resp = requests.post(endpoint, data={"data": query}, timeout=200)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as exc:
            log.warning("Endpoint failed: %s", exc)
            last_err = exc
    else:
        raise RuntimeError(f"All Overpass endpoints failed: {last_err}")

    ways = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        coords = [(n["lon"], n["lat"]) for n in el.get("geometry", [])]
        if len(coords) < 2:
            continue
        ways.append({
            "id": el["id"],
            "tags": el.get("tags", {}),
            "geometry": mapping(LineString(coords)),
        })
    log.info("Extracted %d Minija polylines", len(ways))
    OSM_CACHE.parent.mkdir(parents=True, exist_ok=True)
    OSM_CACHE.write_text(json.dumps(ways, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("Cached to %s", OSM_CACHE.relative_to(ROOT))

    return [shape(w["geometry"]) for w in ways]


def _load_minija_polygons_near_centerline(
    polylines: list[LineString],
    proximity_m: float = 100.0,
    utm_epsg: int = 32634,
) -> list:
    """Load OSM water polygons (basin-wide cache from tributary fetch)
    that intersect a buffered Minija centerline. v0.56.4 union-mode.
    """
    poly_cache = ROOT / "tests/fixtures/_osm_cache/minija_tributaries_polygons.json"
    if not poly_cache.exists():
        log.warning("Polygon cache missing: %s — Minija will use buffer-only.",
                    poly_cache)
        return []
    data = json.loads(poly_cache.read_text(encoding="utf-8"))
    if not data:
        return []
    poly_geoms = []
    for w in data:
        try:
            poly_geoms.append(shape(w["geometry"]))
        except Exception:
            continue
    poly_gdf = gpd.GeoDataFrame(geometry=poly_geoms, crs="EPSG:4326")
    cl_gdf = gpd.GeoDataFrame(geometry=polylines, crs="EPSG:4326").to_crs(epsg=utm_epsg)
    centerline_buffer = cl_gdf.geometry.union_all().buffer(proximity_m)
    poly_utm = poly_gdf.to_crs(epsg=utm_epsg)
    keep = poly_utm[poly_utm.intersects(centerline_buffer)].copy()
    if keep.empty:
        return []
    keep["geometry"] = keep.geometry.intersection(centerline_buffer)
    keep = keep[~keep.is_empty & keep.is_valid].copy()
    log.info("[Minija] %d water polygons near centerline (UNION mode)", len(keep))
    return list(keep.to_crs("EPSG:4326").geometry)


def _generate_cells_per_polyline(
    polylines: list[LineString],
    polygons: list,  # NEW: water polygons to UNION with each polyline's buffer
    target_crs,
) -> "gpd.GeoDataFrame":
    """Generate Minija hex cells one OSM polyline at a time.

    Single-call mode (all polylines together) is too slow at 20 m cells
    because the union bbox spans the whole basin (~57×62 km), creating
    a ~6M-cell raw hex grid before filter. Per-polyline calls keep each
    bbox tight (a few km), so each call returns in seconds.

    v0.56.4 UNION mode: each polyline's buffer is unioned with the
    nearby water polygons (filtered by proximity to the polyline's
    own bbox) before cell generation. This ensures cells fill the
    real OSM polygon shapes (not just the centerline buffer).
    """
    # Index polygons by bounding box for fast per-polyline filtering
    poly_gdf_4326 = (
        gpd.GeoDataFrame(geometry=polygons, crs="EPSG:4326")
        if polygons else None
    )
    pieces: list[gpd.GeoDataFrame] = []
    for i, line in enumerate(polylines, start=1):
        # For this polyline, find nearby water polygons (within ~50m of bbox)
        line_segments: list = [line]
        if poly_gdf_4326 is not None and not poly_gdf_4326.empty:
            from shapely.geometry import box
            line_bbox_buffered = box(*line.buffer(0.001).bounds)  # ~100m at this lat
            nearby = poly_gdf_4326[poly_gdf_4326.intersects(line_bbox_buffered)]
            if not nearby.empty:
                line_segments = list(nearby.geometry) + [line]
        reach_segments = {
            "Minija": {
                "segments": line_segments,
                "frac_spawn": FRAC_SPAWN_MAINSTEM,
            },
        }
        try:
            piece = generate_cells(
                reach_segments=reach_segments,
                cell_size=CELL_SIZE_M,
                cell_shape="hexagonal",
                buffer_factor=BUFFER_FACTOR,
            )
        except Exception as exc:
            log.warning("polyline %d/%d skipped (%s)", i, len(polylines), exc)
            continue
        if piece.empty:
            continue
        pieces.append(piece.to_crs(target_crs))
        if i % 5 == 0 or i == len(polylines):
            log.info("  ... %d/%d polylines processed (%d cells so far)",
                     i, len(polylines), sum(len(p) for p in pieces))
    if not pieces:
        return gpd.GeoDataFrame(columns=["cell_id", "reach_name", "geometry"], crs=target_crs)
    combined = pd.concat(pieces, ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=target_crs)
    # Re-number cell_ids globally to avoid collisions across pieces
    combined["cell_id"] = [f"MJ-{i:06d}" for i in range(1, len(combined) + 1)]
    return combined


def write_minija_osm_sidecar(
    shp_dir: Path, polylines: list, polygons: list, target_crs,
    polygon_sidecar_name: str = "MinijaBasinExample-mainstem-osm-polygons.shp",
    centerline_sidecar_name: str = "MinijaBasinExample-mainstem-osm-centerlines.shp",
) -> None:
    """Write the Minija main-stem OSM input geometry as TWO sidecar
    shapefiles (polygons + centerlines). Shapefile format requires
    uniform geometry type per file.

    v0.56.4: separate per-extender files (no cross-extender merging).
    The tributary extender writes its own
    `MinijaBasinExample-tributaries-osm-{polygons,centerlines}.shp`;
    this script writes the mainstem-prefixed equivalents.
    """
    if polygons:
        poly_rows = [{"REACH_NAME": "Minija", "geometry": g} for g in polygons]
        gdf = gpd.GeoDataFrame(poly_rows, geometry="geometry",
                               crs="EPSG:4326").to_crs(target_crs)
        out = shp_dir / polygon_sidecar_name
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            stale = out.with_suffix(ext)
            if stale.exists():
                stale.unlink()
        gdf.to_file(out, driver="ESRI Shapefile")
        log.info("Wrote polygon sidecar %s (%d features)",
                 out.relative_to(ROOT), len(gdf))

    if polylines:
        line_rows = [{"REACH_NAME": "Minija", "geometry": g} for g in polylines]
        gdf = gpd.GeoDataFrame(line_rows, geometry="geometry",
                               crs="EPSG:4326").to_crs(target_crs)
        out = shp_dir / centerline_sidecar_name
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            stale = out.with_suffix(ext)
            if stale.exists():
                stale.unlink()
        gdf.to_file(out, driver="ESRI Shapefile")
        log.info("Wrote centerline sidecar %s (%d features)",
                 out.relative_to(ROOT), len(gdf))


def main() -> None:
    if not SHP_PATH.exists():
        raise SystemExit(
            f"missing base shapefile: {SHP_PATH}. Run "
            "_extract_minija_from_baltic.py + _extend_minija_with_tributaries.py first."
        )

    base = gpd.read_file(SHP_PATH)
    base_minija_cells = int((base["REACH_NAME"] == "Minija").sum())
    log.info("Base shapefile: %d total cells, Minija reach has %d cells",
             len(base), base_minija_cells)

    # Idempotency: drop ALL existing Minija cells (we replace them)
    other = base[base["REACH_NAME"] != "Minija"].copy()
    log.info("Removing %d existing Minija cells; keeping %d non-Minija cells",
             base_minija_cells, len(other))

    target_crs = base.crs
    log.info("Target CRS: %s", target_crs)

    # Detect UTM for cell generation
    base_wgs = base.to_crs("EPSG:4326")
    bw, bs, be, bn = base_wgs.total_bounds
    utm_epsg = detect_utm_epsg(center_lon=(bw + be) / 2, center_lat=(bs + bn) / 2)
    log.info("UTM EPSG for cell generation: %s", utm_epsg)

    # Fetch Minija polylines (cached from v0.56.2)
    polylines = fetch_minija_polylines()
    if not polylines:
        raise SystemExit("no Minija polylines retrieved — aborting")
    log.info("Loaded %d Minija polylines from OSM (full river)", len(polylines))

    # Compute centerline length for diagnostic
    cl_utm = gpd.GeoDataFrame(geometry=polylines, crs="EPSG:4326").to_crs(epsg=utm_epsg)
    centerline_len_m = float(cl_utm.geometry.length.sum())
    log.info("Minija total centerline length: %.1f km", centerline_len_m / 1000)

    # v0.56.4: load OSM water polygons that intersect the Minija centerline
    # (UNION mode — cells fill real polygon shapes plus centerline buffer).
    polygons = _load_minija_polygons_near_centerline(
        polylines, utm_epsg=utm_epsg,
    )

    log.info("Generating cells per-polyline (cell_size=%s m, buffer_factor=%s, "
             "%d polylines, %d water polygons UNION'd)...",
             CELL_SIZE_M, BUFFER_FACTOR, len(polylines), len(polygons))
    new_cells = _generate_cells_per_polyline(polylines, polygons, target_crs)
    log.info("Generated %d total Minija cells", len(new_cells))

    # Rename columns to match shapefile schema (reach_name → REACH_NAME, etc.)
    COLUMN_RENAME = {
        "cell_id": "ID_TEXT",
        "reach_name": "REACH_NAME",
        "area": "AREA",
        "dist_escape": "M_TO_ESC",
        "num_hiding": "NUM_HIDING",
        "frac_vel_shelter": "FRACVSHL",
        "frac_spawn": "FRACSPWN",
    }
    new_cells = new_cells.rename(columns=COLUMN_RENAME)
    new_cells["ID_TEXT"] = new_cells["ID_TEXT"].astype(str)
    keep_cols = [c for c in other.columns if c in new_cells.columns]
    new_cells = new_cells[keep_cols + ["geometry"]] if "geometry" not in keep_cols else new_cells[keep_cols]

    # Replace Minija reach with new 20m cells
    combined = pd.concat([other, new_cells], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=target_crs)
    n_minija_after = int((combined["REACH_NAME"] == "Minija").sum())
    log.info("Combined: %d cells (was %d). Minija reach: %d cells (was %d)",
             len(combined), len(base), n_minija_after, base_minija_cells)

    # Wipe + rewrite ONLY the main fixture file (MinijaBasinExample.*).
    # A bare `*.shp` glob would also delete sibling sidecar shapefiles
    # written by `_extend_minija_with_tributaries.py` (the tributary OSM
    # input sidecars). Stem-scoped wipe preserves them.
    shp_dir = SHP_PATH.parent
    stem = SHP_PATH.stem  # "MinijaBasinExample"
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        stale = shp_dir / f"{stem}{ext}"
        if stale.exists():
            stale.unlink()
    combined.to_file(SHP_PATH, driver="ESRI Shapefile")
    log.info("Wrote %s", SHP_PATH.relative_to(ROOT))

    # Resize Minija hydraulic CSVs to match new cell count
    n_cells = int((combined["REACH_NAME"] == "Minija").sum())
    log.info("Resizing Minija hydraulic CSVs to %d rows...", n_cells)
    for suffix in ("Depths", "Vels"):
        path = FIXTURE_DIR / f"Minija-{suffix}.csv"
        if path.exists():
            _expand_per_cell_csv(path, path, n_cells)
            log.info("  %s: resized", path.name)

    # v0.56.4: write Minija OSM input geometry to mainstem-prefixed
    # sidecar shapefiles (independent of the tributary extender's
    # tributary-prefixed sidecars). Lets users overlay the original
    # OSM source on the cells map for visual inspection.
    write_minija_osm_sidecar(SHP_PATH.parent, polylines, polygons, target_crs)

    # WGS84 bounds report — verify upper-Minija coverage
    out_wgs = combined.to_crs("EPSG:4326")
    minija_wgs = out_wgs[out_wgs["REACH_NAME"] == "Minija"]
    b = minija_wgs.total_bounds
    log.info("New Minija extent (WGS84): lon %.3f-%.3f, lat %.3f-%.3f",
             b[0], b[2], b[1], b[3])
    log.info("OK: Minija reach extended with full OSM main-stem geometry.")


if __name__ == "__main__":
    main()
