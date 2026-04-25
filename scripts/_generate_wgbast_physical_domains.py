"""Generate physical (geographically real) domain fixtures for the 4 WGBAST rivers.

Replaces the Nemunas-template-copy fixtures with shapefiles whose cells sit at
real lat/lon locations for each river, using curated waypoints from public
geographic data (mouth + source + intermediate tributary confluences).

Rivers covered (north to south):
  Tornionjoki   — Torne river, FI/SE border; mouth Tornio-Haparanda
  Simojoki      — Simo river, Finland; mouth Simo
  Byskealven    — Byske river, Sweden; mouth Byske
  Morrumsan     — Mörrum river, Sweden; mouth Mörrum

For each river, builds a 4-reach topology (Mouth → Lower → Middle → Upper)
along a simplified polyline. Hex cells are generated via the existing
`app/modules/create_model_grid.generate_cells` used by the Create-Model UI.
Output shapefiles match the `spatial.gis_properties` contract of the configs
(ID_TEXT, REACH_NAME, AREA, M_TO_ESC, NUM_HIDING, FRACVSHL, FRACSPWN).

Usage:
    micromamba run -n shiny python scripts/_generate_wgbast_physical_domains.py

This is idempotent — re-running overwrites existing shapefiles.
"""
from __future__ import annotations

import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

# Borrow the Create-Model hex-cell infrastructure so the output is schema-
# compatible with what the Shiny UI produces and what SalmopyModel loads.
from modules.create_model_grid import generate_cells  # noqa: E402
from modules.create_model_utils import detect_utm_epsg  # noqa: E402
from modules.create_model_marine import clip_sea_polygon_to_disk  # noqa: E402
from modules.create_model_river import (  # noqa: E402
    filter_polygons_by_centerline_connectivity,
    partition_polygons_along_channel,
)

OSM_CACHE = ROOT / "tests" / "fixtures" / "_osm_cache"

# Polygon connectivity tolerance (degrees). Two polygons "touch" if their
# distance is below this threshold. Generous enough to handle the small
# gaps OSM tagging sometimes leaves between adjacent water polygons
# (e.g. a road crossing tagged as a separate way). 0.0005° ≈ 55 m at
# our latitudes — small enough to exclude unconnected ponds 100+ m away
# but large enough to bridge OSM-tagging gaps within the river system.
POLY_CONNECT_TOL_DEG = 0.0005

# Maximum reach polygons to keep (largest connected component). Caps
# memory if the centerline accidentally touches a major sea polygon.
MAX_CONNECTED_POLYS = 2000

# BalticCoast (marine) reach constants. v0.46+ spec §Architecture overview.
BALTICCOAST_RADIUS_M = 10_000.0       # 10 km clip around river mouth

