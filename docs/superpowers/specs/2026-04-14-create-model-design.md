# Create Model UI — Design Spec (v2)

## Overview

Interactive model creation workflow in the SalmoPy app. Users download EU-Hydro river network data, select reaches, generate habitat cells (hexagonal, rectangular, or triangular FEM), configure parameters, and export a ready-to-run simulation config.

**Layout:** Hybrid — full-width map with compact action bar above. Configuration in a right slide-out panel. Status bar at bottom.

---

## Layout

### Action Bar (top, single row)

```
[EU-Hydro:] [🌊 Rivers] [💧 Water Bodies] [🏖️ Coastal] | [Model:] [✏️ Select Reaches] [⬡ Generate Cells] [⚙️ Configure] ──── [📦 Export]
```

- EU-Hydro buttons always enabled (fetch data for current view)
- Model buttons enable progressively: Select Reaches after data loaded → Generate Cells after reaches defined → Configure after cells generated → Export after config set
- Disabled buttons greyed out with tooltip: "Load river data first"
- Active step button highlighted with accent border

### Map (center, fills remaining space)

- Full-width WebGL deck.gl MapWidget (same as other panels)
- Floating Strahler filter slider (top-left): range 1-9, default ≥3
- Navigation + fullscreen + legend controls (top-right)
- Click interaction for reach selection (Step 2)
- Loading spinner overlay during EU-Hydro queries

### Slide-out Panel (right, 300px, toggled by Configure button)

- Reach selector dropdown
- Per-reach parameters (all 20 ReachConfig fields with defaults)
- Cell size slider (5-100m, default 20m)
- Cell shape selector: Hexagonal (default) / Rectangular / Triangular (FEM)
- Species preset dropdown
- Simulation dates

### Status Bar (bottom, single row)

```
Rivers: 142 | Water bodies: 3 | Reaches: 5 (127 segments) | Cells: 798 | CRS: EPSG:32634
```

---

## Workflow Steps

### Step 1: Fetch EU-Hydro Data

**Trigger:** Click "Rivers", "Water Bodies", or "Coastal" button.

**API:** EU-Hydro ArcGIS REST API
- Rivers: layer 4 (River_Net_lines) — polylines with Strahler, DFDD, NAME attributes
- Water Bodies: layer 2 (InlandWater) — polygons
- Coastal: layer 0 (Coastal_polygon) — polygons

**Behavior:**
- Query uses current map view bbox (from `widget.view_state_input_id`)
- Max 2000 features per query; for large areas, tile into 4 sub-queries
- Show loading spinner on map during fetch
- Rivers: blue lines, `lineWidthMinPixels` scaled by Strahler (1→1px, 5→3px, 9→6px)
- Water bodies: `[135, 206, 235, 120]` semi-transparent fill
- Strahler slider filters rivers: Python-side GeoDataFrame filter (`gdf[gdf["STRAHLER"] >= threshold]`), then rebuild geojson_layer and send via `widget.update()`. Debounced at 300ms (Shiny `reactive.isolate` with `reactive.invalidate_later(0.3)`) to prevent rapid re-renders while dragging the slider.
- On error: show notification "EU-Hydro query failed — try zooming in"

**Coordinate handling:**
- EU-Hydro returns WGS84 (EPSG:4326) — store as-is for map display
- Auto-detect UTM zone from map center for metric operations (buffering, area):
  ```python
  utm_zone = int((center_lon + 180) / 6) + 1
  utm_epsg = 32600 + utm_zone  # Northern hemisphere
  ```
- Show detected CRS in status bar

**Data stored:** `_rivers_gdf`, `_water_gdf`, `_coastal_gdf` as reactive values (WGS84).

### Step 2: Select Reaches

**Trigger:** Click "Select Reaches" (enabled after rivers loaded).

