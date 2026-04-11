"""Marine fishing mortality — gear selectivity, harvest, bycatch (v0.15.0).

Implements design-document Section 8: per-fish stochastic encounter with
each active gear type, followed by a size-selective retention test and
legal-size decision.

Outputs for each fish/day are:
* a survival probability (1.0 if not encountered or escaped, 0.0 if killed),
* an optional HarvestRecord accumulator at the zone/gear level.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np


# ---------------------------------------------------------------------------
# HarvestRecord
# ---------------------------------------------------------------------------


@dataclass
class HarvestRecord:
    """Daily aggregate of a single (zone, gear) fishing event."""

    date: datetime.date
    zone: str
    gear_type: str
    num_landed: int = 0
    num_bycatch_killed: int = 0
    total_weight_landed_kg: float = 0.0
    mean_length_landed: float = 0.0


# ---------------------------------------------------------------------------
# Selectivity curves
# ---------------------------------------------------------------------------


def logistic_selectivity(length: np.ndarray, L50: float, slope: float) -> np.ndarray:
    """Logistic knife-edge retention probability (0..1)."""
    l = np.asarray(length, dtype=np.float64)
    return 1.0 / (1.0 + np.exp(-slope * (l - L50) / 10.0))


def normal_selectivity(length: np.ndarray, mean: float, sd: float) -> np.ndarray:
    """Gaussian bell-curve retention probability (0..1 at the mode)."""
    l = np.asarray(length, dtype=np.float64)
    return np.exp(-0.5 * ((l - mean) / max(sd, 1e-6)) ** 2)


def gear_selectivity(length: np.ndarray, gear) -> np.ndarray:
    """Dispatch to the correct curve by gear.selectivity_type."""
    if gear.selectivity_type == "logistic":
        return logistic_selectivity(length, gear.selectivity_L50, gear.selectivity_slope)
    if gear.selectivity_type == "normal":
        return normal_selectivity(length, gear.selectivity_mean, gear.selectivity_sd)
    raise ValueError(f"Unknown selectivity_type: {gear.selectivity_type!r}")


# ---------------------------------------------------------------------------
# Core fishing mortality
# ---------------------------------------------------------------------------


def fishing_mortality(
    lengths: np.ndarray,
    zone_idx: np.ndarray,
    current_date: datetime.date,
    zone_name_by_idx: List[str],
    gear_configs: Dict[str, "GearConfig"],  # noqa: F821
    min_legal_length: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, Dict[str, int]]:
    """Return per-fish survival and a {gear_type: num_killed} tally.

    Parameters
    ----------
    lengths, zone_idx : (N,) arrays
        Fish state.
    current_date : datetime.date
        Today — used to check each gear's ``open_months``.
    zone_name_by_idx : list of str
        Zone names indexed by zone_idx.
    gear_configs : mapping name -> GearConfig
    min_legal_length : float
        Harvest threshold. Fish below this go to bycatch logic.
    rng : numpy Generator
    """
    n = lengths.shape[0]
    survival = np.ones(n, dtype=np.float64)
    tally: Dict[str, int] = {}

    month = current_date.month

    for gear_name, gear in gear_configs.items():
        if month not in gear.open_months:
            continue
        if gear.daily_effort <= 0.0:
            continue

        zone_ok = np.zeros(n, dtype=bool)
        for zi, zname in enumerate(zone_name_by_idx):
            if zname in gear.zones:
                zone_ok |= zone_idx == zi
        if not np.any(zone_ok):
            continue

        # 1. Encounter: random draw per fish
        encounter = rng.random(n) < gear.daily_effort
        encounter &= zone_ok
        if not np.any(encounter):
            continue

        # 2. Retention: selectivity curve
        retention = gear_selectivity(lengths, gear)
        retained = (rng.random(n) < retention) & encounter
        if not np.any(retained):
            continue

        # 3. Legal vs bycatch
        legal = retained & (lengths >= min_legal_length)
        sublegal = retained & (lengths < min_legal_length)

        # Legal fish: always killed (landed)
        survival[legal] = 0.0
        landed = int(np.sum(legal))

        # Sublegal fish: killed with prob bycatch_mortality
        if np.any(sublegal):
            bycatch_draws = rng.random(n)
            killed_bycatch = sublegal & (bycatch_draws < gear.bycatch_mortality)
            survival[killed_bycatch] = 0.0
            bycatch = int(np.sum(killed_bycatch))
        else:
            bycatch = 0

        tally[gear_name] = landed + bycatch

    return survival, tally


def apply_fishing_mortality(
    trout_state,
    zone_state,
    marine_mask: np.ndarray,
    config,
    current_date: datetime.date,
    rng: np.random.Generator,
) -> List[HarvestRecord]:
    """Apply fishing in-place. Returns one HarvestRecord per active gear."""
    if config.marine_fishing is None or not config.marine_fishing.gear_types:
        return []
    if not np.any(marine_mask):
        return []

    idx = np.where(marine_mask)[0]
    lengths = trout_state.length[idx]
    zones = trout_state.zone_idx[idx].astype(np.int64, copy=False)

    zone_names = [str(zone_state.name[i]) for i in range(zone_state.num_zones)]

    survival, tally = fishing_mortality(
        lengths=lengths,
        zone_idx=zones,
        current_date=current_date,
        zone_name_by_idx=zone_names,
        gear_configs=config.marine_fishing.gear_types,
        min_legal_length=config.marine_fishing.min_legal_length,
        rng=rng,
    )

    killed = survival <= 0.0
    if np.any(killed):
        dead_idx = idx[killed]
        if hasattr(trout_state, "alive"):
            trout_state.alive[dead_idx] = False
        if hasattr(trout_state, "is_alive"):
            trout_state.is_alive[dead_idx] = False

    return [
        HarvestRecord(
            date=current_date,
            zone="",         # zone-level split left for future refinement
            gear_type=gear_name,
            num_landed=num,  # aggregated; bycatch vs landed split not tracked here
        )
        for gear_name, num in tally.items()
        if num > 0
    ]
