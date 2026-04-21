"""Movement panel — live fish movement map during simulation.

Architecture:
- Widget is created inside @render.ui map_container() where the Shiny module
  namespace context is active (required for _resolve_ns to prefix the ID).
- _process_data() accumulates trajectory data and sends layers via
  widget.update() (cells once) then widget.partial_update() (trips).
- All mutable state is plain Python (not reactive.value) to avoid loops.
"""

import math
import logging
from datetime import datetime

import numpy as np  # noqa: E402
from shiny import module, reactive, render, ui

from shiny_deckgl import MapWidget, geojson_layer
from shiny_deckgl.controls import legend_control
from pathlib import Path

logger = logging.getLogger(__name__)

_WATER_PATH = Path(__file__).parent.parent / "data" / "water_polygons.geojson"
_WATER_COLORS = {"sea": [173, 216, 230, 80], "lagoon": [135, 206, 235, 100], "river": [100, 149, 237, 110]}


def _water_layer():
    if not _WATER_PATH.exists():
        return None
    import geopandas as _gpd
    gdf = _gpd.read_file(str(_WATER_PATH))
    geojson = gdf.__geo_interface__
    for feat in geojson["features"]:
        wtype = feat["properties"].get("type", "water")
        feat["properties"]["_fill"] = _WATER_COLORS.get(wtype, [173, 216, 230, 80])
    return geojson_layer(
        id="water-bg", data=geojson,
        get_fill_color="@@=properties._fill",
        get_line_color=[100, 140, 180, 60],
        get_line_width=1, stroked=True, filled=True, pickable=False,
    )

# OpenStreetMap-based basemap with terrain, roads, labels — highly visible
BASEMAP_VOYAGER = "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"

_TAB10 = [
    [31, 119, 180, 220],
    [255, 127, 14, 220],
    [44, 160, 44, 220],
    [214, 39, 40, 220],
    [148, 103, 189, 220],
    [140, 86, 75, 220],
    [227, 119, 194, 220],
    [127, 127, 127, 220],
    [188, 189, 34, 220],
    [23, 190, 207, 220],
]
_ACTIVITY_COLORS = {
    0: [66, 133, 244, 220],  # drift
    1: [52, 168, 83, 220],  # search
    2: [154, 160, 166, 220],  # hide
    3: [234, 67, 53, 220],  # guard
    4: [251, 188, 4, 220],  # hold
}


def _fit_bounds_zoom(bounds, map_width_px=800, map_height_px=600):
    """Compute zoom level fitting [minx, miny, maxx, maxy] bounds."""
    minx, miny, maxx, maxy = bounds
    lng_span = max(maxx - minx, 1e-6)
    lat_span = max(maxy - miny, 1e-6)
    zoom_lng = math.log2(map_width_px * 360 / (256 * lng_span)) if lng_span > 0 else 20
    lat_rad = math.radians((miny + maxy) / 2)
    zoom_lat = (
        math.log2(map_height_px * 360 / (256 * lat_span / math.cos(lat_rad)))
        if lat_span > 0
        else 20
    )
    zoom = min(zoom_lng, zoom_lat) - 0.5
    return max(8, min(20, zoom))


_MOVEMENT_CSS = """
.movement-map-controls {
    padding: 0.3rem 0.75rem 0 0.75rem;
}
.movement-map-controls .movement-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.2rem;
}
.movement-map-controls .movement-row > label {
    width: 72px;
    margin: 0;
    font-weight: 500;
    font-size: 0.9rem;
    flex-shrink: 0;
    line-height: 1.8;
}
.movement-map-controls .form-group,
.movement-map-controls .shiny-input-container {
    margin: 0 !important;
}
.movement-map-controls .shiny-label-null {
    display: none;
}
.movement-map-controls select.form-select {
    height: 31px;
    padding-top: 0.1rem;
    padding-bottom: 0.1rem;
    font-size: 0.9rem;
    min-width: 160px;
}
.movement-map-controls .irs {
    min-width: 220px;
    margin: 0;
}
.movement-map-controls .layer-description {
    color: #5a6268;
    font-style: italic;
    font-size: 0.82rem;
    margin-left: 0.1rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    min-width: 0;
}
"""

_COLOR_MODE_DESCRIPTIONS = {
    "species": "Trails colour-keyed by species (e.g. Atlantic salmon vs. brown trout).",
    "activity": "Trails colour-keyed by current activity (drift / search / hide / guard / hold).",
    "life_history": "Trails colour-keyed by life stage (fry / parr / smolt / adult / kelt).",
}


