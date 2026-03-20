"""FEMSpace — custom spatial container wrapping mesh backends."""
import numpy as np
from scipy.spatial import cKDTree
from instream.state.cell_state import CellState


class FEMSpace:
    """Spatial container for habitat cells with KD-tree indexing.

    Works with either PolygonMesh or FEMMesh backends — accepts a CellState
    and neighbor matrix, doesn't care how they were produced.
    """

    def __init__(self, cell_state: CellState, neighbor_indices: np.ndarray):
        self.cell_state = cell_state
        self.neighbor_indices = neighbor_indices
        self.num_cells = cell_state.area.shape[0]

        # Build KD-tree from centroids for radius queries
        centroids = np.column_stack([cell_state.centroid_x, cell_state.centroid_y])
        self._tree = cKDTree(centroids)

    def cells_in_radius(self, cell_idx: int, radius_cm: float) -> np.ndarray:
        """Return indices of all cells within radius of given cell."""
        point = [self.cell_state.centroid_x[cell_idx],
                 self.cell_state.centroid_y[cell_idx]]
        indices = self._tree.query_ball_point(point, r=radius_cm)
        return np.array(indices, dtype=np.int64)

    def get_neighbor_indices(self, cell_idx: int) -> np.ndarray:
        """Return neighbor indices for given cell (padded with -1)."""
        return self.neighbor_indices[cell_idx]

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
