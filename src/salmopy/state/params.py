"""Immutable parameter containers.

All ~90 species parameters from SpeciesConfig are mirrored here as frozen
dataclass fields, making SpeciesParams the authoritative runtime container.
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

    Contains all numeric species parameters from SpeciesConfig.
    String fields (display_color, spawn_start_day, spawn_end_day) and
    interpolation table dicts are handled separately.
    """

    name: str

    # --- Consumption ---
    cmax_A: float = 0.0
    cmax_B: float = 0.0

    # --- Weight ---
    weight_A: float = 0.0
    weight_B: float = 0.0

    # --- Interpolation tables (optional, default to empty read-only arrays) ---
    cmax_temp_table_x: np.ndarray = field(default_factory=_readonly_array())
    cmax_temp_table_y: np.ndarray = field(default_factory=_readonly_array())

    # --- Anadromous flag ---
    is_anadromous: bool = False

    # --- Capture / detection ---
    capture_R1: float = 0.0
    capture_R9: float = 0.0

    # --- Emergence ---
    emerge_length_min: float = 0.0
    emerge_length_mode: float = 0.0
    emerge_length_max: float = 0.0

    # --- Reactive distance ---
    react_dist_A: float = 0.0
    react_dist_B: float = 0.0
    turbid_threshold: float = 0.0
    turbid_min: float = 0.0
    turbid_exp: float = 0.0
    light_threshold: float = 0.0
    light_min: float = 0.0
    light_exp: float = 0.0

    # --- Energetics ---
    energy_density: float = 0.0
    fitness_horizon: float = 0.0
    fitness_length: float = 0.0
    fitness_memory_frac: float = 0.0

    # --- Swimming ---
    max_speed_A: float = 0.0
    max_speed_B: float = 0.0
    max_speed_C: float = 0.0
    max_speed_D: float = 0.0
    max_speed_E: float = 0.0

    # --- Migration ---
    migrate_fitness_L1: float = 0.0
    migrate_fitness_L9: float = 0.0

    # --- Movement ---
    move_radius_max: float = 0.0
    move_radius_L1: float = 0.0
    move_radius_L9: float = 0.0

    # --- Piscivory ---
    pisciv_length: float = 0.0

    # --- Respiration ---
    resp_A: float = 0.0
    resp_B: float = 0.0
    resp_C: float = 0.0
    resp_D: float = 0.0
    resp_ref_temp: float = 15.0  # Q10 anchor (degC); conventional salmonid metabolic standard

    # --- Search ---
    search_area: float = 0.0

    # --- Spawning ---
    spawn_defense_area: float = 0.0  # legacy cm² - kept for back-compat
    spawn_defense_area_m: float = 0.0  # Arc E canonical meters
    spawn_egg_viability: float = 0.0
    spawn_fecund_mult: float = 0.0
    spawn_fecund_exp: float = 0.0
    spawn_suitability_tol: float = 0.0
    spawn_max_flow_change: float = 0.0
    spawn_max_temp: float = 0.0
    spawn_min_age: float = 0.0
    spawn_min_length: float = 0.0
    spawn_min_cond: float = 0.0
    spawn_min_temp: float = 0.0
    spawn_prob: float = 0.0
    spawn_wt_loss_fraction: float = 0.0

    # --- Mortality: high temp ---
    mort_high_temp_T1: float = 0.0
    mort_high_temp_T9: float = 0.0
    mort_strand_survival_when_dry: float = 0.0
    mort_condition_S_at_K8: float = 0.0
    mort_condition_S_at_K5: float = 0.0

    # --- Mortality: terrestrial predation ---
    mort_terr_pred_L1: float = 0.0
    mort_terr_pred_L9: float = 0.0
    mort_terr_pred_D1: float = 0.0
    mort_terr_pred_D9: float = 0.0
    mort_terr_pred_V1: float = 0.0
    mort_terr_pred_V9: float = 0.0
    mort_terr_pred_I1: float = 0.0
    mort_terr_pred_I9: float = 0.0
    mort_terr_pred_H1: float = 0.0
    mort_terr_pred_H9: float = 0.0
    mort_terr_pred_hiding_factor: float = 0.0

    # --- Mortality: fish predation ---
    mort_fish_pred_L1: float = 0.0
    mort_fish_pred_L9: float = 0.0
    mort_fish_pred_D1: float = 0.0
    mort_fish_pred_D9: float = 0.0
    mort_fish_pred_I1: float = 0.0
    mort_fish_pred_I9: float = 0.0
    mort_fish_pred_hiding_factor: float = 0.0
    mort_fish_pred_P1: float = 0.0
    mort_fish_pred_P9: float = 0.0
    mort_fish_pred_T1: float = 0.0
    mort_fish_pred_T9: float = 0.0

    # --- Redd mortality ---
    mort_redd_dewater_surv: float = 0.0
    mort_redd_hi_temp_T1: float = 0.0
    mort_redd_hi_temp_T9: float = 0.0
    mort_redd_lo_temp_T1: float = 0.0
    mort_redd_lo_temp_T9: float = 0.0
    mort_redd_scour_depth: float = 0.0

    # --- Redd development ---
    redd_devel_A: float = 0.0
    redd_devel_B: float = 0.0
    redd_devel_C: float = 0.0
    redd_area: float = 0.0

    # --- Superindividual ---
    superind_max_rep: float = 0.0
    superind_max_length: float = 0.0

    # --- New InSALMON parameters ---
    mort_condition_K_crit: float = 0.8
    fecundity_noise: float = 0.0
    spawn_date_jitter_days: int = 0
    outmigration_max_prob: float = 0.1
    outmigration_min_length: float = 8.0
    fitness_growth_weight: float = 1.0

    def __post_init__(self):
        # Make numpy arrays read-only to enforce true immutability
        for fld in ("cmax_temp_table_x", "cmax_temp_table_y"):
            arr = getattr(self, fld)
            if isinstance(arr, np.ndarray) and arr.flags.writeable:
                arr.flags.writeable = False

    def __hash__(self):
        return hash(self.name)
