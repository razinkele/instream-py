"""Tests for create_model_grid hexagon generation."""
import sys
import os

# create_model_grid uses bare `from modules.xxx import ...` which resolves
# relative to the app/ directory — add it to sys.path before importing.
_APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(_APP_DIR))


def test_hexagon_is_flat_top():
    from app.modules.create_model_grid import _hexagon
    h = _hexagon(0, 0, 10)
    coords = list(h.exterior.coords)[:-1]
    ys = sorted([c[1] for c in coords], reverse=True)
    # Flat-top: top two vertices have the same y-coordinate
    assert abs(ys[0] - ys[1]) < 0.01, f"Not flat-top: top y-values {ys[0]:.2f} vs {ys[1]:.2f}"


def test_hexagon_area():
    import math
    from app.modules.create_model_grid import _hexagon
    h = _hexagon(0, 0, 10)
    expected = (3 * math.sqrt(3) / 2) * 10**2  # regular hexagon area formula
    assert abs(h.area - expected) < 0.1, f"Area {h.area} != expected {expected}"


def _small_lithuanian_polygon():
    """Small water polygon (~13k m²) in UTM zone 34N — sized to trigger the
    min_overlap filter bug: smaller than one 200 m hex cell (~104k m²)."""
    from shapely.geometry import Polygon
    # WGS84; detect_utm_epsg picks EPSG:32634 for this centroid.
    # half_lon=0.0004, half_lat=0.0003 → ≈ 100 m x 134 m in UTM → ≈ 13k m²
    lon_c, lat_c = 21.10, 55.7165
    half_lon, half_lat = 0.0004, 0.0003
    return Polygon(
        [
            (lon_c - half_lon, lat_c - half_lat),
            (lon_c + half_lon, lat_c - half_lat),
            (lon_c + half_lon, lat_c + half_lat),
            (lon_c - half_lon, lat_c + half_lat),
            (lon_c - half_lon, lat_c - half_lat),
        ]
    )


def test_generate_cells_small_water_polygon_does_not_crash():
    """Regression: water/sea polygon smaller than one hex cell used to crash
    at `gpd.GeoDataFrame(records, crs=…)` because the min_overlap filter
    rejected every raw cell, leaving an empty records list. See
    `memory/project_generate_cells_small_polygon_bug.md`."""
    from app.modules.create_model_grid import generate_cells

    reaches = {
        "reach_1": {
            "segments": [_small_lithuanian_polygon()],
            "type": "water",
            "properties": [{}],
        }
    }
    # Default water cell_size from the panel is 200 m — triggers the bug.
    cells = generate_cells(reaches, cell_size=200, cell_shape="hexagonal")
    assert cells is not None
    # Must return AT LEAST one cell: the polygon intersects the grid, so
    # users who selected a small water body expect cells to represent it.
    assert len(cells) > 0, "expected at least one cell for a non-empty small water polygon"
    # Output shape contract
    for col in (
        "cell_id", "reach_name", "area", "dist_escape",
        "num_hiding", "frac_vel_shelter", "frac_spawn", "geometry",
    ):
        assert col in cells.columns, f"missing column {col!r}"
    assert cells.crs is not None
    # to_crs("EPSG:4326") is applied at the end
    assert cells.crs.to_epsg() == 4326


def test_generate_cells_empty_reaches_returns_typed_empty_gdf():
    """`generate_cells` with no geometries returns a typed empty GeoDataFrame
    (not None, not a crash) so downstream `pd.concat` paths stay happy."""
    from app.modules.create_model_grid import generate_cells

    cells = generate_cells({}, cell_size=200, cell_shape="hexagonal")
    assert cells is not None
    assert len(cells) == 0
    assert "geometry" in cells.columns
