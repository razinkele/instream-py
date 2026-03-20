"""Immutable parameter containers."""
from dataclasses import dataclass, field
import numpy as np


@dataclass(frozen=True)
class SpeciesParams:
    name: str
    cmax_A: float = 0.0
    cmax_B: float = 0.0
    weight_A: float = 0.0
    weight_B: float = 0.0
    # Interpolation tables (optional, default to empty)
    cmax_temp_table_x: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))
    cmax_temp_table_y: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float64))

    def __hash__(self):
        return hash(self.name)
