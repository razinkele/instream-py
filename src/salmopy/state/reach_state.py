"""ReachState — Structure-of-Arrays for reach data."""
from dataclasses import dataclass
import numpy as np


@dataclass
class ReachState:
    flow: np.ndarray
    temperature: np.ndarray
    turbidity: np.ndarray

    # Intermediate variables: (num_reaches, num_species)
    cmax_temp_func: np.ndarray
    max_swim_temp_term: np.ndarray
    resp_temp_term: np.ndarray

    scour_param: np.ndarray
    is_flow_peak: np.ndarray

    @classmethod
    def zeros(cls, num_reaches: int, num_species: int = 1) -> "ReachState":
        return cls(
            flow=np.zeros(num_reaches, dtype=np.float64),
            temperature=np.zeros(num_reaches, dtype=np.float64),
            turbidity=np.zeros(num_reaches, dtype=np.float64),
            cmax_temp_func=np.zeros((num_reaches, num_species), dtype=np.float64),
            max_swim_temp_term=np.zeros((num_reaches, num_species), dtype=np.float64),
            resp_temp_term=np.zeros((num_reaches, num_species), dtype=np.float64),
            scour_param=np.zeros(num_reaches, dtype=np.float64),
            is_flow_peak=np.zeros(num_reaches, dtype=bool),
        )
