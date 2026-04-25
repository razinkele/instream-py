# WGBAST rivers — extend Tornionjoki + materialize BalticCoast cells (design v4)

**Date:** 2026-04-25 (v4 after Create Model integration audit)
**Scope:** Two independent PRs.
- **PR-1 (Tornionjoki regex):** `scripts/_fetch_wgbast_osm_polylines.py`, regenerated `tests/fixtures/example_tornionjoki/`.
- **PR-2 (BalticCoast cells + WGBAST yaml cleanup + helper refactor):**
  - new `app/modules/create_model_marine.py` (sea-polygon helpers; v3-introduced)
  - **new `app/modules/create_model_river.py`** (connectivity filter + along-channel partition; **v4-introduced**)
  - `scripts/_generate_wgbast_physical_domains.py` (refactored to import the helpers — net thinner)
  - `scripts/_wire_wgbast_physical_configs.py` (per-river BalticCoast tuning + orphan reach cleanup)
  - `app/modules/create_model_panel.py` (small refactor — re-export `_query_marine_regions` from the new module)
  - all 4 `configs/example_*.yaml` (tune BalticCoast + drop orphan reaches)
  - regenerated 4 fixtures

**Out of scope:** Tornionjoki juvenile-growth calibration; basin-wide shared marine state; salinity time-series for the new marine cells; **new UI buttons consuming the v4 helpers** (deferred to follow-up PR-3); **Create Model CSV export format bug** (deferred to follow-up PR-4 — see "Deferred follow-ups").

## Why v3 (changes from v2)

The v2 spec invented a per-river OSM-coastline + disk-minus-land pipeline. Comparison against `app/modules/create_model_panel.py` revealed that:

- **The Create Model UI already has a complete sea-reach workflow.** A "🌊 Sea" button at `create_model_panel.py:229` calls `_query_marine_regions(bbox)` (line 86), filters the result to the polygon containing the bbox centre (lines 744–752), and pipes the polygon through `generate_cells(..., type="sea")` (lines 1136–1147).
- **Marine Regions WFS returns named IHO sea polygons** (`Gulf of Bothnia` for the 3 northern rivers, `Baltic Sea` for Mörrumsån — confirmed by probe). These are **real, sea-only polygons** — no land-vs-sea classifier needed.
- **The cell-id format `f"C{i+1:04d}"` is already standardized** at `create_model_panel.py:1153` and `create_model_grid.py:208`. Both freshwater and sea cells use it consistently.
- **A future Create Model "Add a sea reach to my custom river" workflow** wants the same algorithm the WGBAST batch generator needs.

v3 collapses v2's bespoke OSM-coastline pipeline into a thin reuse of the Create Model framework. The disk geometry survives (UTM-accurate, true-meters radius), but the coastline-clip + land-vs-sea classifier is replaced by `sea_polygon.intersection(disk)`, where `sea_polygon` is whatever Marine Regions WFS returns for the bbox. Sea-only by definition.

## Why v4 (changes from v3)

The v3 spec moved the marine-polygon helpers into `app/modules/`. A follow-up audit ("can other WGBAST script logic move into the Create Model framework?") identified two additional pure-Python algorithms in `_generate_wgbast_physical_domains.py` that have no Shiny dependency, are not WGBAST-specific in their geometric semantics, and would be reusable by a future Create Model UI affordance:

- **`_load_osm_polygons_filtered`** (~50 lines) — STRtree-backed BFS that prunes water polygons to the connected component touching a centerline. Today buried in `scripts/`. Naturally a `create_model_*` capability.
- **`build_reach_segments_from_polygons`** (~40 lines) — partitions polygons into N reaches by along-channel distance from a mouth point. Today hardcodes 4 WGBAST reach names. Naturally generalizes to "give me N polygon groups by along-channel distance."

v4 extracts both into a new `app/modules/create_model_river.py` and rewrites `_generate_wgbast_physical_domains.py` to import them. The WGBAST batch generator becomes thin orchestration; the Create Model framework gains two reusable building blocks. **No new UI buttons in PR-2** — the helpers sit ready for a future PR-3.

