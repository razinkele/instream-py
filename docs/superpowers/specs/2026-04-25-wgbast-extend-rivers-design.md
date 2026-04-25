# WGBAST rivers — extend Tornionjoki + materialize BalticCoast cells (design v2)

**Date:** 2026-04-25 (v2 after multi-reviewer pass)
**Scope:** Two independent PRs.
- **PR-1 (Tornionjoki regex):** `scripts/_fetch_wgbast_osm_polylines.py`, regenerated `tests/fixtures/example_tornionjoki/`.
- **PR-2 (BalticCoast cells + WGBAST yaml cleanup):** `scripts/_generate_wgbast_physical_domains.py`, `scripts/_wire_wgbast_physical_configs.py`, new `scripts/_wgbast_balticcoast.py` helper, all 4 `configs/example_*.yaml`, regenerated 4 fixtures.

**Out of scope:** Tornionjoki juvenile-growth calibration; basin-wide shared marine state; salinity time-series for the new marine cells (deferred — see Open questions).

## Why v2 (changes from v1)

The v1 spec invented a new reach name `Estuary` and an entire generation pipeline. Multi-tool review surfaced:

- **`example_baltic.yaml` already defines a `BalticCoast` reach** (lines 370–388) with the marine-typical hydrology values v1 wanted to recreate.
- **All 4 WGBAST fixtures already ship `BalticCoast-{Depths,Vels,TimeSeriesInputs}.csv`** files — only the shapefile cells are missing.
- **All 4 WGBAST `configs/example_*.yaml` already declare a `BalticCoast` reach** with `upstream_junction: 5, downstream_junction: 6`, downstream of `Upper: 4→5`. The YAML chain is already mouth-to-sea correct; only geometry is missing.
- **`scripts/generate_baltic_example.py:419-485`** has a working precedent: build a sea polygon by `rectangle.difference(land_polygon)` and pass it to `generate_cells` with `type="sea"`.
- Naming a new reach `Estuary` would collide with the **zone-based marine model** (`src/salmopy/marine/`) that uses `"Estuary"` as a string literal in `marine/survival.py:257` and a 14-day residency timer in `marine/domain.py:129`.
- v1's `cell_id + len(fresh)` arithmetic would crash because `cell_id` is the string format `"C0001"` (per `app/modules/create_model_grid.py:208`).

v2 keeps every geometric idea from v1 (UTM disk, coastline clip, adjacency sanity check) but uses the existing `BalticCoast` reach name + `type="sea"` plumbing. This converts the work from "invent new infrastructure" to "fill an empty slot in existing infrastructure."

## Problem (unchanged from v1)

1. **Tornionjoki extent is too small.** OSM line-way fetch matches only `^(Tornionjoki|Torne älv|Torneälven|Torneå älv|Torne)$` — misses Muonionjoki tributary (~150 km of the basin). Tornionjoki ends up with 71 OSM polygons → 860 hex cells, vs Simojoki at 87 polygons → 2595 cells. Cell-count ordering inverted from physical reality.
2. **No marine cells at any WGBAST river mouth.** Configs declare a `BalticCoast` reach with junction integers `(5, 6)`, but the shapefiles contain only `Mouth`/`Lower`/`Middle`/`Upper`. Smolts have no transit cells between the river mouth and the sea-zone abstraction.
3. **Stale Lithuanian template reaches.** Each WGBAST YAML carries 4 orphan reaches (`Skirvyte`, `Leite`, `Gilija`, `CuronianLagoon`) inherited from the example_baltic template. They have `pspc_smolts_per_year: 0` (effectively dead) and reference Lithuanian-named CSV files that ship in each fixture but represent the wrong system. Adding marine cells without removing this cruft keeps a confusing config surface.

## Goals

**PR-1:** Tornionjoki's freshwater extent grows to include Muonionjoki. Cell count rises above Simojoki.

**PR-2 (after PR-1 lands):**
- Each of the 4 WGBAST fixtures has shapefile cells under the existing `BalticCoast` reach name (~10 km coastline-clipped disk at the river mouth, coarse hex cells).
- BalticCoast cells are spatially adjacent to Mouth cells (at least one shared edge in the polygon adjacency graph) so the simulation can route fish through.
- Per-river `BalticCoast` parameter tuning: lower `fish_pred_min` for Bothnian Bay rivers (lower seal density than the Klaipėda value of 0.65) — concrete values in the Components section.
- Stale Lithuanian template reaches removed from each WGBAST YAML.
- All existing tests pass; reach name set in each WGBAST fixture becomes exactly `{Mouth, Lower, Middle, Upper, BalticCoast}`.

