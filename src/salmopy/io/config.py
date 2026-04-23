"""Configuration system for Salmopy-py.

Loads YAML configuration files and converts NetLogo .nls parameter files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import yaml
import math

from pydantic import BaseModel, field_validator, model_validator

from salmopy.state.params import SpeciesParams


# ---------------------------------------------------------------------------
# Pydantic config models
# ---------------------------------------------------------------------------


class SimulationConfig(BaseModel):
    start_date: str
    end_date: str
    output_frequency: int = 1
    output_units: str = "days"
    seed: int = 0
    census_days: list[str] = []
    census_years_to_skip: int = 0
    shuffle_years: bool = False
    shuffle_seed: int = 0
    population_file: str = ""
    adult_arrival_file: str = ""

    # Harvest
    harvest_file: str = ""
    harvest_catch_rate: float = 0.0
    harvest_min_length: float = 0.0
    harvest_bag_limit: int = 999999
    harvest_season_start: str = ""
    harvest_season_end: str = ""

    # P3.4: legacy inputs sometimes list species names that are not
    # declared in the config's `species:` map. Historically this emitted
    # a warning and silently remapped those fish to species index 0,
    # corrupting the simulation without a visible error. The model now
    # fails loudly at init by default. Setting this flag to True
    # restores the legacy warn+remap behaviour for backward compatibility
    # with older population files.
    allow_unknown_species_remap: bool = False

    # WGBAST Arc L: path to the WGBAST M74 YSFM CSV (per-year, per-river
    # yolk-sac-fry mortality fraction). When set, the egg→fry emergence
    # hook applies a binomial cull based on the natal reach's `river_name`
    # and the current simulation year. Reference: Vuorinen et al. 2021,
    # DOI 10.1080/10236244.2021.1941942.
    m74_forcing_csv: str | None = None


class PerformanceConfig(BaseModel):
    backend: str = "numpy"
    device: str = "cpu"
    trout_capacity: int = 2000
    redd_capacity: int = 500
    jit_warmup: bool = False


class SpatialConfig(BaseModel):
    backend: str = "shapefile"
    mesh_file: str = ""
    gis_properties: Dict[str, str] = {}


class LightConfig(BaseModel):
    latitude: float = 0.0
    light_correction: float = 1.0
    light_at_night: float = 0.0
    twilight_angle: float = 6.0


class HatcheryStockingConfig(BaseModel):
    """One hatchery stocking event for a species.

    Added in v0.17.0 (InSALMON extension — no NetLogo counterpart).
    Stocked fish get ``is_hatchery=True`` in TroutState.

    ``release_shock_survival`` is the fraction of the stocked batch that
    survives the immediate release (first ~48 hours): handling stress,
    acclimation, and the initial predation spike. Literature range
    0.3-0.8 depending on hatchery practice and release method
    (soft release vs truck-and-dump); see Saloniemi et al. 2004.

    Distinct from ``MarineConfig.hatchery_predator_naivety_multiplier``
    which models the longer-term (first 2-4 weeks) cormorant-predation
    vulnerability of hatchery-naive smolts. Both apply; they represent
    different phases of the hatchery disadvantage.
    """

    num_fish: int
    reach: str
    date: str                          # ISO 8601 YYYY-MM-DD
    length_mean: float = 15.0
    length_sd: float = 1.5
    release_shock_survival: float = 0.7


class SpeciesConfig(BaseModel, extra="allow"):
    """Species parameters — all species-specific values from the NLS file.

    Uses extra='allow' so every parameter from the YAML is preserved
    as an attribute without having to enumerate all ~100 fields.
    Core fields that tests rely on are declared explicitly.
    """

    is_anadromous: bool = False
    display_color: str = "brown"

    # v0.17.0 — optional hatchery stocking (InSALMON extension)
    hatchery_stocking: Optional[HatcheryStockingConfig] = None

    # v0.17.0 — iteroparous spawning (InSALMON extension, no NetLogo ref)
    # kelt_survival_prob is river-exit survival, NOT realized iteroparity.
    kelt_survival_prob: float = 0.25
    min_kelt_condition: float = 0.5

    # Consumption
    cmax_A: float = 0.0
    cmax_B: float = 0.0
    cmax_temp_table: Dict[float, float] = {}

    # Weight
    weight_A: float = 0.0
    weight_B: float = 0.0

    # Capture / detection
    capture_R1: float = 0.0
    capture_R9: float = 0.0

    # Emergence
    emerge_length_min: float = 0.0
    emerge_length_mode: float = 0.0
    emerge_length_max: float = 0.0

    # Reactive distance
    react_dist_A: float = 0.0
    react_dist_B: float = 0.0
    turbid_threshold: float = 0.0
    turbid_min: float = 0.0
    turbid_exp: float = 0.0
    light_threshold: float = 0.0
    light_min: float = 0.0
    light_exp: float = 0.0

    # Energetics
    energy_density: float = 0.0
    fitness_horizon: float = 0.0
    fitness_length: float = 0.0
    fitness_memory_frac: float = 0.0

    # Swimming
    max_speed_A: float = 0.0
    max_speed_B: float = 0.0
    max_speed_C: float = 0.0
    max_speed_D: float = 0.0
    max_speed_E: float = 0.0

    # Migration
    migrate_fitness_L1: float = 0.0
    migrate_fitness_L9: float = 0.0
    parr_promotion_length: float = 4.0  # Arc D: anadromous FRY->PARR length threshold (cm)

    # Movement
    move_radius_max: float = 0.0
    move_radius_L1: float = 0.0
    move_radius_L9: float = 0.0

    # Piscivory
    pisciv_length: float = 0.0

    # Respiration
    resp_A: float = 0.0
    resp_B: float = 0.0
    resp_C: float = 0.0
    resp_D: float = 0.0
    resp_ref_temp: float = 15.0  # Q10 anchor (degC); conventional salmonid standard

    # Search
    search_area: float = 0.0

    # Spawning
    #
    # Redd-defense semantics (v0.19.0 reconciliation with NetLogo InSALMO):
    #
    # * ``spawn_defense_area`` — Python semantic (shipped since v0.12.0):
    #   minimum *Euclidean distance* in cm from the centroid of any existing
    #   live redd. Used directly by ``select_spawn_cell`` as a radius filter.
    #
    # * ``spawn_defense_area_m2`` — NetLogo InSALMO semantic: the actual
    #   defended *area* in m² around a redd. When set (and
    #   ``spawn_defense_area`` is 0), a Pydantic model_validator converts
    #   it to an equivalent circular-disk radius in cm:
    #
    #       r_cm = sqrt(area_m2 * 10_000 / pi)
    #
    #   (area_m2 × 10_000 = area_cm²; sqrt(area_cm²/pi) = radius_cm.)
    #
    # Users should use **exactly one** of the two fields. Setting both is
    # allowed but ``spawn_defense_area`` (cm) wins and the m² field is
    # ignored, matching the "Python ships cm, NetLogo uses m²" precedence.
    spawn_defense_area: float = 0.0
    spawn_defense_area_m2: float = 0.0
    # P3.5a: canonical meters form. Computed by the model_validator below
    # when one of the legacy fields is set. `select_spawn_cell` in
    # `instream/modules/spawning.py` uses this (and only this) as a
    # distance threshold in the mesh CRS (meters). Setting this field
    # directly wins over the cm/m² legacy fields.
    spawn_defense_area_m: float = 0.0
    # P3.5b: radius in meters used when scanning candidate cells for
    # spawning. Defaults to 0.0, in which case model_day_boundary falls
    # back to ``move_radius_max * 0.1`` (legacy behaviour; the factor
    # encodes "spawn search is ~10% of daily movement radius").
    spawn_search_radius_m: float = 0.0
    spawn_egg_viability: float = 0.0
    spawn_fecund_mult: float = 0.0
    spawn_fecund_exp: float = 0.0
    spawn_suitability_tol: float = 0.0
    spawn_start_day: str = ""
    spawn_end_day: str = ""
    spawn_max_flow_change: float = 0.0
    spawn_max_temp: float = 0.0
    spawn_min_age: float = 0.0
    spawn_min_length: float = 0.0
    spawn_min_cond: float = 0.0
    spawn_min_temp: float = 0.0
    spawn_prob: float = 0.0
    spawn_wt_loss_fraction: float = 0.0

    # Mortality — high temp
    mort_high_temp_T1: float = 0.0
    mort_high_temp_T9: float = 0.0
    mort_strand_survival_when_dry: float = 0.0
    mort_condition_S_at_K8: float = 0.0
    mort_condition_S_at_K5: float = 0.0

    # Mortality — terrestrial predation
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

    # Mortality — fish predation
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

    # Redd mortality
    mort_redd_dewater_surv: float = 0.0
    mort_redd_hi_temp_T1: float = 0.0
    mort_redd_hi_temp_T9: float = 0.0
    mort_redd_lo_temp_T1: float = 0.0
    mort_redd_lo_temp_T9: float = 0.0
    mort_redd_scour_depth: float = 0.0

    # Redd development
    redd_devel_A: float = 0.0
    redd_devel_B: float = 0.0
    redd_devel_C: float = 0.0
    redd_area: float = 0.0

    # Starvation mortality (HexSimPy ED integration)
    mass_floor_fraction: float = 0.5   # fraction of peak weight below which starvation kicks in
    mass_floor_survival: float = 0.9   # daily survival probability when starving

    # Superindividual
    superind_max_rep: float = 0.0
    superind_max_length: float = 0.0

    # Spawning suitability tables
    spawn_depth_table: Dict[float, float] = {}
    spawn_vel_table: Dict[float, float] = {}

    @field_validator(
        "spawn_prob",
        "spawn_egg_viability",
        "mort_strand_survival_when_dry",
        mode="after",
    )
    @classmethod
    def _check_probability_bounds(cls, v: float, info) -> float:
        """v0.43.5 Task A2: probability fields must lie in [0, 1].

        Length-field validators were considered but dropped: several length
        fields use negative sentinel values (e.g. -9.0) to mean "no minimum
        constraint" in NetLogo-heritage configs.
        """
        if not (0.0 <= v <= 1.0):
            raise ValueError(
                f"{info.field_name} is a probability and must lie in [0, 1]; "
                f"got {v!r}."
            )
        return v

    @model_validator(mode="after")
    def _reconcile_defense_area_semantics(self) -> "SpeciesConfig":
        """Reconcile the three spawn-defense fields.

        Precedence:
          1. ``spawn_defense_area_m`` (canonical) — used as-is.
          2. ``spawn_defense_area`` (legacy cm) — radius in cm, converted to m.
          3. ``spawn_defense_area_m2`` (NetLogo area in m²) — converted to
             an equivalent circular-disk radius in m: sqrt(area_m2 / pi).

        Also backfills the legacy cm field for any downstream callers that
        still read it (unit tests, serialisation round-trips).
        """
        if self.spawn_defense_area_m > 0:
            if self.spawn_defense_area == 0:
                self.spawn_defense_area = self.spawn_defense_area_m * 100.0
        elif self.spawn_defense_area > 0:
            self.spawn_defense_area_m = self.spawn_defense_area / 100.0
        elif self.spawn_defense_area_m2 > 0:
            r_m = math.sqrt(self.spawn_defense_area_m2 / math.pi)
            self.spawn_defense_area_m = r_m
            self.spawn_defense_area = r_m * 100.0
        return self

    # New InSALMON parameters
    mort_condition_K_crit: float = 0.8
    fecundity_noise: float = 0.0
    spawn_date_jitter_days: int = 0
    outmigration_max_prob: float = 0.1
    outmigration_min_length: float = 4.0  # Arc D: was 8.0; NetLogo FishEventsOut logs 3.6-4.0 cm outmigrants
    fitness_growth_weight: float = 1.0


class ReachConfig(BaseModel, extra="allow"):
    """Reach-specific parameters."""

    restoration_events: list = []
    drift_conc: float = 0.0
    search_prod: float = 0.0
    shelter_speed_frac: float = 0.0
    prey_energy_density: float = 0.0
    drift_regen_distance: float = 0.0
    shading: float = 0.0
    fish_pred_min: float = 0.0
    terr_pred_min: float = 0.0
    light_turbid_coef: float = 0.0
    light_turbid_const: float = 0.0
    max_spawn_flow: float = 0.0
    shear_A: float = 0.0
    shear_B: float = 0.0
    upstream_junction: int = 0
    downstream_junction: int = 0
    time_series_input_file: str = ""
    depth_file: str = ""
    velocity_file: str = ""

    # WGBAST Arc K: optional Potential Smolt Production Capacity for this
    # reach/river. Used by `write_smolt_production_by_reach` to emit
    # `pspc_achieved_pct`. None = not an assessment reach.
    # Source: WGBAST §3 river-specific PSPC table (e.g. Torne ≈ 2,200k
    # smolts/yr; Simo ≈ 95k; Mörrum ≈ 50k).
    pspc_smolts_per_year: float | None = None

    # WGBAST Arc L: river key used to look up per-(year, river) M74 YSFM
    # fraction from `simulation.m74_forcing_csv`. None = non-WGBAST reach
    # (no M74 cull applied at egg-emergence).
    river_name: str | None = None


# ---------------------------------------------------------------------------
# Barrier config
# ---------------------------------------------------------------------------


class BarrierDirectionConfig(BaseModel):
    """Outcome probabilities for one direction through a barrier.

    The three probabilities partition the sample space and therefore
    must be in [0, 1] and sum to 1.0 within 1e-6. Parsing a misconfigured
    barrier raises a ``ValidationError`` rather than silently normalising,
    because downstream RNG draws assume the triple is already a valid PMF.
    """
    mortality: float = 0.0
    deflection: float = 0.0
    transmission: float = 1.0

    @field_validator("mortality", "deflection", "transmission")
    @classmethod
    def _prob_in_unit_interval(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(
                f"barrier probability must be in [0, 1]; got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _probs_sum_to_one(self) -> "BarrierDirectionConfig":
        total = self.mortality + self.deflection + self.transmission
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                "barrier direction probabilities (mortality, deflection, "
                f"transmission) must sum to 1.0 (±1e-6); got "
                f"{self.mortality}+{self.deflection}+{self.transmission}"
                f"={total}"
            )
        return self


class BarrierConfig(BaseModel):
    """One physical barrier between two reaches."""
    name: str = ""
    from_reach: str
    to_reach: str
    upstream: BarrierDirectionConfig = BarrierDirectionConfig()
    downstream: BarrierDirectionConfig = BarrierDirectionConfig()


class ModelConfig(BaseModel):
    simulation: SimulationConfig
    performance: PerformanceConfig = PerformanceConfig()
    spatial: SpatialConfig = SpatialConfig()
    light: LightConfig = LightConfig()
    species: Dict[str, SpeciesConfig] = {}
    reaches: Dict[str, ReachConfig] = {}
    marine: Optional["MarineConfig"] = None
    barriers: Optional[List[BarrierConfig]] = None


# ---------------------------------------------------------------------------
# ReachParams (frozen dataclass for runtime use)
# ---------------------------------------------------------------------------
from dataclasses import dataclass


@dataclass(frozen=True)
class ReachParams:
    name: str
    drift_conc: float = 0.0
    search_prod: float = 0.0
    shelter_speed_frac: float = 0.0
    prey_energy_density: float = 0.0
    drift_regen_distance: float = 0.0
    shading: float = 0.0
    fish_pred_min: float = 0.0
    terr_pred_min: float = 0.0
    light_turbid_coef: float = 0.0
    light_turbid_const: float = 0.0
    max_spawn_flow: float = 0.0
    shear_A: float = 0.0
    shear_B: float = 0.0
    upstream_junction: int = 0
    downstream_junction: int = 0
    river_name: str | None = None


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def load_config(path: Path) -> ModelConfig:
    """Load a YAML configuration file and return a validated ModelConfig."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ModelConfig(**raw)


