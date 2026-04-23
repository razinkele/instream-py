"""Behavioral decisions — logistic functions, candidate mask, fitness, habitat selection."""

import math
import numpy as np

from salmopy.state.life_stage import LifeStage
# Canonical expected-fitness function — single source of truth for the
# NetLogo InSALMO 7.3 fitness-for formula (see habitat_fitness.py docstring).
# Phase 2 Task 2.9 imports this here so the inline implementations at the
# batch-path and scalar-fallback sites below can be refactored to delegate
# in a follow-up patch without further source changes.
from salmopy.modules.habitat_fitness import expected_fitness  # noqa: F401

try:
    from salmopy.backends.numba_backend.fitness import (
        _evaluate_all_cells as _numba_eval,
        batch_select_habitat as _numba_batch,
    )

    _HAS_NUMBA_FITNESS = True
    _HAS_NUMBA_BATCH = True
except ImportError:
    _HAS_NUMBA_FITNESS = False
    _HAS_NUMBA_BATCH = False

try:
    from salmopy.backends.numba_backend.spatial import (
        build_all_candidates_numba as _numba_build_cands,
        build_candidates_from_cache_numba as _numba_build_cands_cached,
    )

    _HAS_NUMBA_SPATIAL = True
except ImportError:
    _HAS_NUMBA_SPATIAL = False

from salmopy.modules.growth import (
    growth_rate_for,
    max_swim_speed,
    drift_swim_speed,
    drift_intake,
    search_intake,
    cmax_temp_function,
    c_stepmax,
)

# Pre-compute constant used in every logistic call
_LN81 = math.log(81.0)


def evaluate_logistic(x, L1, L9):
    """Evaluate logistic function where f(L1)=0.1 and f(L9)=0.9. Scalar version.

    Uses pure Python math (not numpy) to avoid 0-d array dispatch overhead.
    """
    if L9 == L1:
        return 0.9 if x >= L1 else 0.1
    midpoint = (L1 + L9) * 0.5
    slope = _LN81 / (L9 - L1)
    arg = -slope * (x - midpoint)
    if arg > 500.0:
        arg = 500.0
    elif arg < -500.0:
        arg = -500.0
    return 1.0 / (1.0 + math.exp(arg))


def evaluate_logistic_array(x, L1, L9):
    """Evaluate logistic function on an array."""
    x = np.asarray(x, dtype=np.float64)
    if L9 == L1:
        return np.where(x >= L1, 0.9, 0.1)
    midpoint = (L1 + L9) / 2.0
    slope = np.log(81.0) / (L9 - L1)
    arg = -slope * (x - midpoint)
    arg = np.clip(arg, -500, 500)
    return 1.0 / (1.0 + np.exp(arg))


def movement_radius(length, move_radius_max, move_radius_L1, move_radius_L9):
    """Calculate habitat selection radius (in CRS units, same as centroids).

    Parameters
    ----------
    length : float
        Fish length (cm).
    move_radius_max : float
        Maximum movement radius (CRS units, e.g. cm in NetLogo, meters in projected CRS).
    move_radius_L1 : float
        Fish length at which logistic = 0.1.
    move_radius_L9 : float
        Fish length at which logistic = 0.9.

    Returns
    -------
    float
        Movement radius for this fish.
    """
    fraction = evaluate_logistic(length, L1=move_radius_L1, L9=move_radius_L9)
    return move_radius_max * fraction


def build_candidate_mask(
    trout_state, fem_space, move_radius_max, move_radius_L1, move_radius_L9
):
    """Build boolean mask of candidate cells for each fish.

    Returns shape (N_MAX, num_cells). True = fish can consider that cell.
    Dead fish get all-False row. Dry cells (depth=0) are excluded.

    Parameters
    ----------
    trout_state : TroutState
        All trout state arrays.
    fem_space : FEMSpace
        Spatial container with KD-tree and neighbor info.
    move_radius_max : float
        Maximum movement radius (CRS units).
    move_radius_L1 : float
        Fish length where logistic = 0.1.
    move_radius_L9 : float
        Fish length where logistic = 0.9.

    Returns
    -------
    mask : ndarray, shape (capacity, num_cells), dtype bool
    """
    n_fish = trout_state.alive.shape[0]
    n_cells = fem_space.num_cells
    mask = np.zeros((n_fish, n_cells), dtype=bool)

    wet_mask = fem_space.cell_state.depth > 0

    for i in range(n_fish):
        if not trout_state.alive[i]:
            continue
        current_cell = trout_state.cell_idx[i]
        if current_cell < 0:
            continue
        # Calculate movement radius for this fish
        radius = movement_radius(
            trout_state.length[i], move_radius_max, move_radius_L1, move_radius_L9
        )
        # Get cells within radius via KD-tree
        candidates = fem_space.cells_in_radius(current_cell, radius)
        # Also include direct neighbors (ensures adjacency even if radius is tiny)
        neighbors = fem_space.get_neighbor_indices(current_cell)
        neighbors = neighbors[neighbors >= 0]
        all_candidates = np.unique(np.concatenate([candidates, neighbors]))
        # Apply wet mask
        for c in all_candidates:
            if wet_mask[c]:
                mask[i, c] = True
        # Ensure current cell is included if wet
        if current_cell < n_cells and wet_mask[current_cell]:
            mask[i, current_cell] = True

    return mask


def build_candidate_lists(
    trout_state, fem_space, move_radius_max, move_radius_L1, move_radius_L9,
    reach_allowed=None,
):
    """Build per-fish candidate cell arrays (sparse, no dense mask).

    Returns list of length capacity. Dead fish get None. Alive fish get
    np.ndarray of wet candidate cell indices (int32).

    Uses Numba brute-force distance search when available (faster than
    KD-tree for meshes under ~10k cells). Falls back to KD-tree + Python.
    """
    n_fish = trout_state.alive.shape[0]
    wet_mask = fem_space.cell_state.depth > 0

    if _HAS_NUMBA_SPATIAL and hasattr(fem_space, '_geo_offsets'):
        assert move_radius_max <= fem_space._geo_radius_max, (
            f"move_radius_max={move_radius_max} exceeds cache "
            f"radius {fem_space._geo_radius_max}; rebuild cache."
        )
        offsets, flat = _numba_build_cands_cached(
            trout_state.alive,
            trout_state.cell_idx,
            trout_state.length,
            wet_mask,
            fem_space._geo_offsets,
            fem_space._geo_flat,
            fem_space._geo_dist2,
            fem_space.neighbor_indices,
            move_radius_max,
            move_radius_L1,
            move_radius_L9,
        )
        candidate_lists = [None] * n_fish
        for i in range(n_fish):
            if offsets[i + 1] > offsets[i]:
                candidate_lists[i] = flat[int(offsets[i]) : int(offsets[i + 1])]
    elif _HAS_NUMBA_SPATIAL:
        offsets, flat = _numba_build_cands(
            trout_state.alive,
            trout_state.cell_idx,
            trout_state.length,
            fem_space.cell_state.centroid_x,
            fem_space.cell_state.centroid_y,
            wet_mask,
            fem_space.neighbor_indices,
            move_radius_max,
            move_radius_L1,
            move_radius_L9,
        )
        candidate_lists = [None] * n_fish
        for i in range(n_fish):
            if offsets[i + 1] > offsets[i]:
                candidate_lists[i] = flat[int(offsets[i]) : int(offsets[i + 1])]
    else:
        # Python fallback: KD-tree queries + vectorized wet filter
        candidate_lists = [None] * n_fish
        for i in range(n_fish):
            if not trout_state.alive[i]:
                continue
            current_cell = trout_state.cell_idx[i]
            if current_cell < 0:
                continue
            radius = movement_radius(
                trout_state.length[i], move_radius_max, move_radius_L1, move_radius_L9
            )
            candidates = fem_space.cells_in_radius(current_cell, radius)
            neighbors = fem_space.get_neighbor_indices(current_cell)
            neighbors = neighbors[neighbors >= 0]
            all_c = np.unique(
                np.concatenate([candidates, neighbors, np.array([current_cell])])
            )
            # Vectorized wet filter (replaces Python for-loop)
            candidate_lists[i] = all_c[wet_mask[all_c]].astype(np.int32)

    # Post-filter: restrict to current reach + connected reaches
    if reach_allowed is not None:
        for i in range(n_fish):
            if candidate_lists[i] is None:
                continue
            fish_reach = int(trout_state.reach_idx[i])
            allowed = reach_allowed.get(fish_reach)
            if allowed is None:
                continue
            cell_reaches = fem_space.cell_state.reach_idx[candidate_lists[i]]
            mask = np.isin(cell_reaches, allowed)
            filtered = candidate_lists[i][mask]
            if len(filtered) > 0:
                candidate_lists[i] = filtered
            # else: keep original candidates (don't strand the fish)

    return candidate_lists