## Non-goals (v2)

- Per-tributary multi-reach decomposition of Muonionjoki (PR-1 keeps the existing 4-quartile along-channel partition).
- Bay-scale shared marine state across rivers.
- Tornionjoki juvenile-growth calibration.
- Salinity time-series for the new BalticCoast cells (defer; see Open questions).
- Adjusting the marine-zone model in `src/salmopy/marine/`.

## Architecture overview

### PR-1 (one-line + regenerate Tornionjoki)

```
scripts/_fetch_wgbast_osm_polylines.py     [MOD]   Tornionjoki regex extension
tests/fixtures/_osm_cache/                 [MOD]   refresh tornionjoki line cache
tests/fixtures/example_tornionjoki/        [MOD]   regenerated shapefile (more cells)
```

### PR-2 (BalticCoast cells + WGBAST yaml cleanup)

```
scripts/
├── _wgbast_balticcoast.py                 [NEW]   coastline-clipped disk → polygon
├── _fetch_wgbast_osm_polylines.py         [MOD]   per-river coastline cache fetch
├── _generate_wgbast_physical_domains.py   [MOD]   BalticCoast segment + adjacency check
└── _wire_wgbast_physical_configs.py       [MOD]   per-river BalticCoast tuning + orphan-reach cleanup
configs/
├── example_tornionjoki.yaml               [MOD]   tuned BalticCoast params; orphan reaches removed
├── example_simojoki.yaml                  [MOD]   same
├── example_byskealven.yaml                [MOD]   same
└── example_morrumsan.yaml                 [MOD]   same
tests/fixtures/example_*/                  [MOD]   regenerated shapefile (5 reaches)
```

Per-river `River` dataclass gains **two module-level constants**, not per-river fields (per the YAGNI feedback):

```python
# in _generate_wgbast_physical_domains.py
BALTICCOAST_RADIUS_M = 10_000.0
BALTICCOAST_CELL_FACTOR = 4.0   # BalticCoast cell_size = river.cell_size_m × this
```

A future river that needs different values triggers a refactor; today four rivers, one set of constants.

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

### 1. New `scripts/_wgbast_balticcoast.py` helper

```python
def build_balticcoast_polygon(
    mouth_lon_lat: tuple[float, float],
    source_lon_lat: tuple[float, float],   # next upstream waypoint, identifies "land" side
    radius_m: float,
    coastline_lines: list[LineString],
    utm_epsg: int,                          # explicit; matches freshwater grid's UTM
) -> Polygon:
    """Return a coastline-clipped marine polygon (WGS84) representing the
    BalticCoast extent at a river mouth.

    Algorithm:
      1. In `utm_epsg` (chosen to match the freshwater grid's UTM zone so the
         two grids land in the same projection without round-trip drift):
           a. Project mouth and source to UTM.
           b. Verify the disk does NOT contain the source point. If it does,
              raise ValueError immediately (caller reduces radius_m or
              picks a closer-in source proxy). Source-inside-disk inverts
              the land/sea classifier.
           c. Build the disk: mouth_pt.buffer(radius_m).
           d. Project coastline_lines to UTM, merge into a single
              MultiLineString, buffer by 1.0 (true 1 m at this scale).
      2. If `coastline_lines` is empty:
           Raise ValueError("coastline cache missing") — do NOT silently
           return the unclipped disk. An unclipped disk at any of these
           4 mouths extends ~10 km inland; tagging freshwater pixels as
           marine causes silent biological corruption that the adjacency
           check cannot detect.
      3. Otherwise:
           a. Compute pieces = disk.difference(buffered_coastline). Result
              is one of:
              - empty (disk fully covered by coastline buffer): raise ValueError.
              - single Polygon (coastline does not split the disk): raise
                ValueError("coastline does not cross disk; suspicious").
              - MultiPolygon (coastline splits the disk into ≥2 pieces).
           b. Land = pieces.geoms[i] containing source_pt (UTM).
              Sea = union of pieces NOT containing source_pt.
           c. If no piece contains source_pt (source on or near a coastline
              line): raise ValueError ("source within 1 m of coastline,
              cannot classify").
      4. Reproject sea polygon back to WGS84 (EPSG:4326) and return.

    All branches that "can't decide" raise ValueError — caller turns these
    into `RuntimeError` with the river name. Fail-fast over silent
    fallbacks.
    """
```

