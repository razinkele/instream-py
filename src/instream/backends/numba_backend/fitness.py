"""Numba-compiled fitness evaluation kernel for habitat selection."""

import math
import numba
import numpy as np

_LN81 = math.log(81.0)


@numba.njit(cache=True)
def _logistic(x, L1, L9):
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


@numba.njit(cache=True)
def _drift_intake(
    length,
    depth,
    velocity,
    light,
    turbidity,
    drift_conc,
    max_swim_spd,
    c_stepmax_val,
    available_drift,
    superind_rep,
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
):
    if depth <= 0.0 or velocity <= 0.0:
        return 0.0
    detect_dist = react_dist_A + react_dist_B * length
    if turbidity <= turbid_threshold:
        turbid_func = 1.0
    else:
        turbid_func = turbid_min + (1.0 - turbid_min) * math.exp(
            turbid_exp * (turbidity - turbid_threshold)
        )
    if light >= light_threshold:
        light_func = 1.0
    else:
        light_func = light_min + (1.0 - light_min) * math.exp(
            light_exp * (light_threshold - light)
        )
    detect_dist *= turbid_func * light_func
    capture_height = min(depth, detect_dist)
    capture_area = 2.0 * detect_dist * capture_height
    vel_ratio = velocity / max_swim_spd if max_swim_spd > 0.0 else 999.0
    if capture_R9 == capture_R1:
        capture_success = 0.5
    else:
        mid = (capture_R1 + capture_R9) * 0.5
        slp = _LN81 / (capture_R9 - capture_R1)
        cap_arg = -slp * (vel_ratio - mid)
        if cap_arg > 500.0:
            cap_arg = 500.0
        elif cap_arg < -500.0:
            cap_arg = -500.0
        capture_success = 1.0 / (1.0 + math.exp(cap_arg))
    gross = capture_area * drift_conc * velocity * 86400.0 * capture_success
    gross = min(gross, c_stepmax_val)
    rep = max(superind_rep, 1)
    gross = min(gross, available_drift / rep)
    return gross


@numba.njit(cache=True)
def _search_intake(
    velocity,
    max_swim_spd,
    search_prod,
    search_area,
    c_stepmax_val,
    available_search,
    superind_rep,
):
    if max_swim_spd <= 0.0:
        return 0.0
    vel_ratio = (max_swim_spd - velocity) / max_swim_spd
    if vel_ratio < 0.0:
        return 0.0
    gross = search_prod * search_area * vel_ratio
    gross = min(gross, c_stepmax_val)
    rep = max(superind_rep, 1)
    gross = min(gross, available_search / rep)
    return gross


@numba.njit(cache=True)
def _respiration(resp_std, resp_temp_term, swim_speed, max_swim_spd, resp_D):
    if max_swim_spd <= 0.0:
        return 999999.0
    ratio = swim_speed / max_swim_spd
    if ratio > 20.0:
        return 999999.0
    return resp_std * resp_temp_term * math.exp(resp_D * ratio * ratio)