**Behavior:**
- Enters selection mode — status bar shows "Click river segments to select"
- Click a river segment → uses `widget.click_input_id` → deck.gl returns clicked feature properties
- Feature identification: `pickable=True` on river layer, click returns feature index + properties
- First click on unselected segment → dialog: enter reach name → segment assigned to reach, colored
- Subsequent clicks → add to current reach (same color)
- Click on already-selected segment → deselect (remove from reach)
- "New Reach" mini-button in action bar to start a new reach
- Selected reaches: distinct colors from Tab10 palette
- Segments within a reach: all share the reach color

**Junction auto-detection (geometric flow analysis):**
- After reach assignment, scan all reach segment endpoints (first/last vertex of each LineString)
- Two reaches share a junction if any endpoint pair is within 50m (UTM distance)
- Assign junction IDs: start from 1, increment per unique junction point
- For T-junctions (3+ reaches meeting): create a single junction node shared by all
- **Upstream/downstream by geometry** (not Strahler — Strahler is unreliable for same-order reaches):
  1. For each reach, the segment startpoint is upstream, endpoint is downstream. EU-Hydro river network lines are digitized in the downstream direction per the EEA technical specification (EU-Hydro Product User Manual, section 3.2: "The flow direction is defined by the digitization direction of the line feature").
  2. At a junction: the reach whose endpoint matches the junction is upstream; the reach whose startpoint matches is downstream
  3. If ambiguous (both start or both end at junction): show a notification "Ambiguous junction — click to set flow direction" and display two clickable arrow icons (→ and ←) next to the junction node on the map. User clicks the arrow showing correct flow direction. Store the user override.
- Display junction nodes as circles on the map with junction ID labels and flow direction arrows

**Data stored:** `_reaches` dict: `{reach_name: {"segments": [geom,...], "color": [...], "upstream_junction": int, "downstream_junction": int}}`

### Step 3: Generate Habitat Cells

**Trigger:** Click "Generate Cells" (enabled after ≥1 reach defined).

**Cell shape options:**

#### A. Hexagonal (default)
1. Reproject reach segments from WGS84 → UTM
2. Buffer segments by `cell_size * 2.0` (meters) — produces corridor ~4× cell width, ensuring 3-5 hexagon columns across even narrow streams. For a 20m cell: 40m buffer → 80m corridor → 4 hex columns.
3. Generate flat-top hexagonal grid covering the buffered extent:
   ```
   hex_width = cell_size
   hex_height = cell_size * sqrt(3) / 2
   ```
4. Clip hexagons to buffered area (discard hexagons with <20% overlap)
5. Assign each cell to nearest reach centroid
6. Reproject cells back to WGS84 for map display + store UTM version for export

#### B. Rectangular
- Same as hexagonal but with rectangular grid (simpler, matches existing ExampleA)
- Cells: `cell_size × cell_size` squares
- Clip + assign same as hexagonal

#### C. Triangular FEM (advanced)
- Uses `meshio` (already available v5.3.5) to read externally generated meshes
- "Import Mesh" button: load .msh (GMSH) or .2dm (River2D) file
- FEMMesh backend already supports these formats
- Not generated in-app (requires external tool) — future enhancement with `triangle` library

**Cell attributes (computed for all shapes):**
- `cell_id`: `CELL_0001`, `CELL_0002`, ...
- `reach_name`: from nearest reach assignment
- `area`: polygon area in m² (computed in UTM)
- `centroid_x`, `centroid_y`: in UTM (for simulation) and WGS84 (for display)
- `dist_escape`: distance from cell centroid to nearest reach endpoint (meters → cm)
- `num_hiding_places`: default 2 (edge cells), 1 (interior)
- `frac_vel_shelter`: default 0.15 (edge), 0.05 (interior)
- `frac_spawn`: default from reach config (spawning reaches get 0.3, others 0.0)

**Live preview:** Cells shown on map with reach colors. Cell size slider triggers re-generation (debounced 500ms).

**Data stored:** `_cells_gdf` (WGS84) + `_cells_gdf_utm` (UTM, for export).

### Step 4: Configure Reach Parameters

**Trigger:** Click "Configure" (enabled after cells generated). Opens slide-out panel.

**Per-reach parameters with defaults:**

