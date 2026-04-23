"""Angler harvest — size-selective fishing mortality with bag limits."""



def compute_harvest(
    trout_state,
    num_anglers,
    catch_rate,
    min_length,
    bag_limit,
    rng,
):
    """Apply angler harvest mortality for one day.

    Parameters
    ----------
    trout_state : TroutState
        All trout state arrays.
    num_anglers : float
        Number of angler-days of effort today.
    catch_rate : float
        Probability of catching an eligible fish per angler per fish encounter.
    min_length : float
        Minimum harvestable length (cm). Fish below this are released.
    bag_limit : int
        Maximum fish harvested per day (across all anglers combined).
    rng : numpy.random.Generator
        Random number generator.

    Returns
    -------
    harvest_records : list of dict
        Records of harvested fish: {species_idx, length, weight, cell_idx}.
    """
    alive = trout_state.alive_indices()
    if len(alive) == 0 or num_anglers <= 0:
        return []

    # Filter eligible fish (alive, length >= min_length)
    lengths = trout_state.length[alive]
    eligible_mask = lengths >= min_length
    eligible = alive[eligible_mask]

    if len(eligible) == 0:
        return []

    # Encounter probability scales with angler effort
    # Each eligible fish has a chance of being caught
    encounter_prob = min(1.0, catch_rate * num_anglers / max(1, len(eligible)))

    # Draw random catches
    draws = rng.random(len(eligible))
    caught_mask = draws < encounter_prob

    # Apply bag limit
    caught_indices = eligible[caught_mask]
    if len(caught_indices) > bag_limit:
        caught_indices = rng.choice(caught_indices, size=bag_limit, replace=False)

    # Record and kill
    records = []
    for idx in caught_indices:
        records.append(
            {
                "species_idx": int(trout_state.species_idx[idx]),
                "length": float(trout_state.length[idx]),
                "weight": float(trout_state.weight[idx]),
                "cell_idx": int(trout_state.cell_idx[idx]),
            }
        )
        trout_state.alive[idx] = False

    return records