@numba.njit(cache=True)
def _evaluate_all_cells_v2(
    # Fish scalars
    fish_length,
    fish_weight,
    fish_condition,
    prev_consumption,
    superind_rep,
    # Cell arrays (full mesh, indexed by candidates)
    cell_depths,
    cell_velocities,
    cell_lights,
    cell_dist_escape,
    cell_avail_drift,
    cell_avail_search,
    cell_avail_shelter,
    cell_avail_hiding,
    cell_pisciv,
    # Candidate indices
    candidate_indices,
    # Step-level scalars
    turbidity,
    temperature,
    drift_conc,
    search_prod,
    search_area,
    shelter_speed_frac,
    step_length,
    # Species params
    cmax_A,
    cmax_B,
    cmax_temp,  # pre-computed (replaces table_x/table_y — avoids variable-length arrays in parallel loop)
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
    # Survival params
    mort_ht_T1,
    mort_ht_T9,
    mort_cond_S5,
    mort_cond_S8,
    mort_cond_Kcrit,
    fp_min,
    fp_L1,
    fp_L9,
    fp_D1,
    fp_D9,
    fp_P1,
    fp_P9,
    fp_I1,
    fp_I9,
    fp_T1,
    fp_T9,
    fp_hf,
    tp_min,
    tp_L1,
    tp_L9,
    tp_D1,
    tp_D9,
    tp_V1,
    tp_V9,
    tp_I1,
    tp_I9,
    tp_H1,
    tp_H9,
    tp_hf,
    strand_surv,
):
    """Evaluate all candidate cells x 3 activities for one fish.

    Accepts a pre-computed cmax_temp scalar to avoid passing variable-length
    lookup tables into the batch parallel loop.
    Returns (best_cell, best_activity, best_fitness, best_growth, best_non_starve).
    best_non_starve is the survival product (non_starve * s_cond) at the
    chosen cell/activity, needed by Arc D expected-fitness comparator.
    """
    n_cand = candidate_indices.shape[0]
    best_cell = candidate_indices[0]
    best_act = 2
    best_fitness = -1e308
    best_growth = 0.0
    best_non_starve = 0.0

    # Pre-compute fish-level invariants
    cmax_wt = cmax_A * fish_weight**cmax_B
    cstepmax = (
        max(0.0, (cmax_wt * cmax_temp - prev_consumption) / step_length)
        if step_length > 0.0
        else 0.0
    )
    max_spd = (max_speed_A * fish_length + max_speed_B) * max_swim_temp_term
    resp_std = resp_A * fish_weight**resp_B
    detect_base = react_dist_A + react_dist_B * fish_length

    s_ht = _logistic(temperature, mort_ht_T1, mort_ht_T9)
    fp_temp = _logistic(temperature, fp_T1, fp_T9)

    s_cond_val = 0.0
    if fish_condition <= 0.0:
        s_cond_val = 0.0
    elif fish_condition >= 1.0:
        s_cond_val = 1.0
    elif fish_condition > mort_cond_Kcrit:
        denom_c = 1.0 - mort_cond_Kcrit
        if denom_c <= 0.0:
            s_cond_val = 1.0
        else:
            slope_c = (1.0 - mort_cond_S8) / denom_c
            s_cond_val = mort_cond_S8 + slope_c * (fish_condition - mort_cond_Kcrit)
    else:
        denom_c = mort_cond_Kcrit - 0.5
        if denom_c <= 0.0:
            s_cond_val = mort_cond_S8
        else:
            slope_c = (mort_cond_S8 - mort_cond_S5) / denom_c
            s_cond_val = fish_condition * slope_c + (mort_cond_S5 - 0.5 * slope_c)
    s_cond_val = max(0.0, min(1.0, s_cond_val))

    fp_L = _logistic(fish_length, fp_L1, fp_L9)
    tp_L = _logistic(fish_length, tp_L1, tp_L9)

    if turbidity <= turbid_threshold:
        turbid_func = 1.0
    else:
        turbid_func = turbid_min + (1.0 - turbid_min) * math.exp(
            turbid_exp * (turbidity - turbid_threshold)
        )

    for ci in range(n_cand):
        c = candidate_indices[ci]
        depth = cell_depths[c]
        vel = cell_velocities[c]
        light = cell_lights[c]
        dist_esc = cell_dist_escape[c]
        a_drift = cell_avail_drift[c]
        a_search = cell_avail_search[c]
        a_shelter = cell_avail_shelter[c]
        a_hiding = cell_avail_hiding[c]
        pisciv_d = cell_pisciv[c]

        s_str = strand_surv if depth <= 0.0 else 1.0

        fp_D = _logistic(depth, fp_D1, fp_D9)
        fp_P = _logistic(pisciv_d, fp_P1, fp_P9)
        fp_I = _logistic(light, fp_I1, fp_I9)

        tp_D = _logistic(depth, tp_D1, tp_D9)
        tp_V = _logistic(vel, tp_V1, tp_V9)
        tp_I = _logistic(light, tp_I1, tp_I9)
        tp_H = _logistic(dist_esc, tp_H1, tp_H9)

        for act in range(3):
            if act == 1 and vel > max_spd:
                continue
            if act == 0:
                d_speed = vel * shelter_speed_frac if a_shelter > fish_length * fish_length else vel
                if d_speed > max_spd:
                    continue

            if act == 0:  # drift
                if depth <= 0.0 or vel <= 0.0:
                    intake = 0.0
                else:
                    dd = detect_base * turbid_func
                    if light >= light_threshold:
                        lf = 1.0
                    else:
                        lf = light_min + (1.0 - light_min) * math.exp(
                            light_exp * (light_threshold - light)
                        )
                    dd *= lf
                    ch = min(depth, dd)
                    ca = 2.0 * dd * ch
                    vr = vel / max_spd if max_spd > 0.0 else 999.0
                    if capture_R9 == capture_R1:
                        cs_val = 0.5
                    else:
                        mid = (capture_R1 + capture_R9) * 0.5
                        slp = _LN81 / (capture_R9 - capture_R1)
                        a = -slp * (vr - mid)
                        if a > 500.0:
                            a = 500.0
                        elif a < -500.0:
                            a = -500.0
                        cs_val = 1.0 / (1.0 + math.exp(a))
                    intake = ca * drift_conc * vel * 86400.0 * cs_val
                    intake = min(intake, cstepmax)
                    intake = min(intake, a_drift / max(superind_rep, 1))
                sw_spd = vel * shelter_speed_frac if a_shelter > fish_length * fish_length else vel
                resp = _respiration(resp_std, resp_temp_term, sw_spd, max_spd, resp_D)
                growth = (intake * prey_energy_density - resp) / fish_energy_density

            elif act == 1:  # search
                if max_spd <= 0.0:
                    intake = 0.0
                else:
                    vr_s = (max_spd - vel) / max_spd
                    if vr_s < 0.0:
                        intake = 0.0
                    else:
                        intake = search_prod * search_area * vr_s
                        intake = min(intake, cstepmax)
                        intake = min(intake, a_search / max(superind_rep, 1))
                resp = _respiration(resp_std, resp_temp_term, vel, max_spd, resp_D)
                growth = (intake * prey_energy_density - resp) / fish_energy_density

            else:  # hide
                resp = _respiration(resp_std, resp_temp_term, 0.0, max_spd, resp_D)
                growth = -resp / fish_energy_density

            is_hiding = act == 2
            hf_fp = fp_hf if is_hiding else 0.0
            fp_risk = (
                (1.0 - fp_L)
                * (1.0 - fp_D)
                * (1.0 - fp_P)
                * (1.0 - fp_I)
                * (1.0 - fp_temp)
                * (1.0 - hf_fp)
            )
            s_fp = fp_min + (1.0 - fp_min) * (1.0 - fp_risk)

            in_hiding = is_hiding and (a_hiding >= superind_rep)
            hf_tp = tp_hf if in_hiding else 0.0
            tp_risk = (
                (1.0 - tp_L)
                * (1.0 - tp_D)
                * (1.0 - tp_V)
                * (1.0 - tp_I)
                * (1.0 - tp_H)
                * (1.0 - hf_tp)
            )
            s_tp = tp_min + (1.0 - tp_min) * (1.0 - tp_risk)

            non_starve = s_ht * s_str * s_fp * s_tp
            fitness = growth * step_length * non_starve * s_cond_val

            if fitness > best_fitness:
                best_fitness = fitness
                best_cell = c
                best_act = act
                best_growth = growth
                best_non_starve = non_starve * s_cond_val

    return best_cell, best_act, best_fitness, best_growth, best_non_starve


