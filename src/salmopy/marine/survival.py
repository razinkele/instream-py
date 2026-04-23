"""Marine survival — 7 mortality sources (inSALMON v0.15.0).

Each source returns a daily hazard in [0, 1]; total survival is the product
of (1 - hazard_i) across sources. This is cleaner than additive rates when
any single source approaches its ceiling.

Sources
-------
1. Seal predation           — size-dependent logistic (L1..L9), all zones
2. Cormorant predation      — size-dependent logistic, nearshore zones only,
                              post-smolt vulnerability decay
3. Background mortality     — constant daily rate
4. Temperature stress       — threshold above T_crit
5. M74 syndrome             — constant daily rate representing cohort loss
6. Fishing harvest          — handled by marine.fishing.fishing_mortality()
7. Fishing bycatch          — handled by marine.fishing.fishing_mortality()

This module covers sources 1..5. Fishing (6,7) lives in marine.fishing and
is combined by the MarineDomain orchestrator.
"""

from __future__ import annotations

import numpy as np


def _logistic_hazard(
    length: np.ndarray, L1: float, L9: float, max_daily: float
) -> np.ndarray:
    """Logistic-shaped daily hazard as a function of fork length.

    Hazard rises from ~0.1 * max_daily at ``L1`` to ~0.9 * max_daily at ``L9``.
    Above ``L9`` it saturates at ``max_daily``; below ``L1`` it decays toward 0.
    """
    l = np.asarray(length, dtype=np.float64)
    width = max(L9 - L1, 1e-6)
    # Centre of the logistic is midway between L1 and L9
    midpoint = 0.5 * (L1 + L9)
    # slope chosen so that f(L1)=0.1, f(L9)=0.9  ->  logit(0.1)=-2.197
    k = 2.0 * 2.197 / width
    return max_daily / (1.0 + np.exp(-k * (l - midpoint)))


_SEAL_FORCING_CACHE: "dict" = {}


def seal_hazard(
    length: np.ndarray,
    config,
    current_year: int | None = None,
) -> np.ndarray:
    """Daily seal predation hazard. Larger fish are more targeted.

    Arc P: when `config.seal_abundance_csv` is set and `current_year` is
    provided, the base length-logistic hazard is scaled by a Holling
    Type II multiplier anchored at `config.seal_reference_abundance`.
    Default (no CSV, no current_year) preserves legacy static behavior.
    """
    base = _logistic_hazard(
        length,
        L1=config.marine_mort_seal_L1,
        L9=config.marine_mort_seal_L9,
        max_daily=config.marine_mort_seal_max_daily,
    )
    if (
        getattr(config, "seal_abundance_csv", None) is not None
        and current_year is not None
    ):
        from pathlib import Path
        path = Path(config.seal_abundance_csv)
        if path not in _SEAL_FORCING_CACHE:
            from salmopy.marine.seal_forcing import load_seal_abundance
            _SEAL_FORCING_CACHE[path] = load_seal_abundance(path)
        from salmopy.marine.seal_forcing import (
            abundance_for_year, seal_hazard_multiplier,
        )
        abundance = abundance_for_year(
            _SEAL_FORCING_CACHE[path],
            current_year,
            config.seal_sub_basin,
        )
        if abundance is not None:
            mult = seal_hazard_multiplier(
                abundance=abundance,
                reference_abundance=config.seal_reference_abundance,
                saturation_k_half=config.seal_saturation_k_half,
            )
            base = base * mult
    return base


def cormorant_hazard(
    length: np.ndarray,
    zone_idx: np.ndarray,
    days_since_ocean_entry: np.ndarray,
    cormorant_zone_indices: np.ndarray,
    config,
) -> np.ndarray:
    """Daily cormorant predation hazard.

    Cormorants target small smolts in nearshore zones only. Hazard is
    highest for the smallest fish and decays linearly to zero beyond
    ``post_smolt_vulnerability_days``.
    """
    # Inverted logistic: small fish -> high hazard. Reuse helper by passing
    # a reflected length (L9 - length) and swapping L1/L9.
    reflected = (config.marine_mort_cormorant_L1 + config.marine_mort_cormorant_L9) - np.asarray(length, dtype=np.float64)
    base = _logistic_hazard(
        reflected,
        L1=config.marine_mort_cormorant_L1,
        L9=config.marine_mort_cormorant_L9,
        max_daily=config.marine_mort_cormorant_max_daily,
    )

    # Restrict to nearshore zones
    in_zone = np.isin(np.asarray(zone_idx), cormorant_zone_indices)

    # Post-smolt window decay
    vuln_days = max(config.post_smolt_vulnerability_days, 1)
    days = np.asarray(days_since_ocean_entry, dtype=np.float64)
    decay = np.clip(1.0 - days / vuln_days, 0.0, 1.0)

    return np.where(in_zone, base * decay, 0.0)


def background_hazard(n: int, config) -> np.ndarray:
    """Constant daily background mortality."""
    return np.full(n, config.marine_mort_base, dtype=np.float64)


def temperature_stress_hazard(temperature: np.ndarray, config) -> np.ndarray:
    """Daily hazard from thermal stress above ``temperature_stress_threshold``."""
    t = np.asarray(temperature, dtype=np.float64)
    above = t > config.temperature_stress_threshold
    return np.where(above, config.temperature_stress_daily, 0.0)


def m74_hazard(n: int, config) -> np.ndarray:
    """Daily M74 (thiamine-deficiency) hazard, constant per cohort."""
    return np.full(n, config.marine_mort_m74_prob, dtype=np.float64)


