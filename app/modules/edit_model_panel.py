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
        if not next(iter(shp_dir.glob("*.shp")), None):
            continue
        available.append(short_name)
    return available


def _load_fixture(short_name: str):
    """Return (config_dict, cells_gdf, config_path, shapefile_path)."""
    root = _project_root()
    cfg_path = root / "configs" / f"{short_name}.yaml"
    fix_dir = _fixtures_root(root) / short_name
    shp = next((fix_dir / "Shapefile").glob("*.shp"))
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


def _build_reach_geojson(cells: gpd.GeoDataFrame):
    """Render cells as GeoJSON with per-feature `_fill` (RGBA)."""
    reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
    reach_names = sorted(cells[reach_col].unique())
    color_for = {
        name: PALETTE_RGB[i % len(PALETTE_RGB)] + [180]
        for i, name in enumerate(reach_names)
    }
    cells = cells.copy()
    cells["_fill"] = cells[reach_col].map(color_for)
    geojson = json.loads(cells.to_json())
    legend_entries = [(name, color_for[name]) for name in reach_names]
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
    return ui.div(
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
                ui.h5("Rename reach"),
                ui.input_select("rename_old", "Reach to rename", choices=[]),
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
                ui.h5("Split a reach by drawing a line"),
                ui.input_select("split_target", "Reach to split", choices=[]),
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
                ui.output_ui("save_status"),
            ),
            ui.column(
                8,
                _widget.ui(height="600px"),
                ui.output_ui("legend"),
            ),
        ),
    )


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

    # Undo/redo: list of {cells, cfg} snapshots, capped at 10
    history_undo = reactive.value([])
    history_redo = reactive.value([])

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
        last_save.set(f"loaded {short_name} ({len(cells)} cells)")

    @reactive.effect
    def _populate_reach_dropdowns():
        s = state()
        if s["cells"] is None:
            return
        reach_col = "REACH_NAME" if "REACH_NAME" in s["cells"].columns else "reach_name"
        names = sorted(s["cells"][reach_col].unique())
        ui.update_select(
            "rename_old", choices=names,
            selected=names[0] if names else None,
        )
        ui.update_select(
            "split_target", choices=names,
            selected=names[0] if names else None,
        )

    @reactive.effect
    async def _update_map():
        s = state()
        if s["cells"] is None:
            return
        geojson, _ = _build_reach_geojson(s["cells"])
        layer = geojson_layer(
            id="reaches",
            data=geojson,
            getFillColor="@@=properties._fill",
            getLineColor=[40, 40, 40, 200],
            getLineWidth=1,
            stroked=True,
            filled=True,
            pickable=True,
        )
        try:
            await _widget.update(session, [layer])
        except Exception:
            logger.exception("map update failed")

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
        old = (input.rename_old() or "").strip()
        new = (input.rename_new() or "").strip()
        if not old or not new:
            last_save.set("❌ rename requires both old and new names")
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
        if "reaches" in cfg and old in cfg["reaches"]:
            cfg["reaches"] = {
                (new if k == old else k): v for k, v in cfg["reaches"].items()
            }
            fixture_dir = s["shp_path"].parent.parent
            for suffix in ("TimeSeriesInputs.csv", "Depths.csv", "Vels.csv"):
                src = fixture_dir / f"{old}-{suffix}"
                if src.exists():
                    src.rename(fixture_dir / f"{new}-{suffix}")
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
            last_save.set(f"reach A = {clicked_reach}; click reach B")
        elif ms["phase"] == "pick_b":
            if clicked_reach == ms["reach_a"]:
                last_save.set("❌ same reach picked twice; cancel and retry")
                return
            merge_state.set({
                "phase": "ready", "reach_a": ms["reach_a"], "reach_b": clicked_reach,
            })
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
            for suffix in ("TimeSeriesInputs.csv", "Depths.csv", "Vels.csv"):
                src = fixture_dir / f"{a}-{suffix}"
                if src.exists():
                    dst = fixture_dir / f"{new_name}-{suffix}"
                    if dst.exists() and dst != src:
                        dst.unlink()
                    src.rename(dst)
                # b's CSVs become orphaned — leave on disk for manual cleanup

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
        last_save.set(f"✓ merged '{a}' + '{b}' → '{new_name}' and saved")

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
        last_save.set(
            "split: draw a single line across the target reach, then click Apply"
        )

    @reactive.effect
    @reactive.event(input.split_apply)
    async def _split_apply():
        s = state()
        target = (input.split_target() or "").strip()
        north_name = (input.split_north_name() or "").strip()
        south_name = (input.split_south_name() or "").strip()
        if not target or not north_name or not south_name:
            last_save.set("❌ split: pick target reach and both new names")
            return
        if north_name == south_name:
            last_save.set("❌ split: north and south names must differ")
            return
        try:
            await _widget.get_drawn_features(session)
        except Exception as exc:
            last_save.set(f"❌ get_drawn_features trigger failed: {exc}")
            return
        features_input_name = _widget.drawn_features_input_id
        try:
            features = getattr(input, features_input_name)()
        except Exception:
            features = None
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
            last_save.set(
                "❌ split: no LineString found in drawn features (did you finish the line?)"
            )
            return

        _push_undo_snapshot()
        cells = s["cells"].copy()
        reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
        target_mask = cells[reach_col] == target
        if not target_mask.any():
            last_save.set(f"❌ no cells with reach '{target}'")
            return

        target_cells = cells[target_mask]
        sides = []
        L = line.length
        for geom in target_cells.geometry:
            c = geom.centroid
            nearest_dist = line.project(c)
            nearest_pt = line.interpolate(nearest_dist)
            eps = max(L * 1e-6, 1e-9)
            if nearest_dist + eps <= L:
                tangent_pt = line.interpolate(nearest_dist + eps)
                base = nearest_pt
            else:
                # End-of-line: step backward, flip frame so cross sign matches.
                prev_pt = line.interpolate(max(nearest_dist - eps, 0.0))
                base = prev_pt
                tangent_pt = nearest_pt
            dx = tangent_pt.x - base.x
            dy = tangent_pt.y - base.y
            cross = (c.x - base.x) * dy - (c.y - base.y) * dx
            sides.append("north" if cross >= 0 else "south")
        cells.loc[target_mask, reach_col] = [
            north_name if sd == "north" else south_name for sd in sides
        ]

        cfg = dict(s["cfg"])
        if "reaches" in cfg and target in cfg["reaches"]:
            base_entry = dict(cfg["reaches"][target])
            del cfg["reaches"][target]
            for new_name in (north_name, south_name):
                entry = dict(base_entry)
                entry["time_series_input_file"] = f"{new_name}-TimeSeriesInputs.csv"
                entry["depth_file"] = f"{new_name}-Depths.csv"
                entry["velocity_file"] = f"{new_name}-Vels.csv"
                cfg["reaches"][new_name] = entry
            fixture_dir = s["shp_path"].parent.parent
            for suffix in ("TimeSeriesInputs.csv", "Depths.csv", "Vels.csv"):
                src = fixture_dir / f"{target}-{suffix}"
                if src.exists():
                    shutil.copy2(src, fixture_dir / f"{north_name}-{suffix}")
                    src.rename(fixture_dir / f"{south_name}-{suffix}")

        try:
            cells.to_file(s["shp_path"], driver="ESRI Shapefile")
            with open(s["cfg_path"], "w", encoding="utf-8") as f:
                f.write(
                    f"# {s['short_name']} — split via Edit Model panel.\n"
                    f"# Reach '{target}' split into '{north_name}' (N) and "
                    f"'{south_name}' (S).\n#\n"
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
        new_state["cells"] = cells
        new_state["cfg"] = cfg
        state.set(new_state)
        split_state.set({"phase": "idle"})
        n_north = sum(1 for sd in sides if sd == "north")
        n_south = len(sides) - n_north
        last_save.set(
            f"✓ split '{target}' into '{north_name}' ({n_north} cells) "
            f"and '{south_name}' ({n_south} cells)"
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
        last_save.set(
            "lasso: draw a polygon enclosing the cells to reassign, then Apply"
        )

    @reactive.effect
    @reactive.event(input.lasso_apply)
    async def _lasso_apply():
        s = state()
        new_name = (input.lasso_new_name() or "").strip()
        if not new_name:
            last_save.set("❌ lasso: enter a reach name")
            return
        if s["cells"] is None:
            return
        try:
            await _widget.get_drawn_features(session)
        except Exception as exc:
            last_save.set(f"❌ get_drawn_features trigger failed: {exc}")
            return
        try:
            features = getattr(input, _widget.drawn_features_input_id)()
        except Exception:
            features = None
        polys = [
            shape(f["geometry"]) for f in (features or [])
            if f.get("geometry", {}).get("type") in ("Polygon", "MultiPolygon")
        ]
        if not polys:
            last_save.set("❌ lasso: no polygon found in drawn features")
            return
        from shapely.ops import unary_union
        lasso = unary_union(polys)

        _push_undo_snapshot()
        cells = s["cells"].copy()
        reach_col = "REACH_NAME" if "REACH_NAME" in cells.columns else "reach_name"
        inside_mask = cells.geometry.centroid.within(lasso)
        n_inside = int(inside_mask.sum())
        if n_inside == 0:
            last_save.set("❌ lasso: no cell centroids inside the drawn polygon")
            return

        old_reaches = cells.loc[inside_mask, reach_col].value_counts().to_dict()
        cells.loc[inside_mask, reach_col] = new_name

        cfg = dict(s["cfg"])
        if "reaches" in cfg and new_name not in cfg["reaches"]:
            donor = max(old_reaches, key=old_reaches.get)
            entry = dict(cfg["reaches"].get(donor, {}))
            entry["time_series_input_file"] = f"{new_name}-TimeSeriesInputs.csv"
            entry["depth_file"] = f"{new_name}-Depths.csv"
            entry["velocity_file"] = f"{new_name}-Vels.csv"
            cfg["reaches"][new_name] = entry
            fixture_dir = s["shp_path"].parent.parent
            for suffix in ("TimeSeriesInputs.csv", "Depths.csv", "Vels.csv"):
                src = fixture_dir / f"{donor}-{suffix}"
                if src.exists():
                    shutil.copy2(src, fixture_dir / f"{new_name}-{suffix}")

        try:
            cells.to_file(s["shp_path"], driver="ESRI Shapefile")
            with open(s["cfg_path"], "w", encoding="utf-8") as f:
                f.write(
                    f"# {s['short_name']} — lasso-edited via Edit Model panel.\n"
                    f"# {n_inside} cells reassigned to '{new_name}'.\n#\n"
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
        new_state["cells"] = cells
        new_state["cfg"] = cfg
        state.set(new_state)
        last_save.set(f"✓ lasso: {n_inside} cells reassigned to '{new_name}'")

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
