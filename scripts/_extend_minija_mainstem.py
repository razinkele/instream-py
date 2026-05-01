"""Append upper-Minija OSM cells to example_minija_basin's Minija reach.

The v0.54.3 Minija extraction from example_baltic only covered the
lower 40 km (55.35-55.75°N); real Minija extends to 55.93°N where
Babrungas + Salantas tributaries join. The v0.56.0 conformance check
flagged this as REACH_DISCONNECTED at ~7.5 km gap.

This script fetches Minija's full OSM polylines (Overpass), filters
to the UPPER portion (above 55.75°N — the part missing from
baltic-extracted Minija), buffers them tight, generates hex cells,
and APPENDS them to the existing Minija reach (rather than replacing,
which is much slower).

Idempotent: re-runs detect and remove prior upper-Minija cells via
the new ID_TEXT prefix "MJU-" (Minija Upper).
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

# Match v0.55.2 tributary parameters for consistency
CELL_SIZE_M = 30.0
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


UPPER_MINIJA_LAT_FLOOR = 55.75  # match upper bound of baltic-extracted Minija


def main() -> None:
    if not SHP_PATH.exists():
        raise SystemExit(
            f"missing base shapefile: {SHP_PATH}. Run "
            "_extract_minija_from_baltic.py + _extend_minija_with_tributaries.py first."
        )

    base = gpd.read_file(SHP_PATH)
    base_minija_cells = (base["REACH_NAME"] == "Minija").sum()
    log.info("Base shapefile: %d total cells, Minija reach has %d cells",
             len(base), base_minija_cells)

    # Idempotency: drop any prior upper-Minija cells (ID_TEXT starts with "MJU-")
    if "ID_TEXT" in base.columns:
        is_upper = base["ID_TEXT"].astype(str).str.startswith("MJU-")
        n_prior_upper = int(is_upper.sum())
        if n_prior_upper > 0:
            log.info("Removing %d prior upper-Minija cells (re-run cleanup)", n_prior_upper)
            base = base[~is_upper].copy()

    target_crs = base.crs
    log.info("Target CRS: %s", target_crs)

    # Detect UTM for cell generation
    base_wgs = base.to_crs("EPSG:4326")
    bw, bs, be, bn = base_wgs.total_bounds
    utm_epsg = detect_utm_epsg(center_lon=(bw + be) / 2, center_lat=(bs + bn) / 2)
    log.info("UTM EPSG for cell generation: %s", utm_epsg)

    # Fetch Minija polylines (cached)
    polylines = fetch_minija_polylines()
    if not polylines:
        raise SystemExit("no Minija polylines retrieved — aborting")
    log.info("Loaded %d Minija polylines from OSM", len(polylines))

    # Filter to upper-Minija (above 55.75°N) — the part missing from baltic
    upper_polylines = [
        line for line in polylines
        if line.bounds[3] > UPPER_MINIJA_LAT_FLOOR  # max lat above floor
    ]
    log.info("Filtered to %d upper-Minija polylines (above %s°N)",
             len(upper_polylines), UPPER_MINIJA_LAT_FLOOR)
    if not upper_polylines:
        raise SystemExit(f"no Minija polylines above {UPPER_MINIJA_LAT_FLOOR}°N")

    # Compute centerline length for diagnostic
    cl_utm = gpd.GeoDataFrame(geometry=upper_polylines, crs="EPSG:4326").to_crs(epsg=utm_epsg)
    centerline_len_m = float(cl_utm.geometry.length.sum())
    log.info("Upper-Minija centerline length: %.1f km", centerline_len_m / 1000)

    # Generate cells using the same approach as tributaries
    reach_segments = {
        "Minija": {
            "segments": upper_polylines,
            "frac_spawn": FRAC_SPAWN_MAINSTEM,
        },
    }
    log.info("Generating cells (cell_size=%s m, buffer_factor=%s)...",
             CELL_SIZE_M, BUFFER_FACTOR)
    new_cells = generate_cells(
        reach_segments=reach_segments,
        cell_size=CELL_SIZE_M,
        cell_shape="hexagonal",
        buffer_factor=BUFFER_FACTOR,
    )
    log.info("Generated %d new upper-Minija cells", len(new_cells))

    # Reproject + rename columns to match shapefile schema
    new_cells = new_cells.to_crs(target_crs)
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
    # Mark upper-Minija cells with "MJU-" prefix for idempotent re-runs
    new_cells["ID_TEXT"] = "MJU-" + new_cells["ID_TEXT"].astype(str)
    keep_cols = [c for c in base.columns if c in new_cells.columns]
    new_cells = new_cells[keep_cols + ["geometry"]] if "geometry" not in keep_cols else new_cells[keep_cols]

    # Append upper-Minija cells to existing fixture
    combined = pd.concat([base, new_cells], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=target_crs)
    n_minija_after = int((combined["REACH_NAME"] == "Minija").sum())
    log.info("Combined: %d cells (was %d). Minija reach: %d cells (was %d, +%d upper)",
             len(combined), len(base),
             n_minija_after, base_minija_cells, len(new_cells))

    # Wipe + rewrite shapefile
    shp_dir = SHP_PATH.parent
    for pat in ("*.shp", "*.shx", "*.dbf", "*.prj", "*.cpg"):
        for stale in shp_dir.glob(pat):
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

    # WGS84 bounds report — verify upper-Minija coverage
    out_wgs = combined.to_crs("EPSG:4326")
    minija_wgs = out_wgs[out_wgs["REACH_NAME"] == "Minija"]
    b = minija_wgs.total_bounds
    log.info("New Minija extent (WGS84): lon %.3f-%.3f, lat %.3f-%.3f",
             b[0], b[2], b[1], b[3])
    log.info("OK: Minija reach extended with full OSM main-stem geometry.")


if __name__ == "__main__":
    main()
