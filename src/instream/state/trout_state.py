"""TroutState — Structure-of-Arrays for all trout agent data."""

from dataclasses import dataclass
import numpy as np


@dataclass
class TroutState:
    """All trout state as parallel numpy arrays. Shape: (capacity,)."""

    alive: np.ndarray
    species_idx: np.ndarray
    length: np.ndarray
    weight: np.ndarray
    condition: np.ndarray
    age: np.ndarray
    cell_idx: np.ndarray
    reach_idx: np.ndarray
    activity: np.ndarray  # int enum: 0=drift, 1=search, 2=hide, 3=guard, 4=hold
    sex: np.ndarray  # int enum: 0=female, 1=male
    superind_rep: np.ndarray
    life_history: np.ndarray  # LifeStage IntEnum (see agents.life_stage)
    in_shelter: np.ndarray
    spawned_this_season: np.ndarray
    last_growth_rate: np.ndarray
    fitness_memory: np.ndarray

    # Within-day memory: shape (capacity, max_steps_per_day)
    growth_memory: np.ndarray
    consumption_memory: np.ndarray
    survival_memory: np.ndarray

    # Marine state (inert for freshwater-only runs)
    zone_idx: np.ndarray          # int32, -1 = freshwater
    sea_winters: np.ndarray       # int32
    smolt_date: np.ndarray        # int32, ordinal day of ocean entry
    natal_reach_idx: np.ndarray   # int32, -1 = not set
    smolt_readiness: np.ndarray   # float64, 0-1

    # Cached intermediates
    resp_std_wt_term: np.ndarray
    max_speed_len_term: np.ndarray
    cmax_wt_term: np.ndarray

    @classmethod
    def zeros(cls, capacity: int, max_steps_per_day: int = 4) -> "TroutState":
        return cls(
            alive=np.zeros(capacity, dtype=bool),
            species_idx=np.zeros(capacity, dtype=np.int32),
            length=np.zeros(capacity, dtype=np.float64),
            weight=np.zeros(capacity, dtype=np.float64),
            condition=np.zeros(capacity, dtype=np.float64),
            age=np.zeros(capacity, dtype=np.int32),
            cell_idx=np.full(capacity, -1, dtype=np.int32),
            reach_idx=np.full(capacity, -1, dtype=np.int32),
            activity=np.zeros(capacity, dtype=np.int32),
            sex=np.zeros(capacity, dtype=np.int32),
            superind_rep=np.ones(capacity, dtype=np.int32),
            life_history=np.zeros(capacity, dtype=np.int32),
            in_shelter=np.zeros(capacity, dtype=bool),
            spawned_this_season=np.zeros(capacity, dtype=bool),
            last_growth_rate=np.zeros(capacity, dtype=np.float64),
            fitness_memory=np.zeros(capacity, dtype=np.float64),
            zone_idx=np.full(capacity, -1, dtype=np.int32),
            sea_winters=np.zeros(capacity, dtype=np.int32),
            smolt_date=np.zeros(capacity, dtype=np.int32),
            natal_reach_idx=np.full(capacity, -1, dtype=np.int32),
            smolt_readiness=np.zeros(capacity, dtype=np.float64),
            growth_memory=np.zeros((capacity, max_steps_per_day), dtype=np.float64),
            consumption_memory=np.zeros(
                (capacity, max_steps_per_day), dtype=np.float64
            ),
            survival_memory=np.zeros((capacity, max_steps_per_day), dtype=np.float64),
            resp_std_wt_term=np.zeros(capacity, dtype=np.float64),
            max_speed_len_term=np.zeros(capacity, dtype=np.float64),
            cmax_wt_term=np.zeros(capacity, dtype=np.float64),
        )

    def num_alive(self) -> int:
        return int(np.sum(self.alive))

    def alive_indices(self) -> np.ndarray:
        return np.where(self.alive)[0]

    def first_dead_slot(self) -> int:
        dead = np.where(~self.alive)[0]
        return int(dead[0]) if len(dead) > 0 else -1
