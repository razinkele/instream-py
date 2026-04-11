"""Protocol classes defining the compute backend interface."""

from __future__ import annotations

import datetime
from typing import Any, Dict, Protocol, Tuple, runtime_checkable

import numpy as np


@runtime_checkable
class MarineBackend(Protocol):
    """Interface for marine-phase computations (inSALMON v0.15.0).

    Mirrors the design-document Section 7 protocol. All methods are pure:
    they accept ndarray inputs and return ndarray outputs without mutating
    shared state.
    """

    def marine_growth(
        self,
        weights: np.ndarray,
        temperatures: np.ndarray,
        prey_indices: np.ndarray,
        conditions: np.ndarray,
        **species_params: Any,
    ) -> np.ndarray:
        """Return daily weight delta in grams for each fish."""
        ...

    def marine_survival(
        self,
        lengths: np.ndarray,
        zone_indices: np.ndarray,
        temperatures: np.ndarray,
        days_since_ocean_entry: np.ndarray,
        cormorant_zone_indices: np.ndarray,
        **species_params: Any,
    ) -> np.ndarray:
        """Return combined daily natural survival probability (0..1)."""
        ...

    def fishing_mortality(
        self,
        lengths: np.ndarray,
        zone_indices: np.ndarray,
        current_date: datetime.date,
        zone_name_by_idx: list[str],
        gear_configs: Dict[str, Any],
        min_legal_length: float,
        rng: np.random.Generator,
    ) -> Tuple[np.ndarray, Dict[str, int]]:
        """Return (per-fish survival, {gear_name: num_killed}) tally."""
        ...


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
