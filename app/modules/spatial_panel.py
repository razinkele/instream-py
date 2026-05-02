"""Spatial panel — interactive deck.gl map with cell polygons and fish trips.

Architecture:
- Cell polygon layer is sent ONCE when simulation completes (full update).
  Changing color_var re-colors cells via partial_update (no full re-send).
- Fish movement is visualised via the TripsLayer animation only.
- Trips layer uses partial_update so the static cell layer is never re-sent.
- Animation controls (play/pause/reset, speed, trail length) drive the trips.
"""

import logging
import math

import pandas as pd
from shiny import module, reactive, render, ui


from shiny_deckgl import (
    MapWidget,
    geojson_layer,
    scatterplot_layer,
    trips_layer,
)
# legend_control removed in v0.56.20 — replaced by `layer_legend_widget`
# for per-reach toggles. The old MapLibre legend_control crashed with
# "Cannot read properties of undefined (reading 'layers')" when
# fitBounds fired before the MapLibre style had loaded.

# Light basemap with labels for readability
BASEMAP_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
from shiny_deckgl.ibm import format_trips, trips_animation_server
from simulation import _build_trajectories_data, _value_to_rgba

logger = logging.getLogger(__name__)

COLORING_VARS = {
    "depth": "Depth (cm)",
    "velocity": "Velocity (cm/s)",
    "available_drift": "Drift Food Available",
    "available_search": "Search Food Available",
    "fish_count": "Fish Density",
}

TRIPS_COLOR_MODES = {
    "species": "Species",
    "activity": "Activity",
    "life_history": "Life History",
}


@module.ui
def spatial_ui():
    return ui.card(
        LEGEND_POINTER_EVENTS_FIX,
        ui.card_header("Spatial View"),
        ui.layout_columns(
            ui.input_select("color_var", "Cells color:", choices=COLORING_VARS),
            ui.input_select("trips_color", "Trails color:", choices=TRIPS_COLOR_MODES),
            col_widths=(6, 6),
        ),
        ui.layout_columns(
            ui.input_checkbox("show_trips", "Show fish trails", value=True),
            ui.input_checkbox("show_heads", "Show fish icons", value=True),
            ui.input_checkbox("show_redds", "Show redds (egg nests)", value=True),
            col_widths=(4, 4, 4),
        ),
        # OSM source layers are exposed via the in-map "OSM source layers"
        # legend widget (top-left) — per-reach toggles + color swatches.
        ui.input_slider(
            "trail_width",
            "Trail width (px)",
            min=1,
            max=10,
            value=3,
            step=1,
            width="100%",
        ),
        ui.output_ui("anim_controls"),
        ui.output_ui("map_container"),
        full_screen=True,
        height="100%",
        style="min-height: 600px;",
    )


