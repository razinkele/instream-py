"""PolygonMesh — Shapefile-based polygon mesh reader for inSTREAM cells.

Reads a shapefile of habitat cell polygons and extracts cell attributes,
centroids, and spatial adjacency for use in the inSTREAM model.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

import geopandas as gpd
import numpy as np

from instream.state.cell_state import CellState


class PolygonMesh:
    """Polygon mesh loaded from an ESRI shapefile.

    Parameters
    ----------
    shapefile_path : str or Path
        Path to the .shp file.
    id_field : str
        Column name for cell IDs.
    reach_field : str
        Column name for reach names.
    area_field : str
        Column name for cell areas (in m²; will be converted to cm²).
    dist_escape_field : str
        Column name for distance-to-escape values (cm).
    hiding_field : str
        Column name for number of hiding places.
    shelter_field : str
        Column name for fraction velocity shelter.
    spawn_field : str
        Column name for fraction spawnable area.
    """

    def __init__(
        self,
        shapefile_path: Union[str, Path],
        *,
        id_field: str,
        reach_field: str,
        area_field: str,
        dist_escape_field: str,
        hiding_field: str,
        shelter_field: str,
        spawn_field: str,
    ) -> None:
        gdf = gpd.read_file(shapefile_path)

        self._num_cells: int = len(gdf)
        self._cell_ids: list[str] = gdf[id_field].astype(str).tolist()
        self._reach_names: list[str] = gdf[reach_field].astype(str).tolist()

        # Areas: m² → cm²
        self._areas: np.ndarray = gdf[area_field].to_numpy(dtype=np.float64) * 10_000.0

        # Other cell attributes
        self._dist_escape: np.ndarray = gdf[dist_escape_field].to_numpy(dtype=np.float64)
        self._num_hiding_places: np.ndarray = gdf[hiding_field].to_numpy(dtype=np.int32)
        self._frac_vel_shelter: np.ndarray = gdf[shelter_field].to_numpy(dtype=np.float64)
        self._frac_spawn: np.ndarray = gdf[spawn_field].to_numpy(dtype=np.float64)

        # Centroids from polygon geometries
        centroids = gdf.geometry.centroid
        self._centroids_x: np.ndarray = centroids.x.to_numpy(dtype=np.float64)
        self._centroids_y: np.ndarray = centroids.y.to_numpy(dtype=np.float64)

        # Build adjacency (touches or intersects, excluding self)
        self._neighbor_indices: np.ndarray = self._build_adjacency(gdf)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def num_cells(self) -> int:
        return self._num_cells

    @property
    def areas(self) -> np.ndarray:
        return self._areas

    @property
    def centroids_x(self) -> np.ndarray:
        return self._centroids_x

    @property
    def centroids_y(self) -> np.ndarray:
        return self._centroids_y

    @property
    def reach_names(self) -> list[str]:
        return self._reach_names

    @property
    def cell_ids(self) -> list[str]:
        return self._cell_ids

    @property
    def frac_spawn(self) -> np.ndarray:
        return self._frac_spawn

    @property
    def frac_vel_shelter(self) -> np.ndarray:
        return self._frac_vel_shelter

    @property
    def num_hiding_places(self) -> np.ndarray:
        return self._num_hiding_places

    @property
    def dist_escape(self) -> np.ndarray:
        return self._dist_escape

    @property
    def neighbor_indices(self) -> np.ndarray:
        return self._neighbor_indices

    # ------------------------------------------------------------------
    # Adjacency
    # ------------------------------------------------------------------
    @staticmethod
    def _build_adjacency(gdf: gpd.GeoDataFrame) -> np.ndarray:
        """Build a symmetric adjacency matrix using spatial index.

        Returns an (num_cells, max_neighbors) int32 array padded with -1.
        Two cells are neighbors if their geometries touch or intersect
        (but are not identical).
        """
        n = len(gdf)
        sindex = gdf.sindex
        neighbors: list[list[int]] = [[] for _ in range(n)]

        for i in range(n):
            geom_i = gdf.geometry.iloc[i]
            # Query spatial index for candidate neighbors
            candidates = list(sindex.query(geom_i, predicate="intersects"))
            for j in candidates:
                if j != i and gdf.geometry.iloc[j].intersects(geom_i):
                    if j not in neighbors[i]:
                        neighbors[i].append(j)
                    if i not in neighbors[j]:
                        neighbors[j].append(i)

        max_neighbors = max((len(nb) for nb in neighbors), default=0)
        if max_neighbors == 0:
            return np.full((n, 1), -1, dtype=np.int32)

        result = np.full((n, max_neighbors), -1, dtype=np.int32)
        for i, nb in enumerate(neighbors):
            for k, j in enumerate(nb):
                result[i, k] = j

        return result

    # ------------------------------------------------------------------
    # Conversion to CellState
    # ------------------------------------------------------------------
    def to_cell_state(
        self,
        depth_flows: np.ndarray,
        depth_values: np.ndarray,
        vel_flows: np.ndarray,
        vel_values: np.ndarray,
    ) -> CellState:
        """Create a CellState from this mesh and hydraulic lookup tables.

        Parameters
        ----------
        depth_flows : ndarray, shape (num_depth_flows,)
        depth_values : ndarray, shape (num_cells, num_depth_flows)
        vel_flows : ndarray, shape (num_vel_flows,)
        vel_values : ndarray, shape (num_cells, num_vel_flows)
        """
        n = self._num_cells

        # Build reach index: map unique reach names to integers
        unique_reaches = list(dict.fromkeys(self._reach_names))  # preserve order
        reach_to_idx = {name: idx for idx, name in enumerate(unique_reaches)}
        reach_idx = np.array(
            [reach_to_idx[r] for r in self._reach_names], dtype=np.int32
        )

        return CellState(
            area=self._areas.copy(),
            centroid_x=self._centroids_x.copy(),
            centroid_y=self._centroids_y.copy(),
            reach_idx=reach_idx,
            num_hiding_places=self._num_hiding_places.copy(),
            dist_escape=self._dist_escape.copy(),
            frac_vel_shelter=self._frac_vel_shelter.copy(),
            frac_spawn=self._frac_spawn.copy(),
            depth=np.zeros(n, dtype=np.float64),
            velocity=np.zeros(n, dtype=np.float64),
            light=np.zeros(n, dtype=np.float64),
            available_drift=np.zeros(n, dtype=np.float64),
            available_search=np.zeros(n, dtype=np.float64),
            available_vel_shelter=np.zeros(n, dtype=np.float64),
            available_hiding_places=np.zeros(n, dtype=np.int32),
            depth_table_flows=depth_flows.copy(),
            depth_table_values=depth_values.copy(),
            vel_table_flows=vel_flows.copy(),
            vel_table_values=vel_values.copy(),
        )
