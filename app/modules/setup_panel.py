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

# v0.41.3 (2026-04-21): removed the hand-traced Baltic-specific
# `app/data/water_polygons.geojson` overlay. It was a pre-v0.30.1 v1
# fallback (Curonian Lagoon trapezoid + 3 Nemunas branches + Baltic Sea
# rectangle, ~2 KB) that loaded on EVERY setup_panel view regardless of
# the selected config. For Baltic fixtures it superimposed obsolete
# geometry on the real OSM-sourced reach polygons; for California
# (example_a), Torne (AU 1), Byske, and Mörrum it appeared far off-map
# creating visual clutter. The real per-fixture shapefile already
# represents water geometry correctly.


def _water_layer():
    """Placeholder retained so callers don't break; always returns None."""
    return None

logger = logging.getLogger(__name__)

BASEMAP_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"


def _discover_configs() -> dict[str, str]:
    """Return {full_path: stem} for every runnable example-*.yaml config.

    Duplicates app.py's CONFIG_CHOICES logic so the Setup panel can offer its
    own picker without a circular import. Filter matches `app.py`: only files
    whose stem starts with ``example`` (excludes species-only configs).
    """
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "configs",
        Path(__file__).resolve().parent.parent / "configs",
    ]
    for d in candidates:
        if d.exists():
            return {
                str(p): p.stem
                for p in sorted(d.glob("*.yaml"))
                if p.stem.startswith("example")
            }
    return {}


_SETUP_CONFIG_CHOICES = _discover_configs()

LAYER_CHOICES = {
    "reach": "Reach (color by reach)",
    "frac_spawn": "Spawning Habitat",
    "area": "Cell Area (m²)",
    "num_hiding": "Hiding Places",
    "frac_vel_shelter": "Velocity Shelter",
    "dist_escape": "Distance to Escape (cm)",
}

REACH_COLORS = [
    [31, 119, 180, 180],    # blue
    [255, 127, 14, 180],    # orange
    [44, 160, 44, 180],     # green
    [214, 39, 40, 180],     # red
    [148, 103, 189, 180],   # purple
    [140, 86, 75, 180],     # brown
    [227, 119, 194, 180],   # pink
    [127, 127, 127, 180],   # grey
    [188, 189, 34, 180],    # olive (added for 9-reach example_baltic)
    [23, 190, 207, 180],    # cyan
    [174, 199, 232, 180],   # light-blue
    [255, 152, 150, 180],   # salmon
]


# ---------------------------------------------------------------------------
# UI — MapWidget created statically so JS initializes on page load
# ---------------------------------------------------------------------------

