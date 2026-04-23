"""Estuarine stress functions — salinity and dissolved oxygen.

These are implemented as direct daily survival penalties rather than
respiration multipliers, because marine bioenergetics are currently stubs.
This is self-contained and biologically valid.

Usage::

    from salmopy.modules.estuary import salinity_survival, do_stress

    s = salinity_survival(salinity=22.0, s_opt=8.0, s_tol=4.0, s_range=20.0, max_daily_mort=0.02)
    force_move, surv = do_stress(do=2.5, lethal_threshold=2.0, escape_threshold=4.0)
"""

from __future__ import annotations

import numpy as np


def salinity_survival(
    salinity: float,
    s_opt: float = 8.0,
    s_tol: float = 4.0,
    s_range: float = 20.0,
    max_daily_mort: float = 0.02,
) -> float:
    """Daily survival probability from salinity stress in the estuary.

    Stress begins when salinity exceeds ``s_opt + s_tol`` and scales
    linearly up to ``max_daily_mort`` over ``s_range`` PSU.

    Parameters
    ----------
    salinity : float
        Current salinity (PSU).
    s_opt : float
        Optimal salinity (PSU) — no stress at or below this.
    s_tol : float
        Tolerance band above optimal before stress begins.
    s_range : float
        PSU range over which mortality scales from 0 to max_daily_mort.
    max_daily_mort : float
        Maximum daily mortality probability from salinity.

    Returns
    -------
    float
        Survival probability in [1 - max_daily_mort, 1.0].
    """
    excess = salinity - s_opt - s_tol
    if excess <= 0.0:
        return 1.0
    if s_range <= 0.0:
        return 1.0 - max_daily_mort
    fraction = min(excess / s_range, 1.0)
    return 1.0 - max_daily_mort * fraction


def do_stress(
    dissolved_oxygen: float,
    lethal_threshold: float = 2.0,
    escape_threshold: float = 4.0,
    lethal_daily_mort: float = 0.2,
) -> tuple[bool, float]:
    """Dissolved oxygen stress: mortality or forced zone migration.

    Parameters
    ----------
    dissolved_oxygen : float
        Current DO concentration (mg/L).
    lethal_threshold : float
        DO below which high daily mortality applies.
    escape_threshold : float
        DO below which fish attempt to flee to next zone.
    lethal_daily_mort : float
        Daily mortality probability when DO < lethal.

    Returns
    -------
    (force_move, survival_prob) : tuple[bool, float]
        ``force_move`` is True if fish should advance to next zone.
        ``survival_prob`` is the daily survival from DO stress.
    """
    if dissolved_oxygen >= escape_threshold:
        return False, 1.0
    if dissolved_oxygen < lethal_threshold:
        return True, 1.0 - lethal_daily_mort
    # Between lethal and escape: force move but no mortality
    return True, 1.0


def apply_estuary_stress(
    trout_state,
    zone_state,
    marine_mask: np.ndarray,
    estuary_config,
    rng: np.random.Generator,
) -> None:
    """Apply salinity and DO stress to fish in the estuary zone (zone 0).

    Modifies ``trout_state.alive`` and ``trout_state.zone_idx`` in-place.

    Parameters
    ----------
    trout_state : TroutState
        Fish state arrays.
    zone_state : ZoneState
        Current zone environmental conditions.
    marine_mask : np.ndarray of bool
        Mask of alive marine fish (zone_idx >= 0).
    estuary_config : EstuaryConfig
        Estuary stress parameters.
    rng : np.random.Generator
        Random number generator.
    """
    if estuary_config is None:
        return

    ts = trout_state
    # Find fish in estuary (zone_idx == 0)
    estuary_mask = marine_mask & (ts.zone_idx == 0)
    estuary_idx = np.where(estuary_mask)[0]
    if len(estuary_idx) == 0:
        return

    # Get estuary zone conditions
    estuary_salinity = float(zone_state.salinity[0])
    estuary_do = float(getattr(zone_state, 'dissolved_oxygen', np.array([99.0]))[0])

    # Salinity survival
    sal_surv = salinity_survival(
        estuary_salinity,
        s_opt=estuary_config.salinity_optimal,
        s_tol=estuary_config.salinity_tolerance,
        s_range=estuary_config.salinity_range,
        max_daily_mort=estuary_config.salinity_max_daily_mort,
    )

    # DO stress
    force_move, do_surv = do_stress(
        estuary_do,
        lethal_threshold=estuary_config.do_lethal_threshold,
        escape_threshold=estuary_config.do_escape_threshold,
        lethal_daily_mort=estuary_config.do_lethal_daily_mort,
    )

    # Combined daily survival
    combined_surv = sal_surv * do_surv

    if combined_surv < 1.0:
        draws = rng.random(len(estuary_idx))
        dies = draws >= combined_surv
        ts.alive[estuary_idx[dies]] = False

    # Forced zone migration on low DO
    if force_move:
        alive_in_estuary = estuary_idx[ts.alive[estuary_idx]]
        if len(alive_in_estuary) > 0:
            # Move to zone 1 (coastal) if it exists
            if zone_state.num_zones > 1:
                ts.zone_idx[alive_in_estuary] = 1