@module.server
def spatial_server(input, output, session, results_rv):
    @reactive.calc
    def cells_wgs84():
        results = results_rv()
        if results is None:
            return None
        gdf = results["cells"]
        if gdf.empty:
            return None
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            return gdf.to_crs(epsg=4326)
        return gdf

    _widget = reactive.value(None)
    _cells_sent = reactive.value(False)
    _anim_server = reactive.value(None)
    # v0.56.10: cache last-built cells & redds layers so the OSM toggle
    # can do a full `widget.update()` (forces deck.gl to rebuild the
    # layer stack instead of relying on partial_update's visibility
    # patching, which silently dropped layers in some browser/version
    # combos). Re-using cached layers means re-rendering is still fast.
    _last_cells_layer = reactive.value(None)
    _last_redds_layer = reactive.value(None)

    @output
    @render.ui
    def anim_controls():
        if not input.show_trips():
            return ui.TagList()
        results = results_rv()
        if results is None:
            return ui.TagList()
        traj_df = results.get("trajectories")
        if traj_df is None or traj_df.empty:
            return ui.TagList()
        from shiny_deckgl.ibm import trips_animation_ui

        return trips_animation_ui("fish_anim")

    @output
    @render.ui
    def map_container():
        gdf_wgs84 = cells_wgs84()
        if gdf_wgs84 is None:
            return ui.p("Run a simulation to see results.")

        bounds = gdf_wgs84.total_bounds  # [minx, miny, maxx, maxy]
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
        zoom = _fit_bounds_zoom(bounds)

        widget = MapWidget(
            "spatial_map",
            view_state={
                "longitude": center_lon,
                "latitude": center_lat,
                "zoom": zoom,
                "pitch": 0,
                "bearing": 0,
            },
            style=BASEMAP_LIGHT,
            animate=True,
            controls=[
                {"type": "navigation", "position": "top-right"},
                {"type": "fullscreen", "position": "top-right"},
            ],
            tooltip={
                "html": "<b>{cell_id}</b><br/>{_tooltip_var}: {_tooltip_val}",
                "style": {
                    "backgroundColor": "#fff",
                    "color": "#333",
                    "fontSize": "12px",
                    "border": "1px solid #ccc",
                },
            },
        )
        _widget.set(widget)
        _cells_sent.set(False)
        # Register animation server once per widget lifetime
        _anim_server.set(
            trips_animation_server("fish_anim", widget=widget, session=session)
        )
        return widget.ui(height="550px")

    # ------------------------------------------------------------------
    # ONE-TIME initial layer push — sent once when simulation completes.
    # Reads color_var inside reactive.isolate so it doesn't re-fire.
    # ------------------------------------------------------------------
    @reactive.effect
    async def _send_cells_once():
        widget = _widget()
        gdf_wgs84 = cells_wgs84()
        if widget is None or gdf_wgs84 is None:
            return
        if _cells_sent():
            return

        results = results_rv()
        if results is None:
            return

        try:
            with reactive.isolate():
                color_var = input.color_var()

            cells_layer = _build_cells_layer(gdf_wgs84, color_var)

            # Redd layer: scatterplot of egg nests at host-cell centroids.
            # Sent here so it renders alongside cells on first paint;
            # toggled via _toggle_redds below.
            with reactive.isolate():
                show_redds = input.show_redds()
            redds_layer = _build_redds_layer(results, visible=show_redds)

            # OSM-source overlays (v0.56.17+): one layer per (reach, kind)
            # group across all `*-osm-*.shp` sidecars. Each layer has a
            # stable id (osm-<reach>-<polygons|centerlines>) so the in-map
            # ``layer_legend_widget`` can toggle each reach independently.
            sidecars = (results or {}).get("osm_sidecars") or {}
            osm_layers = build_osm_overlay_layers(sidecars, visible=True)
            osm_legend = build_osm_overlay_legend_widget(sidecars, placement="top-left")
            extra_widgets = [osm_legend] if osm_legend is not None else None

            # Send cells + redds + OSM overlays together; _update_trips
            # handles trips after _cells_sent becomes True.
            await widget.update(
                session,
                [cells_layer, redds_layer, *osm_layers],
                animate=True,
                widgets=extra_widgets,
            )
            _last_cells_layer.set(cells_layer)
            _last_redds_layer.set(redds_layer)
            _cells_sent.set(True)

        except Exception as e:
            if "SilentException" in type(e).__name__:
                return
            logger.exception("Error sending initial layers")

    # ------------------------------------------------------------------
    # REDD VISIBILITY — partial_update when the show_redds checkbox flips
    # ------------------------------------------------------------------
    @reactive.effect
    async def _toggle_redds():
        widget = _widget()
        if widget is None or not _cells_sent():
            return
        results = results_rv()
        if results is None:
            return
        show = input.show_redds()
        try:
            redds_layer = _build_redds_layer(results, visible=show)
            _last_redds_layer.set(redds_layer)
            await widget.partial_update(session, [redds_layer])
        except Exception as e:
            if "SilentException" in type(e).__name__:
                return
            logger.exception("Error updating redds layer")

    # ------------------------------------------------------------------
    # OSM overlay visibility is now driven from the in-map legend widget
    # (deck.gl `layer_legend_widget`, top-left). No server-side reactive
    # effect needed — clicking a checkbox in the legend toggles the
    # corresponding deck.gl layer's visibility on the JS client.
    # ------------------------------------------------------------------
    # CELL RE-COLORING — partial_update when color_var changes
    # ------------------------------------------------------------------
    @reactive.effect
    async def _recolor_cells():
        widget = _widget()
        if widget is None or not _cells_sent():
            return
        gdf_wgs84 = cells_wgs84()
        if gdf_wgs84 is None:
            return

        color_var = input.color_var()

        try:
            cells_layer = _build_cells_layer(gdf_wgs84, color_var)
            _last_cells_layer.set(cells_layer)
            await widget.partial_update(session, [cells_layer])
        except Exception as e:
            if "SilentException" in type(e).__name__:
                return
            logger.exception("Error re-coloring cells")

    # ------------------------------------------------------------------
    # TRIPS layer — partial_update only, never re-sends cells
    # ------------------------------------------------------------------
    @reactive.effect
    async def _update_trips():
        widget = _widget()
        if widget is None or not _cells_sent():
            return

        results = results_rv()
        if results is None:
            return

        show = input.show_trips()
        show_heads = input.show_heads()
        trips_color = input.trips_color()
        trail_width = input.trail_width()

        # Read animation controls if registered
        anim = _anim_server()
        speed = anim.speed() if anim else 8.0
        trail = anim.trail() if anim else 180

        try:
            if not show:
                await widget.partial_update(
                    session,
                    [trips_layer("fish_trips", [], visible=False)],
                )
                return

            traj_df = results.get("trajectories")
            if traj_df is None or traj_df.empty:
                return

            trip_lyr = _build_trips_layer(
                results,
                traj_df,
                trips_color,
                speed=speed,
                trail=trail,
                width=trail_width,
                head_icons=show_heads,
            )
            if trip_lyr is not None:
                await widget.partial_update(session, [trip_lyr])

        except Exception as e:
            if "SilentException" in type(e).__name__:
                return
            logger.exception("Error updating trips layer")


