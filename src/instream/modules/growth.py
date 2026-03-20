"""Bioenergetics module — CMax, consumption, swim speed, intake, respiration, growth."""
import numpy as np


def cmax_temp_function(temperature, table_x, table_y):
    """CMax temperature multiplier from interpolation table."""
    return float(np.interp(temperature, table_x, table_y))


def c_stepmax(cmax_wt_term, cmax_temp, prev_consumption, step_length):
    """Maximum consumption for current time step (g/d as daily rate).

    cmax_wt_term: cmax_A * weight^cmax_B (pre-computed)
    cmax_temp: temperature multiplier from interpolation table
    prev_consumption: food already consumed earlier this day (g)
    step_length: fraction of day for this time step
    """
    if step_length <= 0.0:
        return 0.0
    c_max_daily = cmax_wt_term * cmax_temp
    c_stepmax_val = (c_max_daily - prev_consumption) / step_length
    return max(0.0, c_stepmax_val)


def max_swim_speed(max_speed_len_term, max_swim_temp_term):
    """Maximum sustainable swimming speed (cm/s).

    max_speed_len_term: A * length + B (pre-computed)
    max_swim_temp_term: C*T² + D*T + E (pre-computed per reach)
    """
    return max_speed_len_term * max_swim_temp_term


def drift_swim_speed(velocity, fish_length, available_shelter, shelter_speed_frac):
    """Actual swimming speed of a drift-feeding fish.

    If velocity shelter is available (shelter area > fish_length²),
    the fish swims at reduced speed.
    """
    if available_shelter > fish_length ** 2:
        return velocity * shelter_speed_frac
    return velocity


def drift_intake(length, depth, velocity, light, turbidity, drift_conc,
                 max_swim_speed, c_stepmax_val, available_drift, superind_rep,
                 react_dist_A, react_dist_B,
                 turbid_threshold, turbid_min, turbid_exp,
                 light_threshold, light_min, light_exp,
                 capture_R1, capture_R9):
    """Daily gross drift feeding intake (g/d).

    Implements NetLogo drift-intake-for (Task 3.5).
    """
    if depth <= 0 or velocity <= 0:
        return 0.0

    # 1. Detection distance
    detect_dist = react_dist_A + react_dist_B * length

    # 2. Turbidity function
    if turbidity <= turbid_threshold:
        turbid_func = 1.0
    else:
        turbid_func = turbid_min + (1 - turbid_min) * np.exp(
            turbid_exp * (turbidity - turbid_threshold))

    # 3. Light function
    if light >= light_threshold:
        light_func = 1.0
    else:
        light_func = light_min + (1 - light_min) * np.exp(
            light_exp * (light_threshold - light))

    # 4. Adjusted detection distance
    detect_dist *= turbid_func * light_func

    # 5. Capture geometry
    capture_height = min(depth, detect_dist)
    capture_area = 2 * detect_dist * capture_height

    # 6. Capture success (logistic: evaluate_logistic("capture-success", ...))
    #    f(R1)=0.9, f(R9)=0.1 → midpoint=(R1+R9)/2, slope=ln(81)/(R9-R1)
    vel_ratio = velocity / max_swim_speed if max_swim_speed > 0 else 999.0
    midpoint = (capture_R1 + capture_R9) / 2.0
    slope = np.log(81.0) / (capture_R9 - capture_R1)
    capture_success = 1.0 / (1.0 + np.exp(-slope * (vel_ratio - midpoint)))

    # 7. Gross intake (g/d)
    gross = capture_area * drift_conc * velocity * 86400.0 * capture_success

    # 8-9. Limit by CStepMax and availability
    gross = min(gross, c_stepmax_val)
    gross = min(gross, available_drift / max(superind_rep, 1))

    return gross


def search_intake(velocity, max_swim_speed, search_prod, search_area,
                  c_stepmax_val, available_search, superind_rep):
    """Daily gross search feeding intake (g/d).

    Implements NetLogo search-intake-for (Task 3.6).
    """
    if max_swim_speed <= 0:
        return 0.0
    vel_ratio = (max_swim_speed - velocity) / max_swim_speed
    if vel_ratio < 0:
        return 0.0
    gross = search_prod * search_area * vel_ratio
    gross = min(gross, c_stepmax_val)
    gross = min(gross, available_search / max(superind_rep, 1))
    return gross


def respiration(resp_std_wt_term, resp_temp_term, swim_speed, max_swim_speed,
                resp_D):
    """Total respiration (J/d).

    Implements NetLogo respiration-for (Task 3.7).
    """
    if max_swim_speed <= 0:
        return 999999.0
    ratio = swim_speed / max_swim_speed
    if ratio > 20:
        return 999999.0
    resp_standard = resp_std_wt_term * resp_temp_term
    resp_activity = np.exp(resp_D * ratio ** 2)
    return resp_standard * resp_activity


