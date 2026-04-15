"""Create Model panel — download EU-Hydro river network and build model grid.

Workflow:
1. Pan/zoom the map to the area of interest
2. Click "Fetch Rivers" to download EU-Hydro river network in the current view
3. Filter by Strahler order, then click "Select Reaches" and click segments
4. Generate hexagonal/rectangular habitat cells from selected reaches
5. Export as shapefile + YAML config
"""

import json
import logging
import math

import geopandas as gpd
import numpy as np
import requests
from io import BytesIO
from pathlib import Path
from shapely.geometry import shape, box, Polygon, MultiPolygon, LineString
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

logger = logging.getLogger(__name__)

BASEMAP_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

# EU-Hydro ArcGIS REST endpoints
EUHYDRO_BASE = "https://image.discomap.eea.europa.eu/arcgis/rest/services/EUHydro/EUHydro_RiverNetworkDatabase/MapServer"
# Polygon layers for water overlay + clipping:
#   0 = Coastal_polygon (Baltic Sea, DFDD=SA010)
#   1 = Transit_polygon  (Curonian Lagoon, DFDD=BH999)
#   2 = InlandWater       (small lakes/ponds, DFDD=BH000)
# River lines: layer 4 is GROUP LAYER (not queryable!)
# Actual feature layers: 5=Strahler1, 6=Strahler2, ..., 13=Strahler9
RIVER_STRAHLER_LAYERS = {1: 5, 2: 6, 3: 7, 4: 8, 5: 9, 6: 10, 7: 11, 8: 12, 9: 13}
RIVER_POLYGON_LAYER = 19  # River_Net_polygon — wide river polygons
WATER_LAYERS = [0, 1, 2]  # Coastal + Transit (lagoon!) + InlandWater

# Marine Regions WFS (IHO sea areas — marineregions.org, no auth)
MARINE_REGIONS_WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"

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


def _query_euhydro(layer_id, bbox_wgs84, max_features=2000):
    """Query EU-Hydro ArcGIS REST API for features in a bounding box.

    Parameters
    ----------
    layer_id : int
        ArcGIS layer ID.
    bbox_wgs84 : tuple
        (west, south, east, north) in WGS84.
    max_features : int
        Maximum features to return.

    Returns
    -------
    dict or None
        GeoJSON FeatureCollection, or None on error.
    """
    url = f"{EUHYDRO_BASE}/{layer_id}/query"
    west, south, east, north = bbox_wgs84
    params = {
        "where": "1=1",
        "geometry": f"{west},{south},{east},{north}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "f": "geojson",
        "resultRecordCount": max_features,
    }
    try:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("EU-Hydro query failed: %s", e)
        return None


