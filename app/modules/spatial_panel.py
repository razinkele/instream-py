"""Spatial panel — interactive deck.gl map with cell polygons and fish trips."""

from shiny import module, reactive, render, ui

from shiny_deckgl import (
    MapWidget,
    CARTO_DARK,
    geojson_layer,
)
from simulation import _build_trajectories_data, _value_to_rgba


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
        ui.output_ui("map_container"),
    )


@module.server
def spatial_server(input, output, session, results_rv):
    _widget_holder = reactive.value(None)
    _anim_holder = reactive.value(None)

    @output
    @render.ui
    def map_container():
        results = results_rv()
        if results is None:
            return ui.p("Run a simulation to see results.")

        gdf = results["cells"]
        if gdf.empty:
            return ui.p("No spatial data available.")

        # Compute view state from GeoDataFrame bounds
        gdf_wgs84 = gdf.to_crs(epsg=4326) if gdf.crs is not None else gdf
        bounds = gdf_wgs84.total_bounds  # [minx, miny, maxx, maxy]
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
        extent = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
        zoom = max(1, min(18, int(11 - extent * 50)))

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
        _widget_holder.set(widget)

        # Wire animation controls if trips are available
        if "trajectories" in results and not results["trajectories"].empty:
            from shiny_deckgl.ibm import trips_animation_ui, trips_animation_server

            anim = trips_animation_server("fish_anim", widget=widget, session=session)
            _anim_holder.set(anim)
            return ui.TagList(
                ui.panel_conditional(
                    "input['spatial-show_trips']",
                    trips_animation_ui("fish_anim"),
                ),
                widget.ui(height="600px"),
            )

        return widget.ui(height="600px")

    @reactive.effect
    async def _update_layers():
        widget = _widget_holder()
        results = results_rv()
        if widget is None or results is None:
            return

        gdf = results["cells"]
        if gdf.empty:
            return

        layers = []

        # --- Cell polygon layer ---
        color_var = input.color_var()
        gdf_wgs84 = gdf.to_crs(epsg=4326) if gdf.crs is not None else gdf
        if color_var in gdf_wgs84.columns:
            colors = _value_to_rgba(gdf_wgs84[color_var].values)
            gdf_colored = gdf_wgs84.copy()
            gdf_colored["color"] = colors
            gdf_colored["_tooltip_var"] = COLORING_VARS.get(color_var, color_var)
            gdf_colored["_tooltip_val"] = gdf_colored[color_var].round(2).astype(str)
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
                from shiny_deckgl import trips_layer
                from shiny_deckgl.ibm import format_trips

                species_order = results["config"].get("species", {}).keys()
                species_order = list(species_order) if species_order else ["unknown"]

                trips_color = input.trips_color()
                paths, props = _build_trajectories_data(
                    traj_df,
                    gdf,
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

                    anim = _anim_holder()
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