While auditing the integration, an empirical probe (`scripts/_probe_create_model_csv_format.py`) also surfaced a **separate latent bug**: `create_model_export.py::export_template_csvs` writes per-reach CSVs in a layout (`flow,cell_id_1,cell_id_2,...` header rows) that `src/salmopy/io/hydraulics_reader.py::_parse_hydraulic_csv` cannot parse (it expects the inSALMO format: comment lines, count line, flow-values line, cell-per-row data lines). Loading raises `ValueError: invalid literal for int() with base 10: 'flow'`. Documented under "Deferred follow-ups"; fix is independent of the WGBAST work.

## Why v2 (kept from v2 → v3)

The v2 → v3 transition keeps:
- Use of the existing `BalticCoast` reach name (already in all 4 WGBAST yamls + CSVs).
- PR-1 / PR-2 split.
- Per-river `BalticCoast` parameter tuning (0.95 Bothnian Bay, 0.90 Hanöbukten).
- Drop the 4 orphan Lithuanian template reaches.
- Fail-fast error handling (no silent fallbacks).
- Both grids pinned to the same UTM zone.
- Junction-graph adjacency assertion in tests.

## Why v1 (kept from v1 → v2)

The original v1 surfaced the right *problems* (Tornionjoki extent + missing marine reach) but proposed the wrong *solution shape*. v2/v3 keep the problem framing.

## Problem (unchanged from v1)

1. **Tornionjoki extent is too small.** OSM line-way fetch matches only `^(Tornionjoki|Torne älv|Torneälven|Torneå älv|Torne)$` — misses Muonionjoki tributary (~150 km of the basin). Tornionjoki ends up with 71 OSM polygons → 860 hex cells, vs Simojoki at 87 polygons → 2595 cells.
2. **No marine cells at any WGBAST river mouth.** Configs declare a `BalticCoast` reach with junction integers `(5, 6)`, but the shapefiles contain only `Mouth/Lower/Middle/Upper`.
3. **Stale Lithuanian template reaches.** Each WGBAST YAML carries 4 orphan reaches (`Skirvyte`, `Leite`, `Gilija`, `CuronianLagoon`) inherited from the example_baltic template.

## Goals (PR-2 wording revised; PR-1 unchanged)

**PR-1:** Tornionjoki's freshwater extent grows to include Muonionjoki. Cell count rises above Simojoki.

**PR-2 (after PR-1 lands):**
- Each WGBAST fixture has shapefile cells under the existing `BalticCoast` reach name, generated from a Marine Regions IHO polygon clipped to a 10 km disk at the river mouth.
- BalticCoast cells are spatially adjacent to Mouth cells.
- A new module `app/modules/create_model_marine.py` exposes the disk-clipped sea-polygon helper. Both the WGBAST batch generator AND the Create Model UI consume it (UI integration is a small refactor, not a new feature — see Components §6).
- Per-river `BalticCoast` parameter tuning.
- Stale Lithuanian template reaches removed.

## Non-goals (v3)

- Adding new UI features to Create Model (the helper extraction is purely a refactor; the existing 🌊 Sea button keeps its current behaviour). A future task may add a "Generate sea reach near point" button — the helper is designed to support that, but it's not implemented in PR-2.
- Per-tributary multi-reach decomposition of Muonionjoki.
- Salinity time-series.
- Tornionjoki juvenile-growth calibration.

## Architecture overview

### PR-1 (one-line + regenerate Tornionjoki)

```
scripts/_fetch_wgbast_osm_polylines.py     [MOD]   Tornionjoki regex extension
tests/fixtures/_osm_cache/                 [MOD]   refresh tornionjoki line cache
tests/fixtures/example_tornionjoki/        [MOD]   regenerated shapefile (more cells)
```

### PR-2 (BalticCoast cells via Marine Regions + helper refactor + WGBAST yaml cleanup)

```
app/modules/
├── create_model_marine.py                 [NEW]  query_named_sea_polygon + clip_sea_polygon_to_disk
├── create_model_river.py                  [NEW]  filter_polygons_by_centerline_connectivity + partition_polygons_along_channel
└── create_model_panel.py                  [MOD]  thin wrapper: re-export from create_model_marine

scripts/
├── _generate_wgbast_physical_domains.py   [MOD]  imports helpers from create_model_marine + create_model_river (net thinner)
└── _wire_wgbast_physical_configs.py       [MOD]  per-river BalticCoast tuning + orphan-reach cleanup

configs/
├── example_tornionjoki.yaml               [MOD]  tuned BalticCoast params; orphan reaches removed
├── example_simojoki.yaml                  [MOD]  same
├── example_byskealven.yaml                [MOD]  same
└── example_morrumsan.yaml                 [MOD]  same

tests/fixtures/example_*/                  [MOD]  regenerated shapefile (5 reaches)
```