_POST_SMOLT_CACHE: "dict" = {}

POST_SMOLT_WINDOW_DAYS = 365


def marine_survival(
    length: np.ndarray,
    zone_idx: np.ndarray,
    temperature: np.ndarray,
    days_since_ocean_entry: np.ndarray,
    cormorant_zone_indices: np.ndarray,
    config,
    is_hatchery: np.ndarray | None = None,
    current_year: int | None = None,
) -> np.ndarray:
    """Combined daily survival probability from sources 1..5.

    Parameters
    ----------
    is_hatchery : optional bool array
        If provided, hatchery-origin fish receive an amplified cormorant
        hazard via ``config.hatchery_predator_naivety_multiplier`` during
        the post-smolt vulnerability window. The multiplier applies only
        to the cormorant term; it naturally decays with the
        existing post-smolt decay in :func:`cormorant_hazard`, so no
        separate time gate is needed.
    current_year : optional int (Arc N)
        Calendar year used with ``config.post_smolt_survival_forcing_csv``
        to override the background hazard for fish in the post-smolt
        window (days_since_ocean_entry < POST_SMOLT_WINDOW_DAYS), keyed
        by SMOLT year (derived as current_year - days_since // 365) so a
        fish that emigrated in July Y and is now in January Y+1 still
        gets Y's cohort-posterior forcing.

    Returns
    -------
    (N,) float64
        Per-fish probability of surviving this day from natural sources.
        Multiply with fishing-survival to obtain total survival.
    """
    n = np.asarray(length).shape[0]
    h_seal = seal_hazard(length, config, current_year=current_year)
    h_corm = cormorant_hazard(
        length, zone_idx, days_since_ocean_entry, cormorant_zone_indices, config
    )
    if is_hatchery is not None and np.any(is_hatchery):
        h_corm = np.where(
            is_hatchery,
            h_corm * config.hatchery_predator_naivety_multiplier,
            h_corm,
        )
    h_back = background_hazard(n, config)

    # Arc N: post-smolt survival override keyed by smolt-year cohort
    if (
        getattr(config, "post_smolt_survival_forcing_csv", None) is not None
        and getattr(config, "stock_unit", None) is not None
        and current_year is not None
    ):
        from pathlib import Path
        path = Path(config.post_smolt_survival_forcing_csv)
        if path not in _POST_SMOLT_CACHE:
            from salmopy.marine.survival_forcing import load_post_smolt_forcing
            _POST_SMOLT_CACHE[path] = load_post_smolt_forcing(path)
        from salmopy.marine.survival_forcing import (
            annual_survival_for_year, daily_hazard_multiplier,
        )
        # Smolt year = current_year - floor(days_since_ocean_entry / 365)
        smolt_years = current_year - (
            np.asarray(days_since_ocean_entry) // POST_SMOLT_WINDOW_DAYS
        )
        post_smolt_mask = np.asarray(days_since_ocean_entry) < POST_SMOLT_WINDOW_DAYS
        h_forced_array = np.full_like(h_back, np.nan, dtype=np.float64)
        for sy in np.unique(smolt_years[post_smolt_mask]):
            S_ann = annual_survival_for_year(
                _POST_SMOLT_CACHE[path], int(sy), config.stock_unit,
            )
            if S_ann is not None:
                h_forced_array[smolt_years == sy] = daily_hazard_multiplier(S_ann)
        forced_mask = post_smolt_mask & np.isfinite(h_forced_array)
        h_back = np.where(forced_mask, h_forced_array, h_back)

    h_temp = temperature_stress_hazard(temperature, config)
    h_m74 = m74_hazard(n, config)

    survival = (
        (1.0 - h_seal)
        * (1.0 - h_corm)
        * (1.0 - h_back)
        * (1.0 - h_temp)
        * (1.0 - h_m74)
    )
    return np.clip(survival, 0.0, 1.0)


def apply_marine_survival(
    trout_state,
    zone_state,
    marine_mask: np.ndarray,
    config,
    current_date,
    rng,
) -> int:
    """Apply daily natural mortality in-place.

    Returns the number of fish killed.
    """
    if not np.any(marine_mask):
        return 0

    idx = np.where(marine_mask)[0]
    zones = trout_state.zone_idx[idx].astype(np.int64, copy=False)

    # Build cormorant zone-index list from zone name -> index map
    # Case-insensitive match: the config file may use "Estuary" while the
    # in-state name defaults to "estuary" (or vice versa).
    name_to_idx = {str(nm).strip().lower(): i for i, nm in enumerate(zone_state.name)}
    corm_zones = np.array(
        [
            name_to_idx[str(z).strip().lower()]
            for z in config.marine_mort_cormorant_zones
            if str(z).strip().lower() in name_to_idx
        ],
        dtype=np.int64,
    )

    ordinal_today = current_date.toordinal()
    days_since = ordinal_today - trout_state.smolt_date[idx].astype(np.int64, copy=False)

    surv = marine_survival(
        length=trout_state.length[idx],
        zone_idx=zones,
        temperature=zone_state.temperature[zones],
        days_since_ocean_entry=np.maximum(days_since, 0),
        cormorant_zone_indices=corm_zones,
        config=config,
        is_hatchery=trout_state.is_hatchery[idx],
        current_year=current_date.year,
    )

    draws = rng.random(size=idx.shape[0])
    killed = draws > surv
    if np.any(killed):
        trout_state.alive[idx[killed]] = False

    return int(np.sum(killed))
