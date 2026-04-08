"""Marine fishing mortality — gear selectivity, bycatch, harvest tracking."""
import numpy as np
from dataclasses import dataclass
from datetime import date


def logistic_selectivity(lengths, *, L50, slope):
    return 1.0 / (1.0 + np.exp(-slope * (lengths - L50)))


def normal_selectivity(lengths, *, mean, sd):
    return np.exp(-0.5 * ((lengths - mean) / sd) ** 2)


@dataclass
class HarvestRecord:
    date: date
    zone: str
    gear_type: str
    num_landed: int
    num_bycatch_killed: int
    mean_length_landed: float
    total_weight_landed_kg: float


def apply_fishing_mortality(
    lengths, zone_indices, current_month, gear_configs,
    zone_names, min_legal_length, rng,
):
    """Apply all gear types. Returns (landed_mask, dead_mask) boolean arrays."""
    n = len(lengths)
    landed = np.zeros(n, dtype=bool)
    dead = np.zeros(n, dtype=bool)

    for gear in gear_configs:
        if current_month not in gear.get("open_months", []):
            continue
        active_zone_indices = [
            zone_names.index(z) for z in gear.get("zones", [])
            if z in zone_names
        ]
        in_zone = np.isin(zone_indices, active_zone_indices)
        if not np.any(in_zone):
            continue
        effort = gear.get("daily_effort", 0.001)
        encountered = in_zone & (rng.random(n) < effort)
        if not np.any(encountered):
            continue
        sel_type = gear.get("selectivity_type", "logistic")
        if sel_type == "logistic":
            sel = logistic_selectivity(lengths, L50=gear["selectivity_L50"],
                                        slope=gear["selectivity_slope"])
        elif sel_type == "normal":
            sel = normal_selectivity(lengths, mean=gear["selectivity_mean"],
                                      sd=gear["selectivity_sd"])
        else:
            sel = np.ones(n)
        retained = encountered & (rng.random(n) < sel)
        legal = retained & (lengths >= min_legal_length)
        landed |= legal
        sublegal = retained & (lengths < min_legal_length)
        bycatch_mort = gear.get("bycatch_mortality", 0.1)
        bycatch_dead = sublegal & (rng.random(n) < bycatch_mort)
        dead |= bycatch_dead

    return landed, dead
