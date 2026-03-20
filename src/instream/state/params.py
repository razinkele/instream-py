"""Immutable parameter containers.

NOTE: SpeciesParams is intentionally minimal for Phase 0. It will be extended
with all ~90 species parameters (resp_A/B/C/D, mort_*, trout_*, redd_*, etc.)
as needed by later phases (Phase 3: growth, Phase 4: fitness, Phase 5: survival).
"""
from dataclasses import dataclass, field
import numpy as np


def _readonly_array(dtype=np.float64):
    """Factory for empty read-only numpy arrays (used as frozen dataclass defaults)."""
    def factory():
        arr = np.array([], dtype=dtype)
        arr.flags.writeable = False
        return arr
    return factory


@dataclass(frozen=True)
class SpeciesParams:
    """Immutable species parameters. Numpy arrays are made read-only after creation.

    TODO: Extend with all species parameters as needed by later phases.
    Currently only carries fields needed for Phase 0 config roundtrip testing.
    """
    name: str
    cmax_A: float = 0.0
    cmax_B: float = 0.0
    weight_A: float = 0.0
    weight_B: float = 0.0
    # Interpolation tables (optional, default to empty read-only arrays)
    cmax_temp_table_x: np.ndarray = field(default_factory=_readonly_array())
    cmax_temp_table_y: np.ndarray = field(default_factory=_readonly_array())
    # Max swim speed temperature term coefficients: C*T² + D*T + E
    max_speed_C: float = 0.0
    max_speed_D: float = 0.0
    max_speed_E: float = 0.0
    # Respiration temperature term coefficient: exp(resp_C * T²)
    resp_C: float = 0.0

    def __post_init__(self):
        # Make numpy arrays read-only to enforce true immutability
        for fld in ("cmax_temp_table_x", "cmax_temp_table_y"):
            arr = getattr(self, fld)
            if isinstance(arr, np.ndarray) and arr.flags.writeable:
                arr.flags.writeable = False

    def __hash__(self):
        return hash(self.name)
