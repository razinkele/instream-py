"""Marine survival — 7 mortality sources for Baltic salmon.

Cormorant parameters: L1=15, L9=40 (Jepsen et al. 2019)
Seal parameters: L1=40, L9=80 (Lundstrom et al. 2010, Hansson et al. 2018)
"""
import numpy as np
from instream.modules.behavior import evaluate_logistic_array


def seal_predation(lengths, *, L1, L9, max_daily_rate=0.02):
    """Size-dependent seal predation. Larger fish -> higher risk.
    Scaled by max_daily_rate for realistic daily mortality."""
    size_vulnerability = evaluate_logistic_array(lengths, L1, L9)
    risk = max_daily_rate * size_vulnerability
    return 1.0 - risk


def cormorant_predation(lengths, zone_indices, *, L1, L9, active_zones,
                         max_daily_rate=0.03):
    """Cormorant predation on small post-smolts in estuary/coastal.
    Scaled by max_daily_rate (Jepsen et al. 2019: 1-3% population-level)."""
    size_vulnerability = 1.0 - evaluate_logistic_array(lengths, L1, L9)
    risk = max_daily_rate * size_vulnerability
    zone_mask = np.isin(zone_indices, active_zones)
    return np.where(zone_mask, 1.0 - risk, 1.0)


def background_mortality(n, *, daily_rate):
    return np.full(n, 1.0 - daily_rate)


def temperature_mortality(temperatures, *, threshold):
    excess = np.clip(temperatures - threshold, 0, None)
    return np.exp(-0.1 * excess)


def m74_mortality(n, *, prob, rng):
    if prob <= 0:
        return np.ones(n)
    return np.where(rng.random(n) < prob, 0.0, 1.0)


def post_smolt_vulnerability(days_since_ocean_entry, *, window):
    """Multiplier on mortality. >1 during first months at sea.
    Decays linearly from 2x to 1x over window days (default 60).
    Thorstad et al. 2012: critical period 2-4 months."""
    return np.clip(2.0 - days_since_ocean_entry / window, 1.0, 2.0)


def combined_marine_survival(
    lengths, weights, conditions, temperatures, predation_risks,
    zone_indices, days_since_ocean_entry, rng,
    *, seal_L1, seal_L9, cormorant_L1, cormorant_L9, cormorant_zones,
    cormorant_max_daily_rate=0.03,
    base_mort, temp_threshold, m74_prob, post_smolt_window,
):
    """Combine 5 natural mortality sources. Fishing is separate."""
    n = len(lengths)
    s_seal = seal_predation(lengths, L1=seal_L1, L9=seal_L9)
    s_corm = cormorant_predation(lengths, zone_indices,
                                  L1=cormorant_L1, L9=cormorant_L9,
                                  active_zones=cormorant_zones,
                                  max_daily_rate=cormorant_max_daily_rate)
    s_back = background_mortality(n, daily_rate=base_mort)
    s_temp = temperature_mortality(temperatures, threshold=temp_threshold)
    s_m74 = m74_mortality(n, prob=m74_prob, rng=rng)

    vuln = post_smolt_vulnerability(days_since_ocean_entry,
                                     window=post_smolt_window)
    combined = s_seal * s_corm * s_back * s_temp * s_m74
    # vuln > 1 amplifies mortality: survival^2 < survival^1
    return np.power(combined, vuln)