@numba.njit(cache=True)
def _evaluate_all_cells(
    # Fish scalars
    fish_length,
    fish_weight,
    fish_condition,
    prev_consumption,
    superind_rep,
    # Cell arrays (full mesh, indexed by candidates)
    cell_depths,
    cell_velocities,
    cell_lights,
    cell_dist_escape,
    cell_avail_drift,
    cell_avail_search,
    cell_avail_shelter,
    cell_avail_hiding,
    cell_pisciv,
    # Candidate indices
    candidate_indices,
    # Step-level scalars
    turbidity,
    temperature,
    drift_conc,
    search_prod,
    search_area,
    shelter_speed_frac,
    step_length,
    # Species params
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
    # Survival params
    mort_ht_T1,
    mort_ht_T9,
    mort_cond_S5,
    mort_cond_S8,
    mort_cond_Kcrit,
    fp_min,
    fp_L1,
    fp_L9,
    fp_D1,
    fp_D9,
    fp_P1,
    fp_P9,
    fp_I1,
    fp_I9,
    fp_T1,
    fp_T9,
    fp_hf,
    tp_min,
    tp_L1,
    tp_L9,
    tp_D1,
    tp_D9,
    tp_V1,
    tp_V9,
    tp_I1,
    tp_I9,
    tp_H1,
    tp_H9,
    tp_hf,
    strand_surv,
):
    """Evaluate all candidate cells x 3 activities for one fish.

    Accepts raw cmax lookup tables (table_x/table_y); interpolates temperature
    before delegating to _evaluate_all_cells_v2.
    Returns (best_cell, best_activity, best_fitness, best_growth, best_non_starve).
    """
    cmax_temp = np.interp(temperature, cmax_temp_table_x, cmax_temp_table_y)
    return _evaluate_all_cells_v2(
        fish_length,
        fish_weight,
        fish_condition,
        prev_consumption,
        superind_rep,
        cell_depths,
        cell_velocities,
        cell_lights,
        cell_dist_escape,
        cell_avail_drift,
        cell_avail_search,
        cell_avail_shelter,
        cell_avail_hiding,
        cell_pisciv,
        candidate_indices,
        turbidity,
        temperature,
        drift_conc,
        search_prod,
        search_area,
        shelter_speed_frac,
        step_length,
        cmax_A,
        cmax_B,
        cmax_temp,
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
        mort_ht_T1,
        mort_ht_T9,
        mort_cond_S5,
        mort_cond_S8,
        mort_cond_Kcrit,
        fp_min,
        fp_L1,
        fp_L9,
        fp_D1,
        fp_D9,
        fp_P1,
        fp_P9,
        fp_I1,
        fp_I9,
        fp_T1,
        fp_T9,
        fp_hf,
        tp_min,
        tp_L1,
        tp_L9,
        tp_D1,
        tp_D9,
        tp_V1,
        tp_V9,
        tp_I1,
        tp_I9,
        tp_H1,
        tp_H9,
        tp_hf,
        strand_surv,
    )