Module-level constants in `_generate_wgbast_physical_domains.py`:
```python
BALTICCOAST_RADIUS_M = 10_000.0
BALTICCOAST_CELL_FACTOR = 4.0   # BalticCoast cell_size = river.cell_size_m × this
```

## Components — PR-1

### `_fetch_wgbast_osm_polylines.py` Tornionjoki regex change

```python
# Before
name_regex="^(Tornionjoki|Torne älv|Torneälven|Torneå älv|Torne)$"
# After
name_regex="^(Tornionjoki|Torne älv|Torneälven|Torneå älv|Torne|Muonionjoki|Muonio älv|Muonio)$"
```

Existing bbox `(65.5, 22.8, 68.6, 25.6)` already covers the Muonio basin. Polygon query (no name filter) doesn't change.

After regenerating Tornionjoki, sanity check:
- Tornionjoki cell count > Simojoki cell count.
- Tornionjoki centerline length grows from ~151 km to ~270 km (visible in `scripts/_diag_tornionjoki_polygon_filter.py`).

PR-1 is a single-line code change + a fixture regeneration. Ship by itself.

## Components — PR-2

### 1. New `app/modules/create_model_marine.py` shared helper

Two functions, both pure-Python (no Shiny dependency, no IO beyond the WFS request — same constraints as `create_model_grid.py`):

```python
"""Marine sea-reach geometry helpers shared by Create Model UI and the
WGBAST batch generator.

`query_named_sea_polygon(bbox)` is the same Marine Regions WFS query
that `create_model_panel.py::_query_marine_regions` did privately. It is
moved here so the WGBAST scripts can call it directly without spawning
a Shiny session.

`clip_sea_polygon_to_disk(...)` is a new helper: given an already-fetched
sea polygon and a river-mouth point, returns the polygon clipped to a
true-meters disk around the mouth. The clip is done in UTM so the radius
is in actual metres regardless of latitude.
"""
from __future__ import annotations
import requests
import geopandas as gpd
from shapely.geometry import Point, Polygon, MultiPolygon, box
from shapely.ops import unary_union

MARINE_REGIONS_WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"


def query_named_sea_polygon(
    bbox_wgs84: tuple[float, float, float, float],   # west, south, east, north
    timeout_s: int = 60,
) -> gpd.GeoDataFrame | None:
    """Query Marine Regions WFS for IHO sea-area polygons within bbox.

    Returns a GeoDataFrame in EPSG:4326 with columns ['name', 'geometry'],
    post-filtered to features whose geometry actually intersects the bbox
    (Marine Regions returns global polygons that merely touch the bbox).
    Returns None on network/HTTP failure.
    """
    west, south, east, north = bbox_wgs84
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "MarineRegions:iho",
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": f"{west},{south},{east},{north},EPSG:4326",
    }
    try:
        resp = requests.get(MARINE_REGIONS_WFS, params=params, timeout=timeout_s)
        resp.raise_for_status()
        geoj = resp.json()
    except Exception:
        return None
    if not geoj.get("features"):
        return None
    gdf = gpd.GeoDataFrame.from_features(geoj["features"], crs="EPSG:4326")
    view_box = box(*bbox_wgs84)
    gdf = gdf[gdf.geometry.intersects(view_box)].copy()
    # Prefer polygons that contain the bbox centroid (eliminates spurious
    # globe-spanning matches like Bering Sea).
    if len(gdf) > 1:
        centre = view_box.centroid
        covers = gdf[gdf.geometry.contains(centre)]
        if len(covers) > 0:
            gdf = covers.copy()
    if "name" not in gdf.columns:
        gdf["name"] = ""
    return gdf[["name", "geometry"]].reset_index(drop=True)


def clip_sea_polygon_to_disk(
    sea_polygon: Polygon | MultiPolygon,
    mouth_lon_lat: tuple[float, float],
    radius_m: float,
    utm_epsg: int,
) -> Polygon | MultiPolygon:
    """Return `sea_polygon` clipped to a true-meters disk around the mouth.

    Algorithm (no land subtraction needed — sea_polygon is sea-only by
    definition):
      1. Reproject sea_polygon and mouth point to `utm_epsg`.
      2. Build a true-meters disk: mouth_pt.buffer(radius_m).
      3. Intersect: clipped = sea_polygon_utm.intersection(disk).
      4. Reproject the result back to EPSG:4326. Return.

    Raises ValueError if the intersection is empty (sea polygon does not
    cover the mouth at all — likely a wrong waypoint or zoomed-in bbox).
    """
    if sea_polygon.is_empty:
        raise ValueError("sea_polygon is empty; nothing to clip")
    sea_gdf = gpd.GeoDataFrame(geometry=[sea_polygon], crs="EPSG:4326").to_crs(epsg=utm_epsg)
    mouth_gdf = gpd.GeoDataFrame(
        geometry=[Point(mouth_lon_lat)], crs="EPSG:4326"
    ).to_crs(epsg=utm_epsg)
    disk = mouth_gdf.geometry.iloc[0].buffer(radius_m)
    clipped = sea_gdf.geometry.iloc[0].intersection(disk)
    if clipped.is_empty:
        raise ValueError(
            f"sea polygon does not intersect a {radius_m}m disk at "
            f"mouth {mouth_lon_lat} — wrong waypoint?"
        )
    out = gpd.GeoDataFrame(geometry=[clipped], crs=f"EPSG:{utm_epsg}").to_crs("EPSG:4326")
    return out.geometry.iloc[0]
```