| Parameter | Default | UI | Range |
|-----------|---------|-----|-------|
| `drift_conc` | 5.0e-9 | Log slider | 1e-11 to 1e-7 |
| `search_prod` | 8.0e-7 | Log slider | 1e-9 to 1e-5 |
| `shelter_speed_frac` | 0.3 | Slider | 0-1 |
| `prey_energy_density` | 4500 | Number | 1000-8000 |
| `drift_regen_distance` | 1000 | Number | 0-10000 |
| `shading` | 0.8 | Slider | 0-1 |
| `fish_pred_min` | 0.97 | Slider | 0.5-1.0 |
| `terr_pred_min` | 0.94 | Slider | 0.5-1.0 |
| `light_turbid_coef` | 0.002 | Number | 0-0.01 |
| `light_turbid_const` | 0.0 | Number | 0-0.01 |
| `max_spawn_flow` | 20 | Number | 1-999 |
| `shear_A` | 0.013 | Number | 0-0.1 |
| `shear_B` | 0.40 | Number | 0-1 |

Note: `frac_spawn` is a **cell-level attribute** (stored in shapefile DBF), not a ReachConfig field. The slider in Step 4 sets the default `frac_spawn` for all cells in the selected reach. User can later fine-tune per-cell in the shapefile.

Note: ReachConfig in `config.py` has all defaults as 0.0. The export must write the **spec defaults** above (not 0.0) so the simulation produces realistic results.

Junction IDs: auto-assigned from geometric analysis, displayed as read-only (editable via number input if user wants override).

**Species presets:**
- "Baltic Atlantic Salmon" → loads `configs/baltic_salmon_species.yaml`
- "Chinook Spring" → loads species block from `configs/example_a.yaml`
- "Custom" → expand all species parameters for manual editing
- Preset files are read-only templates; user can modify after loading

**Simulation config:**
- Start date, end date (date pickers)
- Backend: numpy / numba
- Trout capacity: auto-calculated as `n_cells * 15`
- Marine zones toggle: on/off (adds default Estuary/Coastal/Baltic zones)

### Step 5: Export

**Trigger:** Click "Export" (enabled when ≥1 reach configured with cells).

**Output ZIP contains:**

```
model_export/
├── Shapefile/
│   ├── Model.shp          # Cell polygons in UTM CRS
│   ├── Model.shx
│   ├── Model.dbf          # Attributes: ID_TEXT, REACH_NAME, AREA, M_TO_ESC,
│   ├── Model.prj          #   NUM_HIDING, FRACVSHL, FRACSPWN
│   └── Model.cpg
├── model_config.yaml       # Full inSTREAM config
├── {ReachName}-TimeSeriesInputs.csv  # Template per reach (dates + columns)
├── {ReachName}-Depths.csv            # Template (10 flows × n_cells)
└── {ReachName}-Vels.csv              # Template (10 flows × n_cells)
```

**Shapefile attributes (DBF):** `ID_TEXT`, `REACH_NAME`, `AREA` (m², converted to cm² by model at load time), `M_TO_ESC` (cm, distance to nearest reach endpoint × 100), `NUM_HIDING` (int), `FRACVSHL` (float 0-1), `FRACSPWN` (float 0-1)

Note: Centroids are NOT stored in the DBF — they're computed from polygon geometry at model load time by `PolygonMesh._build_cell_state()`.

**Template CSVs:**
- TimeSeriesInputs: header + 365 rows (1 year) with placeholder values (temp=10, flow=5, turbidity=2). User must replace with real time-series data.
- Depths: header + n_cells rows × 10 flow columns. Flow values are geometric sequence from 0.5 to 500 m³/s: `[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0]`. Default depth per cell: `0.3 + 0.7 * log(flow / 0.5) / log(1000) * cell_var` where `cell_var` is ±30% random per cell. User must replace with real hydraulic data (e.g., from River2D or HEC-RAS).
- Velocities: same 10 flows, default velocity: `0.1 + 0.5 * flow / 50 * cell_var`. Placeholder only.

