"""Movement panel — live fish movement map during simulation."""

import math
import logging
from datetime import datetime

import numpy as np
from shiny import module, reactive, render, ui

from shiny_deckgl import MapWidget, geojson_layer, trips_layer
from shiny_deckgl.ibm import format_trips

logger = logging.getLogger(__name__)

BASEMAP_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

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


@module.ui
def movement_ui():
    return ui.card(
        ui.card_header("Live Movement Map"),
        ui.layout_columns(
            ui.input_select(
                "color_mode",
                "Color by:",
                choices={"species": "Species", "activity": "Activity"},
            ),
            col_widths=(4,),
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
    _trajectory_history = {}  # {fish_idx: [[lon, lat, day], ...]}
    _species_map = {}  # {fish_idx: species_idx}
    _activity_map = {}  # {fish_idx: last_activity_code}
    _last_seen_day = {}  # {fish_idx: last day_num} for slot-reuse detection
    _last_processed_idx = [0]
    _centroid_lut = [None]  # mutable container for np.ndarray
    _cells_gdf = [None]
    _widget = [None]  # plain mutable — NOT reactive.value
    _cells_sent = [False]
    _species_order = [[]]
    _start_date = [None]

    # Signal for map_container to re-render when widget is created
    _widget_version = reactive.value(0)

    @output
    @render.ui
    def map_container():
        """Reactively render map widget or placeholder."""
        _widget_version()  # take dependency — re-renders when widget is created
        if _widget[0] is not None:
            return _widget[0].ui(height="100%")
        data = dashboard_data_rv()
        if not data:
            return ui.p(
                "Run a simulation to see fish movement.",
                style="text-align:center;color:#888;padding:60px;",
            )
        return ui.p(
            "Waiting for simulation data...",
            style="text-align:center;color:#888;padding:40px;",
        )

    @output
    @render.ui
    def status_text():
        data = dashboard_data_rv()
        if not data:
            return ui.p("Idle", style="color:#888;text-align:center;")
        snapshots = [d for d in data if d.get("type") == "snapshot"]
        if not snapshots:
            return ui.p("Waiting for data...", style="color:#888;text-align:center;")
        return ui.p(
            "Day {} — {} fish tracked".format(
                snapshots[-1]["date"],
                len(_trajectory_history),
            ),
            style="color:#555;text-align:center;",
        )

    @reactive.effect
    async def _process_data():
        data = dashboard_data_rv()
        if not data:
            return

        # Reset detection: data shrank (new simulation started)
        total_len = len(data)
        if total_len < _last_processed_idx[0]:
            _trajectory_history.clear()
            _species_map.clear()
            _activity_map.clear()
            _last_seen_day.clear()
            _last_processed_idx[0] = 0
            _centroid_lut[0] = None
            _cells_gdf[0] = None
            _cells_sent[0] = False
            _start_date[0] = None
            _widget[0] = None

        # Process new messages since last index
        new_messages = data[_last_processed_idx[0] :]
        if not new_messages:
            return
        _last_processed_idx[0] = total_len

        try:
            for msg in new_messages:
                if msg.get("type") == "cells":
                    _cells_gdf[0] = msg["cells_geojson"]
                    centroids = _cells_gdf[0].geometry.centroid
                    _centroid_lut[0] = np.column_stack([centroids.x, centroids.y])
                    _species_order[0] = []
                    # Create widget now
                    gdf = _cells_gdf[0]
                    bounds = gdf.total_bounds
                    center_lon = (bounds[0] + bounds[2]) / 2
                    center_lat = (bounds[1] + bounds[3]) / 2
                    zoom = _fit_bounds_zoom(bounds)
                    _widget[0] = MapWidget(
                        "movement_map",
                        view_state={
                            "longitude": center_lon,
                            "latitude": center_lat,
                            "zoom": zoom,
                        },
                        style=BASEMAP_LIGHT,
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
                    _cells_sent[0] = False
                    _widget_version.set(_widget_version() + 1)

                elif msg.get("type") == "snapshot" and _centroid_lut[0] is not None:
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

                        if cid >= len(_centroid_lut[0]):
                            continue

                        # Slot-reuse detection: gap > 1 day means slot was recycled
                        if fid in _last_seen_day and day_num > _last_seen_day[fid] + 1:
                            _trajectory_history[fid] = []

                        lon, lat = _centroid_lut[0][cid]
                        if fid not in _trajectory_history:
                            _trajectory_history[fid] = []
                        _trajectory_history[fid].append(
                            [float(lon), float(lat), day_num]
                        )
                        _species_map[fid] = sid
                        _activity_map[fid] = act
                        _last_seen_day[fid] = day_num

            # Send layers if widget exists and we have trajectory data
            widget = _widget[0]
            if widget is not None and _trajectory_history:
                # Send cells once
                if not _cells_sent[0] and _cells_gdf[0] is not None:
                    cells_layer = geojson_layer(
                        "movement_cells",
                        _cells_gdf[0],
                        getFillColor=[200, 200, 200, 80],
                        getLineColor=[120, 120, 120, 150],
                        lineWidthMinPixels=1,
                        pickable=True,
                    )
                    await widget.update(session, [cells_layer])
                    _cells_sent[0] = True

                # Build trips from accumulated history
                color_mode = "species"
                try:
                    color_mode = input.color_mode()
                except Exception:
                    pass

                paths = []
                props = []
                for fid, path in _trajectory_history.items():
                    if len(path) < 2:
                        continue
                    paths.append(path)  # 3-element [lon, lat, day_num] lists
                    sid = _species_map.get(fid, 0)
                    if color_mode == "activity":
                        act = _activity_map.get(fid, 0)
                        color = _ACTIVITY_COLORS.get(act, [127, 127, 127, 220])
                    else:
                        color = _TAB10[sid % len(_TAB10)]
                    sp_name = (
                        _species_order[0][sid]
                        if sid < len(_species_order[0])
                        else "species_{}".format(sid)
                    )
                    props.append({"species": sp_name, "color": color})

                if paths:
                    max_day = max(p[-1][2] for p in paths)
                    trips_data = format_trips(
                        paths, loop_length=max_day + 1, properties=props
                    )
                    trip_lyr = trips_layer(
                        "fish_movement",
                        trips_data,
                        getColor="@@=d.color",
                        currentTime=max_day,
                        trailLength=max_day + 1,
                        fadeTrail=True,
                        widthMinPixels=2,
                    )
                    await widget.partial_update(session, [trip_lyr])

        except Exception as e:
            if "SilentException" in type(e).__name__:
                return
            logger.exception("Error processing movement data")