The helper takes **explicit `utm_epsg`** rather than computing it locally — this forces the caller to pin the BalticCoast UTM to the freshwater grid's UTM, eliminating cross-grid round-trip drift in the adjacency check (numerical reviewer finding 3).

Pure-Python (geopandas + shapely + pyproj already in the `shiny` env), no I/O, fully unit-testable on synthetic inputs.

### 2. `_fetch_wgbast_osm_polylines.py` — coastline fetch

For each `RiverQuery`, add a third Overpass query for `natural=coastline` ways within a 0.3° × 0.3° bbox centered on `mouth_lon_lat`. Cache to `_osm_cache/<short_name>_coastline.json` in the same flat-list format as the existing line/polygon caches. Network errors and non-200 responses are non-recoverable — fail loudly so the user re-runs after Overpass recovers (no silent empty cache).

### 3. `_generate_wgbast_physical_domains.py` — BalticCoast cell generation

After the existing `build_reach_segments(river)` call returns the 4 freshwater reach segments:

```python
from _wgbast_balticcoast import build_balticcoast_polygon
from app.modules.create_model_utils import detect_utm_epsg

# Pin both grids to the SAME UTM zone (freshwater centroid's zone)
all_geoms = []
for info in fresh_segments.values():
    all_geoms.extend(info["segments"])
fresh_centroid = unary_union(all_geoms).centroid
utm_epsg = detect_utm_epsg(fresh_centroid.x, fresh_centroid.y)

coastline_lines = _load_coastline_cache(river)   # raises if missing
bc_polygon = build_balticcoast_polygon(
    mouth_lon_lat=river.waypoints[0],
    source_lon_lat=river.waypoints[1],     # second waypoint = next upstream
    radius_m=BALTICCOAST_RADIUS_M,
    coastline_lines=coastline_lines,
    utm_epsg=utm_epsg,
)

bc_segment = {"segments": [bc_polygon], "frac_spawn": 0.0, "type": "sea"}
```

Two `generate_cells` calls (per the v1 design — kept verbatim):

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
```

Both calls return GeoDataFrames with a `cell_id` STRING column formatted `"C0001"`, `"C0002"`, ... (per `create_model_grid.py:208`). Renumber the marine ids to avoid collision with freshwater ids:

```python
n_fresh = len(fresh)
n_total = n_fresh + len(marine)
width = max(4, len(str(n_total)))   # widen format if needed; 4 was the old hardcoded width
fresh["cell_id"] = [f"C{(i+1):0{width}d}" for i in range(n_fresh)]
marine["cell_id"] = [f"C{(n_fresh + i + 1):0{width}d}" for i in range(len(marine))]
combined = pd.concat([fresh, marine], ignore_index=True)
```

(The existing fresh ids are also re-formatted so widths match. This is safe because cell_id is informational, not a foreign key into other CSVs — `Depths.csv` and `Vels.csv` are indexed by row position, not id.)

### 4. Adjacency sanity check

```python
reach_col = "REACH_NAME" if "REACH_NAME" in combined.columns else "reach_name"
mouth_subset = combined[combined[reach_col] == "Mouth"]
marine_subset = combined[combined[reach_col] == "BalticCoast"]
if marine_subset.empty:
    raise RuntimeError(
        f"{river.river_name}: BalticCoast generated 0 cells "
        f"(disk minus coastline likely too small at radius={BALTICCOAST_RADIUS_M}m)."
    )
marine_union = marine_subset.geometry.unary_union
if marine_union is None or marine_union.is_empty:
    raise RuntimeError(
        f"{river.river_name}: BalticCoast geometry is empty after concat."
    )
