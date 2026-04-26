"""Create Model panel — extract local OSM river data and build model grid.

Workflow:
1. Pan/zoom the map to the area of interest
2. Select your country/region from the dropdown
3. Click "Fetch Rivers" to extract river network from local OSM PBF data
4. Filter by Strahler order, then click "Select Reaches" and click segments
5. Generate hexagonal/rectangular habitat cells from selected reaches
6. Export as shapefile + YAML config
"""

import json
import logging

import geopandas as gpd
from pathlib import Path
from shapely.validation import make_valid
from shapely.geometry import Point
from shapely.ops import unary_union
from shiny import module, reactive, render, ui

from shiny_deckgl import MapWidget, geojson_layer
from shiny_deckgl.controls import legend_control

# Optional imports — modules may not exist yet during early development
try:
    from modules.create_model_grid import generate_cells
except ImportError:
    generate_cells = None

try:
    from modules.create_model_reaches import (
        assign_segment_to_reach,
        remove_segment_from_reach,
        detect_junctions,
    )
except ImportError:
    assign_segment_to_reach = None
    remove_segment_from_reach = None
    detect_junctions = None

try:
    from modules.create_model_export import export_zip
except ImportError:
    export_zip = None

try:
    from modules.create_model_utils import detect_utm_epsg
except ImportError:
    detect_utm_epsg = None

try:
    from modules.create_model_osm import (
        query_waterways,
        query_water_bodies,
        WATERWAY_STRAHLER,
        GEOFABRIK_COUNTRIES,
        REGION_VIEWS,
    )
except ImportError:
    from app.modules.create_model_osm import (
        query_waterways,
        query_water_bodies,
        GEOFABRIK_COUNTRIES,
        REGION_VIEWS,
    )
logger = logging.getLogger(__name__)

BASEMAP_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

# Reach colour palette — high-contrast, avoids blue (river colour)
REACH_COLORS = [
    [255, 87, 34, 255],   # deep orange
    [76, 220, 80, 255],   # bright green
    [200, 50, 220, 255],  # magenta
    [255, 210, 0, 255],   # yellow
    [255, 60, 60, 255],   # bright red
    [0, 230, 180, 255],   # teal
    [255, 140, 0, 255],   # orange
    [180, 80, 255, 255],  # violet
]


try:
    from modules.create_model_marine import query_named_sea_polygon
except ImportError:  # pragma: no cover — matches existing fallback pattern
    query_named_sea_polygon = None  # type: ignore[assignment]

try:
    from modules.create_model_geocode import lookup_place_bbox
except ImportError:  # pragma: no cover
    lookup_place_bbox = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

