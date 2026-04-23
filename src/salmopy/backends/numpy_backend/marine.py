"""Numpy implementation of the MarineBackend protocol (v0.15.0).

Thin delegating adapter — the real formulae live in
:mod:`instream.marine.growth`, :mod:`instream.marine.survival`, and
:mod:`instream.marine.fishing`. Keeping the backend purely delegational
makes it straightforward to add a JAX or Numba counterpart later without
touching the domain orchestration.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Tuple

import numpy as np

from salmopy.marine.growth import marine_growth as _growth
from salmopy.marine.survival import marine_survival as _survival
from salmopy.marine.fishing import fishing_mortality as _fishing


class NumpyMarineBackend:
    """Vectorised numpy implementation of :class:`MarineBackend`."""

    # -- growth -----------------------------------------------------------

    def marine_growth(
        self,
        weights: np.ndarray,
        temperatures: np.ndarray,
        prey_indices: np.ndarray,
        conditions: np.ndarray,
        **species_params: Any,
    ) -> np.ndarray:
        return _growth(
            weights=weights,
            temperatures=temperatures,
            prey_indices=prey_indices,
            conditions=conditions,
            **species_params,
        )

    # -- survival ---------------------------------------------------------

    def marine_survival(
        self,
        lengths: np.ndarray,
        zone_indices: np.ndarray,
        temperatures: np.ndarray,
        days_since_ocean_entry: np.ndarray,
        cormorant_zone_indices: np.ndarray,
        config: Any,
    ) -> np.ndarray:
        return _survival(
            length=lengths,
            zone_idx=zone_indices,
            temperature=temperatures,
            days_since_ocean_entry=days_since_ocean_entry,
            cormorant_zone_indices=cormorant_zone_indices,
            config=config,
        )

    # -- fishing ----------------------------------------------------------

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
        return _fishing(
            lengths=lengths,
            zone_idx=zone_indices,
            current_date=current_date,
            zone_name_by_idx=zone_name_by_idx,
            gear_configs=gear_configs,
            min_legal_length=min_legal_length,
            rng=rng,
        )