# Use a small buffer to absorb sub-meter UTM↔WGS84 round-trip noise.
# Both grids ran in the SAME utm_epsg (set above) so noise is small;
# a 1e-7° buffer (~0.011 m at this latitude) is enough.
hits = mouth_subset.geometry.buffer(1e-7).intersects(marine_union).sum()
if hits == 0:
    raise RuntimeError(
        f"{river.river_name}: BalticCoast not adjacent to Mouth — "
        f"disk geometry leaves a gap (radius {BALTICCOAST_RADIUS_M}m). "
        f"Increase radius or move mouth waypoint seaward."
    )
```

The check guards against:
- Empty marine cells (from coastline cache covering the whole disk).
- `unary_union` returning `None` on empty selections (older shapely versions).
- Sub-meter round-trip drift between freshwater and marine grids (mitigated by pinning UTM to the same zone, but the `1e-7°` buffer absorbs any residual hairline gap).

### 5. `_wire_wgbast_physical_configs.py` — per-river BalticCoast tuning + orphan cleanup

For each WGBAST config (Tornionjoki, Simojoki, Byskealven, Morrumsan):

**5a. Drop the 4 orphan reaches** — `Skirvyte`, `Leite`, `Gilija`, `CuronianLagoon` (remove their YAML blocks entirely).

**5b. Update `BalticCoast` parameters** to per-river marine ecology. Defaults from `example_baltic.yaml`'s BalticCoast (Klaipėda) block apply for marine-typical hydrology, but predator regime differs per river. The 3 northern rivers see Bothnian Bay (lower seal density historically; cormorant + cod the dominant predators); Mörrumsån sees Hanöbukten (intermediate seal density). Concrete tuning:

```yaml
# Tornionjoki, Simojoki, Byskealven (Bothnian Bay rivers)
BalticCoast:
  drift_conc: 2.0e-10
  search_prod: 1.0e-07
  shelter_speed_frac: 0.0
  prey_energy_density: 1500
  drift_regen_distance: 20000
  shading: 0.02
  fish_pred_min: 0.95          # was 0.65 (Klaipėda seals);
                               # Bothnian Bay smolts see lower seal density.
                               # 0.95 = ~5% daily mortality, ~consistent with
                               # post-smolt at-sea survival of 75% over 30 days
                               # (matches existing example_baltic Mouth = 0.985)
  terr_pred_min: 0.995
  light_turbid_coef: 0.007
  light_turbid_const: 0.004
  max_spawn_flow: 999
  shear_A: 0.001
  shear_B: 0.15
  upstream_junction: 5         # already set; downstream of Upper: 4→5
  downstream_junction: 6       # already set; terminal toward marine zone
  time_series_input_file: "BalticCoast-TimeSeriesInputs.csv"
  depth_file: "BalticCoast-Depths.csv"
  velocity_file: "BalticCoast-Vels.csv"

# Mörrumsån (Hanöbukten, southern Baltic)
BalticCoast:
  ...
  fish_pred_min: 0.90          # higher seal density than Bothnian Bay,
                               # lower than Klaipėda; ~10% daily mortality
  ...
