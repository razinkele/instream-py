"""v0.57.0 fix #1: lasso + split must hand off via the JS draw layer.

The shiny_deckgl `get_drawn_features` is a side-effect trigger (the JS
side pushes the GeoJSON feature list into a reactive input on its own
schedule), NOT a synchronous getter. Pre-fix _split_apply and
_lasso_apply read the input on the next Python line — always seeing the
previous (None) value, so both Apply handlers always aborted.

These tests pin the new two-effect structure: a trigger effect that
captures intent and calls get_drawn_features, and a completion effect
keyed on the drawn-features reactive input that performs the geometry
mutation.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def _extract_effect_body(src: str, start_marker: str) -> str:
    """Return the body of an @reactive.effect-decorated coroutine that
    begins at `start_marker` (e.g. `'async def _split_apply'`).

    Body ends at the NEXT `@reactive.effect` decorator in the file —
    that decorator is the natural per-effect boundary in this module
    regardless of whether `# ----` separator comments are present.
    Pre-fix the next decorator points at `_lasso_apply` / `_split_start`
    etc.; post-fix it points at `_split_completion` / `_lasso_completion`.
    Either way, the extracted body is exactly the function we asked for.
    """
    start = src.index(start_marker)
    # Skip the marker itself, then look for the next decorator at the
    # same indentation level (4 spaces, since these are nested inside
    # `def edit_model_server(...)`).
    end = src.find("\n    @reactive.effect", start + len(start_marker))
    if end == -1:
        end = len(src)
    return src[start:end]


def test_split_apply_does_not_read_drawn_features_synchronously():
    """The split Apply handler must NOT call getattr(input, drawn_features...)
    in the same coroutine as await get_drawn_features. Inspecting the
    source is sufficient to lock this in — a refactor that re-introduces
    the synchronous read will fail this assertion."""
    from modules import edit_model_panel as ep
    src = Path(ep.__file__).read_text(encoding="utf-8")

    body = _extract_effect_body(src, "async def _split_apply")

    # Forbidden: reading drawn_features on the same line/coroutine as the
    # trigger call. We disallow `getattr(input, ..._drawn_features_input_id)`
    # appearing AFTER `await _widget.get_drawn_features` inside the same
    # function body.
    if "get_drawn_features" in body:
        idx_trigger = body.index("get_drawn_features")
        after = body[idx_trigger:]
        assert "drawn_features_input_id" not in after, (
            "v0.57.0 fix #1: _split_apply still reads drawn_features_input_id "
            "synchronously after triggering get_drawn_features. The read "
            "must move to a separate @reactive.effect keyed on the input."
        )


def test_lasso_apply_does_not_read_drawn_features_synchronously():
    """Same assertion as the split test, scoped to _lasso_apply."""
    from modules import edit_model_panel as ep
    src = Path(ep.__file__).read_text(encoding="utf-8")

    body = _extract_effect_body(src, "async def _lasso_apply")

    if "get_drawn_features" in body:
        idx_trigger = body.index("get_drawn_features")
        after = body[idx_trigger:]
        assert "drawn_features_input_id" not in after, (
            "v0.57.0 fix #1: _lasso_apply still reads drawn_features_input_id "
            "synchronously after triggering get_drawn_features. The read "
            "must move to a separate @reactive.effect keyed on the input."
        )


def test_completion_effects_exist_by_name():
    """The panel module must define `_split_completion` and
    `_lasso_completion` functions inside `edit_model_server`. Pre-fix
    these names did not exist; post-fix they hold the geometry-mutation
    code that the drawn-features reactive input drives.

    This is a stronger guard than a string-count: the count would pass
    pre-fix because the existing `_split_apply` and `_lasso_apply` already
    reference `drawn_features_input_id` synchronously (the bug being
    fixed). Function names are unambiguous.
    """
    from modules import edit_model_panel as ep
    src = Path(ep.__file__).read_text(encoding="utf-8")
    assert "async def _split_completion" in src, (
        "v0.57.0 fix #1: edit_model_panel must define `_split_completion` "
        "as a separate @reactive.effect that consumes drawn-features"
    )
    assert "async def _lasso_completion" in src, (
        "v0.57.0 fix #1: edit_model_panel must define `_lasso_completion` "
        "as a separate @reactive.effect that consumes drawn-features"
    )


def test_split_pure_geometry_helper_exists():
    """The split geometry math is testable in isolation as a pure function.
    The plan extracts it to `_apply_split_to_cells` so the completion
    effect calls a tested helper rather than inlining the math.
    """
    from modules import edit_model_panel as ep
    assert hasattr(ep, "_apply_split_to_cells"), (
        "v0.57.0 fix #1: edit_model_panel must expose `_apply_split_to_cells` "
        "as the pure-Python helper called by the completion effect"
    )


def test_lasso_pure_helper_exists():
    """Mirror of the split helper — pure-Python lasso reassignment."""
    from modules import edit_model_panel as ep
    assert hasattr(ep, "_apply_lasso_to_cells"), (
        "v0.57.0 fix #1: edit_model_panel must expose `_apply_lasso_to_cells` "
        "as the pure-Python helper called by the completion effect"
    )


def test_undo_pushed_after_validation_in_completion_effects():
    """The original 2026-05-03 review flagged that `_lasso_apply` pushed
    an undo snapshot before checking `n_inside == 0`. The same anti-
    pattern would re-occur if the new completion effects pushed undo
    before validating the geometry result. Pin the contract that
    `_push_undo_snapshot()` appears AFTER the `if n_north + n_south == 0`
    / `if n_inside == 0` guard in both completion functions.

    Pre-fix, `_split_completion` and `_lasso_completion` do not exist.
    This test must FAIL pre-fix — that signals the fix has not yet been
    applied. We therefore assert the function name exists FIRST, and
    fail loudly with a fix-pointer message if it does not.
    """
    from modules import edit_model_panel as ep
    src = Path(ep.__file__).read_text(encoding="utf-8")

    for fn_name, guard_substr in (
        ("_split_completion", "n_north + n_south == 0"),
        ("_lasso_completion", "n_inside == 0"),
    ):
        assert f"async def {fn_name}" in src, (
            f"v0.57.0 fix #1: `async def {fn_name}` not found in "
            f"edit_model_panel.py — Task 5.3/5.4 has not been applied."
        )
        start = src.index(f"async def {fn_name}")
        # End at the next top-level function or the end of the module
        next_def = src.find("\n    @reactive.effect", start + 1)
        if next_def == -1:
            next_def = len(src)
        body = src[start:next_def]
        guard_idx = body.find(guard_substr)
        push_idx = body.find("_push_undo_snapshot()")
        assert guard_idx != -1, f"{fn_name}: missing zero-count guard ({guard_substr!r})"
        assert push_idx != -1, f"{fn_name}: missing _push_undo_snapshot() call"
        assert push_idx > guard_idx, (
            f"v0.57.0 fix #1: in {fn_name}, _push_undo_snapshot() at "
            f"position {push_idx} runs BEFORE the zero-count guard at "
            f"position {guard_idx}. Move the undo push after validation "
            f"so a no-op apply does not pollute the undo stack "
            f"(the original review's anti-pattern)."
        )


def test_triggers_clear_other_op_for_mutual_exclusion():
    """Both `_split_completion` and `_lasso_completion` watch the same
    drawn-features reactive input. If a user switches from split to
    lasso mid-flow, two pending ops would race. The trigger effects
    must clear the OTHER op's pending value before staging their own.

    Uses `str.find()` + explicit assert messages so a missing function
    produces a clean test FAIL with a fix-pointer, not a `ValueError:
    substring not found` traceback.
    """
    from modules import edit_model_panel as ep
    src = Path(ep.__file__).read_text(encoding="utf-8")

    # In _split_apply: lasso_pending.set(None) must appear before
    # split_pending.set({...})
    split_apply_idx = src.find("async def _split_apply")
    split_completion_idx = src.find("async def _split_completion")
    assert split_apply_idx != -1, (
        "v0.57.0 fix #1: `async def _split_apply` not found — Task 5.3 "
        "has not been applied"
    )
    assert split_completion_idx != -1, (
        "v0.57.0 fix #1: `async def _split_completion` not found — Task "
        "5.3 has not been applied"
    )
    split_apply_body = src[split_apply_idx:split_completion_idx]
    lasso_clear = split_apply_body.find("lasso_pending.set(None)")
    split_set = split_apply_body.find("split_pending.set({")
    assert lasso_clear != -1, (
        "v0.57.0 fix #1: _split_apply must call lasso_pending.set(None) "
        "to clear any prior lasso op before staging its own"
    )
    assert split_set != -1, "v0.57.0 fix #1: _split_apply must stage split_pending"
    assert lasso_clear < split_set, (
        "v0.57.0 fix #1: _split_apply must clear lasso_pending BEFORE "
        "staging split_pending (otherwise both could be set briefly)"
    )

    # In _lasso_apply: split_pending.set(None) before lasso_pending.set({...})
    lasso_apply_idx = src.find("async def _lasso_apply")
    lasso_completion_idx = src.find("async def _lasso_completion")
    assert lasso_apply_idx != -1, (
        "v0.57.0 fix #1: `async def _lasso_apply` not found — Task 5.4 "
        "has not been applied"
    )
    assert lasso_completion_idx != -1, (
        "v0.57.0 fix #1: `async def _lasso_completion` not found — Task "
        "5.4 has not been applied"
    )
    lasso_apply_body = src[lasso_apply_idx:lasso_completion_idx]
    split_clear = lasso_apply_body.find("split_pending.set(None)")
    lasso_set = lasso_apply_body.find("lasso_pending.set({")
    assert split_clear != -1, (
        "v0.57.0 fix #1: _lasso_apply must call split_pending.set(None) "
        "to clear any prior split op before staging its own"
    )
    assert lasso_set != -1, "v0.57.0 fix #1: _lasso_apply must stage lasso_pending"
    assert split_clear < lasso_set, (
        "v0.57.0 fix #1: _lasso_apply must clear split_pending BEFORE "
        "staging lasso_pending"
    )


def test_apply_split_to_cells_classifies_and_renames(monkeypatch):
    """End-to-end on the helper: a horizontal line splits a 4x4 grid into
    8 north + 8 south cells, with cells renamed to north_name / south_name."""
    import geopandas as gpd
    from shapely.geometry import LineString, Polygon

    from modules.edit_model_panel import _apply_split_to_cells

    cells = []
    for x in range(4):
        for y in range(4):
            cells.append(Polygon([
                (x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)
            ]))
    gdf = gpd.GeoDataFrame(
        {"REACH_NAME": ["Target"] * 16},
        geometry=cells, crs="EPSG:4326",
    )
    line = LineString([(0, 2), (4, 2)])

    new_gdf, n_north, n_south = _apply_split_to_cells(
        cells=gdf, target_reach="Target", line=line,
        north_name="N", south_name="S",
    )
    assert n_north == 8
    assert n_south == 8
    assert set(new_gdf["REACH_NAME"]) == {"N", "S"}


def test_apply_lasso_to_cells_reassigns(monkeypatch):
    """Lasso polygon over a 4x4 grid must reassign only the cells whose
    centroids fall inside it."""
    import geopandas as gpd
    from shapely.geometry import Polygon

    from modules.edit_model_panel import _apply_lasso_to_cells

    cells = []
    for x in range(4):
        for y in range(4):
            cells.append(Polygon([
                (x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)
            ]))
    gdf = gpd.GeoDataFrame(
        {"REACH_NAME": ["Old"] * 16},
        geometry=cells, crs="EPSG:4326",
    )
    # Lasso covers only the bottom-left 2x2 quadrant: cells with centroids
    # at (0.5,0.5), (1.5,0.5), (0.5,1.5), (1.5,1.5).
    lasso = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])

    new_gdf, n_inside = _apply_lasso_to_cells(
        cells=gdf, lasso=lasso, new_name="Side",
    )
    assert n_inside == 4
    side_count = (new_gdf["REACH_NAME"] == "Side").sum()
    assert side_count == 4
    old_count = (new_gdf["REACH_NAME"] == "Old").sum()
    assert old_count == 12