def growth_rate_for(activity, length, weight, depth, velocity, light,
                    turbidity, temperature,
                    drift_conc, search_prod, search_area,
                    available_drift, available_search,
                    available_shelter, shelter_speed_frac,
                    superind_rep, prev_consumption, step_length,
                    cmax_A, cmax_B,
                    cmax_temp_table_x, cmax_temp_table_y,
                    react_dist_A, react_dist_B,
                    turbid_threshold, turbid_min, turbid_exp,
                    light_threshold, light_min, light_exp,
                    capture_R1, capture_R9,
                    max_speed_A, max_speed_B, max_swim_temp_term,
                    resp_A, resp_B, resp_D, resp_temp_term,
                    prey_energy_density, fish_energy_density):
    """Compute growth rate (g/d) for a fish at a cell with given activity.

    Implements NetLogo growth-rate-for (Task 3.8).
    """
    # Pre-compute intermediates
    cmax_wt_term = cmax_A * weight ** cmax_B
    cmax_temp = cmax_temp_function(temperature, cmax_temp_table_x, cmax_temp_table_y)
    cstepmax = c_stepmax(cmax_wt_term, cmax_temp, prev_consumption, step_length)
    max_speed_len_term = max_speed_A * length + max_speed_B
    max_speed = max_swim_speed(max_speed_len_term, max_swim_temp_term)
    resp_std_wt_term = resp_A * weight ** resp_B

    if activity == "drift":
        intake = drift_intake(length, depth, velocity, light, turbidity, drift_conc,
                              max_speed, cstepmax, available_drift, superind_rep,
                              react_dist_A, react_dist_B,
                              turbid_threshold, turbid_min, turbid_exp,
                              light_threshold, light_min, light_exp,
                              capture_R1, capture_R9)
        swim_speed = drift_swim_speed(velocity, length, available_shelter,
                                      shelter_speed_frac)
        resp = respiration(resp_std_wt_term, resp_temp_term, swim_speed,
                           max_speed, resp_D)
        net_energy = intake * prey_energy_density - resp
    elif activity == "search":
        intake = search_intake(velocity, max_speed, search_prod, search_area,
                               cstepmax, available_search, superind_rep)
        resp = respiration(resp_std_wt_term, resp_temp_term, velocity,
                           max_speed, resp_D)
        net_energy = intake * prey_energy_density - resp
    elif activity == "hide":
        resp = respiration(resp_std_wt_term, resp_temp_term, 0.0,
                           max_speed, resp_D)
        net_energy = -resp
    else:
        raise ValueError(f"Unknown activity: {activity}")

    return float(net_energy / fish_energy_density)


def weight_from_length_and_condition(length, condition, weight_A, weight_B):
    """Compute weight from length, condition factor, and allometric params."""
    return condition * weight_A * length ** weight_B


def length_for_weight(weight, weight_A, weight_B):
    """Compute length from weight using inverse allometric relationship."""
    if weight <= 0:
        return 0.0
    return (weight / weight_A) ** (1.0 / weight_B)


def apply_growth(weight, length, condition, growth, weight_A, weight_B):
    """Update weight, length, condition from daily growth (Task 3.9).

    Returns (new_weight, new_length, new_condition).
    """
    new_weight = weight + growth
    if new_weight < 0:
        new_weight = 0.0
    healthy_weight = weight_A * length ** weight_B
    if new_weight > healthy_weight:
        new_length = length_for_weight(new_weight, weight_A, weight_B)
        new_condition = 1.0
    else:
        new_length = length  # length never decreases
        new_condition = new_weight / healthy_weight if healthy_weight > 0 else 0.0
    return new_weight, new_length, new_condition


def split_superindividuals(trout_state, max_length):
    """Split superindividuals that exceed length threshold (Task 3.10).

    For each alive fish with superind_rep > 1 and length >= max_length,
    find a dead slot, copy all attributes, and halve the rep count.
    """
    for i in trout_state.alive_indices():
        if trout_state.superind_rep[i] <= 1:
            continue
        if trout_state.length[i] < max_length:
            continue
        new_slot = trout_state.first_dead_slot()
        if new_slot < 0:
            continue  # no room
        # Copy ALL attributes (iterate dataclass fields to never miss new ones)
        import dataclasses
        for f in dataclasses.fields(trout_state):
            if f.name in ('alive', 'superind_rep'):
                continue  # handled separately
            arr = getattr(trout_state, f.name)
            if arr.ndim == 1:
                arr[new_slot] = arr[i]
            else:
                arr[new_slot] = arr[i]  # copies entire row for 2D arrays
        # Split rep (integer division: 10 → 5+5, 7 → 4+3)
        half = trout_state.superind_rep[i] // 2
        trout_state.superind_rep[i] = trout_state.superind_rep[i] - half
        trout_state.superind_rep[new_slot] = half
        trout_state.alive[new_slot] = True
