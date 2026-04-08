"""Smoltification — photoperiod + temperature triggered transition."""
import numpy as np


def update_smolt_readiness(
    readiness, lengths, temperature, photoperiod,
    *, min_length, temp_min, temp_max, photoperiod_threshold, rate=0.02,
):
    """Update smolt readiness. Accumulates when conditions met.
    Default rate=0.02 requires ~50 qualifying days (~350-400 degree-days at 7-8C).
    Reference: Handeland et al. 1998."""
    new = readiness.copy()
    eligible = (
        (lengths >= min_length)
        & (temperature >= temp_min)
        & (temperature <= temp_max)
        & (photoperiod >= photoperiod_threshold)
    )
    new[eligible] = np.clip(new[eligible] + rate, 0.0, 1.0)
    return new


def check_smolt_trigger(readiness, current_month, *,
                         window_start_month, window_end_month):
    """Return boolean mask of fish ready to smoltify.
    Only triggers within seasonal window (Baltic: April-June)."""
    in_window = window_start_month <= current_month <= window_end_month
    if not in_window:
        return np.zeros(len(readiness), dtype=bool)
    return readiness >= 1.0
