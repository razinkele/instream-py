"""Setup Review panel — inspect spatial grid and config layers without simulation.

The MapWidget is created statically in the UI (not dynamically via render.ui)
so the deck.gl JavaScript initializes it on page load. Layers are pushed
via widget.update() when the config changes.
"""

import logging
import math

import geopandas as gpd
import numpy as np
import yaml
from pathlib import Path
from shiny import module, reactive, render, ui

from shiny_deckgl import MapWidget, geojson_layer
from shiny_deckgl.controls import legend_control
from simulation import _value_to_rgba

logger = logging.getLogger(__name__)

BASEMAP_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"

LAYER_CHOICES = {
    "reach": "Reach (color by reach)",
    "frac_spawn": "Spawning Habitat",
    "area": "Cell Area (m²)",
    "num_hiding": "Hiding Places",
    "frac_vel_shelter": "Velocity Shelter",
    "dist_escape": "Distance to Escape (cm)",
}

REACH_COLORS = [
    [31, 119, 180, 180],
    [255, 127, 14, 180],
    [44, 160, 44, 180],
    [214, 39, 40, 180],
    [148, 103, 189, 180],
    [140, 86, 75, 180],
    [227, 119, 194, 180],
    [127, 127, 127, 180],
]


# ---------------------------------------------------------------------------
# UI — MapWidget created statically so JS initializes on page load
# ---------------------------------------------------------------------------

@module.ui
def setup_ui():
    # Create widget at UI build time (not in a render function)
    _widget = MapWidget(
        "setup_map",
        view_state={
            "longitude": 21.1,
            "latitude": 55.7,
            "zoom": 6,
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
            "html": ("<b>{cell_id}</b><br/>Reach: {reach}<br/>"
                     "Area: {area} m²<br/>Spawn: {frac_spawn}"),
            "style": {
                "backgroundColor": "#fff",
                "color": "#333",
                "fontSize": "12px",
                "border": "1px solid #ccc",
            },
        },
    )
    return ui.card(
        ui.card_header("Setup Review"),
        ui.div(
            ui.tags.span("Color by:", style="font-weight:500; margin-right:0.5rem;"),
            ui.div(
                ui.input_select("layer_var", None,
                                choices=LAYER_CHOICES, selected="reach",
                                width="200px"),
                style="display:inline-block; vertical-align:middle;",
            ),
            style="display:flex; align-items:center; margin-bottom:0.5rem;",
        ),
        _widget.ui(height="550px"),
        ui.output_ui("setup_summary"),
        full_screen=True,
    )


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def _build_layer(gdf, layer_var):
    if layer_var == "reach" and "reach" in gdf.columns:
        unique_reaches = list(gdf["reach"].unique())
        colors = [REACH_COLORS[unique_reaches.index(r) % len(REACH_COLORS)]
                  for r in gdf["reach"]]
    elif layer_var in gdf.columns:
        values = gdf[layer_var].fillna(0).values
        colors = _value_to_rgba(values, cmap="YlGnBu", alpha=180)
    else:
        colors = [[100, 100, 100, 120]] * len(gdf)

    geojson = gdf.__geo_interface__
    for i, feat in enumerate(geojson["features"]):
        c = colors[i]
        feat["properties"]["_fill"] = c if isinstance(c, list) else c.tolist()

    return geojson_layer(
        id="setup-cells",
        data=geojson,
        get_fill_color="@@=properties._fill",
        get_line_color=[60, 60, 60, 100],
        get_line_width=1,
        stroked=True,
        filled=True,
        pickable=True,
        auto_highlight=True,
    )


