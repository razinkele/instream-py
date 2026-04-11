"""Spawning module — readiness checks, cell selection, redd creation (Tasks 6.1-6.3)."""

import numpy as np


def ready_to_spawn(
    sex,
    age,
    length,
    condition,
    temperature,
    flow,
    spawned_this_season,
    day_of_year,
    spawn_min_age,
    spawn_min_length,
    spawn_min_cond,
    spawn_min_temp,
    spawn_max_temp,
    spawn_prob,
    max_spawn_flow,
    spawn_start_doy,
    spawn_end_doy,
    rng,
    spawn_date_jitter_days=0,
):
    """Check whether a fish is ready to spawn (Task 6.1).

    Parameters
    ----------
    sex : int
        0 = female, 1 = male.
    age : int
        Fish age in years.
    length, condition : float
        Fish length (cm) and condition factor.
    temperature : float
        Current water temperature (C).
    flow : float
        Current flow (m3/s or model units).
    spawned_this_season : bool
        Whether this fish already spawned this season.
    day_of_year : int
        Julian day (1-365).
    spawn_min_age, spawn_min_length, spawn_min_cond : float
        Minimum thresholds; negative values disable the check.
    spawn_min_temp, spawn_max_temp : float
        Temperature window for spawning.
    spawn_prob : float
        Probability of spawning when all other criteria are met.
    max_spawn_flow : float
        Maximum flow at which spawning can occur.
    spawn_start_doy, spawn_end_doy : int
        Day-of-year window for spawning season.
    rng : numpy.random.Generator
        Random number generator.

    Returns
    -------
    bool
    """
    # Only females spawn
    if sex != 0:
        return False

    # Already spawned this season
    if spawned_this_season:
        return False

    # Age check (disabled when negative)
    if spawn_min_age >= 0 and age < spawn_min_age:
        return False

    # Length check (disabled when negative)
    if spawn_min_length >= 0 and length < spawn_min_length:
        return False

    # Condition check (disabled when negative)
    if spawn_min_cond >= 0 and condition < spawn_min_cond:
        return False

    # Temperature window
    if temperature < spawn_min_temp or temperature > spawn_max_temp:
        return False

    # Season window (with optional per-fish jitter)
    eff_start = spawn_start_doy
    eff_end = spawn_end_doy
    if spawn_date_jitter_days > 0:
        jitter = int(rng.integers(-spawn_date_jitter_days, spawn_date_jitter_days + 1))
        eff_start = max(1, eff_start + jitter)
        eff_end = min(365, eff_end + jitter)

    if eff_start <= eff_end:
        if day_of_year < eff_start or day_of_year > eff_end:
            return False
    else:
        # Wraps around year boundary (e.g. Nov-Feb)
        if day_of_year < eff_start and day_of_year > eff_end:
            return False

    # Flow check
    if flow >= max_spawn_flow:
        return False

    # Probabilistic check
    if rng.random() >= spawn_prob:
        return False

    return True


def spawn_suitability(
    depth,
    velocity,
    frac_spawn,
    area,
    depth_table_x,
    depth_table_y,
    vel_table_x,
    vel_table_y,
):
    """Compute spawn suitability score for a cell (Task 6.2).

    Parameters
    ----------
    depth, velocity : float
        Cell hydraulic conditions.
    frac_spawn : float
        Fraction of cell area with spawning gravel (0-1).
    area : float
        Cell area.
    depth_table_x, depth_table_y : array
        Piecewise-linear depth suitability lookup.
    vel_table_x, vel_table_y : array
        Piecewise-linear velocity suitability lookup.

    Returns
    -------
    float
        Suitability score (area-weighted).
    """
    depth_suit = float(np.interp(depth, depth_table_x, depth_table_y))
    vel_suit = float(np.interp(velocity, vel_table_x, vel_table_y))
    return depth_suit * vel_suit * frac_spawn * area


def select_spawn_cell(
    scores,
    candidates,
    redd_cells=None,
    centroids_x=None,
    centroids_y=None,
    defense_area=0.0,
):
    """Select best spawning cell from candidates (Task 6.2).

    Parameters
    ----------
    scores : array
        Suitability scores for each candidate.
    candidates : array
        Cell indices corresponding to scores.
    redd_cells : array or None
        Cell indices of existing alive redds.
    centroids_x, centroids_y : array or None
        Cell centroid coordinates.
    defense_area : float
        Minimum distance (cm) from existing redds. 0 = no exclusion.

    Returns
    -------
    int
        Cell index of the best candidate, or -1 if none available.
    """
    if len(candidates) == 0:
        return -1

    valid_mask = np.ones(len(candidates), dtype=bool)

    if defense_area > 0 and redd_cells is not None and len(redd_cells) > 0:
        for rc in redd_cells:
            dx = centroids_x[candidates] - centroids_x[rc]
            dy = centroids_y[candidates] - centroids_y[rc]
            dist = np.sqrt(dx**2 + dy**2)
            valid_mask &= dist > defense_area

    valid_scores = np.where(valid_mask, scores, -1.0)
    best_idx = np.argmax(valid_scores)
    if valid_scores[best_idx] <= 0:
        return -1
    return int(candidates[best_idx])