Key advantages over v2:
- **No coastline cache.** Marine Regions data is fetched once at generation time. No `_osm_cache/<river>_coastline.json` files.
- **No land-vs-sea classifier.** Marine Regions IHO polygons are sea-only.
- **No `source_lon_lat` parameter.** The disk doesn't need a "land side" to exclude.
- **Reusable.** The Create Model UI's existing fetch_sea handler can call into the same helper.

### 1b. New `app/modules/create_model_river.py` shared helper (v4)

Two functions extracted from `_generate_wgbast_physical_domains.py`. Both pure-Python (no Shiny dependency, no IO — same constraints as `create_model_grid.py`).

```python
"""Centerline-driven river-polygon analysis helpers.

Extracted from scripts/_generate_wgbast_physical_domains.py so that
both the WGBAST batch generator AND a future Create Model UI button
can share the algorithms.
"""
from __future__ import annotations
from typing import Sequence
from shapely.geometry import LineString, Point, Polygon, MultiPolygon
from shapely.ops import unary_union


def filter_polygons_by_centerline_connectivity(
    centerline: list[LineString] | LineString,
    polygons: Sequence[Polygon | MultiPolygon],
    tolerance_deg: float = 0.0005,    # ~55 m at typical river latitudes
    max_polys: int = 2000,
    label: str | None = None,         # for log messages; e.g. "Tornionjoki"
) -> list[Polygon | MultiPolygon]:
    """Return only the polygons in the connected component that touches
    the centerline.

    Algorithm (graph flood-fill):
      1. Buffer each polygon by `tolerance_deg` (small bridge over OSM
         tagging gaps).
      2. Build an STRtree spatial index for fast neighbor lookup.
      3. Seed the visited-set with polygons whose buffered envelope
         intersects the buffered centerline.
      4. BFS: for each visited polygon, find polygons whose buffered
         envelope intersects → add to visited.
      5. Return only visited polygons (capped at `max_polys`).

    The cap protects against the centerline accidentally touching a
    sea polygon and blowing up the connected component.
    """


def partition_polygons_along_channel(
    centerline: list[LineString] | LineString,
    polygons: Sequence[Polygon | MultiPolygon],
    mouth_lon_lat: tuple[float, float],
    n_reaches: int,
) -> list[list[Polygon | MultiPolygon]]:
    """Partition polygons into N groups by ALONG-channel distance from
    the mouth.

    Each polygon's centroid is projected onto the centerline; polygons
    are sorted by along-line distance from the mouth and split into N
    equal-count quartile groups (the last group absorbs rounding).

    Returns a list of N lists. Caller assigns reach names + frac_spawn.
    For < N polygons (`len(polygons) < n_reaches`), returns whatever
    polygons exist with the rest empty; caller decides whether to
    raise or fall back to a centerline-line split.
    """
```