@module.ui
def create_model_ui():
    _widget = MapWidget(
        "create_map",
        view_state={
            "longitude": 21.1,
            "latitude": 55.7,
            "zoom": 10,
            "pitch": 0,
            "bearing": 0,
        },
        style=BASEMAP_LIGHT,
        controls=[
            {"type": "navigation", "position": "top-right"},
            {"type": "fullscreen", "position": "top-right"},
            legend_control(position="bottom-left", show_default=False, show_checkbox=True),
        ],
        tooltip={
            "html": "<b>{nameText}</b><br/>Strahler: {STRAHLER}<br/>Type: {waterway}",
            "style": {
                "backgroundColor": "#fff",
                "color": "#333",
                "fontSize": "12px",
            },
        },
    )
    # Inline CSS matching sidebar theme
    _toolbar_css = ui.tags.style("""
    .cm-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:0.3rem; padding:0.3rem 0.5rem;
                  background:#1e293b; border-radius:6px; margin-bottom:0.3rem; }
    .cm-toolbar .btn-cm { background:rgba(43,184,157,.15); color:#2bb89d; border:1px solid rgba(43,184,157,.4);
                          border-radius:4px; padding:0.2rem 0.5rem; font-size:0.75rem; font-weight:600;
                          cursor:pointer; transition: background .15s, box-shadow .15s; }
    .cm-toolbar .btn-cm:hover { background:rgba(43,184,157,.3); }
    .cm-toolbar .btn-cm.active, .cm-toolbar .btn-cm[aria-pressed="true"] {
        background:#2bb89d; color:#fff; box-shadow:0 0 0 2px rgba(43,184,157,.5); }
    .cm-toolbar .cm-label { color:rgba(255,255,255,.6); font-size:0.72rem; margin-right:0.2rem; }
    .cm-toolbar .cm-sep { width:1px; height:1.2rem; background:rgba(255,255,255,.15); margin:0 0.2rem; }
    .cm-toolbar select, .cm-toolbar .form-select {
        background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.15);
        color:#fff; border-radius:3px; padding:0.25rem 0.3rem; font-size:0.78rem;
        height:auto; vertical-align:middle; }
    .cm-toolbar select option, .cm-toolbar .form-select option { background:#1e293b; color:#fff; }
    .cm-toolbar .form-group { margin-bottom:0; display:inline-flex; align-items:center; }
    .cm-toolbar .irs { margin:0; }
    .cm-toolbar .shiny-input-container { margin-bottom:0; }
    /* Ion Range Slider: make track/handle visible on dark toolbar */
    .cm-toolbar .irs--shiny .irs-bar { background:#2bb89d; border-color:#2bb89d; height:4px; top:25px; }
    .cm-toolbar .irs--shiny .irs-line { height:4px; top:25px; }
    .cm-toolbar .irs--shiny .irs-handle { background:#2bb89d; border-color:#1a9e82;
        width:14px; height:14px; top:19px; cursor:pointer; }
    .cm-toolbar .irs--shiny .irs-line { background:rgba(255,255,255,.15); border-color:transparent; }
    .cm-toolbar .irs--shiny .irs-min,
    .cm-toolbar .irs--shiny .irs-max { color:rgba(255,255,255,.4); background:transparent; }
    .cm-toolbar .irs--shiny .irs-single,
    .cm-toolbar .irs--shiny .irs-from,
    .cm-toolbar .irs--shiny .irs-to { background:#2bb89d; color:#fff; }
    .cm-toolbar .irs--shiny .irs-grid-text { color:rgba(255,255,255,.3); }
    /* Force slider track to fill container width */
    .cm-toolbar .irs { width:100% !important; }
    .cm-toolbar .irs--shiny { padding:0 6px; }
    /* Toolbar badges */
    .cm-badge { display:inline-block; padding:0.15rem 0.5rem; border-radius:3px;
                font-size:0.72rem; font-weight:600; margin-left:0.3rem; vertical-align:middle; }
    .cm-badge-select { color:#fff; animation: pulse-select 1.5s infinite; }
    .cm-badge-select-river { background:#3b82f6; }
    .cm-badge-select-lagoon { background:#06b6d4; }
    .cm-badge-select-sea { background:#6366f1; }
    .cm-badge-reach { background:rgba(255,160,0,.85); color:#fff; }
    .cm-badge-cells { background:rgba(34,197,94,.85); color:#fff; }
    @keyframes pulse-select { 0%,100%{opacity:1;} 50%{opacity:.6;} }
    /* Selection mode button highlights */
    .cm-toolbar .btn-sel-river.active { background:#3b82f6 !important; color:#fff !important;
        box-shadow:0 0 0 2px rgba(59,130,246,.6); }
    .cm-toolbar .btn-sel-lagoon.active { background:#06b6d4 !important; color:#fff !important;
        box-shadow:0 0 0 2px rgba(6,182,212,.6); }
    .cm-toolbar .btn-sel-sea.active { background:#6366f1 !important; color:#fff !important;
        box-shadow:0 0 0 2px rgba(99,102,241,.6); }
    """)

    return ui.card(
        ui.card_header(
            ui.div(
                ui.tags.span("Create Model"),
                ui.tags.span("", id="cm-gpu-slot"),  # GPU badge injected here by JS
                ui.tags.div(style="flex:1;"),  # spacer pushes help to right
                ui.input_action_button("help_btn", "? Help",
                                       class_="btn btn-cm",
                                       style="padding:0.15rem 0.5rem; font-size:0.72rem;",
                                       title="Show model creation guide"),
                style="display:flex; align-items:center; gap:0.4rem; width:100%;",
            ),
            style="padding:0.35rem 0.6rem;",
        ),
        _toolbar_css,
        # -- Compact toolbar matching sidebar theme ---
        ui.div(
            {"class": "cm-toolbar"},
            ui.tags.span("Region:", class_="cm-label"),
            ui.div(
                ui.input_select(
                    "osm_country", None,
                    choices=sorted(GEOFABRIK_COUNTRIES),
                    selected="lithuania",
                    width="120px",
                ),
                style="display:inline-block; vertical-align:middle;",
            ),
            ui.input_action_button("fetch_rivers", "🌊 Rivers",
                                   class_="btn btn-cm",
                                   title="Extract river network from local OSM data"),
            ui.input_action_button("fetch_water", "💧 Water",
                                   class_="btn btn-cm",
                                   title="Extract water bodies from local OSM data"),
            ui.input_action_button("fetch_sea", "🌊 Sea",
                                   class_="btn btn-cm",
                                   title="Fetch IHO sea areas from Marine Regions"),
            ui.tags.div(class_="cm-sep"),
            ui.tags.span("Strahler≥", class_="cm-label"),
            ui.div(
                ui.input_slider("strahler_min", None, min=1, max=9, value=3, step=1, width="100%"),
                style="display:inline-block; vertical-align:middle; width:160px;",
            ),
            ui.tags.div(class_="cm-sep"),
            ui.tags.span("River cell:", class_="cm-label"),
            ui.div(
                ui.input_slider("cell_size", None, min=5, max=100, value=20, step=5, width="100%"),
                style="display:inline-block; vertical-align:middle; width:150px;",
            ),
            ui.tags.span("Water cell:", class_="cm-label"),
            ui.div(
                ui.input_slider("water_cell_size", None, min=50, max=1000, value=200, step=50, width="100%"),
                style="display:inline-block; vertical-align:middle; width:150px;",
            ),
            ui.tags.span("Sea cell:", class_="cm-label"),
            ui.div(
                ui.input_slider("sea_cell_size", None, min=500, max=10000, value=2000, step=500, width="100%"),
                style="display:inline-block; vertical-align:middle; width:150px;",
            ),
            ui.div(
                ui.input_select("cell_shape", None,
                                choices={"hexagonal": "Hexagonal", "rectangular": "Rectangular"},
                                selected="hexagonal", width="120px"),
                style="display:inline-flex; align-items:center;",
            ),
            ui.tags.div(class_="cm-sep"),
            ui.input_action_button("sel_river_btn", "🏞️ River",
                                   class_="btn btn-cm btn-sel-river",
                                   title="Select river segments / river polygons"),
            ui.input_action_button("sel_lagoon_btn", "💧 Lagoon",
                                   class_="btn btn-cm btn-sel-lagoon",
                                   title="Select lagoon / lake / water body polygons"),
            ui.input_action_button("sel_sea_btn", "🌊 Sea",
                                   class_="btn btn-cm btn-sel-sea",
                                   title="Select sea area polygons"),
            ui.input_action_button("clear_reaches_btn", "🗑 Clear",
                                   class_="btn btn-cm",
                                   title="Clear all selected reaches and cells"),
            ui.input_action_button("generate_cells_btn", "⬡ Cells",
                                   class_="btn btn-cm",
                                   title="Generate habitat cells from selected reaches"),
            ui.input_action_button("export_btn", "📦 Export",
                                   class_="btn btn-cm",
                                   title="Export shapefile + YAML config as ZIP"),
            ui.tags.div(style="flex:1;"),  # spacer
            ui.output_ui("toolbar_badges"),
        ),
        ui.div(
            {"class": "cm-toolbar"},
            ui.tags.span("Auto:", class_="cm-label"),
            ui.input_text(
                "place_name", None,
                placeholder="Place name…",
                width="180px",
            ),
            ui.input_action_button("find_btn", "🔍 Find",
                                   class_="btn btn-cm",
                                   title="Look up a place via Nominatim and load Rivers + Water"),
            ui.tags.div(class_="cm-sep"),
            ui.input_action_button("auto_extract_btn", "✨ Auto-extract",
                                   class_="btn btn-cm",
                                   title="Filter water polygons to the centerline-connected component"),
            ui.tags.div(class_="cm-sep"),
            ui.input_action_button("auto_split_btn", "⚡ Auto-split",
                                   class_="btn btn-cm",
                                   title="Partition extracted polygons into N reaches by along-channel distance"),
            ui.tags.span("N:", class_="cm-label"),
            ui.div(
                ui.input_numeric("auto_split_n", None, value=4, min=2, max=8, step=1, width="70px"),
                style="display:inline-block; vertical-align:middle;",
            ),
        ),
        # -- Map (shown immediately, before any fetch) ---
        _widget.ui(height="550px"),
        # Hidden action button + JS bridge for map click events.
        # Action buttons are event-type inputs: each click increments
        # a counter, and @reactive.event always fires on increment.
        # The click coordinate data is stored in a separate hidden input.
        ui.div(
            ui.input_action_button("map_click_trigger", "click", style="display:none"),
            ui.input_text("map_click_coords", "", value=""),
            style="display:none !important; height:0; overflow:hidden;",
        ),
        ui.tags.script("""
        // Bridge: intercept shiny_deckgl map_click → trigger hidden action button
        document.addEventListener('DOMContentLoaded', function() {
          function patchWhenReady() {
            if (typeof Shiny === 'undefined' || !Shiny.setInputValue) {
              setTimeout(patchWhenReady, 200);
              return;
            }
            var srcKey = 'create-create_map_map_click';
            var coordKey = 'create-map_click_coords';
            var triggerKey = 'create-map_click_trigger';
            var clickCount = 0;
            var origSetInput = Shiny.setInputValue.bind(Shiny);
            Shiny.setInputValue = function(name, value, opts) {
              origSetInput(name, value, opts);
              if (name === srcKey && value) {
                clickCount++;
                var json = JSON.stringify({
                  longitude: value.longitude,
                  latitude: value.latitude
                });
                origSetInput(coordKey, json);
                origSetInput(triggerKey + ':shiny.action', clickCount, {priority: 'event'});
              }
            };
            // Listen for eval_js custom messages from Python
            Shiny.addCustomMessageHandler('eval_js', function(js) {
              try { eval(js); } catch(e) { console.warn('eval_js error:', e); }
            });
          }
          patchWhenReady();
        });
        """),
        # -- Status (compact) ---
        ui.output_ui("fetch_status"),
        ui.output_ui("data_summary"),
        ui.output_ui("workflow_status"),
        full_screen=True,
    )


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

