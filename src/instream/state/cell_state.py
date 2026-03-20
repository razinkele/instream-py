"""CellState — Structure-of-Arrays for habitat cell data."""
from dataclasses import dataclass
import numpy as np


@dataclass
class CellState:
    # Static attributes
    area: np.ndarray
    centroid_x: np.ndarray
    centroid_y: np.ndarray
    reach_idx: np.ndarray
    num_hiding_places: np.ndarray
    dist_escape: np.ndarray
    frac_vel_shelter: np.ndarray
    frac_spawn: np.ndarray

    # Dynamic state
    depth: np.ndarray
    velocity: np.ndarray
    light: np.ndarray

    # Resource availability
    available_drift: np.ndarray
    available_search: np.ndarray
    available_vel_shelter: np.ndarray
    available_hiding_places: np.ndarray

    # Hydraulic lookup tables
    depth_table_flows: np.ndarray     # (num_flows,)
    depth_table_values: np.ndarray    # (num_cells, num_flows)
    vel_table_flows: np.ndarray       # (num_flows,)
    vel_table_values: np.ndarray      # (num_cells, num_flows)

    @classmethod
    def zeros(cls, num_cells: int, num_flows: int = 1) -> "CellState":
        return cls(
            area=np.zeros(num_cells, dtype=np.float64),
            centroid_x=np.zeros(num_cells, dtype=np.float64),
            centroid_y=np.zeros(num_cells, dtype=np.float64),
            reach_idx=np.zeros(num_cells, dtype=np.int32),
            num_hiding_places=np.zeros(num_cells, dtype=np.int32),
            dist_escape=np.zeros(num_cells, dtype=np.float64),
            frac_vel_shelter=np.zeros(num_cells, dtype=np.float64),
            frac_spawn=np.zeros(num_cells, dtype=np.float64),
            depth=np.zeros(num_cells, dtype=np.float64),
            velocity=np.zeros(num_cells, dtype=np.float64),
            light=np.zeros(num_cells, dtype=np.float64),
            available_drift=np.zeros(num_cells, dtype=np.float64),
            available_search=np.zeros(num_cells, dtype=np.float64),
            available_vel_shelter=np.zeros(num_cells, dtype=np.float64),
            available_hiding_places=np.zeros(num_cells, dtype=np.int32),
            depth_table_flows=np.zeros(num_flows, dtype=np.float64),
            depth_table_values=np.zeros((num_cells, num_flows), dtype=np.float64),
            vel_table_flows=np.zeros(num_flows, dtype=np.float64),
            vel_table_values=np.zeros((num_cells, num_flows), dtype=np.float64),
        )