The two functions are extracted by parameterising the existing private functions:
- `_load_osm_polygons_filtered(river, centerline)` becomes `filter_polygons_by_centerline_connectivity(centerline, polygons, ...)` — the `River` dataclass is removed; the caller passes the polygons directly and a `label` for logging.
- `build_reach_segments_from_polygons(river, centerline, polygons)` becomes `partition_polygons_along_channel(centerline, polygons, mouth, n_reaches)` — returns N lists of polygons. The WGBAST caller wraps these in the `{"segments": ..., "frac_spawn": ..., "type": "water"}` dict it already expects (see §3b code snippet).

### 2. `create_model_panel.py` refactor

Replace the private `_query_marine_regions` (line 86) with `from .create_model_marine import query_named_sea_polygon`. The handler at line 727 (`_on_fetch_sea`) keeps its existing body but consumes the moved function.

This is a 5-line patch — extract + re-export. Behaviour-preserving.

### 3a. WFS payload caching

The WGBAST generator caches the Marine Regions response to
`tests/fixtures/_osm_cache/<short_name>_marineregions.json` (same flat-list
format as the existing OSM line-way / polygon caches). On second and
subsequent runs the cache is read instead of hitting WFS, making
fixture regeneration fully offline-clean. Pass `--refresh` (mirroring
the existing flag in `_fetch_wgbast_osm_polylines.py`) to force a
re-fetch.

### 3b. `_generate_wgbast_physical_domains.py` — BalticCoast cell generation

After the existing `build_reach_segments(river)` call returns the 4 freshwater reach segments:

```python
from app.modules.create_model_marine import (
    query_named_sea_polygon, clip_sea_polygon_to_disk,
)
from app.modules.create_model_utils import detect_utm_epsg

# Pin both grids to the SAME UTM zone (freshwater centroid's zone)
all_geoms = []
for info in fresh_segments.values():
    all_geoms.extend(info["segments"])
fresh_centroid = unary_union(all_geoms).centroid
utm_epsg = detect_utm_epsg(fresh_centroid.x, fresh_centroid.y)

# Marine Regions returns the IHO polygon (`Gulf of Bothnia` or `Baltic Sea`).
# 0.5° bbox around mouth is wide enough to ensure the polygon is returned
# but narrow enough to keep WFS payloads small.
mouth_lon, mouth_lat = river.waypoints[0]
bbox = (mouth_lon - 0.5, mouth_lat - 0.5, mouth_lon + 0.5, mouth_lat + 0.5)
sea_gdf = query_named_sea_polygon(bbox)
if sea_gdf is None or sea_gdf.empty:
    raise RuntimeError(
        f"{river.river_name}: Marine Regions returned no sea polygon for "
        f"mouth {river.waypoints[0]}. Re-run when WFS recovers."
    )
# Use the polygon that actually covers the mouth point (post-filter
# redundant with query_named_sea_polygon's own filter, but defensive).
mouth_pt = Point(mouth_lon, mouth_lat)
sea_gdf = sea_gdf[sea_gdf.geometry.contains(mouth_pt)]
if sea_gdf.empty:
    raise RuntimeError(
        f"{river.river_name}: no sea polygon contains the mouth point. "
        f"Mouth waypoint may need updating."
    )
sea_polygon = sea_gdf.geometry.iloc[0]

bc_polygon = clip_sea_polygon_to_disk(
    sea_polygon=sea_polygon,
    mouth_lon_lat=river.waypoints[0],
    radius_m=BALTICCOAST_RADIUS_M,
    utm_epsg=utm_epsg,
)
bc_segment = {"segments": [bc_polygon], "frac_spawn": 0.0, "type": "sea"}
```

Two `generate_cells` calls (per the v2 design — kept verbatim). The renumber-cell-id logic uses the standardised format from `create_model_panel.py:1153`:

