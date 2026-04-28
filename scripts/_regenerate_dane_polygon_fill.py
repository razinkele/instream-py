"""v0.51.3: regenerate Danė + KlaipedaStrait with geometry that matches
real OSM widths.

Replaces the v0.51.0 output that produced 376-465 m effective river
widths against a real ~25-50 m Danė. The fix uses two different
strategies depending on what OSM gives us:

- **Danė: tight calibrated centerline buffer** (buffer_factor=0.3 on a
  75 m hex grid → ~45 m wide channel). Polygon-fill was attempted first
  but Overpass returned only 7 polygons covering 0.16 km² (vs ~2.2 km²
  of real river surface) — OSM tags Danė primarily as a `waterway=river`
  LINE, not as `natural=water` polygons, so polygon-fill produces only
  9-21 disconnected lake-patch cells per reach instead of a contiguous
  channel. The v0.51.0 mistake was not the centerline approach; it was
  the 150 m buffer (`buffer_factor=2.0`). Recalibrating that to match
  real width (`buffer_factor=0.3`) gives an effective width of ~45 m
  while preserving the channel-continuity needed for a habitat model.

- **KlaipedaStrait: polygon-fill** of the existing v0.51.0 hand-traced
  rectangle (1.7×6.7 km). 150 m hex tile gives ~200 cells of meaningful
  spatial structure instead of 1 mega-cell.

Pipeline:
  1. Load cached Danė centerline (already in `_osm_cache/dane.json`).
  2. Reuse v0.51.0's `split_centerline_into_n` logic to chop into
     4 sub-LineStrings (Mouth/Lower/Middle/Upper).
  3. generate_cells with `cell_size=75`, `buffer_factor=0.3` —
     ~45 m wide cell strip matching real Danė width.
  4. KlaipedaStrait: fill the v0.51.0 rectangle with 150 m hex cells
     via generate_cells with type="water".
  5. Write per-cell Depths/Vels/TimeSeriesInputs CSVs + the shapefile
     fragment, then merge into example_baltic.

Usage:
    micromamba run -n shiny python scripts/_regenerate_dane_polygon_fill.py
    micromamba run -n shiny python scripts/_regenerate_dane_polygon_fill.py --no-merge
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import math
import sys
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.errors import GEOSException
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, mapping, shape
from shapely.ops import linemerge, unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from modules.create_model_grid import generate_cells  # noqa: E402
from modules.create_model_export import _write_hydraulic_csv  # noqa: E402
from modules.create_model_utils import TEMPLATE_FLOWS  # noqa: E402
from modules.create_model_river import (  # noqa: E402
    filter_polygons_by_centerline_connectivity,
    partition_polygons_along_channel,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

OUT_DIR = ROOT / "tests" / "fixtures" / "_dane_temp"
SHAPEFILE_DIR = OUT_DIR / "Shapefile"
CENTERLINE_CACHE = ROOT / "tests" / "fixtures" / "_osm_cache" / "dane.json"
POLYGON_CACHE = ROOT / "tests" / "fixtures" / "_osm_cache" / "dane_polygons.json"
EXAMPLE_BALTIC = ROOT / "tests" / "fixtures" / "example_baltic"
EXAMPLE_BALTIC_SHP = EXAMPLE_BALTIC / "Shapefile" / "BalticExample.shp"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Tight bbox: keeps the Danė watershed but cuts west of lon 21.10° to
# exclude the Klaipėda port basin + strait + Curonian Lagoon (all of
# which sit between 21.00-21.13°E). Mouth is at lon 21.135° but only
# the river itself extends east of that — the port is to the west.
DANE_BBOX = (55.68, 21.10, 56.05, 21.55)  # (S, W, N, E)
DANE_NAME_TOKENS = {"Danė", "Dange", "Dangė", "Dane", "Akmena", "Akmena-Danė", "Akmena-Dange"}
DANE_MOUTH_LON_LAT = (21.135, 55.713)

# v0.51.0 KlaipedaStrait WKT (recovered from BalticExample.shp). 1.7 ×
# 6.7 km rectangle covering the Smiltynė–Klaipėda strait water surface.
# v0.51.5: clipped at runtime by lithuania_land + curonian_spit polygons
# to keep only real water (~2-3 km² of the 11.3 km² rectangle).
KLAIPEDA_STRAIT_BBOX = (21.103, 55.685, 21.130, 55.745)

# v0.51.5: BalticCoast nearshore Baltic polygon — same construction as
# generate_baltic_example.py fetch_baltic_coast() but copied here so a
# single regen run can fix both reaches without touching the 9-reach
# base generator.
BALTIC_COAST_BBOX = (20.70, 55.65, 21.20, 55.98)  # (W, S, E, N)

REACH_NAMES = ["Dane_Mouth", "Dane_Lower", "Dane_Middle", "Dane_Upper"]
REACH_FRAC_SPAWN = [0.0, 0.05, 0.05, 0.05]  # mouth=brackish, no spawn

# Cell + buffer calibration:
# - cell_size 75 m matches the v0.51.0 hex resolution (no schema break).
# - buffer_factor 0.3 → 22.5 m buffer on each side → ~45 m wide channel.
#   Real Danė is 20-30 m wide at most points; ~45 m gives 1-2 hex cells
#   of cross-channel coverage with margin so min_overlap doesn't drop
#   most cells. Matches the v0.51.2 conformance threshold of 350 m by
#   a 7× safety factor (effective_width ≈ 45 m).
DANE_CELL_SIZE_M = 75.0
DANE_BUFFER_FACTOR = 0.3
# Strait is genuine open water (1.7×6.7 km). Coarser hex keeps cell
# count modest while still giving ~200 cells of spatial structure.
STRAIT_CELL_SIZE_M = 150.0
# BalticCoast nearshore zone is ~1700 km² post-clip — coarser tile keeps
# cell count modest. Default at 2000 m (matches v0.51.4 generate_baltic_example.py).
BALTIC_COAST_CELL_SIZE_M = 2000.0


# ----------------------------------------------------------------------
# Step 1: load centerline (already cached from v0.51.0)
# ----------------------------------------------------------------------

def load_dane_centerline() -> list[LineString]:
    if not CENTERLINE_CACHE.exists():
        raise RuntimeError(
            f"Missing centerline cache {CENTERLINE_CACHE}. "
            f"Run scripts/_generate_dane_temp_fixture.py first to populate it."
        )
    data = json.loads(CENTERLINE_CACHE.read_text(encoding="utf-8"))
    lines: list[LineString] = []
    for elem in data.get("elements", []):
        if elem.get("tags", {}).get("name") not in DANE_NAME_TOKENS:
            continue
        geom = elem.get("geometry") or []
        if len(geom) < 2:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in geom]
        ls = LineString(coords)
        if ls.is_valid and not ls.is_empty:
            lines.append(ls)
    log.info("loaded %d Danė centerline ways from %s", len(lines), CENTERLINE_CACHE.name)
    if not lines:
        raise RuntimeError("No Danė centerlines found in cache")
    return lines


# ----------------------------------------------------------------------
# Step 2: fetch Danė water polygons (natural=water + waterway=riverbank)
# ----------------------------------------------------------------------

def _build_polygon_query() -> str:
    s, w, n, e = DANE_BBOX
    bbox = f"({s:.4f},{w:.4f},{n:.4f},{e:.4f})"
    # Pull all water polygons in the bbox; we filter by spatial
    # connectivity to the centerline afterwards. `out geom` returns
    # full coordinate arrays inline so we don't need a second pass.
    return (
        "[out:json][timeout:240];\n"
        "(\n"
        f'  way["natural"="water"]{bbox};\n'
        f'  way["waterway"="riverbank"]{bbox};\n'
        f'  relation["natural"="water"]{bbox};\n'
        ")->.water;\n"
        ".water out geom;\n"
    )


def fetch_dane_polygons(refresh: bool = False) -> list[dict]:
    """Return raw Overpass elements (writes ``dane_polygons.json`` cache).

    Each element is a way or relation with a `geometry` field once we've
    converted to GeoJSON Polygon shape.
    """
    if POLYGON_CACHE.exists() and not refresh:
        log.info("using cached %s", POLYGON_CACHE)
        return json.loads(POLYGON_CACHE.read_text(encoding="utf-8"))

    query = _build_polygon_query()
    log.info("Overpass query:\n%s", query)
    raw = None
    for url in OVERPASS_ENDPOINTS:
        try:
            log.info("trying %s ...", url)
            resp = requests.post(
                url,
                data={"data": query},
                timeout=300,
                headers={"User-Agent": "inSTREAM-py/0.51.3 (research; arturas.razinkovas-baziukas@ku.lt)"},
            )
            if resp.status_code != 200:
                log.warning("%s returned HTTP %d: %s", url, resp.status_code, resp.text[:200])
                time.sleep(5)
                continue
            data = resp.json()
            if not data.get("elements"):
                log.warning("%s returned 200 but 0 elements", url)
                time.sleep(5)
                continue
            raw = data
            break
        except Exception as exc:  # noqa: BLE001
            log.warning("%s failed: %s: %s", url, type(exc).__name__, exc)
            time.sleep(5)
    if raw is None:
        raise RuntimeError("All Overpass endpoints failed for Danė polygon query")

    # Normalize to a flat list of {id, name, source, geometry} dicts in
    # the same shape as example_morrumsan_polygons.json so the cache is
    # interchangeable with the WGBAST polygon caches.
    out: list[dict] = []
    for elem in raw["elements"]:
        if elem["type"] == "way":
            geom = elem.get("geometry") or []
            if len(geom) < 4:  # need ≥ 3 points + closing
                continue
            coords = [[pt["lon"], pt["lat"]] for pt in geom]
            if coords[0] != coords[-1]:
                coords.append(coords[0])  # close ring
            out.append({
                "id": elem["id"],
                "name": elem.get("tags", {}).get("name", ""),
                "source": "way:" + (
                    "riverbank" if elem.get("tags", {}).get("waterway") == "riverbank" else "water"
                ),
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            })
        elif elem["type"] == "relation":
            members = elem.get("members") or []
            outer_rings: list[list[list[float]]] = []
            for m in members:
                if m.get("role") != "outer":
                    continue
                geom = m.get("geometry") or []
                if len(geom) < 4:
                    continue
                ring = [[pt["lon"], pt["lat"]] for pt in geom]
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                outer_rings.append(ring)
            if not outer_rings:
                continue
            if len(outer_rings) == 1:
                out.append({
                    "id": elem["id"],
                    "name": elem.get("tags", {}).get("name", ""),
                    "source": "relation:water",
                    "geometry": {"type": "Polygon", "coordinates": outer_rings},
                })
            else:
                out.append({
                    "id": elem["id"],
                    "name": elem.get("tags", {}).get("name", ""),
                    "source": "relation:water",
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [[r] for r in outer_rings],
                    },
                })

    POLYGON_CACHE.parent.mkdir(parents=True, exist_ok=True)
    POLYGON_CACHE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    log.info("cached %d polygon items → %s", len(out), POLYGON_CACHE)
    return out


# ----------------------------------------------------------------------
# Step 3: parse + filter polygons (connectivity to centerline)
# ----------------------------------------------------------------------

def parse_and_filter_polygons(
    cached: list[dict], centerline: list[LineString]
) -> list[Polygon | MultiPolygon]:
    raw_polys: list = []
    for idx, item in enumerate(cached):
        try:
            poly = shape(item["geometry"])
        except (GEOSException, ValueError, TypeError, KeyError) as exc:
            log.warning("skipping cached polygon %d: %s: %s",
                        idx, type(exc).__name__, exc)
            continue
        if not poly.is_valid or poly.is_empty:
            continue
        if poly.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        raw_polys.append(poly)
    log.info("parsed %d valid polygons; filtering by connectivity to %d centerlines...",
             len(raw_polys), len(centerline))

    filtered = filter_polygons_by_centerline_connectivity(
        centerline=centerline,
        polygons=raw_polys,
        tolerance_deg=0.0005,
        max_polys=1000,
        label="Danė",
    )
    log.info("kept %d polygons in centerline-connected component", len(filtered))
    return filtered


# ----------------------------------------------------------------------
# Step 4: partition + build reach_segments
# ----------------------------------------------------------------------

def build_dane_reach_segments_from_centerline(
    centerline: list[LineString]
) -> dict:
    """Split the Danė centerline into 4 along-channel sub-LineStrings.

    Reuses the linemerge+orient+substring strategy from v0.51.0's
    ``_generate_dane_temp_fixture.py``. Each reach gets one sub-LineString
    with type="river" so generate_cells applies the calibrated buffer
    rather than treating it as a polygon.
    """
    from shapely.ops import substring

    union = unary_union(centerline)
    if union.geom_type == "MultiLineString":
        merged = linemerge(union)
    else:
        merged = union

    if merged.geom_type == "MultiLineString":
        # Disjoint segments — take the longest connected component.
        longest = max(merged.geoms, key=lambda g: g.length)
        log.warning("centerline is MultiLineString; using longest "
                    "(%.4f deg)", longest.length)
        merged = longest

    if merged.geom_type != "LineString":
        raise RuntimeError(f"Cannot split: merged is {merged.geom_type}")

    # Orient mouth → source so substring(0, 1/N) starts at the mouth.
    mouth_pt = Point(DANE_MOUTH_LON_LAT)
    coords = list(merged.coords)
    if mouth_pt.distance(Point(coords[0])) > mouth_pt.distance(Point(coords[-1])):
        coords = list(reversed(coords))
        merged = LineString(coords)
    log.info("oriented centerline: total length %.4f deg "
             "(~%.0f km at ~55.7°N)", merged.length, merged.length * 111)

    segments: dict = {}
    for i, (name, frac) in enumerate(zip(REACH_NAMES, REACH_FRAC_SPAWN)):
        sub = substring(
            merged,
            start_dist=i / len(REACH_NAMES),
            end_dist=(i + 1) / len(REACH_NAMES),
            normalized=True,
        )
        segments[name] = {
            "segments": [sub],
            "frac_spawn": frac,
            "type": "river",  # use centerline + calibrated buffer
        }
        log.info("  %s: %.4f deg (~%.1f km) of centerline",
                 name, sub.length, sub.length * 111)
    return segments


# ----------------------------------------------------------------------
# Step 5: build KlaipedaStrait fill
# ----------------------------------------------------------------------

def build_strait_segments() -> dict:
    """Build the KlaipedaStrait fill polygon with land subtracted.

    The v0.51.3 version used the raw rectangular bbox unchanged. That
    placed 198/211 cells (94%) on actual land (Klaipėda port + city +
    spit tip) — only ~2 km² of the 11.3 km² rectangle was real water.

    v0.51.5 fix: subtract Lithuanian land + Curonian Spit polygons from
    the rectangle. The remaining geometry is the actual strait water
    surface, which is ~6 km long × ~400 m wide between the spit tip
    and the port — only ~2-3 km² total.
    """
    s_lat, w_lon, n_lat, e_lon = (
        KLAIPEDA_STRAIT_BBOX[1],
        KLAIPEDA_STRAIT_BBOX[0],
        KLAIPEDA_STRAIT_BBOX[3],
        KLAIPEDA_STRAIT_BBOX[2],
    )
    strait_rect = Polygon([
        (w_lon, s_lat), (e_lon, s_lat),
        (e_lon, n_lat), (w_lon, n_lat),
        (w_lon, s_lat),
    ])

    land_path = ROOT / "app/data/marineregions/lithuania_land_real.geojson"
    spit_path = ROOT / "app/data/marineregions/curonian_spit.geojson"
    geom = strait_rect
    if land_path.exists():
        land = gpd.read_file(land_path).geometry.iloc[0]
        geom = geom.difference(land)
        log.info("KlaipedaStrait: subtracted lithuania_land_real")
    if spit_path.exists():
        spit = gpd.read_file(spit_path).geometry.iloc[0]
        geom = geom.difference(spit)
        log.info("KlaipedaStrait: subtracted curonian_spit")

    if not geom.is_valid:
        from shapely.validation import make_valid
        geom = make_valid(geom)

    if geom.is_empty:
        raise RuntimeError(
            "KlaipedaStrait polygon is empty after land/spit subtraction. "
            "Check lithuania_land_real.geojson + curonian_spit.geojson."
        )

    # Diagnostic: how much water remained?
    area_m2 = gpd.GeoDataFrame(
        geometry=[geom], crs="EPSG:4326"
    ).to_crs("EPSG:3035").geometry.iloc[0].area
    log.info("KlaipedaStrait water area after clip: %.2f km² (was 11.3 km² rectangle)",
             area_m2 / 1e6)

    # generate_cells expects a list of segments. Explode MultiPolygon into
    # its parts so each component is a Polygon.
    if geom.geom_type == "MultiPolygon":
        segments = list(geom.geoms)
    else:
        segments = [geom]

    return {
        "KlaipedaStrait": {
            "segments": segments,
            "frac_spawn": 0.0,  # marine, no spawn
            "type": "water",
        }
    }


# ----------------------------------------------------------------------
# Step 5b (v0.51.5): BalticCoast re-clip
# ----------------------------------------------------------------------

def build_balticcoast_segments() -> dict:
    """Build the BalticCoast polygon clipped by lithuania_land + curonian_spit.

    Mirrors the construction in generate_baltic_example.py fetch_baltic_coast(),
    duplicated here so this regen script can fix BalticCoast cells without
    re-running the entire 9-reach generator (which would also wipe Danė
    and force re-stitching).

    The v0.51.4 generator ran with `if/elif` between lithuania_land and
    curonian_spit; lithuania_land covers only 18.5% of the spit (it's
    Lithuania-only, the spit's south half is in Kaliningrad waters), so
    cells extended onto the spit. The fix subtracts BOTH polygons.
    """
    w_lon, s_lat, e_lon, n_lat = BALTIC_COAST_BBOX
    coast_rect = Polygon([
        (w_lon, s_lat), (e_lon, s_lat),
        (e_lon, n_lat), (w_lon, n_lat),
        (w_lon, s_lat),
    ])

    land_path = ROOT / "app/data/marineregions/lithuania_land_real.geojson"
    spit_path = ROOT / "app/data/marineregions/curonian_spit.geojson"
    geom = coast_rect
    if land_path.exists():
        land = gpd.read_file(land_path).geometry.iloc[0]
        geom = geom.difference(land)
        log.info("BalticCoast: subtracted lithuania_land_real")
    if spit_path.exists():
        spit = gpd.read_file(spit_path).geometry.iloc[0]
        geom = geom.difference(spit)
        log.info("BalticCoast: subtracted curonian_spit")

    if not geom.is_valid:
        from shapely.validation import make_valid
        geom = make_valid(geom)
    if geom.is_empty:
        raise RuntimeError("BalticCoast polygon empty after land/spit subtraction.")

    area_m2 = gpd.GeoDataFrame(
        geometry=[geom], crs="EPSG:4326"
    ).to_crs("EPSG:3035").geometry.iloc[0].area
    log.info("BalticCoast water area after clip: %.2f km²", area_m2 / 1e6)

    if geom.geom_type == "MultiPolygon":
        segments = list(geom.geoms)
    else:
        segments = [geom]

    return {
        "BalticCoast": {
            "segments": segments,
            "frac_spawn": 0.0,  # marine, no spawn
            "type": "water",
        }
    }


# ----------------------------------------------------------------------
# Step 6: per-cell CSV + shapefile output
# ----------------------------------------------------------------------

def write_per_cell_csvs(out_dir: Path, cells_gdf: gpd.GeoDataFrame, reach_names: list[str]) -> None:
    """Mirror the v0.51.0 CSV-writing logic so example_baltic loads
    unchanged after the merge."""
    flow_template = list(TEMPLATE_FLOWS)
    n_flows = len(flow_template)

    for name in reach_names:
        sub = cells_gdf[cells_gdf["reach_name"] == name].reset_index(drop=True)
        if len(sub) == 0:
            log.warning("reach %s has 0 cells; skipping CSVs", name)
            continue
        cell_ids = [f"CELL_{i+1:04d}" for i in range(len(sub))]

        depths = []
        for i, _row in sub.iterrows():
            base = 0.5 + 0.01 * i
            depths.append([
                round(base * (1.0 + 0.20 * (j / max(1, n_flows - 1))), 3)
                for j in range(n_flows)
            ])
        _write_hydraulic_csv(
            out_dir / f"{name}-Depths.csv",
            reach_name=name, kind="Depths", units="m",
            flows=flow_template, cell_ids=cell_ids, values=depths,
        )

        vels = []
        for i, _row in sub.iterrows():
            base = 0.30 + 0.005 * i
            vels.append([
                round(base * (1.0 + 0.30 * (j / max(1, n_flows - 1))), 3)
                for j in range(n_flows)
            ])
        _write_hydraulic_csv(
            out_dir / f"{name}-Vels.csv",
            reach_name=name, kind="Vels", units="m/s",
            flows=flow_template, cell_ids=cell_ids, values=vels,
        )

        # v0.51.6: extend time-series to cover the full baltic sim window
        # (2011-2038, ~28 years) so the simulation doesn't fail on lookups
        # past 2011-12-31. The original 365-day stub was a v0.51.0 bug —
        # other example_baltic reaches (Nemunas etc.) ship 9865 lines of
        # daily data. Tick day-by-day with datetime.timedelta so leap
        # years are handled automatically.
        with (out_dir / f"{name}-TimeSeriesInputs.csv").open("w", encoding="utf-8") as f:
            f.write(f"; Daily time-series inputs for {name}\n")
            f.write("; v0.51.6 multi-year extension (2011-2038)\n")
            f.write("Date,flow,temperature,turbidity,light\n")
            d = datetime.date(2011, 1, 1)
            end = datetime.date(2038, 12, 31)
            while d <= end:
                doy = d.timetuple().tm_yday
                temp = 2.0 + 8.0 * (1.0 + math.sin(2 * math.pi * (doy - 90) / 365.0))
                f.write(f"{d.isoformat()},50.0,{temp:.2f},5.0,500\n")
                d += datetime.timedelta(days=1)
        log.info("wrote %s-{Depths,Vels,TimeSeriesInputs}.csv (%d cells)", name, len(sub))


# ----------------------------------------------------------------------
# Step 7: merge into example_baltic
# ----------------------------------------------------------------------

def merge_into_example_baltic(new_cells: gpd.GeoDataFrame, reaches_to_replace: list[str]) -> None:
    """Drop existing Dane_*+KlaipedaStrait rows from BalticExample.shp,
    append regenerated cells, renumber ID_TEXT globally to keep IDs
    contiguous, write back. Also delete + rewrite per-reach CSVs.
    """
    log.info("loading %s ...", EXAMPLE_BALTIC_SHP)
    existing = gpd.read_file(EXAMPLE_BALTIC_SHP)
    log.info("existing: %d cells in %s", len(existing), sorted(existing["REACH_NAME"].unique()))

    keep = existing[~existing["REACH_NAME"].isin(reaches_to_replace)].copy()
    log.info("after dropping %s: %d cells remain", reaches_to_replace, len(keep))

    # Reproject regenerated cells to match existing CRS (EPSG:3035)
    target_crs = existing.crs
    if new_cells.crs != target_crs:
        log.info("reprojecting regenerated cells %s → %s", new_cells.crs, target_crs)
        new_cells = new_cells.to_crs(target_crs)

    # Standardize new_cells columns to match the shapefile schema
    schema_cols = ["ID_TEXT", "REACH_NAME", "AREA", "M_TO_ESC",
                   "NUM_HIDING", "FRACVSHL", "FRACSPWN", "geometry"]
    rename_map = {
        "cell_id": "ID_TEXT",
        "reach_name": "REACH_NAME",
        "area": "AREA",
        "dist_escape": "M_TO_ESC",
        "num_hiding": "NUM_HIDING",
        "frac_vel_shelter": "FRACVSHL",
        "frac_spawn": "FRACSPWN",
    }
    new_cells = new_cells.rename(columns=rename_map)
    for col in schema_cols:
        if col not in new_cells.columns and col != "geometry":
            new_cells[col] = 0
    new_cells = new_cells[schema_cols]

    # Recompute AREA in target CRS units
    new_cells["AREA"] = new_cells.geometry.area

    merged = pd.concat([keep, new_cells], ignore_index=True)

    # Renumber ID_TEXT globally as CELL_NNNN so IDs are contiguous and
    # the v0.51.2 conformance test never sees CELL_2357-style outliers.
    merged["ID_TEXT"] = [f"CELL_{i+1:04d}" for i in range(len(merged))]
    merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=target_crs)
    log.info("merged: %d cells across %d reaches", len(merged),
             merged["REACH_NAME"].nunique())

    merged.to_file(EXAMPLE_BALTIC_SHP)
    log.info("wrote %s", EXAMPLE_BALTIC_SHP)

    # Move per-reach CSVs from _dane_temp into example_baltic, deleting
    # any v0.51.0 vintage that we're replacing.
    for reach in reaches_to_replace:
        for suffix in ("Depths", "Vels", "TimeSeriesInputs"):
            old = EXAMPLE_BALTIC / f"{reach}-{suffix}.csv"
            if old.exists():
                old.unlink()
                log.info("removed old %s", old.name)

    for src in OUT_DIR.glob("*.csv"):
        dst = EXAMPLE_BALTIC / src.name
        dst.write_bytes(src.read_bytes())
        log.info("copied %s → example_baltic/", src.name)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-overpass", action="store_true",
                        help="re-fetch polygon cache from Overpass (ignores existing JSON)")
    parser.add_argument("--no-merge", action="store_true",
                        help="skip merging into example_baltic; leave output in _dane_temp/")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SHAPEFILE_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: centerline (cached). Polygon-fetch+filter is kept as a
    # diagnostic path but doesn't drive cell generation — see module
    # docstring for why.
    centerline = load_dane_centerline()

    # Step 2: split centerline into 4 sub-LineStrings
    dane_segments = build_dane_reach_segments_from_centerline(centerline)

    # Step 3: Danė hex cells with calibrated tight buffer
    log.info("generating Danė cells (cell_size=%.0f m, buffer_factor=%.2f) ...",
             DANE_CELL_SIZE_M, DANE_BUFFER_FACTOR)
    dane_cells = generate_cells(
        reach_segments=dane_segments,
        cell_size=DANE_CELL_SIZE_M,
        cell_shape="hexagonal",
        buffer_factor=DANE_BUFFER_FACTOR,
        min_overlap=0.1,
    )
    if dane_cells.empty:
        raise RuntimeError("Danė generate_cells produced 0 cells")
    log.info("Danė cells: %d total", len(dane_cells))

    # Step 6: KlaipedaStrait hex cells
    strait_segments = build_strait_segments()
    log.info("generating KlaipedaStrait cells (cell_size=%.0f m) ...", STRAIT_CELL_SIZE_M)
    strait_cells = generate_cells(
        reach_segments=strait_segments,
        cell_size=STRAIT_CELL_SIZE_M,
        cell_shape="hexagonal",
        buffer_factor=2.0,
        min_overlap=0.1,
    )
    if strait_cells.empty:
        raise RuntimeError("KlaipedaStrait generate_cells produced 0 cells")
    log.info("KlaipedaStrait cells: %d total", len(strait_cells))

    # Step 6b (v0.51.5): BalticCoast hex cells with land + spit clip
    bc_segments = build_balticcoast_segments()
    log.info("generating BalticCoast cells (cell_size=%.0f m) ...", BALTIC_COAST_CELL_SIZE_M)
    bc_cells = generate_cells(
        reach_segments=bc_segments,
        cell_size=BALTIC_COAST_CELL_SIZE_M,
        cell_shape="hexagonal",
        buffer_factor=2.0,
        min_overlap=0.1,
    )
    if bc_cells.empty:
        raise RuntimeError("BalticCoast generate_cells produced 0 cells")
    log.info("BalticCoast cells: %d total", len(bc_cells))

    # Combine + write CSVs in _dane_temp/
    all_cells = gpd.GeoDataFrame(
        pd.concat([dane_cells, strait_cells, bc_cells], ignore_index=True),
        geometry="geometry",
        crs=dane_cells.crs,
    )
    all_reach_names = REACH_NAMES + ["KlaipedaStrait", "BalticCoast"]
    write_per_cell_csvs(OUT_DIR, all_cells, all_reach_names)

    # Per-reach summary
    for reach in all_reach_names:
        n = int((all_cells["reach_name"] == reach).sum())
        sub = all_cells[all_cells["reach_name"] == reach]
        if len(sub):
            area_m2 = sub.geometry.union_all().area  # already in UTM meters
            log.info("  %s: %d cells, total %.0f m²", reach, n, area_m2)
        else:
            log.warning("  %s: 0 cells", reach)

    # Write the shapefile fragment
    shp = SHAPEFILE_DIR / "dane.shp"
    all_cells_for_shp = all_cells.rename(columns={
        "cell_id": "ID_TEXT",
        "reach_name": "REACH_NAME",
        "area": "AREA",
        "dist_escape": "M_TO_ESC",
        "num_hiding": "NUM_HIDING",
        "frac_vel_shelter": "FRACVSHL",
        "frac_spawn": "FRACSPWN",
    })
    all_cells_for_shp.to_file(shp)
    log.info("wrote shapefile fragment → %s (%d features, CRS=%s)",
             shp, len(all_cells_for_shp), all_cells_for_shp.crs)

    if not args.no_merge:
        merge_into_example_baltic(
            all_cells_for_shp,
            REACH_NAMES + ["KlaipedaStrait", "BalticCoast"],
        )
    else:
        log.info("--no-merge: skipping example_baltic merge")

    print()
    print("=" * 60)
    print("v0.51.5 Danė + KlaipedaStrait + BalticCoast regen complete.")
    print(f"  Total new cells: {len(all_cells)}")
    for reach in all_reach_names:
        n = int((all_cells["reach_name"] == reach).sum())
        print(f"    {reach}: {n} cells")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
