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

    Returns (best_cell, best_activity, best_fitness, best_growth).
    """
    n_cand = candidate_indices.shape[0]
    best_cell = candidate_indices[0]
    best_act = 2
    best_fitness = -1e308
    best_growth = 0.0

    # Pre-compute fish-level invariants
    cmax_wt = cmax_A * fish_weight**cmax_B
    cmax_temp = np.interp(temperature, cmax_temp_table_x, cmax_temp_table_y)
    cstepmax = (
        max(0.0, (cmax_wt * cmax_temp - prev_consumption) / step_length)
        if step_length > 0.0
        else 0.0
    )
    max_spd = (max_speed_A * fish_length + max_speed_B) * max_swim_temp_term
    resp_std = resp_A * fish_weight**resp_B
    detect_base = react_dist_A + react_dist_B * fish_length

    # Pre-compute step-level survival terms
    s_ht = _logistic(temperature, mort_ht_T1, mort_ht_T9)
    fp_temp = _logistic(temperature, fp_T1, fp_T9)

    # Pre-compute fish-level survival terms
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

    # Turbidity function (step-level)
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

        # Stranding survival (per-cell)
        s_str = strand_surv if depth <= 0.0 else 1.0

        # Fish predation cell terms
        fp_D = _logistic(depth, fp_D1, fp_D9)
        fp_P = _logistic(pisciv_d, fp_P1, fp_P9)
        fp_I = _logistic(light, fp_I1, fp_I9)

        # Terrestrial predation cell terms
        tp_D = _logistic(depth, tp_D1, tp_D9)
        tp_V = _logistic(vel, tp_V1, tp_V9)
        tp_I = _logistic(light, tp_I1, tp_I9)
        tp_H = _logistic(dist_esc, tp_H1, tp_H9)

        for act in range(3):
            # Speed check
            if act == 1 and vel > max_spd:
                continue
            if act == 0:
                if a_shelter > fish_length * fish_length:
                    d_speed = vel * shelter_speed_frac
                else:
                    d_speed = vel
                if d_speed > max_spd:
                    continue

            # Growth
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
                if a_shelter > fish_length * fish_length:
                    sw_spd = vel * shelter_speed_frac
                else:
                    sw_spd = vel
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

            # Survival
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

    return best_cell, best_act, best_fitness, best_growth