def create_redd(
    redd_state,
    species_idx,
    cell_idx,
    reach_idx,
    weight,
    fecund_mult,
    fecund_exp,
    egg_viability,
    fecundity_noise=0.0,
    rng=None,
):
    """Create a new redd in the first available slot (Task 6.3).

    Parameters
    ----------
    redd_state : ReddState
        Redd state arrays (modified in place).
    species_idx, cell_idx, reach_idx : int
        Species, cell, and reach identifiers.
    weight : float
        Spawner weight (g).
    fecund_mult, fecund_exp : float
        Fecundity parameters: eggs = fecund_mult * weight^fecund_exp * egg_viability.
    egg_viability : float
        Fraction of eggs that are viable (0-1).
    fecundity_noise : float
        If > 0, multiply deterministic egg count by exp(N(0, fecundity_noise))
        to introduce lognormal noise. Default 0.0 (deterministic).
    rng : numpy.random.Generator or None
        Random number generator (required when fecundity_noise > 0).

    Returns
    -------
    int
        Slot index of the new redd (>= 0), or -1 if no slot available.
    """
    slot = redd_state.first_dead_slot()
    if slot < 0:
        return -1

    num_eggs = fecund_mult * weight**fecund_exp * egg_viability
    if fecundity_noise > 0.0 and rng is not None:
        num_eggs *= np.exp(rng.normal(0.0, fecundity_noise))
    num_eggs = int(num_eggs)

    redd_state.alive[slot] = True
    redd_state.species_idx[slot] = species_idx
    redd_state.cell_idx[slot] = cell_idx
    redd_state.reach_idx[slot] = reach_idx
    redd_state.num_eggs[slot] = num_eggs
    redd_state.eggs_initial[slot] = num_eggs
    redd_state.frac_developed[slot] = 0.0
    redd_state.emerge_days[slot] = 0

    return slot


def apply_superimposition(redd_state, new_redd_idx, redd_area):
    """Reduce eggs in existing redds on the same cell as the new redd.

    Each existing redd loses a fraction of eggs proportional to
    redd_area / cell_area overlap. Simplified: lose 50% of remaining eggs
    when superimposed.

    Parameters
    ----------
    redd_state : ReddState
        Redd state arrays (modified in place).
    new_redd_idx : int
        Index of the newly created redd.
    redd_area : float
        Area of the redd (currently unused; fixed 50% loss).
    """
    cell = redd_state.cell_idx[new_redd_idx]
    alive_redds = np.where(redd_state.alive)[0]
    for i in alive_redds:
        if i == new_redd_idx:
            continue
        if redd_state.cell_idx[i] == cell:
            # Existing redd loses eggs from disturbance
            lost = redd_state.num_eggs[i] // 2
            redd_state.num_eggs[i] -= lost
            redd_state.eggs_scour[i] += lost


def apply_spawner_weight_loss(weight, wt_loss_fraction):
    """Apply post-spawning weight loss (Task 6.3).

    Parameters
    ----------
    weight : float
        Current weight.
    wt_loss_fraction : float
        Fraction of weight lost (e.g. 0.4 = 40% loss).

    Returns
    -------
    float
        New weight after loss.
    """
    return weight * (1.0 - wt_loss_fraction)


def develop_eggs(frac_developed, temperature, step_length, devel_A, devel_B, devel_C):
    """Advance egg fractional development (Task 6.4).

    Parameters
    ----------
    frac_developed : float
        Current fractional development (0 to 1+).
    temperature : float
        Water temperature (C).
    step_length : float
        Time step length (days, typically 1.0).
    devel_A, devel_B, devel_C : float
        Polynomial coefficients for development rate.

    Returns
    -------
    float
        Updated fractional development.
    """
    increment = (
        devel_A + devel_B * temperature + devel_C * temperature * temperature
    ) * step_length
    increment = max(0.0, increment)
    return frac_developed + increment