# Marine cell_size = river.cell_size_m × factor. Per-river so Mörrumsån's
# 60 m freshwater cells don't produce >5000 marine cells (the 10 km disk
# at Hanöbukten is mostly open water). Tornionjoki/Simojoki/Byskeälven
# use factor=4 (river cells 80–150 m → marine 320–600 m).
# Mörrumsån uses factor=8 (river 60 m → marine 480 m, ~1500 disk cells).
BALTICCOAST_CELL_FACTOR_DEFAULT = 4.0
BALTICCOAST_CELL_FACTOR_OVERRIDE = {
    "example_morrumsan": 8.0,
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# River waypoints (WGS84, lon/lat). Curated from:
#   - OpenStreetMap (main channel + major tributary confluences)
#   - SMHI (Sweden) and SYKE (Finland) public river metadata
#   - Wikipedia gazetteer entries (cross-referenced)
# Each river lists waypoints from mouth (index 0) to source (last index).
# We split the polyline into 4 reaches at roughly equal along-channel
# distances so every fixture has Mouth / Lower / Middle / Upper reaches.
# ---------------------------------------------------------------------------


@dataclass
class River:
    short_name: str           # example_tornionjoki
    stem: str                 # TornionjokiExample (for CSV/Shapefile naming)
    river_name: str           # "Tornionjoki" (for config river_name field)
    latitude: float           # river-mouth latitude (config.light.latitude)
    # Waypoints: list of (lon, lat) pairs, MOUTH first, SOURCE last.
    # Must be in geographic (EPSG:4326) coordinates.
    waypoints: list[tuple[float, float]]
    # Cell size in metres (hex circumradius). Larger rivers → bigger cells.
    cell_size_m: float
    # Buffer factor × cell_size_m defines the cross-channel extent.
    # ~half channel width in cell units. 30-50 m channels -> factor 3-4.
    buffer_factor: float


RIVERS: list[River] = [
    # --- Tornionjoki (Torne River) — Finnish-Swedish border ---
    # Mouth Tornio/Haparanda (~65.88°N). Flows south from Lake Kilpisjärvi
    # region; the Finnish-Swedish border follows the main stem.
    # Source waypoint: Muonionjoki confluence at Pajala/Kolari.
    River(
        short_name="example_tornionjoki",
        stem="TornionjokiExample",
        river_name="Tornionjoki",
        latitude=65.85,
        waypoints=[
            (24.142, 65.881),   # 0: Tornio/Haparanda (mouth into Gulf of Bothnia)
            (23.910, 66.260),   # 1: Karunki area (lower)
            (23.665, 66.820),   # 2: Ylitornio (middle)
            (23.640, 67.180),   # 3: Pello (upper-middle)
            (23.530, 67.600),   # 4: Kolari / Muonionjoki confluence (upper)
        ],
        cell_size_m=150.0,      # ~100m channel width, 150m cells
        buffer_factor=3.0,
    ),
    # --- Simojoki (Simo River) — small Finnish Baltic salmon river ---
    # Mouth at Simo (~65.62°N). Flows SW from Lake Simojärvi.
    River(
        short_name="example_simojoki",
        stem="SimojokiExample",
        river_name="Simojoki",
        latitude=65.62,
        waypoints=[
            (25.063, 65.619),   # 0: Simo (mouth into Gulf of Bothnia)
            (25.400, 65.780),   # 1: Simonkylä (lower)
            (25.950, 65.900),   # 2: Ranua area (middle)
            (26.600, 66.000),   # 3: Tainijärvi area
            (26.916, 66.091),   # 4: Simojärvi outflow (upper/source)
        ],
        cell_size_m=80.0,       # ~30m channel width, smaller cells
        buffer_factor=3.0,
    ),
    # --- Byskealven (Byske River) — Swedish Baltic salmon river ---
    # Mouth at Byske (~64.94°N). Flows SE from Västerbotten highlands.
    River(
        short_name="example_byskealven",
        stem="ByskealvenExample",
        river_name="Byskealven",
        latitude=64.94,
        waypoints=[
            (21.182, 64.945),   # 0: Byske (mouth into Gulf of Bothnia)
            (20.700, 65.000),   # 1: Fällfors
            (20.100, 65.070),   # 2: Jörn area
            (19.400, 65.120),   # 3: Kåtaviken area
            (18.850, 65.160),   # 4: Arvidsjaur area (upper)
        ],
        cell_size_m=80.0,
        buffer_factor=3.0,
    ),
    # --- Mörrumsån (Mörrum River) — southern Swedish Baltic salmon river ---
    # Mouth at Mörrum (~56.17°N). Short river (~186 km); flows S from
    # Lake Möckeln. Famous salmon-angling river.
    River(
        short_name="example_morrumsan",
        stem="MorrumsanExample",
        river_name="Morrumsan",
        latitude=56.17,
        waypoints=[
            (14.745, 56.175),   # 0: Mörrum (mouth into Hanöbukten/Baltic)
            (14.702, 56.300),   # 1: Svängsta
            (14.636, 56.450),   # 2: Asarum / mid-course
            (14.595, 56.570),   # 3: Ubbaboda area
            (14.580, 56.671),   # 4: Lake Möckeln outflow (upper/source)
        ],
        cell_size_m=60.0,       # ~20m channel width, small cells
        buffer_factor=4.0,
    ),
]


# Property naming from configs/example_baltic.yaml spatial.gis_properties.
# The loader reads these exact column names from the shapefile.
COLUMN_RENAME = {
    "cell_id": "ID_TEXT",
    "reach_name": "REACH_NAME",
    "area": "AREA",
    "dist_escape": "M_TO_ESC",
    "num_hiding": "NUM_HIDING",
    "frac_vel_shelter": "FRACVSHL",
    "frac_spawn": "FRACSPWN",
}


REACH_NAMES = ["Mouth", "Lower", "Middle", "Upper"]
# Salmon prefer fast-water riffles in mid-upper reaches for redd digging.
FRAC_SPAWN = [0.0, 0.15, 0.35, 0.30]


def _load_osm_ways(river: River) -> list[LineString] | None:
    """Load cached OSM ways for `river` if available, else return None.

    Use `scripts/_fetch_wgbast_osm_polylines.py` to populate the cache.
    Returns a list of LineStrings in WGS84 lon/lat.
    """
    cache_path = OSM_CACHE / f"{river.short_name}.json"
    if not cache_path.exists():
        return None
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    lines = []
    for w in data:
        try:
            lines.append(shape(w["geometry"]))
        except Exception as exc:
            log.debug("skipping malformed OSM way %s: %s", w.get("id"), exc)
    return lines or None


def _load_or_fetch_marineregions(
    river: River,
    refresh: bool = False,
    bbox_pad_deg: float = 0.5,
) -> "gpd.GeoDataFrame | None":
    """Return the Marine Regions IHO polygons for `river`, cached at
    tests/fixtures/_osm_cache/<short_name>_marineregions.json.

    On first call (or when `refresh=True`), queries Marine Regions WFS
    via `create_model_marine.query_named_sea_polygon`. Caches the
    response as a flat list of GeoJSON features (matching the existing
    OSM line/polygon cache shape).

    Returns None if WFS fetch fails on a fresh attempt.
    """
    cache = OSM_CACHE / f"{river.short_name}_marineregions.json"
    if not refresh and cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        if not data:
            # An empty cache file is never a legitimate state — we only
            # write the cache when WFS returned a non-empty result.
            # Surface this as a hard error rather than silently returning
            # None (which would mask the real cause: the cache was
            # corrupted, manually emptied, or written by an old buggy
            # version of this script).
            raise RuntimeError(
                f"Cache file {cache} is empty (never a legitimate state). "
                f"Delete it and re-run the generator (it will re-fetch from "
                f"WFS), or copy a known-good cache from another developer's "
                f"machine."
            )
        gdf = gpd.GeoDataFrame.from_features(data, crs="EPSG:4326")
        # Drop null / invalid geometries (defensive — caches could be
        # corrupted by external editing or version drift).
        gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid].copy()
        if gdf.empty:
            return None
        return gdf[["name", "geometry"]] if "name" in gdf.columns else gdf

    from modules.create_model_marine import query_named_sea_polygon
    mouth_lon, mouth_lat = river.waypoints[0]
    bbox = (
        mouth_lon - bbox_pad_deg, mouth_lat - bbox_pad_deg,
        mouth_lon + bbox_pad_deg, mouth_lat + bbox_pad_deg,
    )
    gdf = query_named_sea_polygon(bbox)
    if gdf is None or gdf.empty:
        # WFS unreachable or empty result — do NOT write an empty cache
        # file. Future calls will see "no cache" and retry the WFS,
        # rather than seeing a corrupt empty cache.
        return None
    # Cache as a list of GeoJSON features (always non-empty here)
    payload = json.loads(gdf.to_json())["features"]
    if not payload:
        # Defensive: gdf was non-empty but to_json round-trip yielded
        # no features. Don't write a misleading empty cache.
        return gdf
    cache.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: PID+thread-unique tmp file, then os.replace.
    # Defeats OneDrive sync / Defender real-time scan read-locks that
    # could otherwise cause PermissionError [WinError 32] on the second
    # write of the 4-river loop. os.replace is atomic on NTFS and Linux.
    # The try/except cleans up the .tmp file if os.replace fails
    # (Defender lock, permission denied), preventing orphan files in
    # the cache dir.
    #
    # PID+thread-unique suffix prevents tmp-file collision when two
    # concurrent processes (regenerator + Shiny session both calling
    # query_named_sea_polygon, or a CI run + dev machine on shared
    # storage) both miss the cache and race to write it.
    import os
    import threading
    tmp = cache.with_suffix(
        f".{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, cache)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return gdf


def _load_osm_polygons_filtered(
    river: River, centerline: list[LineString]
) -> list:
    """Load cached OSM water polygons, keep only the connected component
    that touches the centerline.

    Thin wrapper around create_model_river.filter_polygons_by_centerline_connectivity.
    """
    poly_cache = OSM_CACHE / f"{river.short_name}_polygons.json"
    if not poly_cache.exists():
        return []
    data = json.loads(poly_cache.read_text(encoding="utf-8"))
    from shapely.errors import GEOSException
    import logging
    log = logging.getLogger(__name__)
    raw_polys: list = []
    for idx, item in enumerate(data):
        try:
            poly = shape(item["geometry"])
        except (GEOSException, ValueError, TypeError, KeyError) as exc:
            log.warning(
                "%s: skipping cached polygon %d (%s): %s",
                river.short_name, idx, type(exc).__name__, exc,
            )
            continue
        if not poly.is_valid or poly.is_empty:
            continue
        if poly.geom_type not in ("Polygon", "MultiPolygon"):
            continue
        raw_polys.append(poly)
    return filter_polygons_by_centerline_connectivity(
        centerline=centerline,
        polygons=raw_polys,
        tolerance_deg=POLY_CONNECT_TOL_DEG,
        max_polys=MAX_CONNECTED_POLYS,
        label=river.river_name,
    )


def build_reach_segments_from_waypoints(river: River) -> dict:
    """Fallback: split hand-curated waypoints into 4 reaches.

    With 5 waypoints we get 4 segments; each segment becomes one reach.
    The most-downstream reach (0→1) is the Mouth; it receives
    frac_spawn=0 because Atlantic salmon spawn upstream, not at the mouth.
    Upstream reaches get progressively higher frac_spawn.
    """
    wps = river.waypoints
    segments = {}
    for i, name in enumerate(REACH_NAMES):
        line = LineString([wps[i], wps[i + 1]])
        segments[name] = {
            "segments": [line],
            "frac_spawn": FRAC_SPAWN[i],
            "type": "river",
        }
    return segments


def build_reach_segments_from_osm(
    river: River, ways: list[LineString]
) -> dict:
    """Split real OSM ways into 4 reaches by quartile of along-channel
    distance from the river mouth.

    Each OSM way's centroid is projected to a 1-D coordinate measuring
    how far the way is from `river.waypoints[0]` (the mouth). Ways are
    then partitioned into 4 equal-count quartiles ordered mouth→source.

    This is a simple proxy for true along-channel distance (which would
    require graph assembly of connected ways). Quartile splits by
    euclidean distance are robust when the river's centerline is roughly
    monotone in one direction from the mouth, which holds for all 4
    WGBAST rivers (they flow SE/S/SW from inland sources to the Baltic).
    """
    if len(ways) < 4:
        # Fall back to waypoint split if OSM returned too few segments.
        log.warning(
            "[%s] only %d OSM ways — falling back to waypoint polyline.",
            river.river_name, len(ways),
        )
        return build_reach_segments_from_waypoints(river)

    mouth = Point(river.waypoints[0])
    # distance in degrees (approximate) — fine for ordering
    scored = sorted(
        ((w.centroid.distance(mouth), w) for w in ways),
        key=lambda t: t[0],
    )

    # Split into 4 quartiles as equally as possible
    n = len(scored)
    q = n / 4.0
    slices = [
        (int(q * i), int(q * (i + 1))) for i in range(4)
    ]
    # last slice always goes to end to absorb rounding
    slices[-1] = (slices[-1][0], n)

    segments: dict = {}
    for i, name in enumerate(REACH_NAMES):
        lo, hi = slices[i]
        reach_ways = [w for _, w in scored[lo:hi]]
        segments[name] = {
            "segments": reach_ways,
            "frac_spawn": FRAC_SPAWN[i],
            "type": "river",
        }
        log.info("  [%s] %d ways, distance range %.4f → %.4f deg",
                 name, len(reach_ways),
                 scored[lo][0] if reach_ways else 0.0,
                 scored[hi - 1][0] if reach_ways else 0.0)
    return segments


def build_reach_segments_from_polygons(
    river: River, centerline: list[LineString], polygons: list
) -> dict:
    """Partition water polygons into 4 reaches by along-channel distance,
    delegating geometry to create_model_river.partition_polygons_along_channel.
    """
    if len(polygons) < 4:
        log.warning(
            "[%s] only %d polygons (need ≥4) — falling back to line-buffer split.",
            river.river_name, len(polygons),
        )
        return build_reach_segments_from_osm(river, centerline)

    groups = partition_polygons_along_channel(
        centerline=centerline,
        polygons=polygons,
        mouth_lon_lat=river.waypoints[0],
        n_reaches=len(REACH_NAMES),  # 4
    )

    segments: dict = {}
    for name, frac, group in zip(REACH_NAMES, FRAC_SPAWN, groups):
        if not group:
            continue
        segments[name] = {
            "segments": group,
            "frac_spawn": frac,
            "type": "water",
        }
        log.info("  [%s] %d polys", name, len(group))
    return segments


def build_reach_segments(river: River) -> dict:
    """Use the highest-fidelity source available:
       (1) OSM water polygons (filtered near the centerline)
       (2) OSM waterway=river line ways (centerlines + buffer)
       (3) Hand-curated waypoints (fallback)
    """
    ways = _load_osm_ways(river)
    if ways is None:
        log.info("[%s] no OSM cache; using %d hand-curated waypoints.",
                 river.river_name, len(river.waypoints))
        return build_reach_segments_from_waypoints(river)

    polygons = _load_osm_polygons_filtered(river, ways)
    if polygons:
        log.info("[%s] using %d OSM water polygons (centerline-connected "
                 "component) + %d line ways as center reference.",
                 river.river_name, len(polygons), len(ways))
        return build_reach_segments_from_polygons(river, ways, polygons)

    log.info("[%s] no polygons available; using %d OSM line ways.",
             river.river_name, len(ways))
    return build_reach_segments_from_osm(river, ways)


def write_river_shapefile(river: River) -> Path:
    """Generate hex cells for `river` and write {RiverStem}Example.shp."""
    fixture_dir = ROOT / "tests" / "fixtures" / river.short_name
    shp_dir = fixture_dir / "Shapefile"
    shp_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("River: %s  (%s)", river.river_name, river.short_name)
    log.info("Latitude: %.3f  |  cell_size=%s m, buffer=%s×",
             river.latitude, river.cell_size_m, river.buffer_factor)

    reach_segments = build_reach_segments(river)
    total_len = sum(
        r["segments"][0].length for r in reach_segments.values()
    )
    log.info("Main channel length (degrees): %.4f  [~%s km at this lat]",
             total_len, int(total_len * 111))

    fresh = generate_cells(
        reach_segments=reach_segments,
        cell_size=river.cell_size_m,
        cell_shape="hexagonal",
        buffer_factor=river.buffer_factor,
        min_overlap=0.1,
    )
    if fresh.empty:
        raise RuntimeError(
            f"{river.short_name}: generate_cells returned 0 freshwater cells. "
            f"Increase buffer_factor or cell_size and re-run."
        )

    # --- BalticCoast marine reach -----------------------------------------
    # Pin the marine disk to the MOUTH's UTM zone (NOT the freshwater
    # centroid's zone). The mouth is where the disk is centred, and for
    # Tornionjoki the mouth lon=24.142° is in zone 35 while the centerline
    # centroid is at ~23.77° (zone 34); using the freshwater zone for a
    # mouth-centred disk would push the entire disk to the far edge of
    # the wrong zone where UTM scale distortion grows.
    #
    # The freshwater grid was already generated by `generate_cells` in a
    # zone derived from its own internal centroid logic. Both grids are
    # reprojected to WGS84 by `generate_cells` before they are returned
    # (see app/modules/create_model_grid.py:237 `gdf.to_crs("EPSG:4326")`),
    # so cross-zone differences are eliminated in the output. The 1e-5°
    # WGS84 buffer (~1m) absorbs cell-edge round-trip drift, not zone
    # drift — adjacency between Mouth and BalticCoast cells is
    # reliable as long as the disk extends to the freshwater shoreline.
    # (Module-top imports for `pd`, `detect_utm_epsg`, `clip_sea_polygon_to_disk`
    # were added in Step 2b above.)

    mouth_lon, mouth_lat = river.waypoints[0]
    utm_epsg = detect_utm_epsg(mouth_lon, mouth_lat)

    sea_gdf = _load_or_fetch_marineregions(river)
    if sea_gdf is None or sea_gdf.empty:
        raise RuntimeError(
            f"{river.river_name}: Marine Regions returned no sea polygon. "
            f"Re-run when WFS recovers (or delete the cached payload at "
            f"tests/fixtures/_osm_cache/{river.short_name}_marineregions.json "
            f"if it has gone stale and re-run to re-fetch)."
        )
    # Pick the sea polygon nearest to the mouth. IHO sea-area polygons end
    # at the navigational coastline, which can be 0.5-1.5 km offshore from
    # a river mouth (Simojoki's Gulf of Bothnia boundary ends 0.0085° / ~945m
    # from its mouth). The plan-prescribed 1e-6° intersect tolerance was too
    # tight for that real-world gap, so we now select by closest distance
    # to the mouth point. query_named_sea_polygon already does the
    # bbox-centroid disambiguation upstream, so sea_gdf is typically a
    # single polygon; the .distance().idxmin() is robust to either case.
    mouth_pt = Point(river.waypoints[0])
    if sea_gdf.empty:
        raise RuntimeError(
            f"{river.river_name}: Marine Regions returned no sea polygon "
            f"in the mouth bbox. Re-fetch from WFS or move mouth waypoint."
        )
    nearest_idx = sea_gdf.geometry.distance(mouth_pt).idxmin()
    sea_polygon = sea_gdf.geometry.loc[nearest_idx]

    bc_polygon = clip_sea_polygon_to_disk(
        sea_polygon=sea_polygon,
        mouth_lon_lat=river.waypoints[0],
        radius_m=BALTICCOAST_RADIUS_M,
        utm_epsg=utm_epsg,
    )
    # The intersection can return a MultiPolygon if the disk straddles
    # an island, peninsula, or skerry (e.g., Tärnö near Mörrum, the many
    # small skerries near Tornio). Pass the geoms separately to
    # generate_cells so each piece tessellates independently. Polygon-
    # with-holes is also handled correctly by generate_cells (line 173
    # uses combined_buffer.intersection(poly) which preserves holes —
    # cells inside an island get empty intersection and are dropped).
    #
    # Edge case: shapely's intersection can return a GeometryCollection
    # when the disk and sea polygon share an exact boundary segment.
    # Filter to (Multi)Polygon members so generate_cells doesn't get
    # passed a degenerate Point/LineString that would silently produce
    # zero cells.
    if bc_polygon.geom_type == "MultiPolygon":
        bc_segments = list(bc_polygon.geoms)
    elif bc_polygon.geom_type == "Polygon":
        bc_segments = [bc_polygon]
    elif bc_polygon.geom_type == "GeometryCollection":
        bc_segments = [
            g for g in bc_polygon.geoms
            if g.geom_type in ("Polygon", "MultiPolygon")
        ]
        if not bc_segments:
            raise RuntimeError(
                f"{river.river_name}: BalticCoast intersection returned a "
                f"GeometryCollection with no polygon members "
                f"(only points/lines). Disk likely tangent to coastline."
            )
    else:
        raise RuntimeError(
            f"{river.river_name}: unexpected geometry type "
            f"{bc_polygon.geom_type!r} from clip_sea_polygon_to_disk"
        )
    bc_segment = {"segments": bc_segments, "frac_spawn": 0.0, "type": "sea"}
    bc_cell_factor = BALTICCOAST_CELL_FACTOR_OVERRIDE.get(
        river.short_name, BALTICCOAST_CELL_FACTOR_DEFAULT,
    )
    marine = generate_cells(
        reach_segments={"BalticCoast": bc_segment},
        cell_size=river.cell_size_m * bc_cell_factor,
        cell_shape="hexagonal",
        buffer_factor=1.0,
        min_overlap=0.1,
    )
    if marine.empty:
        raise RuntimeError(
            f"{river.river_name}: BalticCoast generated 0 cells "
            f"(disk radius={BALTICCOAST_RADIUS_M}m, "
            f"cell_size={river.cell_size_m * bc_cell_factor:.0f}m). "
            f"Try: (1) increase BALTICCOAST_RADIUS_M in "
            f"scripts/_generate_wgbast_physical_domains.py; "
            f"(2) lower BALTICCOAST_CELL_FACTOR_OVERRIDE for this river "
            f"(currently {bc_cell_factor}); "
            f"(3) move mouth waypoint {river.waypoints[0]} seaward if "
            f"the disk is dominated by land."
        )

    # Concat freshwater + marine. pd.concat of two GeoDataFrames may
    # return a plain DataFrame (CRS lost) on older geopandas — wrap
    # explicitly so downstream .geometry.buffer() and .to_file() work.
    cells = gpd.GeoDataFrame(
        pd.concat([fresh, marine], ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )
    # Renumber cell_ids with width adapted to the total count
    # (so C00001 and C99999 sort lexically).
    width = max(4, len(str(len(cells))))
    cells["cell_id"] = [f"C{i+1:0{width}d}" for i in range(len(cells))]

    log.info("Generated %d cells (fresh=%d + BalticCoast=%d)",
             len(cells), len(fresh), len(marine))
    log.info("Per-reach distribution:")
    for reach, count in cells["reach_name"].value_counts().sort_index().items():
        log.info("  %-12s %d cells", reach, count)

    # --- Adjacency sanity check ------------------------------------------
    mouth_subset = cells[cells["reach_name"] == "Mouth"]
    marine_subset = cells[cells["reach_name"] == "BalticCoast"]
    if mouth_subset.empty:
        raise RuntimeError(
            f"{river.river_name}: 0 cells assigned to 'Mouth' reach — "
            f"check REACH_NAMES + partition output."
        )
    # Quick empty check before the UTM reproject + adjacency math.
    # Use the row-level emptiness rather than a union (cheaper; the
    # full union is computed in UTM 8 lines below for the actual
    # adjacency test).
    if marine_subset.empty or marine_subset.geometry.is_empty.all():
        raise RuntimeError(
            f"{river.river_name}: BalticCoast geometry empty after concat."
        )
    # Project both subsets to UTM for a true-meters adjacency check.
    # A WGS84-degree buffer is anisotropic at high latitudes (1e-5° is
    # ~0.45 m east-west at 65°N, ~1.1 m north-south) — the Tornio coast
    # runs roughly N-S so a degree-buffer's E-W slack would be the
    # constraint. UTM gives uniform meters; 5 m absorbs UTM↔WGS84
    # round-trip drift comfortably without false-positives.
    mouth_utm = mouth_subset.to_crs(epsg=utm_epsg)
    marine_utm = marine_subset.to_crs(epsg=utm_epsg)
    marine_union_utm = marine_utm.geometry.union_all()
    hits = mouth_utm.geometry.buffer(5.0).intersects(marine_union_utm).sum()
    if hits == 0:
        raise RuntimeError(
            f"{river.river_name}: BalticCoast not adjacent to Mouth — "
            f"disk geometry leaves a gap (radius {BALTICCOAST_RADIUS_M}m). "
            f"Increase radius or move mouth waypoint seaward."
        )

    # Rename columns to match the shapefile-loader contract
    cells = cells.rename(columns=COLUMN_RENAME)
    # Re-cast ID_TEXT to string explicitly — pandas can demote dtype
    # across concat; this keeps the DBF column type consistent.
    cells["ID_TEXT"] = cells["ID_TEXT"].astype(str)

    # Clear any stale Shapefile/* from a prior run (Nemunas leftover)
    for pat in ("*.shp", "*.shx", "*.dbf", "*.prj", "*.cpg"):
        for stale in shp_dir.glob(pat):
            stale.unlink()

    out_path = shp_dir / f"{river.stem}.shp"
    cells.to_file(out_path, driver="ESRI Shapefile")
    log.info("Wrote %s (%d cells, EPSG:4326)", out_path.relative_to(ROOT), len(cells))
    return out_path


def main():
    for river in RIVERS:
        write_river_shapefile(river)
    log.info("=" * 60)
    log.info("All 4 WGBAST river shapefiles regenerated with real geography.")


if __name__ == "__main__":
    main()