```python
fresh = generate_cells(
    reach_segments=fresh_segments,
    cell_size=river.cell_size_m,
    cell_shape="hexagonal",
    buffer_factor=river.buffer_factor,
    min_overlap=0.1,
)
marine = generate_cells(
    reach_segments={"BalticCoast": bc_segment},
    cell_size=river.cell_size_m * BALTICCOAST_CELL_FACTOR,
    cell_shape="hexagonal",
    buffer_factor=1.0,
    min_overlap=0.1,
)
combined = pd.concat([fresh, marine], ignore_index=True)
combined["cell_id"] = [f"C{i+1:04d}" for i in range(len(combined))]
```

(Cell-id is informational, not a foreign key into `Depths.csv`/`Vels.csv` which are indexed by row position.)

### 4. Adjacency sanity check

Same as v2 — both grids in the same `utm_epsg` mean residual round-trip drift is sub-meter; a 1e-7° buffer absorbs it:

```python
reach_col = "REACH_NAME" if "REACH_NAME" in combined.columns else "reach_name"
mouth_subset = combined[combined[reach_col] == "Mouth"]
marine_subset = combined[combined[reach_col] == "BalticCoast"]
if marine_subset.empty:
    raise RuntimeError(f"{river.river_name}: BalticCoast generated 0 cells.")
marine_union = marine_subset.geometry.unary_union
if marine_union is None or marine_union.is_empty:
    raise RuntimeError(f"{river.river_name}: BalticCoast geometry empty after concat.")
hits = mouth_subset.geometry.buffer(1e-7).intersects(marine_union).sum()
if hits == 0:
    raise RuntimeError(
        f"{river.river_name}: BalticCoast not adjacent to Mouth — "
        f"disk geometry leaves a gap (radius {BALTICCOAST_RADIUS_M}m). "
        f"Increase radius or move mouth waypoint seaward."
    )
```

### 5. `_wire_wgbast_physical_configs.py` — per-river BalticCoast tuning + orphan cleanup

Unchanged from v2 (per-river tuning of `fish_pred_min` to 0.95 / 0.90; drop Skirvyte/Leite/Gilija/CuronianLagoon; re-expand BalticCoast-Depths.csv/Vels.csv to new cell counts using the v0.46.0 H7 algorithm).

### 6. Create Model UI continuity

The 🌊 Sea button at `create_model_panel.py:229` keeps its existing behaviour: user clicks it, current bbox is queried, returned polygon is added to the reach list as `type="sea"`. No new UI work in PR-2.

Future enhancement (deferred — out of scope for PR-2): a "Add coastal reach near current river mouth" button that calls `clip_sea_polygon_to_disk` on top of `query_named_sea_polygon` to produce a per-river sea reach without the user needing to tag a separately-fetched polygon. The helper is already shaped for this.

## Error handling

