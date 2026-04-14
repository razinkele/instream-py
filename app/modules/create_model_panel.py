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
WATER_LAYERS = [0, 1, 2]  # Coastal + Transit (lagoon!) + InlandWater

# Reach colour palette (cycle for multiple reaches)
REACH_COLORS = [
    [255, 87, 34, 220],   # deep orange
    [76, 175, 80, 220],   # green
    [156, 39, 176, 220],  # purple
    [255, 193, 7, 220],   # amber
    [0, 188, 212, 220],   # cyan
    [244, 67, 54, 220],   # red
    [63, 81, 181, 220],   # indigo
    [121, 85, 72, 220],   # brown
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
            legend_control(position="bottom-left", show_default=True, show_checkbox=True),
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
    .cm-toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:0.4rem; padding:0.5rem 0.6rem;
                  background:#1e293b; border-radius:6px; margin-bottom:0.4rem; }
    .cm-toolbar .btn-cm { background:rgba(43,184,157,.15); color:#2bb89d; border:1px solid rgba(43,184,157,.4);
                          border-radius:4px; padding:0.25rem 0.6rem; font-size:0.78rem; font-weight:600;
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
    """)

    return ui.card(
        ui.card_header("Create Model"),
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
            ui.tags.div(class_="cm-sep"),
            ui.tags.span("Strahler≥", class_="cm-label"),
            ui.div(
                ui.input_slider("strahler_min", None, min=1, max=9, value=3, step=1, width="90px"),
                style="display:inline-block; vertical-align:middle; width:90px;",
            ),
            ui.tags.div(class_="cm-sep"),
            ui.tags.span("Cell:", class_="cm-label"),
            ui.div(
                ui.input_slider("cell_size", None, min=5, max=100, value=20, step=5, width="80px"),
                style="display:inline-block; vertical-align:middle; width:80px;",
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
            ui.input_action_button("generate_cells_btn", "⬡ Cells",
                                   class_="btn btn-cm",
                                   title="Generate habitat cells from selected reaches"),
            ui.input_action_button("export_btn", "📦 Export",
                                   class_="btn btn-cm",
                                   title="Export shapefile + YAML config as ZIP"),
        ),
        # -- Map (shown immediately, before any fetch) ---
        _widget.ui(height="550px"),
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
            get_line_color=[30, 100, 200, 200],
            get_line_width=2,
            line_width_min_pixels=1,
            line_width_max_pixels=6,
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
            get_fill_color=[135, 206, 235, 120],
            get_line_color=[70, 130, 180, 150],
            get_line_width=1,
            pickable=True,
            stroked=True,
            filled=True,
        )

    def _build_reach_layers():
        """Build one GeoJSON layer per reach with distinct colours."""
        layers = []
        reaches = _reaches_dict()
        for idx, (name, segments) in enumerate(reaches.items()):
            if not segments:
                continue
            color = REACH_COLORS[idx % len(REACH_COLORS)]
            features = []
            for seg in segments:
                features.append({
                    "type": "Feature",
                    "geometry": seg.__geo_interface__,
                    "properties": {"reach": name},
                })
            geoj = {"type": "FeatureCollection", "features": features}
            layers.append(geojson_layer(
                id=f"reach-{name}",
                data=geoj,
                get_line_color=color,
                get_line_width=5,
                line_width_min_pixels=3,
                line_width_max_pixels=10,
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
            get_fill_color=[100, 200, 100, 80],
            get_line_color=[50, 150, 50, 180],
            get_line_width=1,
            pickable=True,
            stroked=True,
            filled=True,
        )

    async def _refresh_map():
        """Rebuild all map layers from current state and push to widget."""
        layers = []
        # Water bodies (bottom)
        water = _water_gdf()
        if water is not None and len(water) > 0:
            logger.info("Water layer: %d features", len(water))
            layers.append(_build_water_layer(water))
        else:
            logger.info("No water features to display")
        # Filtered rivers
        fgdf = _filtered_rivers_gdf()
        if fgdf is not None and len(fgdf) > 0:
            layers.append(_build_river_layer(fgdf))
        # Cells
        cells_lyr = _build_cells_layer()
        if cells_lyr is not None:
            layers.append(cells_lyr)
        # Reach overlays (top)
        layers.extend(_build_reach_layers())
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
        await _refresh_map()
        n_final = len(gdf)
        water_msg = f" + {len(water_gdf)} water bodies" if water_gdf is not None else ""
        _fetch_msg.set(f"Loaded {n_final} river segments (Strahler >= {strahler_min}){water_msg}.")

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
    # Strahler filter — re-render map when slider changes
    # -----------------------------------------------------------------

    @reactive.effect
    @reactive.event(input.strahler_min)
    async def _on_strahler_change():
        if _rivers_gdf() is not None:
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

    @reactive.effect
    async def _on_map_click():
        """Handle click on map — find nearest river segment to click point."""
        try:
            data = getattr(input, _widget.click_input_id)()
        except Exception:
            return
        if data is None or not _selection_mode():
            return

        # First try: extract geometry from click object (full GeoJSON feature)
        obj = data.get("object")
        geom = None
        if obj is not None:
            geom_dict = obj.get("geometry")
            if geom_dict is not None:
                try:
                    geom = shape(geom_dict)
                except Exception:
                    pass

        # Fallback: use click coordinate to find nearest river segment
        if geom is None:
            coord = data.get("coordinate")
            if coord is None:
                return
            rivers = _filtered_rivers_gdf()
            if rivers is None or len(rivers) == 0:
                return
            from shapely.geometry import Point as _Pt
            click_pt = _Pt(coord[0], coord[1])
            dists = rivers.geometry.distance(click_pt)
            nearest_idx = dists.idxmin()
            geom = rivers.geometry.iloc[nearest_idx]
            # Only accept if within ~0.002 degrees (~200m)
            if dists.iloc[nearest_idx] > 0.002:
                return

        if geom is None:
            return

        # Convert to LineString if needed
        if geom.geom_type == "MultiLineString":
            geom = max(geom.geoms, key=lambda g: g.length)
        if geom.geom_type != "LineString":
            _workflow_msg.set(f"Clicked geometry is {geom.geom_type}, expected LineString.")
            return

        reach_name = _current_reach_name()
        if not reach_name:
            return

        # Use assign_segment_to_reach if available, otherwise do it inline
        reaches = dict(_reaches_dict())  # shallow copy
        if assign_segment_to_reach is not None:
            reaches = assign_segment_to_reach(reaches, reach_name, geom)
        else:
            if reach_name not in reaches:
                reaches[reach_name] = []
            reaches[reach_name].append(geom)

        _reaches_dict.set(reaches)

        n_segs = len(reaches.get(reach_name, []))
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

        cell_size = input.cell_size()
        cell_shape = input.cell_shape()

        # Collect all reach geometries
        all_lines = []
        for segs in reaches.values():
            all_lines.extend(segs)

        if not all_lines:
            _workflow_msg.set("Reaches are empty — no segments to generate cells from.")
            return

        import asyncio
        loop = asyncio.get_running_loop()
        try:
            cells = await loop.run_in_executor(
                None,
                lambda: generate_cells(
                    lines=all_lines,
                    cell_size=cell_size,
                    cell_shape=cell_shape,
                ),
            )
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
        loop = asyncio.get_running_loop()
        try:
            zip_path = await loop.run_in_executor(
                None,
                lambda: export_zip(
                    cells_gdf=cells,
                    reaches_dict=reaches,
                ),
            )
            _workflow_msg.set(f"Exported to: {zip_path}")
            await session.send_custom_message(
                "notification",
                {"message": f"Model exported to {zip_path}", "type": "message"},
            )
        except Exception as exc:
            _workflow_msg.set(f"Export failed: {exc}")
            logger.exception("export_zip error")

    # -----------------------------------------------------------------
    # Outputs
    # -----------------------------------------------------------------

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
            total_segs = sum(len(v) for v in reaches.values())
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