@numba.njit(parallel=True, cache=True)
def _pass1_evaluate_parallel(
    fish_lengths,
    fish_weights,
    fish_conditions,
    fish_prev_cons,
    fish_superind_reps,
    cand_offsets,
    cand_indices,
    cell_depths,
    cell_velocities,
    cell_lights,
    cell_dist_escape,
    cell_avail_drift,
    cell_avail_search,
    cell_avail_shelter,
    cell_avail_hiding,
    cell_pisciv,
    p_turbidity,
    p_temperature,
    p_drift_conc,
    p_search_prod,
    p_search_area,
    p_shelter_speed_frac,
    p_cmax_A,
    p_cmax_B,
    p_cmax_temp,
    p_react_dist_A,
    p_react_dist_B,
    p_turbid_threshold,
    p_turbid_min,
    p_turbid_exp,
    p_light_threshold,
    p_light_min,
    p_light_exp,
    p_capture_R1,
    p_capture_R9,
    p_max_speed_A,
    p_max_speed_B,
    p_max_swim_temp_term,
    p_resp_A,
    p_resp_B,
    p_resp_D,
    p_resp_temp_term,
    p_prey_energy_density,
    p_fish_energy_density,
    p_mort_ht_T1,
    p_mort_ht_T9,
    p_mort_cond_S5,
    p_mort_cond_S8,
    p_mort_cond_Kcrit,
    p_fp_min,
    p_fp_L1,
    p_fp_L9,
    p_fp_D1,
    p_fp_D9,
    p_fp_P1,
    p_fp_P9,
    p_fp_I1,
    p_fp_I9,
    p_fp_T1,
    p_fp_T9,
    p_fp_hf,
    p_tp_min,
    p_tp_L1,
    p_tp_L9,
    p_tp_D1,
    p_tp_D9,
    p_tp_V1,
    p_tp_V9,
    p_tp_I1,
    p_tp_I9,
    p_tp_H1,
    p_tp_H9,
    p_tp_hf,
    p_strand_surv,
    step_length,
):
    """Pass 1: Evaluate fitness for ALL fish in parallel (no depletion).

    Uses numba.prange to parallelize the outer fish loop. Each fish
    independently finds its best cell/activity/growth using pre-depletion
    resource levels. Returns arrays of (best_cells, best_activities, best_growths).
    """
    n_fish = fish_lengths.shape[0]
    best_cells = np.empty(n_fish, dtype=np.int32)
    best_activities = np.empty(n_fish, dtype=np.int32)
    best_growths = np.empty(n_fish, dtype=np.float64)
    best_non_starves = np.empty(n_fish, dtype=np.float64)

    for fi in numba.prange(n_fish):
        start = cand_offsets[fi]
        end = cand_offsets[fi + 1]
        candidates = cand_indices[start:end]

        bc, ba, _, bg, bns = _evaluate_all_cells_v2(
            fish_lengths[fi],
            fish_weights[fi],
            fish_conditions[fi],
            fish_prev_cons[fi],
            fish_superind_reps[fi],
            cell_depths,
            cell_velocities,
            cell_lights,
            cell_dist_escape,
            cell_avail_drift,
            cell_avail_search,
            cell_avail_shelter,
            cell_avail_hiding,
            cell_pisciv,
            candidates,
            p_turbidity[fi],
            p_temperature[fi],
            p_drift_conc[fi],
            p_search_prod[fi],
            p_search_area[fi],
            p_shelter_speed_frac[fi],
            step_length,
            p_cmax_A[fi],
            p_cmax_B[fi],
            p_cmax_temp[fi],
            p_react_dist_A[fi],
            p_react_dist_B[fi],
            p_turbid_threshold[fi],
            p_turbid_min[fi],
            p_turbid_exp[fi],
            p_light_threshold[fi],
            p_light_min[fi],
            p_light_exp[fi],
            p_capture_R1[fi],
            p_capture_R9[fi],
            p_max_speed_A[fi],
            p_max_speed_B[fi],
            p_max_swim_temp_term[fi],
            p_resp_A[fi],
            p_resp_B[fi],
            p_resp_D[fi],
            p_resp_temp_term[fi],
            p_prey_energy_density[fi],
            p_fish_energy_density[fi],
            p_mort_ht_T1[fi],
            p_mort_ht_T9[fi],
            p_mort_cond_S5[fi],
            p_mort_cond_S8[fi],
            p_mort_cond_Kcrit[fi],
            p_fp_min[fi],
            p_fp_L1[fi],
            p_fp_L9[fi],
            p_fp_D1[fi],
            p_fp_D9[fi],
            p_fp_P1[fi],
            p_fp_P9[fi],
            p_fp_I1[fi],
            p_fp_I9[fi],
            p_fp_T1[fi],
            p_fp_T9[fi],
            p_fp_hf[fi],
            p_tp_min[fi],
            p_tp_L1[fi],
            p_tp_L9[fi],
            p_tp_D1[fi],
            p_tp_D9[fi],
            p_tp_V1[fi],
            p_tp_V9[fi],
            p_tp_I1[fi],
            p_tp_I9[fi],
            p_tp_H1[fi],
            p_tp_H9[fi],
            p_tp_hf[fi],
            p_strand_surv[fi],
        )

        best_cells[fi] = bc
        best_activities[fi] = ba
        best_growths[fi] = bg
        best_non_starves[fi] = bns

    return best_cells, best_activities, best_growths, best_non_starves