# ======================================================================
# Helper functions (module-level, no reactive dependencies)
# ======================================================================


def _fit_bounds_zoom(bounds, map_width_px=800, map_height_px=600):
    """Compute a zoom level that fits the given [minx, miny, maxx, maxy] bounds.

    Uses the Web Mercator formula to calculate the zoom that fits both
    the longitude and latitude spans into the given pixel dimensions,
    with a small padding margin.
    """
    minx, miny, maxx, maxy = bounds
    lng_span = max(maxx - minx, 1e-6)
    lat_span = max(maxy - miny, 1e-6)

    # Mercator formula: pixels = 256 * 2^zoom * (lng_span / 360)
    zoom_lng = math.log2(map_width_px * 360 / (256 * lng_span)) if lng_span > 0 else 20
    # Latitude uses Mercator projection stretch factor
    lat_rad = math.radians((miny + maxy) / 2)
    zoom_lat = (
        math.log2(map_height_px * 360 / (256 * lat_span / math.cos(lat_rad)))
        if lat_span > 0
        else 20
    )

    zoom = min(zoom_lng, zoom_lat) - 0.5  # padding
    return max(8, min(20, zoom))


def _build_redds_layer(results, visible: bool = True):
    """Scatterplot of redd (egg-nest) locations at their host cell centroids.

    Point radius scales with ``sqrt(eggs)`` so a 1,000-egg redd is ~3x the
    visual radius of a 100-egg redd (log-ish scaling keeps small redds
    visible without dwarfing them). Colour is deep pink (``#e2007a``)
    matching the dashboard's redd chart trace.

    Returns ``None`` when the simulation produced no redds (empty DF).
    """
    import math

    redds = results.get("redds")
    if redds is None or redds.empty:
        # Return an empty layer so partial_update toggles work cleanly.
        return scatterplot_layer("redds", [], visible=visible)

    cells = results.get("cells")
    if cells is None or cells.empty:
        return scatterplot_layer("redds", [], visible=visible)

    # Centroids from polygons in a geographic CRS (EPSG:4326 / WGS84)
    # trigger a shapely UserWarning because degrees aren't equal-area.
    # Reproject to the mesh's local UTM for centroid computation (silences
    # the warning AND gives geometrically-correct centroids), then pull
    # lon/lat back out. Auto-detects the right UTM zone so non-Baltic
    # deploys don't silently use UTM 34N.
    try:
        target_crs = cells.estimate_utm_crs()
    except Exception:
        # Fallback: Baltic UTM 34N (legacy behavior) if auto-detect fails
        target_crs = 32634
    cells_geo = cells if (cells.crs is not None) else cells.set_crs(4326, allow_override=True)
    cells_utm = (
        cells_geo.to_crs(target_crs)
        if cells_geo.crs.to_epsg() != getattr(target_crs, "to_epsg", lambda: target_crs)()
        else cells_geo
    )
    centroids_utm = cells_utm.geometry.centroid
    centroids = centroids_utm.to_crs(epsg=4326)
    data = []
    for _, r in redds.iterrows():
        cidx = int(r["cell_idx"])
        if cidx < 0 or cidx >= len(centroids):
            continue
        c = centroids.iloc[cidx]
        eggs = int(r.get("eggs", 0))
        # Radius in metres; sqrt(eggs) keeps a 10,000-egg redd at 100 m
        # and a 100-egg redd at ~10 m. radiusMinPixels floors it visibly.
        radius_m = max(5.0, math.sqrt(max(eggs, 1)) * 1.5)
        data.append({
            "position": [float(c.x), float(c.y)],
            "radius": radius_m,
            "eggs": eggs,
            "species": str(r.get("species", "")),
            "frac_developed": float(r.get("frac_developed", 0.0)),
        })

    return scatterplot_layer(
        "redds",
        data,
        getPosition="@@=d.position",
        getRadius="@@=d.radius",
        getFillColor=[226, 0, 122, 200],          # #e2007a to match dashboard
        getLineColor=[100, 0, 60, 255],
        lineWidthMinPixels=1,
        radiusMinPixels=4,
        radiusMaxPixels=40,
        radiusUnits="meters",
        pickable=True,
        visible=visible,
    )