# ---------------------------------------------------------------------------
# params_from_config
# ---------------------------------------------------------------------------


def params_from_config(
    config: ModelConfig,
) -> tuple[dict[str, SpeciesParams], dict[str, ReachParams]]:
    """Convert a ModelConfig into frozen runtime parameter objects.

    Returns (species_params, reach_params) dicts keyed by name.
    """
    species_params: dict[str, SpeciesParams] = {}
    for name, sp in config.species.items():
        table = sp.cmax_temp_table
        xs = np.array(sorted(table.keys()), dtype=np.float64)
        ys = np.array([table[k] for k in sorted(table.keys())], dtype=np.float64)
        species_params[name] = SpeciesParams(
            name=name,
            # Consumption
            cmax_A=sp.cmax_A,
            cmax_B=sp.cmax_B,
            # Weight
            weight_A=sp.weight_A,
            weight_B=sp.weight_B,
            # Interpolation tables
            cmax_temp_table_x=xs,
            cmax_temp_table_y=ys,
            # Anadromous
            is_anadromous=sp.is_anadromous,
            # Capture / detection
            capture_R1=sp.capture_R1,
            capture_R9=sp.capture_R9,
            # Emergence
            emerge_length_min=sp.emerge_length_min,
            emerge_length_mode=sp.emerge_length_mode,
            emerge_length_max=sp.emerge_length_max,
            # Reactive distance
            react_dist_A=sp.react_dist_A,
            react_dist_B=sp.react_dist_B,
            turbid_threshold=sp.turbid_threshold,
            turbid_min=sp.turbid_min,
            turbid_exp=sp.turbid_exp,
            light_threshold=sp.light_threshold,
            light_min=sp.light_min,
            light_exp=sp.light_exp,
            # Energetics
            energy_density=sp.energy_density,
            fitness_horizon=sp.fitness_horizon,
            fitness_length=sp.fitness_length,
            fitness_memory_frac=sp.fitness_memory_frac,
            # Swimming
            max_speed_A=sp.max_speed_A,
            max_speed_B=sp.max_speed_B,
            max_speed_C=sp.max_speed_C,
            max_speed_D=sp.max_speed_D,
            max_speed_E=sp.max_speed_E,
            # Migration
            migrate_fitness_L1=sp.migrate_fitness_L1,
            migrate_fitness_L9=sp.migrate_fitness_L9,
            # Movement
            move_radius_max=sp.move_radius_max,
            move_radius_L1=sp.move_radius_L1,
            move_radius_L9=sp.move_radius_L9,
            # Piscivory
            pisciv_length=sp.pisciv_length,
            # Respiration
            resp_A=sp.resp_A,
            resp_B=sp.resp_B,
            resp_C=sp.resp_C,
            resp_D=sp.resp_D,
            resp_ref_temp=getattr(sp, "resp_ref_temp", 15.0),
            # Search
            search_area=sp.search_area,
            # Spawning
            spawn_defense_area=sp.spawn_defense_area,
            spawn_defense_area_m=getattr(sp, "spawn_defense_area_m", 0.0),
            spawn_egg_viability=sp.spawn_egg_viability,
            spawn_fecund_mult=sp.spawn_fecund_mult,
            spawn_fecund_exp=sp.spawn_fecund_exp,
            spawn_suitability_tol=sp.spawn_suitability_tol,
            spawn_max_flow_change=sp.spawn_max_flow_change,
            spawn_max_temp=sp.spawn_max_temp,
            spawn_min_age=sp.spawn_min_age,
            spawn_min_length=sp.spawn_min_length,
            spawn_min_cond=sp.spawn_min_cond,
            spawn_min_temp=sp.spawn_min_temp,
            spawn_prob=sp.spawn_prob,
            spawn_wt_loss_fraction=sp.spawn_wt_loss_fraction,
            # Mortality: high temp
            mort_high_temp_T1=sp.mort_high_temp_T1,
            mort_high_temp_T9=sp.mort_high_temp_T9,
            mort_strand_survival_when_dry=sp.mort_strand_survival_when_dry,
            mort_condition_S_at_K8=sp.mort_condition_S_at_K8,
            mort_condition_S_at_K5=sp.mort_condition_S_at_K5,
            # Mortality: terrestrial predation
            mort_terr_pred_L1=sp.mort_terr_pred_L1,
            mort_terr_pred_L9=sp.mort_terr_pred_L9,
            mort_terr_pred_D1=sp.mort_terr_pred_D1,
            mort_terr_pred_D9=sp.mort_terr_pred_D9,
            mort_terr_pred_V1=sp.mort_terr_pred_V1,
            mort_terr_pred_V9=sp.mort_terr_pred_V9,
            mort_terr_pred_I1=sp.mort_terr_pred_I1,
            mort_terr_pred_I9=sp.mort_terr_pred_I9,
            mort_terr_pred_H1=sp.mort_terr_pred_H1,
            mort_terr_pred_H9=sp.mort_terr_pred_H9,
            mort_terr_pred_hiding_factor=sp.mort_terr_pred_hiding_factor,
            # Mortality: fish predation
            mort_fish_pred_L1=sp.mort_fish_pred_L1,
            mort_fish_pred_L9=sp.mort_fish_pred_L9,
            mort_fish_pred_D1=sp.mort_fish_pred_D1,
            mort_fish_pred_D9=sp.mort_fish_pred_D9,
            mort_fish_pred_I1=sp.mort_fish_pred_I1,
            mort_fish_pred_I9=sp.mort_fish_pred_I9,
            mort_fish_pred_hiding_factor=sp.mort_fish_pred_hiding_factor,
            mort_fish_pred_P1=sp.mort_fish_pred_P1,
            mort_fish_pred_P9=sp.mort_fish_pred_P9,
            mort_fish_pred_T1=sp.mort_fish_pred_T1,
            mort_fish_pred_T9=sp.mort_fish_pred_T9,
            # Redd mortality
            mort_redd_dewater_surv=sp.mort_redd_dewater_surv,
            mort_redd_hi_temp_T1=sp.mort_redd_hi_temp_T1,
            mort_redd_hi_temp_T9=sp.mort_redd_hi_temp_T9,
            mort_redd_lo_temp_T1=sp.mort_redd_lo_temp_T1,
            mort_redd_lo_temp_T9=sp.mort_redd_lo_temp_T9,
            mort_redd_scour_depth=sp.mort_redd_scour_depth,
            # Redd development
            redd_devel_A=sp.redd_devel_A,
            redd_devel_B=sp.redd_devel_B,
            redd_devel_C=sp.redd_devel_C,
            redd_area=sp.redd_area,
            # Superindividual
            superind_max_rep=sp.superind_max_rep,
            superind_max_length=sp.superind_max_length,
            # New InSALMON parameters
            mort_condition_K_crit=sp.mort_condition_K_crit,
            fecundity_noise=sp.fecundity_noise,
            spawn_date_jitter_days=sp.spawn_date_jitter_days,
            outmigration_max_prob=sp.outmigration_max_prob,
            outmigration_min_length=sp.outmigration_min_length,
            fitness_growth_weight=sp.fitness_growth_weight,
        )

    reach_params: dict[str, ReachParams] = {}
    for name, r in config.reaches.items():
        reach_params[name] = ReachParams(
            name=name,
            drift_conc=r.drift_conc,
            search_prod=r.search_prod,
            shelter_speed_frac=r.shelter_speed_frac,
            prey_energy_density=r.prey_energy_density,
            drift_regen_distance=r.drift_regen_distance,
            shading=r.shading,
            fish_pred_min=r.fish_pred_min,
            terr_pred_min=r.terr_pred_min,
            light_turbid_coef=r.light_turbid_coef,
            light_turbid_const=r.light_turbid_const,
            max_spawn_flow=r.max_spawn_flow,
            shear_A=r.shear_A,
            shear_B=r.shear_B,
            upstream_junction=r.upstream_junction,
            downstream_junction=r.downstream_junction,
            river_name=r.river_name,
        )

    return species_params, reach_params


