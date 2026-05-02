"""Setup Review panel — inspect spatial grid and config layers without simulation.

The MapWidget is created statically in the UI (not dynamically via render.ui)
so the deck.gl JavaScript initializes it on page load. Layers are pushed
via widget.update() when the config changes.
"""

import logging

import geopandas as gpd
import yaml
from pathlib import Path
from shiny import module, reactive, render, ui

from shiny_deckgl import MapWidget, geojson_layer
# legend_control removed in v0.56.20 — see spatial_panel.py for rationale
from simulation import _value_to_rgba, discover_osm_sidecars
from modules.spatial_panel import build_osm_overlay_layers, build_osm_overlay_legend_widget

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
    "reach": "Reach",
    "frac_spawn": "Spawning Habitat",
    "area": "Cell Area (m²)",
    "num_hiding": "Hiding Places",
    "frac_vel_shelter": "Velocity Shelter",
    "dist_escape": "Distance to Escape (cm)",
}

# Inline explanatory blurb shown to the right of the Color-by dropdown.
# Keep short — one sentence, ≤90 chars — so it fits the row without wrapping.
LAYER_DESCRIPTIONS = {
    "reach": "Each reach is painted in a distinct colour for topology inspection.",
    "frac_spawn": "Fraction of the cell usable for spawning (0–1). Darker = more spawn habitat.",
    "area": "Cell area in m². Darker cells are larger; used for density normalisation.",
    "num_hiding": "Count of small-fish hiding places per cell. Darker = more escape cover.",
    "frac_vel_shelter": "Fraction of the cell with velocity shelter (0–1). Darker = more shelter.",
    "dist_escape": "Distance (cm) from the cell to the nearest lateral escape point.",
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
    # Tight control row styling. Shiny's input_select wraps the <select>
    # in a .form-group.shiny-input-container with Bootstrap's default
    # margin-bottom:1rem + an empty <label> that still consumes baseline
    # height. Neutralise both so label/select/button sit on a single
    # baseline with no visible whitespace between rows. Scoped to
    # .setup-map-controls so it doesn't bleed into the sidebar.
    _SETUP_CSS = """
    .setup-map-controls {
        padding: 0.3rem 0.75rem 0 0.75rem;
    }
    .setup-map-controls .setup-row {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.2rem;
    }
    .setup-map-controls .setup-row > label {
        width: 72px;
        margin: 0;
        font-weight: 500;
        font-size: 0.9rem;
        flex-shrink: 0;
        line-height: 1.8;
    }
    /* Kill Bootstrap's default form-group bottom margin + hide Shiny's
       empty `label=None` placeholder so the <select> sits flush. */
    .setup-map-controls .form-group,
    .setup-map-controls .shiny-input-container {
        margin: 0 !important;
    }
    .setup-map-controls .shiny-label-null {
        display: none;
    }
    /* Match select height to .btn-sm so they visually align on one line. */
    .setup-map-controls select.form-select {
        height: 31px;
        padding-top: 0.1rem;
        padding-bottom: 0.1rem;
        font-size: 0.9rem;
    }
    .setup-map-controls .btn-sm {
        font-size: 0.85rem;
        padding: 0.2rem 0.6rem;
    }
    .setup-map-controls .layer-description {
        color: #5a6268;
        font-style: italic;
        font-size: 0.82rem;
        margin-left: 0.2rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        min-width: 0;  /* let ellipsis trigger inside flex */
    }
    """

    from modules.spatial_panel import LEGEND_POINTER_EVENTS_FIX
    return ui.card(
        LEGEND_POINTER_EVENTS_FIX,
        ui.tags.style(_SETUP_CSS),
        ui.card_header("Setup Review",
                       style="padding:0.3rem 0.75rem; font-size:0.95rem;"),
        ui.div(
            # Row 1: Config + Load
            ui.div(
                ui.tags.label("Config:"),
                ui.input_select(
                    "setup_config", None,
                    choices=_SETUP_CONFIG_CHOICES,
                    width="260px",
                ),
                ui.input_action_button(
                    "setup_load_btn", "Load",
                    class_="btn btn-sm btn-primary",
                ),
                class_="setup-row",
            ),
            # Row 2: Color by + description
            ui.div(
                ui.tags.label("Color by:"),
                ui.input_select(
                    "layer_var", None,
                    choices=LAYER_CHOICES,
                    selected="reach",
                    width="260px",
                ),
                ui.output_ui("layer_description"),
                class_="setup-row",
            ),
            # OSM source layers are exposed via the in-map "OSM source
            # layers" legend widget (top-left): one toggle per reach, color
            # swatches included.
            class_="setup-map-controls",
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
        gdf.attrs["mesh_path"] = str(mesh_path)
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

            # Build layer list: water background + grid cells + per-reach
            # OSM-source overlay layers (v0.56.17+). The in-map
            # `layer_legend_widget` (top-left) provides per-reach toggles.
            layers = []
            wl = _water_layer()
            if wl is not None:
                layers.append(wl)
            layers.append(layer)
            mesh_path = gdf.attrs.get("mesh_path")
            extra_widgets = None
            if mesh_path:
                sidecars = discover_osm_sidecars(mesh_path)
                layers.extend(build_osm_overlay_layers(sidecars, visible=True))
                osm_legend = build_osm_overlay_legend_widget(sidecars, placement="top-left")
                if osm_legend is not None:
                    extra_widgets = [osm_legend]

            await _widget.update(session, layers, animate=False, widgets=extra_widgets)

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
    def layer_description():
        """Inline explanatory blurb right of the Color-by dropdown.

        Styled via `.setup-map-controls .layer-description` CSS in the
        scoped block (see setup_ui) so it ellipses + italicises without
        inline style. Reads input.layer_var() reactively so the text
        updates instantly when the user switches the dropdown.
        """
        key = input.layer_var() or "reach"
        text = LAYER_DESCRIPTIONS.get(key, "")
        return ui.tags.span(text, class_="layer-description")

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