# Per-reach palette for the OSM-overlay layers. Each reach gets a
# distinct color across both polygon (fill) and centerline (stroke)
# layers so the legend swatches read well. Reaches not in this map use
# the fallback color (orange/red).
_REACH_COLORS = {
    "Minija":         {"fill": [255, 140,   0, 170], "stroke": [200,  50,   0, 255]},
    "Babrungas":      {"fill": [ 30, 144, 255, 170], "stroke": [  0,  80, 200, 255]},
    "Salantas":       {"fill": [148, 103, 189, 170], "stroke": [ 80,  40, 130, 255]},
    "Salpe":          {"fill": [ 44, 160,  44, 170], "stroke": [ 20, 100,  20, 255]},
    "Veivirzas":      {"fill": [227, 119, 194, 170], "stroke": [180,  60, 130, 255]},
    "Atmata":         {"fill": [220,  20,  60, 170], "stroke": [140,   0,  20, 255]},
    "CuronianLagoon": {"fill": [ 70, 200, 230, 130], "stroke": [ 30, 120, 170, 255]},
}
_FALLBACK_COLOR = {"fill": [255, 140, 0, 170], "stroke": [200, 50, 0, 255]}


def _reach_layer_id(reach: str, kind: str) -> str:
    """Stable layer id used by the layer-legend widget for visibility toggles."""
    return f"osm-{reach}-{kind}"


def _reach_label(reach: str, kind: str) -> str:
    """Human-readable label shown in the in-map legend widget."""
    pretty = {"polygons": "area", "centerlines": "centerline"}[kind]
    return f"{reach} ({pretty})"


