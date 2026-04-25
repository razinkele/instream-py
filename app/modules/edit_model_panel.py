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
from pathlib import Path

import geopandas as gpd
import yaml
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
                ui.output_ui("reach_table"),
                ui.hr(),
                ui.h5("Rename reach"),
                ui.input_select("rename_old", "Reach to rename", choices=[]),
                ui.input_text("rename_new", "New name", placeholder="e.g. Estuary"),
                ui.input_action_button(
                    "do_rename", "Apply rename + save", class_="btn-primary",
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
    def _populate_rename_dropdown():
        s = state()
        if s["cells"] is None:
            return
        reach_col = "REACH_NAME" if "REACH_NAME" in s["cells"].columns else "reach_name"
        names = sorted(s["cells"][reach_col].unique())
        ui.update_select(
            "rename_old", choices=names,
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