def redd_emergence(
    redd_state,
    trout_state,
    rng,
    emerge_length_min,
    emerge_length_mode,
    emerge_length_max,
    weight_A,
    weight_B,
    species_index,
):
    """Hatch eggs from fully-developed redds and create new trout (Task 6.5).

    For each alive redd of the given species with frac_developed >= 1.0,
    all remaining eggs emerge as new trout.  When num_eggs reaches 0 the
    redd is killed.

    Parameters
    ----------
    redd_state : ReddState
        Redd state arrays (modified in place).
    trout_state : TroutState
        Trout state arrays (modified in place — new fish fill dead slots).
    rng : numpy.random.Generator
        Random number generator.
    emerge_length_min, emerge_length_mode, emerge_length_max : float
        Triangular distribution parameters for emerged-fry length (cm).
    weight_A, weight_B : float
        Allometric weight parameters: weight = weight_A * length^weight_B.
    species_index : int
        Species index to match against redd species_idx.
    """
    rs = redd_state
    ts = trout_state

    for i in range(len(rs.alive)):
        if not rs.alive[i]:
            continue
        if rs.species_idx[i] != species_index:
            continue
        if rs.frac_developed[i] < 1.0:
            continue

        # All remaining eggs emerge
        n_emerge = int(rs.num_eggs[i])
        if n_emerge <= 0:
            rs.alive[i] = False
            continue

        # Pre-compute available dead slots for batch allocation
        dead_slots = np.where(~ts.alive)[0]
        n_slots = min(n_emerge, len(dead_slots))
        if n_slots <= 0:
            continue

        slots = dead_slots[:n_slots]
        lengths = rng.triangular(
            emerge_length_min, emerge_length_mode, emerge_length_max, size=n_slots
        )
        weights = weight_A * lengths**weight_B

        ts.alive[slots] = True
        ts.species_idx[slots] = rs.species_idx[i]
        ts.length[slots] = lengths
        ts.weight[slots] = weights
        ts.condition[slots] = 1.0
        ts.age[slots] = 0
        ts.cell_idx[slots] = rs.cell_idx[i]
        ts.reach_idx[slots] = rs.reach_idx[i]
        ts.natal_reach_idx[slots] = rs.reach_idx[i]
        ts.sex[slots] = rng.integers(0, 2, size=n_slots, dtype=np.int32)
        ts.superind_rep[slots] = 1
        from instream.state.life_stage import LifeStage
        ts.life_history[slots] = LifeStage.FRY
        ts.in_shelter[slots] = False
        ts.spawned_this_season[slots] = False
        ts.activity[slots] = 0
        ts.growth_memory[slots, :] = 0.0
        ts.consumption_memory[slots, :] = 0.0
        ts.survival_memory[slots, :] = 0.0
        ts.last_growth_rate[slots] = 0.0
        ts.fitness_memory[slots] = 0.0

        # Reset marine state — slots may have been freed by a previous
        # smolt/adult death, and without this the new fry would inherit
        # smolt_date, zone, sea_winters, and readiness from the corpse
        # (the ghost-smoltified-fry bug, fixed in v0.16.0).
        ts.zone_idx[slots] = -1
        ts.sea_winters[slots] = 0
        ts.smolt_date[slots] = -1
        ts.smolt_readiness[slots] = 0.0
        # Hatchery origin is reset to False — new wild fry emerging from
        # redds are never hatchery-origin (v0.17.0).
        ts.is_hatchery[slots] = False

        rs.num_eggs[i] -= n_slots
        if rs.num_eggs[i] <= 0:
            rs.alive[i] = False


def apply_post_spawn_kelt_survival(
    trout_state,
    kelt_survival_prob: float,
    min_kelt_condition: float,
    rng,
) -> int:
    """Give post-spawn SPAWNER fish a chance to survive the spawning act
    and out-migrate to the ocean as KELT.

    **InSALMON extension — no NetLogo reference.** NetLogo InSALMO 7.3
    has no kelt stage and no iteroparous survival rule; its only
    post-spawn mechanic is the flat ``trout-spawn-wt-loss-fraction = 0.4``.

    **Semantics**: ``kelt_survival_prob`` is the **river-exit survival**
    — the probability that a post-spawn SPAWNER survives the spawning
    act and physically reaches the river mouth as a kelt. It is NOT
    the realized repeat-spawning rate. The realized rate emerges from
    the chain ``kelt_survival_prob × P(ocean recondition) × P(return)``.

    With the default ``kelt_survival_prob = 0.25`` and v0.17.0 calibrated
    marine hazards, the target realized rate is 5–10% (Niemelä et al.
    on Teno, Jutila et al. 2006 Simojoki). The Atlantic-average value
    of ~10–11% (Fleming & Reynolds 2004; Bordeleau et al. 2019) is
    expected for more productive rivers.

    Condition is halved multiplicatively (Jonsson et al. 1997;
    Bordeleau et al. 2019 document 40–70% post-spawn energy depletion)
    with a floor of 0.3 so survivors remain viable.

    Parameters
    ----------
    trout_state : TroutState
        Modified in place: surviving SPAWNERs become KELT; the rest
        keep SPAWNER and are killed by the existing post-spawn death
        block that runs immediately after this function.
    kelt_survival_prob : float
        River-exit survival probability in [0, 1].
    min_kelt_condition : float
        Eligibility floor — depleted spawners below this threshold
        cannot attempt the kelt migration.
    rng : numpy.random.Generator

    Returns
    -------
    int
        Number of SPAWNERs promoted to KELT this call.
    """
    from instream.state.life_stage import LifeStage

    eligible = (
        trout_state.alive
        & (trout_state.life_history == int(LifeStage.SPAWNER))
        & trout_state.spawned_this_season
        & (trout_state.condition >= min_kelt_condition)
    )
    idx = np.where(eligible)[0]
    if len(idx) == 0:
        return 0

    draws = rng.random(len(idx))
    promoted = idx[draws < kelt_survival_prob]
    if len(promoted) == 0:
        return 0

    trout_state.life_history[promoted] = int(LifeStage.KELT)
    trout_state.condition[promoted] = np.maximum(
        trout_state.condition[promoted] * 0.5,
        0.3,
    )
    return int(len(promoted))
