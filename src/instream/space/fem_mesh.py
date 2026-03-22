"""FEM mesh reader for River2D (.2dm), GMSH (.msh), and other formats via meshio."""

from pathlib import Path
from collections import defaultdict

import numpy as np
import meshio

from instream.state.cell_state import CellState


class FEMMesh:
    """Read a finite element mesh and produce CellState + neighbor indices.

    Each triangular element becomes a "cell" in the simulation.
    Cell area is computed from element geometry. Centroids from element vertex averages.
    Adjacency from shared edges between elements.

    Supported formats (via meshio):
    - River2D .2dm (SMS format)
    - GMSH .msh
    - Any format supported by meshio

    Usage:
        mesh = FEMMesh("river.2dm", reach_field="material_id")
        cell_state = mesh.to_cell_state(depth_flows, depth_values, vel_flows, vel_values)
        fem_space = FEMSpace(cell_state, mesh.neighbor_indices)
    """

    def __init__(
        self,
        mesh_path,
        reach_field=None,
        default_reach=0,
        dist_escape_default=100.0,
        num_hiding_default=5,
        frac_vel_shelter_default=0.1,
        frac_spawn_default=0.0,
    ):
        mesh_path = Path(mesh_path)
        if not mesh_path.exists():
            raise FileNotFoundError("Mesh file not found: {}".format(mesh_path))

        self._mesh = meshio.read(str(mesh_path))
        points = self._mesh.points[:, :2]  # 2D (x, y)

        # Collect triangular cells (the primary cell type for FEM meshes)
        tri_cells = None
        for block in self._mesh.cells:
            if block.type == "triangle":
                tri_cells = block.data
                break

        if tri_cells is None:
            raise ValueError("No triangular cells found in mesh file")

        n_cells = len(tri_cells)

        # Compute centroids
        self._centroids_x = np.mean(points[tri_cells, 0], axis=1)
        self._centroids_y = np.mean(points[tri_cells, 1], axis=1)

        # Compute areas (cross product formula)
        v0 = points[tri_cells[:, 0]]
        v1 = points[tri_cells[:, 1]]
        v2 = points[tri_cells[:, 2]]
        self._areas = 0.5 * np.abs(
            (v1[:, 0] - v0[:, 0]) * (v2[:, 1] - v0[:, 1])
            - (v2[:, 0] - v0[:, 0]) * (v1[:, 1] - v0[:, 1])
        )
        # Convert m^2 to cm^2
        self._areas *= 10_000.0

        # Reach assignment
        if reach_field and reach_field in self._mesh.cell_data:
            self._reach_idx = self._mesh.cell_data[reach_field][0].astype(np.int32)
        else:
            self._reach_idx = np.full(n_cells, default_reach, dtype=np.int32)

        # Default habitat properties (can be overridden by cell_data if available)
        self._dist_escape = np.full(n_cells, dist_escape_default, dtype=np.float64)
        self._num_hiding = np.full(n_cells, num_hiding_default, dtype=np.int32)
        self._frac_vel_shelter = np.full(
            n_cells, frac_vel_shelter_default, dtype=np.float64
        )
        self._frac_spawn = np.full(n_cells, frac_spawn_default, dtype=np.float64)

        # Build adjacency (shared edges)
        self._neighbor_indices = self._build_adjacency(tri_cells, n_cells)
        self._n_cells = n_cells

    @staticmethod
    def _build_adjacency(tri_cells, n_cells):
        """Build neighbor indices from shared triangle edges.

        Returns an (n_cells, max_neighbors) int32 array padded with -1.
        Two elements are neighbors if they share an edge (two vertices).
        """
        edge_to_cells = defaultdict(list)
        for ci, tri in enumerate(tri_cells):
            for j in range(3):
                edge = tuple(sorted([tri[j], tri[(j + 1) % 3]]))
                edge_to_cells[edge].append(ci)

        neighbors = defaultdict(set)
        for edge, cells in edge_to_cells.items():
            if len(cells) == 2:
                neighbors[cells[0]].add(cells[1])
                neighbors[cells[1]].add(cells[0])

        max_nbrs = max((len(v) for v in neighbors.values()), default=1)
        max_nbrs = max(max_nbrs, 1)
        result = np.full((n_cells, max_nbrs), -1, dtype=np.int32)
        for ci, nbrs in neighbors.items():
            for j, nb in enumerate(sorted(nbrs)):
                if j < max_nbrs:
                    result[ci, j] = nb
        return result

    @property
    def num_cells(self):
        return self._n_cells

    @property
    def neighbor_indices(self):
        return self._neighbor_indices

    @property
    def num_hiding_places(self):
        return self._num_hiding.copy()

    def to_cell_state(self, depth_flows, depth_values, vel_flows, vel_values):
        """Create CellState from this mesh + hydraulic tables.

        Parameters
        ----------
        depth_flows : ndarray, shape (num_depth_flows,)
        depth_values : ndarray, shape (num_cells, num_depth_flows)
        vel_flows : ndarray, shape (num_vel_flows,)
        vel_values : ndarray, shape (num_cells, num_vel_flows)
        """
        return CellState(
            area=self._areas,
            centroid_x=self._centroids_x,
            centroid_y=self._centroids_y,
            reach_idx=self._reach_idx,
            num_hiding_places=self._num_hiding,
            dist_escape=self._dist_escape,
            frac_vel_shelter=self._frac_vel_shelter,
            frac_spawn=self._frac_spawn,
            depth=np.zeros(self._n_cells, dtype=np.float64),
            velocity=np.zeros(self._n_cells, dtype=np.float64),
            light=np.zeros(self._n_cells, dtype=np.float64),
            available_drift=np.zeros(self._n_cells, dtype=np.float64),
            available_search=np.zeros(self._n_cells, dtype=np.float64),
            available_vel_shelter=np.zeros(self._n_cells, dtype=np.float64),
            available_hiding_places=self._num_hiding.copy(),
            depth_table_flows=depth_flows,
            depth_table_values=depth_values,
            vel_table_flows=vel_flows,
            vel_table_values=vel_values,
        )
