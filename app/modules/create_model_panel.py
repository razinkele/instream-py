"""Create Model panel — download EU-Hydro river network and build model grid.

Workflow:
1. Pan/zoom the map to the area of interest
2. Click "Fetch Rivers" to download EU-Hydro river network in the current view
3. Select reaches and set properties
4. Generate hexagonal habitat cells from the river network
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
from shapely.geometry import shape, box, Polygon, MultiPolygon
from shapely.ops import unary_union
from shiny import module, reactive, render, ui

from shiny_deckgl import MapWidget, geojson_layer
from shiny_deckgl.controls import legend_control

logger = logging.getLogger(__name__)

BASEMAP_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

# EU-Hydro ArcGIS REST endpoints
EUHYDRO_BASE = "https://image.discomap.eea.europa.eu/arcgis/rest/services/EUHydro/EUHydro_RiverNetworkDatabase/MapServer"
# Layer IDs: 0=Coastal, 2=InlandWater, 4=River_Net_lines, 19=River_Net_polygon
RIVER_LINES_LAYER = 4
INLAND_WATER_LAYER = 2
COASTAL_LAYER = 0


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
            "html": "<b>{DFDD}</b><br/>Strahler: {STRAHLER}<br/>Name: {NAME}",
            "style": {
                "backgroundColor": "#fff",
                "color": "#333",
                "fontSize": "12px",
            },
        },
    )
    return ui.card(
        ui.card_header("Create Model"),
        ui.layout_columns(
            ui.div(
                ui.input_action_button("fetch_rivers", "Fetch Rivers",
                                       class_="btn btn-primary btn-sm"),
                ui.input_action_button("fetch_water", "Fetch Water Bodies",
                                       class_="btn btn-info btn-sm"),
                style="display:flex; gap:0.5rem; margin-bottom:0.5rem;",
            ),
            ui.div(
                ui.tags.small(
                    "Pan/zoom the map, then click Fetch to download EU-Hydro data for the visible area.",
                    style="color:#888;",
                ),
            ),
            col_widths=(8, 4),
        ),
        _widget.ui(height="550px"),
        ui.output_ui("fetch_status"),
        ui.output_ui("data_summary"),
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
    _rivers_gdf = reactive.value(None)
    _water_gdf = reactive.value(None)
    _fetch_msg = reactive.value("")

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

    @reactive.effect
    @reactive.event(input.fetch_rivers)
    async def _on_fetch_rivers():
        _fetch_msg.set("Fetching river network from EU-Hydro...")
        bbox = _get_view_bbox()

        import asyncio
        loop = asyncio.get_running_loop()
        geojson = await loop.run_in_executor(
            None, lambda: _query_euhydro(RIVER_LINES_LAYER, bbox)
        )

        if geojson is None or "features" not in geojson:
            _fetch_msg.set("Failed to fetch river data. Try a smaller area.")
            return

        n = len(geojson["features"])
        _fetch_msg.set(f"Got {n} river segments. Sending to map...")

        if n > 0:
            gdf = gpd.GeoDataFrame.from_features(geojson["features"], crs="EPSG:4326")
            _rivers_gdf.set(gdf)

            river_layer = geojson_layer(
                id="euhydro-rivers",
                data=geojson,
                get_line_color=[30, 100, 200, 200],
                get_line_width=2,
                line_width_min_pixels=1,
                line_width_max_pixels=6,
                pickable=True,
                stroked=True,
                filled=False,
            )
            await _widget.update(session, [river_layer])
            _fetch_msg.set(f"Loaded {n} river segments.")
        else:
            _fetch_msg.set("No river features found in this area.")

    @reactive.effect
    @reactive.event(input.fetch_water)
    async def _on_fetch_water():
        _fetch_msg.set("Fetching water bodies from EU-Hydro...")
        bbox = _get_view_bbox()

        import asyncio
        loop = asyncio.get_running_loop()
        geojson = await loop.run_in_executor(
            None, lambda: _query_euhydro(INLAND_WATER_LAYER, bbox)
        )

        if geojson is None or "features" not in geojson:
            _fetch_msg.set("Failed to fetch water body data.")
            return

        n = len(geojson["features"])
        if n > 0:
            gdf = gpd.GeoDataFrame.from_features(geojson["features"], crs="EPSG:4326")
            _water_gdf.set(gdf)

            water_layer = geojson_layer(
                id="euhydro-water",
                data=geojson,
                get_fill_color=[135, 206, 235, 120],
                get_line_color=[70, 130, 180, 150],
                get_line_width=1,
                pickable=True,
                stroked=True,
                filled=True,
            )

            # Also include rivers if loaded
            layers = [water_layer]
            rivers = _rivers_gdf()
            if rivers is not None:
                rj = rivers.__geo_interface__
                river_lyr = geojson_layer(
                    id="euhydro-rivers",
                    data=rj,
                    get_line_color=[30, 100, 200, 200],
                    get_line_width=2,
                    line_width_min_pixels=1,
                    pickable=True,
                    stroked=True,
                    filled=False,
                )
                layers.append(river_lyr)

            await _widget.update(session, layers)
            _fetch_msg.set(f"Loaded {n} water bodies.")
        else:
            _fetch_msg.set("No water bodies found in this area.")

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
            strahler_col = None
            for c in rivers.columns:
                if "strahler" in c.lower():
                    strahler_col = c
                    break
            if strahler_col:
                strahler_range = f"{int(rivers[strahler_col].min())}-{int(rivers[strahler_col].max())}"
            else:
                strahler_range = "—"
            rows.append(ui.tags.tr(
                ui.tags.td("River segments"),
                ui.tags.td(str(n_rivers)),
                ui.tags.td(f"Strahler {strahler_range}"),
            ))

        if water is not None:
            rows.append(ui.tags.tr(
                ui.tags.td("Water bodies"),
                ui.tags.td(str(len(water))),
                ui.tags.td("—"),
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