```

(Marine-zone parameters left for a later calibration pass.)

**5c. Per-reach hydrology CSVs** — the BalticCoast-*.csv files already exist in each fixture (template-copied). After the regenerate they will have row counts that don't match the new BalticCoast cell count, so they must be re-expanded the same way the v0.46.0 H7 fix re-expands per-cell CSVs after regenerate:

```
# For each river, re-expand BalticCoast-Depths.csv and BalticCoast-Vels.csv
# to len(combined[combined.REACH_NAME == "BalticCoast"]) rows by replicating
# the first data row (header lines + count row + flow-values row preserved).
# BalticCoast-TimeSeriesInputs.csv is per-reach not per-cell, so it needs no
# row-count change; only the temperature column may need adjustment to match
# the Mouth reach's mean (so smolts emerging into BalticCoast don't see a
# discontinuous temp jump).
```

The CSV format (verified by code-explorer) is:

```
; comment line 1
; comment line 2 (e.g. "CELL DEPTHS IN METERS")
N,Number of flows in table,,,,,...    ← N flow columns
,f1,f2,f3,...,fN                       ← leading empty cell, then N flow values
1,d11,d12,...,d1N                      ← cell 1
2,d21,d22,...,d2N                      ← cell 2
...
```

Re-expansion preserves lines 1-4 verbatim and replicates the cell-1 data row for every new cell. (This is the same algorithm v0.46.0 uses in `app/modules/edit_model_panel.py::_regen_apply` H7 fix.)

### 6. Reach-name set in shapefile after PR-2

Final reach set per WGBAST shapefile: `{Mouth, Lower, Middle, Upper, BalticCoast}`. Ordering in YAML `reaches:` block: `BalticCoast` stays at the END (after Upper), preserving the YAML's existing junction order (Mouth=1→2 first, BalticCoast=5→6 last).

## Error handling

- **Coastline fetch fails (Overpass timeout/error):** raise. Re-run when Overpass is back. No silent empty cache.
- **Coastline cache covers entire disk** (`disk.difference(buffered_coastline)` empty): raise `ValueError`.
- **Coastline cache present but doesn't cross disk** (single Polygon result): raise `ValueError` (suspicious — coastline should cross any reasonable river-mouth disk).
- **`source_lon_lat` inside disk** (radius too large for the river's first waypoint spacing): raise `ValueError` early in `build_balticcoast_polygon`.
- **`source_lon_lat` within 1 m of coastline** (no disk piece contains it): raise `ValueError` (waypoint hand-curation issue; user fixes the waypoint).
- **BalticCoast generates 0 cells**: raise `RuntimeError`.
- **BalticCoast not adjacent to Mouth**: raise `RuntimeError`.

The hard stance on fail-fast (rejecting silent fallbacks) addresses the architect's concern that a silently degraded fixture is worse than no fixture.

## Testing

Three test layers, all fast (<30 s) and network-free at CI time (OSM caches committed to git per existing pattern):

### `tests/test_wgbast_balticcoast.py` (new)

Pure-Python unit tests of `build_balticcoast_polygon`:

1. **Synthetic half-disk (success):** mouth at `(0.0, 0.0)`, source at `(0.0, 1.0)`, coastline = `LineString([(-1, 0), (1, 0)])`. Result: a half-disk in the southern half-plane (the side NOT containing source). UTM EPSG arbitrary fixed value for test (e.g. 32634).
2. **Empty coastline (raises):** `coastline_lines=[]` → ValueError, no silent unclipped fallback.
3. **Source inside disk (raises):** mouth at `(0,0)`, source at `(0, 0.05)` with radius_m equivalent to ~6 km → ValueError.
4. **Source on coastline (raises):** source within 1 m of the coastline buffer → ValueError.
5. **Coastline does not cross disk (raises):** coastline parallel to disk diameter but offset by 1.5×radius → single-polygon difference result → ValueError.
6. **Real Mörrumsån case:** mouth `(14.745, 56.175)`, source `(14.702, 56.300)`, real cached coastline → polygon non-empty, area ≥ 30% of unclipped disk, polygon entirely SOUTH of source.

### `tests/test_wgbast_river_extents.py` (new)

For each of the 4 rivers, after running the generator end-to-end:

1. Reach name set is exactly `{Mouth, Lower, Middle, Upper, BalticCoast}`.
2. BalticCoast cell count ∈ `[100, 3000]` (widened from v1's tight `[200, 2000]` per the numerical review — Mörrumsån's 240 m hexes plus an open Hanöbukten can reasonably yield 1500–2500 cells, while the 600 m Tornionjoki cells over a half-clipped disk can fall to ~150).
3. BalticCoast cell centroids lie SOUTH of (or coastward of) the Mouth centroid mean. (Direction depends on the river — for Mörrumsån the bay is south; for Bothnian rivers it's the bay generally south of the mouth.)
4. **PR-1 acceptance:** Tornionjoki cell count > Simojoki cell count.
5. **No orphan reaches:** YAML for each river has exactly 5 entries under `reaches:`. No `Skirvyte`, `Leite`, `Gilija`, `CuronianLagoon` keys.

### `tests/test_wgbast_river_extents.py::test_mouth_balticcoast_topology`

For each river, two assertions:

1. **Geometric adjacency:** `mouth_subset.geometry.buffer(1e-7).intersects(balticcoast_union).sum() >= 1` (matches the generator's check).
2. **Junction graph adjacency:** load the YAML; assert `BalticCoast.upstream_junction == Upper.downstream_junction`. The migration graph (`src/salmopy/modules/migration.py::build_reach_graph`) connects reaches by integer junction matching, NOT by polygon adjacency. Both must agree.

### Existing tests

- `tests/test_multi_river_baltic.py::test_fixture_loads_and_runs_3_days`: should keep passing. The 5th reach is materialized; YAML schema unchanged (just smaller after orphan removal). 3-day run won't yet exercise migration into BalticCoast (smolts emigrate later in season), but the fixture must still load.
- `tests/test_multi_river_baltic.py::test_latitudinal_smolt_age_gradient[Tornionjoki]`: stays xfailed until Workstream B (juvenile-growth calibration) lands. Adding BalticCoast cells does not address that.

## Migration / rollout

- PR-1 ships independently. One-line code change + Tornionjoki fixture regenerate. ~15 min of work.
- PR-2 ships after PR-1 lands. Larger blast radius: 4 fixtures regenerated, 4 YAMLs cleaned + tuned, new helper module, 3 new test files. The full WGBAST regeneration (`_fetch_wgbast_osm_polylines.py --refresh && _generate_wgbast_physical_domains.py && _wire_wgbast_physical_configs.py`) is idempotent.
- After PR-2, server deploy uses the existing skill (`/deploy`); fixture refresh is part of Step 6 already.

## Open questions

1. **Salinity in BalticCoast-TimeSeriesInputs.csv.** The simulation has `salmopy/modules/estuary.py::salinity_survival()` but no salinity column flows in via the per-reach time-series CSV today. Adding one is non-trivial (loader change + per-river salinity data sourcing). Deferred — the Bothnian Bay rivers can use the existing freshwater-temperature column without crashing the model; the marine-zone scaffold (`marine/`) handles salinity-driven mortality independently.
2. **Marine-zone integration.** The zone-based marine model in `src/salmopy/marine/` uses string literal `"Estuary"` (case-insensitive) in `marine/survival.py:257` for cormorant predation. Adding a reach NAMED `BalticCoast` doesn't collide with this. But: when smolts transit the new BalticCoast cells, they are simultaneously in the zone-based `Estuary`/`Coastal` zones and in the reach-based `BalticCoast` reach. Both apply mortality; this is by design (zone = at-sea survival, reach = local-cell predation), but worth flagging in the eventual implementation plan.
3. **Hanöbukten vs Bothnian Bay seal density.** The `fish_pred_min` values prescribed in §5b are ballpark (0.95 Bothnian, 0.90 Hanöbukten). Validating against ICES seal-survey data is a separate calibration step; this spec freezes plausible defaults that won't kill all smolts on day 1.

## Reviewer findings addressed (v1 → v2)

| # | v1 issue | v2 resolution |
|---|---|---|
| 1 | Invents `Estuary` reach when `BalticCoast` already in YAML/CSVs | Use `BalticCoast` reach name throughout |
| 2 | Junction integers unspecified → 2-mouth ValueError | YAML already declares `BalticCoast: upstream_junction=5, downstream_junction=6`; no change needed |
| 3 | `Estuary` collides with marine-zone string match | `BalticCoast` doesn't collide |
| 4 | `cell_id + len(fresh)` crashes (cell_id is string) | Explicit `f"C{n:0{width}d}"` reformat with adaptive width |
| 5 | Empty-coastline fallback returns inland disk silently | Removed: empty cache now raises |
| 6 | BalticCoast `fish_pred_min=0.65` lethal for Bothnian smolts | Per-river tuning: 0.95 Bothnian, 0.90 Hanöbukten |
| 7 | CSV format vague | Format documented (lines 290–296) and re-expand reuses v0.46.0 H7 algorithm |
| 8 | Stale Lithuanian template reaches (Skirvyte/Leite/Gilija/CuronianLagoon) not addressed | Drop them in §5a |
| 9 | source_lon_lat inside disk inverts classifier | Pre-check raises `ValueError` |
| 10 | UTM zone mismatch between freshwater + marine grids | Both use the same `utm_epsg` (freshwater centroid's zone) |
| 11 | Two orthogonal fixes bundled | Split into PR-1 + PR-2 |
| 12 | Cell-count bounds `[200, 2000]` too tight | Widen to `[100, 3000]` |
| 13 | Per-river estuary fields over-engineered | Module-level constants instead |
| 14 | Tests cover geometry but not topology | Add junction-graph adjacency assertion |