Note: Example A uses 26 flows. 10 is sufficient for a template — users add more flow breakpoints when they have real hydraulic data. The template serves as a runnable starting point, not a substitute for calibrated hydraulics.

**"Load into Setup"** button:
1. Creates directory `app/data/fixtures/example_{model_name}/`
2. Writes shapefile + CSVs to that directory
3. Writes config YAML to `configs/example_{model_name}.yaml` (prefixed with "example" so it appears in the config dropdown which filters `p.stem.startswith("example")`)
4. Updates the module-level `CONFIG_CHOICES` dict to include the new config path
5. Uses `ui.update_select("config_file", choices=CONFIG_CHOICES, selected=new_config_path)` (Shiny for Python's standard input updater) to refresh the dropdown and select the new config
6. Sets a shared `reactive.value` (`_created_model_config`) that the Setup panel's server watches. When this value changes, the Setup panel loads the new config automatically (no simulated button click needed — pure reactive chain).
7. Shows notification: "Model loaded — switch to Setup tab to review"
8. No writes to `tests/` — that's for test fixtures only

---

## Mesh Generation Approaches

### Comparison

| Approach | Dependencies | Resolution | Boundary Fit | Speed | Best For |
|----------|-------------|-----------|--------------|-------|----------|
| **Hexagonal** | shapely (built-in) | Uniform | Moderate (clipped) | Fast (<1s) | General use, MVP |
| **Rectangular** | shapely (built-in) | Uniform | Poor (staircase) | Fast (<1s) | Quick prototyping |
| **Triangular FEM** | meshio (available) | Adaptive | Excellent | External tool | Complex geometries |
| **H3 Hexagonal** | h3 (available) | Hierarchical | Good | Fast | Large-scale studies |

### Implementation priority
1. **Phase 1 (MVP):** Hexagonal + Rectangular (shapely only, in-app generation)
2. **Phase 2:** Import FEM mesh (.msh, .2dm via meshio — FEMMesh backend already exists)
3. **Phase 3:** H3 hierarchical hexagons (h3 library already installed)
4. **Phase 4:** In-app adaptive triangular mesh (requires `triangle` library install)

All mesh types render identically in deck.gl (GeoJSON polygons). CellState is shape-agnostic — only needs area, centroids, and neighbor topology.

---

## File Map

| File | Lines (est.) | Responsibility |
|------|-------------|----------------|
| `app/modules/create_model_panel.py` | 400 | UI, action bar, state management, map interactions, Strahler filter |
| `app/modules/create_model_grid.py` | 300 | Hexagonal + rectangular cell generation, buffering, clipping |
| `app/modules/create_model_export.py` | 300 | Shapefile + YAML + CSV export, ZIP packaging, validation |
| `app/modules/create_model_reaches.py` | 250 | Reach selection, junction detection (geometric flow), topology |
| `app/modules/create_model_utils.py` | 150 | CRS auto-detection, UTM reprojection, species preset loading |

---

## Error Handling

| Scenario | Response |
|----------|----------|
| EU-Hydro timeout (>60s) | Notification: "Query timed out — try zooming in" |
| No features in view | Notification: "No rivers found — pan to a river area" |
| >2000 features | Auto-tile into 4 sub-queries, merge results |
| Click on empty map area | Ignored (no selection change) |
| Zero cells after clipping | Notification: "No cells generated — increase cell size or select more segments" |
| Export with missing params | Validation: highlight missing fields, block export |
| File write error | Notification with error message |

---

## Success Criteria

1. User can fetch EU-Hydro data for any European river area
2. Click-select river segments to define named reaches with auto-junctions
3. Generate hexagonal or rectangular cells with adjustable resolution (5-100m)
4. Configure all reach parameters via slide-out panel
5. Export ZIP with shapefile + YAML + template CSVs
6. Exported config loads and runs in SalmoPy without manual editing
7. All cell shapes (hex, rect, triangle) render correctly on the deck.gl map
8. CRS handled automatically (WGS84 for display, UTM for metric operations)