@module.ui
def movement_ui():
    return ui.card(
        ui.tags.style(_MOVEMENT_CSS),
        ui.card_header("Live Movement Map",
                       style="padding:0.3rem 0.75rem; font-size:0.95rem;"),
        ui.div(
            # Row 1: Color-by + description
            ui.div(
                ui.tags.label("Color by:"),
                ui.input_select(
                    "color_mode", None,
                    choices={
                        "species": "Species",
                        "activity": "Activity",
                        "life_history": "Life Stage",
                    },
                    width="200px",
                ),
                ui.output_ui("color_mode_description"),
                class_="movement-row",
            ),
            # Row 2: Trail length slider
            ui.div(
                ui.tags.label("Trail:"),
                ui.input_slider(
                    "trail_length", None,
                    min=1, max=90, value=5, step=1, width="300px",
                ),
                ui.tags.span(
                    "How many past days of trajectory to keep visible.",
                    class_="layer-description",
                ),
                class_="movement-row",
            ),
            class_="movement-map-controls",
        ),
        ui.output_ui("map_container"),
        ui.output_ui("status_text"),
        full_screen=True,
        height="100%",
        style="min-height: 600px;",
    )


@module.server
def movement_server(input, output, session, dashboard_data_rv):
    # ALL state is plain mutable — NOT reactive (avoids self-triggering loops)
    _trajectory_history = {}
    _species_map = {}
    _activity_map = {}
    _last_seen_day = {}
    _last_processed_idx = [0]
    _centroid_lut = [None]
    _cells_gdf = [None]
    _cells_sent = [False]
    _species_order = [[]]
    _start_date = [None]

    # Create widget ONCE in the module server context (namespace is active here).
    # Never re-create it — map_container renders it once and never re-renders.
    _map_widget = MapWidget(
        "movement_map",
        view_state={"longitude": 0.0, "latitude": 30.0, "zoom": 2},
        style=BASEMAP_VOYAGER,
        controls=[
            {"type": "navigation", "position": "top-right"},
            {"type": "fullscreen", "position": "top-right"},
            legend_control(position="bottom-left", show_default=False, show_checkbox=True),
        ],
        tooltip={
            "html": "<b>{cell_id}</b>",
            "style": {
                "backgroundColor": "#fff",
                "color": "#333",
                "fontSize": "12px",
                "border": "1px solid #ccc",
            },
        },
    )

    @output
    @render.ui
    def map_container():
        """Render the map widget div once. Never re-renders."""
        return _map_widget.ui(height="550px")

    @output
    @render.ui
    def color_mode_description():
        """Inline blurb right of the Color-by dropdown; matches Setup UX."""
        key = input.color_mode() or "species"
        text = _COLOR_MODE_DESCRIPTIONS.get(key, "")
        return ui.tags.span(text, class_="layer-description")

    @output
    @render.ui
    def status_text():
        data = dashboard_data_rv()
        if not data:
            return ui.p(
                "Idle — click 'Run Simulation' in the sidebar to populate "
                "fish-movement trails here.",
                style=(
                    "color:#888; text-align:center; font-style:italic; "
                    "padding:0.6rem 0;"
                ),
            )
        snapshots = [d for d in data if d.get("type") == "snapshot"]
        if not snapshots:
            return ui.p("Waiting for data…",
                        style="color:#888;text-align:center;")
        return ui.p(
            "Day {} — {} fish tracked".format(
                snapshots[-1]["date"], len(_trajectory_history)
            ),
            style="color:#555;text-align:center;",
        )

    @reactive.effect
    async def _process_data():
        """Accumulate trajectory data and send layers to the map."""
        data = dashboard_data_rv()
        if not data:
            return
        widget = _map_widget

        # Reset detection: data shrank (new simulation started)
        total_len = len(data)
        if total_len < _last_processed_idx[0]:
            _trajectory_history.clear()
            _species_map.clear()
            _activity_map.clear()
            _last_seen_day.clear()
            _last_processed_idx[0] = 0
            _cells_sent[0] = False
            _start_date[0] = None

        # Process new messages since last index
        start_idx = _last_processed_idx[0]
        new_messages = data[start_idx:]
        if not new_messages:
            return

        try:
            for msg in new_messages:
                if msg.get("type") == "cells":
                    gdf = msg["cells_geojson"]
                    _cells_gdf[0] = gdf
                    centroids = gdf.geometry.centroid
                    _centroid_lut[0] = np.column_stack([centroids.x, centroids.y])
                    _species_order[0] = []
                    _cells_sent[0] = False
                    continue

                if msg.get("type") != "snapshot" or _centroid_lut[0] is None:
                    continue

                pos = msg["positions"]
                date_str = msg["date"]

                if _start_date[0] is None:
                    _start_date[0] = date_str
                dt_start = datetime.strptime(_start_date[0], "%Y-%m-%d")
                dt_now = datetime.strptime(date_str, "%Y-%m-%d")
                day_num = (dt_now - dt_start).days

                if not _species_order[0]:
                    _species_order[0] = list(msg["alive"].keys())

                for i in range(len(pos["fish_idx"])):
                    fid = pos["fish_idx"][i]
                    cid = pos["cell_idx"][i]
                    sid = pos["species_idx"][i]
                    act = pos["activity"][i]

                    if cid < 0 or cid >= len(_centroid_lut[0]):
                        continue  # skip marine fish (cell_idx=-1) and out-of-bounds

                    # Slot-reuse detection
                    if fid in _last_seen_day and day_num > _last_seen_day[fid] + 1:
                        _trajectory_history[fid] = []

                    lon, lat = _centroid_lut[0][cid]
                    if fid not in _trajectory_history:
                        _trajectory_history[fid] = []
                    _trajectory_history[fid].append([float(lon), float(lat), day_num])
                    _species_map[fid] = sid
                    _activity_map[fid] = act
                    _last_seen_day[fid] = day_num

            _last_processed_idx[0] = total_len

            # Send cells layer once + fly to bounds
            if not _cells_sent[0] and _cells_gdf[0] is not None:
                gdf = _cells_gdf[0]
                bounds = gdf.total_bounds
                center_lon = (bounds[0] + bounds[2]) / 2
                center_lat = (bounds[1] + bounds[3]) / 2
                zoom = _fit_bounds_zoom(bounds)
                cells_layer = geojson_layer(
                    "movement_cells",
                    gdf,
                    getFillColor=[200, 200, 200, 80],
                    getLineColor=[120, 120, 120, 150],
                    lineWidthMinPixels=1,
                    pickable=True,
                )
                await widget.update(
                    session,
                    [cells_layer],
                    view_state={
                        "longitude": center_lon,
                        "latitude": center_lat,
                        "zoom": zoom,
                    },
                    transition_duration=1000,
                )
                _cells_sent[0] = True

            # Build TripsLayer — only for fish seen in the latest snapshot
            if not _trajectory_history:
                return

            color_mode = "species"
            try:
                color_mode = input.color_mode()
            except Exception:
                pass

            # Determine the current day and which fish are alive
            max_time = 0
            for path in _trajectory_history.values():
                if path:
                    max_time = max(max_time, path[-1][2])

            # Only show fish that were updated on the latest day (alive)
            trips_data = []
            for fid, path in _trajectory_history.items():
                if len(path) < 2:
                    continue
                # Skip dead fish — their last seen day is old
                last_day = _last_seen_day.get(fid, -1)
                if last_day < max_time:
                    continue
                sid = _species_map.get(fid, 0)
                if color_mode == "activity":
                    act = _activity_map.get(fid, 0)
                    color = _ACTIVITY_COLORS.get(act, [127, 127, 127, 220])
                else:
                    color = _TAB10[sid % len(_TAB10)]
                timestamps = [p[2] for p in path]
                trips_data.append({
                    "path": path,
                    "timestamps": timestamps,
                    "color": color,
                })

            if trips_data:
                from shiny_deckgl import trips_layer

                trail_len = 5
                try:
                    trail_len = int(input.trail_length())
                except Exception:
                    pass

                trail_lyr = trips_layer(
                    "fish_trails",
                    trips_data,
                    getPath="@@d.path",
                    getTimestamps="@@d.timestamps",
                    getColor="@@d.color",
                    currentTime=max_time,
                    trailLength=trail_len,
                    widthMinPixels=2,
                    widthMaxPixels=5,
                    pickable=False,
                )
                # Rebuild all layers: water background + cells + trails
                layers = []
                wl = _water_layer()
                if wl is not None:
                    layers.append(wl)
                if _cells_gdf[0] is not None:
                    cells_lyr = geojson_layer(
                        "movement_cells",
                        _cells_gdf[0],
                        getFillColor=[200, 200, 200, 80],
                        getLineColor=[120, 120, 120, 150],
                        lineWidthMinPixels=1,
                        pickable=True,
                    )
                    layers.append(cells_lyr)
                layers.append(trail_lyr)
                await widget.update(session, layers)

        except Exception as e:
            if "SilentException" in type(e).__name__:
                return
            logger.exception("Error processing movement data")
