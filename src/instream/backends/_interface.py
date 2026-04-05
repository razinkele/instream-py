"""Protocol classes defining the compute backend interface."""

from typing import Protocol, runtime_checkable
import numpy as np


@runtime_checkable
class ComputeBackend(Protocol):
    """Interface that all compute backends must implement."""

    def update_hydraulics(
        self,
        flow: float,
        table_flows: np.ndarray,
        depth_values: np.ndarray,
        vel_values: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]: ...

    def compute_light(
        self,
        julian_date: float,
        latitude: float,
        light_correction: float,
        shading: float,
        light_at_night: float,
        twilight_angle: float,
    ) -> tuple[float, float, float]: ...

    def compute_cell_light(
        self,
        depths: np.ndarray,
        irradiance: float,
        turbid_coef: float,
        turbidity: float,
        light_at_night: float,
        turbid_const: float = 0.0,
    ) -> np.ndarray: ...

    def growth_rate(
        self,
        lengths: np.ndarray,
        weights: np.ndarray,
        temperatures: np.ndarray,
        velocities: np.ndarray,
        depths: np.ndarray,
        **params,
    ) -> np.ndarray: ...

    def survival(
        self,
        lengths: np.ndarray,
        weights: np.ndarray,
        conditions: np.ndarray,
        temperatures: np.ndarray,
        depths: np.ndarray,
        **params,
    ) -> np.ndarray: ...

    def fitness_all(
        self, trout_arrays: dict, cell_arrays: dict, candidates: np.ndarray, **params
    ) -> tuple[np.ndarray, np.ndarray]: ...

    def deplete_resources(
        self,
        fish_order: np.ndarray,
        chosen_cells: np.ndarray,
        available_drift: np.ndarray,
        available_search: np.ndarray,
        **params,
    ) -> tuple[np.ndarray, np.ndarray]: ...

    def spawn_suitability(
        self,
        depths: np.ndarray,
        velocities: np.ndarray,
        frac_spawn: np.ndarray,
        **params,
    ) -> np.ndarray: ...

    def evaluate_logistic(self, x: np.ndarray, L1: float, L9: float) -> np.ndarray: ...

    def interp1d(
        self, x: np.ndarray, table_x: np.ndarray, table_y: np.ndarray
    ) -> np.ndarray: ...
