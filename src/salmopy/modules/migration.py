"""Migration — reach connectivity, downstream migration, outmigrant tracking."""
from salmopy.modules.behavior import evaluate_logistic
from salmopy.state.life_stage import LifeStage


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
    """Decide if a fish should migrate downstream.

    Both arguments must be on the same [0, 1] probability scale.
    best_habitat_fit should be the per-tick expected fitness of the
    fish's chosen cell/activity (see modules.habitat_fitness and the
    Arc D post-pass in modules.behavior), matching NetLogo InSALMO 7.3
    fitness-for. Passing the fitness_memory EMA here is a scale bug
    (see docs/validation/v0.30.2-netlogo-comparison.md).

    Only anadromous juveniles (PARR) may migrate.
    """
    if life_history != LifeStage.PARR:
        return False
    return migration_fit > best_habitat_fit


def _build_outmigrant_record(trout_state, fish_idx, current_reach,
                             current_date, start_date, reach_names):
    """Assemble a NetLogo InSALMO 7.3 compatible outmigrant record.

    See `instream.io.output.write_outmigrants` for the 10-column schema.
    """
    if current_date is not None and start_date is not None:
        timestep_int = int((current_date - start_date).days)
    else:
        timestep_int = -1
    natal_idx = int(trout_state.natal_reach_idx[fish_idx])
    if reach_names is not None and 0 <= natal_idx < len(reach_names):
        natal_name = reach_names[natal_idx]
    else:
        natal_name = ""
    fish_length = float(trout_state.length[fish_idx])
    length_category = "Juvenile" if fish_length < 12.0 else "Smolt"
    return {
        "species_idx": int(trout_state.species_idx[fish_idx]),
        "timestep": timestep_int,
        "reach_idx": int(current_reach),
        "natal_reach_idx": natal_idx,
        "natal_reach_name": natal_name,
        "age_years": float(trout_state.age[fish_idx]) / 365.25,
        "length_category": length_category,
        "length": fish_length,
        "initial_length": float(trout_state.initial_length[fish_idx]),
        "superind_rep": int(trout_state.superind_rep[fish_idx]),
    }


def migrate_fish_downstream(trout_state, fish_idx, reach_graph,
                            marine_config=None, smolt_readiness_threshold=0.8,
                            smolt_min_length=12.0, current_date=None,
                            barrier_map=None, rng=None,
                            start_date=None, reach_names=None):
    """Move a fish to the downstream reach, or make it an outmigrant.

    When *marine_config* is provided and the fish is a PARR at the river
    mouth (no downstream reach) with sufficient readiness and length, it
    transitions to SMOLT and enters the marine domain instead of dying.

    When *barrier_map* is provided, each downstream step checks for a
    barrier on the edge. Possible outcomes: transmit (pass through),
    deflect (stay in current reach), or die.

    `start_date` and `reach_names` are used to populate the NetLogo-compatible
    outmigrant record (timestep, natal_reach_name). See
    `instream.io.output.write_outmigrants` for the 10-column schema.

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
        target_reach = downstream[0]
        # Barrier check
        if barrier_map is not None and rng is not None:
            from salmopy.modules.barriers import (
                attempt_downstream_passage,
                RESULT_DEFLECT,
                RESULT_MORTALITY,
            )
            result = attempt_downstream_passage(
                barrier_map, current_reach, target_reach, rng
            )
            if result == RESULT_MORTALITY:
                trout_state.alive[fish_idx] = False
                return outmigrants, False
            elif result == RESULT_DEFLECT:
                # Fish stays in current reach
                return outmigrants, False
            # RESULT_TRANSMIT: fall through to normal movement
        trout_state.reach_idx[fish_idx] = target_reach
    else:
        # No downstream reach — fish is at the river mouth.
        life_history = int(trout_state.life_history[fish_idx])
        fish_length = float(trout_state.length[fish_idx])
        readiness = float(trout_state.smolt_readiness[fish_idx])

        # v0.17.0 — KELT re-entering the ocean as OCEAN_ADULT.
        if marine_config is not None and life_history == int(LifeStage.KELT):
            outmigrants.append(_build_outmigrant_record(
                trout_state, fish_idx, current_reach,
                current_date, start_date, reach_names,
            ))
            trout_state.life_history[fish_idx] = int(LifeStage.OCEAN_ADULT)
            trout_state.zone_idx[fish_idx] = 0
            # v0.43.5 Task B1: refresh smolt_date so days_since_ocean_entry
            # starts at 0 for re-entering kelts. Previously the original
            # (years-ago) smolt_date persisted, making days_since_ocean_entry
            # thousands of days — the fish immediately bypassed the
            # estuary-stress zone on the next daily_step.
            trout_state.smolt_date[fish_idx] = (
                current_date.toordinal() if current_date is not None else 0
            )
            trout_state.cell_idx[fish_idx] = -1
            trout_state.reach_idx[fish_idx] = -1
            return outmigrants, False

        if (
            marine_config is not None
            and life_history == int(LifeStage.PARR)
            and readiness >= smolt_readiness_threshold
            and fish_length >= smolt_min_length
        ):
            outmigrants.append(_build_outmigrant_record(
                trout_state, fish_idx, current_reach,
                current_date, start_date, reach_names,
            ))
            trout_state.life_history[fish_idx] = int(LifeStage.SMOLT)
            trout_state.zone_idx[fish_idx] = 0
            # Arc O.1 (2026-04-21): DO NOT overwrite natal_reach_idx at
            # smoltification. Pre-v0.38 this line assigned current_reach,
            # destroying the birth-reach signal needed for Arc K PSPC
            # analytics and Arc O genetic-MSA reconstruction. NetLogo
            # InSALMO 7.3 preserves birth-reach across the full life cycle.
            trout_state.smolt_date[fish_idx] = (
                current_date.toordinal() if current_date is not None else 0
            )
            trout_state.cell_idx[fish_idx] = -1
            trout_state.reach_idx[fish_idx] = -1
            smoltified = True
        elif life_history == int(LifeStage.PARR) and marine_config is not None:
            # v0.24.0 — PARR at the mouth that can't smoltify yet (too
            # small or insufficient readiness). Keep alive at the current
            # reach so it can grow and try again next spring. No outmigrant
            # record — this is a failed attempt, not a real outmigration.
            pass
        else:
            outmigrants.append(_build_outmigrant_record(
                trout_state, fish_idx, current_reach,
                current_date, start_date, reach_names,
            ))
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