@numba.njit(cache=True)
def batch_select_habitat(
    # Fish arrays (n_fish, in dominance order)
    fish_lengths,
    fish_weights,
    fish_conditions,
    fish_prev_cons,
    fish_superind_reps,
    # Candidate CSR (offsets[n_fish+1], flat_indices[total])
    cand_offsets,
    cand_indices,
    # Cell state arrays (n_cells) — MUTABLE for resource depletion
    cell_depths,
    cell_velocities,
    cell_lights,
    cell_dist_escape,
    cell_avail_drift,
    cell_avail_search,
    cell_avail_shelter,
    cell_avail_hiding,
    cell_pisciv,
    # Per-fish params (n_fish) — pre-indexed by species/reach in Python
    p_turbidity,
    p_temperature,
    p_drift_conc,
    p_search_prod,
    p_search_area,
    p_shelter_speed_frac,
    p_cmax_A,
    p_cmax_B,
    p_cmax_temp,
    p_react_dist_A,
    p_react_dist_B,
    p_turbid_threshold,
    p_turbid_min,
    p_turbid_exp,
    p_light_threshold,
    p_light_min,
    p_light_exp,
    p_capture_R1,
    p_capture_R9,
    p_max_speed_A,
    p_max_speed_B,
    p_max_swim_temp_term,
    p_resp_A,
    p_resp_B,
    p_resp_D,
    p_resp_temp_term,
    p_prey_energy_density,
    p_fish_energy_density,
    p_mort_ht_T1,
    p_mort_ht_T9,
    p_mort_cond_S5,
    p_mort_cond_S8,
    p_mort_cond_Kcrit,
    p_fp_min,
    p_fp_L1,
    p_fp_L9,
    p_fp_D1,
    p_fp_D9,
    p_fp_P1,
    p_fp_P9,
    p_fp_I1,
    p_fp_I9,
    p_fp_T1,
    p_fp_T9,
    p_fp_hf,
    p_tp_min,
    p_tp_L1,
    p_tp_L9,
    p_tp_D1,
    p_tp_D9,
    p_tp_V1,
    p_tp_V9,
    p_tp_I1,
    p_tp_I9,
    p_tp_H1,
    p_tp_H9,
    p_tp_hf,
    p_strand_surv,
    # Scalar
    step_length,
):
    """Batch habitat selection with two-pass parallelism.

    Pass 1 (PARALLEL): Evaluate fitness for all fish x cells x activities
    independently using numba.prange. No resource depletion — just find each
    fish's best cell/activity/growth.

    Pass 2 (SEQUENTIAL): Iterate fish in dominance order. Deplete resources
    from each fish's chosen cell. Fish keep their Pass-1 choices regardless
    of depletion (matching NetLogo inSTREAM which does not re-evaluate).

    Returns (best_cells, best_activities, best_growths, got_shelter, best_non_starves) arrays of shape (n_fish,).
    best_non_starves is the survival product (non_starve * s_cond) at the chosen
    cell/activity — Arc D uses it to compute per-tick expected habitat fitness.
    """
    n_fish = fish_lengths.shape[0]

    # --- Pass 1: Parallel fitness evaluation (no depletion) ---
    best_cells, best_activities, best_growths, best_non_starves = _pass1_evaluate_parallel(
        fish_lengths,
        fish_weights,
        fish_conditions,
        fish_prev_cons,
        fish_superind_reps,
        cand_offsets,
        cand_indices,
        cell_depths,
        cell_velocities,
        cell_lights,
        cell_dist_escape,
        cell_avail_drift,
        cell_avail_search,
        cell_avail_shelter,
        cell_avail_hiding,
        cell_pisciv,
        p_turbidity,
        p_temperature,
        p_drift_conc,
        p_search_prod,
        p_search_area,
        p_shelter_speed_frac,
        p_cmax_A,
        p_cmax_B,
        p_cmax_temp,
        p_react_dist_A,
        p_react_dist_B,
        p_turbid_threshold,
        p_turbid_min,
        p_turbid_exp,
        p_light_threshold,
        p_light_min,
        p_light_exp,
        p_capture_R1,
        p_capture_R9,
        p_max_speed_A,
        p_max_speed_B,
        p_max_swim_temp_term,
        p_resp_A,
        p_resp_B,
        p_resp_D,
        p_resp_temp_term,
        p_prey_energy_density,
        p_fish_energy_density,
        p_mort_ht_T1,
        p_mort_ht_T9,
        p_mort_cond_S5,
        p_mort_cond_S8,
        p_mort_cond_Kcrit,
        p_fp_min,
        p_fp_L1,
        p_fp_L9,
        p_fp_D1,
        p_fp_D9,
        p_fp_P1,
        p_fp_P9,
        p_fp_I1,
        p_fp_I9,
        p_fp_T1,
        p_fp_T9,
        p_fp_hf,
        p_tp_min,
        p_tp_L1,
        p_tp_L9,
        p_tp_D1,
        p_tp_D9,
        p_tp_V1,
        p_tp_V9,
        p_tp_I1,
        p_tp_I9,
        p_tp_H1,
        p_tp_H9,
        p_tp_hf,
        p_strand_surv,
        step_length,
    )

    # --- Pass 2: Sequential resource depletion in dominance order ---
    got_shelter = np.zeros(n_fish, dtype=np.bool_)

    for fi in range(n_fish):
        bc = best_cells[fi]
        ba = best_activities[fi]
        fl = fish_lengths[fi]
        rep = fish_superind_reps[fi]
        if rep < 1:
            rep = 1

        # Pre-compute cstepmax for depletion
        max_spd = (p_max_speed_A[fi] * fl + p_max_speed_B[fi]) * p_max_swim_temp_term[fi]
        if step_length > 0.0:
            cstepmax = max(
                0.0,
                (
                    p_cmax_A[fi] * fish_weights[fi] ** p_cmax_B[fi] * p_cmax_temp[fi]
                    - fish_prev_cons[fi]
                )
                / step_length,
            )
        else:
            cstepmax = 0.0

        if ba == 0:  # drift feeding
            depth = cell_depths[bc]
            vel = cell_velocities[bc]
            light = cell_lights[bc]
            avail = cell_avail_drift[bc]
            intake = _drift_intake(
                fl, depth, vel, light,
                p_turbidity[fi], p_drift_conc[fi], max_spd, cstepmax,
                avail, rep,
                p_react_dist_A[fi], p_react_dist_B[fi],
                p_turbid_threshold[fi], p_turbid_min[fi], p_turbid_exp[fi],
                p_light_threshold[fi], p_light_min[fi], p_light_exp[fi],
                p_capture_R1[fi], p_capture_R9[fi],
            )
            consumed = min(intake * rep, avail)
            cell_avail_drift[bc] -= consumed
            shelter_needed = fl * fl * rep
            if cell_avail_shelter[bc] >= shelter_needed:
                cell_avail_shelter[bc] -= shelter_needed
                got_shelter[fi] = True

        elif ba == 1:  # search feeding
            vel = cell_velocities[bc]
            avail = cell_avail_search[bc]
            intake = _search_intake(
                vel, max_spd,
                p_search_prod[fi], p_search_area[fi], cstepmax,
                avail, rep,
            )
            consumed = min(intake * rep, avail)
            cell_avail_search[bc] -= consumed

        elif ba == 2:  # hide
            if cell_avail_hiding[bc] >= rep:
                cell_avail_hiding[bc] -= rep

    return best_cells, best_activities, best_growths, got_shelter, best_non_starves
