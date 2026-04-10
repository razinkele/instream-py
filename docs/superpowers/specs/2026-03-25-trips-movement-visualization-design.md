# Trips Movement Visualization — Design Spec

**Date**: 2026-03-25
**Status**: Draft
**Scope**: Upgrade the Spatial panel to deck.gl with real-time fish movement animation

## Goal

Replace the matplotlib-based Spatial panel with an interactive deck.gl map that shows:
1. Cell polygons colored by environmental/population variables (GeoJsonLayer)
2. Animated fish movement trails with species/activity coloring (TripsLayer)

Both layers share a single `MapWidget`. The Trips layer is toggleable.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Panel strategy | Upgrade Spatial (not new tab) | One unified interactive map with cell polygons + trips overlay |
| Trajectory resolution | Every day | Matches simulation timestep; ~36–180 MB depending on turnover — manageable |
| Base layer | GeoJsonLayer | Accepts GeoDataFrame directly; handles CRS; 1373 polygons is light |
| Color by (trips) | Last recorded state per fish | Simple; one trip per fish. Activity/life-history/size rarely need mid-trajectory splits. |
| Animation | Client-side requestAnimationFrame | 60fps; no server polling. Built into shiny-deckgl. |
| Head icons | Omitted for v1 | shiny-deckgl ICON_ATLAS has no trout silhouettes. Future enhancement. |

## Architecture

### 1. Data Collection (Backend)

**File**: `app/simulation.py`

Add trajectory collection to the existing simulation step loop. Inside the `if model.time_manager.is_day_boundary` block, record for every alive fish:

```python
trajectory_records.append({
    "fish_idx": fish_indices,      # int array
    "cell_idx": cell_indices,      # int array
    "species_idx": species_indices, # int array
    "activity": activities,        # int array
    "life_history": life_histories, # int array
    "day_num": day_number,         # int scalar (0-based day offset from sim start)
})
```

At simulation end, flatten into a DataFrame and add to results dict as `results["trajectories"]`.

**Memory estimate**: The actual cost is `total_alive_fish_days × 5 columns × 4 bytes`. With ~2000 concurrent fish and 912 days, but accounting for turnover (fish dying and new fish being born/emerging), the total fish created could be 5,000–10,000+. Assuming average lifespan of ~200 days and 8,000 total fish: `8000 × 200 × 5 × 4 ≈ 32 MB`. Upper bound with high turnover: ~180 MB. Both are acceptable.

Fish trajectories have variable length: a fish's trajectory starts when it appears (birth/emergence/immigration) and ends when it dies/emigrates.

### 2. Coordinate Transformation

**File**: `app/simulation.py` — new helper `_build_trajectories_data()`

This function must be unit-testable in isolation with a mock GeoDataFrame + trajectory DataFrame.

**Returns**: Two parallel lists — `paths` and `properties` — which are passed separately to `format_trips(paths=paths, properties=properties, loop_length=total_sim_days)`.

Steps:
1. Reproject cells GeoDataFrame to EPSG:4326 (WGS84). If `gdf.crs is None`, attempt to read CRS from config; if unavailable, raise a clear error: `"Shapefile has no CRS metadata — cannot reproject to WGS84"`.
2. Extract centroid lookup table: `centroid_lut[cell_idx] → [lon, lat]`
3. Group trajectory records by `fish_idx`
4. For each fish, map `cell_idx` sequence → `[lon, lat, day_num]` coordinate path (3D with actual day number as timestamp). This ensures fish born on day 100 animate starting at day 100, not time 0.
5. Compute per-fish properties from last recorded state: species name, activity name, life history name, size class, color RGBA.
6. Return `(paths, properties)` — `paths` is `list[list[list[float]]]` where each inner list is `[lon, lat, day_num]` triplets; `properties` is `list[dict]`.

**Timestamp handling**: Since paths are 3D `[lon, lat, day_num]`, `format_trips()` will use the third element as the timestamp directly (ibm.py line 363-366). The `loop_length` must equal `total_sim_days` so the animation loops over the full simulation period.

### 3. Spatial Panel (Frontend)

**File**: `app/modules/spatial_panel.py` — full rewrite

#### MapWidget Lifecycle

The `MapWidget` is created once during module server initialization. It is stored as a module-level variable and shared between:
- The layer-update reactive effects (for `set_layers()` calls)
- The `trips_animation_server()` wiring (for Play/Pause/Reset control)

Initialization order:
1. Create `MapWidget` with initial view state and dark basemap
2. Wire `trips_animation_server("fish_anim", widget=widget, session=session)` → returns `anim` namespace
3. Set up reactive effects that call `widget.set_layers(session, layers)` when inputs change

#### UI Structure

```
Card: "Spatial View"
├── Row: [Color-by cells dropdown] [Color-by trips dropdown] [Show Trips checkbox]
├── trips_animation_ui("fish_anim")  — conditionally visible
└── MapWidget output
```

#### Controls

| Control | Type | Values |
|---------|------|--------|
| `color_var` | Select | depth, velocity, drift food, search food, fish count |
| `trips_color` | Select | Species (default), Activity, Life History, Size Class |
| `show_trips` | Checkbox | Toggle trips layer visibility |
| Animation | trips_animation_ui | Play/Pause/Reset + speed/trail sliders |

