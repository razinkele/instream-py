"""v0.46 Task A3: Edit Model panel lasso-select feature.

Tests the centroid-in-polygon containment used by _lasso_apply.
"""
import geopandas as gpd
from shapely.geometry import Polygon


def test_centroid_in_polygon_picks_only_inside_cells():
    # 4x4 grid; lasso covers the central 2x2 cells (centroids at (1.5, 1.5)
    # to (2.5, 2.5))
    cells = []
    for x in range(4):
        for y in range(4):
            cells.append(Polygon([
                (x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)
            ]))
    gdf = gpd.GeoDataFrame(geometry=cells, crs="EPSG:4326")
    lasso = Polygon([(1.2, 1.2), (2.8, 1.2), (2.8, 2.8), (1.2, 2.8)])
    inside = gdf.geometry.centroid.within(lasso)
    assert int(inside.sum()) == 4  # central 2x2 = 4 cells
