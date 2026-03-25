"""Spatial panel — interactive deck.gl map with cell polygons and fish trips."""

import logging

from shiny import module, reactive, render, ui

from shiny_deckgl import (
    MapWidget,
    CARTO_DARK,
    geojson_layer,
    trips_layer,
)
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
        ui.card_header("Spatial View"),
        ui.layout_columns(
            ui.input_select("color_var", "Cells color:", choices=COLORING_VARS),
            ui.input_select("trips_color", "Trails color:", choices=TRIPS_COLOR_MODES),
            ui.input_checkbox("show_trips", "Show fish trails", value=False),
            col_widths=(4, 4, 4),
        ),
        ui.output_ui("anim_controls"),
        ui.output_ui("map_container"),
    )


@module.server
def spatial_server(input, output, session, results_rv):
    # Cache reprojected GeoDataFrame to avoid redundant CRS transforms
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

    # Create widget once per simulation run, stable across input changes
    _widget = reactive.value(None)

    # Register animation server unconditionally (avoids duplicate registration)
    # It will be a no-op when widget is None
    @reactive.calc
    def _anim():
        widget = _widget()
        if widget is None:
            return None
        return trips_animation_server("fish_anim", widget=widget, session=session)

    @output
    @render.ui
    def anim_controls():
        """Show animation controls only when trips checkbox is on and data exists."""
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

        # Compute view state from bounds
        bounds = gdf_wgs84.total_bounds  # [minx, miny, maxx, maxy]
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
        # Zoom heuristic: ~14 for a small river reach, clamped to [8, 18]
        extent = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
        zoom = max(8, min(18, int(14 - extent * 100)))

        widget = MapWidget(
            "spatial_map",
            view_state={
                "longitude": center_lon,
                "latitude": center_lat,
                "zoom": zoom,
            },
            style=CARTO_DARK,
            animate=True,
            tooltip={
                "html": "<b>{cell_id}</b><br/>{_tooltip_var}: {_tooltip_val}",
                "style": {
                    "backgroundColor": "#222",
                    "color": "#fff",
                    "fontSize": "12px",
                },
            },
        )
        _widget.set(widget)
        return widget.ui(height="600px")

    @reactive.effect
    async def _update_layers():
        widget = _widget()
        gdf_wgs84 = cells_wgs84()
        if widget is None or gdf_wgs84 is None:
            return

        results = results_rv()
        if results is None:
            return

        try:
            layers = []

            # --- Cell polygon layer ---
            color_var = input.color_var()
            if color_var in gdf_wgs84.columns:
                colors = _value_to_rgba(gdf_wgs84[color_var].values)
                gdf_colored = gdf_wgs84.copy()
                gdf_colored["color"] = colors
                gdf_colored["_tooltip_var"] = COLORING_VARS.get(color_var, color_var)
                gdf_colored["_tooltip_val"] = (
                    gdf_colored[color_var].round(2).astype(str)
                )
            else:
                gdf_colored = gdf_wgs84.copy()
                gdf_colored["color"] = [[100, 100, 100, 100]] * len(gdf_colored)
                gdf_colored["_tooltip_var"] = ""
                gdf_colored["_tooltip_val"] = ""

            cells_layer = geojson_layer(
                "cells",
                gdf_colored,
                getFillColor="@@=d.properties.color",
                getLineColor=[60, 60, 60, 100],
                lineWidthMinPixels=1,
            )
            layers.append(cells_layer)

            # --- Trips layer ---
            if input.show_trips():
                traj_df = results.get("trajectories")
                if traj_df is not None and not traj_df.empty:
                    species_cfg = results["config"].get("species", {})
                    species_order = (
                        list(species_cfg.keys()) if species_cfg else ["unknown"]
                    )

                    trips_color = input.trips_color()
                    paths, props = _build_trajectories_data(
                        traj_df,
                        results["cells"],  # pass original CRS for reprojection
                        species_order,
                        color_mode=trips_color,
                    )

                    if paths:
                        total_days = int(traj_df["day_num"].max()) + 1
                        trips_data = format_trips(
                            paths,
                            loop_length=total_days,
                            properties=props,
                        )

                        anim = _anim()
                        speed = anim.speed() if anim else 8.0
                        trail = anim.trail() if anim else 180

                        trip_layer = trips_layer(
                            "fish_trips",
                            trips_data,
                            getColor="@@=d.color",
                            trailLength=trail,
                            fadeTrail=True,
                            widthMinPixels=3,
                            _tripsAnimation={
                                "loopLength": total_days,
                                "speed": speed,
                            },
                        )
                        layers.append(trip_layer)

            await widget.update(session, layers, animate=True)

        except Exception:
            logger.exception("Error updating spatial layers")
            ui.notification_show(
                "Error updating map layers. Check console for details.",
                type="error",
                duration=5,
            )
