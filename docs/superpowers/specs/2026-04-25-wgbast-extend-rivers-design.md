# WGBAST rivers — extend Tornionjoki + add Estuary reach (design)

**Date:** 2026-04-25
**Scope:** `scripts/_fetch_wgbast_osm_polylines.py`, `scripts/_generate_wgbast_physical_domains.py`, `scripts/_wire_wgbast_physical_configs.py`, new `scripts/_wgbast_estuary.py`, `configs/example_{tornionjoki,simojoki,byskealven,morrumsan}.yaml`, regenerated fixtures under `tests/fixtures/example_*/`.
**Out of scope:** Tornionjoki juvenile-growth calibration (Workstream B from the v0.46 plan); fixture-coupling refactors that share marine state across rivers; full-basin Tornionjoki coverage (Lainio älv, Könkämäeno).

## Problem

Two distinct gaps in the v0.45.3 WGBAST fixtures:

1. **Tornionjoki extent is too small.** The OSM line-way fetch uses
   `name~"^(Tornionjoki|Torne älv|Torneälven|Torneå älv|Torne)$"`, which only
   matches the lower 151 km. The Torne main stem reaches the Muonionjoki
   confluence at Pajala (~67.4°N) where it bifurcates: the eastern branch
   keeps the name "Tornionjoki" through several lakes, the western branch
   becomes "Muonionjoki" and runs another ~150 km along the Finnish-Swedish
   border. Stock-assessment context (WGBAST) treats Muonionjoki as part of
   the Tornionjoki population. The diagnostic
   (`scripts/_diag_tornionjoki_polygon_filter.py`) confirms the connectivity
   filter only seeds 4 polygons (vs 22-71 for the other 3 rivers) → 71
   kept polygons → 860 hex cells. Simojoki, a much smaller river, ends up
   with 2595 cells. The cell-count ordering is inverted from reality.

2. **No marine extent at any river mouth.** All 4 rivers stop at the
   freshwater/brackish boundary. Smolt outmigration and adult homing both
   transit a coastal estuary that the current fixtures cannot represent.

## Goals

- Tornionjoki includes the Muonionjoki main stem, restoring it as the
  largest of the 4 WGBAST fixtures by cell count.
- Each river has an additional `Estuary` reach: a coastline-clipped marine
  patch at the mouth, sized for smolt-emigration transit (~10 km radius,
  ~4× coarser hex cells than the freshwater grid).
- The Estuary connects topologically to the freshwater `Mouth` reach (at
  least one shared edge in the polygon adjacency graph) so the simulation
  can route fish through it.
- All existing tests pass; the 4 WGBAST fixtures keep their current
  `Mouth`/`Lower`/`Middle`/`Upper` reach names — `Estuary` is a 5th
  additive reach, not a rename.

## Non-goals

- Per-tributary multi-reach decomposition of Muonionjoki. The two name
  matches share the same 4-quartile along-channel partition.
- Bay-scale shared marine state across the 3 northern rivers (deferred
  to a future release if/when the simulation needs basin-wide marine
  representation).
- Tornionjoki juvenile-growth calibration (Workstream B from
  `docs/superpowers/plans/2026-04-25-v046-edit-model-and-calibration.md`).

## Architecture overview

Two changes to existing scripts + one new helper module + 5-reach config
update for each of the 4 rivers:

```
scripts/
├── _fetch_wgbast_osm_polylines.py          [MOD] Tornionjoki regex; coastline fetch per river
├── _generate_wgbast_physical_domains.py    [MOD] Estuary reach builder; adjacency sanity check
├── _wire_wgbast_physical_configs.py        [MOD] Estuary entry in YAML; per-reach Estuary CSVs
└── _wgbast_estuary.py                      [NEW] coastline-clipped disk → polygon
```

Per-river `River` dataclass gains two fields:
```python
estuary_radius_m: float = 10000.0       # disk radius at mouth (metres)
estuary_cell_factor: float = 4.0        # estuary cell size = river cell_size × this
```

## Data flow

```
_fetch_wgbast_osm_polylines.py
  ├─ rivers: name+bbox query → _osm_cache/example_*.json (line ways)
  ├─ rivers: bbox query for water polygons → _osm_cache/example_*_polygons.json
  └─ NEW: per-river coastline query → _osm_cache/example_*_coastline.json
                                  ↓
_generate_wgbast_physical_domains.py
  ├─ build_reach_segments(river)         # 4 freshwater reaches (existing)
  ├─ build_estuary_segment(river)        # NEW: coastline-clipped disk Polygon
  ├─ generate_cells(freshwater, fine size)
  ├─ generate_cells({Estuary: ...}, coarse size = cell_size × estuary_cell_factor)
  ├─ concat → renumber Estuary cell_ids to avoid collision
  ├─ adjacency_check(Mouth ↔ Estuary)
  └─ write {Stem}Example.shp (5 reaches)
                                  ↓
_wire_wgbast_physical_configs.py
  ├─ add Estuary entry to configs/example_*.yaml reaches: block
  ├─ per-reach hydrology CSVs: Estuary-Depths.csv, Estuary-Vels.csv, Estuary-TimeSeriesInputs.csv
  │    (marine-typical defaults: depth 5-15m mean, velocity 0 m/s, temp = mouth temp)
  └─ frac_spawn=0 for Estuary
```

