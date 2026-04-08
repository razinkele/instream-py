"""Marine growth — simplified bioenergetics for ocean phase.

Parameters from Hanson et al. (1997) Fish Bioenergetics 3.0,
adapted for Atlantic salmon. Uses O'Neill (1986) temperature function.
"""
import numpy as np


def _temp_dependence(temperatures, temp_opt, temp_max, temp_min=1.0):
    """Temperature dependence for consumption (modified O'Neill 1986 form).

    Returns fraction 0-1, peaking at temp_opt, zero at temp_max and temp_min.
    Rising limb: linear from temp_min to temp_opt.
    Falling limb: O'Neill form V^X * exp(X*(1-V)).

    Atlantic salmon consumption approaches zero below ~1C (Elliott 1976).
    """
    x = np.asarray(temperatures, dtype=np.float64)
    frac = np.zeros_like(x)

    # Rising limb: linear from temp_min to temp_opt
    rising = (x >= temp_min) & (x <= temp_opt)
    if temp_opt > temp_min:
        frac[rising] = (x[rising] - temp_min) / (temp_opt - temp_min)

    # Falling limb: O'Neill form from temp_opt to temp_max
    falling = (x > temp_opt) & (x < temp_max)
    if np.any(falling):
        V = (temp_max - x[falling]) / (temp_max - temp_opt)
        X = 2.0  # shape parameter for salmonids
        frac[falling] = np.power(V, X) * np.exp(X * (1.0 - V))

    return np.clip(frac, 0, 1)


def marine_growth_rate(
    lengths, weights, temperatures, prey_indices, conditions,
    *, cmax_A, cmax_B, growth_efficiency, resp_A, resp_B,
    temp_opt, temp_max,
):
    """Daily weight change (grams) for marine fish.

    CMax parameters: A=0.303, B=-0.275 (Hanson et al. 1997)
    """
    cmax_wt = cmax_A * np.power(weights, cmax_B)
    temp_frac = _temp_dependence(temperatures, temp_opt, temp_max)
    cmax = cmax_wt * temp_frac * weights  # grams/day

    consumption = cmax * prey_indices * np.clip(conditions, 0.1, 1.5)

    resp_wt = resp_A * np.power(weights, resp_B)
    resp = resp_wt * temperatures * weights / temp_opt

    daily_growth = (consumption - resp) * growth_efficiency
    return daily_growth
