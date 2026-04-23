"""Marine domain: ZoneState, StaticDriver, and MarineDomain."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional

import numpy as np

from salmopy.state.life_stage import LifeStage

if TYPE_CHECKING:
    from salmopy.marine.config import MarineConfig
    from salmopy.state.trout_state import TroutState


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
    dissolved_oxygen: np.ndarray  # float64 (mg/L) — for estuary stress

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
            dissolved_oxygen=np.full(num_zones, 99.0, dtype=np.float64),
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
        self._dissolved_oxygen = np.full((n, 12), 99.0, dtype=np.float64)

        for i, zc in enumerate(config.zones):
            self._zone_names.append(zc.name)
            self._area_km2[i] = zc.area_km2
            drv = config.static_driver.get(zc.name)
            if drv is not None:
                self._temperature[i] = drv.temperature
                self._salinity[i] = drv.salinity
                self._prey_index[i] = drv.prey_index
                self._predation_risk[i] = drv.predation_risk
                # Dissolved oxygen from estuary driver data (optional)
                do_data = getattr(drv, 'dissolved_oxygen', None)
                if do_data is not None:
                    self._dissolved_oxygen[i] = do_data

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
        zone_state.dissolved_oxygen[:] = self._dissolved_oxygen[:, month_idx]
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
        rng: Optional[np.random.Generator] = None,
    ) -> None:
        self.trout_state = trout_state
        self.zone_state = zone_state
        self.config = marine_config
        self.driver = StaticDriver(marine_config)
        self._rng = rng if rng is not None else np.random.default_rng()
        self.harvest_log: list = []
        # Lifetime counters — never reset by slot reuse (v0.16.0, extended v0.17.0)
        self.total_smoltified: int = 0
        self.total_returned: int = 0
        self.total_kelts: int = 0             # v0.17.0: successful kelt rolls
        self.total_repeat_spawners: int = 0   # v0.17.0: 2+ sea-winter returners

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
        alive = ts.alive
        marine_mask = alive & (ts.zone_idx >= 0)

        if not np.any(marine_mask):
            return

        # 1. Update environment
        self.update_environment(current_date)

        # 2. Increment sea-winters on Jan 1
        if current_date.month == 1 and current_date.day == 1:
            ts.sea_winters[marine_mask] += 1

        # 3. Time-based zone migration (respects adjacency graph)
        ordinal_today = current_date.toordinal()
        marine_indices = np.where(marine_mask)[0]

        for idx in marine_indices:
            current_zone = int(ts.zone_idx[idx])
            neighbors = self._adjacency.get(current_zone, [])
            if not neighbors:
                continue  # no connected zones — fish stays

            days_since = ordinal_today - int(ts.smolt_date[idx])

            # Promote to next zone along the connectivity path
            # after threshold days in current zone
            if current_zone == _ESTUARY and days_since >= _ESTUARY_TO_COASTAL_DAYS:
                next_zone = neighbors[0]  # first neighbor
                ts.zone_idx[idx] = next_zone
            elif current_zone == _COASTAL and days_since >= _COASTAL_TO_BALTIC_DAYS:
                # Move to the next offshore zone (not back to estuary)
                for nz in neighbors:
                    if nz != _ESTUARY:
                        ts.zone_idx[idx] = nz
                        break

        # 4. Life stage progression
        #    SMOLT -> OCEAN_JUVENILE once past estuary (zone > 0)
        #    OCEAN_JUVENILE -> OCEAN_ADULT after 1+ sea-winter
        marine_indices = np.where(marine_mask)[0]  # refresh after zone changes
        for idx in marine_indices:
            lh = int(ts.life_history[idx])
            if lh == int(LifeStage.SMOLT) and int(ts.zone_idx[idx]) > 0:
                ts.life_history[idx] = int(LifeStage.OCEAN_JUVENILE)
            elif lh == int(LifeStage.OCEAN_JUVENILE) and ts.sea_winters[idx] >= 1:
                ts.life_history[idx] = int(LifeStage.OCEAN_ADULT)

        # 5. Growth — Hanson bioenergetics
        from salmopy.marine.growth import apply_marine_growth

        marine_mask = alive & (ts.zone_idx >= 0)  # refresh after migration
        apply_marine_growth(
            ts,
            self.zone_state,
            marine_mask,
            self.config,
            species_weight_A=getattr(self, "species_weight_A", None),
            species_weight_B=getattr(self, "species_weight_B", None),
        )

        # 6. Natural survival — 5 sources (seal, cormorant, background,
        #    temperature stress, M74). Fishing is handled separately.
        from salmopy.marine.survival import apply_marine_survival

        apply_marine_survival(
            ts, self.zone_state, marine_mask, self.config, current_date, self._rng
        )

        # 7. Fishing mortality — gear selectivity + bycatch (sources 6,7).
        from salmopy.marine.fishing import apply_fishing_mortality

        marine_mask_post = alive & (ts.zone_idx >= 0)
        records = apply_fishing_mortality(
            ts, self.zone_state, marine_mask_post, self.config, current_date, self._rng
        )
        if records:
            self.harvest_log.extend(records)

        # 8. Estuarine stress — salinity + dissolved oxygen
        estuary_cfg = getattr(self.config, 'estuary', None)
        if estuary_cfg is not None:
            from salmopy.modules.estuary import apply_estuary_stress

            marine_mask_estuary = alive & (ts.zone_idx >= 0)
            apply_estuary_stress(
                ts, self.zone_state, marine_mask_estuary, estuary_cfg, self._rng
            )


# ---------------------------------------------------------------------------
# Smolt readiness accumulation
# ---------------------------------------------------------------------------


def accumulate_smolt_readiness(
    readiness: np.ndarray,
    life_history: np.ndarray,
    lengths: np.ndarray,
    day_length: float,
    max_day_length: float,
    temperature: np.ndarray,
    optimal_temp: float,
    photo_weight: float = 0.6,
    temp_weight: float = 0.4,
    doy: int = 1,
    window_start: int = 90,
    window_end: int = 180,
    min_length: float = 12.0,
) -> None:
    """Accumulate smolt readiness for PARR fish during the spring window.

    Readiness increases based on photoperiod (day_length / max_day_length)
    and temperature proximity to *optimal_temp*.  All PARR fish during
    DOY [window_start, window_end] accumulate readiness regardless of body
    length (physiological smoltification begins before migratory size).
    Winter decay (DOY > 270) partially resets readiness each year, enabling
    multi-year build-up over 2-3 springs.  *min_length* is retained in the
    signature for backward compatibility but is no longer used.
    Modifies *readiness* in-place.
    """
    n = len(readiness)

    # Winter decay (DOY 270-365): partial readiness reset
    if doy > 270:
        for i in range(n):
            if life_history[i] == int(LifeStage.PARR) and readiness[i] > 0:
                readiness[i] *= 0.996  # ~30% decay over 90 days (0.996^90 ≈ 0.70)
        return

    if doy < window_start or doy > window_end:
        return
    for i in range(n):
        if life_history[i] != int(LifeStage.PARR):
            continue
        # Photoperiod signal: fraction of maximum day length
        photo_signal = day_length / max(max_day_length, 1e-6)
        # Temperature signal: 1 when at optimal, declining away
        temp_diff = abs(float(temperature[i]) - optimal_temp)
        temp_signal = max(0.0, 1.0 - temp_diff / optimal_temp) if optimal_temp > 0 else 0.0

        increment = photo_weight * photo_signal + temp_weight * temp_signal
        readiness[i] = min(1.0, readiness[i] + increment * 0.012)  # 2-spring rate


# ---------------------------------------------------------------------------
# Adult return from marine to freshwater
# ---------------------------------------------------------------------------


def check_adult_return(
    trout_state: "TroutState",
    reach_cells: dict,
    return_sea_winters: int = 1,
    return_condition_min: float = 0.5,
    current_date: "datetime.date | None" = None,
    rng=None,
    barrier_map=None,
    reverse_reach_graph=None,
    estuary_reach: int = 0,
    config=None,
) -> tuple[int, int]:
    """Check OCEAN_ADULT fish for return to natal freshwater reach.

    Fish with sufficient *sea_winters* and *condition*, during spring
    (DOY 90-180), transition to RETURNING_ADULT and are placed in a
    random wet cell in their natal reach.

    When *barrier_map* is provided, fish must pass all barriers on the
    upstream route from estuary to natal reach.  Fish that are deflected
    are placed in the last passable reach; fish killed at a barrier die.

    Returns
    -------
    (n_returned, n_repeat_spawners) : tuple[int, int]
        Number of fish promoted to RETURNING_ADULT this call and the
        subset whose ``sea_winters >= 2`` (signal of a prior round-trip
        or extended ocean residency — the strongest repeat-spawner
        signal without adding a dedicated ``times_spawned`` field).
    """
    if current_date is None:
        return 0, 0

    doy = current_date.timetuple().tm_yday
    if doy < 90 or doy > 180:
        return 0, 0

    alive = trout_state.alive_indices() if hasattr(trout_state, 'alive_indices') else np.where(trout_state.alive)[0]
    n_returned = 0
    n_repeat = 0

    repeat_threshold = return_sea_winters + 1

    for i in alive:
        if int(trout_state.life_history[i]) != int(LifeStage.OCEAN_ADULT):
            continue
        if trout_state.zone_idx[i] < 0:
            continue  # already freshwater
        if trout_state.sea_winters[i] < return_sea_winters:
            continue
        if trout_state.condition[i] < return_condition_min:
            continue

        natal = int(trout_state.natal_reach_idx[i])
        target_reach = natal

        # Upstream barrier passage
        if barrier_map is not None and reverse_reach_graph is not None and rng is not None:
            from salmopy.modules.barriers import (
                attempt_upstream_route,
                RESULT_MORTALITY,
            )
            result, last_passable = attempt_upstream_route(
                barrier_map, estuary_reach, natal,
                reverse_reach_graph, rng,
            )
            if result == RESULT_MORTALITY:
                trout_state.alive[i] = False
                continue
            # DEFLECT or TRANSMIT: place at the reached location
            target_reach = last_passable

        # Arc O: apply straying. With probability stray_fraction, redirect
        # the returning adult to a random non-natal freshwater reach
        # (uniform across candidates that have wet cells). natal_reach_idx
        # stays unchanged (genetic/birth property); only reach_idx — the
        # spawning location — changes.
        if (
            config is not None
            and getattr(config, "stray_fraction", 0.0) > 0.0
            and rng is not None
        ):
            candidates = [
                r for r in reach_cells.keys()
                if r != natal and reach_cells[r] is not None and len(reach_cells[r]) > 0
            ]
            if candidates and rng.random() < config.stray_fraction:
                target_reach = int(rng.choice(candidates))

        cells = reach_cells.get(target_reach)
        if cells is None or len(cells) == 0:
            continue

        # Transition to returning adult
        if trout_state.sea_winters[i] >= repeat_threshold:
            n_repeat += 1
        trout_state.life_history[i] = int(LifeStage.RETURNING_ADULT)
        trout_state.zone_idx[i] = -1
        trout_state.reach_idx[i] = target_reach
        trout_state.cell_idx[i] = int(rng.choice(cells)) if rng is not None else int(cells[0])
        n_returned += 1

    return n_returned, n_repeat