## Components

### 1. `_fetch_wgbast_osm_polylines.py` modifications

- Tornionjoki regex extended to include Muonionjoki:
  ```python
  name_regex="^(Tornionjoki|Torne älv|Torneälven|Torneå älv|Torne|Muonionjoki|Muonio älv|Muonio)$"
  ```
  Existing bbox `(65.5, 22.8, 68.6, 25.6)` already covers the Muonio basin.
- Bbox unchanged for the 3 other rivers.
- New per-river coastline fetch: a 0.3° × 0.3° bbox centered on
  `mouth_lon_lat`, querying `way["natural"="coastline"]` and writing to
  `_osm_cache/<short_name>_coastline.json`. Cached identically to the
  existing way + polygon caches.
- Coastline fetch is best-effort: timeouts/failures log a warning and
  the cache file is written empty (zero ways). The downstream consumer
  treats an empty cache as "no land to clip" → fall back to the unclipped
  disk.

### 2. New `scripts/_wgbast_estuary.py` helper

```python
def build_estuary_polygon(
    mouth_lon_lat: tuple[float, float],
    source_lon_lat: tuple[float, float],   # next upstream waypoint, identifies "land" side
    radius_m: float,
    coastline_lines: list[LineString],     # may be []
) -> Polygon:
    """Return a coastline-clipped disk polygon (WGS84) representing the
    marine extent at a river mouth.

    Algorithm:
      1. Project mouth + radius into the local UTM zone for a true-meters
         circle. Build the disk in UTM then project the result back.
      2. If `coastline_lines` is empty, return the unclipped disk.
      3. Otherwise, identify the "land side" without ambiguity by passing
         a `source_lon_lat` parameter (the next waypoint upstream of the
         mouth, already known per `River.waypoints[1]`):
           a. Merge the coastline lines into one geometry, buffer by 1 m
              (closes hairline gaps between consecutive ways).
           b. Compute `disk_minus_coastline = disk.difference(buffered_coastline)`.
              This produces a MultiPolygon with one piece per "side".
           c. The piece containing `source_lon_lat` is land. The piece(s)
              NOT containing source are sea. Return the union of the
              sea pieces.
           d. If only one piece exists (coastline doesn't cross the disk),
              treat it as sea: the mouth is already inside the disk on
              the sea side.
      4. If the resulting polygon is empty, raise ValueError with the
         input parameters for diagnosis.

    Caller decides what to do with ValueError (typically: raise
    RuntimeError with a more user-facing message that includes the river
    name).
    """
```

The helper is pure-Python (geopandas + shapely + pyproj already in the
`shiny` env), no I/O, fully unit-testable on synthetic inputs.

### 3. `_generate_wgbast_physical_domains.py` modifications

- New `River` fields with sensible defaults (see Architecture overview).
- After `build_reach_segments(river)`:
  ```python
  estuary_seg = build_estuary_segment(river)  # uses _wgbast_estuary
  ```
- Two `generate_cells` calls:
  ```python
  fresh = generate_cells(reach_segments=fresh_segments,
                         cell_size=river.cell_size_m, ...)
  marine = generate_cells(reach_segments={"Estuary": estuary_seg},
                          cell_size=river.cell_size_m * river.estuary_cell_factor,
                          buffer_factor=1.0, ...)
  marine["cell_id"] = marine["cell_id"] + len(fresh)  # renumber to avoid collision
  combined = pd.concat([fresh, marine], ignore_index=True)
  ```
- Adjacency sanity check (inline, no PolygonMesh instantiation):
  ```python
  reach_col = "REACH_NAME" if "REACH_NAME" in combined.columns else "reach_name"
  estuary_union = combined[combined[reach_col] == "Estuary"].geometry.unary_union
  mouth_subset = combined[combined[reach_col] == "Mouth"]
  hits = mouth_subset.geometry.intersects(estuary_union).sum()
  if hits == 0:
      raise RuntimeError(
          f"{river.river_name}: Estuary not adjacent to Mouth — "
          f"disk geometry leaves a gap (radius {river.estuary_radius_m}m). "
          f"Increase radius or move mouth waypoint seaward."
      )
  ```
- The combined GeoDataFrame is column-renamed via the existing
  `COLUMN_RENAME` dict (no new columns) and written to the same shapefile
  path as before.

### 4. `_wire_wgbast_physical_configs.py` modifications

- Add an `Estuary` entry to each river's YAML `reaches:` block with
  marine-typical hydrology parameters copied from `example_baltic.yaml`'s
  `BalticCoast` reach. The implementation reads BalticCoast verbatim and
  copies the entire dict, then overrides `time_series_input_file`,
  `depth_file`, `velocity_file` to the new `Estuary-*.csv` filenames and
  sets `frac_spawn=0`. If `BalticCoast` is missing from
  `example_baltic.yaml` (config schema change), fall back to the river's
  own `Mouth` reach config with `frac_spawn=0` and a `marine: true` flag
  the loader can act on.
