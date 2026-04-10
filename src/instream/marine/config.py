"""Marine configuration models."""

from __future__ import annotations

from typing import Dict, List, Optional

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