@module.ui
def setup_ui():
    # Create widget at UI build time (not in a render function).
    # Initial view is a neutral global position; the first config load
    # will call set_view_state to fly to the loaded fixture's bounds.
    _widget = MapWidget(
        "setup_map",
        view_state={
            "longitude": 0.0,
            "latitude": 30.0,
            "zoom": 1.5,
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
        # Inline config picker — mirrors the sidebar Configuration selector
        # so users can load a different config without hunting for the
        # sidebar (which can be collapsed). Loading here sets the Setup
        # panel's local state *and* updates the sidebar dropdown so the
        # Run Simulation button picks up the same choice.
        ui.div(
            ui.tags.span("Config:", style="font-weight:500; margin-right:0.5rem;"),
            ui.div(
                ui.input_select(
                    "setup_config", None,
                    choices=_SETUP_CONFIG_CHOICES,
                    width="300px",
                ),
                style="display:inline-block; vertical-align:middle;",
            ),
            ui.input_action_button(
                "setup_load_btn", "Load",
                class_="btn btn-sm btn-primary",
                style="margin-left:0.5rem;",
            ),
            style="display:flex; align-items:center; margin-bottom:0.5rem; "
                  "gap:0.3rem;",
        ),
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

    # Bake colors directly into each feature as a flat array
    geojson = gdf.__geo_interface__
    for i, feat in enumerate(geojson["features"]):
        c = colors[i]
        feat["properties"]["_fill"] = c if isinstance(c, list) else c.tolist()

    # Stable layer id so recolors via layer_var changes patch data in-place.
    # Kwargs MUST be camelCase — geojson_layer passes them through to deck.gl
    # verbatim, and deck.gl's JS side expects `getFillColor` not
    # `get_fill_color` (silently ignores unrecognized keys). Matches
    # spatial_panel's working pattern.
    return geojson_layer(
        "setup-cells",
        geojson,
        getFillColor="@@=d.properties._fill",
        getLineColor=[60, 60, 60, 100],
        getLineWidth=1,
        stroked=True,
        filled=True,
        pickable=True,
        autoHighlight=True,
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
    # Start centered on a neutral global view; the first config load will
    # re-center on that config's bounds.
    _widget = MapWidget(
        "setup_map",
        view_state={"longitude": 0.0, "latitude": 30.0, "zoom": 1.5},
        style=BASEMAP_LIGHT,
    )
    # Track which config the map is currently centered on. When this
    # differs from `_loaded_config`, `_update_layer` re-fits view bounds.
    # Color-variable changes never reset this, so layer recoloring alone
    # doesn't trigger a re-fit.
    _centered_for_config = reactive.value(None)
    _loaded_config = reactive.value(None)

    @reactive.effect
    @reactive.event(load_btn_rv)
    def _on_load_click():
        """Store the config path when the sidebar's Load Config button is clicked."""
        config_path = config_file_rv()
        if config_path:
            _loaded_config.set(config_path)

    @reactive.effect
    @reactive.event(input.setup_load_btn)
    def _on_setup_load_click():
        """Allow loading a config directly from the Setup panel picker.

        Mirrors the selection into the sidebar's `config_file` widget so the
        Run Simulation button picks up the same choice. Uses the root session
        because `config_file` is defined in the main app namespace, not the
        `setup` module namespace.
        """
        config_path = input.setup_config()
        if not config_path:
            return
        _loaded_config.set(config_path)
        try:
            # session here is the module session; its `parent` is the root
            # ShinySession whose inputs include the sidebar's `config_file`.
            root = getattr(session, "parent", None) or session
            ui.update_select("config_file", selected=config_path, session=root)
        except Exception as exc:  # pragma: no cover — defensive for API drift
            logger.debug("Could not sync sidebar config_file: %s", exc)

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
        mesh_name = Path(mesh_file).name
        candidates = [
            data_dir / mesh_file,             # exact path from config
            data_dir / mesh_name,             # flat fallback
            data_dir / "Shapefile" / mesh_name,  # server layout (ExampleA)
        ]
        # Final fallback: search anywhere under data_dir
        mesh_path = next((p for p in candidates if p.exists()), None)
        if mesh_path is None:
            matches = list(data_dir.rglob(mesh_name))
            if matches:
                mesh_path = matches[0]
        if mesh_path is None:
            logger.warning(
                "Could not find mesh %r under %s; tried: %s",
                mesh_name, data_dir, [str(p) for p in candidates],
            )
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
        """Push layers when config or color variable changes. Always
        re-centers the map when the loaded config changes (not when the
        color variable changes)."""
        gdf = _load_gdf()
        if gdf is None:
            return
        try:
            layer_var = input.layer_var()
            layer = _build_layer(gdf, layer_var)

            # Build layer list: water background + grid cells
            layers = []
            wl = _water_layer()
            if wl is not None:
                layers.append(wl)
            layers.append(layer)

            await _widget.update(session, layers, animate=False)

            # Re-fit view bounds ONLY when the loaded config changed.
            # Recoloring via `layer_var` leaves `_loaded_config` unchanged,
            # so the view stays put.
            current_config = _loaded_config()
            if _centered_for_config() != current_config:
                # gdf.total_bounds: (minx, miny, maxx, maxy)
                minx, miny, maxx, maxy = gdf.total_bounds
                await _widget.fit_bounds(
                    session,
                    bounds=[[minx, miny], [maxx, maxy]],
                    padding=50,
                    duration=1000,
                )
                _centered_for_config.set(current_config)
        except Exception as e:
            if "SilentException" in type(e).__name__:
                return
            logger.exception("Error updating setup layer")

    @render.ui
    def setup_summary():
        gdf = _load_gdf()
        if gdf is None:
            return ui.div(
                ui.p(
                    ui.tags.strong("No configuration loaded. "),
                    "Pick one above (or in the sidebar Configuration selector) "
                    "and click Load to inspect its reaches, cells, and marine zones.",
                    style="color:#555; font-size:0.9rem; margin-top:0.4rem;",
                ),
            )

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
