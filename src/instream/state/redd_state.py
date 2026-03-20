"""ReddState — Structure-of-Arrays for all redd data."""
from dataclasses import dataclass
import numpy as np


@dataclass
class ReddState:
    alive: np.ndarray
    species_idx: np.ndarray
    num_eggs: np.ndarray
    frac_developed: np.ndarray
    emerge_days: np.ndarray
    cell_idx: np.ndarray
    reach_idx: np.ndarray

    # Output tracking
    eggs_initial: np.ndarray
    eggs_lo_temp: np.ndarray
    eggs_hi_temp: np.ndarray
    eggs_dewatering: np.ndarray
    eggs_scour: np.ndarray

    @classmethod
    def zeros(cls, capacity: int) -> "ReddState":
        return cls(
            alive=np.zeros(capacity, dtype=bool),
            species_idx=np.zeros(capacity, dtype=np.int32),
            num_eggs=np.zeros(capacity, dtype=np.int32),
            frac_developed=np.zeros(capacity, dtype=np.float64),
            emerge_days=np.zeros(capacity, dtype=np.int32),
            cell_idx=np.full(capacity, -1, dtype=np.int32),
            reach_idx=np.full(capacity, -1, dtype=np.int32),
            eggs_initial=np.zeros(capacity, dtype=np.int32),
            eggs_lo_temp=np.zeros(capacity, dtype=np.int32),
            eggs_hi_temp=np.zeros(capacity, dtype=np.int32),
            eggs_dewatering=np.zeros(capacity, dtype=np.int32),
            eggs_scour=np.zeros(capacity, dtype=np.int32),
        )

    def num_alive(self) -> int:
        return int(np.sum(self.alive))