- **Marine Regions WFS unreachable / 5xx** → raise `RuntimeError` with the river name. Re-run when WFS recovers. The Marine Regions service has been stable for years; this is a soft failure mode.
- **WFS returns no polygon containing the mouth** → raise `RuntimeError` (mouth waypoint is wrong, or the IHO regions don't cover it).
- **`clip_sea_polygon_to_disk` returns empty** → `ValueError` from the helper, caller wraps as `RuntimeError`.
- **BalticCoast generates 0 cells / not adjacent to Mouth** → `RuntimeError` (same as v2).

No silent fallbacks at any layer.

## Testing

Three test layers, all fast (<30 s) and network-free at CI time. WFS is hit only at fixture-generation time; tests use cached `_osm_cache/<river>_marineregions.json` payloads committed alongside fixtures (mirrors the existing OSM line-way / polygon cache pattern).

### `tests/test_create_model_marine.py` (new)

Pure-Python unit tests of `clip_sea_polygon_to_disk`:

1. **Basic intersection (success):** sea_polygon = box(0, 0, 2, 2) (deg), mouth at (1.0, 1.0), radius 50_000m, UTM zone 33 (Sweden) → result has area > 0 and lies inside the disk's circular bound.
2. **Mouth outside polygon (raises ValueError):** sea = box(0, 0, 1, 1), mouth at (5, 5), radius 1_000_000m → intersection empty.
3. **Tiny radius (raises ValueError):** sea = box(0, 0, 1, 1), mouth at (0.5, 0.5), radius 1m, UTM zone 33 → 1m disk doesn't intersect at all when reprojected back, OR clip is sub-mm. (Edge case to confirm.)

### `tests/test_create_model_marine.py::test_query_named_sea_polygon_offline`

Mock the requests.get response with a fake WFS GeoJSON payload to exercise the post-filter logic without hitting the network. Two scenarios:
1. Multiple polygons, one contains bbox centroid → only that one returned.
2. WFS returns 500 → returns None.

### `tests/test_wgbast_river_extents.py` (new)

For each of the 4 rivers, after running the generator end-to-end:

1. Reach name set is exactly `{Mouth, Lower, Middle, Upper, BalticCoast}`.
2. BalticCoast cell count ∈ `[100, 3000]`.
3. BalticCoast cells lie SOUTH of (or coastward of) the Mouth centroid mean.
4. **PR-1 acceptance:** Tornionjoki cell count > Simojoki cell count.
5. **No orphan reaches:** YAML for each river has exactly 5 entries under `reaches:`.

### `tests/test_wgbast_river_extents.py::test_mouth_balticcoast_topology`

For each river:
1. **Geometric adjacency:** `mouth_subset.geometry.buffer(1e-7).intersects(balticcoast_union).sum() >= 1`.
2. **Junction graph adjacency:** `BalticCoast.upstream_junction == Upper.downstream_junction`.

### Existing tests

- `tests/test_multi_river_baltic.py::test_fixture_loads_and_runs_3_days`: keeps passing.
- `tests/test_multi_river_baltic.py::test_latitudinal_smolt_age_gradient[Tornionjoki]`: stays xfailed until Workstream B (juvenile-growth calibration).
- The Create Model panel's existing `_on_fetch_sea` test (if any — TBC; if absent, NOT in scope to add) keeps passing because the helper extraction is behaviour-preserving.

## Migration / rollout

- PR-1 ships independently. One-line code change + Tornionjoki fixture regenerate. ~15 min.
- PR-2 ships after PR-1 lands. Larger blast radius: 4 fixtures regenerated, 4 YAMLs cleaned + tuned, 2 module changes (1 new + 1 refactor), 2 new test files. The full WGBAST regeneration is idempotent.
- After PR-2, server deploy uses the existing `/deploy` skill.

## Open questions

1. **Salinity in BalticCoast-TimeSeriesInputs.csv.** Same as v2 — deferred.
2. **Marine-zone integration.** Same as v2 — `marine/survival.py:257` matches "estuary" not "BalticCoast", so no collision. When smolts transit BalticCoast cells they're simultaneously in the zone-based marine pipeline; this is by design.
_(WFS payload caching was an open question; resolved in v3 — see Components §3a below.)_

## Reviewer findings addressed (v1 → v2 → v3)

| # | v1 issue | v2 resolution | v3 change |
|---|---|---|---|
| 1 | Invents `Estuary` reach when `BalticCoast` already in YAML/CSVs | Use `BalticCoast` reach name throughout | Same |
| 2 | Junction integers unspecified | YAML already declares (5, 6) | Same |
| 3 | `Estuary` collides with marine-zone string match | `BalticCoast` doesn't collide | Same |
| 4 | `cell_id + len(fresh)` crashes (cell_id is string) | Adaptive-width string format | Switched to standardised `f"C{i+1:04d}"` from `create_model_panel.py:1153` |
| 5 | Empty-coastline fallback returns inland disk | Removed: empty cache raises | **Removed entire coastline pipeline** — Marine Regions polygon is sea-only |
| 6 | BalticCoast `fish_pred_min=0.65` lethal for Bothnian smolts | Per-river tuning: 0.95 / 0.90 | Same |
| 7 | CSV format vague | Format documented; H7 algorithm reuse | Same |
| 8 | Stale Lithuanian template reaches | Drop them | Same |
| 9 | source_lon_lat inside disk inverts classifier | Pre-check raises | **No longer applies** — no land/sea classifier in v3 |
| 10 | UTM zone mismatch between freshwater + marine grids | Pin both to `freshwater_centroid` UTM | Same |
| 11 | Two orthogonal fixes bundled | Split into PR-1 + PR-2 | Same |
| 12 | Cell-count bounds `[200, 2000]` too tight | Widen to `[100, 3000]` | Same |
| 13 | Per-river estuary fields over-engineered | Module-level constants | Same |
| 14 | Tests cover geometry but not topology | Junction-graph adjacency assertion | Same |

### v3-specific changes (Create Model framework reuse)

- **A**: Replace OSM coastline + disk-minus-land with Marine Regions WFS + disk-intersect. Eliminates ~150 lines of bespoke coastline-clip code.
- **B**: Move the helper from `scripts/_wgbast_balticcoast.py` to `app/modules/create_model_marine.py`. Now importable from both UI and batch generator.
- **C**: Standardise cell-id format on `f"C{i+1:04d}"` (matches `create_model_panel.py:1153`).
- **D**: Refactor `_query_marine_regions` out of `create_model_panel.py` into the shared module.
- **E**: Drop the `_fetch_wgbast_osm_polylines.py` coastline-fetch addition that v2 prescribed (no longer needed).

### v4-specific changes (continued Create Model integration)

- **F**: Move `_load_osm_polygons_filtered` and `build_reach_segments_from_polygons` from `scripts/_generate_wgbast_physical_domains.py` to a new `app/modules/create_model_river.py`. Both helpers become first-class `create_model_*` capabilities reusable by future UI features.
- **G**: Generalize `partition_polygons_along_channel` to take an explicit `n_reaches` parameter (drops the WGBAST-specific hardcoded `["Mouth", "Lower", "Middle", "Upper"]` list; caller maps groups to reach names).
- **H**: WGBAST batch generator becomes thin orchestration: `River` dataclass + per-river YAML wiring + the marine-cell glue. The geometric algorithms live in `app/modules/`.
- **I**: Surfaced (but **NOT** fixed in this spec): `create_model_export.py::export_template_csvs` writes per-reach CSVs in a layout that `src/salmopy/io/hydraulics_reader.py::_parse_hydraulic_csv` cannot parse. Documented in "Deferred follow-ups" → PR-4.

## Deferred follow-ups (intentionally out of scope for PR-2)

**PR-3: Wire Create Model UI buttons to the v4 helpers.** New affordances on the existing Create Model panel that consume the now-shared algorithms. Sketch:

- "Auto-extract main river system" button on the OSM-fetch panel: takes the user's currently-selected centerline + all fetched water polygons, runs `filter_polygons_by_centerline_connectivity`, replaces the polygon set with the connected component. Eliminates the manual "click each polygon to keep" workflow for users with > ~50 polygons.
- "Auto-split into N reaches" slider + button: takes the user's current polygon set, runs `partition_polygons_along_channel` with the chosen N, names the resulting reaches sequentially (e.g. "R1"…"RN"), and assigns frac_spawn from a default schedule.
- "Find by name" search box on the OSM fetch panel: post-filters `query_waterways` results by a name regex. Mirrors the WGBAST Overpass `name~` query but uses the local PBF.

Estimated work: 300–500 lines across `create_model_panel.py` (UI), `create_model_river.py` (already in PR-2, minor signature additions if needed), and tests. Independent of PR-2; ships when the underlying helpers are stable.

**PR-4: Fix `create_model_export.py` CSV format.** `export_template_csvs` currently writes:

```
flow,C0001,C0002,...
0.5,0.234,0.198,...
1.0,0.288,0.243,...
```

But `_parse_hydraulic_csv` (the simulation loader) expects:

```
;comment
N,Number of flows in table,...
,0.5,1.0,...
C0001,0.234,0.288,...
C0002,0.198,0.243,...
```

A fixture exported from the Create Model UI today raises `ValueError: invalid literal for int() with base 10: 'flow'` when loaded. Fix: rewrite `export_template_csvs` to emit the inSALMO format (using `_expand_per_cell_csv` from `_wire_wgbast_physical_configs.py:211` as a working reference, or extracting it to a third shared helper). Add a test that exports a Create Model fixture and round-trips it through `SalmopyModel.__init__`. Unblocks any user who has ever attempted to use a Create-Model-built model in simulation. ~50 lines of code + a regression test. Probe at `scripts/_probe_create_model_csv_format.py` confirms the bug; ships from there directly. Independent of PR-2.
