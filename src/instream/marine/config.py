"""Marine configuration models."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, field_validator


class ZoneConfig(BaseModel):
    """Definition of a single marine zone."""

    name: str
    area_km2: float


class ZoneDriverData(BaseModel):
    """Monthly environmental driver data for one zone.

    Each list has exactly 12 elements (Jan..Dec).
    """

    temperature: List[float]
    salinity: List[float]
    prey_index: List[float]
    predation_risk: List[float]

    @field_validator("temperature", "salinity", "prey_index", "predation_risk")
    @classmethod
    def _check_twelve(cls, v: List[float]) -> List[float]:
        if len(v) != 12:
            raise ValueError(f"Expected 12 monthly values, got {len(v)}")
        return v


class GearConfig(BaseModel):
    """One fishing gear type with selectivity and seasonal closure."""

    selectivity_type: Literal["logistic", "normal"] = "logistic"
    selectivity_L50: float = 55.0        # logistic midpoint (cm)
    selectivity_slope: float = 3.0       # logistic slope
    selectivity_mean: float = 70.0       # normal mode (cm)
    selectivity_sd: float = 8.0          # normal width
    bycatch_mortality: float = 0.10
    zones: List[str] = []
    open_months: List[int] = []
    daily_effort: float = 0.0


class MarineFishingConfig(BaseModel):
    """Fishing-module configuration (minimum legal size + gears)."""

    min_legal_length: float = 60.0
    gear_types: Dict[str, GearConfig] = {}


class MarineConfig(BaseModel):
    """Top-level marine configuration."""

    zones: List[ZoneConfig]
    zone_connectivity: Dict[str, List[str]] = {}

    # Smolt parameters
    smolt_min_length: float = 12.0
    smolt_migration_speed_km_d: float = 20.0

    # Return migration parameters
    return_min_sea_winters: int = 1
    return_prob_per_day: float = 0.01

    # Static driver data keyed by zone name
    static_driver: Dict[str, ZoneDriverData] = {}

    # ------------------------------------------------------------------
    # v0.15.0 marine ecology parameters (Sub-project B)
    # All optional with design-document defaults so existing v0.14.0
    # configs remain valid.
    # ------------------------------------------------------------------

    # Bioenergetics (Hanson et al. 1997, Fish Bioenergetics 3.0)
    marine_cmax_A: float = 0.303
    marine_cmax_B: float = -0.275
    marine_cmax_topt: float = 15.0        # deg C, optimal consumption temp
    marine_cmax_tmax: float = 22.0        # deg C, zero-consumption cutoff
    marine_resp_A: float = 0.0548         # respiration allometric intercept
    marine_resp_B: float = -0.299         # respiration allometric slope
    marine_resp_Q10: float = 2.1          # temperature coefficient
    marine_growth_efficiency: float = 0.50  # K2 net growth efficiency

    # Seal predation (logistic, size-dependent)
    # NOTE: max_daily is the sustainable-rate asymptote of the logistic, NOT
    # the peak-event intensity. The design doc's original value (0.02) was a
    # peak-event ceiling and collapses a cohort to <1% in 2 years when applied
    # continuously. Calibrated to land in the ICES WGBAST 5-15% 2-y survival
    # band for Baltic salmon.
    marine_mort_seal_L1: float = 40.0
    marine_mort_seal_L9: float = 80.0
    marine_mort_seal_max_daily: float = 0.010

    # Cormorant predation (post-smolt, nearshore only)
    # See note on seal max_daily above.
    marine_mort_cormorant_L1: float = 15.0
    marine_mort_cormorant_L9: float = 40.0
    marine_mort_cormorant_max_daily: float = 0.010
    marine_mort_cormorant_zones: List[str] = ["estuary", "coastal"]
    # Post-smolt vulnerability window decays linearly over this many days
    post_smolt_vulnerability_days: int = 28

    # Background and environmental mortality
    marine_mort_base: float = 0.001
    temperature_stress_threshold: float = 20.0
    temperature_stress_daily: float = 0.01

    # M74 thiamine-deficiency syndrome
    marine_mort_m74_prob: float = 0.0

    # v0.17.0 — hatchery predator-naivety multiplier applied to cormorant
    # hazard for fish with is_hatchery=True during the post-smolt
    # vulnerability window. After the window, hatchery fish converge on
    # wild survival rates. Reference: Kallio-Nyberg et al. 2004
    # (Simojoki wild vs reared smolt recapture ratio ~2.0);
    # DOI 10.1111/j.0022-1112.2004.00435.x
    hatchery_predator_naivety_multiplier: float = 2.5

    # Maturation (conditional probabilities per sea-winter)
    maturation_min_sea_winters: int = 1
    maturation_prob_1SW: float = 0.15
    maturation_prob_2SW: float = 0.59
    maturation_prob_3SW: float = 0.86
    maturation_prob_4SW: float = 0.99
    maturation_min_length: float = 55.0
    maturation_min_condition: float = 0.8

    # Fishing
    marine_fishing: Optional[MarineFishingConfig] = None

    @field_validator("marine_growth_efficiency")
    @classmethod
    def _efficiency_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"marine_growth_efficiency must be in [0,1], got {v}")
        return v