- Generate three new CSVs per river:
  - `Estuary-Depths.csv`: 5–15 m per-cell depth column (monotone with
    distance from mouth: shallowest near coastline, deepest seaward).
    The format matches existing `*-Depths.csv` files (header rows, one
    data row per cell, multiple flow columns).
  - `Estuary-Vels.csv`: ~0 m/s for tidal-mixing approximation. Format
    matches existing `*-Vels.csv`.
  - `Estuary-TimeSeriesInputs.csv`: temperature = mouth temperature
    (from `Mouth-TimeSeriesInputs.csv`, no transformation), flow column
    inherited from Mouth (the simulation uses estuary flow only as a
    placeholder; salt-front dynamics aren't modelled).

### 5. YAML `reaches:` ordering

The new `Estuary` entry is inserted FIRST in the block (before `Mouth`),
matching the upstream→downstream-by-distance convention used elsewhere
(Estuary is the most-downstream reach). This also positions it
deterministically for `discover_fixtures()` and the Edit Model panel
dropdown.

## Error handling

- **Coastline fetch fails (Overpass timeout/error):** log warning, write
  empty cache file, continue. Downstream `build_estuary_polygon` sees
  empty `coastline_lines` and returns the unclipped disk.
- **Coastline-clipped disk is empty** (mouth waypoint sits inland of all
  coastline ways, or coastline orientation is ambiguous): raise
  `ValueError` with the river name and area ratios for diagnosis. Don't
  ship a fixture with a 5th reach that has 0 cells.
- **Adjacency sanity check fails** (Estuary disk doesn't touch the
  freshwater Mouth polygon): raise `RuntimeError` with the river name
  and a hint to increase `estuary_radius_m` or revise the mouth
  waypoint. Forces the user to inspect the geometry.
- **Existing `MAX_CONNECTED_POLYS=2000` cap** for the freshwater BFS:
  unchanged. Tornionjoki's expanded regex is not expected to bump up
  against it (Simojoki's centerline of 299 km only seeded 71 polygons;
  Tornionjoki+Muonio at ~300 km should land in a similar range).

## Testing

Three test layers, all fast (<30 s) and network-free at CI time
(OSM caches committed to git per existing pattern):

### `tests/test_wgbast_estuary.py` (new)

Pure-Python unit tests of `build_estuary_polygon`:
1. **Synthetic half-disk:** mouth at `(0.0, 0.0)`, coastline =
   `LineString([(-1, 0), (1, 0)])`. Result: a half-disk in the southern
   half-plane (the side opposite to the river-source direction).
2. **Empty coastline:** returns the unclipped disk; area ≈ π·r².
3. **Mouth deep inland:** raises `ValueError`.
4. **Real Mörrum case:** mouth at `(14.745, 56.175)` with the
   `_osm_cache/example_morrumsan_coastline.json` cache. Polygon is
   non-empty, area ≥ 30 % of the unclipped disk.

### `tests/test_wgbast_river_extents.py` (new)

For each of the 4 rivers, after running the generator end-to-end:
- 5 distinct reach names: `{Mouth, Lower, Middle, Upper, Estuary}`.
- Estuary cell count ∈ `[200, 2000]` (sanity bound for a 10 km disk
  at 240–600 m hex resolution).
- Estuary cell centroids lie southward (or coastward) of the Mouth
  centroid mean.
- Tornionjoki cell count > Simojoki cell count (the Muonio regex-fix
  payoff: today this is the inverse).

### `tests/test_wgbast_river_extents.py::test_mouth_estuary_adjacency`

For each river, build the same intersection-based adjacency check the
generator runs and assert `hits >= 1`. This is a regression test for
the Mouth↔Estuary topology requirement; without it the generator might
silently ship a fixture where smolts can never reach the marine grid.

### Existing tests

`tests/test_multi_river_baltic.py::test_fixture_loads_and_runs_3_days`
already loads each WGBAST fixture and runs a 3-day simulation. The
Estuary addition is purely additive — these tests should keep passing
without changes. If they fail, the YAML `reaches:` block is mis-shaped.

## Migration / rollout

- The fixture regeneration is idempotent and runs locally
  (`micromamba run -n shiny python scripts/_fetch_wgbast_osm_polylines.py
  --refresh && micromamba run -n shiny python
  scripts/_generate_wgbast_physical_domains.py && micromamba run -n
  shiny python scripts/_wire_wgbast_physical_configs.py`).
- The 4 WGBAST configs and shapefiles will change. The 4 corresponding
  fixtures committed under `tests/fixtures/example_*/` change in size
  (each gains ~500–2000 Estuary cells). Tests adjust automatically; no
  data-format migration is needed.
- Server deploy uses the existing skill (`/deploy`); fixture refresh is
  already part of Step 6 thanks to the v0.46.0 deploy-skill update.

## Open questions

None. All 6 brainstorming questions resolved with the user
(extent=A, sea-extent=A, integration=A, OSM-source=B, cell-size=B,
adjacency=A).