def fitness_for(
    activity,
    length,
    weight,
    depth,
    velocity,
    light,
    turbidity,
    temperature,
    drift_conc,
    search_prod,
    search_area,
    available_drift,
    available_search,
    available_shelter,
    shelter_speed_frac,
    superind_rep,
    prev_consumption,
    step_length,
    cmax_A,
    cmax_B,
    cmax_temp_table_x,
    cmax_temp_table_y,
    react_dist_A,
    react_dist_B,
    turbid_threshold,
    turbid_min,
    turbid_exp,
    light_threshold,
    light_min,
    light_exp,
    capture_R1,
    capture_R9,
    max_speed_A,
    max_speed_B,
    max_swim_temp_term,
    resp_A,
    resp_B,
    resp_D,
    resp_temp_term,
    prey_energy_density,
    fish_energy_density,
    # --- Survival parameters (Phase 5) ---
    condition=1.0,
    mort_high_temp_T1=28.0,
    mort_high_temp_T9=24.0,
    mort_condition_S_at_K5=0.8,
    mort_condition_S_at_K8=0.992,
    mort_condition_K_crit=0.8,
    fish_pred_min=0.99,
    fish_pred_L1=10.0,
    fish_pred_L9=3.0,
    fish_pred_D1=50.0,
    fish_pred_D9=10.0,
    fish_pred_P1=0.5,
    fish_pred_P9=0.1,
    fish_pred_I1=200.0,
    fish_pred_I9=50.0,
    fish_pred_T1=25.0,
    fish_pred_T9=15.0,
    fish_pred_hiding_factor=0.5,
    pisciv_density=0.0,
    terr_pred_min=0.99,
    terr_pred_L1=15.0,
    terr_pred_L9=5.0,
    terr_pred_D1=50.0,
    terr_pred_D9=10.0,
    terr_pred_V1=50.0,
    terr_pred_V9=10.0,
    terr_pred_I1=200.0,
    terr_pred_I9=50.0,
    terr_pred_H1=50.0,
    terr_pred_H9=10.0,
    terr_pred_hiding_factor=0.5,
    dist_escape=100.0,
    available_hiding=10,
    mort_strand_survival_when_dry=0.5,
):
    """Compute fitness for a fish at a cell with given activity.

    Phase 5: fitness = growth_rate * step_length * non_starve_survival * condition_survival.
    Survival penalizes cells with high predation risk, extreme temperature, or stranding.
    """
    max_speed_len_term = max_speed_A * length + max_speed_B
    max_speed = max_swim_speed(max_speed_len_term, max_swim_temp_term)

    # Speed check: if velocity exceeds max speed for this activity, fitness = 0
    if activity == "search" and velocity > max_speed:
        return 0.0
    if activity == "drift":
        d_speed = drift_swim_speed(
            velocity, length, available_shelter, shelter_speed_frac
        )
        if d_speed > max_speed:
            return 0.0

    growth = growth_rate_for(
        activity=activity,
        length=length,
        weight=weight,
        depth=depth,
        velocity=velocity,
        light=light,
        turbidity=turbidity,
        temperature=temperature,
        drift_conc=drift_conc,
        search_prod=search_prod,
        search_area=search_area,
        available_drift=available_drift,
        available_search=available_search,
        available_shelter=available_shelter,
        shelter_speed_frac=shelter_speed_frac,
        superind_rep=superind_rep,
        prev_consumption=prev_consumption,
        step_length=step_length,
        cmax_A=cmax_A,
        cmax_B=cmax_B,
        cmax_temp_table_x=cmax_temp_table_x,
        cmax_temp_table_y=cmax_temp_table_y,
        react_dist_A=react_dist_A,
        react_dist_B=react_dist_B,
        turbid_threshold=turbid_threshold,
        turbid_min=turbid_min,
        turbid_exp=turbid_exp,
        light_threshold=light_threshold,
        light_min=light_min,
        light_exp=light_exp,
        capture_R1=capture_R1,
        capture_R9=capture_R9,
        max_speed_A=max_speed_A,
        max_speed_B=max_speed_B,
        max_swim_temp_term=max_swim_temp_term,
        resp_A=resp_A,
        resp_B=resp_B,
        resp_D=resp_D,
        resp_temp_term=resp_temp_term,
        prey_energy_density=prey_energy_density,
        fish_energy_density=fish_energy_density,
    )

    # Phase 5: full fitness = growth * survival
    from salmopy.modules.survival import (
        survival_high_temperature as _ff_surv_ht,
        survival_stranding as _ff_surv_str,
        survival_condition as surv_cond_fn,
        survival_fish_predation as _ff_surv_fp,
        survival_terrestrial_predation as _ff_surv_tp,
    )

    s_ht = _ff_surv_ht(temperature, mort_high_temp_T1, mort_high_temp_T9)
    s_str = _ff_surv_str(depth, mort_strand_survival_when_dry)
    s_cond = surv_cond_fn(condition, mort_condition_S_at_K5, mort_condition_S_at_K8, mort_condition_K_crit)
    s_fp = _ff_surv_fp(
        length,
        depth,
        light,
        pisciv_density,
        temperature,
        activity,
        fish_pred_min,
        fish_pred_L1,
        fish_pred_L9,
        fish_pred_D1,
        fish_pred_D9,
        fish_pred_P1,
        fish_pred_P9,
        fish_pred_I1,
        fish_pred_I9,
        fish_pred_T1,
        fish_pred_T9,
        fish_pred_hiding_factor,
    )
    s_tp = _ff_surv_tp(
        length,
        depth,
        velocity,
        light,
        dist_escape,
        activity,
        available_hiding,
        superind_rep,
        terr_pred_min,
        terr_pred_L1,
        terr_pred_L9,
        terr_pred_D1,
        terr_pred_D9,
        terr_pred_V1,
        terr_pred_V9,
        terr_pred_I1,
        terr_pred_I9,
        terr_pred_H1,
        terr_pred_H9,
        terr_pred_hiding_factor,
    )
    non_starve = s_ht * s_str * s_fp * s_tp
    return growth * step_length * non_starve * s_cond


def deplete_resources(
    fish_order,
    chosen_cells,
    chosen_activities,
    intake_amounts,
    fish_lengths,
    superind_reps,
    available_drift,
    available_search,
    available_shelter,
    available_hiding,
):
    """Sequential resource depletion (order-dependent). Modifies arrays in place."""
    for idx in fish_order:
        cell = chosen_cells[idx]
        act = chosen_activities[idx]
        rep = superind_reps[idx]
        length = fish_lengths[idx]

        if act == 0:  # drift
            consumed = min(intake_amounts[idx] * rep, available_drift[cell])
            available_drift[cell] -= consumed
            # Also deplete velocity shelter
            shelter_needed = length**2 * rep
            if available_shelter[cell] >= shelter_needed:
                available_shelter[cell] -= shelter_needed
        elif act == 1:  # search
            consumed = min(intake_amounts[idx] * rep, available_search[cell])
            available_search[cell] -= consumed
        elif act == 2:  # hide
            if available_hiding[cell] >= rep:
                available_hiding[cell] -= rep