def build_osm_overlay_layers(sidecars: dict, visible: bool = True) -> list:
    """Render the OSM-source sidecar shapefiles as **per-reach** overlay layers.

    Each ``REACH_NAME`` value across all sidecars produces TWO deck.gl
    layers — one for its polygons and one for its centerlines — with a
    stable id (``osm-<reach>-<kind>``) so the in-map ``layer_legend_widget``
    can toggle each reach independently. Per-reach colors come from
    ``_REACH_COLORS``; layers default to ``visible=True`` because the
    legend widget controls visibility from the client side.

    Z-order: emit centerlines first and polygons last so polygons render
    on top (avoids the v0.56.14 problem where 3 px magenta centerlines
    hid the polygon stroke for thin streams).
    """
    if not sidecars:
        return []

    # Group features by (REACH_NAME, kind) across all sidecars so each
    # reach gets one polygon layer + one centerline layer regardless of
    # which sidecar file the rows come from.
    import geopandas as _gpd
    grouped: dict = {}
    for stem, gdf in sidecars.items():
        kind = "polygons" if "-polygons" in stem else "centerlines"
        if "REACH_NAME" not in gdf.columns:
            continue
        for reach, sub in gdf.groupby("REACH_NAME"):
            key = (str(reach), kind)
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = sub.copy()
            else:
                grouped[key] = _gpd.GeoDataFrame(
                    pd.concat([existing, sub], ignore_index=True),
                    geometry="geometry",
                    crs=existing.crs,
                )

    centerline_layers = []
    polygon_layers = []
    for (reach, kind), sub_gdf in grouped.items():
        colors = _REACH_COLORS.get(reach, _FALLBACK_COLOR)
        if kind == "polygons":
            polygon_layers.append(
                geojson_layer(
                    _reach_layer_id(reach, kind),
                    sub_gdf,
                    visible=visible,
                    pickable=False,
                    getFillColor=colors["fill"],
                    getLineColor=colors["stroke"],
                    lineWidthMinPixels=3,
                    stroked=True,
                    filled=True,
                )
            )
        else:
            centerline_layers.append(
                geojson_layer(
                    _reach_layer_id(reach, kind),
                    sub_gdf,
                    visible=visible,
                    pickable=False,
                    getLineColor=colors["stroke"],
                    lineWidthMinPixels=3,
                    stroked=True,
                    filled=False,
                )
            )
    return centerline_layers + polygon_layers


# CSS fix for shiny-deckgl 1.9.2: the widget container hierarchy
# (.deck-widget-container > .top-left/...) sets pointer-events:none so
# the underlying map can be dragged through the empty corner area, but
# `.deck-widget` itself doesn't opt back in to pointer-events:auto. As
# a result, all clicks on the legend widget header / checkboxes are
# silently dropped. We inject this rule once per panel.
LEGEND_POINTER_EVENTS_FIX = ui.tags.style("""
.deck-widget-container,
.deck-widget-container .top-left,
.deck-widget-container .top-right,
.deck-widget-container .bottom-left,
.deck-widget-container .bottom-right { pointer-events: none; }
.deck-widget,
.deck-widget * { pointer-events: auto !important; }
""")


def build_osm_overlay_legend_widget(sidecars: dict, *, placement: str = "top-left") -> dict | None:
    """Build a ``layer_legend_widget`` listing one entry per reach layer.

    Returns ``None`` when there are no sidecars (so the caller can skip
    the widget entirely). Entries are constructed manually rather than
    relying on auto-introspect — this keeps swatch colors aligned with
    the layer styling and labels human-friendly.
    """
    from shiny_deckgl import layer_legend_widget

    if not sidecars:
        return None

    # Walk sidecars in the same way build_osm_overlay_layers does to get
    # the same (reach, kind) keyset; this guarantees the legend's layer_id
    # entries match real layer ids in the deck.
    seen: dict = {}
    for stem, gdf in sidecars.items():
        kind = "polygons" if "-polygons" in stem else "centerlines"
        if "REACH_NAME" not in gdf.columns:
            continue
        for reach in gdf["REACH_NAME"].unique():
            seen.setdefault((str(reach), kind), True)
    if not seen:
        return None

    entries = []
    for (reach, kind) in seen:
        colors = _REACH_COLORS.get(reach, _FALLBACK_COLOR)
        if kind == "polygons":
            entries.append({
                "layer_id": _reach_layer_id(reach, kind),
                "label": _reach_label(reach, kind),
                "color": colors["fill"],
                "shape": "rect",
            })
        else:
            entries.append({
                "layer_id": _reach_layer_id(reach, kind),
                "label": _reach_label(reach, kind),
                "color": colors["stroke"],
                "shape": "line",
            })
    return layer_legend_widget(
        entries=entries,
        placement=placement,
        title="OSM source layers",
        show_checkbox=True,
        collapsed=False,
    )


