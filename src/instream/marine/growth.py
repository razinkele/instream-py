"""Marine growth bioenergetics (inSALMON v0.15.0).

Simplified Hanson et al. 1997 Fish Bioenergetics 3.0 model applied to
post-smolt and adult salmon in the marine phase. Compared to the freshwater
cell-level routine this module:

* has no drift/search activity choice (no cell competition),
* uses a single prey index per zone instead of drift/search rates,
* returns a daily weight delta (g/day) as a pure function of arrays.

Formulae
--------
CMax(W, T)      = cmax_A * W^(1 + cmax_B) * f_c(T)           [g/day]
f_c(T)          = max(0, (Tmax - T) / (Tmax - Topt)) for T <= Tmax, else 0
consumption     = CMax * prey_index * condition_modifier
respiration     = resp_A * W^(1 + resp_B) * Q10^((T - Topt) / 10)
daily_growth    = (consumption - respiration) * growth_efficiency

All inputs are broadcastable numpy arrays; the function operates vectorised
and never allocates Python-level lists.
"""

from __future__ import annotations

import numpy as np


def _cmax_temperature_response(
    temperature: np.ndarray, topt: float, tmax: float
) -> np.ndarray:
    """Return the unitless [0, 1] temperature multiplier for CMax.

    Linear descent from 1.0 at Topt to 0.0 at Tmax, then clamped to zero.
    Below Topt the response is also linear (from 0 at 0 deg C to 1 at Topt)
    to prevent unrealistic winter consumption at near-freezing Baltic water.
    """
    t = np.asarray(temperature, dtype=np.float64)
    above = (tmax - t) / max(tmax - topt, 1e-6)
    below = t / max(topt, 1e-6)
    response = np.where(t <= topt, below, above)
    return np.clip(response, 0.0, 1.0)


def marine_growth(
    weights: np.ndarray,
    temperatures: np.ndarray,
    prey_indices: np.ndarray,
    conditions: np.ndarray,
    *,
    cmax_A: float,
    cmax_B: float,
    cmax_topt: float,
    cmax_tmax: float,
    resp_A: float,
    resp_B: float,
    resp_Q10: float,
    growth_efficiency: float,
) -> np.ndarray:
    """Compute daily marine weight delta (g/day) for each fish.

    Parameters
    ----------
    weights : (N,) float64
        Fish wet weight (g). Zero or negative weights return zero growth.
    temperatures : (N,) float64
        Ambient zone temperature (deg C).
    prey_indices : (N,) float64
        Zone prey density (0..1). 0 = no food, 1 = saturated.
    conditions : (N,) float64
        Condition factor (0..1). Acts as a modifier on realised intake.
    cmax_A, cmax_B : float
        Allometric CMax coefficients (Hanson et al. 1997 defaults 0.303, -0.275).
    cmax_topt, cmax_tmax : float
        Optimal and maximum temperatures for consumption (deg C).
    resp_A, resp_B : float
        Allometric respiration coefficients.
    resp_Q10 : float
        Respiration Q10 temperature coefficient.
    growth_efficiency : float
        K2 net growth efficiency (0..1).

    Returns
    -------
    (N,) float64
        Daily weight change (g/day). Can be negative when respiration
        exceeds assimilated consumption (starvation).
    """
    w = np.asarray(weights, dtype=np.float64)
    t = np.asarray(temperatures, dtype=np.float64)
    prey = np.asarray(prey_indices, dtype=np.float64)
    cond = np.asarray(conditions, dtype=np.float64)

    valid = w > 0.0

    w_safe = np.where(valid, w, 1.0)  # avoid 0^exp warnings
    cmax = cmax_A * np.power(w_safe, 1.0 + cmax_B)
    cmax *= _cmax_temperature_response(t, cmax_topt, cmax_tmax)
    consumption = cmax * np.clip(prey, 0.0, 1.0) * np.clip(cond, 0.0, 1.0)

    q10_exp = (t - cmax_topt) / 10.0
    respiration = resp_A * np.power(w_safe, 1.0 + resp_B) * np.power(resp_Q10, q10_exp)

    delta = (consumption - respiration) * growth_efficiency
    return np.where(valid, delta, 0.0)


def apply_marine_growth(
    trout_state,
    zone_state,
    marine_mask: np.ndarray,
    config,
) -> None:
    """Apply :func:`marine_growth` in-place to *trout_state* for fish in
    *marine_mask*.

    Updates ``weight`` and re-derives ``condition`` as
    ``weight / length_cubed_factor``, clamped to [0, 1.5]. Length is not
    updated here — length growth in the marine phase is handled by a
    separate length-weight relationship in a later step.
    """
    if not np.any(marine_mask):
        return

    idx = np.where(marine_mask)[0]
    zones = trout_state.zone_idx[idx].astype(np.int64, copy=False)

    delta = marine_growth(
        weights=trout_state.weight[idx],
        temperatures=zone_state.temperature[zones],
        prey_indices=zone_state.prey_index[zones],
        conditions=trout_state.condition[idx],
        cmax_A=config.marine_cmax_A,
        cmax_B=config.marine_cmax_B,
        cmax_topt=config.marine_cmax_topt,
        cmax_tmax=config.marine_cmax_tmax,
        resp_A=config.marine_resp_A,
        resp_B=config.marine_resp_B,
        resp_Q10=config.marine_resp_Q10,
        growth_efficiency=config.marine_growth_efficiency,
    )

    new_weight = np.maximum(0.0, trout_state.weight[idx] + delta)
    trout_state.weight[idx] = new_weight

    lengths = trout_state.length[idx]
    healthy_weight = np.where(lengths > 0, 0.01 * np.power(lengths, 3.0), 1.0)
    trout_state.condition[idx] = np.clip(new_weight / healthy_weight, 0.0, 1.5)
