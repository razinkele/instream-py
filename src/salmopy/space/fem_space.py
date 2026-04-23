"""FEMSpace — custom spatial container wrapping mesh backends."""
import numpy as np
from scipy.spatial import cKDTree
from salmopy.state.cell_state import CellState


class FEMSpace:
    """Spatial container for habitat cells with KD-tree indexing.

    Works with either PolygonMesh or FEMMesh backends — accepts a CellState
    and neighbor matrix, doesn't care how they were produced.
    """

    def __init__(self, cell_state: CellState, neighbor_indices: np.ndarray):
        self.cell_state = cell_state
        self.neighbor_indices = neighbor_indices
        self.num_cells = cell_state.area.shape[0]

        # Validate that depth and velocity tables share the same flow breakpoints.
        # inSTREAM format guarantees this; if they ever differ, the backend
        # signature must be extended to accept separate flow arrays.
        if len(cell_state.depth_table_flows) > 0 and len(cell_state.vel_table_flows) > 0:
            if not np.array_equal(cell_state.depth_table_flows, cell_state.vel_table_flows):
                raise ValueError(
                    "Depth and velocity tables have different flow breakpoints. "
                    "This is not supported — inSTREAM format requires identical flows."
                )

        # Build KD-tree from centroids for radius queries
        # NOTE: centroids are in CRS units (typically meters for projected CRS).
        # The radius parameter in cells_in_radius() must use the same units.
        centroids = np.column_stack([cell_state.centroid_x, cell_state.centroid_y])
        self._tree = cKDTree(centroids)

    def cells_in_radius(self, cell_idx: int, radius: float) -> np.ndarray:
        """Return indices of all cells within radius of given cell.

        Parameters
        ----------
        cell_idx : int
        radius : float
            Search radius in CRS units (same as centroid coordinates —
            typically meters for projected CRS).
        """
        point = [self.cell_state.centroid_x[cell_idx],
                 self.cell_state.centroid_y[cell_idx]]
        indices = self._tree.query_ball_point(point, r=radius)
        return np.array(indices, dtype=np.int64)

    def get_neighbor_indices(self, cell_idx: int) -> np.ndarray:
        """Return neighbor indices for given cell (padded with -1)."""
        return self.neighbor_indices[cell_idx]

    def precompute_geometry_candidates(self, move_radius_max: float) -> None:
        """Pre-compute geometry-based candidate cells for each cell (CSR format).

        For each cell, stores all cells within *move_radius_max* plus direct
        neighbors.  Result is stored as CSR arrays (_geo_offsets, _geo_flat,
        _geo_dist2) for O(1) lookup at runtime.
        """
        cs = self.cell_state
        n = self.num_cells
        parts = []
        dist2_parts = []
        offsets = np.zeros(n + 1, dtype=np.int64)

        for c in range(n):
            indices = self._tree.query_ball_point(
                [cs.centroid_x[c], cs.centroid_y[c]], move_radius_max
            )
            ni = self.neighbor_indices[c]
            neighbors = ni[ni >= 0]
            all_cands = np.unique(np.concatenate([
                np.array(indices, dtype=np.int32),
                neighbors.astype(np.int32),
                np.array([c], dtype=np.int32),
            ]))
            dx = cs.centroid_x[all_cands] - cs.centroid_x[c]
            dy = cs.centroid_y[all_cands] - cs.centroid_y[c]
            d2 = dx * dx + dy * dy
            parts.append(all_cands)
            dist2_parts.append(d2)
            offsets[c + 1] = offsets[c] + len(all_cands)

        self._geo_offsets = offsets
        self._geo_flat = np.concatenate(parts).astype(np.int32)
        self._geo_dist2 = np.concatenate(dist2_parts).astype(np.float64)
        self._geo_radius_max = move_radius_max

    def update_hydraulics(self, flow: float, backend) -> None:
        """Update depth and velocity for all cells at given flow."""
        depths, velocities = backend.update_hydraulics(
            flow,
            self.cell_state.depth_table_flows,
            self.cell_state.depth_table_values,
            self.cell_state.vel_table_values,
        )
        self.cell_state.depth[:] = depths
        self.cell_state.velocity[:] = velocities