Note: `frac_spawn` removed from color dropdown — it is a binary (0/1) shapefile attribute that produces no useful gradient.

#### Layers

**Layer 1: Cell polygons** (`geojson_layer`)
- Data: cells GeoDataFrame (reprojected to EPSG:4326), with a `"color"` column added containing `[R, G, B, A]` lists computed from the selected variable
- `getFillColor`: `"@@=d.properties.color"` — reads the per-feature color from the GeoDataFrame column
- `getLineColor`: `[60, 60, 60, 100]`
- `pickable`: True
- Always visible

**Layer 2: Fish trails** (`trips_layer`)
- Data: output of `format_trips(paths, properties=properties, loop_length=total_sim_days)` — each trip dict has a `"color"` key with RGBA
- `_tripsAnimation`: `{loopLength: total_sim_days, speed: anim.speed()}`
- Head icons: omitted for v1 (no trout sprites in ICON_ATLAS)
- `trailLength`: `anim.trail()`
- `fadeTrail`: True
- `getColor`: `"@@=d.color"` — reads per-trip RGBA from the data
- `widthMinPixels`: 3
- Visible only when `show_trips` is checked

#### Tooltip

Both layers have `pickable: True`. Configure `getTooltip` on the MapWidget:
- Cell polygons: show cell_id, reach, and the current color variable name + value
- Fish trails: show fish_idx, species, activity, life history, length

#### Reactive Flow

| Trigger | Action |
|---------|--------|
| `results_rv` changes | Rebuild both layers, recompute trajectories data |
| `color_var` changes | Rebuild cell layer only (recompute fill colors in GeoDataFrame) |
| `trips_color` changes | Rebuild trips layer only (recompute trail colors in properties) |
| `show_trips` changes | Include/exclude trips layer from `set_layers()` |
| `anim.speed()` / `anim.trail()` | Rebuild trips layer |

#### Map View

- `initial_view_state`: auto-computed from GeoDataFrame bounds (center lon/lat + zoom)
- Basemap: Carto Dark Matter (good contrast with colored polygons and trails)

### 4. Color Mapping

#### Cell polygon colors

Helper function `_value_to_rgba(values, cmap="viridis", alpha=160)`:
- Normalize values to 0–1 range (min-max scaling)
- Map through matplotlib viridis colormap → `[R, G, B, A]` per cell (0-255 int scale)
- NaN/null → `[0, 0, 0, 0]` (transparent)
- Returns a list of RGBA lists, one per cell

#### Fish trail colors

| Mode | Mapping |
|------|---------|
| Species | Categorical palette (tab10): deterministic color per `species_idx` order from config. E.g., species 0 = tab10[0], species 1 = tab10[1], etc. |
| Activity | drift=`[66,133,244]` (blue), search=`[52,168,83]` (green), hide=`[154,160,166]` (gray), guard=`[234,67,53]` (red), hold=`[251,188,4]` (yellow) |
| Life History | resident=`[0,150,136]` (teal), anad_juve=`[0,188,212]` (cyan), anad_adult=`[255,152,0]` (orange) |
| Size Class | 4 quartile bins on fish length → sequential blue ramp: `[189,215,231]`, `[107,174,214]`, `[49,130,189]`, `[8,81,156]` |

All modes use the fish's **last recorded state** (single color per trip).

## File Changes

| File | Action | Summary |
|------|--------|---------|
| `app/simulation.py` | Edit | Add daily trajectory collection in step loop (~30 lines). Add `_build_trajectories_data()` helper (~60 lines). Add `"trajectories"` key to results dict. Total growth: ~100 lines. |
| `app/modules/spatial_panel.py` | Rewrite | Replace matplotlib with MapWidget + geojson_layer + trips_layer + animation controls + tooltip. |
| `app/app.py` | Edit | Minimal — spatial panel is already wired as a module. Verify shiny_deckgl is importable. |
| `pyproject.toml` | Edit | Verify `shiny-deckgl>=1.9` in frontend extras. |

**No new files.** No changes to `src/instream/` model code.

## Constraints

- shiny-deckgl ≥ 1.9 required (already in frontend extras)
- Trips animation loops by default (no play-once mode)
- Shapefile must have valid CRS for reprojection to WGS84; error raised if CRS is missing
- Fish positions are cell centroids — no within-cell interpolation
- Maximum ~2000 concurrent fish; deck.gl handles this easily
- No head icons in v1 — shiny-deckgl ICON_ATLAS lacks trout silhouettes

## Testing

- Unit test `_build_trajectories_data()` with a mock GeoDataFrame (3 cells with known EPSG:4326 coords) and a small trajectory DataFrame (5 fish, 10 days). Verify output paths have correct `[lon, lat, day_num]` structure and properties contain expected species/color keys.
- Run simulation with Example A config, verify `results["trajectories"]` DataFrame has expected columns and row count proportional to alive-fish-days.
- Verify WGS84 reprojection produces valid lon/lat (not meters) — check bounds are within [-180, 180] × [-90, 90].
- Verify Trips layer animates in browser with Play/Pause/Reset.
- Verify color-by toggles update trail colors without full page reload.
- Verify cell polygon colors update on dropdown change.
- Verify tooltip shows cell/fish info on hover.
