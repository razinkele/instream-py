# Create Model UI — Design Spec

## Overview

Interactive model creation workflow in the SalmoPy app. Users download EU-Hydro river network data, select reaches, generate hexagonal habitat cells, configure parameters, and export a ready-to-run simulation config.

**Layout:** Hybrid — full-width map with compact action bar above. Configuration in a right slide-out panel. Status bar at bottom.

---

## Layout

### Action Bar (top, single row)

```
[EU-Hydro:] [🌊 Rivers] [💧 Water Bodies] [🏖️ Coastal] | [Model:] [✏️ Select Reaches] [⬡ Generate Cells] [⚙️ Configure] ──── [📦 Export]
```

- EU-Hydro buttons always enabled (fetch data for current view)
- Model buttons enable progressively: Select Reaches after data loaded → Generate Cells after reaches defined → Configure after cells generated → Export after config set
- Disabled buttons are greyed out with tooltip explaining what's needed

### Map (center, fills remaining space)

- Full-width WebGL deck.gl map (same MapWidget as other panels)
- Floating Strahler filter slider (top-left): range 1-9, default ≥3
- Navigation + fullscreen + legend controls (top-right)
- Click interaction: click river segments to select → highlight → assign to reach

### Slide-out Panel (right, 300px, toggled by Configure button)

- Reach selector dropdown
- Per-reach parameters: drift_conc, fish_pred_min, terr_pred_min, shading, prey_energy_density
- Cell size slider (5-100m, default 20m)
- Cell shape selector (Hexagonal / Rectangular)
- Species config (simplified: select from presets or import)

### Status Bar (bottom, single row)

```
Rivers: 142 | Water bodies: 3 | Selected reaches: 5 | Cells: 798 | [Ready to export]
```

---

## Workflow Steps

### Step 1: Fetch EU-Hydro Data

**Trigger:** Click "Rivers", "Water Bodies", or "Coastal" button.

**API:** EU-Hydro ArcGIS REST API
- Rivers: layer 4 (River_Net_lines) — Strahler-classified polylines
- Water Bodies: layer 2 (InlandWater) — polygons
- Coastal: layer 0 (Coastal_polygon) — polygons

**Behavior:**
- Query uses current map view bounding box (from widget view state)
- Max 2000 features per query
- Results displayed as deck.gl layers on the map
- Rivers: blue lines, width scaled by Strahler order
- Water bodies: semi-transparent blue fill
- Coastal: light blue fill
- Strahler filter slider hides rivers below threshold

**Data stored:** GeoDataFrame per layer type in reactive values.

### Step 2: Select Reaches

**Trigger:** Click "Select Reaches" button (enabled after rivers loaded).

**Behavior:**
- Enters selection mode — cursor changes, click handler activates
- Click a river segment → highlights in orange → prompts for reach name
- Shift+click to add more segments to the current reach
- Right-click to finish current reach and name it
- Selected reaches shown in distinct colors (Tab10 palette)
- Auto-detect junctions: where reaches share endpoints, automatically assign upstream/downstream junction IDs
- Junction connectivity displayed as arrows on the map

**Data stored:** Dict mapping reach_name → list of river segment geometries + junction topology.

### Step 3: Generate Hexagonal Cells

**Trigger:** Click "Generate Cells" button (enabled after ≥1 reach defined).

**Behavior:**
- For each reach: buffer river segments by cell_size/2
- Tessellate buffered area into hexagonal cells (using H3 or shapely)
- Each cell gets: reach_name, area, centroid, frac_spawn (from reach config), dist_escape (from distance to nearest reach endpoint), num_hiding (default), frac_vel_shelter (default)
- Live preview: cells shown on map as colored polygons
- Cell size slider adjustable — regenerates grid in real-time
- Cell shape toggle: hexagonal (default) or rectangular

**Algorithm (hexagonal):**
1. Buffer each reach's river segments by `cell_size * 0.6`
2. Create hexagonal grid covering the buffered extent
3. Clip hexagons to the buffered area
4. Assign each cell to its nearest reach
5. Compute cell attributes (area, centroid, adjacency)

**Data stored:** GeoDataFrame of cells with all attributes.

### Step 4: Configure Reach Parameters

**Trigger:** Click "Configure" button (enabled after cells generated). Opens right slide-out panel.

**Behavior:**
- Dropdown to select reach
- Per-reach parameters with sensible defaults:
  - `drift_conc`: 5.0e-9 (slider: 1e-10 to 1e-7, log scale)
  - `search_prod`: 8.0e-7
  - `prey_energy_density`: 4500
  - `shading`: 0.8 (slider: 0-1)
  - `fish_pred_min`: 0.97 (slider: 0.8-1.0)
  - `terr_pred_min`: 0.94 (slider: 0.8-1.0)
- Species preset dropdown: "Baltic Atlantic Salmon", "Chinook Spring", "Custom"
- Simulation dates: start/end date pickers
- Marine config toggle: enable/disable marine zones

### Step 5: Export

**Trigger:** Click "Export" button (enabled after config set).

**Output:**
- Shapefile (.shp + sidecar files) with cell polygons + attributes
- YAML config file matching inSTREAM config schema
- Per-reach CSV files: time series (template with date column), depths, velocities
- ZIP download containing all files
- Option: "Load into Setup" — directly loads the generated config into the Setup Review tab

---

## File Map

| File | Action |
|------|--------|
| `app/modules/create_model_panel.py` | Extend existing panel with all 5 steps |
| `app/modules/create_model_grid.py` | New: hexagonal cell generation logic |
| `app/modules/create_model_export.py` | New: config YAML + shapefile export |

---

## Technical Notes

### Hexagonal Grid Generation

Use `shapely` for hex tessellation (no H3 dependency needed):

```python
def hexagonal_grid(bounds, cell_size):
    """Generate hexagonal cells covering a bounding box."""
    w = cell_size
    h = cell_size * math.sqrt(3) / 2
    cols = int((bounds[2] - bounds[0]) / w) + 2
    rows = int((bounds[3] - bounds[1]) / h) + 2
    hexagons = []
    for row in range(rows):
        for col in range(cols):
            x = bounds[0] + col * w + (row % 2) * w / 2
            y = bounds[1] + row * h
            hex_poly = _hexagon(x, y, cell_size / 2)
            hexagons.append(hex_poly)
    return hexagons
```

### EU-Hydro API Limits

- Max 2000 features per query
- For large areas, tile the bbox into sub-queries
- Strahler filter reduces feature count significantly (Strahler ≥ 3 removes ~80% of tiny streams)

### Click-to-Select on deck.gl

Use the MapWidget's click input (`widget.click_input_id`) to get click coordinates. Find nearest river segment using spatial index. Highlight by changing the segment's color in the GeoJSON layer.

---

## Success Criteria

1. User can fetch EU-Hydro data for any European river area
2. Click-select river segments to define named reaches
3. Generate hexagonal cells with adjustable resolution
4. Configure reach parameters via slide-out panel
5. Export ZIP with shapefile + YAML config
6. Exported config loads and runs in SalmoPy without manual editing
