"""Edit Model panel — load an existing fixture, inspect reaches, rename them.

MVP scope (v0.45.3):
  * Pick an existing fixture from the configs/ directory.
  * Show its reach polygons on a deck.gl map, color-coded by reach.
  * Show a table summarising reach names, cell counts, and area.
  * Rename a reach (text input) and save back to the fixture's shapefile
    and YAML config.

Future v0.46+:
  * Merge / split reaches by clicking on the map
  * Adjust reach boundaries (lasso select)
  * Regenerate cells with a new cell size
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import geopandas as gpd
import yaml
from shapely.geometry import shape
from shiny import module, reactive, render, ui
from shiny_deckgl import MapWidget, geojson_layer

from simulation import discover_osm_sidecars
from modules.spatial_panel import build_osm_overlay_layers, build_osm_overlay_legend_widget

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Fixture discovery
# -----------------------------------------------------------------------------

def _project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in (here.parent, here.parent.parent, here.parent.parent.parent):
        if (parent / "configs").exists():
            return parent
    return here.parent.parent.parent  # best-effort fallback


def _fixtures_root(root: Path) -> Path:
    """data/fixtures/ on the server, tests/fixtures/ in dev."""
    if (root / "data" / "fixtures").exists():
        return root / "data" / "fixtures"
    return root / "tests" / "fixtures"


def _pick_main_shapefile(shp_dir: Path) -> Path | None:
    """Find the fixture's main cell shapefile in a directory.

    v0.56.4 introduced ``*-osm-{polygons,centerlines}.shp`` sidecar
    shapefiles next to the main mesh shapefile. A naive
    ``next(glob('*.shp'))`` picks one of those sidecars on filesystems
    that return the dash-prefixed names first, breaking Edit Model.
    Filter sidecars out by the ``-osm-`` substring; pick the largest
    remaining shapefile by file size (the main mesh is always
    significantly larger than any sidecar).
    """
    candidates = [
        p for p in shp_dir.glob("*.shp")
        if "-osm-" not in p.stem
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)


def discover_fixtures() -> list[str]:
    """Return short_name list for fixtures with both a config + shapefile."""
    root = _project_root()
    fix_root = _fixtures_root(root)
    if not fix_root.exists():
        return []
    available = []
    for cfg_path in sorted((root / "configs").glob("example_*.yaml")):
        short_name = cfg_path.stem
        fix_dir = fix_root / short_name
        if not fix_dir.exists():
            continue
        shp_dir = fix_dir / "Shapefile"
        if not shp_dir.exists():
            continue
        if _pick_main_shapefile(shp_dir) is None:
            continue
        available.append(short_name)
    return available


def _load_fixture(short_name: str):
    """Return (config_dict, cells_gdf, config_path, shapefile_path)."""
    root = _project_root()
    cfg_path = root / "configs" / f"{short_name}.yaml"
    fix_dir = _fixtures_root(root) / short_name
    shp = _pick_main_shapefile(fix_dir / "Shapefile")
    if shp is None:
        raise FileNotFoundError(f"no main mesh shapefile in {fix_dir}/Shapefile")
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cells = gpd.read_file(shp)
    if cells.crs is None:
        cells = cells.set_crs("EPSG:4326")
    elif str(cells.crs) != "EPSG:4326":
        cells = cells.to_crs("EPSG:4326")
    return cfg, cells, cfg_path, shp


# Distinct, accessible color palette
PALETTE_RGB = [
    [31, 119, 180],   # blue
    [255, 127, 14],   # orange
    [44, 160, 44],    # green
    [214, 39, 40],    # red
    [148, 103, 189],  # purple
    [140, 86, 75],    # brown
    [227, 119, 194],  # pink
    [127, 127, 127],  # grey
    [188, 189, 34],   # olive
    [23, 190, 207],   # cyan
]


_HIGHLIGHT_LINE = [255, 215, 0, 255]   # gold outline for selected reach
_DEFAULT_LINE = [40, 40, 40, 200]      # dark grey for un-selected
_HIGHLIGHT_FILL_ALPHA = 230            # selected → fully opaque
_DEFAULT_FILL_ALPHA = 180              # un-selected → semi-transparent


def _build_reach_geojson(
    cells: gpd.GeoDataFrame,
    selected: str | None = None,
):
    """Render cells as GeoJSON with per-feature `_fill`, `_line`, `_line_w`.

    When ``selected`` matches a reach name, that reach's cells get a
    bolder gold outline + fully-opaque fill so the selection is
    visually obvious on the map. v0.57.4.
    """
    reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
    reach_names = sorted(cells[reach_col].unique())
    base_color = {
        name: PALETTE_RGB[i % len(PALETTE_RGB)]
        for i, name in enumerate(reach_names)
    }

    def _fill(reach: str) -> list[int]:
        c = base_color[reach]
        a = _HIGHLIGHT_FILL_ALPHA if reach == selected else _DEFAULT_FILL_ALPHA
        return [c[0], c[1], c[2], a]

    def _line(reach: str) -> list[int]:
        return _HIGHLIGHT_LINE if reach == selected else _DEFAULT_LINE

    def _line_w(reach: str) -> int:
        return 3 if reach == selected else 1

    cells = cells.copy()
    cells["_fill"] = cells[reach_col].map(_fill)
    cells["_line"] = cells[reach_col].map(_line)
    cells["_line_w"] = cells[reach_col].map(_line_w)
    geojson = json.loads(cells.to_json())
    legend_entries = [
        (name, base_color[name] + [_DEFAULT_FILL_ALPHA])
        for name in reach_names
    ]
    return geojson, legend_entries


# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------

@module.ui
def edit_model_ui():
    fixtures = discover_fixtures()
    _widget = MapWidget(
        "edit_map",
        view_state={"longitude": 22.0, "latitude": 60.0, "zoom": 5},
        controls=[
            {"type": "navigation", "position": "top-right"},
            {"type": "fullscreen", "position": "top-right"},
        ],
    )
    from modules.spatial_panel import LEGEND_POINTER_EVENTS_FIX
    # v0.57.3 UX: cursor styling + active-mode banner styling, plus a JS
    # bridge that toggles `body[data-em-mode=...]` so the cursor rule below
    # actually targets the deck.gl canvas. Without the body-class indirection
    # we cannot scope cursor styles to "draw mode active" without colliding
    # with mapbox-gl-draw's own internal cursor handling.
    EM_UX_STYLE = ui.tags.style("""
    .em-mode-banner { padding: 10px 14px; margin: 0 0 8px 0; border-radius: 4px;
                      display: flex; align-items: center; justify-content: space-between;
                      gap: 12px; font-size: 13px; font-weight: 500;
                      box-shadow: 0 1px 2px rgba(0,0,0,.06); }
    .em-mode-banner.merge-a, .em-mode-banner.merge-b {
        background: #fff3cd; color: #664d03; border: 1px solid #ffc107; }
    .em-mode-banner.split  { background: #cff4fc; color: #055160; border: 1px solid #0dcaf0; }
    .em-mode-banner.lasso  { background: #d1e7dd; color: #0f5132; border: 1px solid #198754; }
    .em-mode-banner .em-mode-text { flex: 1; }
    .em-mode-banner .em-mode-text strong { font-weight: 600; }
    .em-mode-banner .btn { font-size: 12px; padding: 3px 10px; flex-shrink: 0; }
    /* Cursor override on the deck.gl/mapbox canvas while a draw or click
       mode is active. The !important is needed because mapbox-gl and
       deckgl set their own cursors on these canvases. Targeting
       'canvas' broadly inside the data-em-mode'd body covers both
       deck-gl-overlay-canvas and mapbox-gl-canvas. */
    body[data-em-mode="split"] canvas,
    body[data-em-mode="lasso"] canvas { cursor: crosshair !important; }
    body[data-em-mode="merge-a"] canvas,
    body[data-em-mode="merge-b"] canvas { cursor: pointer !important; }
    /* v0.57.4 unified reach selector: color buttons below the map.
       Each chip is the reach color; .active gets a heavier outline. */
    .em-reach-btn-row { display: flex; flex-wrap: wrap; gap: 6px;
                        padding: 8px 0; align-items: center; }
    .em-reach-btn-row .em-label { color: #555; font-size: 12px;
                                   margin-right: 4px; font-weight: 500; }
    .em-reach-btn { padding: 4px 12px; border-radius: 4px;
                    border: 1px solid rgba(0,0,0,.2); cursor: pointer;
                    color: #fff; font-size: 12px; font-weight: 500;
                    text-shadow: 0 0 2px rgba(0,0,0,.5);
                    transition: transform .12s, box-shadow .12s; }
    .em-reach-btn:hover { transform: translateY(-1px);
                          box-shadow: 0 2px 4px rgba(0,0,0,.2); }
    .em-reach-btn.active { outline: 3px solid #ffd700;
                           outline-offset: 1px;
                           box-shadow: 0 0 0 1px rgba(0,0,0,.4); }
    .em-reach-btn.clear { background: #f0f0f0; color: #555;
                          text-shadow: none; }
    """)
    EM_MODE_BRIDGE = ui.tags.script("""
    (function(){
        if (window.__emModeBridgeInstalled) return;
        window.__emModeBridgeInstalled = true;
        Shiny.addCustomMessageHandler('em_set_mode', function(msg){
            if (msg && msg.mode) {
                document.body.setAttribute('data-em-mode', msg.mode);
            } else {
                document.body.removeAttribute('data-em-mode');
            }
        });
    })();
    """)
    return ui.div(
        LEGEND_POINTER_EVENTS_FIX,
        EM_UX_STYLE,
        EM_MODE_BRIDGE,
        ui.row(
            ui.column(
                4,
                ui.h4("Edit Model"),
                ui.input_select(
                    "fixture",
                    "Fixture",
                    choices=fixtures or ["(none — generate one first)"],
                    selected=fixtures[0] if fixtures else None,
                ),
                # v0.57.4: unified reach selector. Single source of truth
                # for "which reach is the user editing". The dropdown here
                # and the colour-button row below the map both drive the
                # same `selected_reach` reactive value; the map highlights
                # the selected reach with a gold outline.
                ui.input_select(
                    "select_reach",
                    "Selected reach",
                    choices=["(none)"],
                    selected="(none)",
                ),
                ui.row(
                    ui.column(6, ui.input_action_button(
                        "undo", "↶ Undo", class_="btn-secondary btn-sm",
                    )),
                    ui.column(6, ui.input_action_button(
                        "redo", "↷ Redo", class_="btn-secondary btn-sm",
                    )),
                ),
                ui.output_ui("reach_table"),
                ui.hr(),
                ui.h5("Rename selected reach"),
                ui.input_text("rename_new", "New name", placeholder="e.g. Estuary"),
                ui.input_action_button(
                    "do_rename", "Apply rename + save", class_="btn-primary",
                ),
                ui.hr(),
                ui.h5("Merge two reaches"),
                ui.input_action_button(
                    "merge_start", "Start merge: click reach A", class_="btn-warning",
                ),
                ui.output_ui("merge_status"),
                ui.input_text("merge_new_name", "New combined name", placeholder="e.g. Estuary"),
                ui.input_action_button(
                    "merge_apply", "Apply merge", class_="btn-primary",
                ),
                ui.hr(),
                ui.h5("Split selected reach by drawing a line"),
                ui.input_text(
                    "split_north_name", "Name for north side",
                    placeholder="e.g. Upper-N",
                ),
                ui.input_text(
                    "split_south_name", "Name for south side",
                    placeholder="e.g. Upper-S",
                ),
                ui.input_action_button(
                    "split_start", "Start drawing line", class_="btn-warning",
                ),
                ui.input_action_button(
                    "split_apply", "Apply split", class_="btn-primary",
                ),
                ui.hr(),
                ui.h5("Lasso-select cells → reassign"),
                ui.input_text(
                    "lasso_new_name", "Assign selected cells to reach",
                    placeholder="e.g. Side-Channel",
                ),
                ui.input_action_button(
                    "lasso_start", "Start drawing polygon", class_="btn-warning",
                ),
                ui.input_action_button(
                    "lasso_apply", "Apply selection", class_="btn-primary",
                ),
                ui.hr(),
                ui.h5("Regenerate cell grid"),
                ui.input_numeric(
                    "regen_cell_size", "Cell size (metres)",
                    value=80.0, min=10.0, max=2000.0, step=10.0,
                ),
                ui.input_action_button(
                    "regen_apply", "Regenerate + save", class_="btn-danger",
                ),
                # OSM source layers exposed via the in-map "OSM source layers"
                # legend widget (top-left): per-reach toggles + color swatches.
                ui.output_ui("save_status"),
            ),
            ui.column(
                8,
                ui.output_ui("active_mode_banner"),
                _widget.ui(height="600px"),
                ui.output_ui("reach_button_row"),
            ),
        ),
    )


# -----------------------------------------------------------------------------
# Pure geometry helpers (v0.57.0 fix #1) — split apart so the completion
# effects can call them without Shiny session in scope. Tested directly
# in tests/test_edit_model_panel_draw_handoff.py.
# -----------------------------------------------------------------------------

def _apply_split_to_cells(
    cells: gpd.GeoDataFrame,
    *,
    target_reach: str,
    line,                          # shapely LineString
    north_name: str,
    south_name: str,
) -> tuple[gpd.GeoDataFrame, int, int]:
    """Classify each cell of `target_reach` as north or south of `line`
    and return (mutated_cells, n_north, n_south).

    Side classification mirrors the v0.46.0 sign-of-cross-product logic
    in _split_apply (extracted verbatim so the completion effect calls
    this helper rather than inlining the math).
    """
    out = cells.copy()
    reach_col = "REACH_NAME" if "REACH_NAME" in out.columns else "reach_name"
    target_mask = out[reach_col] == target_reach
    if not target_mask.any():
        return out, 0, 0
    L = line.length
    eps = max(L * 1e-6, 1e-9)
    sides: list[str] = []
    for geom in out.loc[target_mask].geometry:
        c = geom.centroid
        nearest_dist = line.project(c)
        nearest_pt = line.interpolate(nearest_dist)
        if nearest_dist + eps <= L:
            tangent_pt = line.interpolate(nearest_dist + eps)
            base = nearest_pt
        else:
            prev_pt = line.interpolate(max(nearest_dist - eps, 0.0))
            base = prev_pt
            tangent_pt = nearest_pt
        dx = tangent_pt.x - base.x
        dy = tangent_pt.y - base.y
        cross = (c.x - base.x) * dy - (c.y - base.y) * dx
        sides.append("north" if cross >= 0 else "south")
    out.loc[target_mask, reach_col] = [
        north_name if sd == "north" else south_name for sd in sides
    ]
    n_north = sum(1 for sd in sides if sd == "north")
    return out, n_north, len(sides) - n_north


def _apply_lasso_to_cells(
    cells: gpd.GeoDataFrame,
    *,
    lasso,                         # shapely Polygon | MultiPolygon
    new_name: str,
) -> tuple[gpd.GeoDataFrame, int]:
    """Reassign every cell whose centroid is inside `lasso` to `new_name`.

    Returns (mutated_cells, n_inside).
    """
    out = cells.copy()
    reach_col = "REACH_NAME" if "REACH_NAME" in out.columns else "reach_name"
    inside_mask = out.geometry.centroid.within(lasso)
    n_inside = int(inside_mask.sum())
    out.loc[inside_mask, reach_col] = new_name
    return out, n_inside


# -----------------------------------------------------------------------------
# Server
# -----------------------------------------------------------------------------

@module.server
def edit_model_server(input, output, session):
    # Re-construct the widget (must match the UI by the same id)
    _widget = MapWidget(
        "edit_map",
        view_state={"longitude": 22.0, "latitude": 60.0, "zoom": 5},
    )

    state = reactive.value({
        "short_name": None,
        "cfg": None,
        "cfg_path": None,
        "cells": None,
        "shp_path": None,
    })
    last_save = reactive.value("")

    # Merge state machine: idle -> pick_a -> pick_b -> ready
    merge_state = reactive.value({"phase": "idle", "reach_a": None})

    # Split state: idle -> drawing
    split_state = reactive.value({"phase": "idle"})
    # v0.57.0 fix #1: pending split operation captured by the trigger
    # effect; consumed by the completion effect when drawn features
    # arrive. None means "no pending op".
    split_pending = reactive.value(None)
    lasso_pending = reactive.value(None)

    # Undo/redo: list of {cells, cfg} snapshots, capped at 10
    history_undo = reactive.value([])
    history_redo = reactive.value([])

    # v0.57.3 UX: single source of truth for "what is the user doing right
    # now". Values: None | "merge-a" | "merge-b" | "split" | "lasso".
    # Drives both the visible banner and the body[data-em-mode] cursor CSS.
    active_mode = reactive.value(None)
    # Track which fixture's bounds we last fitted on, so we don't re-zoom
    # on every state mutation (rename, split apply, etc.) — only on
    # fixture change.
    last_fitted_fixture = reactive.value(None)
    # v0.57.4 UX: unified reach selector. Drives the map highlight and
    # serves as the default target for rename/split. Set by either the
    # `select_reach` dropdown or the colour buttons below the map.
    selected_reach = reactive.value(None)

    def _push_undo_snapshot():
        s = state()
        if s["cells"] is None:
            return
        snap = {"cells": s["cells"].copy(), "cfg": dict(s["cfg"])}
        stack = list(history_undo())
        stack.append(snap)
        if len(stack) > 10:
            stack = stack[-10:]
        history_undo.set(stack)
        # Any new edit clears the redo stack
        history_redo.set([])

    @reactive.effect
    def _load_on_select():
        short_name = input.fixture()
        if not short_name or short_name.startswith("("):
            return
        try:
            cfg, cells, cfg_path, shp_path = _load_fixture(short_name)
        except Exception as exc:
            logger.exception("load failed for %s", short_name)
            last_save.set(f"❌ load failed: {exc}")
            return
        state.set({
            "short_name": short_name,
            "cfg": cfg,
            "cfg_path": cfg_path,
            "cells": cells,
            "shp_path": shp_path,
        })
        # v0.57.4: clear selection on fixture switch (the previously-
        # selected reach may not exist in the new fixture).
        selected_reach.set(None)
        last_save.set(f"loaded {short_name} ({len(cells)} cells)")

    @reactive.effect
    def _populate_reach_dropdowns():
        s = state()
        if s["cells"] is None:
            return
        reach_col = "REACH_NAME" if "REACH_NAME" in s["cells"].columns else "reach_name"
        names = sorted(s["cells"][reach_col].unique())
        # v0.57.4: single unified `select_reach` dropdown. The "(none)"
        # sentinel is the default — keeps no reach selected on first load,
        # so the user can either pick from the dropdown or click a
        # colour button below the map.
        choices = ["(none)"] + names
        cur = selected_reach()
        # If the previously-selected reach still exists, keep it
        # selected; otherwise drop back to "(none)".
        sel = cur if cur in names else "(none)"
        ui.update_select("select_reach", choices=choices, selected=sel)

    @reactive.effect
    @reactive.event(input.select_reach)
    def _on_select_reach_dropdown():
        # Sync dropdown → reactive value. The "(none)" sentinel maps to
        # None so downstream consumers can short-circuit cleanly.
        v = (input.select_reach() or "").strip()
        selected_reach.set(None if not v or v == "(none)" else v)

    @reactive.effect
    @reactive.event(input.reach_button_click)
    def _on_reach_button_click():
        # Sync colour-button click → reactive value. Clicking the same
        # reach again deselects (toggle), so users can clear via the
        # button row without going to the dropdown.
        v = (input.reach_button_click() or "").strip()
        if not v:
            selected_reach.set(None)
            return
        cur = selected_reach()
        selected_reach.set(None if cur == v else v)

    @reactive.effect
    def _selected_reach_to_dropdown():
        # Keep the dropdown in sync when a button click changes the
        # selection. Without this, dropdown and buttons can drift.
        cur = selected_reach()
        s = state()
        if s["cells"] is None:
            return
        target = cur if cur is not None else "(none)"
        try:
            ui.update_select("select_reach", selected=target)
        except Exception:
            pass

    @reactive.effect
    async def _update_map():
        s = state()
        if s["cells"] is None:
            return
        geojson, _ = _build_reach_geojson(s["cells"], selected=selected_reach())
        layer = geojson_layer(
            id="reaches",
            data=geojson,
            getFillColor="@@=properties._fill",
            getLineColor="@@=properties._line",
            getLineWidth="@@=properties._line_w",
            stroked=True,
            filled=True,
            pickable=True,
            lineWidthMinPixels=1,
        )

        # v0.56.17: per-reach OSM-source overlay layers + in-map legend
        # widget (top-left) drives per-reach visibility toggles.
        layers = [layer]
        extra_widgets = None
        shp_path = s.get("shp_path")
        if shp_path:
            sidecars = discover_osm_sidecars(shp_path)
            layers.extend(build_osm_overlay_layers(sidecars, visible=True))
            osm_legend = build_osm_overlay_legend_widget(sidecars, placement="top-left")
            if osm_legend is not None:
                extra_widgets = [osm_legend]

        try:
            await _widget.update(session, layers, widgets=extra_widgets)
        except Exception:
            logger.exception("map update failed")

        # v0.57.3 UX: auto-zoom to the loaded fixture's bounds. Only fire
        # when the fixture identity changes — otherwise every rename /
        # split / lasso mutation would reset the map view, fighting any
        # manual pan/zoom the user has done. fit_bounds payload is
        # `[[sw_lng, sw_lat], [ne_lng, ne_lat]]` per shiny_deckgl's
        # MapWidget.fit_bounds contract.
        short_name = s.get("short_name")
        if short_name and short_name != last_fitted_fixture():
            try:
                bounds_arr = s["cells"].total_bounds  # [minx, miny, maxx, maxy]
                bounds = [
                    [float(bounds_arr[0]), float(bounds_arr[1])],
                    [float(bounds_arr[2]), float(bounds_arr[3])],
                ]
                await _widget.fit_bounds(
                    session, bounds, padding=50, max_zoom=14, duration=600,
                )
                last_fitted_fixture.set(short_name)
            except Exception:
                logger.exception("fit_bounds failed for %s", short_name)

    # ------------------------------------------------------------------
    # v0.57.3 UX: active-mode banner + JS body-class bridge
    # ------------------------------------------------------------------
    _MODE_LABELS = {
        "merge-a": (
            "MERGE — click any cell of <strong>reach A</strong> on the map.",
            "Cancel merge",
        ),
        "merge-b": (
            "MERGE — click any cell of <strong>reach B</strong> on the map.",
            "Cancel merge",
        ),
        "split": (
            "SPLIT — draw a single <strong>line</strong> across the target reach, then click <strong>Apply split</strong>.",
            "Cancel split",
        ),
        "lasso": (
            "LASSO — draw a <strong>polygon</strong> enclosing the cells to reassign, then click <strong>Apply selection</strong>.",
            "Cancel selection",
        ),
    }

    @output
    @render.ui
    def active_mode_banner():
        mode = active_mode()
        if mode is None or mode not in _MODE_LABELS:
            return ui.HTML("")
        text_html, cancel_label = _MODE_LABELS[mode]
        return ui.div(
            {"class": f"em-mode-banner {mode}"},
            ui.div({"class": "em-mode-text"}, ui.HTML(text_html)),
            ui.input_action_button(
                "mode_cancel", cancel_label, class_="btn btn-sm btn-light",
            ),
        )

    # v0.57.4 unified reach selector — colour buttons below the map.
    # Clicking a button drives the same `selected_reach` reactive value
    # as the dropdown above, and toggles selection on second click.
    @output
    @render.ui
    def reach_button_row():
        s = state()
        if s["cells"] is None:
            return ui.HTML("")
        cells = s["cells"]
        reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
        names = sorted(cells[reach_col].unique())
        sel = selected_reach()
        # Each click pushes the reach name as a string into a single
        # shared input. The Shiny module namespacing means we must use
        # `session.ns(...)` to compute the wire-level input id that the
        # JS-side `Shiny.setInputValue` should target.
        btn_input_id = session.ns("reach_button_click")
        chips = []
        for i, name in enumerate(names):
            c = PALETTE_RGB[i % len(PALETTE_RGB)]
            active = (name == sel)
            # Escape backticks/quotes in name for the JS string literal.
            # Reach names in this codebase are alphanumeric, but defend.
            safe_name = name.replace("\\", "\\\\").replace("'", "\\'")
            chips.append(ui.tags.button(
                name,
                {
                    "type": "button",
                    "class": "em-reach-btn" + (" active" if active else ""),
                    "style": (
                        f"background:rgb({c[0]},{c[1]},{c[2]});"
                    ),
                    "onclick": (
                        f"Shiny.setInputValue("
                        f"'{btn_input_id}', '{safe_name}', "
                        f"{{priority: 'event'}});"
                    ),
                    "title": f"Click to select '{name}' (click again to deselect)",
                },
            ))
        # Trailing "Clear" chip for one-click deselection.
        clear_chip = ui.tags.button(
            "× clear",
            {
                "type": "button",
                "class": "em-reach-btn clear",
                "onclick": (
                    f"Shiny.setInputValue("
                    f"'{btn_input_id}', '', {{priority: 'event'}});"
                ),
                "title": "Deselect the current reach",
            },
        )
        label_text = (
            f"Selected: {sel}" if sel is not None
            else "No reach selected — pick one to edit:"
        )
        return ui.div(
            {"class": "em-reach-btn-row"},
            ui.span({"class": "em-label"}, label_text),
            *chips,
            clear_chip,
        )

    @reactive.effect
    async def _propagate_mode_to_js():
        # Push the current mode (or None) to the body[data-em-mode]
        # attribute so the cursor CSS can scope itself.
        mode = active_mode()
        try:
            await session.send_custom_message(
                "em_set_mode", {"mode": mode if mode else None},
            )
        except Exception:
            logger.exception("em_set_mode dispatch failed")

    @reactive.effect
    @reactive.event(input.mode_cancel)
    async def _on_mode_cancel():
        # Clear all pending op state + tear down any active draw layer.
        merge_state.set({"phase": "idle", "reach_a": None})
        split_state.set({"phase": "idle"})
        split_pending.set(None)
        lasso_pending.set(None)
        active_mode.set(None)
        try:
            await _widget.delete_drawn_features(session)
            await _widget.disable_draw(session)
        except Exception:
            pass
        last_save.set("✓ cancelled — no edits applied")

    @output
    @render.ui
    def reach_table():
        s = state()
        if s["cells"] is None:
            return ui.p("Load a fixture to inspect reaches.")
        cells = s["cells"]
        reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
        try:
            cells_proj = cells.to_crs("EPSG:3035")
        except Exception:
            cells_proj = cells
        rows = []
        for name, grp in cells.groupby(reach_col):
            area_km2 = float(cells_proj.loc[grp.index].geometry.area.sum() / 1e6)
            rows.append((name, len(grp), area_km2))
        rows.sort(key=lambda r: r[0])
        return ui.tags.table(
            {"class": "table table-sm"},
            ui.tags.thead(ui.tags.tr(
                ui.tags.th("Reach"), ui.tags.th("Cells"), ui.tags.th("Area (km²)")
            )),
            ui.tags.tbody(*[
                ui.tags.tr(
                    ui.tags.td(name),
                    ui.tags.td(f"{n}"),
                    ui.tags.td(f"{a:.2f}"),
                )
                for name, n, a in rows
            ]),
        )

    @output
    @render.ui
    def legend():
        s = state()
        if s["cells"] is None:
            return ui.HTML("")
        _, legend_entries = _build_reach_geojson(s["cells"])
        chips = [
            ui.tags.span(
                {
                    "style": (
                        f"display:inline-block; padding:2px 8px; margin-right:6px;"
                        f" border-radius:3px; color:#fff; font-size:12px;"
                        f" background:rgba({c[0]},{c[1]},{c[2]},0.7)"
                    )
                },
                name,
            )
            for name, c in legend_entries
        ]
        return ui.div({"style": "padding:6px 0;"}, *chips)

    @output
    @render.ui
    def save_status():
        msg = last_save()
        if not msg:
            return ui.HTML("")
        cls = "alert-danger" if msg.startswith("❌") else "alert-success"
        return ui.div(
            {"class": f"alert {cls}", "style": "padding:6px; margin-top:8px;"}, msg,
        )

    @reactive.effect
    @reactive.event(input.do_rename)
    def _do_rename():
        s = state()
        if s["cells"] is None:
            return
        # v0.57.4: rename targets the unified `selected_reach`. Pre-fix
        # used a separate `rename_old` dropdown — now the user picks
        # the target via either the "Selected reach" dropdown at the
        # top or the colour buttons below the map.
        old = (selected_reach() or "").strip()
        new = (input.rename_new() or "").strip()
        if not old:
            last_save.set("❌ rename: pick a reach first (use the dropdown or click a colour button)")
            return
        if not new:
            last_save.set("❌ rename: enter a new name")
            return
        if old == new:
            last_save.set("❌ old and new names are identical")
            return
        cells = s["cells"]
        reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
        if old not in cells[reach_col].values:
            last_save.set(f"❌ reach '{old}' not in current fixture")
            return
        if new in cells[reach_col].values:
            last_save.set(f"❌ '{new}' already exists — pick another name")
            return

        _push_undo_snapshot()
        cells = cells.copy()
        cells.loc[cells[reach_col] == old, reach_col] = new
        cfg = dict(s["cfg"])
        # v0.57.0 fix #13: rename CSVs on disk unconditionally — fixtures
        # without a top-level `reaches:` key (e.g. minimal smoke fixtures)
        # still own per-reach CSVs that must follow the rename, otherwise
        # the next load fails with a missing-file error.
        fixture_dir = s["shp_path"].parent.parent
        for suffix in ("TimeSeriesInputs.csv", "Depths.csv", "Vels.csv"):
            src = fixture_dir / f"{old}-{suffix}"
            if src.exists():
                src.rename(fixture_dir / f"{new}-{suffix}")
        if "reaches" in cfg and old in cfg["reaches"]:
            cfg["reaches"] = {
                (new if k == old else k): v for k, v in cfg["reaches"].items()
            }
            r = cfg["reaches"][new]
            for fk in ("time_series_input_file", "depth_file", "velocity_file"):
                v = r.get(fk, "")
                if isinstance(v, str) and v.startswith(f"{old}-"):
                    r[fk] = v.replace(f"{old}-", f"{new}-", 1)

        try:
            cells.to_file(s["shp_path"], driver="ESRI Shapefile")
            with open(s["cfg_path"], "w", encoding="utf-8") as f:
                f.write(
                    f"# {s['short_name']} — edited via Edit Model panel.\n"
                    "# Reach renamed via app/modules/edit_model_panel.py.\n#\n"
                )
                yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)
        except Exception as exc:
            logger.exception("save failed")
            last_save.set(f"❌ save failed: {exc}")
            return

        new_state = dict(s)
        new_state["cells"] = cells
        new_state["cfg"] = cfg
        state.set(new_state)
        last_save.set(f"✓ renamed '{old}' → '{new}' and saved")

    # ------------------------------------------------------------------
    # Merge two reaches (click-click)
    # ------------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.merge_start)
    def _merge_start():
        s = state()
        if s["cells"] is not None:
            reach_col = "REACH_NAME" if "REACH_NAME" in s["cells"].columns else "reach_name"
            n_reaches = s["cells"][reach_col].nunique()
            if n_reaches < 2:
                last_save.set(
                    f"❌ merge: fixture has only {n_reaches} reach — "
                    "need at least 2 to merge. Use rename or lasso instead."
                )
                return
        merge_state.set({"phase": "pick_a", "reach_a": None})
        active_mode.set("merge-a")
        last_save.set("merge: click any cell of the first reach")

    @reactive.effect
    def _merge_on_click():
        click_input_name = _widget.feature_click_input_id
        try:
            payload = getattr(input, click_input_name)()
        except Exception:
            return
        if not payload:
            return
        ms = merge_state()
        if ms["phase"] not in ("pick_a", "pick_b"):
            return
        feature = payload.get("object") if isinstance(payload, dict) else None
        if not feature:
            return
        props = feature.get("properties", {})
        clicked_reach = props.get("REACH_NAME") or props.get("reach_name")
        if not clicked_reach:
            return
        if ms["phase"] == "pick_a":
            merge_state.set({"phase": "pick_b", "reach_a": clicked_reach})
            active_mode.set("merge-b")
            last_save.set(f"reach A = {clicked_reach}; click reach B")
        elif ms["phase"] == "pick_b":
            if clicked_reach == ms["reach_a"]:
                last_save.set("❌ same reach picked twice; cancel and retry")
                return
            merge_state.set({
                "phase": "ready", "reach_a": ms["reach_a"], "reach_b": clicked_reach,
            })
            # Both reaches picked — clear the cursor mode but keep the
            # state machine in "ready" so Apply can fire.
            active_mode.set(None)
            last_save.set(
                f"reach A = {ms['reach_a']}, reach B = {clicked_reach}; "
                "type a new name and Apply"
            )

    @output
    @render.ui
    def merge_status():
        ms = merge_state()
        if ms["phase"] == "idle":
            return ui.HTML("")
        return ui.div(
            {"class": "alert alert-info", "style": "padding:6px;"},
            f"phase: {ms['phase']}, A={ms.get('reach_a')}, B={ms.get('reach_b','-')}",
        )

    @reactive.effect
    @reactive.event(input.merge_apply)
    def _merge_apply():
        s = state()
        ms = merge_state()
        new_name = (input.merge_new_name() or "").strip()
        if ms["phase"] != "ready" or not new_name:
            last_save.set("❌ merge: pick A and B then enter a new name")
            return
        if s["cells"] is None:
            return
        _push_undo_snapshot()
        a, b = ms["reach_a"], ms["reach_b"]
        cells = s["cells"].copy()
        reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
        cells.loc[cells[reach_col].isin([a, b]), reach_col] = new_name
        orphaned_b_csvs: list[str] = []

        cfg = dict(s["cfg"])
        if "reaches" in cfg:
            new_reaches = {}
            merged_in = False
            for k, v in cfg["reaches"].items():
                if k in (a, b):
                    if not merged_in:
                        new_reaches[new_name] = dict(cfg["reaches"][a])
                        merged_in = True
                else:
                    new_reaches[k] = v
            r = new_reaches.get(new_name, {})
            for fk in ("time_series_input_file", "depth_file", "velocity_file"):
                v = r.get(fk, "")
                if isinstance(v, str) and v.startswith(f"{a}-"):
                    r[fk] = v.replace(f"{a}-", f"{new_name}-", 1)
            cfg["reaches"] = new_reaches

            fixture_dir = s["shp_path"].parent.parent
            # v0.57.0 fix #11: detect reach B CSVs that will be orphaned
            # by the merge. The merged reach inherits ONLY reach A's
            # hydraulics — B's CSVs stay on disk under their old name and
            # never get loaded again. Users merging upper+lower reaches
            # could otherwise get silently wrong inputs.
            for suffix in ("TimeSeriesInputs.csv", "Depths.csv", "Vels.csv"):
                b_src = fixture_dir / f"{b}-{suffix}"
                if b_src.exists():
                    orphaned_b_csvs.append(b_src.name)
            for suffix in ("TimeSeriesInputs.csv", "Depths.csv", "Vels.csv"):
                src = fixture_dir / f"{a}-{suffix}"
                if src.exists():
                    dst = fixture_dir / f"{new_name}-{suffix}"
                    if dst.exists() and dst != src:
                        dst.unlink()
                    src.rename(dst)
            if orphaned_b_csvs:
                logger.warning(
                    "merge: %d reach-B CSVs orphaned on disk under '%s-' "
                    "prefix (merged reach inherits reach A's hydraulics): %s",
                    len(orphaned_b_csvs), b, ", ".join(orphaned_b_csvs),
                )

        try:
            cells.to_file(s["shp_path"], driver="ESRI Shapefile")
            with open(s["cfg_path"], "w", encoding="utf-8") as f:
                f.write(
                    f"# {s['short_name']} — merged via Edit Model panel.\n"
                    f"# Reaches '{a}' and '{b}' combined into '{new_name}'.\n#\n"
                )
                yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)
        except Exception as exc:
            logger.exception("merge save failed")
            last_save.set(f"❌ save failed: {exc}")
            return

        new_state = dict(s)
        new_state["cells"] = cells
        new_state["cfg"] = cfg
        state.set(new_state)
        merge_state.set({"phase": "idle", "reach_a": None})
        active_mode.set(None)
        merged_msg = f"✓ merged '{a}' + '{b}' → '{new_name}' and saved"
        if orphaned_b_csvs:
            merged_msg += (
                f" — note: {len(orphaned_b_csvs)} '{b}-' CSVs orphaned on "
                f"disk; merged reach uses '{a}' hydraulics. Delete or merge "
                "the orphaned files manually."
            )
        last_save.set(merged_msg)

    # ------------------------------------------------------------------
    # Split a reach by drawing a line
    # ------------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.split_start)
    async def _split_start():
        try:
            await _widget.enable_draw(
                session,
                modes=["draw_line_string"],
                default_mode="draw_line_string",
            )
        except Exception as exc:
            last_save.set(f"❌ enable_draw failed: {exc}")
            return
        split_state.set({"phase": "drawing"})
        active_mode.set("split")
        last_save.set(
            "split: draw a single line across the target reach, then click Apply"
        )

    @reactive.effect
    @reactive.event(input.split_apply)
    async def _split_apply():
        """Trigger effect: validate inputs, stash op params, fire
        get_drawn_features. The completion effect at
        _split_completion handles the geometry mutation."""
        s = state()
        # v0.57.4: split targets the unified `selected_reach` — same
        # source of truth as rename. Pre-fix used a separate
        # `split_target` dropdown.
        target = (selected_reach() or "").strip()
        north_name = (input.split_north_name() or "").strip()
        south_name = (input.split_south_name() or "").strip()
        if not target:
            last_save.set("❌ split: pick a reach first (dropdown or colour button)")
            return
        if not north_name or not south_name:
            last_save.set("❌ split: enter both north and south names")
            return
        if north_name == south_name:
            last_save.set("❌ split: north and south names must differ")
            return
        if s["cells"] is None:
            return
        # Mutual-exclusion: a previous lasso may still have a pending op.
        # Both completions react to the same drawn-features input — if both
        # ops are set simultaneously, the wrong completion can fire on the
        # next JS push. Clear the other op before staging this one.
        lasso_pending.set(None)
        split_pending.set({
            "target": target,
            "north_name": north_name,
            "south_name": south_name,
        })
        try:
            await _widget.get_drawn_features(session)
        except Exception as exc:
            last_save.set(f"❌ get_drawn_features trigger failed: {exc}")
            split_pending.set(None)
            return
        last_save.set("split: collecting drawn line — please wait…")

    @reactive.effect
    async def _split_completion():
        """Completion effect: react to drawn-features arriving from JS.
        Reads pending op (set by _split_apply trigger); performs geometry
        + shapefile/YAML mutation; clears pending op + draw mode."""
        try:
            features = getattr(input, _widget.drawn_features_input_id)()
        except Exception:
            return
        op = split_pending()
        if op is None:
            return
        line = None
        for f in (features or []):
            try:
                g = shape(f["geometry"])
            except Exception:
                continue
            if g.geom_type == "LineString":
                line = g
                break
        if line is None:
            # Drawn features arrived but no LineString in the payload.
            # Either the payload is empty (JS hasn't pushed yet — ignore)
            # or it contains a polygon (user switched to lasso). Use the
            # presence of features to decide: empty → keep pending so we
            # see the next JS push; non-empty → clear pending so we don't
            # block future split Apply presses.
            if features:
                split_pending.set(None)
            return

        # Claim the operation NOW (before any disk I/O). If the user
        # double-clicked Apply, two _split_completion runs are queued;
        # the first claims by clearing pending, the second reads
        # pending=None on its next dependency-trigger and exits early.
        # This is a defensive idiom — Shiny's single-threaded effect
        # loop usually serialises the two runs, but pending can leak
        # across reactive flushes if the JS layer pushes twice.
        split_pending.set(None)

        s = state()
        if s["cells"] is None:
            return

        # Geometry pass first — _apply_split_to_cells is pure (no state
        # mutation). Only push undo AFTER we know the operation will
        # actually mutate cells, so a no-op apply doesn't pollute the
        # undo stack.
        new_cells, n_north, n_south = _apply_split_to_cells(
            cells=s["cells"],
            target_reach=op["target"],
            line=line,
            north_name=op["north_name"],
            south_name=op["south_name"],
        )
        if n_north + n_south == 0:
            last_save.set(f"❌ no cells with reach '{op['target']}'")
            return
        _push_undo_snapshot()

        # YAML mutation (rebuild reach entries)
        cfg = dict(s["cfg"])
        if "reaches" in cfg and op["target"] in cfg["reaches"]:
            base_entry = dict(cfg["reaches"][op["target"]])
            del cfg["reaches"][op["target"]]
            for new_name in (op["north_name"], op["south_name"]):
                entry = dict(base_entry)
                entry["time_series_input_file"] = f"{new_name}-TimeSeriesInputs.csv"
                entry["depth_file"] = f"{new_name}-Depths.csv"
                entry["velocity_file"] = f"{new_name}-Vels.csv"
                cfg["reaches"][new_name] = entry
        # CSV rename on disk runs unconditionally — same v0.57.0 fix #13
        # contract as _do_rename: don't gate disk-side IO on the YAML
        # having a reaches: key.
        fixture_dir = s["shp_path"].parent.parent
        for suffix in ("TimeSeriesInputs.csv", "Depths.csv", "Vels.csv"):
            src = fixture_dir / f"{op['target']}-{suffix}"
            if src.exists():
                shutil.copy2(src, fixture_dir / f"{op['north_name']}-{suffix}")
                src.rename(fixture_dir / f"{op['south_name']}-{suffix}")

        try:
            new_cells.to_file(s["shp_path"], driver="ESRI Shapefile")
            with open(s["cfg_path"], "w", encoding="utf-8") as f:
                f.write(
                    f"# {s['short_name']} — split via Edit Model panel.\n"
                    f"# Reach '{op['target']}' split into "
                    f"'{op['north_name']}' (N) and "
                    f"'{op['south_name']}' (S).\n#\n"
                )
                yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)
        except Exception as exc:
            logger.exception("split save failed")
            last_save.set(f"❌ save failed: {exc}")
            return

        try:
            await _widget.delete_drawn_features(session)
            await _widget.disable_draw(session)
        except Exception:
            pass

        new_state = dict(s)
        new_state["cells"] = new_cells
        new_state["cfg"] = cfg
        state.set(new_state)
        split_state.set({"phase": "idle"})
        active_mode.set(None)
        # split_pending was already cleared at the top of this effect
        # (right after the line-found check), so a double-Apply race
        # cannot re-trigger this body. No second clear needed here.
        last_save.set(
            f"✓ split '{op['target']}' into '{op['north_name']}' "
            f"({n_north} cells) and '{op['south_name']}' ({n_south} cells)"
        )

    # ------------------------------------------------------------------
    # Lasso-select cells + bulk reassign
    # ------------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.lasso_start)
    async def _lasso_start():
        try:
            await _widget.enable_draw(
                session,
                modes=["draw_polygon"],
                default_mode="draw_polygon",
            )
        except Exception as exc:
            last_save.set(f"❌ enable_draw failed: {exc}")
            return
        active_mode.set("lasso")
        last_save.set(
            "lasso: draw a polygon enclosing the cells to reassign, then Apply"
        )

    @reactive.effect
    @reactive.event(input.lasso_apply)
    async def _lasso_apply():
        """Trigger effect — captures op params, calls get_drawn_features.
        Completion handled in _lasso_completion."""
        s = state()
        new_name = (input.lasso_new_name() or "").strip()
        if not new_name:
            last_save.set("❌ lasso: enter a reach name")
            return
        if s["cells"] is None:
            return
        # Mutual-exclusion: see _split_apply for rationale. Clear the
        # split op before staging this one so split_completion does not
        # mistake an arriving polygon for its target.
        split_pending.set(None)
        lasso_pending.set({"new_name": new_name})
        try:
            await _widget.get_drawn_features(session)
        except Exception as exc:
            last_save.set(f"❌ get_drawn_features trigger failed: {exc}")
            lasso_pending.set(None)
            return
        last_save.set("lasso: collecting drawn polygon — please wait…")

    @reactive.effect
    async def _lasso_completion():
        """React to drawn-features arriving from JS; perform the lasso
        reassignment + shapefile/YAML write."""
        try:
            features = getattr(input, _widget.drawn_features_input_id)()
        except Exception:
            return
        op = lasso_pending()
        if op is None:
            return
        from shapely.ops import unary_union
        polys = [
            shape(f["geometry"]) for f in (features or [])
            if f.get("geometry", {}).get("type") in ("Polygon", "MultiPolygon")
        ]
        if not polys:
            # No polygon in the payload. Empty payload → keep pending and
            # wait for the next JS push. Non-empty (LineString) → clear
            # pending so future lasso Apply presses can proceed.
            if features:
                lasso_pending.set(None)
            return
        lasso = unary_union(polys)

        # Claim the operation NOW (before any disk I/O); see
        # _split_completion for the double-Apply race rationale.
        lasso_pending.set(None)

        s = state()
        if s["cells"] is None:
            return

        # Pure geometry pass first; only push undo if we will actually
        # mutate cells (mirrors _split_completion's ordering).
        reach_col = "REACH_NAME" if "REACH_NAME" in s["cells"].columns else "reach_name"
        old_reaches = (
            s["cells"][s["cells"].geometry.centroid.within(lasso)]
            [reach_col].value_counts().to_dict()
        )
        new_cells, n_inside = _apply_lasso_to_cells(
            cells=s["cells"], lasso=lasso, new_name=op["new_name"],
        )
        if n_inside == 0:
            last_save.set("❌ lasso: no cell centroids inside the drawn polygon")
            return
        _push_undo_snapshot()

        cfg = dict(s["cfg"])
        if "reaches" in cfg and op["new_name"] not in cfg["reaches"]:
            donor = max(old_reaches, key=old_reaches.get) if old_reaches else None
            if donor is not None:
                entry = dict(cfg["reaches"].get(donor, {}))
                entry["time_series_input_file"] = f"{op['new_name']}-TimeSeriesInputs.csv"
                entry["depth_file"] = f"{op['new_name']}-Depths.csv"
                entry["velocity_file"] = f"{op['new_name']}-Vels.csv"
                cfg["reaches"][op["new_name"]] = entry
                fixture_dir = s["shp_path"].parent.parent
                for suffix in ("TimeSeriesInputs.csv", "Depths.csv", "Vels.csv"):
                    src = fixture_dir / f"{donor}-{suffix}"
                    if src.exists():
                        shutil.copy2(src, fixture_dir / f"{op['new_name']}-{suffix}")

        try:
            new_cells.to_file(s["shp_path"], driver="ESRI Shapefile")
            with open(s["cfg_path"], "w", encoding="utf-8") as f:
                f.write(
                    f"# {s['short_name']} — lasso-edited via Edit Model panel.\n"
                    f"# {n_inside} cells reassigned to '{op['new_name']}'.\n#\n"
                )
                yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False)
        except Exception as exc:
            logger.exception("lasso save failed")
            last_save.set(f"❌ save failed: {exc}")
            return

        try:
            await _widget.delete_drawn_features(session)
            await _widget.disable_draw(session)
        except Exception:
            pass

        new_state = dict(s)
        new_state["cells"] = new_cells
        new_state["cfg"] = cfg
        state.set(new_state)
        # lasso_pending was already cleared at the top of the post-validation
        # block; no second clear needed here (mirrors _split_completion).
        active_mode.set(None)
        last_save.set(f"✓ lasso: {n_inside} cells reassigned to '{op['new_name']}'")

    # ------------------------------------------------------------------
    # Regenerate cells at a new cell size
    # ------------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.regen_apply)
    def _regen_apply():
        s = state()
        if s["cells"] is None:
            return
        new_size = float(input.regen_cell_size() or 0)
        if new_size < 10:
            last_save.set("❌ regenerate: cell size must be ≥10 m")
            return

        _push_undo_snapshot()
        from modules.create_model_grid import generate_cells
        cells = s["cells"]
        reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
        reach_segments = {}
        for name, grp in cells.groupby(reach_col):
            if "FRACSPWN" in grp.columns:
                fspawn = float(grp["FRACSPWN"].iloc[0])
            elif "frac_spawn" in grp.columns:
                fspawn = float(grp["frac_spawn"].iloc[0])
            else:
                fspawn = 0.0
            reach_segments[name] = {
                "segments": list(grp.geometry),
                "frac_spawn": fspawn,
                "type": "water",
            }
        try:
            new_cells = generate_cells(
                reach_segments=reach_segments,
                cell_size=new_size,
                cell_shape="hexagonal",
                buffer_factor=1.0,
                min_overlap=0.1,
            )
        except Exception as exc:
            logger.exception("regenerate failed")
            last_save.set(f"❌ regenerate failed: {exc}")
            return

        if new_cells.empty:
            last_save.set(f"❌ regenerate produced 0 cells at size={new_size} m")
            return

        rename = {
            "cell_id": "ID_TEXT", "reach_name": "REACH_NAME", "area": "AREA",
            "dist_escape": "M_TO_ESC", "num_hiding": "NUM_HIDING",
            "frac_vel_shelter": "FRACVSHL", "frac_spawn": "FRACSPWN",
        }
        new_cells = new_cells.rename(columns=rename)
        new_cells["ID_TEXT"] = new_cells["ID_TEXT"].astype(str)

        try:
            new_cells.to_file(s["shp_path"], driver="ESRI Shapefile")
        except Exception as exc:
            logger.exception("save failed")
            last_save.set(f"❌ save failed: {exc}")
            return

        # H7 (iteration-5 review): per-reach Depths.csv / Vels.csv have one
        # row per cell. After regenerate the cell counts change → next load
        # raises "hydraulic table has X rows but cell count is Y". Re-expand
        # those CSVs to the new counts.
        fixture_dir = s["shp_path"].parent.parent
        new_reach_cell_counts = new_cells["REACH_NAME"].value_counts().to_dict()
        for reach_name, n_new in new_reach_cell_counts.items():
            for suffix in ("Depths.csv", "Vels.csv"):
                csv_path = fixture_dir / f"{reach_name}-{suffix}"
                if not csv_path.exists():
                    continue
                lines = csv_path.read_text(encoding="utf-8").splitlines()
                header_end = None
                for i, line in enumerate(lines):
                    parts = line.split(",")
                    if not parts:
                        continue
                    first = parts[0].strip()
                    if first.isdigit() and len(parts) > 1:
                        try:
                            float(parts[1])
                            header_end = i
                            break
                        except ValueError:
                            continue
                if header_end is None:
                    logger.warning("could not locate data rows in %s", csv_path)
                    continue
                header_lines = lines[:header_end]
                template = lines[header_end].split(",")
                payload = template[1:]
                with open(csv_path, "w", encoding="utf-8") as f:
                    for hl in header_lines:
                        f.write(hl + "\n")
                    for i in range(int(n_new)):
                        f.write(f"{i + 1}," + ",".join(payload) + "\n")

        new_state = dict(s)
        new_state["cells"] = new_cells
        state.set(new_state)
        last_save.set(
            f"✓ regenerated at cell_size={new_size} m: "
            f"{len(s['cells'])} → {len(new_cells)} cells (CSVs re-expanded)"
        )

    # ------------------------------------------------------------------
    # Undo / redo
    # ------------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.undo)
    def _undo():
        stack = list(history_undo())
        if not stack:
            last_save.set("nothing to undo")
            return
        snap = stack.pop()
        history_undo.set(stack)
        s = state()
        redo_stack = list(history_redo())
        redo_stack.append({"cells": s["cells"].copy(), "cfg": dict(s["cfg"])})
        history_redo.set(redo_stack)
        new_state = dict(s)
        new_state["cells"] = snap["cells"]
        new_state["cfg"] = snap["cfg"]
        state.set(new_state)
        try:
            snap["cells"].to_file(s["shp_path"], driver="ESRI Shapefile")
            with open(s["cfg_path"], "w", encoding="utf-8") as f:
                yaml.safe_dump(snap["cfg"], f, sort_keys=False, default_flow_style=False)
        except Exception as exc:
            last_save.set(f"❌ undo save failed: {exc}")
            return
        last_save.set(f"↶ undo ok ({len(stack)} more available)")

    @reactive.effect
    @reactive.event(input.redo)
    def _redo():
        stack = list(history_redo())
        if not stack:
            last_save.set("nothing to redo")
            return
        snap = stack.pop()
        history_redo.set(stack)
        s = state()
        undo_stack = list(history_undo())
        undo_stack.append({"cells": s["cells"].copy(), "cfg": dict(s["cfg"])})
        history_undo.set(undo_stack)
        new_state = dict(s)
        new_state["cells"] = snap["cells"]
        new_state["cfg"] = snap["cfg"]
        state.set(new_state)
        try:
            snap["cells"].to_file(s["shp_path"], driver="ESRI Shapefile")
            with open(s["cfg_path"], "w", encoding="utf-8") as f:
                yaml.safe_dump(snap["cfg"], f, sort_keys=False, default_flow_style=False)
        except Exception as exc:
            last_save.set(f"❌ redo save failed: {exc}")
            return
        last_save.set(f"↷ redo ok ({len(stack)} more available)")
