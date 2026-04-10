"""Marine domain: ZoneState, StaticDriver, and MarineDomain."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

import numpy as np

if TYPE_CHECKING:
    from instream.marine.config import MarineConfig
    from instream.state.trout_state import TroutState


# ---------------------------------------------------------------------------
# ZoneState
# ---------------------------------------------------------------------------


@dataclass
class ZoneState:
    """Current environmental state for all marine zones."""

    num_zones: int
    name: np.ndarray          # object array of zone name strings
    temperature: np.ndarray   # float64
    salinity: np.ndarray      # float64
    prey_index: np.ndarray    # float64
    predation_risk: np.ndarray  # float64
    area_km2: np.ndarray      # float64

    @classmethod
    def zeros(cls, num_zones: int) -> "ZoneState":
        """Factory: create a ZoneState with all-zero arrays."""
        return cls(
            num_zones=num_zones,
            name=np.array([""] * num_zones, dtype=object),
            temperature=np.zeros(num_zones, dtype=np.float64),
            salinity=np.zeros(num_zones, dtype=np.float64),
            prey_index=np.zeros(num_zones, dtype=np.float64),
            predation_risk=np.zeros(num_zones, dtype=np.float64),
            area_km2=np.zeros(num_zones, dtype=np.float64),
        )


# ---------------------------------------------------------------------------
# StaticDriver
# ---------------------------------------------------------------------------


class StaticDriver:
    """Provides monthly environmental conditions from MarineConfig tables.

    Looks up the month index (0-based) from *date.month* and fills
    *zone_state* arrays accordingly.
    """

    def __init__(self, config: "MarineConfig") -> None:
        self._config = config
        n = len(config.zones)
        # Build (num_zones, 12) arrays for fast lookup
        self._temperature = np.zeros((n, 12), dtype=np.float64)
        self._salinity = np.zeros((n, 12), dtype=np.float64)
        self._prey_index = np.zeros((n, 12), dtype=np.float64)
        self._predation_risk = np.zeros((n, 12), dtype=np.float64)

        self._zone_names: List[str] = []
        self._area_km2 = np.zeros(n, dtype=np.float64)

        for i, zc in enumerate(config.zones):
            self._zone_names.append(zc.name)
            self._area_km2[i] = zc.area_km2
            drv = config.static_driver.get(zc.name)
            if drv is not None:
                self._temperature[i] = drv.temperature
                self._salinity[i] = drv.salinity
                self._prey_index[i] = drv.prey_index
                self._predation_risk[i] = drv.predation_risk

    @property
    def num_zones(self) -> int:
        return len(self._zone_names)

    def get_conditions(self, date: datetime.date, zone_state: ZoneState) -> None:
        """Fill *zone_state* with conditions for *date* (in-place)."""
        month_idx = date.month - 1  # 0-based
        zone_state.temperature[:] = self._temperature[:, month_idx]
        zone_state.salinity[:] = self._salinity[:, month_idx]
        zone_state.prey_index[:] = self._prey_index[:, month_idx]
        zone_state.predation_risk[:] = self._predation_risk[:, month_idx]
        zone_state.area_km2[:] = self._area_km2
        for i, nm in enumerate(self._zone_names):
            zone_state.name[i] = nm


# ---------------------------------------------------------------------------
# MarineDomain
# ---------------------------------------------------------------------------

# Zone indices (must match config.zones ordering)
_ESTUARY = 0
_COASTAL = 1
_BALTIC = 2

# Migration timing thresholds (days since smolt_date)
_ESTUARY_TO_COASTAL_DAYS = 14
_COASTAL_TO_BALTIC_DAYS = 30


class MarineDomain:
    """Orchestrates marine-phase fish each daily step.

    Responsibilities
    ----------------
    * Update zone environmental conditions from the static driver.
    * Increment sea-winters on Jan 1.
    * Time-based zone migration:
      - estuary -> coastal after 14 days
      - coastal -> baltic after 30 days
      - 1+ sea-winter in baltic -> eligible for return (not yet implemented)
    * Growth and survival are placeholders (no-ops).
    """

    def __init__(
        self,
        trout_state: "TroutState",
        zone_state: ZoneState,
        marine_config: "MarineConfig",
    ) -> None:
        self.trout_state = trout_state
        self.zone_state = zone_state
        self.config = marine_config
        self.driver = StaticDriver(marine_config)

        # Build zone-name-to-index map
        self._zone_name_to_idx: Dict[str, int] = {
            zc.name: i for i, zc in enumerate(marine_config.zones)
        }

        # Build adjacency list (index -> list of index)
        self._adjacency: Dict[int, List[int]] = {}
        for src_name, dst_names in marine_config.zone_connectivity.items():
            src_idx = self._zone_name_to_idx.get(src_name)
            if src_idx is not None:
                self._adjacency[src_idx] = [
                    self._zone_name_to_idx[d]
                    for d in dst_names
                    if d in self._zone_name_to_idx
                ]

    # ----- public API -----

    def update_environment(self, date: datetime.date) -> None:
        """Fetch conditions from the static driver for *date*."""
        self.driver.get_conditions(date, self.zone_state)

    def daily_step(self, current_date: datetime.date) -> None:
        """Process one day for all marine fish (zone_idx >= 0)."""
        ts = self.trout_state
        alive = ts.is_alive if hasattr(ts, "is_alive") else np.ones(ts.zone_idx.shape[0], dtype=bool)
        marine_mask = alive & (ts.zone_idx >= 0)

        if not np.any(marine_mask):
            return

        # 1. Update environment
        self.update_environment(current_date)

        # 2. Increment sea-winters on Jan 1
        if current_date.month == 1 and current_date.day == 1:
            ts.sea_winters[marine_mask] += 1

        # 3. Time-based zone migration
        ordinal_today = current_date.toordinal()
        smolt_dates = ts.smolt_date[marine_mask]
        zone_idxs = ts.zone_idx[marine_mask]

        days_since_smolt = ordinal_today - smolt_dates

        # estuary -> coastal after 14 days
        promote_to_coastal = (zone_idxs == _ESTUARY) & (days_since_smolt >= _ESTUARY_TO_COASTAL_DAYS)
        # coastal -> baltic after 30 days
        promote_to_baltic = (zone_idxs == _COASTAL) & (days_since_smolt >= _COASTAL_TO_BALTIC_DAYS)

        # Apply promotions back to trout_state
        marine_indices = np.where(marine_mask)[0]

        if np.any(promote_to_coastal):
            ts.zone_idx[marine_indices[promote_to_coastal]] = _COASTAL

        if np.any(promote_to_baltic):
            ts.zone_idx[marine_indices[promote_to_baltic]] = _BALTIC

        # 4. Growth placeholder — no-op
        # 5. Survival placeholder — no-op
