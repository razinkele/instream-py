"""Behavioral decisions — logistic functions, candidate mask, fitness, habitat selection."""

import math
import numpy as np

try:
    from instream.backends.numba_backend.fitness import (
        _evaluate_all_cells as _numba_eval,
    )

    _HAS_NUMBA_FITNESS = True
except ImportError:
    _HAS_NUMBA_FITNESS = False

from instream.modules.growth import (
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
    midpoint = (L1 + L9) * 0.5
    slope = _LN81 / (L9 - L1) if L9 != L1 else 0.0
    arg = -slope * (x - midpoint)
    if arg > 500.0:
        arg = 500.0
    elif arg < -500.0:
        arg = -500.0
    return 1.0 / (1.0 + math.exp(arg))


def evaluate_logistic_array(x, L1, L9):
    """Evaluate logistic function on an array."""
    x = np.asarray(x, dtype=np.float64)
    midpoint = (L1 + L9) / 2.0
    slope = np.log(81.0) / (L9 - L1) if L9 != L1 else 0.0
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
    trout_state, fem_space, move_radius_max, move_radius_L1, move_radius_L9
):
    """Build per-fish candidate cell arrays (sparse, no dense mask).

    Returns list of length capacity. Dead fish get None. Alive fish get
    np.ndarray of wet candidate cell indices (int32).
    """
    n_fish = trout_state.alive.shape[0]
    wet_mask = fem_space.cell_state.depth > 0
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
    from instream.modules.survival import (
        survival_high_temperature as _ff_surv_ht,
        survival_stranding as _ff_surv_str,
        survival_condition as surv_cond_fn,
        survival_fish_predation as _ff_surv_fp,
        survival_terrestrial_predation as _ff_surv_tp,
    )

    s_ht = _ff_surv_ht(temperature, mort_high_temp_T1, mort_high_temp_T9)
    s_str = _ff_surv_str(depth, mort_strand_survival_when_dry)
    s_cond = surv_cond_fn(condition, mort_condition_S_at_K5, mort_condition_S_at_K8)
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
    """
    # Lazy import to avoid circular dependency (survival imports evaluate_logistic)
    from instream.modules.survival import (  # noqa: E402
        survival_high_temperature as _surv_ht,
        survival_stranding as _surv_str,
        survival_condition as _surv_cond,
    )

    candidate_lists = build_candidate_lists(
        trout_state,
        fem_space,
        params["move_radius_max"],
        params["move_radius_L1"],
        params["move_radius_L9"],
    )

    cs = fem_space.cell_state
    alive = trout_state.alive_indices()

    # Sort by length descending (large fish first, as in NetLogo)
    alive_sorted = alive[np.argsort(-trout_state.length[alive])]

    best_cells = np.full(trout_state.alive.shape[0], -1, dtype=np.int32)
    best_activities = np.zeros(trout_state.alive.shape[0], dtype=np.int32)
    intake_amounts = np.zeros(trout_state.alive.shape[0], dtype=np.float64)

    activities = ["drift", "search", "hide"]

    # === PRE-EXTRACT params to locals (eliminates 37M+ dict lookups) ===
    _temperature = params["temperature"]
    _turbidity = params["turbidity"]
    _drift_conc = params["drift_conc"]
    _search_prod = params["search_prod"]
    _search_area = params["search_area"]
    _shelter_speed_frac = params["shelter_speed_frac"]
    _step_length = params["step_length"]
    _cmax_A = params["cmax_A"]
    _cmax_B = params["cmax_B"]
    _cmax_table_x = np.asarray(params["cmax_temp_table_x"], dtype=np.float64)
    _cmax_table_y = np.asarray(params["cmax_temp_table_y"], dtype=np.float64)
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
    _max_swim_temp_term = params["max_swim_temp_term"]
    _resp_A = params["resp_A"]
    _resp_B = params["resp_B"]
    _resp_D = params["resp_D"]
    _resp_temp_term = params["resp_temp_term"]
    _prey_energy_density = params["prey_energy_density"]
    _fish_energy_density = params["fish_energy_density"]
    # Survival parameters (with defaults)
    _mort_ht_T1 = params.get("mort_high_temp_T1", 28.0)
    _mort_ht_T9 = params.get("mort_high_temp_T9", 24.0)
    _mort_cond_S5 = params.get("mort_condition_S_at_K5", 0.8)
    _mort_cond_S8 = params.get("mort_condition_S_at_K8", 0.992)
    _fp_min = params.get("fish_pred_min", 0.99)
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
    _tp_min = params.get("terr_pred_min", 0.99)
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
    _mort_strand_dry = params.get("mort_strand_survival_when_dry", 0.5)
    _pisciv_densities = params.get("pisciv_densities", None)

    # Cell arrays to locals
    _c_depth = cs.depth
    _c_vel = cs.velocity
    _c_light = cs.light
    _c_adrift = cs.available_drift
    _c_asearch = cs.available_search
    _c_ashelter = cs.available_vel_shelter
    _c_ahiding = cs.available_hiding_places
    _c_dist_esc = cs.dist_escape

    # === STEP-LEVEL INVARIANTS (computed ONCE, not 1.2M times) ===
    _cmax_temp = cmax_temp_function(_temperature, _cmax_table_x, _cmax_table_y)
    _s_high_temp = _surv_ht(_temperature, _mort_ht_T1, _mort_ht_T9)
    # Fish predation temperature term (same for all cells)
    _fp_temp_logistic = evaluate_logistic(_temperature, _fp_T1, _fp_T9)
    # Turbidity function (same for all cells)
    if _turbidity <= _turbid_threshold:
        _turbid_func = 1.0
    else:
        _turbid_func = _turbid_min + (1.0 - _turbid_min) * math.exp(
            _turbid_exp * (_turbidity - _turbid_threshold)
        )
    # Capture success midpoint/slope (same for all cells)
    _cap_mid = (_capture_R1 + _capture_R9) * 0.5
    _cap_slope = (
        _LN81 / (_capture_R9 - _capture_R1) if _capture_R9 != _capture_R1 else 0.0
    )

    for i in alive_sorted:
        candidates = candidate_lists[i]
        if candidates is None or len(candidates) == 0:
            # No wet candidates — fish is stranded at current cell
            cur = trout_state.cell_idx[i]
            if cur < 0 or cur >= fem_space.num_cells:
                cur = 0  # safety fallback
            best_cells[i] = cur
            best_activities[i] = 2  # hide
            trout_state.cell_idx[i] = cur
            trout_state.activity[i] = 2
            continue

        best_fitness = -np.inf
        best_c = candidates[0]
        best_a = 2  # default hide
        best_growth = 0.0  # track growth to avoid second growth_rate_for call

        prev_cons = float(np.sum(trout_state.consumption_memory[i]))

        # === PER-FISH INVARIANTS (computed ONCE, not 3579x) ===
        _fl = float(trout_state.length[i])
        _fw = float(trout_state.weight[i])
        _fc = float(trout_state.condition[i])
        _frep = int(trout_state.superind_rep[i])
        _cmax_wt = _cmax_A * _fw**_cmax_B
        _cstepmax = c_stepmax(_cmax_wt, _cmax_temp, prev_cons, _step_length)
        _max_spd = (_max_speed_A * _fl + _max_speed_B) * _max_swim_temp_term
        _resp_std = _resp_A * _fw**_resp_B
        _detect_base = _react_dist_A + _react_dist_B * _fl
        _s_cond = _surv_cond(_fc, _mort_cond_S5, _mort_cond_S8)
        _fp_L_term = evaluate_logistic(_fl, _fp_L1, _fp_L9)
        _tp_L_term = evaluate_logistic(_fl, _tp_L1, _tp_L9)

        # Evaluate fitness for all candidate cells x activities
        # Fish sees CURRENT resource levels (depleted by larger fish above)
        if _HAS_NUMBA_FITNESS:
            # --- Numba fast path: compiled inner loop ---
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
            best_c, best_a, _, best_growth = _numba_eval(
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
            # --- Python fallback: inline inner loop ---
            for c_idx in candidates:
                # --- Read cell values ONCE per cell ---
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

                # Stranding survival (same for all activities at this cell)
                s_str = _surv_str(cd, _mort_strand_dry)

                # Light function for drift intake (per-cell, same for all activities)
                if cl >= _light_threshold:
                    _light_func = 1.0
                else:
                    _light_func = _light_min + (1.0 - _light_min) * math.exp(
                        _light_exp * (_light_threshold - cl)
                    )

                # Adjusted detection distance for this cell
                _detect_adj = _detect_base * _turbid_func * _light_func

                # Fish predation survival terms that vary by cell (not activity)
                _fp_D_term = evaluate_logistic(cd, _fp_D1, _fp_D9)
                _fp_P_term = evaluate_logistic(_pisciv_d, _fp_P1, _fp_P9)
                _fp_I_term = evaluate_logistic(cl, _fp_I1, _fp_I9)

                # Terrestrial predation terms that vary by cell (not activity)
                _tp_D_term = evaluate_logistic(cd, _tp_D1, _tp_D9)
                _tp_V_term = evaluate_logistic(cv, _tp_V1, _tp_V9)
                _tp_I_term = evaluate_logistic(cl, _tp_I1, _tp_I9)
                _tp_H_term = evaluate_logistic(c_dist_esc_val, _tp_H1, _tp_H9)

                for a_idx in range(3):
                    # --- Activity 0: drift, 1: search, 2: hide ---

                    # Speed check
                    if a_idx == 1:  # search
                        if cv > _max_spd:
                            continue
                    elif a_idx == 0:  # drift
                        if c_ashelter_val > _fl**2:
                            d_speed = cv * _shelter_speed_frac
                        else:
                            d_speed = cv
                        if d_speed > _max_spd:
                            continue

                    # --- Compute growth rate inline ---
                    if a_idx == 0:  # drift
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
                        # Swim speed for respiration
                        if c_ashelter_val > _fl**2:
                            swim_spd = cv * _shelter_speed_frac
                        else:
                            swim_spd = cv
                        # Respiration
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

                    elif a_idx == 1:  # search
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
                        # Respiration (swim speed = velocity for search)
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

                    else:  # hide (a_idx == 2)
                        # Respiration at rest (swim_speed = 0)
                        if _max_spd <= 0:
                            resp_val = 999999.0
                        else:
                            # ratio = 0, exp(0) = 1
                            resp_val = _resp_std * _resp_temp_term
                        net_energy = -resp_val

                    growth = net_energy / _fish_energy_density

                    # --- Compute survival inline ---
                    # Fish predation: activity-dependent hiding factor
                    if a_idx == 2:  # hide
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

                    # Terrestrial predation
                    if (
                        a_idx == 2 and c_ahiding_val >= _frep
                    ):  # hide with available spots
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

        # Assign fish to chosen cell + activity
        best_cells[i] = best_c
        best_activities[i] = best_a
        trout_state.cell_idx[i] = best_c
        trout_state.activity[i] = best_a

        # Store raw growth rate (tracked in inner loop, no second call needed)
        trout_state.last_growth_rate[i] = best_growth

        # --- DEPLETE IMMEDIATELY (before next fish evaluates) ---
        # This matches NetLogo: large fish deplete first, small fish see reduced resources.
        # Re-use pre-computed per-fish invariants (_fl, _fw, _frep, _cmax_wt, etc.)
        if best_a == 0:  # drift
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
            # Deplete velocity shelter
            shelter_needed = _fl**2 * _frep
            if _c_ashelter[best_c] >= shelter_needed:
                _c_ashelter[best_c] -= shelter_needed
                trout_state.in_shelter[i] = True
        elif best_a == 1:  # search
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
        elif best_a == 2:  # hide
            if _c_ahiding[best_c] >= _frep:
                _c_ahiding[best_c] -= _frep