def select_habitat_and_activity(trout_state, fem_space, **params):
    """Main habitat selection: for each fish, pick best cell x activity.

    Phase 5: fitness includes survival weighting via fitness_for().

    Performance-optimized: pre-extracts params to locals, pre-computes
    step-level and per-fish invariants, inlines fitness/growth/survival
    computation to eliminate function-call and dict-lookup overhead.

    Now supports per-fish species/reach dispatch via sp_arrays, rp_arrays,
    and per-reach temperature/turbidity arrays.
    """
    # Lazy import to avoid circular dependency (survival imports evaluate_logistic)
    from salmopy.modules.survival import (  # noqa: E402
        survival_high_temperature as _surv_ht,
        survival_stranding as _surv_str,
        survival_condition as _surv_cond,
    )

    # --- Extract per-species / per-reach arrays ---
    _sp = params.get("sp_arrays", None)
    _rp = params.get("rp_arrays", None)
    _sp_cmax_table_x = params.get("sp_cmax_table_x", None)
    _sp_cmax_table_y = params.get("sp_cmax_table_y", None)

    # Temperature/turbidity: accept arrays (per-reach) or scalars (backward compat)
    _raw_temp = params["temperature"]
    _raw_turb = params["turbidity"]
    _raw_mstt = params["max_swim_temp_term"]
    _raw_rtt = params["resp_temp_term"]
    _temperature_arr = np.atleast_1d(np.asarray(_raw_temp, dtype=np.float64))
    _turbidity_arr = np.atleast_1d(np.asarray(_raw_turb, dtype=np.float64))
    _max_swim_tt_arr = np.atleast_2d(np.asarray(_raw_mstt, dtype=np.float64))
    _resp_tt_arr = np.atleast_2d(np.asarray(_raw_rtt, dtype=np.float64))

    _reach_allowed = params.get("reach_allowed", None)

    # Build candidate lists using per-species max movement radius (use global max)
    if _sp is not None:
        _move_max = float(np.max(_sp["move_radius_max"]))
        _move_L1 = float(_sp["move_radius_L1"][0])
        _move_L9 = float(_sp["move_radius_L9"][0])
        # For multi-species, use most permissive radius for candidate building
        # (the fitness evaluation will still be per-fish correct)
        for si in range(len(_sp["move_radius_max"])):
            if _sp["move_radius_max"][si] > _move_max:
                _move_max = float(_sp["move_radius_max"][si])
    else:
        _move_max = params.get("move_radius_max", 0.0)
        _move_L1 = params.get("move_radius_L1", 0.0)
        _move_L9 = params.get("move_radius_L9", 0.0)

    candidate_lists = build_candidate_lists(
        trout_state,
        fem_space,
        _move_max,
        _move_L1,
        _move_L9,
        reach_allowed=_reach_allowed,
    )

    cs = fem_space.cell_state
    alive = trout_state.alive_indices()

    # v0.26.0 — pre-filter to freshwater fish only. Marine fish (zone_idx
    # >= 0) skip the inner loop anyway (line ~583), but without pre-filtering
    # they still occupy ~60% of alive_sorted and waste iteration time.
    _zone_idx = getattr(trout_state, 'zone_idx', None)
    if _zone_idx is not None:
        fw_mask = _zone_idx[alive] < 0
        alive = alive[fw_mask]

    # Sort by length descending (large fish first, as in NetLogo)
    alive_sorted = alive[np.argsort(-trout_state.length[alive])]

    best_cells = np.full(trout_state.alive.shape[0], -1, dtype=np.int32)
    best_activities = np.zeros(trout_state.alive.shape[0], dtype=np.int32)
    intake_amounts = np.zeros(trout_state.alive.shape[0], dtype=np.float64)

    activities = ["drift", "search", "hide"]

    # === PRE-EXTRACT species param arrays to locals ===
    _step_length = params["step_length"]
    _pisciv_densities = params.get("pisciv_densities", None)

    if _sp is not None:
        _spa_cmax_A = _sp["cmax_A"]
        _spa_cmax_B = _sp["cmax_B"]
        _spa_react_dist_A = _sp["react_dist_A"]
        _spa_react_dist_B = _sp["react_dist_B"]
        _spa_turbid_threshold = _sp["turbid_threshold"]
        _spa_turbid_min = _sp["turbid_min"]
        _spa_turbid_exp = _sp["turbid_exp"]
        _spa_light_threshold = _sp["light_threshold"]
        _spa_light_min = _sp["light_min"]
        _spa_light_exp = _sp["light_exp"]
        _spa_capture_R1 = _sp["capture_R1"]
        _spa_capture_R9 = _sp["capture_R9"]
        _spa_max_speed_A = _sp["max_speed_A"]
        _spa_max_speed_B = _sp["max_speed_B"]
        _spa_resp_A = _sp["resp_A"]
        _spa_resp_B = _sp["resp_B"]
        _spa_resp_D = _sp["resp_D"]
        _spa_search_area = _sp["search_area"]
        _spa_energy_density = _sp["energy_density"]
        _spa_mort_ht_T1 = _sp["mort_high_temp_T1"]
        _spa_mort_ht_T9 = _sp["mort_high_temp_T9"]
        _spa_mort_cond_S5 = _sp["mort_condition_S_at_K5"]
        _spa_mort_cond_S8 = _sp["mort_condition_S_at_K8"]
        _spa_mort_cond_Kcrit = _sp["mort_condition_K_crit"]
        _spa_mort_strand_dry = _sp["mort_strand_survival_when_dry"]
        _spa_fp_L1 = _sp["mort_fish_pred_L1"]
        _spa_fp_L9 = _sp["mort_fish_pred_L9"]
        _spa_fp_D1 = _sp["mort_fish_pred_D1"]
        _spa_fp_D9 = _sp["mort_fish_pred_D9"]
        _spa_fp_P1 = _sp["mort_fish_pred_P1"]
        _spa_fp_P9 = _sp["mort_fish_pred_P9"]
        _spa_fp_I1 = _sp["mort_fish_pred_I1"]
        _spa_fp_I9 = _sp["mort_fish_pred_I9"]
        _spa_fp_T1 = _sp["mort_fish_pred_T1"]
        _spa_fp_T9 = _sp["mort_fish_pred_T9"]
        _spa_fp_hiding_factor = _sp["mort_fish_pred_hiding_factor"]
        _spa_tp_L1 = _sp["mort_terr_pred_L1"]
        _spa_tp_L9 = _sp["mort_terr_pred_L9"]
        _spa_tp_D1 = _sp["mort_terr_pred_D1"]
        _spa_tp_D9 = _sp["mort_terr_pred_D9"]
        _spa_tp_V1 = _sp["mort_terr_pred_V1"]
        _spa_tp_V9 = _sp["mort_terr_pred_V9"]
        _spa_tp_I1 = _sp["mort_terr_pred_I1"]
        _spa_tp_I9 = _sp["mort_terr_pred_I9"]
        _spa_tp_H1 = _sp["mort_terr_pred_H1"]
        _spa_tp_H9 = _sp["mort_terr_pred_H9"]
        _spa_tp_hiding_factor = _sp["mort_terr_pred_hiding_factor"]

    if _rp is not None:
        _rpa_drift_conc = _rp["drift_conc"]
        _rpa_search_prod = _rp["search_prod"]
        _rpa_shelter_speed_frac = _rp["shelter_speed_frac"]
        _rpa_prey_energy_density = _rp["prey_energy_density"]
        _rpa_fish_pred_min = _rp["fish_pred_min"]
        _rpa_terr_pred_min = _rp["terr_pred_min"]

    # Cell arrays to locals
    _c_depth = cs.depth
    _c_vel = cs.velocity
    _c_light = cs.light
    _c_adrift = cs.available_drift
    _c_asearch = cs.available_search
    _c_ashelter = cs.available_vel_shelter
    _c_ahiding = cs.available_hiding_places
    _c_dist_esc = cs.dist_escape

    # === PRE-PASS: handle stranded and RA/KELT fish ===
    # These are small populations; keep them in Python.
    _RA_VAL = int(LifeStage.RETURNING_ADULT)
    _KELT_VAL = int(LifeStage.KELT)
    normal_fish = []  # indices into alive_sorted for batch processing

    for i in alive_sorted:
        candidates = candidate_lists[i]
        if candidates is None or len(candidates) == 0:
            cur = trout_state.cell_idx[i]
            if cur < 0 or cur >= fem_space.num_cells:
                cur = 0
            best_cells[i] = cur
            best_activities[i] = 2
            trout_state.cell_idx[i] = cur
            trout_state.activity[i] = 2
            continue

        _lh_i = int(trout_state.life_history[i])
        if _lh_i == _RA_VAL or _lh_i == _KELT_VAL:
            hold_cell = candidates[int(np.argmin(cs.velocity[candidates]))]
            best_cells[i] = hold_cell
            best_activities[i] = 4
            trout_state.cell_idx[i] = hold_cell
            trout_state.activity[i] = 4
            trout_state.reach_idx[i] = cs.reach_idx[hold_cell]
            _fish_species_h = int(trout_state.species_idx[i])
            _fish_reach_h = int(trout_state.reach_idx[i])
            _fr_h = min(_fish_reach_h, len(_temperature_arr) - 1)
            _fs_h = (
                min(_fish_species_h, _max_swim_tt_arr.shape[1] - 1)
                if _max_swim_tt_arr.ndim >= 2
                else 0
            )
            _fr_r_h = min(_fish_reach_h, _max_swim_tt_arr.shape[0] - 1)
            _resp_temp_term_h = float(_resp_tt_arr[_fr_r_h, _fs_h])
            if _sp is not None:
                _resp_A_h = float(_sp["resp_A"][_fish_species_h])
                _resp_B_h = float(_sp["resp_B"][_fish_species_h])
                _fed_h = float(_sp["energy_density"][_fish_species_h])
            else:
                _resp_A_h = params["resp_A"]
                _resp_B_h = params["resp_B"]
                _fed_h = params["fish_energy_density"]
            _fw_h = float(trout_state.weight[i])
            resp_std_h = _resp_A_h * _fw_h ** _resp_B_h
            resp_h = resp_std_h * _resp_temp_term_h
            trout_state.last_growth_rate[i] = -resp_h / _fed_h
            continue

        normal_fish.append(i)

    # === BATCH PATH: process normal fish in one Numba call ===
    if len(normal_fish) > 0 and _HAS_NUMBA_BATCH:
        normal_idx = np.array(normal_fish, dtype=np.int64)
        n_batch = len(normal_idx)

        # --- Build CSR candidate lists ---
        cand_flat_parts = []
        offsets = np.empty(n_batch + 1, dtype=np.int64)
        offsets[0] = 0
        for fi_local in range(n_batch):
            i = normal_idx[fi_local]
            cands = candidate_lists[i]
            if cands.dtype != np.int32:
                cands = cands.astype(np.int32)
            cand_flat_parts.append(cands)
            offsets[fi_local + 1] = offsets[fi_local] + len(cands)
        cand_flat = np.concatenate(cand_flat_parts) if cand_flat_parts else np.empty(0, dtype=np.int32)

        # --- Pack per-fish arrays via fancy indexing ---
        _f_lengths = trout_state.length[normal_idx].astype(np.float64)
        _f_weights = trout_state.weight[normal_idx].astype(np.float64)
        _f_conditions = trout_state.condition[normal_idx].astype(np.float64)
        _f_reps = trout_state.superind_rep[normal_idx].astype(np.int64)
        _f_prev_cons = trout_state.consumption_memory[normal_idx].sum(axis=1).astype(np.float64)

        _f_species = trout_state.species_idx[normal_idx].astype(np.int64)
        _f_reach = trout_state.reach_idx[normal_idx].astype(np.int64)

        # Clamp indices
        _f_fr = np.minimum(_f_reach, len(_temperature_arr) - 1)
        if _max_swim_tt_arr.ndim >= 2:
            _f_fs = np.minimum(_f_species, _max_swim_tt_arr.shape[1] - 1)
        else:
            _f_fs = np.zeros(n_batch, dtype=np.int64)
        _f_fr_r = np.minimum(_f_reach, _max_swim_tt_arr.shape[0] - 1)

        # Per-fish reach-dependent scalars
        _pf_temperature = _temperature_arr[_f_fr]
        _pf_turbidity = _turbidity_arr[_f_fr]
        _pf_max_swim_tt = _max_swim_tt_arr[_f_fr_r, _f_fs]
        _pf_resp_tt = _resp_tt_arr[_f_fr_r, _f_fs]

        # Per-fish species params
        if _sp is not None:
            _pf_cmax_A = _spa_cmax_A[_f_species]
            _pf_cmax_B = _spa_cmax_B[_f_species]
            _pf_react_dist_A = _spa_react_dist_A[_f_species]
            _pf_react_dist_B = _spa_react_dist_B[_f_species]
            _pf_turbid_threshold = _spa_turbid_threshold[_f_species]
            _pf_turbid_min = _spa_turbid_min[_f_species]
            _pf_turbid_exp = _spa_turbid_exp[_f_species]
            _pf_light_threshold = _spa_light_threshold[_f_species]
            _pf_light_min = _spa_light_min[_f_species]
            _pf_light_exp = _spa_light_exp[_f_species]
            _pf_capture_R1 = _spa_capture_R1[_f_species]
            _pf_capture_R9 = _spa_capture_R9[_f_species]
            _pf_max_speed_A = _spa_max_speed_A[_f_species]
            _pf_max_speed_B = _spa_max_speed_B[_f_species]
            _pf_resp_A = _spa_resp_A[_f_species]
            _pf_resp_B = _spa_resp_B[_f_species]
            _pf_resp_D = _spa_resp_D[_f_species]
            _pf_search_area = _spa_search_area[_f_species]
            _pf_fish_ED = _spa_energy_density[_f_species]
            _pf_mort_ht_T1 = _spa_mort_ht_T1[_f_species]
            _pf_mort_ht_T9 = _spa_mort_ht_T9[_f_species]
            _pf_mort_cond_S5 = _spa_mort_cond_S5[_f_species]
            _pf_mort_cond_S8 = _spa_mort_cond_S8[_f_species]
            _pf_mort_cond_Kcrit = _spa_mort_cond_Kcrit[_f_species]
            _pf_strand_surv = _spa_mort_strand_dry[_f_species]
            _pf_fp_L1 = _spa_fp_L1[_f_species]
            _pf_fp_L9 = _spa_fp_L9[_f_species]
            _pf_fp_D1 = _spa_fp_D1[_f_species]
            _pf_fp_D9 = _spa_fp_D9[_f_species]
            _pf_fp_P1 = _spa_fp_P1[_f_species]
            _pf_fp_P9 = _spa_fp_P9[_f_species]
            _pf_fp_I1 = _spa_fp_I1[_f_species]
            _pf_fp_I9 = _spa_fp_I9[_f_species]
            _pf_fp_T1 = _spa_fp_T1[_f_species]
            _pf_fp_T9 = _spa_fp_T9[_f_species]
            _pf_fp_hf = _spa_fp_hiding_factor[_f_species]
            _pf_tp_L1 = _spa_tp_L1[_f_species]
            _pf_tp_L9 = _spa_tp_L9[_f_species]
            _pf_tp_D1 = _spa_tp_D1[_f_species]
            _pf_tp_D9 = _spa_tp_D9[_f_species]
            _pf_tp_V1 = _spa_tp_V1[_f_species]
            _pf_tp_V9 = _spa_tp_V9[_f_species]
            _pf_tp_I1 = _spa_tp_I1[_f_species]
            _pf_tp_I9 = _spa_tp_I9[_f_species]
            _pf_tp_H1 = _spa_tp_H1[_f_species]
            _pf_tp_H9 = _spa_tp_H9[_f_species]
            _pf_tp_hf = _spa_tp_hiding_factor[_f_species]
            # Pre-compute cmax_temp per fish — vectorized per species group
            _pf_cmax_temp = np.empty(n_batch, dtype=np.float64)
            for si in range(len(_sp_cmax_table_x)):
                mask = _f_species == si
                if not np.any(mask):
                    continue
                tx = np.asarray(_sp_cmax_table_x[si], dtype=np.float64)
                ty = np.asarray(_sp_cmax_table_y[si], dtype=np.float64)
                _pf_cmax_temp[mask] = np.interp(_pf_temperature[mask], tx, ty)
        else:
            # Backward compat: broadcast scalar params to per-fish arrays
            _pf_cmax_A = np.full(n_batch, params["cmax_A"])
            _pf_cmax_B = np.full(n_batch, params["cmax_B"])
            _pf_react_dist_A = np.full(n_batch, params["react_dist_A"])
            _pf_react_dist_B = np.full(n_batch, params["react_dist_B"])
            _pf_turbid_threshold = np.full(n_batch, params["turbid_threshold"])
            _pf_turbid_min = np.full(n_batch, params["turbid_min"])
            _pf_turbid_exp = np.full(n_batch, params["turbid_exp"])
            _pf_light_threshold = np.full(n_batch, params["light_threshold"])
            _pf_light_min = np.full(n_batch, params["light_min"])
            _pf_light_exp = np.full(n_batch, params["light_exp"])
            _pf_capture_R1 = np.full(n_batch, params["capture_R1"])
            _pf_capture_R9 = np.full(n_batch, params["capture_R9"])
            _pf_max_speed_A = np.full(n_batch, params["max_speed_A"])
            _pf_max_speed_B = np.full(n_batch, params["max_speed_B"])
            _pf_resp_A = np.full(n_batch, params["resp_A"])
            _pf_resp_B = np.full(n_batch, params["resp_B"])
            _pf_resp_D = np.full(n_batch, params["resp_D"])
            _pf_search_area = np.full(n_batch, params["search_area"])
            _pf_fish_ED = np.full(n_batch, params["fish_energy_density"])
            _pf_mort_ht_T1 = np.full(n_batch, params.get("mort_high_temp_T1", 28.0))
            _pf_mort_ht_T9 = np.full(n_batch, params.get("mort_high_temp_T9", 24.0))
            _pf_mort_cond_S5 = np.full(n_batch, params.get("mort_condition_S_at_K5", 0.8))
            _pf_mort_cond_S8 = np.full(n_batch, params.get("mort_condition_S_at_K8", 0.992))
            _pf_mort_cond_Kcrit = np.full(n_batch, params.get("mort_condition_K_crit", 0.8))
            _pf_strand_surv = np.full(n_batch, params.get("mort_strand_survival_when_dry", 0.5))
            _pf_fp_L1 = np.full(n_batch, params.get("fish_pred_L1", 10.0))
            _pf_fp_L9 = np.full(n_batch, params.get("fish_pred_L9", 3.0))
            _pf_fp_D1 = np.full(n_batch, params.get("fish_pred_D1", 50.0))
            _pf_fp_D9 = np.full(n_batch, params.get("fish_pred_D9", 10.0))
            _pf_fp_P1 = np.full(n_batch, params.get("fish_pred_P1", 0.5))
            _pf_fp_P9 = np.full(n_batch, params.get("fish_pred_P9", 0.1))
            _pf_fp_I1 = np.full(n_batch, params.get("fish_pred_I1", 200.0))
            _pf_fp_I9 = np.full(n_batch, params.get("fish_pred_I9", 50.0))
            _pf_fp_T1 = np.full(n_batch, params.get("fish_pred_T1", 25.0))
            _pf_fp_T9 = np.full(n_batch, params.get("fish_pred_T9", 15.0))
            _pf_fp_hf = np.full(n_batch, params.get("fish_pred_hiding_factor", 0.5))
            _pf_tp_L1 = np.full(n_batch, params.get("terr_pred_L1", 15.0))
            _pf_tp_L9 = np.full(n_batch, params.get("terr_pred_L9", 5.0))
            _pf_tp_D1 = np.full(n_batch, params.get("terr_pred_D1", 50.0))
            _pf_tp_D9 = np.full(n_batch, params.get("terr_pred_D9", 10.0))
            _pf_tp_V1 = np.full(n_batch, params.get("terr_pred_V1", 50.0))
            _pf_tp_V9 = np.full(n_batch, params.get("terr_pred_V9", 10.0))
            _pf_tp_I1 = np.full(n_batch, params.get("terr_pred_I1", 200.0))
            _pf_tp_I9 = np.full(n_batch, params.get("terr_pred_I9", 50.0))
            _pf_tp_H1 = np.full(n_batch, params.get("terr_pred_H1", 50.0))
            _pf_tp_H9 = np.full(n_batch, params.get("terr_pred_H9", 10.0))
            _pf_tp_hf = np.full(n_batch, params.get("terr_pred_hiding_factor", 0.5))
            _ct_x = np.asarray(params["cmax_temp_table_x"], dtype=np.float64)
            _ct_y = np.asarray(params["cmax_temp_table_y"], dtype=np.float64)
            _pf_cmax_temp = np.interp(_pf_temperature, _ct_x, _ct_y)

        # Per-fish reach params
        if _rp is not None:
            _f_reach_clamped = np.minimum(_f_reach, np.int64(len(_rpa_drift_conc) - 1))
            _pf_drift_conc = _rpa_drift_conc[_f_reach_clamped].astype(np.float64)
            _pf_search_prod = _rpa_search_prod[_f_reach_clamped].astype(np.float64)
            _pf_shelter_speed_frac = _rpa_shelter_speed_frac[_f_reach_clamped].astype(np.float64)
            _pf_prey_ED = _rpa_prey_energy_density[_f_reach_clamped].astype(np.float64)
            _pf_fp_min = _rpa_fish_pred_min[_f_reach_clamped].astype(np.float64)
            _pf_tp_min = _rpa_terr_pred_min[_f_reach_clamped].astype(np.float64)
        else:
            _pf_drift_conc = np.full(n_batch, params["drift_conc"])
            _pf_search_prod = np.full(n_batch, params["search_prod"])
            _pf_shelter_speed_frac = np.full(n_batch, params["shelter_speed_frac"])
            _pf_prey_ED = np.full(n_batch, params["prey_energy_density"])
            _pf_fp_min = np.full(n_batch, params.get("fish_pred_min", 0.99))
            _pf_tp_min = np.full(n_batch, params.get("terr_pred_min", 0.99))

        # Cell arrays — ensure correct dtype for Numba
        _hiding_arr = _c_ahiding.astype(np.float64) if _c_ahiding.dtype != np.float64 else _c_ahiding
        _pisciv_safe = _pisciv_densities if _pisciv_densities is not None else np.zeros_like(_c_depth)

        # --- Call batch Numba function ---
        b_cells, b_acts, b_growths, b_shelter, b_non_starves = _numba_batch(
            _f_lengths,
            _f_weights,
            _f_conditions,
            _f_prev_cons,
            _f_reps,
            offsets,
            cand_flat,
            _c_depth,
            _c_vel,
            _c_light,
            _c_dist_esc,
            _c_adrift,
            _c_asearch,
            _c_ashelter,
            _hiding_arr,
            _pisciv_safe,
            _pf_turbidity,
            _pf_temperature,
            _pf_drift_conc,
            _pf_search_prod,
            _pf_search_area,
            _pf_shelter_speed_frac,
            _pf_cmax_A,
            _pf_cmax_B,
            _pf_cmax_temp,
            _pf_react_dist_A,
            _pf_react_dist_B,
            _pf_turbid_threshold,
            _pf_turbid_min,
            _pf_turbid_exp,
            _pf_light_threshold,
            _pf_light_min,
            _pf_light_exp,
            _pf_capture_R1,
            _pf_capture_R9,
            _pf_max_speed_A,
            _pf_max_speed_B,
            _pf_max_swim_tt,
            _pf_resp_A,
            _pf_resp_B,
            _pf_resp_D,
            _pf_resp_tt,
            _pf_prey_ED,
            _pf_fish_ED,
            _pf_mort_ht_T1,
            _pf_mort_ht_T9,
            _pf_mort_cond_S5,
            _pf_mort_cond_S8,
            _pf_mort_cond_Kcrit,
            _pf_fp_min,
            _pf_fp_L1,
            _pf_fp_L9,
            _pf_fp_D1,
            _pf_fp_D9,
            _pf_fp_P1,
            _pf_fp_P9,
            _pf_fp_I1,
            _pf_fp_I9,
            _pf_fp_T1,
            _pf_fp_T9,
            _pf_fp_hf,
            _pf_tp_min,
            _pf_tp_L1,
            _pf_tp_L9,
            _pf_tp_D1,
            _pf_tp_D9,
            _pf_tp_V1,
            _pf_tp_V9,
            _pf_tp_I1,
            _pf_tp_I9,
            _pf_tp_H1,
            _pf_tp_H9,
            _pf_tp_hf,
            _pf_strand_surv,
            float(_step_length),
        )

        # --- Unpack batch results back to trout_state ---
        # Arc D: compute per-tick best_habitat_fitness via NetLogo fitness-for
        #   f = (daily_survival * mean_starv_survival)^horizon * length penalty
        # Vectorized gather over the batch — faster than per-fish.
        _sp_fit_horizon = _sp.get("fitness_horizon") if _sp is not None else None
        _sp_fit_length = _sp.get("fitness_length") if _sp is not None else None
        for fi_local in range(n_batch):
            i = normal_idx[fi_local]
            bc = int(b_cells[fi_local])
            ba = int(b_acts[fi_local])
            best_cells[i] = bc
            best_activities[i] = ba
            trout_state.cell_idx[i] = bc
            trout_state.activity[i] = ba
            trout_state.reach_idx[i] = cs.reach_idx[bc]
            trout_state.last_growth_rate[i] = b_growths[fi_local]
            if b_shelter[fi_local]:
                trout_state.in_shelter[i] = True

            # Arc D: expected_fitness port of NetLogo InSALMO 7.3
            # fitness-for (nlogo:2798-2840). daily_survival is the
            # non_starve*s_cond product at the chosen cell; we use
            # mean_starv_survival=1.0 as a per-tick proxy (condition
            # survival is already folded into non_starve). The length
            # penalty applies when expected-length-at-horizon falls
            # below species fitness_length.
            ds = float(b_non_starves[fi_local])
            if _sp_fit_horizon is not None:
                sp_i = int(trout_state.species_idx[i])
                horizon = float(_sp_fit_horizon[sp_i])
                fit_len = float(_sp_fit_length[sp_i])
            else:
                horizon = 60.0
                fit_len = 15.0
            if horizon <= 0.0:
                base = 0.0
            else:
                # Clamp to avoid negative-base pow issues
                ds_c = max(0.0, min(1.0, ds))
                base = ds_c ** horizon
                if fit_len > 0.0:
                    L_now = float(trout_state.length[i])
                    if L_now < fit_len:
                        L_at_h = L_now + float(b_growths[fi_local]) * horizon
                        if L_at_h < fit_len:
                            base *= max(0.0, L_at_h) / fit_len
            if hasattr(trout_state, "best_habitat_fitness"):
                trout_state.best_habitat_fitness[i] = max(0.0, min(1.0, base))

    elif len(normal_fish) > 0:
        # === FALLBACK: per-fish Python/Numba scalar path ===
        for i in normal_fish:
            candidates = candidate_lists[i]

            best_fitness = -np.inf
            best_c = candidates[0]
            best_a = 2
            best_growth = 0.0
            best_non_starve = 0.0  # Arc D: survival product at chosen cell

            prev_cons = float(np.sum(trout_state.consumption_memory[i]))

            _fish_reach = int(trout_state.reach_idx[i])
            _fish_species = int(trout_state.species_idx[i])

            _fr = min(_fish_reach, len(_temperature_arr) - 1)
            _fs = (
                min(_fish_species, _max_swim_tt_arr.shape[1] - 1)
                if _max_swim_tt_arr.ndim >= 2
                else 0
            )
            _fr_r = min(_fish_reach, _max_swim_tt_arr.shape[0] - 1)

            _temperature = float(_temperature_arr[_fr])
            _turbidity = float(_turbidity_arr[_fr])
            _max_swim_temp_term = float(_max_swim_tt_arr[_fr_r, _fs])
            _resp_temp_term = float(_resp_tt_arr[_fr_r, _fs])

            if _sp is not None:
                _cmax_A = float(_spa_cmax_A[_fish_species])
                _cmax_B = float(_spa_cmax_B[_fish_species])
                _react_dist_A = float(_spa_react_dist_A[_fish_species])
                _react_dist_B = float(_spa_react_dist_B[_fish_species])
                _turbid_threshold = float(_spa_turbid_threshold[_fish_species])
                _turbid_min = float(_spa_turbid_min[_fish_species])
                _turbid_exp = float(_spa_turbid_exp[_fish_species])
                _light_threshold = float(_spa_light_threshold[_fish_species])
                _light_min = float(_spa_light_min[_fish_species])
                _light_exp = float(_spa_light_exp[_fish_species])
                _capture_R1 = float(_spa_capture_R1[_fish_species])
                _capture_R9 = float(_spa_capture_R9[_fish_species])
                _max_speed_A = float(_spa_max_speed_A[_fish_species])
                _max_speed_B = float(_spa_max_speed_B[_fish_species])
                _resp_A = float(_spa_resp_A[_fish_species])
                _resp_B = float(_spa_resp_B[_fish_species])
                _resp_D = float(_spa_resp_D[_fish_species])
                _search_area = float(_spa_search_area[_fish_species])
                _fish_energy_density = float(_spa_energy_density[_fish_species])
                _mort_ht_T1 = float(_spa_mort_ht_T1[_fish_species])
                _mort_ht_T9 = float(_spa_mort_ht_T9[_fish_species])
                _mort_cond_S5 = float(_spa_mort_cond_S5[_fish_species])
                _mort_cond_S8 = float(_spa_mort_cond_S8[_fish_species])
                _mort_cond_Kcrit = float(_spa_mort_cond_Kcrit[_fish_species])
                _mort_strand_dry = float(_spa_mort_strand_dry[_fish_species])
                _fp_L1 = float(_spa_fp_L1[_fish_species])
                _fp_L9 = float(_spa_fp_L9[_fish_species])
                _fp_D1 = float(_spa_fp_D1[_fish_species])
                _fp_D9 = float(_spa_fp_D9[_fish_species])
                _fp_P1 = float(_spa_fp_P1[_fish_species])
                _fp_P9 = float(_spa_fp_P9[_fish_species])
                _fp_I1 = float(_spa_fp_I1[_fish_species])
                _fp_I9 = float(_spa_fp_I9[_fish_species])
                _fp_T1 = float(_spa_fp_T1[_fish_species])
                _fp_T9 = float(_spa_fp_T9[_fish_species])
                _fp_hiding_factor = float(_spa_fp_hiding_factor[_fish_species])
                _tp_L1 = float(_spa_tp_L1[_fish_species])
                _tp_L9 = float(_spa_tp_L9[_fish_species])
                _tp_D1 = float(_spa_tp_D1[_fish_species])
                _tp_D9 = float(_spa_tp_D9[_fish_species])
                _tp_V1 = float(_spa_tp_V1[_fish_species])
                _tp_V9 = float(_spa_tp_V9[_fish_species])
                _tp_I1 = float(_spa_tp_I1[_fish_species])
                _tp_I9 = float(_spa_tp_I9[_fish_species])
                _tp_H1 = float(_spa_tp_H1[_fish_species])
                _tp_H9 = float(_spa_tp_H9[_fish_species])
                _tp_hiding_factor = float(_spa_tp_hiding_factor[_fish_species])
                _cmax_table_x = np.asarray(
                    _sp_cmax_table_x[_fish_species], dtype=np.float64
                )
                _cmax_table_y = np.asarray(
                    _sp_cmax_table_y[_fish_species], dtype=np.float64
                )
            else:
                _cmax_A = params["cmax_A"]
                _cmax_B = params["cmax_B"]
                _react_dist_A = params["react_dist_A"]
                _react_dist_B = params["react_dist_B"]
                _turbid_threshold = params["turbid_threshold"]
                _turbid_min = params["turbid_min"]
                _turbid_exp = params["turbid_exp"]
                _light_threshold = params["light_threshold"]
                _light_min = params["light_min"]
                _light_exp = params["light_exp"]
                _capture_R1 = params["capture_R1"]
                _capture_R9 = params["capture_R9"]
                _max_speed_A = params["max_speed_A"]
                _max_speed_B = params["max_speed_B"]
                _resp_A = params["resp_A"]
                _resp_B = params["resp_B"]
                _resp_D = params["resp_D"]
                _search_area = params["search_area"]
                _fish_energy_density = params["fish_energy_density"]
                _mort_ht_T1 = params.get("mort_high_temp_T1", 28.0)
                _mort_ht_T9 = params.get("mort_high_temp_T9", 24.0)
                _mort_cond_S5 = params.get("mort_condition_S_at_K5", 0.8)
                _mort_cond_S8 = params.get("mort_condition_S_at_K8", 0.992)
                _mort_cond_Kcrit = params.get("mort_condition_K_crit", 0.8)
                _mort_strand_dry = params.get("mort_strand_survival_when_dry", 0.5)
                _fp_L1 = params.get("fish_pred_L1", 10.0)
                _fp_L9 = params.get("fish_pred_L9", 3.0)
                _fp_D1 = params.get("fish_pred_D1", 50.0)
                _fp_D9 = params.get("fish_pred_D9", 10.0)
                _fp_P1 = params.get("fish_pred_P1", 0.5)
                _fp_P9 = params.get("fish_pred_P9", 0.1)
                _fp_I1 = params.get("fish_pred_I1", 200.0)
                _fp_I9 = params.get("fish_pred_I9", 50.0)
                _fp_T1 = params.get("fish_pred_T1", 25.0)
                _fp_T9 = params.get("fish_pred_T9", 15.0)
                _fp_hiding_factor = params.get("fish_pred_hiding_factor", 0.5)
                _tp_L1 = params.get("terr_pred_L1", 15.0)
                _tp_L9 = params.get("terr_pred_L9", 5.0)
                _tp_D1 = params.get("terr_pred_D1", 50.0)
                _tp_D9 = params.get("terr_pred_D9", 10.0)
                _tp_V1 = params.get("terr_pred_V1", 50.0)
                _tp_V9 = params.get("terr_pred_V9", 10.0)
                _tp_I1 = params.get("terr_pred_I1", 200.0)
                _tp_I9 = params.get("terr_pred_I9", 50.0)
                _tp_H1 = params.get("terr_pred_H1", 50.0)
                _tp_H9 = params.get("terr_pred_H9", 10.0)
                _tp_hiding_factor = params.get("terr_pred_hiding_factor", 0.5)
                _cmax_table_x = np.asarray(params["cmax_temp_table_x"], dtype=np.float64)
                _cmax_table_y = np.asarray(params["cmax_temp_table_y"], dtype=np.float64)

            if _rp is not None:
                _drift_conc = float(
                    _rpa_drift_conc[min(_fish_reach, len(_rpa_drift_conc) - 1)]
                )
                _search_prod = float(
                    _rpa_search_prod[min(_fish_reach, len(_rpa_search_prod) - 1)]
                )
                _shelter_speed_frac = float(
                    _rpa_shelter_speed_frac[
                        min(_fish_reach, len(_rpa_shelter_speed_frac) - 1)
                    ]
                )
                _prey_energy_density = float(
                    _rpa_prey_energy_density[
                        min(_fish_reach, len(_rpa_prey_energy_density) - 1)
                    ]
                )
                _fp_min = float(
                    _rpa_fish_pred_min[min(_fish_reach, len(_rpa_fish_pred_min) - 1)]
                )
                _tp_min = float(
                    _rpa_terr_pred_min[min(_fish_reach, len(_rpa_terr_pred_min) - 1)]
                )
            else:
                _drift_conc = params["drift_conc"]
                _search_prod = params["search_prod"]
                _shelter_speed_frac = params["shelter_speed_frac"]
                _prey_energy_density = params["prey_energy_density"]
                _fp_min = params.get("fish_pred_min", 0.99)
                _tp_min = params.get("terr_pred_min", 0.99)

            _fl = float(trout_state.length[i])
            _fw = float(trout_state.weight[i])
            _fc = float(trout_state.condition[i])
            _frep = int(trout_state.superind_rep[i])

            _cmax_temp = cmax_temp_function(_temperature, _cmax_table_x, _cmax_table_y)
            _s_high_temp = _surv_ht(_temperature, _mort_ht_T1, _mort_ht_T9)
            _fp_temp_logistic = evaluate_logistic(_temperature, _fp_T1, _fp_T9)
            if _turbidity <= _turbid_threshold:
                _turbid_func = 1.0
            else:
                _turbid_func = _turbid_min + (1.0 - _turbid_min) * math.exp(
                    _turbid_exp * (_turbidity - _turbid_threshold)
                )
            _cap_mid = (_capture_R1 + _capture_R9) * 0.5
            _cap_slope = (
                _LN81 / (_capture_R9 - _capture_R1) if _capture_R9 != _capture_R1 else 0.0
            )

            _cmax_wt = _cmax_A * _fw**_cmax_B
            _cstepmax = c_stepmax(_cmax_wt, _cmax_temp, prev_cons, _step_length)
            _max_spd = (_max_speed_A * _fl + _max_speed_B) * _max_swim_temp_term
            _resp_std = _resp_A * _fw**_resp_B
            _detect_base = _react_dist_A + _react_dist_B * _fl
            _s_cond = _surv_cond(_fc, _mort_cond_S5, _mort_cond_S8, _mort_cond_Kcrit)
            _fp_L_term = evaluate_logistic(_fl, _fp_L1, _fp_L9)
            _tp_L_term = evaluate_logistic(_fl, _tp_L1, _tp_L9)

            if _HAS_NUMBA_FITNESS:
                candidates_i32 = (
                    candidates
                    if candidates.dtype == np.int32
                    else candidates.astype(np.int32)
                )
                _hiding_arr = (
                    _c_ahiding.astype(np.float64)
                    if _c_ahiding.dtype != np.float64
                    else _c_ahiding
                )
                _pisciv_safe = (
                    _pisciv_densities
                    if _pisciv_densities is not None
                    else np.zeros_like(_c_depth)
                )
                best_c, best_a, _, best_growth, best_non_starve = _numba_eval(
                    _fl,
                    _fw,
                    _fc,
                    prev_cons,
                    _frep,
                    _c_depth,
                    _c_vel,
                    _c_light,
                    _c_dist_esc,
                    _c_adrift,
                    _c_asearch,
                    _c_ashelter,
                    _hiding_arr,
                    _pisciv_safe,
                    candidates_i32,
                    _turbidity,
                    _temperature,
                    _drift_conc,
                    _search_prod,
                    _search_area,
                    _shelter_speed_frac,
                    _step_length,
                    _cmax_A,
                    _cmax_B,
                    _cmax_table_x,
                    _cmax_table_y,
                    _react_dist_A,
                    _react_dist_B,
                    _turbid_threshold,
                    _turbid_min,
                    _turbid_exp,
                    _light_threshold,
                    _light_min,
                    _light_exp,
                    _capture_R1,
                    _capture_R9,
                    _max_speed_A,
                    _max_speed_B,
                    _max_swim_temp_term,
                    _resp_A,
                    _resp_B,
                    _resp_D,
                    _resp_temp_term,
                    _prey_energy_density,
                    _fish_energy_density,
                    _mort_ht_T1,
                    _mort_ht_T9,
                    _mort_cond_S5,
                    _mort_cond_S8,
                    _mort_cond_Kcrit,
                    _fp_min,
                    _fp_L1,
                    _fp_L9,
                    _fp_D1,
                    _fp_D9,
                    _fp_P1,
                    _fp_P9,
                    _fp_I1,
                    _fp_I9,
                    _fp_T1,
                    _fp_T9,
                    _fp_hiding_factor,
                    _tp_min,
                    _tp_L1,
                    _tp_L9,
                    _tp_D1,
                    _tp_D9,
                    _tp_V1,
                    _tp_V9,
                    _tp_I1,
                    _tp_I9,
                    _tp_H1,
                    _tp_H9,
                    _tp_hiding_factor,
                    _mort_strand_dry,
                )
            else:
                for c_idx in candidates:
                    cd = float(_c_depth[c_idx])
                    cv = float(_c_vel[c_idx])
                    cl = float(_c_light[c_idx])
                    c_adrift_val = float(_c_adrift[c_idx])
                    c_asearch_val = float(_c_asearch[c_idx])
                    c_ashelter_val = float(_c_ashelter[c_idx])
                    c_ahiding_val = int(_c_ahiding[c_idx])
                    c_dist_esc_val = float(_c_dist_esc[c_idx])
                    _pisciv_d = (
                        float(_pisciv_densities[c_idx])
                        if _pisciv_densities is not None
                        else 0.0
                    )

                    s_str = _surv_str(cd, _mort_strand_dry)

                    if cl >= _light_threshold:
                        _light_func = 1.0
                    else:
                        _light_func = _light_min + (1.0 - _light_min) * math.exp(
                            _light_exp * (_light_threshold - cl)
                        )

                    _detect_adj = _detect_base * _turbid_func * _light_func

                    _fp_D_term = evaluate_logistic(cd, _fp_D1, _fp_D9)
                    _fp_P_term = evaluate_logistic(_pisciv_d, _fp_P1, _fp_P9)
                    _fp_I_term = evaluate_logistic(cl, _fp_I1, _fp_I9)

                    _tp_D_term = evaluate_logistic(cd, _tp_D1, _tp_D9)
                    _tp_V_term = evaluate_logistic(cv, _tp_V1, _tp_V9)
                    _tp_I_term = evaluate_logistic(cl, _tp_I1, _tp_I9)
                    _tp_H_term = evaluate_logistic(c_dist_esc_val, _tp_H1, _tp_H9)

                    for a_idx in range(3):
                        if a_idx == 1:
                            if cv > _max_spd:
                                continue
                        elif a_idx == 0:
                            if c_ashelter_val > _fl**2:
                                d_speed = cv * _shelter_speed_frac
                            else:
                                d_speed = cv
                            if d_speed > _max_spd:
                                continue

                        if a_idx == 0:
                            if cd <= 0 or cv <= 0:
                                intake = 0.0
                            else:
                                capture_height = min(cd, _detect_adj)
                                capture_area = 2.0 * _detect_adj * capture_height
                                vel_ratio = cv / _max_spd if _max_spd > 0 else 999.0
                                if _capture_R9 == _capture_R1:
                                    capture_success = 0.5
                                else:
                                    cap_arg = -_cap_slope * (vel_ratio - _cap_mid)
                                    if cap_arg > 500.0:
                                        cap_arg = 500.0
                                    elif cap_arg < -500.0:
                                        cap_arg = -500.0
                                    capture_success = 1.0 / (1.0 + math.exp(cap_arg))
                                gross = (
                                    capture_area
                                    * _drift_conc
                                    * cv
                                    * 86400.0
                                    * capture_success
                                )
                                gross = min(gross, _cstepmax)
                                intake = min(gross, c_adrift_val / max(_frep, 1))
                            if c_ashelter_val > _fl**2:
                                swim_spd = cv * _shelter_speed_frac
                            else:
                                swim_spd = cv
                            if _max_spd <= 0:
                                resp_val = 999999.0
                            else:
                                ratio = swim_spd / _max_spd
                                if ratio > 20:
                                    resp_val = 999999.0
                                else:
                                    resp_val = (
                                        _resp_std
                                        * _resp_temp_term
                                        * math.exp(_resp_D * ratio**2)
                                    )
                            net_energy = intake * _prey_energy_density - resp_val

                        elif a_idx == 1:
                            if _max_spd <= 0:
                                intake = 0.0
                            else:
                                vel_ratio_s = (_max_spd - cv) / _max_spd
                                if vel_ratio_s < 0:
                                    intake = 0.0
                                else:
                                    gross = _search_prod * _search_area * vel_ratio_s
                                    gross = min(gross, _cstepmax)
                                    intake = min(gross, c_asearch_val / max(_frep, 1))
                            if _max_spd <= 0:
                                resp_val = 999999.0
                            else:
                                ratio = cv / _max_spd
                                if ratio > 20:
                                    resp_val = 999999.0
                                else:
                                    resp_val = (
                                        _resp_std
                                        * _resp_temp_term
                                        * math.exp(_resp_D * ratio**2)
                                    )
                            net_energy = intake * _prey_energy_density - resp_val

                        else:
                            if _max_spd <= 0:
                                resp_val = 999999.0
                            else:
                                resp_val = _resp_std * _resp_temp_term
                            net_energy = -resp_val

                        growth = net_energy / _fish_energy_density

                        if a_idx == 2:
                            fp_hide = _fp_hiding_factor
                        else:
                            fp_hide = 0.0
                        fp_rel_risk = (
                            (1.0 - _fp_L_term)
                            * (1.0 - _fp_D_term)
                            * (1.0 - _fp_P_term)
                            * (1.0 - _fp_I_term)
                            * (1.0 - _fp_temp_logistic)
                            * (1.0 - fp_hide)
                        )
                        s_fp = _fp_min + (1.0 - _fp_min) * (1.0 - fp_rel_risk)

                        if (
                            a_idx == 2 and c_ahiding_val >= _frep
                        ):
                            tp_hide = _tp_hiding_factor
                        else:
                            tp_hide = 0.0
                        tp_rel_risk = (
                            (1.0 - _tp_L_term)
                            * (1.0 - _tp_D_term)
                            * (1.0 - _tp_V_term)
                            * (1.0 - _tp_I_term)
                            * (1.0 - _tp_H_term)
                            * (1.0 - tp_hide)
                        )
                        s_tp = _tp_min + (1.0 - _tp_min) * (1.0 - tp_rel_risk)

                        non_starve = _s_high_temp * s_str * s_fp * s_tp
                        f = growth * _step_length * non_starve * _s_cond

                        if f > best_fitness:
                            best_fitness = f
                            best_c = c_idx
                            best_a = a_idx
                            best_growth = growth
                            best_non_starve = non_starve * _s_cond

            best_cells[i] = best_c
            best_activities[i] = best_a
            trout_state.cell_idx[i] = best_c
            trout_state.activity[i] = best_a
            trout_state.reach_idx[i] = cs.reach_idx[best_c]
            trout_state.last_growth_rate[i] = best_growth

            # Arc D: expected_fitness post-pass (same formula as batch path)
            sp_i = int(trout_state.species_idx[i])
            if _sp is not None and "fitness_horizon" in _sp:
                _fh = float(_sp["fitness_horizon"][sp_i])
                _fitL = float(_sp["fitness_length"][sp_i])
            else:
                _fh = 60.0
                _fitL = 15.0
            if _fh <= 0.0:
                _ehab = 0.0
            else:
                _dsc = max(0.0, min(1.0, best_non_starve))
                _ehab = _dsc ** _fh
                if _fitL > 0.0 and _fl < _fitL:
                    _L_at_h = _fl + best_growth * _fh
                    if _L_at_h < _fitL:
                        _ehab *= max(0.0, _L_at_h) / _fitL
            if hasattr(trout_state, "best_habitat_fitness"):
                trout_state.best_habitat_fitness[i] = max(0.0, min(1.0, _ehab))

            if best_a == 0:
                intake = drift_intake(
                    _fl,
                    _c_depth[best_c],
                    _c_vel[best_c],
                    _c_light[best_c],
                    _turbidity,
                    _drift_conc,
                    _max_spd,
                    _cstepmax,
                    _c_adrift[best_c],
                    _frep,
                    _react_dist_A,
                    _react_dist_B,
                    _turbid_threshold,
                    _turbid_min,
                    _turbid_exp,
                    _light_threshold,
                    _light_min,
                    _light_exp,
                    _capture_R1,
                    _capture_R9,
                )
                _c_adrift[best_c] -= min(intake * _frep, _c_adrift[best_c])
                shelter_needed = _fl**2 * _frep
                if _c_ashelter[best_c] >= shelter_needed:
                    _c_ashelter[best_c] -= shelter_needed
                    trout_state.in_shelter[i] = True
            elif best_a == 1:
                intake = search_intake(
                    _c_vel[best_c],
                    _max_spd,
                    _search_prod,
                    _search_area,
                    _cstepmax,
                    _c_asearch[best_c],
                    _frep,
                )
                _c_asearch[best_c] -= min(intake * _frep, _c_asearch[best_c])
            elif best_a == 2:
                if _c_ahiding[best_c] >= _frep:
                    _c_ahiding[best_c] -= _frep