def _build_osm_overlay_layers(results, visible: bool = False) -> list:
    """Backwards-compatible wrapper: extracts ``osm_sidecars`` from the
    simulation results dict and delegates to :func:`build_osm_overlay_layers`.
    """
    sidecars = results.get("osm_sidecars") if results else None
    return build_osm_overlay_layers(sidecars or {}, visible=visible)


def _build_cells_layer(gdf_wgs84, color_var):
    """Build a GeoJSON cell polygon layer coloured by color_var."""
    gdf_colored = gdf_wgs84.copy()
    if color_var in gdf_colored.columns:
        gdf_colored["color"] = _value_to_rgba(gdf_colored[color_var].values)
        gdf_colored["_tooltip_var"] = COLORING_VARS.get(color_var, color_var)
        gdf_colored["_tooltip_val"] = gdf_colored[color_var].round(2).astype(str)
    else:
        gdf_colored["color"] = [[100, 100, 100, 100] for _ in range(len(gdf_colored))]
        gdf_colored["_tooltip_var"] = ""
        gdf_colored["_tooltip_val"] = ""

    return geojson_layer(
        "cells",
        gdf_colored,
        getFillColor="@@=d.properties.color",
        getLineColor=[120, 120, 120, 150],
        lineWidthMinPixels=1,
    )


def _build_trips_layer(
    results,
    traj_df,
    color_mode,
    speed=8.0,
    trail=180,
    width=3,
    head_icons=True,
):
    """Build a TripsLayer dict from simulation results."""
    from shiny_deckgl.ibm import ICON_ATLAS, ICON_MAPPING

    species_cfg = results["config"].get("species", {})
    species_order = list(species_cfg.keys()) if species_cfg else ["unknown"]

    paths, props = _build_trajectories_data(
        traj_df,
        results["cells"],
        species_order,
        color_mode=color_mode,
    )

    if not paths:
        return None

    total_days = max(int(traj_df["day_num"].max()) + 1, 2)
    trips_data = format_trips(
        paths,
        loop_length=total_days,
        properties=props,
    )

    # Map inSTREAM species names to fish sprites from the sprite sheet.
    _FISH_SPRITES = [
        "Atlantic salmon",
        "Atlantic cod",
        "Baltic herring",
        "European smelt",
    ]
    icon_mapping = {}
    for i, sp_name in enumerate(species_order):
        sprite_name = _FISH_SPRITES[i % len(_FISH_SPRITES)]
        icon_mapping[sp_name] = dict(
            ICON_MAPPING[sprite_name]
        )  # copy to avoid aliasing

    layer_kwargs = {
        "getColor": "@@=d.color",
        "trailLength": trail,
        "fadeTrail": True,
        "widthMinPixels": width,
        "_tripsAnimation": {
            "loopLength": total_days,
            "speed": speed,
        },
    }

    if head_icons:
        layer_kwargs["_tripsHeadIcons"] = {
            "iconAtlas": ICON_ATLAS,
            "iconMapping": icon_mapping,
            "iconField": "species",
            "getSize": 28,
            "sizeScale": 1,
            "sizeMinPixels": 12,
            "sizeMaxPixels": 48,
        }

    return trips_layer("fish_trips", trips_data, **layer_kwargs)
