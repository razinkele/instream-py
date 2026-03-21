"""Behavioral decisions — logistic functions, candidate mask, fitness, habitat selection."""
import numpy as np

from instream.modules.growth import (
    growth_rate_for, max_swim_speed, drift_swim_speed,
    drift_intake, search_intake,
    cmax_temp_function, c_stepmax,
)


def evaluate_logistic(x, L1, L9):
    """Evaluate logistic function where f(L1)=0.1 and f(L9)=0.9. Scalar version."""
    midpoint = (L1 + L9) / 2.0
    slope = np.log(81.0) / (L9 - L1) if L9 != L1 else 0.0
    arg = -slope * (x - midpoint)
    arg = float(np.clip(arg, -500, 500))
    return float(1.0 / (1.0 + np.exp(arg)))


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


def build_candidate_mask(trout_state, fem_space, move_radius_max, move_radius_L1, move_radius_L9):
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
        radius = movement_radius(trout_state.length[i], move_radius_max,
                                  move_radius_L1, move_radius_L9)
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


def fitness_for(activity, length, weight, depth, velocity, light, turbidity, temperature,
                drift_conc, search_prod, search_area,
                available_drift, available_search, available_shelter, shelter_speed_frac,
                superind_rep, prev_consumption, step_length,
                cmax_A, cmax_B, cmax_temp_table_x, cmax_temp_table_y,
                react_dist_A, react_dist_B,
                turbid_threshold, turbid_min, turbid_exp,
                light_threshold, light_min, light_exp,
                capture_R1, capture_R9,
                max_speed_A, max_speed_B, max_swim_temp_term,
                resp_A, resp_B, resp_D, resp_temp_term,
                prey_energy_density, fish_energy_density,
                # --- Survival parameters (Phase 5) ---
                condition=1.0,
                mort_high_temp_T1=28.0, mort_high_temp_T9=24.0,
                mort_condition_S_at_K5=0.8, mort_condition_S_at_K8=0.992,
                fish_pred_min=0.99,
                fish_pred_L1=10.0, fish_pred_L9=3.0,
                fish_pred_D1=50.0, fish_pred_D9=10.0,
                fish_pred_P1=0.5, fish_pred_P9=0.1,
                fish_pred_I1=200.0, fish_pred_I9=50.0,
                fish_pred_T1=25.0, fish_pred_T9=15.0,
                fish_pred_hiding_factor=0.5,
                pisciv_density=0.0,
                terr_pred_min=0.99,
                terr_pred_L1=15.0, terr_pred_L9=5.0,
                terr_pred_D1=50.0, terr_pred_D9=10.0,
                terr_pred_V1=50.0, terr_pred_V9=10.0,
                terr_pred_I1=200.0, terr_pred_I9=50.0,
                terr_pred_H1=50.0, terr_pred_H9=10.0,
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
        d_speed = drift_swim_speed(velocity, length, available_shelter, shelter_speed_frac)
        if d_speed > max_speed:
            return 0.0

    growth = growth_rate_for(
        activity=activity, length=length, weight=weight,
        depth=depth, velocity=velocity, light=light,
        turbidity=turbidity, temperature=temperature,
        drift_conc=drift_conc, search_prod=search_prod, search_area=search_area,
        available_drift=available_drift, available_search=available_search,
        available_shelter=available_shelter, shelter_speed_frac=shelter_speed_frac,
        superind_rep=superind_rep, prev_consumption=prev_consumption, step_length=step_length,
        cmax_A=cmax_A, cmax_B=cmax_B,
        cmax_temp_table_x=cmax_temp_table_x, cmax_temp_table_y=cmax_temp_table_y,
        react_dist_A=react_dist_A, react_dist_B=react_dist_B,
        turbid_threshold=turbid_threshold, turbid_min=turbid_min, turbid_exp=turbid_exp,
        light_threshold=light_threshold, light_min=light_min, light_exp=light_exp,
        capture_R1=capture_R1, capture_R9=capture_R9,
        max_speed_A=max_speed_A, max_speed_B=max_speed_B,
        max_swim_temp_term=max_swim_temp_term,
        resp_A=resp_A, resp_B=resp_B, resp_D=resp_D, resp_temp_term=resp_temp_term,
        prey_energy_density=prey_energy_density, fish_energy_density=fish_energy_density,
    )

    # Phase 5: full fitness = growth * survival
    from instream.modules.survival import (
        survival_high_temperature, survival_stranding,
        survival_condition as surv_cond_fn,
        survival_fish_predation, survival_terrestrial_predation,
    )
    s_ht = survival_high_temperature(temperature, mort_high_temp_T1, mort_high_temp_T9)
    s_str = survival_stranding(depth, mort_strand_survival_when_dry)
    s_cond = surv_cond_fn(condition, mort_condition_S_at_K5, mort_condition_S_at_K8)
    s_fp = survival_fish_predation(
        length, depth, light, pisciv_density, temperature, activity,
        fish_pred_min, fish_pred_L1, fish_pred_L9,
        fish_pred_D1, fish_pred_D9, fish_pred_P1, fish_pred_P9,
        fish_pred_I1, fish_pred_I9, fish_pred_T1, fish_pred_T9,
        fish_pred_hiding_factor,
    )
    s_tp = survival_terrestrial_predation(
        length, depth, velocity, light, dist_escape,
        activity, available_hiding, superind_rep,
        terr_pred_min, terr_pred_L1, terr_pred_L9,
        terr_pred_D1, terr_pred_D9, terr_pred_V1, terr_pred_V9,
        terr_pred_I1, terr_pred_I9, terr_pred_H1, terr_pred_H9,
        terr_pred_hiding_factor,
    )
    non_starve = s_ht * s_str * s_fp * s_tp
    return growth * step_length * non_starve * s_cond


def deplete_resources(fish_order, chosen_cells, chosen_activities,
                      intake_amounts, fish_lengths, superind_reps,
                      available_drift, available_search,
                      available_shelter, available_hiding):
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
    """
    mask = build_candidate_mask(trout_state, fem_space,
                                 params['move_radius_max'],
                                 params['move_radius_L1'],
                                 params['move_radius_L9'])

    cs = fem_space.cell_state
    alive = trout_state.alive_indices()

    # Sort by length descending (large fish first, as in NetLogo)
    alive_sorted = alive[np.argsort(-trout_state.length[alive])]

    best_cells = np.full(trout_state.alive.shape[0], -1, dtype=np.int32)
    best_activities = np.zeros(trout_state.alive.shape[0], dtype=np.int32)
    intake_amounts = np.zeros(trout_state.alive.shape[0], dtype=np.float64)

    activities = ["drift", "search", "hide"]

    for i in alive_sorted:
        candidates = np.where(mask[i])[0]
        if len(candidates) == 0:
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

        prev_cons = float(np.sum(trout_state.consumption_memory[i]))

        # Evaluate fitness for all candidate cells × activities
        # Fish sees CURRENT resource levels (depleted by larger fish above)
        for c_idx in candidates:
            for a_idx, act_name in enumerate(activities):
                # Build survival kwargs from params (use defaults if not provided)
                _pisciv_densities = params.get('pisciv_densities', None)
                _pisciv_d = float(_pisciv_densities[c_idx]) if _pisciv_densities is not None else 0.0
                f = fitness_for(
                    activity=act_name,
                    length=trout_state.length[i], weight=trout_state.weight[i],
                    depth=cs.depth[c_idx], velocity=cs.velocity[c_idx],
                    light=cs.light[c_idx], turbidity=params['turbidity'],
                    temperature=params['temperature'],
                    drift_conc=params['drift_conc'], search_prod=params['search_prod'],
                    search_area=params['search_area'],
                    available_drift=cs.available_drift[c_idx],
                    available_search=cs.available_search[c_idx],
                    available_shelter=cs.available_vel_shelter[c_idx],
                    shelter_speed_frac=params['shelter_speed_frac'],
                    superind_rep=trout_state.superind_rep[i],
                    prev_consumption=prev_cons,
                    step_length=params['step_length'],
                    cmax_A=params['cmax_A'], cmax_B=params['cmax_B'],
                    cmax_temp_table_x=params['cmax_temp_table_x'],
                    cmax_temp_table_y=params['cmax_temp_table_y'],
                    react_dist_A=params['react_dist_A'], react_dist_B=params['react_dist_B'],
                    turbid_threshold=params['turbid_threshold'],
                    turbid_min=params['turbid_min'], turbid_exp=params['turbid_exp'],
                    light_threshold=params['light_threshold'],
                    light_min=params['light_min'], light_exp=params['light_exp'],
                    capture_R1=params['capture_R1'], capture_R9=params['capture_R9'],
                    max_speed_A=params['max_speed_A'], max_speed_B=params['max_speed_B'],
                    max_swim_temp_term=params['max_swim_temp_term'],
                    resp_A=params['resp_A'], resp_B=params['resp_B'],
                    resp_D=params['resp_D'],
                    resp_temp_term=params['resp_temp_term'],
                    prey_energy_density=params['prey_energy_density'],
                    fish_energy_density=params['fish_energy_density'],
                    # Survival parameters (Phase 5)
                    condition=float(trout_state.condition[i]),
                    mort_high_temp_T1=params.get('mort_high_temp_T1', 28.0),
                    mort_high_temp_T9=params.get('mort_high_temp_T9', 24.0),
                    mort_condition_S_at_K5=params.get('mort_condition_S_at_K5', 0.8),
                    mort_condition_S_at_K8=params.get('mort_condition_S_at_K8', 0.992),
                    fish_pred_min=params.get('fish_pred_min', 0.99),
                    fish_pred_L1=params.get('fish_pred_L1', 10.0),
                    fish_pred_L9=params.get('fish_pred_L9', 3.0),
                    fish_pred_D1=params.get('fish_pred_D1', 50.0),
                    fish_pred_D9=params.get('fish_pred_D9', 10.0),
                    fish_pred_P1=params.get('fish_pred_P1', 0.5),
                    fish_pred_P9=params.get('fish_pred_P9', 0.1),
                    fish_pred_I1=params.get('fish_pred_I1', 200.0),
                    fish_pred_I9=params.get('fish_pred_I9', 50.0),
                    fish_pred_T1=params.get('fish_pred_T1', 25.0),
                    fish_pred_T9=params.get('fish_pred_T9', 15.0),
                    fish_pred_hiding_factor=params.get('fish_pred_hiding_factor', 0.5),
                    pisciv_density=_pisciv_d,
                    terr_pred_min=params.get('terr_pred_min', 0.99),
                    terr_pred_L1=params.get('terr_pred_L1', 15.0),
                    terr_pred_L9=params.get('terr_pred_L9', 5.0),
                    terr_pred_D1=params.get('terr_pred_D1', 50.0),
                    terr_pred_D9=params.get('terr_pred_D9', 10.0),
                    terr_pred_V1=params.get('terr_pred_V1', 50.0),
                    terr_pred_V9=params.get('terr_pred_V9', 10.0),
                    terr_pred_I1=params.get('terr_pred_I1', 200.0),
                    terr_pred_I9=params.get('terr_pred_I9', 50.0),
                    terr_pred_H1=params.get('terr_pred_H1', 50.0),
                    terr_pred_H9=params.get('terr_pred_H9', 10.0),
                    terr_pred_hiding_factor=params.get('terr_pred_hiding_factor', 0.5),
                    dist_escape=float(cs.dist_escape[c_idx]),
                    available_hiding=int(cs.available_hiding_places[c_idx]),
                    mort_strand_survival_when_dry=params.get('mort_strand_survival_when_dry', 0.5),
                )
                if f > best_fitness:
                    best_fitness = f
                    best_c = c_idx
                    best_a = a_idx

        # Assign fish to chosen cell + activity
        best_cells[i] = best_c
        best_activities[i] = best_a
        trout_state.cell_idx[i] = best_c
        trout_state.activity[i] = best_a

        # Store raw growth rate (NOT fitness, which now includes survival)
        chosen_growth = growth_rate_for(
            activity=activities[best_a],
            length=trout_state.length[i], weight=trout_state.weight[i],
            depth=cs.depth[best_c], velocity=cs.velocity[best_c],
            light=cs.light[best_c], turbidity=params['turbidity'],
            temperature=params['temperature'],
            drift_conc=params['drift_conc'], search_prod=params['search_prod'],
            search_area=params['search_area'],
            available_drift=cs.available_drift[best_c],
            available_search=cs.available_search[best_c],
            available_shelter=cs.available_vel_shelter[best_c],
            shelter_speed_frac=params['shelter_speed_frac'],
            superind_rep=trout_state.superind_rep[i],
            prev_consumption=prev_cons,
            step_length=params['step_length'],
            cmax_A=params['cmax_A'], cmax_B=params['cmax_B'],
            cmax_temp_table_x=params['cmax_temp_table_x'],
            cmax_temp_table_y=params['cmax_temp_table_y'],
            react_dist_A=params['react_dist_A'], react_dist_B=params['react_dist_B'],
            turbid_threshold=params['turbid_threshold'],
            turbid_min=params['turbid_min'], turbid_exp=params['turbid_exp'],
            light_threshold=params['light_threshold'],
            light_min=params['light_min'], light_exp=params['light_exp'],
            capture_R1=params['capture_R1'], capture_R9=params['capture_R9'],
            max_speed_A=params['max_speed_A'], max_speed_B=params['max_speed_B'],
            max_swim_temp_term=params['max_swim_temp_term'],
            resp_A=params['resp_A'], resp_B=params['resp_B'],
            resp_D=params['resp_D'],
            resp_temp_term=params['resp_temp_term'],
            prey_energy_density=params['prey_energy_density'],
            fish_energy_density=params['fish_energy_density'],
        )
        trout_state.last_growth_rate[i] = chosen_growth

        # --- DEPLETE IMMEDIATELY (before next fish evaluates) ---
        # This matches NetLogo: large fish deplete first, small fish see reduced resources.
        _len = trout_state.length[i]
        _wt = trout_state.weight[i]
        _rep = trout_state.superind_rep[i]
        _cmax_wt = params['cmax_A'] * _wt ** params['cmax_B']
        _cmax_temp = cmax_temp_function(params['temperature'],
                                         params['cmax_temp_table_x'],
                                         params['cmax_temp_table_y'])
        _cstepmax = c_stepmax(_cmax_wt, _cmax_temp, prev_cons, params['step_length'])
        _max_spd_len = params['max_speed_A'] * _len + params['max_speed_B']
        _max_spd = max_swim_speed(_max_spd_len, params['max_swim_temp_term'])

        if best_a == 0:  # drift
            intake = drift_intake(
                _len, cs.depth[best_c], cs.velocity[best_c],
                cs.light[best_c], params['turbidity'], params['drift_conc'],
                _max_spd, _cstepmax, cs.available_drift[best_c],
                _rep,
                params['react_dist_A'], params['react_dist_B'],
                params['turbid_threshold'], params['turbid_min'], params['turbid_exp'],
                params['light_threshold'], params['light_min'], params['light_exp'],
                params['capture_R1'], params['capture_R9'])
            cs.available_drift[best_c] -= min(intake * _rep, cs.available_drift[best_c])
            # Deplete velocity shelter
            shelter_needed = _len ** 2 * _rep
            if cs.available_vel_shelter[best_c] >= shelter_needed:
                cs.available_vel_shelter[best_c] -= shelter_needed
                trout_state.in_shelter[i] = True
        elif best_a == 1:  # search
            intake = search_intake(
                cs.velocity[best_c], _max_spd,
                params['search_prod'], params['search_area'],
                _cstepmax, cs.available_search[best_c],
                _rep)
            cs.available_search[best_c] -= min(intake * _rep, cs.available_search[best_c])
        elif best_a == 2:  # hide
            if cs.available_hiding_places[best_c] >= _rep:
                cs.available_hiding_places[best_c] -= _rep
