"""Migration — reach connectivity, downstream migration, outmigrant tracking."""
import numpy as np
from instream.agents.life_stage import LifeStage
from instream.modules.behavior import evaluate_logistic


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


def migrate_fish_downstream(trout_state, fish_idx, reach_graph, *,
                            current_date=None, is_anadromous=None):
    """Move a fish to the downstream reach, or make it an outmigrant.

    Parameters
    ----------
    is_anadromous : array-like or None
        Boolean array indexed by species_idx. When True and the fish has no
        downstream reach, the fish transitions to SMOLT and enters the marine
        domain instead of dying.
    """
    outmigrants = []
    current_reach = int(trout_state.reach_idx[fish_idx])
    downstream = reach_graph.get(current_reach, [])
    if len(downstream) > 0:
        trout_state.reach_idx[fish_idx] = downstream[0]
    else:
        # No downstream reach — fish becomes outmigrant
        record = {
            "species_idx": int(trout_state.species_idx[fish_idx]),
            "length": float(trout_state.length[fish_idx]),
            "reach_idx": current_reach,
        }
        if current_date is not None:
            record["date"] = current_date
            record["day_of_year"] = current_date.timetuple().tm_yday
        outmigrants.append(record)

        # Check if anadromous: transition to smolt instead of dying
        sp_idx = int(trout_state.species_idx[fish_idx])
        is_anad = (is_anadromous is not None and sp_idx < len(is_anadromous)
                   and is_anadromous[sp_idx])
        if is_anad:
            trout_state.life_history[fish_idx] = int(LifeStage.SMOLT)
            trout_state.zone_idx[fish_idx] = 0  # estuary
            trout_state.natal_reach_idx[fish_idx] = current_reach
            if current_date is not None:
                trout_state.smolt_date[fish_idx] = current_date.toordinal()
        else:
            trout_state.alive[fish_idx] = False
    return outmigrants


def stochastic_should_migrate(length, L1, L9, life_history, rng):
    """inSALMO-style daily stochastic outmigration probability.

    Instead of comparing migration fitness to habitat fitness (deterministic),
    this draws a random number and compares to the logistic migration
    probability.  Only PARR (life_history == 1) are eligible.
    """
    if life_history != LifeStage.PARR:
        return False
    prob = evaluate_logistic(length, L1, L9)
    return rng.random() < prob


def bin_outmigrant(length, length_classes):
    """Bin an outmigrant by length class. Returns bin index (0-based)."""
    for i, threshold in enumerate(length_classes):
        if length < threshold:
            return i
    return len(length_classes)  # last bin