# ---------------------------------------------------------------------------
# nls_to_yaml — NetLogo .nls parameter file converter
# ---------------------------------------------------------------------------


def _parse_nls_date(val: str) -> str:
    """Convert NetLogo date 'M/d/yyyy' to ISO 'yyyy-MM-dd'."""
    parts = val.strip().strip('"').split("/")
    if len(parts) == 3:
        m, d, y = parts
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return val


def _parse_nls_day(val: str) -> str:
    """Convert NetLogo day 'M/d' to 'MM-dd'."""
    parts = val.strip().strip('"').split("/")
    if len(parts) == 2:
        m, d = parts
        return f"{int(m):02d}-{int(d):02d}"
    return val


def _parse_value(raw: str) -> Any:
    """Parse a single NetLogo value string into a Python type."""
    raw = raw.strip()
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    # Try number
    try:
        if "." in raw or "e" in raw.lower():
            return float(raw)
        return int(raw)
    except ValueError:
        pass
    # String (strip quotes)
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    return raw


def nls_to_yaml(nls_path: Path) -> str:
    """Parse a NetLogo .nls parameter file and return YAML configuration string."""
    nls_path = Path(nls_path)
    if not nls_path.exists():
        raise FileNotFoundError(f"NLS file not found: {nls_path}")

    text = nls_path.read_text(encoding="utf-8")

    # Extract simple `set var-name value` assignments
    sets: dict[str, str] = {}
    for line in text.splitlines():
        line = line.split(";")[0].strip()  # strip comments
        m = re.match(r"^set\s+([\w\-\?]+)\s+(.+)$", line)
        if m:
            sets[m.group(1)] = m.group(2).strip()

    # Extract list assignments: set var-name (list val1 val2 ...)
    lists: dict[str, list] = {}
    for key, val in sets.items():
        if val.startswith("(list"):
            inner = val[5:].rstrip(")")
            # Handle time:create values
            items = []
            for token in re.findall(
                r'time:create\s+"[^"]*"|"[^"]*"|[\w\.\-\+Ee]+', inner
            ):
                if token.startswith("time:create"):
                    # Extract the date string
                    date_str = re.search(r'"([^"]*)"', token).group(1)
                    items.append(_parse_nls_day(date_str))
                else:
                    items.append(_parse_value(token))
            lists[key] = items

    # Extract table:put lines for interpolation tables
    tables: dict[str, dict[float, float]] = {}
    for line in text.splitlines():
        line_stripped = line.split(";")[0].strip()
        m = re.match(
            r"^table:put\s+([\w\-]+)\s+([\d\.\-Ee]+)\s+([\d\.\-Ee]+)", line_stripped
        )
        if m:
            tname = m.group(1)
            k = float(m.group(2))
            v = float(m.group(3))
            tables.setdefault(tname, {})[k] = v

    # Build config dict
    species_names = [s for s in lists.get("species-list", []) if isinstance(s, str)]
    reach_names = [s for s in lists.get("reach-names", []) if isinstance(s, str)]

    config: dict[str, Any] = {}

    # Simulation
    config["simulation"] = {
        "start_date": _parse_nls_date(sets.get("start-date", "")),
        "end_date": _parse_nls_date(sets.get("end-date", "")),
        "output_frequency": _parse_value(sets.get("file-output-frequency", "1")),
        "output_units": _parse_value(sets.get("file-output-units", '"days"')),
        "seed": 0,
        "census_days": [
            _parse_nls_day(d)
            for d in lists.get("census-days", [])
            if isinstance(d, str)
        ],
        "census_years_to_skip": _parse_value(sets.get("census-years-to-skip", "0")),
    }

    # Performance (defaults)
    config["performance"] = {
        "backend": "numpy",
        "trout_capacity": 2000,
        "redd_capacity": 500,
    }

    # Spatial
    gis_props = {}
    gis_mapping = {
        "cell_id": "GIS-property-for-cell-ID",
        "reach_name": "GIS-property-for-cell-reach-name",
        "area": "GIS-property-for-cell-area",
        "dist_escape": "GIS-property-for-cell-dist-escape",
        "num_hiding_places": "GIS-property-for-cell-num-hiding-places",
        "frac_vel_shelter": "GIS-property-for-cell-frac-vel-shelter",
        "frac_spawn": "GIS-property-for-cell-frac-spawn",
    }
    for yaml_key, nls_key in gis_mapping.items():
        if nls_key in sets:
            gis_props[yaml_key] = _parse_value(sets[nls_key])

    config["spatial"] = {
        "backend": "shapefile",
        "mesh_file": _parse_value(sets.get("GIS-file-name", '""')),
        "gis_properties": gis_props,
    }

    # Light
    config["light"] = {
        "latitude": _parse_value(sets.get("latitude", "0")),
        "light_correction": _parse_value(sets.get("light-correction", "1.0")),
        "light_at_night": _parse_value(sets.get("light-at-night", "0.0")),
        "twilight_angle": _parse_value(sets.get("twilight-angle", "6.0")),
    }

    # Species — map from NLS list params (indexed) to per-species dicts
    # Mapping: yaml_field -> nls_list_name
    species_scalar_map = {
        "is_anadromous": "trout-is-anadromous?",
        "display_color": "trout-display-color",
        "capture_R1": "trout-capture-R1",
        "capture_R9": "trout-capture-R9",
        "cmax_A": "trout-cmax-A",
        "cmax_B": "trout-cmax-B",
        "emerge_length_min": "trout-emerge-length-min",
        "emerge_length_mode": "trout-emerge-length-mode",
        "emerge_length_max": "trout-emerge-length-max",
        "react_dist_A": "trout-react-dist-A",
        "react_dist_B": "trout-react-dist-B",
        "turbid_threshold": "trout-turbid-threshold",
        "turbid_min": "trout-turbid-min",
        "turbid_exp": "trout-turbid-exp",
        "light_threshold": "trout-light-threshold",
        "light_min": "trout-light-min",
        "light_exp": "trout-light-exp",
        "energy_density": "trout-energy-density",
        "fitness_horizon": "trout-fitness-horizon",
        "fitness_length": "trout-fitness-length",
        "max_speed_A": "trout-max-speed-A",
        "max_speed_B": "trout-max-speed-B",
        "max_speed_C": "trout-max-speed-C",
        "max_speed_D": "trout-max-speed-D",
        "max_speed_E": "trout-max-speed-E",
        "migrate_fitness_L1": "trout-migrate-fitness-L1",
        "migrate_fitness_L9": "trout-migrate-fitness-L9",
        "move_radius_max": "trout-move-radius-max",
        "move_radius_L1": "trout-move-radius-L1",
        "move_radius_L9": "trout-move-radius-L9",
        "pisciv_length": "trout-pisciv-length",
        "resp_A": "trout-resp-A",
        "resp_B": "trout-resp-B",
        "resp_C": "trout-resp-C",
        "resp_D": "trout-resp-D",
        "search_area": "trout-search-area",
        "spawn_defense_area": "trout-spawn-defense-area",
        "spawn_egg_viability": "trout-spawn-egg-viability",
        "spawn_fecund_mult": "trout-spawn-fecund-mult",
        "spawn_fecund_exp": "trout-spawn-fecund-exp",
        "spawn_suitability_tol": "trout-spawn-suitability-tol",
        "spawn_start_day": "trout-spawn-start-day",
        "spawn_end_day": "trout-spawn-end-day",
        "spawn_max_flow_change": "trout-spawn-max-flow-change",
        "spawn_max_temp": "trout-spawn-max-temp",
        "spawn_min_age": "trout-spawn-min-age",
        "spawn_min_length": "trout-spawn-min-length",
        "spawn_min_cond": "trout-spawn-min-cond",
        "spawn_min_temp": "trout-spawn-min-temp",
        "spawn_prob": "trout-spawn-prob",
        "spawn_wt_loss_fraction": "trout-spawn-wt-loss-fraction",
        "weight_A": "trout-weight-A",
        "weight_B": "trout-weight-B",
        "mort_high_temp_T1": "mort-high-temp-T1",
        "mort_high_temp_T9": "mort-high-temp-T9",
        "mort_strand_survival_when_dry": "mort-strand-survival-when-dry",
        "mort_condition_S_at_K8": "mort-condition-S-at-K8",
        "mort_condition_S_at_K5": "mort-condition-S-at-K5",
        "mort_terr_pred_L1": "mort-terr-pred-L1",
        "mort_terr_pred_L9": "mort-terr-pred-L9",
        "mort_terr_pred_D1": "mort-terr-pred-D1",
        "mort_terr_pred_D9": "mort-terr-pred-D9",
        "mort_terr_pred_V1": "mort-terr-pred-V1",
        "mort_terr_pred_V9": "mort-terr-pred-V9",
        "mort_terr_pred_I1": "mort-terr-pred-I1",
        "mort_terr_pred_I9": "mort-terr-pred-I9",
        "mort_terr_pred_H1": "mort-terr-pred-H1",
        "mort_terr_pred_H9": "mort-terr-pred-H9",
        "mort_terr_pred_hiding_factor": "mort-terr-pred-hiding-factor",
        "mort_fish_pred_L1": "mort-fish-pred-L1",
        "mort_fish_pred_L9": "mort-fish-pred-L9",
        "mort_fish_pred_D1": "mort-fish-pred-D1",
        "mort_fish_pred_D9": "mort-fish-pred-D9",
        "mort_fish_pred_I1": "mort-fish-pred-I1",
        "mort_fish_pred_I9": "mort-fish-pred-I9",
        "mort_fish_pred_hiding_factor": "mort-fish-pred-hiding-factor",
        "mort_fish_pred_P1": "mort-fish-pred-P1",
        "mort_fish_pred_P9": "mort-fish-pred-P9",
        "mort_fish_pred_T1": "mort-fish-pred-T1",
        "mort_fish_pred_T9": "mort-fish-pred-T9",
        "mort_redd_dewater_surv": "mort-redd-dewater-surv",
        "mort_redd_hi_temp_T1": "mort-redd-hi-temp-T1",
        "mort_redd_hi_temp_T9": "mort-redd-hi-temp-T9",
        "mort_redd_lo_temp_T1": "mort-redd-lo-temp-T1",
        "mort_redd_lo_temp_T9": "mort-redd-lo-temp-T9",
        "mort_redd_scour_depth": "mort-redd-scour-depth",
        "redd_devel_A": "redd-devel-A",
        "redd_devel_B": "redd-devel-B",
        "redd_devel_C": "redd-devel-C",
        "redd_area": "redd-area",
        "superind_max_rep": "trout-superind-max-rep",
        "superind_max_length": "trout-superind-max-length",
    }

    config["species"] = {}
    for i, sp_name in enumerate(species_names):
        sp_dict: dict[str, Any] = {}
        for yaml_key, nls_key in species_scalar_map.items():
            vals = lists.get(nls_key, [])
            if i < len(vals):
                sp_dict[yaml_key] = vals[i]
        # Add cmax interpolation table
        cmax_table_name = f"{sp_name}-cmax-table"
        if cmax_table_name in tables:
            sp_dict["cmax_temp_table"] = {
                k: v for k, v in sorted(tables[cmax_table_name].items())
            }
        # Add spawn depth table
        depth_table_name = f"{sp_name}-depth-table"
        if depth_table_name in tables:
            sp_dict["spawn_depth_table"] = {
                k: v for k, v in sorted(tables[depth_table_name].items())
            }
        # Add spawn velocity table
        vel_table_name = f"{sp_name}-vel-table"
        if vel_table_name in tables:
            sp_dict["spawn_vel_table"] = {
                k: v for k, v in sorted(tables[vel_table_name].items())
            }
        config["species"][sp_name] = sp_dict

    # Reaches
    reach_scalar_map = {
        "drift_conc": "reach-drift-concs",
        "search_prod": "reach-search-prods",
        "shelter_speed_frac": "reach-shelter-speed-fracs",
        "prey_energy_density": "reach-prey-energy-densities",
        "drift_regen_distance": "reach-drift-regen-distances",
        "shading": "reach-shadings",
        "fish_pred_min": "reach-fish-pred-mins",
        "terr_pred_min": "reach-terr-pred-mins",
        "light_turbid_coef": "reach-light-turbid-coefs",
        "light_turbid_const": "reach-light-turbid-consts",
        "max_spawn_flow": "reach-max-spawn-flows",
        "shear_A": "reach-shear-As",
        "shear_B": "reach-shear-Bs",
        "upstream_junction": "reach-upstream-junctions",
        "downstream_junction": "reach-downstream-junctions",
        "time_series_input_file": "time-series-input-files",
        "depth_file": "depth-file-names",
        "velocity_file": "velocity-file-names",
    }

    config["reaches"] = {}
    for i, r_name in enumerate(reach_names):
        r_dict: dict[str, Any] = {}
        for yaml_key, nls_key in reach_scalar_map.items():
            vals = lists.get(nls_key, [])
            if i < len(vals):
                r_dict[yaml_key] = vals[i]
        config["reaches"][r_name] = r_dict

    return yaml.dump(
        config, default_flow_style=False, sort_keys=False, allow_unicode=True
    )


# ---------------------------------------------------------------------------
# Deferred import to resolve forward reference in ModelConfig.marine
# ---------------------------------------------------------------------------
from salmopy.marine.config import MarineConfig  # noqa: E402

ModelConfig.model_rebuild()