@module.server
def create_model_server(input, output, session):
    _widget = MapWidget(
        "create_map",
        view_state={"longitude": 21.1, "latitude": 55.7, "zoom": 10},
        style=BASEMAP_LIGHT,
    )

    # -- Existing reactive state --
    _rivers_gdf = reactive.value(None)
    _water_gdf = reactive.value(None)
    _sea_gdf = reactive.value(None)
    _fetch_msg = reactive.value("")

    _map_initialized = reactive.value(False)

    @reactive.effect
    async def _init_map():
        """Force deck.gl to initialize the map on first render."""
        if _map_initialized():
            return
        import asyncio
        await asyncio.sleep(1.5)  # Wait for tab to render in DOM
        try:
            await _widget.update(session, [])  # Empty layer list triggers map init
            _map_initialized.set(True)
        except Exception:
            pass  # Tab not visible yet — will retry via invalidate_later
            reactive.invalidate_later(2)

    # -- New reactive state --
    _reaches_dict = reactive.value({})       # {reach_name: [LineString, ...]}
    _cells_gdf = reactive.value(None)        # GeoDataFrame of generated cells
    _selection_mode = reactive.value("")       # "", "river", "lagoon", or "sea"
    _current_reach_name = reactive.value("")  # active reach being built
    _workflow_msg = reactive.value("")
    _auto_extract_done = reactive.value(False)
    _mouth_lon_lat = reactive.value(None)
    _finding = reactive.value(False)

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _get_view_bbox():
        """Get the current map view bounding box from the widget's view state input."""
        try:
            vs = getattr(input, _widget.view_state_input_id)()
            if vs:
                # Approximate bbox from center + zoom
                lon = vs.get("longitude", 21.1)
                lat = vs.get("latitude", 55.7)
                zoom = vs.get("zoom", 10)
                # Approximate span from zoom level
                span = 360 / (2 ** zoom)
                return (lon - span / 2, lat - span / 3, lon + span / 2, lat + span / 3)
        except Exception:
            pass
        # Default: Curonian Lagoon area
        return (20.9, 55.6, 21.3, 55.85)

    def _filtered_rivers_gdf():
        """Return the rivers GeoDataFrame filtered by the current Strahler threshold."""
        gdf = _rivers_gdf()
        if gdf is None:
            return None
        strahler_col = None
        for c in gdf.columns:
            if "strahler" in c.lower():
                strahler_col = c
                break
        if strahler_col is None:
            return gdf
        threshold = input.strahler_min()
        return gdf[gdf[strahler_col] >= threshold].copy()

    def _build_river_layer(gdf):
        """Build deck.gl GeoJSON layers from a rivers GeoDataFrame.

        River polygons are rendered as filled shapes.  Line features
        are split by waterway type and styled with MapLibre-like width
        scaling: rivers get thick lines, streams get thin ones.
        Returns a list of layers.
        """
        layers = []
        is_poly = gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        polys = gdf[is_poly]
        lines = gdf[~is_poly]

        if len(polys) > 0:
            geoj = json.loads(polys.to_json())
            layers.append(geojson_layer(
                id="osm-river-polys",
                data=geoj,
                getFillColor=[135, 185, 230, 140],
                getLineColor=[30, 100, 200, 200],
                getLineWidth=1,
                lineWidthMinPixels=1,
                pickable=True,
                stroked=True,
                filled=True,
            ))

        if len(lines) > 0:
            # Split lines by waterway type for MapLibre-style width scaling.
            # river/canal get thick lines; stream/ditch get thin ones.
            wtype_col = "waterway" if "waterway" in lines.columns else None
            big = lines[lines[wtype_col].isin(["river", "canal"])] if wtype_col else lines.iloc[:0]
            small = lines[~lines.index.isin(big.index)] if wtype_col else lines

            if len(big) > 0:
                geoj = json.loads(big.to_json())
                layers.append(geojson_layer(
                    id="osm-river-lines-big",
                    data=geoj,
                    getLineColor=[100, 160, 220, 220],
                    getLineWidth=12,
                    lineWidthMinPixels=4,
                    lineWidthMaxPixels=24,
                    pickable=True,
                    stroked=True,
                    filled=False,
                ))
            if len(small) > 0:
                geoj = json.loads(small.to_json())
                layers.append(geojson_layer(
                    id="osm-river-lines-small",
                    data=geoj,
                    getLineColor=[30, 100, 200, 180],
                    getLineWidth=3,
                    lineWidthMinPixels=1,
                    lineWidthMaxPixels=8,
                    pickable=True,
                    stroked=True,
                    filled=False,
                ))
        return layers

    def _build_water_layer(gdf):
        """Build a deck.gl GeoJSON layer from a water bodies GeoDataFrame."""
        sel = _selection_mode()
        simplified = gdf.copy()
        simplified["geometry"] = simplified.geometry.simplify(0.001, preserve_topology=True)
        simplified = simplified[~simplified.geometry.is_empty]
        logger.info("Water layer: %d features (simplified from %d)", len(simplified), len(gdf))
        geoj = json.loads(simplified.to_json())
        return geojson_layer(
            id="osm-water",
            data=geoj,
            getFillColor=[135, 206, 235, 120],
            getLineColor=[70, 130, 180, 150],
            getLineWidth=1,
            pickable=(sel == "lagoon"),
            stroked=True,
            filled=True,
        )

    def _build_sea_layer(gdf):
        """Build a deck.gl GeoJSON layer from sea area polygons."""
        sel = _selection_mode()
        geoj = json.loads(gdf.to_json())
        return geojson_layer(
            id="marine-sea-areas",
            data=geoj,
            getFillColor=[50, 80, 140, 40],
            getLineColor=[30, 60, 120, 150],
            getLineWidth=2,
            lineWidthMinPixels=1,
            pickable=(sel == "sea"),
            stroked=True,
            filled=True,
        )

    def _build_reach_layers():
        """Build one GeoJSON layer per reach with distinct colours."""
        layers = []
        reaches = _reaches_dict()
        for idx, (name, reach_data) in enumerate(reaches.items()):
            segments = reach_data["segments"] if isinstance(reach_data, dict) else reach_data
            if not segments:
                continue
            color = REACH_COLORS[idx % len(REACH_COLORS)]
            reach_type = reach_data.get("type", "river") if isinstance(reach_data, dict) else "river"
            features = []
            for seg in segments:
                features.append({
                    "type": "Feature",
                    "geometry": seg.__geo_interface__,
                    "properties": {"reach": name},
                })
            geoj = {"type": "FeatureCollection", "features": features}

            if reach_type == "water":
                # Water body: semi-transparent fill + bold outline
                fill_color = [color[0], color[1], color[2], 60]
                layers.append(geojson_layer(
                    id=f"reach-{name}",
                    data=geoj,
                    getFillColor=fill_color,
                    getLineColor=color,
                    getLineWidth=3,
                    lineWidthMinPixels=2,
                    pickable=True,
                    stroked=True,
                    filled=True,
                ))
            else:
                # River: glow outline + bold core line
                outline_color = [min(255, c + 60) if i < 3 else 100 for i, c in enumerate(color)]
                layers.append(geojson_layer(
                    id=f"reach-outline-{name}",
                    data=geoj,
                    getLineColor=outline_color,
                    getLineWidth=14,
                    lineWidthMinPixels=8,
                    lineWidthMaxPixels=20,
                    pickable=False,
                    stroked=True,
                    filled=False,
                ))
                layers.append(geojson_layer(
                    id=f"reach-{name}",
                    data=geoj,
                    getLineColor=color,
                    getLineWidth=6,
                    lineWidthMinPixels=4,
                    lineWidthMaxPixels=12,
                    pickable=True,
                    stroked=True,
                    filled=False,
                ))
        return layers

    def _build_cells_layer():
        """Build a GeoJSON layer for generated cells."""
        gdf = _cells_gdf()
        if gdf is None:
            return None
        geoj = json.loads(gdf.to_json())
        return geojson_layer(
            id="habitat-cells",
            data=geoj,
            getFillColor=[100, 200, 100, 80],
            getLineColor=[50, 150, 50, 180],
            getLineWidth=1,
            pickable=True,
            stroked=True,
            filled=True,
        )

    async def _refresh_map():
        """Rebuild all map layers from current state and push to widget."""
        layers = []
        # Sea areas (bottommost)
        sea = _sea_gdf()
        if sea is not None and len(sea) > 0:
            layers.append(_build_sea_layer(sea))
        # Water bodies
        water = _water_gdf()
        if water is not None and len(water) > 0:
            logger.info("Water layer: %d features", len(water))
            layers.append(_build_water_layer(water))
        else:
            logger.info("No water features to display")
        # Filtered rivers (polygons + line fallbacks)
        fgdf = _filtered_rivers_gdf()
        if fgdf is not None and len(fgdf) > 0:
            layers.extend(_build_river_layer(fgdf))
        # Cells
        cells_lyr = _build_cells_layer()
        if cells_lyr is not None:
            layers.append(cells_lyr)
        # Reach overlays (top)
        reach_layers = _build_reach_layers()
        layers.extend(reach_layers)
        await _widget.update(session, layers)

    # -----------------------------------------------------------------
    # Fetch handlers (existing, preserved)
    # -----------------------------------------------------------------

    async def _do_fetch_rivers():
        """Body lift of fetch_rivers — callable from the Find handler too.

        Sets `_auto_extract_done.set(False)` as the first line because fresh
        OSM data invalidates any prior Auto-extract result regardless of who
        triggered the fetch (button or Find).
        """
        _auto_extract_done.set(False)
        country = input.osm_country()
        bbox = _get_view_bbox()
        _fetch_msg.set(f"Extracting river network for {country} (bbox clipped)...")

        import asyncio
        loop = asyncio.get_running_loop()

        def _progress(msg):
            _fetch_msg.set(msg)

        gdf = await loop.run_in_executor(
            None, lambda: query_waterways(country, bbox, progress_cb=_progress)
        )

        if gdf is None or len(gdf) == 0:
            _fetch_msg.set("No river features found. Try zooming in or selecting a different region.")
            return

        # Count polygons vs lines
        is_poly = gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        n_polys = int(is_poly.sum())
        n_lines = len(gdf) - n_polys

        # Auto-fetch water body polygons (lakes, lagoons) for context
        _fetch_msg.set(f"Got {n_polys} river polygons + {n_lines} stream lines. Fetching water bodies...")
        water_gdf = await loop.run_in_executor(
            None, lambda: query_water_bodies(country, bbox)
        )

        if water_gdf is not None and len(water_gdf) > 0:
            _water_gdf.set(water_gdf)
        else:
            water_gdf = None

        # Clip only small stream/ditch/drain lines that cross water bodies.
        # Never clip river/canal centerlines — they legitimately flow through
        # lagoons, lakes, and their own river polygons.
        clip_types = {"stream", "ditch", "drain"}
        if water_gdf is not None and len(water_gdf) > 0 and n_lines > 0:
            _fetch_msg.set("Clipping small streams to exclude lagoon/lake segments...")
            try:
                valid_geoms = water_gdf.geometry.apply(
                    lambda g: make_valid(g) if g and not g.is_valid else g
                )
                repaired = valid_geoms.apply(lambda g: g.buffer(0) if g and not g.is_empty else g)
                water_union = repaired.unary_union
            except Exception as e:
                logger.warning("Water union failed, skipping stream clipping: %s", e)
                water_union = None

            if water_union is not None:
                keep_mask = []
                for idx, row in gdf.iterrows():
                    geom = row.geometry
                    if geom is None or geom.is_empty:
                        keep_mask.append(False)
                    elif geom.geom_type in ("Polygon", "MultiPolygon"):
                        keep_mask.append(True)
                    elif row.get("waterway", "") not in clip_types:
                        keep_mask.append(True)
                    else:
                        try:
                            inside = geom.intersection(water_union)
                            frac_inside = inside.length / geom.length if geom.length > 0 else 0
                            keep_mask.append(frac_inside < 0.5)
                        except Exception:
                            keep_mask.append(True)
                n_before = len(gdf)
                gdf = gdf[keep_mask].reset_index(drop=True)
                n_clipped = n_before - len(gdf)
                if n_clipped > 0:
                    _fetch_msg.set(f"Clipped {n_clipped} lagoon/lake stream segments.")

        _rivers_gdf.set(gdf)

        await _refresh_map()
        is_poly_final = gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        water_msg = f" + {len(water_gdf)} water bodies" if water_gdf is not None else ""
        _fetch_msg.set(f"Loaded {int(is_poly_final.sum())} river polygons + {int((~is_poly_final).sum())} stream lines{water_msg}.")

    @reactive.effect
    @reactive.event(input.fetch_rivers)
    async def _on_fetch_rivers():
        await _do_fetch_rivers()

    async def _do_fetch_water():
        """Body lift of fetch_water — callable from Find too.
        Resets _auto_extract_done first since fresh data invalidates prior extract.
        """
        _auto_extract_done.set(False)
        country = input.osm_country()
        bbox = _get_view_bbox()
        _fetch_msg.set(f"Extracting water bodies for {country} (bbox clipped)...")

        import asyncio
        loop = asyncio.get_running_loop()

        gdf = await loop.run_in_executor(
            None, lambda: query_water_bodies(country, bbox)
        )

        if gdf is None or len(gdf) == 0:
            _fetch_msg.set("No water bodies found in this area.")
            return

        _water_gdf.set(gdf)
        await _refresh_map()
        _fetch_msg.set(f"Loaded {len(gdf)} water bodies from local OSM data.")

    @reactive.effect
    @reactive.event(input.fetch_water)
    async def _on_fetch_water():
        await _do_fetch_water()

    @reactive.effect
    @reactive.event(input.find_btn)
    async def _on_find():
        import asyncio
        import math

        if lookup_place_bbox is None:
            ui.notification_show(
                "Geocoder helper unavailable (create_model_geocode failed to import)",
                type="error",
            )
            return
        if _finding():
            return
        _finding.set(True)
        try:
            name = input.place_name() or ""
            if not name.strip():
                ui.notification_show("Type a place name first", type="warning")
                return

            result = await asyncio.to_thread(lookup_place_bbox, name)
            if result is None:
                ui.notification_show(f"No place found for '{name}'", type="warning")
                return

            country_geofabrik, bbox = result
            lon_w, lat_s, lon_e, lat_n = bbox
            cx = (lon_w + lon_e) / 2.0
            cy = (lat_s + lat_n) / 2.0
            span = max(lon_e - lon_w, lat_n - lat_s)
            zoom = int(max(5, min(13, 9 - math.log2(max(span, 0.05)))))

            if country_geofabrik is None:
                ui.notification_show(
                    f"Place found at ({cy:.2f}, {cx:.2f}) but its country has no "
                    "Geofabrik OSM extract; map zoomed but Rivers/Water not auto-fetched",
                    type="warning",
                )
                _pending_fly_to.set((cx, cy, zoom))
                return

            ui.update_select("osm_country", selected=country_geofabrik)
            _pending_fly_to.set((cx, cy, zoom))
            ui.notification_show(
                f"Loaded {name} (lat {cy:.2f}, lon {cx:.2f}). Fetching rivers and water…",
                type="message",
            )
            await _do_fetch_rivers()
        finally:
            _finding.set(False)

    # -----------------------------------------------------------------
    # Fetch sea areas (Marine Regions IHO)
    # -----------------------------------------------------------------

    @reactive.effect
    @reactive.event(input.fetch_sea)
    async def _on_fetch_sea():
        _fetch_msg.set("Fetching IHO sea areas from Marine Regions...")
        bbox = _get_view_bbox()

        import asyncio
        # Guard against the helper-module import having failed (matches the
        # graceful-degradation pattern of other panel imports at lines 25-49)
        if query_named_sea_polygon is None:
            _fetch_msg.set(
                "Marine Regions helper unavailable (create_model_marine module "
                "failed to import). Sea-fetch disabled."
            )
            return
        loop = asyncio.get_running_loop()
        gdf = await loop.run_in_executor(None, query_named_sea_polygon, bbox)
        # query_named_sea_polygon already does the bbox-intersect + centroid-cover
        # post-filter that this handler used to do inline (see create_model_marine.py).
        # It returns a GeoDataFrame in EPSG:4326 with columns ['name', 'geometry'],
        # or None on failure / empty result.
        if gdf is None or len(gdf) == 0:
            _fetch_msg.set("No sea areas found — try zooming out to see the coast.")
            return
        gdf = gdf.copy()
        gdf["geometry"] = gdf.geometry.simplify(0.01, preserve_topology=True)
        _sea_gdf.set(gdf)
        names = ", ".join(gdf["name"].dropna().unique()[:5]) if "name" in gdf.columns else ""
        _fetch_msg.set(f"Loaded {len(gdf)} sea areas. {names}")
        await _refresh_map()

    # -----------------------------------------------------------------
    # Strahler filter — re-render map when slider changes
    # -----------------------------------------------------------------

    _last_region = reactive.value("")
    _pending_fly_to = reactive.value(None)  # (lon, lat, zoom) or None

    @reactive.effect
    @reactive.event(input.osm_country)
    async def _on_region_change():
        """Fly the map to the selected region center on user change."""
        country = input.osm_country()
        prev = _last_region()
        _last_region.set(country)
        if not prev:
            return  # skip initial dropdown fire
        view = REGION_VIEWS.get(country)
        if not view:
            return
        if not _map_initialized():
            _pending_fly_to.set(view)  # defer until map ready
            return
        lon, lat, zoom = view
        await _widget.fly_to(session, lon, lat, zoom=zoom)

    @reactive.effect
    async def _flush_pending_fly():
        """Fly to pending region after map initialization completes."""
        if not _map_initialized():
            return
        pending = _pending_fly_to()
        if pending is None:
            return
        _pending_fly_to.set(None)
        import asyncio
        await asyncio.sleep(0.5)  # let deck.gl finish layer init
        lon, lat, zoom = pending
        await _widget.fly_to(session, lon, lat, zoom=zoom)

    @reactive.effect
    @reactive.event(input.strahler_min)
    async def _on_strahler_change():
        if _rivers_gdf() is not None:
            await _refresh_map()

    # -----------------------------------------------------------------
    # Clear all reaches and cells
    # -----------------------------------------------------------------

    @reactive.effect
    @reactive.event(input.clear_reaches_btn)
    async def _on_clear_reaches():
        _reaches_dict.set({})
        _cells_gdf.set(None)
        _selection_mode.set("")
        _current_reach_name.set("")
        _workflow_msg.set("All reaches and cells cleared.")
        await _refresh_map()

    # -----------------------------------------------------------------
    # Select Reaches toggle
    # -----------------------------------------------------------------

    def _toggle_selection_mode(mode: str):
        """Toggle a selection mode on/off. Only one can be active at a time."""
        current = _selection_mode()
        if current == mode:
            # Deactivate
            _selection_mode.set("")
            _current_reach_name.set("")
            _workflow_msg.set("Selection mode OFF.")
        else:
            # Activate — auto-name next reach
            reaches = _reaches_dict()
            idx = len(reaches) + 1
            name = f"reach_{idx}"
            _current_reach_name.set(name)
            _selection_mode.set(mode)
            labels = {"river": "🏞️ River", "lagoon": "💧 Lagoon", "sea": "🌊 Sea"}
            _workflow_msg.set(
                f"{labels[mode]} selection ON — click features to add to '{name}'. "
                "Click the same button again to finish."
            )

    @reactive.effect
    @reactive.event(input.sel_river_btn)
    async def _on_sel_river():
        _toggle_selection_mode("river")
        await _refresh_map()

    @reactive.effect
    @reactive.event(input.sel_lagoon_btn)
    async def _on_sel_lagoon():
        _toggle_selection_mode("lagoon")
        await _refresh_map()

    @reactive.effect
    @reactive.event(input.sel_sea_btn)
    async def _on_sel_sea():
        _toggle_selection_mode("sea")
        await _refresh_map()

    # Highlight the active selection mode button via JS
    @reactive.effect
    def _update_sel_buttons():
        mode = _selection_mode()
        js = """
        document.querySelectorAll('.btn-sel-river,.btn-sel-lagoon,.btn-sel-sea')
          .forEach(b => b.classList.remove('active'));
        """
        if mode == "river":
            js += "document.querySelector('.btn-sel-river')?.classList.add('active');"
        elif mode == "lagoon":
            js += "document.querySelector('.btn-sel-lagoon')?.classList.add('active');"
        elif mode == "sea":
            js += "document.querySelector('.btn-sel-sea')?.classList.add('active');"
        session.send_custom_message("eval_js", js)

    # -----------------------------------------------------------------
    # Click-to-select handler
    # -----------------------------------------------------------------
    # JS bridge: shiny_deckgl fires Shiny.setInputValue for map clicks,
    # our monkey-patch in the UI script intercepts that and also fires
    # a hidden action button (map_click_trigger) + text input (map_click_coords).
    # This gives us a reliable @reactive.event trigger.

    @reactive.effect
    @reactive.event(input.map_click_trigger)
    async def _on_map_click():
        """Handle map-level click — find nearest river segment.

        Triggered by a hidden action button that JS increments on
        every map click. Coordinates come from a companion text input.
        """
        raw = input.map_click_coords()
        if not raw:
            return
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return

        lon = data.get("longitude")
        lat = data.get("latitude")
        if lon is None or lat is None:
            return

        sel = _selection_mode()
        if not sel:
            _workflow_msg.set(f"Click: ({lon:.4f}, {lat:.4f}) — select a mode first (River / Lagoon / Sea)")
            return

        from shapely.geometry import Point as _Pt
        click_pt = _Pt(lon, lat)

        reach_name = _current_reach_name()
        if not reach_name:
            return

        # Helper: add a polygon geometry to the current reach
        def _add_polygon_to_reach(geom, reach_type, label=""):
            if geom.geom_type == "MultiPolygon":
                geom = max(geom.geoms, key=lambda g: g.area)
            reaches = dict(_reaches_dict())
            if reach_name not in reaches:
                reaches[reach_name] = {
                    "segments": [], "properties": [],
                    "color": REACH_COLORS[len(reaches) % len(REACH_COLORS)],
                    "type": reach_type,
                }
            rd = reaches[reach_name]
            if not any(g.equals(geom) for g in rd["segments"]):
                rd["segments"].append(geom)
                rd["properties"].append({})
            reaches[reach_name] = rd
            _reaches_dict.set(reaches)
            n = len(rd["segments"])
            suffix = f" ({label})" if label else ""
            _workflow_msg.set(f"Added {reach_type} feature{suffix} to '{reach_name}' ({n} features).")

        # ── LAGOON mode: water bodies (lakes, lagoons, transit waters) ──
        if sel == "lagoon":
            water = _water_gdf()
            if water is not None and len(water) > 0:
                hits = water[water.geometry.contains(click_pt)]
                if len(hits) == 0:
                    dists = water.geometry.distance(click_pt)
                    nearest_idx = dists.idxmin()
                    if dists.loc[nearest_idx] < 0.02:
                        hits = water.iloc[[nearest_idx]]
                if len(hits) > 0:
                    label = hits.iloc[0].get("nameText", "") if "nameText" in hits.columns else ""
                    _add_polygon_to_reach(hits.geometry.iloc[0], "water", label)
                    await _refresh_map()
                    return
            _workflow_msg.set(f"No lagoon/water body at ({lon:.4f}, {lat:.4f}) — fetch Water first.")
            return

        # ── SEA mode: IHO sea area polygons ──
        if sel == "sea":
            sea = _sea_gdf()
            if sea is not None and len(sea) > 0:
                hits = sea[sea.geometry.contains(click_pt)]
                if len(hits) == 0:
                    dists = sea.geometry.distance(click_pt)
                    nearest_idx = dists.idxmin()
                    if dists.loc[nearest_idx] < 0.05:
                        hits = sea.iloc[[nearest_idx]]
                if len(hits) > 0:
                    label = hits.iloc[0].get("name", "") if "name" in hits.columns else ""
                    _add_polygon_to_reach(hits.geometry.iloc[0], "sea", label)
                    await _refresh_map()
                    return
            _workflow_msg.set(f"No sea area at ({lon:.4f}, {lat:.4f}) — fetch Sea first.")
            return

        # ── RIVER mode: river polygons + line fallbacks ──
        rivers = _filtered_rivers_gdf()
        if rivers is None or len(rivers) == 0:
            _workflow_msg.set("No rivers loaded — fetch Rivers first.")
            return

        # Split into polygons and lines (filter out exotic geometry types)
        is_poly = rivers.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        is_line = rivers.geometry.geom_type.isin(["LineString", "MultiLineString"])
        polys = rivers[is_poly]
        lines = rivers[is_line]

        if len(polys) == 0 and len(lines) == 0:
            _workflow_msg.set(f"No valid river geometries near ({lon:.4f}, {lat:.4f}).")
            return

        if len(polys) > 0:
            hits = polys[polys.geometry.contains(click_pt)]
            if len(hits) > 0:
                label = hits.iloc[0].get("nameText", "") if "nameText" in hits.columns else ""
                _add_polygon_to_reach(hits.geometry.iloc[0], "water", label)
                await _refresh_map()
                return

        # Fallback: nearest line segment (small streams)
        if len(lines) > 0:
            dists = lines.geometry.distance(click_pt)
            nearest_idx = dists.idxmin()
            min_dist = dists.loc[nearest_idx]
        else:
            # All features are polygons but click missed — find nearest polygon boundary
            dists = polys.geometry.boundary.distance(click_pt)
            nearest_idx = dists.idxmin()
            min_dist = dists.loc[nearest_idx]
            if min_dist < 0.005:
                label = polys.loc[nearest_idx].get("nameText", "") if "nameText" in polys.columns else ""
                _add_polygon_to_reach(polys.geometry.loc[nearest_idx], "water", label)
                await _refresh_map()
            else:
                _workflow_msg.set(f"Click ({lon:.4f}, {lat:.4f}) too far from any river polygon ({min_dist:.4f}°).")
            return  # always return from polygon-only path

        if min_dist > 0.02:
            _workflow_msg.set(
                f"Click ({lon:.4f}, {lat:.4f}) too far from any river ({min_dist:.4f}°)."
            )
            return

        geom = lines.geometry.loc[nearest_idx]
        if geom.geom_type == "MultiLineString":
            geom = max(geom.geoms, key=lambda g: g.length)
        if geom.geom_type != "LineString":
            _workflow_msg.set(f"Clicked geometry is {geom.geom_type}, expected LineString.")
            return

        reaches = dict(_reaches_dict())
        if assign_segment_to_reach is not None:
            reaches = assign_segment_to_reach(reaches, reach_name, geom, {})
        else:
            if reach_name not in reaches:
                reaches[reach_name] = {
                    "segments": [], "properties": [],
                    "color": REACH_COLORS[len(reaches) % len(REACH_COLORS)],
                    "type": "river",
                }
            rd = reaches[reach_name]
            rd["segments"].append(geom)
            rd["properties"].append({})

        _reaches_dict.set(reaches)

        r = reaches.get(reach_name, {})
        n_segs = len(r["segments"]) if isinstance(r, dict) else len(r)
        _workflow_msg.set(f"Added segment to '{reach_name}' ({n_segs} segments total).")
        await _refresh_map()

    # -----------------------------------------------------------------
    # Generate cells
    # -----------------------------------------------------------------

    @reactive.effect
    @reactive.event(input.generate_cells_btn)
    async def _on_generate_cells():
        reaches = _reaches_dict()
        if not reaches:
            _workflow_msg.set("No reaches defined. Click 'Select Reaches' first.")
            return

        if generate_cells is None:
            _workflow_msg.set(
                "Cell generation module not available (create_model_grid not implemented)."
            )
            return

        _workflow_msg.set("Generating habitat cells...")

        river_cell_size = input.cell_size()
        water_cell_size = input.water_cell_size()
        sea_cell_size = input.sea_cell_size()
        cell_shape = input.cell_shape()

        # Split reaches by type
        river_reaches = {}
        water_reaches = {}
        sea_reaches = {}
        for name, rd in reaches.items():
            if not isinstance(rd, dict):
                rd = {"segments": rd, "type": "river"}
            rtype = rd.get("type", "river")
            n_segs = len(rd.get("segments", []))
            geom_types = [g.geom_type for g in rd.get("segments", [])]
            logger.info("Reach '%s': type=%s, %d segments, geom_types=%s", name, rtype, n_segs, geom_types)
            if rtype == "sea":
                sea_reaches[name] = rd
            elif rtype == "water":
                water_reaches[name] = rd
            else:
                river_reaches[name] = rd

        logger.info("Split: %d river, %d water, %d sea reaches",
                     len(river_reaches), len(water_reaches), len(sea_reaches))

        if not river_reaches and not water_reaches and not sea_reaches:
            _workflow_msg.set("Reaches are empty — no segments to generate cells from.")
            return

        import asyncio
        loop = asyncio.get_running_loop()
        try:
            all_cells = []
            # Generate river cells
            if river_reaches:
                river_cells = await loop.run_in_executor(
                    None,
                    lambda: generate_cells(
                        reach_segments=river_reaches,
                        cell_size=river_cell_size,
                        cell_shape=cell_shape,
                    ),
                )
                if river_cells is not None and len(river_cells) > 0:
                    all_cells.append(river_cells)
            # Generate water body cells
            if water_reaches:
                water_cells = await loop.run_in_executor(
                    None,
                    lambda: generate_cells(
                        reach_segments=water_reaches,
                        cell_size=water_cell_size,
                        cell_shape=cell_shape,
                    ),
                )
                if water_cells is not None and len(water_cells) > 0:
                    all_cells.append(water_cells)
            # Generate sea area cells
            if sea_reaches:
                _workflow_msg.set("Generating sea area cells (this may take a moment)...")
                sea_cells = await loop.run_in_executor(
                    None,
                    lambda: generate_cells(
                        reach_segments=sea_reaches,
                        cell_size=sea_cell_size,
                        cell_shape=cell_shape,
                    ),
                )
                if sea_cells is not None and len(sea_cells) > 0:
                    all_cells.append(sea_cells)

            if all_cells:
                import pandas as pd
                cells = gpd.GeoDataFrame(pd.concat(all_cells, ignore_index=True))
                # Re-number cell IDs
                cells["cell_id"] = [f"C{i+1:04d}" for i in range(len(cells))]
            else:
                cells = None
        except Exception as exc:
            _workflow_msg.set(f"Cell generation failed: {exc}")
            logger.exception("generate_cells error")
            return

        if cells is not None and len(cells) > 0:
            _cells_gdf.set(cells)
            _workflow_msg.set(f"Generated {len(cells)} habitat cells.")
            await _refresh_map()
        else:
            _workflow_msg.set("Cell generation returned no cells.")

    # -----------------------------------------------------------------
    # Help modal
    # -----------------------------------------------------------------

    @reactive.effect
    @reactive.event(input.help_btn)
    def _on_help():
        m = ui.modal(
            ui.h4("Creating a Model in SalmoPy", style="margin-top:0;"),
            ui.markdown("""
**SalmoPy** is an individual-based salmon population model. This panel
lets you create a new model domain from OpenStreetMap river network data:
select river reaches, generate habitat cells, and export a ready-to-run
simulation configuration.

---

### Key Concepts

**Strahler stream order** classifies rivers by size. Order 1 is a
headwater stream with no tributaries. When two order-1 streams merge
they form an order-2 stream; two order-2 streams form order-3, and so
on. The **Strahler** slider filters the map display:

| Order | Typical width | Example |
|-------|--------------|---------|
| 1-2 | < 2 m | Small headwater brooks |
| 3-4 | 2-10 m | Medium streams |
| 5-6 | 10-50 m | Large rivers (e.g. Minija) |
| 7-9 | > 50 m | Major rivers (e.g. Nemunas) |

Set the slider higher to hide small tributaries and focus on the main
channels relevant for salmon habitat.

**River cell size** (5-100 m) controls the spatial resolution of
habitat cells along river reaches. Each cell is a hexagonal or
rectangular polygon that represents a patch of river habitat with its
own depth, velocity, and substrate properties. Smaller cells give more
spatial detail but increase computation time:

| Cell size | Cells per km | Best for |
|-----------|-------------|----------|
| 10-20 m | 50-100 | Detailed reach studies |
| 20-50 m | 20-50 | Standard models |
| 50-100 m | 10-20 | Large-scale screening |

**Water cell size** (50-1000 m) applies to water body reaches
(lagoons, lakes, estuaries). These features are much larger than river
channels and need bigger cells to keep the model tractable. The
Curonian Lagoon, for example, is ~1,600 km² — at 200 m cell size it
produces ~40,000 cells; at 500 m about 6,400 cells.

**Sea cell size** (500-10,000 m) applies to open sea/ocean reaches
selected from IHO sea area boundaries. Marine areas are vast and
require very large cells. For salmon marine migration modelling,
typical cell sizes are 2-5 km (2,000-5,000 m).

---

### Step 1 — Load Data

1. **Pan and zoom** the map to your area of interest.
2. Select your **Region** from the dropdown (country for Geofabrik PBF data).
3. Click **🌊 Rivers** to extract river network from local OSM data.
4. Click **💧 Water** to extract water body polygons (lagoons, lakes, coastal areas).
5. Click **🌊 Sea** to download IHO sea area boundaries (Baltic Sea, Gulf of Bothnia, etc.).
5. Adjust the **Strahler** slider to filter small streams in real-time.

> River and water body data is extracted from OpenStreetMap via local
> .osm.pbf files downloaded from Geofabrik. Select your region from
> the dropdown — the data file is downloaded once (~200 MB) and
> clipped to your map view on each fetch (~23s). Sea areas come from
> the Marine Regions database (marineregions.org).

### Step 2 — Select Reaches

1. Click **✏️ Select** to enter selection mode (pulsing red SELECTING badge appears).
2. **Click on a river line** to add that segment to the current reach.
   Click more segments to extend the reach.
3. **Click inside a water body** (lagoon, lake) to add it as a water reach.
4. **Click inside a sea area** (after loading sea data) to add it as a marine reach.
5. Click **✏️ Select** again to finish the current reach.
5. Click **✏️ Select** once more to start a **new reach** (auto-named reach_2, reach_3, ...).
6. Each reach is drawn in a distinct colour (orange, green, magenta, ...).
7. Use **🗑 Clear** to reset all selections and start over.

> **What is a reach?** A reach is a hydrologically connected section of
> the river network. Salmon move between reaches through junctions.
> Typical reaches: main stem, tributary, lagoon passage, estuary.

### Step 3 — Generate Habitat Cells

1. Set the **River cell** and **Water cell** sizes using the sliders.
2. Choose **Hexagonal** (recommended) or **Rectangular** cell shape.
3. Click **⬡ Cells** to generate the habitat grid.
4. Green cells appear on the map, covering each reach.

> Hexagonal cells tessellate tightly and have uniform neighbour
> distances, making them ideal for ecological models. Rectangular
> cells are simpler but create directional artefacts.

### Step 4 — Export

Click **📦 Export** to download a ZIP containing:

| File | Contents |
|------|----------|
| `Shapefile/Model.shp` | Cell polygons with attributes (area, reach, hiding places, velocity shelter, spawning fraction) |
| `model_config.yaml` | Full inSTREAM simulation configuration |
| `{Reach}-TimeSeriesInputs.csv` | Template daily data (temperature, flow, turbidity) — 365 rows |
| `{Reach}-Depths.csv` | Template depth table (10 flows x N cells) |
| `{Reach}-Vels.csv` | Template velocity table (10 flows x N cells) |

> Template CSVs contain **placeholder values**. Replace them with real
> hydraulic data from HEC-RAS, River2D, or field measurements for
> accurate simulations.

### Step 5 — Run Simulation

1. Switch to the **Setup** tab.
2. Select the exported config from the dropdown and click **Load Config**.
3. Set start/end dates and click **Run Simulation**.

---

### Cell Attributes

Each habitat cell carries these properties (editable in the shapefile):

| Attribute | Description | Default |
|-----------|-------------|---------|
| `AREA` | Cell area in m² | Computed from geometry |
| `M_TO_ESC` | Distance to nearest reach endpoint (cm) | Computed |
| `NUM_HIDING` | Number of hiding places | 5 (edge) / 2 (interior) |
| `FRACVSHL` | Fraction of velocity shelter | 0.4 (edge) / 0.15 (interior) |
| `FRACSPWN` | Fraction suitable for spawning | 0.0 (set per reach) |
"""),
            title=None,
            easy_close=True,
            size="xl",
        )
        ui.modal_show(m)

    # -----------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------

    @reactive.effect
    @reactive.event(input.export_btn)
    async def _on_export():
        cells = _cells_gdf()
        reaches = _reaches_dict()
        if cells is None or len(cells) == 0:
            _workflow_msg.set("Nothing to export. Generate cells first.")
            return

        if export_zip is None:
            _workflow_msg.set(
                "Export module not available (create_model_export not implemented)."
            )
            return

        _workflow_msg.set("Exporting model files...")

        import asyncio
        import tempfile
        loop = asyncio.get_running_loop()
        output_dir = Path(tempfile.mkdtemp(prefix="salmopy_export_"))
        try:
            zip_path = await loop.run_in_executor(
                None,
                lambda: export_zip(
                    cells_gdf=cells,
                    reaches=reaches,
                    model_name="model",
                    species_params={},
                    output_dir=output_dir,
                ),
            )
            _workflow_msg.set(f"Exported to: {zip_path}")
        except Exception as exc:
            _workflow_msg.set(f"Export failed: {exc}")
            logger.exception("export_zip error")

    # -----------------------------------------------------------------
    # Outputs
    # -----------------------------------------------------------------

    @render.ui
    def toolbar_badges():
        """Live badges in the toolbar: selecting indicator + counters."""
        reaches = _reaches_dict()
        cells = _cells_gdf()
        sel_mode = _selection_mode()
        badges = []
        if sel_mode:
            mode_labels = {"river": "RIVER", "lagoon": "LAGOON", "sea": "SEA"}
            mode_css = {"river": "cm-badge-select-river", "lagoon": "cm-badge-select-lagoon", "sea": "cm-badge-select-sea"}
            label = mode_labels.get(sel_mode, "SELECT")
            css = mode_css.get(sel_mode, "cm-badge-select-river")
            badges.append(ui.tags.span(f"✏️ {label}", class_=f"cm-badge cm-badge-select {css}"))
        if reaches:
            total_segs = sum(
                len(r["segments"]) if isinstance(r, dict) else len(r)
                for r in reaches.values()
            )
            badges.append(ui.tags.span(
                f"{len(reaches)} reaches · {total_segs} seg",
                class_="cm-badge cm-badge-reach",
            ))
        if cells is not None and len(cells) > 0:
            badges.append(ui.tags.span(
                f"{len(cells)} cells", class_="cm-badge cm-badge-cells",
            ))
        if not badges:
            return ui.div()
        return ui.div(*badges, style="display:inline-flex; align-items:center; gap:0.2rem;")

    @render.ui
    def fetch_status():
        msg = _fetch_msg()
        if not msg:
            return ui.div()
        return ui.p(msg, style="color:#555; font-size:0.85rem; margin-top:0.5rem;")

    @render.ui
    def data_summary():
        rivers = _rivers_gdf()
        water = _water_gdf()
        if rivers is None and water is None:
            return ui.div()

        rows = []
        if rivers is not None:
            n_rivers = len(rivers)
            # Also show filtered count
            filtered = _filtered_rivers_gdf()
            n_filtered = len(filtered) if filtered is not None else n_rivers
            strahler_col = None
            for c in rivers.columns:
                if "strahler" in c.lower():
                    strahler_col = c
                    break
            if strahler_col:
                strahler_range = f"{int(rivers[strahler_col].min())}-{int(rivers[strahler_col].max())}"
            else:
                strahler_range = "---"
            rows.append(ui.tags.tr(
                ui.tags.td("River segments"),
                ui.tags.td(f"{n_filtered} / {n_rivers}"),
                ui.tags.td(f"Strahler {strahler_range}"),
            ))

        if water is not None:
            rows.append(ui.tags.tr(
                ui.tags.td("Water bodies"),
                ui.tags.td(str(len(water))),
                ui.tags.td("---"),
            ))

        return ui.div(
            ui.h6("OSM River Data"),
            ui.tags.table(
                {"class": "table table-sm table-striped", "style": "font-size:0.85rem;"},
                ui.tags.thead(ui.tags.tr(
                    ui.tags.th("Type"),
                    ui.tags.th("Count"),
                    ui.tags.th("Details"),
                )),
                ui.tags.tbody(*rows),
            ),
            style="margin-top:0.5rem;",
        )

    @render.ui
    def workflow_status():
        msg = _workflow_msg()
        reaches = _reaches_dict()
        cells = _cells_gdf()
        sel_mode = _selection_mode()

        parts = []
        if msg:
            parts.append(ui.p(msg, style="color:#555; font-size:0.85rem;"))

        # Summary badges
        badges = []
        if reaches:
            total_segs = sum(
                len(v["segments"]) if isinstance(v, dict) else len(v)
                for v in reaches.values()
            )
            badges.append(
                ui.tags.span(
                    f"{len(reaches)} reaches ({total_segs} segments)",
                    class_="badge bg-warning text-dark",
                    style="margin-right:0.3rem;",
                )
            )
        if cells is not None:
            badges.append(
                ui.tags.span(
                    f"{len(cells)} cells",
                    class_="badge bg-success",
                    style="margin-right:0.3rem;",
                )
            )
        if sel_mode:
            mode_labels = {"river": "🏞️ RIVER", "lagoon": "💧 LAGOON", "sea": "🌊 SEA"}
            badges.append(
                ui.tags.span(
                    mode_labels.get(sel_mode, "✏️ SELECTING"),
                    class_="badge bg-danger",
                    style="margin-right:0.3rem;",
                )
            )

        # Button highlighting is handled by _update_sel_buttons reactive effect

        if badges:
            parts.append(ui.div(*badges, style="margin-top:0.25rem;"))

        if not parts:
            return ui.div()
        return ui.div(*parts, style="margin-top:0.5rem;")
