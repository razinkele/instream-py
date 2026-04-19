"""Unit tests for the redds scatterplot layer builder.

The layer shows egg-nest locations on the deck.gl spatial map. We can't
unit-test the rendering itself (that's the deck.gl runtime), but we can
verify the helper returns the expected structure and handles edge cases
cleanly — which is enough to prevent the most common regressions.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "app"))

from modules.spatial_panel import _build_redds_layer  # noqa: E402


def _make_cells(n: int = 3) -> gpd.GeoDataFrame:
    """Tiny 3-cell mock GDF in WGS84 — cells are small squares
    centred on known coordinates so we can assert centroid lookup."""
    geoms = [
        Polygon([(lon, lat), (lon + 0.01, lat), (lon + 0.01, lat + 0.01),
                 (lon, lat + 0.01)])
        for lon, lat in [(21.2, 55.3), (21.3, 55.4), (21.4, 55.5)][:n]
    ]
    return gpd.GeoDataFrame({"cell_id": range(n)}, geometry=geoms, crs="EPSG:4326")


def test_empty_redds_returns_empty_layer() -> None:
    """No redds → layer still exists so partial_update toggles work."""
    results = {
        "cells": _make_cells(),
        "redds": pd.DataFrame(columns=["redd_idx", "cell_idx", "eggs"]),
    }
    layer = _build_redds_layer(results, visible=True)
    assert layer["id"] == "redds"
    assert layer["visible"] is True
    # data can be [] or a dict depending on deck.gl defaults — just
    # require it to be falsy so the layer renders nothing.
    assert not layer.get("data")


def test_missing_cells_returns_empty_layer() -> None:
    """Guards against build-time callers that lack a cells GDF."""
    results = {
        "cells": gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"),
        "redds": pd.DataFrame({"redd_idx": [0], "cell_idx": [0], "eggs": [100]}),
    }
    layer = _build_redds_layer(results, visible=True)
    assert not layer.get("data")


def test_redds_emit_scatterplot_data_at_cell_centroids() -> None:
    """Each redd becomes one data point positioned at its host cell's
    centroid, with eggs carried through so the hover tooltip can show it."""
    cells = _make_cells(n=3)
    redds = pd.DataFrame({
        "redd_idx": [0, 1, 2],
        "cell_idx": [0, 2, 0],
        "eggs": [100, 10_000, 1],
        "species": ["BalticAtlanticSalmon"] * 3,
        "frac_developed": [0.1, 0.5, 0.9],
    })
    layer = _build_redds_layer({"cells": cells, "redds": redds}, visible=True)
    data = layer["data"]
    assert len(data) == 3

    # First redd sits on cell 0 (centroid near 21.205, 55.305)
    r0 = data[0]
    assert r0["eggs"] == 100
    assert r0["position"] == pytest.approx([21.205, 55.305], abs=0.01)

    # Middle redd sits on cell 2 (centroid near 21.405, 55.505)
    r1 = data[1]
    assert r1["eggs"] == 10_000
    assert r1["position"] == pytest.approx([21.405, 55.505], abs=0.01)

    # sqrt-scaling: radius = sqrt(eggs) × 1.5, clamped at 5m minimum.
    # 10,000-egg redd = sqrt(10000) × 1.5 = 150m; 100-egg redd =
    # sqrt(100) × 1.5 = 15m → the bigger redd is exactly 10× the
    # smaller. Asserts the sqrt growth is linear in log-egg space.
    assert r1["radius"] == pytest.approx(10 * r0["radius"], rel=1e-3)


def test_out_of_range_cell_idx_is_skipped() -> None:
    """A redd referencing a cell index outside the cells GDF should be
    dropped (not crash). This guards against stale fixture mismatches."""
    cells = _make_cells(n=2)
    redds = pd.DataFrame({
        "redd_idx": [0, 1, 2],
        "cell_idx": [0, 999, 1],   # 999 is out of range
        "eggs": [100, 100, 100],
        "species": ["BalticAtlanticSalmon"] * 3,
        "frac_developed": [0.1, 0.1, 0.1],
    })
    layer = _build_redds_layer({"cells": cells, "redds": redds}, visible=True)
    assert len(layer["data"]) == 2  # the 999 redd was skipped


def test_visibility_flag_is_respected() -> None:
    """show_redds checkbox = False should produce an invisible layer."""
    cells = _make_cells()
    redds = pd.DataFrame({
        "redd_idx": [0], "cell_idx": [0], "eggs": [100],
        "species": ["X"], "frac_developed": [0.0],
    })
    layer = _build_redds_layer({"cells": cells, "redds": redds}, visible=False)
    assert layer["visible"] is False
