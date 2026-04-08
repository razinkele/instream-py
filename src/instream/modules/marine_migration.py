"""Marine migration — zone-to-zone movement and maturation."""
import numpy as np


def check_maturation(lengths, conditions, sea_winters, rng,
                      *, min_sea_winters, prob_by_sw, min_length, min_condition):
    """Return boolean mask of fish that should return to freshwater."""
    n = len(lengths)
    mature = np.zeros(n, dtype=bool)
    for i in range(n):
        sw = int(sea_winters[i])
        if sw < min_sea_winters:
            continue
        if lengths[i] < min_length or conditions[i] < min_condition:
            continue
        prob = prob_by_sw.get(sw, prob_by_sw.get(max(prob_by_sw.keys()), 0.99))
        if rng.random() < prob:
            mature[i] = True
    return mature


def seasonal_zone_movement(zone_indices, days_in_zone, current_month,
                            *, zone_graph, max_residence):
    """Move fish to next zone when they exceed max residence time."""
    new_zones = zone_indices.copy()
    for i in range(len(zone_indices)):
        z = int(zone_indices[i])
        max_days = max_residence.get(z, 999999)
        if days_in_zone[i] > max_days:
            downstream = zone_graph.get(z, [])
            if downstream:
                new_zones[i] = downstream[0]
    return new_zones
