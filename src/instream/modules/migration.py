"""Migration — reach connectivity, downstream migration, outmigrant tracking."""
import numpy as np
from instream.modules.behavior import evaluate_logistic
from instream.state.life_stage import LifeStage


def build_reach_graph(upstream_junctions, downstream_junctions):
    """Build reach connectivity: dict mapping reach_idx -> list of downstream reach indices."""
    n = len(upstream_junctions)
    graph = {i: [] for i in range(n)}
    for i in range(n):
        for j in range(n):
            if i != j and downstream_junctions[i] == upstream_junctions[j]:
                graph[i].append(j)
    return graph


def migration_fitness(length, L1, L9):
    """Migration fitness for a fish (logistic of length)."""
    return evaluate_logistic(length, L1, L9)


def should_migrate(migration_fit, best_habitat_fit, life_history):
    """Decide if fish should migrate downstream."""
    if life_history != LifeStage.PARR:  # only anad_juve migrates
        return False
    return migration_fit > best_habitat_fit


def migrate_fish_downstream(trout_state, fish_idx, reach_graph,
                            marine_config=None, smolt_readiness_threshold=0.8,
                            smolt_min_length=12.0, current_date=None):
    """Move a fish to the downstream reach, or make it an outmigrant.

    When *marine_config* is provided and the fish is a PARR at the river
    mouth (no downstream reach) with sufficient readiness and length, it
    transitions to SMOLT and enters the marine domain instead of dying.

    Returns
    -------
    (outmigrants, smoltified) : tuple[list, bool]
        ``outmigrants`` is a list of the outmigrant record dicts (empty when
        the fish just moved downstream). ``smoltified`` is True iff this
        call transitioned a PARR to SMOLT and sent it to the marine domain.
    """
    outmigrants = []
    smoltified = False
    current_reach = int(trout_state.reach_idx[fish_idx])
    downstream = reach_graph.get(current_reach, [])
    if len(downstream) > 0:
        trout_state.reach_idx[fish_idx] = downstream[0]
    else:
        # No downstream reach — record outmigrant
        outmigrants.append({
            "species_idx": int(trout_state.species_idx[fish_idx]),
            "length": float(trout_state.length[fish_idx]),
            "reach_idx": current_reach,
        })

        # Attempt smolt transition when marine domain is available
        life_history = int(trout_state.life_history[fish_idx])
        fish_length = float(trout_state.length[fish_idx])
        readiness = float(trout_state.smolt_readiness[fish_idx])

        if (
            marine_config is not None
            and life_history == LifeStage.PARR
            and readiness >= smolt_readiness_threshold
            and fish_length >= smolt_min_length
        ):
            # Transition to SMOLT and enter marine estuary (zone 0)
            trout_state.life_history[fish_idx] = int(LifeStage.SMOLT)
            trout_state.zone_idx[fish_idx] = 0
            trout_state.natal_reach_idx[fish_idx] = current_reach
            trout_state.smolt_date[fish_idx] = (
                current_date.toordinal() if current_date is not None else 0
            )
            trout_state.cell_idx[fish_idx] = -1
            trout_state.reach_idx[fish_idx] = -1
            smoltified = True
        else:
            # Kill as before
            trout_state.alive[fish_idx] = False
    return outmigrants, smoltified


def outmigration_probability(fitness, length, min_length, max_prob=0.1):
    """Fitness-based probability of downstream outmigration.

    Fish below min_length never migrate. Above min_length, probability
    increases as fitness decreases.
    """
    if length < min_length:
        return 0.0
    return max_prob * max(0.0, 1.0 - fitness)


def bin_outmigrant(length, length_classes):
    """Bin an outmigrant by length class. Returns bin index (0-based)."""
    for i, threshold in enumerate(length_classes):
        if length < threshold:
            return i
    return len(length_classes)  # last bin
