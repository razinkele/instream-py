"""ZoneState — Structure-of-Arrays for marine zone environmental conditions."""
from dataclasses import dataclass
import numpy as np


@dataclass
class ZoneState:
    """Environmental conditions for marine zones. Shape: (num_zones,)."""
    temperature: np.ndarray     # deg C
    salinity: np.ndarray        # PSU
    prey_index: np.ndarray      # 0-1, normalized from chlorophyll-a
    predation_risk: np.ndarray  # 0-1, seal/cormorant pressure
    area_km2: np.ndarray        # zone extent

    @classmethod
    def zeros(cls, num_zones: int) -> "ZoneState":
        return cls(
            temperature=np.zeros(num_zones, dtype=np.float64),
            salinity=np.zeros(num_zones, dtype=np.float64),
            prey_index=np.zeros(num_zones, dtype=np.float64),
            predation_risk=np.zeros(num_zones, dtype=np.float64),
            area_km2=np.zeros(num_zones, dtype=np.float64),
        )
