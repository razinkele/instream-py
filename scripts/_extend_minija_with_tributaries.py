"""Extend example_minija_basin with tributary reaches (v0.55.0).

Reads the cached tributary OSM polylines (from
`_fetch_minija_tributaries_osm.py`), buffers them into polygons, generates
hex cells via `create_model_grid.generate_cells`, and appends them to the
existing example_minija_basin shapefile (Minija + Atmata + CuronianLagoon
+ BalticCoast from v0.54.4).

Tributaries added (right bank, north to south):
  Babrungas   ~22 km, Lake Plateliai → Plungė → Minija main stem
  Salantas    ~52 km, north Lithuania → Salantai → Minija
  Šalpė       smaller stream, mid-river area

Veiviržė was queried but returned 0 ways (OSM regex mismatch — likely a
diacritic/spelling issue). Deferred to v0.55.x patch.

Each tributary becomes a new reach with:
  * unique REACH_NAME in the shapefile DBF
  * hex cells generated at 50m circumradius (small-channel scale)
  * per-cell Depths/Vels CSVs cloned from Minija (calibration deferred)
  * reach-level TimeSeriesInputs cloned from Minija (deferred)
  * upstream_junction = unique (7/8/9), downstream_junction = 3 (joins
    Minija's upstream end). Topologically a star — geographically the
    tributaries join at different points along Minija, but with Minija
    as a single reach we converge them all at the same junction.

Side effects: rewrites
  tests/fixtures/example_minija_basin/Shapefile/MinijaBasinExample.{shp,dbf,prj,shx,cpg}
  tests/fixtures/example_minija_basin/{Babrungas,Salantas,Salpe}-{Depths,Vels,TimeSeriesInputs}.csv

Re-running is idempotent — wipes prior tributary CSVs first.
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

from modules.create_model_grid import generate_cells  # noqa: E402
from modules.create_model_utils import detect_utm_epsg  # noqa: E402


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "example_minija_basin"
SHP_PATH = FIXTURE_DIR / "Shapefile" / "MinijaBasinExample.shp"
OSM_CACHE = ROOT / "tests" / "fixtures" / "_osm_cache" / "minija_tributaries.json"
POLY_CACHE = ROOT / "tests" / "fixtures" / "_osm_cache" / "minija_tributaries_polygons.json"

# Tributaries to add (must have data in OSM cache).
# v0.55.1: added Veivirzas (was deferred in v0.55.0 due to OSM name
# regex mismatch — actual tag is "Veiviržas", not "Veiviržė").
TRIBUTARIES = ["Babrungas", "Salantas", "Salpe", "Veivirzas"]

# Generation parameters.
# v0.55.2: tightened buffer + added polygon-clip mode to address the
# "RIVER_TOO_WIDE" error from test_geographic_conformance. Real Minija
# tributaries are 5-15 m wide channels.
# v0.56.3: bumped cell_size 30 → 20 m for higher-resolution freshwater
# habitat tiling. Real tributary widths land at the cell scale (1-2
# cells across the channel), giving finer per-cell hydraulic detail.
# Atmata, CuronianLagoon, and BalticCoast keep their existing resolution
# (inherited from example_baltic at ~50 m).
CELL_SIZE_M = 20.0
BUFFER_FACTOR = 0.5   # 10 m total buffer (5 m each side) for fallback
# Distance (m) to consider a water polygon as "belonging to" a tributary
POLY_PROXIMITY_M = 100.0
FRAC_SPAWN_TRIBUTARY = 0.30

# v0.55.3: per-tributary mean-flow multipliers vs Minija main stem.
# Approximate from drainage-area scaling (real Lithuanian gauging data
# would refine — deferred). Applied when cloning Minija-TimeSeriesInputs
# so each tributary's flow column reflects its real-river scale.
#   Minija    ~22 m³/s mean  → 1.0× baseline
#   Babrungas ~140 km² basin → 0.11
#   Salantas  ~205 km² basin → 0.16
#   Salpe     small stream   → 0.05
#   Veivirzas ~370 km² basin → 0.27 (largest tributary)
# Temperature is NOT scaled — all tributaries share Minija's climate
# zone (NW Lithuania, ~55-56°N). Same shape as
# `_scaffold_wgbast_rivers.RIVERS[*].mean_flow_multiplier` per-river config.
FLOW_MULTIPLIERS = {
    "Babrungas": 0.11,
    "Salantas":  0.16,
    "Salpe":     0.05,
    "Veivirzas": 0.27,
}

# Match the COLUMN_RENAME from _generate_wgbast_physical_domains.py so the
# output shapefile follows the same DBF schema as Minija/Atmata/etc.
COLUMN_RENAME = {
    "cell_id": "ID_TEXT",
    "reach_name": "REACH_NAME",
    "area": "AREA",
    "dist_escape": "M_TO_ESC",
    "num_hiding": "NUM_HIDING",
    "frac_vel_shelter": "FRACVSHL",
    "frac_spawn": "FRACSPWN",
}


def load_osm_lines(trib_name: str) -> list[LineString]:
    data = json.loads(OSM_CACHE.read_text(encoding="utf-8"))
    ways = data.get(trib_name, [])
    lines = []
    for w in ways:
        try:
            geom = shape(w["geometry"])
            if isinstance(geom, LineString) and len(geom.coords) >= 2:
                lines.append(geom)
        except Exception as exc:
            log.warning("[%s] skipping malformed way %s: %s",
                        trib_name, w.get("id"), exc)
    return lines


def load_basin_polygons() -> "gpd.GeoDataFrame | None":
    """Load all water polygons in the Minija basin bbox (v0.55.2)."""
    if not POLY_CACHE.exists():
        log.warning("Polygon cache missing: %s — falling back to tight buffer "
                    "for all tributaries.", POLY_CACHE)
        return None
    data = json.loads(POLY_CACHE.read_text(encoding="utf-8"))
    if not data:
        log.warning("Polygon cache empty — falling back to tight buffer.")
        return None
    polys = []
    for w in data:
        try:
            polys.append(shape(w["geometry"]))
        except Exception:
            continue
    if not polys:
        return None
    gdf = gpd.GeoDataFrame(geometry=polys, crs="EPSG:4326")
    log.info("Loaded %d basin water polygons", len(gdf))
    return gdf


def clip_polygons_to_tributary(
    poly_gdf: "gpd.GeoDataFrame",
    centerlines: list[LineString],
    proximity_m: float = POLY_PROXIMITY_M,
    utm_epsg: int = 32634,
) -> "gpd.GeoDataFrame | None":
    """Filter water polygons that intersect a buffer around the tributary
    centerline. Returns None if no polygons overlap the buffer (caller
    falls back to tight buffer mode).
    """
    if poly_gdf is None or poly_gdf.empty or not centerlines:
        return None
    # Reproject centerlines to UTM for meter-accurate buffering
    cl_gdf = gpd.GeoDataFrame(geometry=centerlines, crs="EPSG:4326").to_crs(epsg=utm_epsg)
    centerline_buffer = cl_gdf.geometry.union_all().buffer(proximity_m)
    # Reproject polys to UTM and clip to buffer
    poly_utm = poly_gdf.to_crs(epsg=utm_epsg)
    keep = poly_utm[poly_utm.intersects(centerline_buffer)].copy()
    if keep.empty:
        return None
    # Clip polygons to the centerline buffer (drop bits far from the river)
    keep["geometry"] = keep.geometry.intersection(centerline_buffer)
    keep = keep[~keep.is_empty & keep.is_valid].copy()
    if keep.empty:
        return None
    return keep.to_crs("EPSG:4326")


def write_osm_input_sidecar(
    shp_dir: Path, reach_segments: dict, target_crs,
    polygon_sidecar_name: str = "MinijaBasinExample-tributaries-osm-polygons.shp",
    centerline_sidecar_name: str = "MinijaBasinExample-tributaries-osm-centerlines.shp",
) -> None:
    """Write the OSM input geometry as TWO sidecar shapefiles
    (polygons + centerlines) — shapefile format requires uniform geom
    type per file. Both have a REACH_NAME column for filtering.

    v0.56.4: enables map overlay for visual inspection of cell coverage
    vs. real river polygon shapes.
    """
    poly_rows: list = []
    line_rows: list = []
    for reach_name, reach_data in reach_segments.items():
        for seg in reach_data.get("segments", []):
            if seg.geom_type in ("Polygon", "MultiPolygon"):
                poly_rows.append({"REACH_NAME": reach_name, "geometry": seg})
            elif seg.geom_type in ("LineString", "MultiLineString"):
                line_rows.append({"REACH_NAME": reach_name, "geometry": seg})

    if poly_rows:
        sidecar = gpd.GeoDataFrame(poly_rows, geometry="geometry", crs="EPSG:4326").to_crs(target_crs)
        out = shp_dir / polygon_sidecar_name
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            stale = out.with_suffix(ext)
            if stale.exists():
                stale.unlink()
        sidecar.to_file(out, driver="ESRI Shapefile")
        log.info("Wrote polygon sidecar %s (%d features)",
                 out.relative_to(ROOT), len(sidecar))

    if line_rows:
        sidecar = gpd.GeoDataFrame(line_rows, geometry="geometry", crs="EPSG:4326").to_crs(target_crs)
        out = shp_dir / centerline_sidecar_name
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            stale = out.with_suffix(ext)
            if stale.exists():
                stale.unlink()
        sidecar.to_file(out, driver="ESRI Shapefile")
        log.info("Wrote centerline sidecar %s (%d features)",
                 out.relative_to(ROOT), len(sidecar))


def main() -> None:
    if not SHP_PATH.exists():
        raise SystemExit(
            f"missing base shapefile: {SHP_PATH}. Run "
            "_extract_minija_from_baltic.py first."
        )
    if not OSM_CACHE.exists():
        raise SystemExit(
            f"missing OSM cache: {OSM_CACHE}. Run "
            "_fetch_minija_tributaries_osm.py first."
        )

    base = gpd.read_file(SHP_PATH)
    # If a previous run left tributary cells in the shapefile, drop them
    # so we don't double-up on re-run (v0.55.1 idempotency).
    pre_tribs = [r for r in base["REACH_NAME"].unique() if r in TRIBUTARIES]
    if pre_tribs:
        log.info("Removing pre-existing tributary cells: %s", pre_tribs)
        base = base[~base["REACH_NAME"].isin(TRIBUTARIES)].copy()
    log.info("Base fixture: %d cells, reaches=%s",
             len(base), sorted(base["REACH_NAME"].unique()))
    target_crs = base.crs
    log.info("Target CRS: %s", target_crs)

    # Determine UTM zone from base bounds (for cell generation)
    base_wgs = base.to_crs("EPSG:4326")
    bw, bs, be, bn = base_wgs.total_bounds
    utm_epsg = detect_utm_epsg(center_lon=(bw + be) / 2, center_lat=(bs + bn) / 2)
    log.info("Detected UTM EPSG: %s for cell generation", utm_epsg)

    # v0.55.2: load basin polygons (cached for future reference) and
    # measure their per-tributary coverage. Use polygon-clip mode ONLY
    # if polygons cover >= POLY_COVERAGE_FLOOR of the expected channel
    # area (centerline length × tight_buffer). Otherwise fall back to
    # tight-buffer mode — full river length, correct width.
    #
    # OSM tags Lithuanian small tributaries inconsistently: some short
    # named segments are tagged as natural=water (Babrungas, Salantas,
    # Veivirzas) but the bulk of each river is just waterway=river
    # centerline. Polygon-only mode misses 80-95% of the river length;
    # tight-buffer mode covers everything at ~30 m channel approximation,
    # which passes test_geographic_conformance and matches real widths.
    basin_polys = load_basin_polygons()
    reach_segments = {}
    poly_modes = {}  # trib -> "polygon" | "buffer"
    for trib in TRIBUTARIES:
        lines = load_osm_lines(trib)
        if not lines:
            log.warning("[%s] no OSM lines — skipping", trib)
            continue
        log.info("[%s] %d OSM line segments", trib, len(lines))
        clipped = clip_polygons_to_tributary(basin_polys, lines, utm_epsg=utm_epsg)
        polygon_area = 0.0
        if clipped is not None and not clipped.empty:
            polygon_area = float(clipped.to_crs(epsg=utm_epsg).geometry.area.sum())
        # Expected channel area = centerline length × tight buffer width
        cl_utm = gpd.GeoDataFrame(geometry=lines, crs="EPSG:4326").to_crs(epsg=utm_epsg)
        centerline_len_m = float(cl_utm.geometry.length.sum())
        expected_area = centerline_len_m * (CELL_SIZE_M * BUFFER_FACTOR)
        coverage_ratio = polygon_area / expected_area if expected_area > 0 else 0.0
        log.info("[%s] centerline=%.0f m, polygons=%.0f m², expected=%.0f m², coverage=%.1f%%",
                 trib, centerline_len_m, polygon_area, expected_area, coverage_ratio * 100)
        # v0.56.4: ALWAYS combine polygons + centerlines (UNION mode).
        # Previously the choice was polygon-OR-buffer based on a 50%
        # coverage floor. That left gaps: polygon-only mode missed
        # uncovered river segments; buffer-only mode missed wider real
        # river shapes (pools, eddies). Now we pass BOTH to generate_cells
        # which unions them into one reach polygon, ensuring cells cover
        # the union of (real OSM water polygon shape) ∪ (tight centerline
        # buffer for gaps).
        polys_for_reach: list = []
        if clipped is not None and not clipped.empty:
            polys_for_reach = list(clipped.geometry)
        combined_segments = polys_for_reach + lines
        if polys_for_reach and lines:
            mode = f"UNION (polygons={len(polys_for_reach)}, lines={len(lines)})"
        elif polys_for_reach:
            mode = f"POLYGON-only ({len(polys_for_reach)})"
        else:
            mode = f"BUFFER-only ({len(lines)} centerlines, {CELL_SIZE_M * BUFFER_FACTOR:.1f} m total)"
        log.info("[%s] using %s mode (polygon coverage %.1f%%)",
                 trib, mode, coverage_ratio * 100)
        reach_segments[trib] = {
            "segments": combined_segments,
            "frac_spawn": FRAC_SPAWN_TRIBUTARY,
        }
        poly_modes[trib] = mode

    if not reach_segments:
        raise SystemExit("no tributary data — aborting.")

    # v0.56.4: Per-tributary cell generation. Single-call mode unions all
    # tributaries' polygons into one bbox spanning the whole basin
    # (~57×62 km), which at 20 m cells creates a ~6M-cell raw grid even
    # before filter — kills walltime. Per-tributary calls keep each
    # bbox to one tributary's spatial extent (a few km), so each call
    # returns in seconds. Same pattern as `_extend_minija_mainstem.py`'s
    # per-polyline chunking.
    log.info("Generating hex cells per-tributary (cell_size=%s m, buffer=%sx, "
             "%d tributaries)...",
             CELL_SIZE_M, BUFFER_FACTOR, len(reach_segments))
    pieces: list = []
    for trib_name, trib_data in reach_segments.items():
        single_reach = {trib_name: trib_data}
        log.info("  generating %s (%d segments)...",
                 trib_name, len(trib_data["segments"]))
        try:
            piece = generate_cells(
                reach_segments=single_reach,
                cell_size=CELL_SIZE_M,
                cell_shape="hexagonal",
                buffer_factor=BUFFER_FACTOR,
            )
        except Exception as exc:
            log.warning("  %s: SKIPPED (%s)", trib_name, exc)
            continue
        if piece.empty:
            log.warning("  %s: 0 cells generated", trib_name)
            continue
        log.info("  %s: %d cells", trib_name, len(piece))
        pieces.append(piece.to_crs(target_crs))
    if not pieces:
        raise SystemExit("no cells generated — aborting.")
    new_cells = pd.concat(pieces, ignore_index=True)
    new_cells = gpd.GeoDataFrame(new_cells, geometry="geometry", crs=target_crs)
    log.info("Generated %d total cells across %d tributaries",
             len(new_cells), new_cells["reach_name"].nunique())

    # Rename columns to match the shapefile schema (UPPERCASE)
    new_cells = new_cells.rename(columns=COLUMN_RENAME)
    new_cells["ID_TEXT"] = new_cells["ID_TEXT"].astype(str)

    # Drop columns base doesn't have (defensive)
    keep_cols = [c for c in base.columns if c in new_cells.columns]
    new_cells = new_cells[keep_cols + ["geometry"]] if "geometry" not in keep_cols else new_cells[keep_cols]

    # Concatenate base + tributaries
    combined = pd.concat([base, new_cells], ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=target_crs)
    log.info("Combined: %d cells, reaches=%s",
             len(combined), sorted(combined["REACH_NAME"].unique()))

    # Wipe & rewrite shapefile
    shp_dir = SHP_PATH.parent
    for pat in ("MinijaBasinExample.shp", "MinijaBasinExample.shx",
                "MinijaBasinExample.dbf", "MinijaBasinExample.prj",
                "MinijaBasinExample.cpg"):
        stale = shp_dir / pat
        if stale.exists():
            stale.unlink()
    combined.to_file(SHP_PATH, driver="ESRI Shapefile")
    log.info("Wrote %s", SHP_PATH.relative_to(ROOT))

    # v0.56.4: write OSM input geometry as a sidecar shapefile so users
    # can overlay it on the cells map in QGIS / Shiny / any GIS to
    # verify cell coverage matches the real river polygon shape.
    write_osm_input_sidecar(shp_dir, reach_segments, target_crs)

    # Clone hydraulic CSVs for each tributary from Minija
    log.info("Cloning hydraulic CSVs from Minija for each tributary...")
    for trib in TRIBUTARIES:
        if trib not in reach_segments:
            continue
        n_cells = int((combined["REACH_NAME"] == trib).sum())
        # TimeSeriesInputs: reach-scoped. v0.55.3: scale `flow` column
        # by tributary-specific multiplier (drainage-area approx).
        src_ts = FIXTURE_DIR / "Minija-TimeSeriesInputs.csv"
        dst_ts = FIXTURE_DIR / f"{trib}-TimeSeriesInputs.csv"
        flow_mult = FLOW_MULTIPLIERS.get(trib, 1.0)
        if flow_mult == 1.0:
            shutil.copy2(src_ts, dst_ts)
        else:
            with open(src_ts, encoding="utf-8") as f:
                lines = f.readlines()
            comments = [ln for ln in lines if ln.startswith(";")]
            ts = pd.read_csv(src_ts, comment=";")
            if "flow" in ts.columns:
                ts["flow"] = ts["flow"] * flow_mult
            header_note = (
                f"; v0.55.3: flow column scaled by {flow_mult:.2f} from Minija "
                f"baseline (drainage-area approximation; real gauging data "
                f"would refine).\n"
            )
            with open(dst_ts, "w", encoding="utf-8", newline="") as f:
                f.writelines(comments)
                f.write(header_note)
                ts.to_csv(f, index=False, lineterminator="\n")
        # Depths/Vels: per-cell — need n_cells rows. Borrow the
        # _expand_per_cell_csv helper from _wire_wgbast_physical_configs.
        sys.path.insert(0, str(ROOT / "scripts"))
        from _wire_wgbast_physical_configs import _expand_per_cell_csv
        for suffix in ("Depths", "Vels"):
            src = FIXTURE_DIR / f"Minija-{suffix}.csv"
            dst = FIXTURE_DIR / f"{trib}-{suffix}.csv"
            _expand_per_cell_csv(src, dst, n_cells)
        log.info("  %s: TimeSeriesInputs + Depths(%d rows) + Vels(%d rows)",
                 trib, n_cells, n_cells)

    log.info("OK: example_minija_basin extended with %d tributaries.",
             len(reach_segments))


if __name__ == "__main__":
    main()