@module.server
def setup_server(input, output, session, config_file_rv, load_btn_rv):
    """Server logic for setup review panel.

    Parameters
    ----------
    config_file_rv : reactive callable
        Returns the currently selected config file path.
    load_btn_rv : reactive callable
        Returns the load button click count (triggers config loading).
    """
    _widget = MapWidget(
        "setup_map",
        view_state={"longitude": 21.1, "latitude": 55.7, "zoom": 6},
        style=BASEMAP_LIGHT,
    )
    _layer_sent = reactive.value(False)
    _loaded_config = reactive.value(None)

    @reactive.effect
    @reactive.event(load_btn_rv)
    def _on_load_click():
        """Store the config path when Load button is clicked."""
        config_path = config_file_rv()
        if config_path:
            _loaded_config.set(config_path)
            _layer_sent.set(False)

    @reactive.calc
    def _load_gdf():
        config_path = _loaded_config()
        if not config_path:
            return None
        try:
            with open(config_path) as f:
                raw = yaml.safe_load(f)
        except Exception:
            return None

        spatial = raw.get("spatial", {})
        mesh_file = spatial.get("mesh_file")
        if not mesh_file:
            return None

        from app import _resolve_data_dir
        data_dir = Path(_resolve_data_dir(config_path))
        mesh_path = data_dir / mesh_file
        if not mesh_path.exists():
            mesh_path = data_dir / Path(mesh_file).name
        if not mesh_path.exists():
            return None

        gdf = gpd.read_file(str(mesh_path))

        gis = spatial.get("gis_properties", {})
        canonical_map = {
            "cell_id": "cell_id",
            "reach_name": "reach",
            "area": "area",
            "frac_spawn": "frac_spawn",
            "num_hiding_places": "num_hiding",
            "frac_vel_shelter": "frac_vel_shelter",
            "dist_escape": "dist_escape",
        }
        col_map = {}
        for key, shp_col in gis.items():
            for actual_col in gdf.columns:
                if actual_col.upper() == shp_col.upper():
                    canonical = canonical_map.get(key)
                    if canonical:
                        col_map[actual_col] = canonical
                    break
        gdf = gdf.rename(columns=col_map)

        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        gdf.attrs["raw_config"] = raw
        return gdf

    @reactive.effect
    async def _update_layer():
        """Push layers when config or color variable changes."""
        gdf = _load_gdf()
        if gdf is None:
            return
        try:
            layer_var = input.layer_var()
            layer = _build_layer(gdf, layer_var)

            # Fly to the data bounds
            bounds = gdf.total_bounds
            center_lon = (bounds[0] + bounds[2]) / 2
            center_lat = (bounds[1] + bounds[3]) / 2
            span = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
            zoom = max(1, min(18, 14 - math.log2(max(span, 0.001))))

            if not _layer_sent():
                await _widget.update(session, [layer], animate=False)
                await _widget.set_view_state(session, {
                    "longitude": center_lon,
                    "latitude": center_lat,
                    "zoom": zoom,
                    "transitionDuration": 1000,
                })
                _layer_sent.set(True)
            else:
                await _widget.partial_update(session, [layer])
        except Exception as e:
            if "SilentException" in type(e).__name__:
                return
            logger.exception("Error updating setup layer")

    @render.ui
    def setup_summary():
        gdf = _load_gdf()
        if gdf is None:
            return ui.div()

        raw = gdf.attrs.get("raw_config", {})
        reaches = raw.get("reaches", {})
        n_cells = len(gdf)
        n_reaches = gdf["reach"].nunique() if "reach" in gdf.columns else 0

        rows = []
        if "reach" in gdf.columns:
            for rname in gdf["reach"].unique():
                rmask = gdf["reach"] == rname
                rc = reaches.get(rname, {})
                n = int(rmask.sum())
                spawn_pct = (gdf.loc[rmask, "frac_spawn"].mean() * 100
                             if "frac_spawn" in gdf.columns else 0)
                rows.append(ui.tags.tr(
                    ui.tags.td(rname),
                    ui.tags.td(str(n)),
                    ui.tags.td(f"{spawn_pct:.0f}%"),
                    ui.tags.td(f"{rc.get('drift_conc', '—')}"),
                    ui.tags.td(f"{rc.get('fish_pred_min', '—')}"),
                ))

        marine = raw.get("marine", {})
        zones = marine.get("zones", [])
        zone_info = ""
        if zones:
            zone_names = [z["name"] for z in zones]
            zone_info = f" + {len(zones)} marine zones ({', '.join(zone_names)})"

        return ui.div(
            ui.h6(f"Grid: {n_cells} cells across {n_reaches} reaches{zone_info}"),
            ui.tags.table(
                {"class": "table table-sm table-striped", "style": "font-size:0.85rem;"},
                ui.tags.thead(ui.tags.tr(
                    ui.tags.th("Reach"),
                    ui.tags.th("Cells"),
                    ui.tags.th("Spawn %"),
                    ui.tags.th("Drift Conc"),
                    ui.tags.th("Fish Pred Min"),
                )),
                ui.tags.tbody(*rows),
            ) if rows else ui.div(),
            style="margin-top:1rem;",
        )