def _query_marine_regions(bbox_wgs84):
    """Query Marine Regions WFS for IHO sea area polygons in a bounding box.

    Returns GeoJSON FeatureCollection or None on error.
    """
    west, south, east, north = bbox_wgs84
    # GeoServer uses lon,lat axis order despite WFS 2.0.0 spec
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
        resp = requests.get(MARINE_REGIONS_WFS, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("Marine Regions query failed: %s", e)
        return None


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
            "html": "<b>{nameText}</b><br/>Strahler: {STRAHLER}<br/>Type: {DFDD}",
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
    .cm-badge-select { background:#ef4444; color:#fff; animation: pulse-select 1.5s infinite; }
    .cm-badge-reach { background:rgba(255,160,0,.85); color:#fff; }
    .cm-badge-cells { background:rgba(34,197,94,.85); color:#fff; }
    @keyframes pulse-select { 0%,100%{opacity:1;} 50%{opacity:.6;} }
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
            ui.input_action_button("fetch_rivers", "🌊 Rivers",
                                   class_="btn btn-cm",
                                   title="Fetch EU-Hydro river network for current map view"),
            ui.input_action_button("fetch_water", "💧 Water",
                                   class_="btn btn-cm",
                                   title="Fetch EU-Hydro water bodies (lakes, lagoons)"),
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
            ui.input_action_button("select_reaches_btn", "✏️ Select",
                                   class_="btn btn-cm",
                                   title="Toggle: click river segments to assign to reaches"),
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
    _river_polygons_gdf = reactive.value(None)  # EU-Hydro layer 19 (wide river polygons)
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
    _selection_mode = reactive.value(False)   # True when click-to-select active
    _current_reach_name = reactive.value("")  # active reach being built
    _workflow_msg = reactive.value("")

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
        """Build a deck.gl GeoJSON layer from a rivers GeoDataFrame."""
        geoj = json.loads(gdf.to_json())
        return geojson_layer(
            id="euhydro-rivers",
            data=geoj,
            getLineColor=[30, 100, 200, 200],
            getLineWidth=3,
            lineWidthMinPixels=2,
            lineWidthMaxPixels=8,
            pickable=True,
            stroked=True,
            filled=False,
        )

    def _build_water_layer(gdf):
        """Build a deck.gl GeoJSON layer from a water bodies GeoDataFrame."""
        # Simplify large polygons to reduce WebGL payload
        simplified = gdf.copy()
        simplified["geometry"] = simplified.geometry.simplify(0.001, preserve_topology=True)
        simplified = simplified[~simplified.geometry.is_empty]
        logger.info("Water layer: %d features (simplified from %d)", len(simplified), len(gdf))
        geoj = json.loads(simplified.to_json())
        return geojson_layer(
            id="euhydro-water",
            data=geoj,
            getFillColor=[135, 206, 235, 120],
            getLineColor=[70, 130, 180, 150],
            getLineWidth=1,
            pickable=True,
            stroked=True,
            filled=True,
        )

    def _build_sea_layer(gdf):
        """Build a deck.gl GeoJSON layer from sea area polygons."""
        geoj = json.loads(gdf.to_json())
        return geojson_layer(
            id="marine-sea-areas",
            data=geoj,
            getFillColor=[50, 80, 140, 40],
            getLineColor=[30, 60, 120, 150],
            getLineWidth=2,
            lineWidthMinPixels=1,
            pickable=True,
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
        # River polygons (wide rivers from EU-Hydro layer 19)
        rpoly = _river_polygons_gdf()
        if rpoly is not None and len(rpoly) > 0:
            layers.append(_build_water_layer(rpoly))  # reuse water style
        # Filtered rivers
        fgdf = _filtered_rivers_gdf()
        if fgdf is not None and len(fgdf) > 0:
            layers.append(_build_river_layer(fgdf))
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

    @reactive.effect
    @reactive.event(input.fetch_rivers)
    async def _on_fetch_rivers():
        _fetch_msg.set("Fetching river network from EU-Hydro...")
        bbox = _get_view_bbox()
        strahler_min = input.strahler_min()

        import asyncio
        loop = asyncio.get_running_loop()

        # Query each Strahler sub-layer >= threshold, merge results
        all_features = []
        for strahler_order, layer_id in RIVER_STRAHLER_LAYERS.items():
            if strahler_order < strahler_min:
                continue
            _fetch_msg.set(f"Fetching Strahler {strahler_order} rivers...")
            geojson = await loop.run_in_executor(
                None, lambda lid=layer_id: _query_euhydro(lid, bbox)
            )
            if geojson and "features" in geojson:
                # Add STRAHLER attribute to each feature
                for feat in geojson["features"]:
                    if "properties" not in feat:
                        feat["properties"] = {}
                    feat["properties"]["STRAHLER"] = strahler_order
                all_features.extend(geojson["features"])

        n = len(all_features)
        if n == 0:
            _fetch_msg.set("No river features found. Try zooming in or lowering the Strahler filter.")
            return

        combined = {"type": "FeatureCollection", "features": all_features}
        gdf = gpd.GeoDataFrame.from_features(combined["features"], crs="EPSG:4326")

        # Auto-fetch ALL water polygon layers for context + clipping
        # Layer 0=Coastal (Baltic Sea), 1=Transit (Curonian Lagoon!), 2=InlandWater
        _fetch_msg.set(f"Got {n} rivers. Fetching water bodies + lagoon + coast...")
        all_water_features = []
        layer_names = {0: "Coastal", 1: "Lagoon/Transit", 2: "InlandWater"}

        for water_layer_id in WATER_LAYERS:
            lname = layer_names.get(water_layer_id, str(water_layer_id))
            _fetch_msg.set(f"Fetching {lname}...")
            wj = await loop.run_in_executor(
                None, lambda lid=water_layer_id: _query_euhydro(lid, bbox)
            )
            if wj and "features" in wj and wj["features"]:
                all_water_features.extend(wj["features"])

        water_gdf = None
        if all_water_features:
            water_gdf = gpd.GeoDataFrame.from_features(
                all_water_features, crs="EPSG:4326"
            )
            _water_gdf.set(water_gdf)

        # Clip rivers: remove segments that are mostly inside water bodies/coastal
        if water_gdf is not None and len(water_gdf) > 0:
            _fetch_msg.set("Clipping rivers to exclude lagoon/coastal segments...")
            water_union = water_gdf.geometry.unary_union
            keep_mask = []
            for _, row in gdf.iterrows():
                line = row.geometry
                if line is None or line.is_empty:
                    keep_mask.append(False)
                    continue
                try:
                    inside = line.intersection(water_union)
                    frac_inside = inside.length / line.length if line.length > 0 else 0
                    keep_mask.append(frac_inside < 0.5)  # keep if <50% inside water body
                except Exception:
                    keep_mask.append(True)
            n_before = len(gdf)
            gdf = gdf[keep_mask].reset_index(drop=True)
            n_clipped = n_before - len(gdf)
            _fetch_msg.set(f"Clipped {n_clipped} lagoon/lake segments.")

        _rivers_gdf.set(gdf)

        # Fetch river polygons (EU-Hydro layer 19 — wide river polygons)
        _fetch_msg.set("Fetching river polygons (wide rivers)...")
        rpoly_geojson = await loop.run_in_executor(
            None, lambda: _query_euhydro(RIVER_POLYGON_LAYER, bbox)
        )
        rpoly_gdf = None
        if rpoly_geojson and "features" in rpoly_geojson and rpoly_geojson["features"]:
            rpoly_gdf = gpd.GeoDataFrame.from_features(
                rpoly_geojson["features"], crs="EPSG:4326"
            )
            _river_polygons_gdf.set(rpoly_gdf)

        await _refresh_map()
        n_final = len(gdf)
        water_msg = f" + {len(water_gdf)} water bodies" if water_gdf is not None else ""
        rpoly_msg = f" + {len(rpoly_gdf)} river polygons" if rpoly_gdf is not None else ""
        _fetch_msg.set(f"Loaded {n_final} river segments (Strahler >= {strahler_min}){water_msg}{rpoly_msg}.")

    @reactive.effect
    @reactive.event(input.fetch_water)
    async def _on_fetch_water():
        _fetch_msg.set("Fetching water bodies (inland + lagoon + coastal)...")
        bbox = _get_view_bbox()

        import asyncio
        loop = asyncio.get_running_loop()

        all_feats = []
        layer_names = {0: "Coastal", 1: "Lagoon/Transit", 2: "InlandWater"}
        for lid in WATER_LAYERS:
            lname = layer_names.get(lid, str(lid))
            _fetch_msg.set(f"Fetching {lname}...")
            wj = await loop.run_in_executor(
                None, lambda l=lid: _query_euhydro(l, bbox)
            )
            if wj and "features" in wj and wj["features"]:
                all_feats.extend(wj["features"])

        if not all_feats:
            _fetch_msg.set("No water bodies found in this area.")
            return

        gdf = gpd.GeoDataFrame.from_features(all_feats, crs="EPSG:4326")
        _water_gdf.set(gdf)
        await _refresh_map()
        _fetch_msg.set(f"Loaded {len(gdf)} water bodies (coastal + lagoon + inland).")

    # -----------------------------------------------------------------
    # Fetch sea areas (Marine Regions IHO)
    # -----------------------------------------------------------------

    @reactive.effect
    @reactive.event(input.fetch_sea)
    async def _on_fetch_sea():
        _fetch_msg.set("Fetching IHO sea areas from Marine Regions...")
        bbox = _get_view_bbox()

        import asyncio
        loop = asyncio.get_running_loop()
        geoj = await loop.run_in_executor(None, _query_marine_regions, bbox)

        if geoj is None or not geoj.get("features"):
            _fetch_msg.set("No sea areas found — try zooming out to see the coast.")
            return

        gdf = gpd.GeoDataFrame.from_features(geoj["features"], crs="EPSG:4326")

        # Post-filter: WFS bbox returns global polygons that merely touch
        # the bbox. Keep only features whose geometry actually intersects
        # the bbox interior (not just a shared edge).
        from shapely.geometry import box as _box
        view_box = _box(*bbox)
        gdf = gdf[gdf.geometry.intersects(view_box)].copy()
        # Prefer features that actually cover the bbox center
        if len(gdf) > 1:
            center = view_box.centroid
            covers = gdf[gdf.geometry.contains(center)]
            if len(covers) > 0:
                gdf = covers.copy()

        if len(gdf) == 0:
            _fetch_msg.set("No sea areas found — try zooming out to see the coast.")
            return

        # Simplify large sea polygons for display performance
        gdf["geometry"] = gdf.geometry.simplify(0.01, preserve_topology=True)
        _sea_gdf.set(gdf)
        names = ", ".join(gdf["name"].dropna().unique()[:5]) if "name" in gdf.columns else ""
        _fetch_msg.set(f"Loaded {len(gdf)} sea areas. {names}")
        await _refresh_map()

    # -----------------------------------------------------------------
    # Strahler filter — re-render map when slider changes
    # -----------------------------------------------------------------

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
        _selection_mode.set(False)
        _current_reach_name.set("")
        _workflow_msg.set("All reaches and cells cleared.")
        await _refresh_map()

    # -----------------------------------------------------------------
    # Select Reaches toggle
    # -----------------------------------------------------------------

    @reactive.effect
    @reactive.event(input.select_reaches_btn)
    def _on_select_reaches():
        active = _selection_mode()
        if active:
            # Deactivate
            _selection_mode.set(False)
            _current_reach_name.set("")
            _workflow_msg.set("Selection mode OFF.")
        else:
            # Activate — auto-name next reach
            reaches = _reaches_dict()
            idx = len(reaches) + 1
            name = f"reach_{idx}"
            _current_reach_name.set(name)
            _selection_mode.set(True)
            _workflow_msg.set(
                f"Selection mode ON. Click river segments to add them to '{name}'. "
                "Click 'Select Reaches' again to finish."
            )

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
        sel = _selection_mode()

        if not sel:
            _workflow_msg.set(f"Click: ({lon:.4f}, {lat:.4f}) — selection mode OFF")
            return

        if lon is None or lat is None:
            return

        from shapely.geometry import Point as _Pt
        click_pt = _Pt(lon, lat)

        # --- Check water bodies first (click inside polygon) ---
        water = _water_gdf()
        if water is not None and len(water) > 0:
            hits = water[water.geometry.contains(click_pt)]
            if len(hits) > 0:
                geom = hits.geometry.iloc[0]
                # Simplify large polygons for storage
                if geom.geom_type == "MultiPolygon":
                    geom = max(geom.geoms, key=lambda g: g.area)
                reach_name = _current_reach_name()
                if not reach_name:
                    return
                reaches = dict(_reaches_dict())
                if reach_name not in reaches:
                    reaches[reach_name] = {
                        "segments": [], "properties": [],
                        "color": REACH_COLORS[len(reaches) % len(REACH_COLORS)],
                        "type": "water",
                    }
                rd = reaches[reach_name]
                # Avoid duplicate polygons
                already = any(g.equals(geom) for g in rd["segments"])
                if not already:
                    rd["segments"].append(geom)
                    rd["properties"].append({})
                reaches[reach_name] = rd
                _reaches_dict.set(reaches)
                n = len(rd["segments"])
                name_attr = hits.iloc[0].get("nameText", "") if "nameText" in hits.columns else ""
                label = f" ({name_attr})" if name_attr else ""
                _workflow_msg.set(
                    f"Added water body{label} to '{reach_name}' ({n} features)."
                )
                await _refresh_map()
                return

        # --- Check river polygons (click inside wide-river polygon) ---
        rpoly = _river_polygons_gdf()
        if rpoly is not None and len(rpoly) > 0:
            hits = rpoly[rpoly.geometry.contains(click_pt)]
            if len(hits) > 0:
                geom = hits.geometry.iloc[0]
                if geom.geom_type == "MultiPolygon":
                    geom = max(geom.geoms, key=lambda g: g.area)
                reach_name = _current_reach_name()
                if not reach_name:
                    return
                reaches = dict(_reaches_dict())
                if reach_name not in reaches:
                    reaches[reach_name] = {
                        "segments": [], "properties": [],
                        "color": REACH_COLORS[len(reaches) % len(REACH_COLORS)],
                        "type": "water",
                    }
                rd = reaches[reach_name]
                already = any(g.equals(geom) for g in rd["segments"])
                if not already:
                    rd["segments"].append(geom)
                    rd["properties"].append({})
                reaches[reach_name] = rd
                _reaches_dict.set(reaches)
                n = len(rd["segments"])
                name_attr = hits.iloc[0].get("nameText", "") if "nameText" in hits.columns else ""
                label = f" ({name_attr})" if name_attr else ""
                _workflow_msg.set(
                    f"Added river polygon{label} to '{reach_name}' ({n} features)."
                )
                await _refresh_map()
                return

        # --- Check sea areas (click inside or near IHO polygon) ---
        sea = _sea_gdf()
        if sea is not None and len(sea) > 0:
            # Try strict containment first, then proximity (~0.05° ≈ 5 km)
            hits = sea[sea.geometry.contains(click_pt)]
            if len(hits) == 0:
                dists = sea.geometry.distance(click_pt)
                nearest_idx = dists.idxmin()
                if dists.loc[nearest_idx] < 0.05:
                    hits = sea.iloc[[nearest_idx]]
            if len(hits) > 0:
                geom = hits.geometry.iloc[0]
                if geom.geom_type == "MultiPolygon":
                    geom = max(geom.geoms, key=lambda g: g.area)
                reach_name = _current_reach_name()
                if not reach_name:
                    return
                reaches = dict(_reaches_dict())
                if reach_name not in reaches:
                    reaches[reach_name] = {
                        "segments": [], "properties": [],
                        "color": REACH_COLORS[len(reaches) % len(REACH_COLORS)],
                        "type": "sea",
                    }
                rd = reaches[reach_name]
                already = any(g.equals(geom) for g in rd["segments"])
                if not already:
                    rd["segments"].append(geom)
                    rd["properties"].append({})
                reaches[reach_name] = rd
                _reaches_dict.set(reaches)
                n = len(rd["segments"])
                sea_name = hits.iloc[0].get("name", "") if "name" in hits.columns else ""
                label = f" ({sea_name})" if sea_name else ""
                _workflow_msg.set(
                    f"Added sea area{label} to '{reach_name}' ({n} features)."
                )
                await _refresh_map()
                return

        # --- Then check rivers (nearest line) ---
        rivers = _filtered_rivers_gdf()
        if rivers is None or len(rivers) == 0:
            _workflow_msg.set("No data loaded — fetch rivers/water first.")
            return

        dists = rivers.geometry.distance(click_pt)
        nearest_idx = dists.idxmin()
        min_dist = dists.iloc[nearest_idx]
        if min_dist > 0.02:
            _workflow_msg.set(
                f"Click ({lon:.4f}, {lat:.4f}) too far from any feature ({min_dist:.4f}°). "
                "Click closer to a river or inside a water body."
            )
            return

        geom = rivers.geometry.iloc[nearest_idx]
        if geom.geom_type == "MultiLineString":
            geom = max(geom.geoms, key=lambda g: g.length)
        if geom.geom_type != "LineString":
            _workflow_msg.set(f"Clicked geometry is {geom.geom_type}, expected LineString.")
            return

        # Check if a river polygon from layer 19 contains this line segment.
        # If so, use the polygon (fills the river width) instead of the line.
        use_polygon = False
        rpoly = _river_polygons_gdf()
        if rpoly is not None and len(rpoly) > 0:
            try:
                candidates = rpoly[rpoly.geometry.intersects(geom)]
                if len(candidates) > 0:
                    # Pick the polygon with the largest intersection
                    best_idx = candidates.geometry.intersection(geom).length.idxmax()
                    poly_geom = candidates.geometry.loc[best_idx]
                    if poly_geom.geom_type == "MultiPolygon":
                        poly_geom = max(poly_geom.geoms, key=lambda g: g.area)
                    geom = poly_geom
                    use_polygon = True
            except Exception:
                pass  # fall back to line geometry

        reach_name = _current_reach_name()
        if not reach_name:
            return

        reaches = dict(_reaches_dict())
        if use_polygon:
            # Add as water-type reach (polygon → grid fills the area)
            if reach_name not in reaches:
                reaches[reach_name] = {
                    "segments": [], "properties": [],
                    "color": REACH_COLORS[len(reaches) % len(REACH_COLORS)],
                    "type": "water",
                }
            rd = reaches[reach_name]
            already = any(g.equals(geom) for g in rd["segments"])
            if not already:
                rd["segments"].append(geom)
                rd["properties"].append({})
            reaches[reach_name] = rd
        elif assign_segment_to_reach is not None:
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
        poly_note = " (river polygon — grid will fill area)" if use_polygon else ""
        _workflow_msg.set(f"Added segment to '{reach_name}' ({n_segs} segments total).{poly_note}")
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
            if rtype == "sea":
                sea_reaches[name] = rd
            elif rtype == "water":
                water_reaches[name] = rd
            else:
                river_reaches[name] = rd

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
                cells = gpd.pd.concat(all_cells, ignore_index=True)
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
    # Configure (placeholder)
    # -----------------------------------------------------------------

    @reactive.effect
    @reactive.event(input.configure_btn)
    def _on_configure():
        reaches = _reaches_dict()
        cells = _cells_gdf()
        n_reaches = len(reaches)
        n_cells = len(cells) if cells is not None else 0
        _workflow_msg.set(
            f"Configure: {n_reaches} reaches, {n_cells} cells. "
            "(Configuration dialog not yet implemented.)"
        )

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
lets you create a new model domain from EU-Hydro river network data:
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
2. Click **🌊 Rivers** to download EU-Hydro river line segments.
3. Click **💧 Water** to download water body polygons (lagoons, lakes, coastal areas).
4. Click **🌊 Sea** to download IHO sea area boundaries (Baltic Sea, Gulf of Bothnia, etc.).
5. Adjust the **Strahler** slider to filter small streams in real-time.

> River and water body data comes from the EEA EU-Hydro River Network
> Database (Copernicus Land Monitoring Service). Sea areas come from
> the Marine Regions database (marineregions.org), using IHO
> (International Hydrographic Organization) sea area boundaries.

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
            badges.append(ui.tags.span("SELECTING", class_="cm-badge cm-badge-select"))
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
            ui.h6("EU-Hydro Data"),
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
            badges.append(
                ui.tags.span(
                    "✏️ SELECTING",
                    class_="badge bg-danger",
                    style="margin-right:0.3rem;",
                )
            )

        # Toggle active class on Select button via inline JS
        toggle_js = "active" if sel_mode else ""
        parts.append(ui.tags.script(
            f'document.querySelectorAll("[id$=select_reaches_btn]").forEach('
            f'function(b){{ b.className = b.className.replace(" active",""); '
            f'if("{toggle_js}") b.className += " active"; }});'
        ))

        if badges:
            parts.append(ui.div(*badges, style="margin-top:0.25rem;"))

        if not parts:
            return ui.div()
        return ui.div(*parts, style="margin-top:0.5rem;")
