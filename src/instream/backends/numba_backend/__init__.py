"""Numba compute backend — JIT-compiled, CPU multi-threaded."""

import math
import numpy as np
import numba


@numba.njit(cache=True)
def _compute_light(
    julian_date, latitude, light_correction, shading, light_at_night, twilight_angle
):
    """Compute day length, twilight length, and mean daytime irradiance."""
    # Solar declination
    decl = 23.45 * math.sin(math.radians((284.0 + julian_date) * 360.0 / 365.0))
    decl_rad = math.radians(decl)
    lat_rad = math.radians(latitude)

    # Hour angle at sunrise/sunset
    cos_ha = -math.tan(lat_rad) * math.tan(decl_rad)
    if cos_ha < -1.0:
        cos_ha = -1.0
    elif cos_ha > 1.0:
        cos_ha = 1.0
    hour_angle = math.degrees(math.acos(cos_ha))
    day_length = 2.0 * hour_angle / 360.0

    # Twilight hour angle
    denom = math.cos(lat_rad) * math.cos(decl_rad)
    if abs(denom) < 1e-15:
        twilight_length = 0.0
    else:
        cos_tw = (
            -math.sin(math.radians(twilight_angle))
            - math.sin(lat_rad) * math.sin(decl_rad)
        ) / denom
        if cos_tw < -1.0:
            cos_tw = -1.0
        elif cos_tw > 1.0:
            cos_tw = 1.0
        tw_hour_angle = math.degrees(math.acos(cos_tw))
        twilight_length = (tw_hour_angle - hour_angle) / 360.0
        if twilight_length < 0.0:
            twilight_length = 0.0

    # Mean daytime irradiance via daily integral formula
    solar_constant = 1360.0
    ha_rad = math.radians(hour_angle)
    if day_length > 0.0:
        irradiance = (solar_constant / math.pi) * (
            math.sin(lat_rad) * math.sin(decl_rad) * ha_rad
            + math.cos(lat_rad) * math.cos(decl_rad) * math.sin(ha_rad)
        )
        if irradiance < 0.0:
            irradiance = 0.0
        irradiance = irradiance * light_correction * shading
    else:
        irradiance = 0.0

    return day_length, twilight_length, irradiance


@numba.njit(parallel=True, cache=True)
def _compute_cell_light(
    depths, irradiance, turbid_coef, turbidity, light_at_night, turbid_const
):
    """Compute light at mid-depth for all cells (Beer-Lambert)."""
    n = depths.shape[0]
    light = np.empty(n, dtype=np.float64)
    attenuation = turbid_coef * turbidity + turbid_const
    for i in numba.prange(n):
        if depths[i] > 0.0:
            light[i] = irradiance * math.exp(-attenuation * depths[i] / 2.0)
        else:
            light[i] = light_at_night
    return light


@numba.njit(parallel=True, cache=True)
def _update_hydraulics(flow, table_flows, depth_values, vel_values):
    """Interpolate depth and velocity for all cells at given flow.

    Uses np.interp (supported in numba nopython mode since 0.64.0).
    cache=True ensures hard failure if object-mode fallback is attempted.
    """
    n_cells = depth_values.shape[0]
    depths = np.empty(n_cells, dtype=np.float64)
    vels = np.empty(n_cells, dtype=np.float64)
    if flow <= 0.0:
        depths[:] = 0.0
        vels[:] = 0.0
        return depths, vels
    for i in numba.prange(n_cells):
        d = np.interp(flow, table_flows, depth_values[i])
        v = np.interp(flow, table_flows, vel_values[i])
        # Clamp: negative depth → 0, dry cell → zero velocity
        if d < 0.0:
            d = 0.0
        if d == 0.0:
            v = 0.0
        if v < 0.0:
            v = 0.0
        depths[i] = d
        vels[i] = v
    return depths, vels


class NumbaBackend:
    """Numba JIT-compiled compute backend."""

    def update_hydraulics(self, flow, table_flows, depth_values, vel_values):
        return _update_hydraulics(float(flow), table_flows, depth_values, vel_values)

    def compute_light(
        self,
        julian_date,
        latitude,
        light_correction,
        shading,
        light_at_night,
        twilight_angle,
    ):
        return _compute_light(
            float(julian_date),
            float(latitude),
            float(light_correction),
            float(shading),
            float(light_at_night),
            float(twilight_angle),
        )

    def compute_cell_light(
        self,
        depths,
        irradiance,
        turbid_coef,
        turbidity,
        light_at_night,
        turbid_const=0.0,
    ):
        depths = np.asarray(depths, dtype=np.float64)
        return _compute_cell_light(
            depths,
            float(irradiance),
            float(turbid_coef),
            float(turbidity),
            float(light_at_night),
            float(turbid_const),
        )

    def growth_rate(self, lengths, weights, temperatures, velocities, depths, **params):
        """Compute growth rate for each fish (loop-based, delegates to scalar function)."""
        from instream.modules.growth import growth_rate_for

        n = len(lengths)
        result = np.empty(n, dtype=np.float64)
        activities = params["activities"]
        for i in range(n):
            result[i] = growth_rate_for(
                int(activities[i]),
                float(lengths[i]),
                float(weights[i]),
                float(depths[i]),
                float(velocities[i]),
                float(params["lights"][i]),
                float(params["turbidities"][i]),
                float(temperatures[i]),
                float(params["drift_concs"][i]),
                float(params["search_prods"][i]),
                float(params["search_areas"][i]),
                float(params["available_drifts"][i]),
                float(params["available_searches"][i]),
                float(params["available_shelters"][i]),
                float(params["shelter_speed_fracs"][i]),
                int(params["superind_reps"][i]),
                float(params["prev_consumptions"][i]),
                float(params["step_length"]),
                float(params["cmax_As"][i]),
                float(params["cmax_Bs"][i]),
                params["cmax_temp_table_xs"][int(params["species_idxs"][i])],
                params["cmax_temp_table_ys"][int(params["species_idxs"][i])],
                float(params["react_dist_As"][i]),
                float(params["react_dist_Bs"][i]),
                float(params["turbid_thresholds"][i]),
                float(params["turbid_mins"][i]),
                float(params["turbid_exps"][i]),
                float(params["light_thresholds"][i]),
                float(params["light_mins"][i]),
                float(params["light_exps"][i]),
                float(params["capture_R1s"][i]),
                float(params["capture_R9s"][i]),
                float(params["max_speed_As"][i]),
                float(params["max_speed_Bs"][i]),
                float(params["max_swim_temp_terms"][i]),
                float(params["resp_As"][i]),
                float(params["resp_Bs"][i]),
                float(params["resp_Ds"][i]),
                float(params["resp_temp_terms"][i]),
                float(params["prey_energy_densities"][i]),
                float(params["fish_energy_densities"][i]),
            )
        return result

    def survival(self, lengths, weights, conditions, temperatures, depths, **params):
        """Vectorized survival (delegates to NumPy-style vectorized computation)."""
        n = len(lengths)

        # High temperature
        s_ht = self.evaluate_logistic(
            temperatures, params["sp_mort_high_temp_T1"], params["sp_mort_high_temp_T9"]
        )

        # Stranding
        s_str = np.where(depths > 0, 1.0, params["sp_mort_strand_survival_when_dry"])

        # Condition (two-piece linear)
        cond = conditions
        S_at_K5 = params["sp_mort_condition_S_at_K5"]
        S_at_K8 = params["sp_mort_condition_S_at_K8"]
        K_crit = params.get("sp_mort_condition_K_crit", 0.8)
        denom_upper = np.maximum(1.0 - K_crit, 1e-12)
        slope_upper = (1.0 - S_at_K8) / denom_upper
        s_upper = S_at_K8 + slope_upper * (cond - K_crit)
        denom_lower = np.maximum(K_crit - 0.5, 1e-12)
        slope_lower = (S_at_K8 - S_at_K5) / denom_lower
        intercept_lower = S_at_K5 - 0.5 * slope_lower
        s_lower = cond * slope_lower + intercept_lower
        s_cond = np.where(cond > K_crit, s_upper, s_lower)
        s_cond = np.where(cond <= 0.0, 0.0, s_cond)
        s_cond = np.where(cond >= 1.0, 1.0, s_cond)
        s_cond = np.clip(s_cond, 0.0, 1.0)

        # Fish predation
        activities = params["activities"]
        is_hiding = activities == 2
        hide_fp = np.where(is_hiding, params["sp_mort_fish_pred_hiding_factor"], 0.0)
        fp_risk = (
            (
                1.0
                - self.evaluate_logistic(
                    lengths,
                    params["sp_mort_fish_pred_L1"],
                    params["sp_mort_fish_pred_L9"],
                )
            )
            * (
                1.0
                - self.evaluate_logistic(
                    depths,
                    params["sp_mort_fish_pred_D1"],
                    params["sp_mort_fish_pred_D9"],
                )
            )
            * (
                1.0
                - self.evaluate_logistic(
                    params["pisciv_densities"],
                    params["sp_mort_fish_pred_P1"],
                    params["sp_mort_fish_pred_P9"],
                )
            )
            * (
                1.0
                - self.evaluate_logistic(
                    params["lights"],
                    params["sp_mort_fish_pred_I1"],
                    params["sp_mort_fish_pred_I9"],
                )
            )
            * (
                1.0
                - self.evaluate_logistic(
                    temperatures,
                    params["sp_mort_fish_pred_T1"],
                    params["sp_mort_fish_pred_T9"],
                )
            )
            * (1.0 - hide_fp)
        )
        fp_min = params["rp_fish_pred_min"]
        s_fp = fp_min + (1.0 - fp_min) * (1.0 - fp_risk)

        # Terrestrial predation
        avail_hide = params["available_hidings"]
        sreps = params["superind_reps"]
        in_hiding = is_hiding & (avail_hide >= sreps)
        hide_tp = np.where(in_hiding, params["sp_mort_terr_pred_hiding_factor"], 0.0)
        tp_risk = (
            (
                1.0
                - self.evaluate_logistic(
                    lengths,
                    params["sp_mort_terr_pred_L1"],
                    params["sp_mort_terr_pred_L9"],
                )
            )
            * (
                1.0
                - self.evaluate_logistic(
                    depths,
                    params["sp_mort_terr_pred_D1"],
                    params["sp_mort_terr_pred_D9"],
                )
            )
            * (
                1.0
                - self.evaluate_logistic(
                    params["velocities"],
                    params["sp_mort_terr_pred_V1"],
                    params["sp_mort_terr_pred_V9"],
                )
            )
            * (
                1.0
                - self.evaluate_logistic(
                    params["lights"],
                    params["sp_mort_terr_pred_I1"],
                    params["sp_mort_terr_pred_I9"],
                )
            )
            * (
                1.0
                - self.evaluate_logistic(
                    params["dist_escapes"],
                    params["sp_mort_terr_pred_H1"],
                    params["sp_mort_terr_pred_H9"],
                )
            )
            * (1.0 - hide_tp)
        )
        tp_min = params["rp_terr_pred_min"]
        s_tp = tp_min + (1.0 - tp_min) * (1.0 - tp_risk)

        return s_ht * s_str * s_cond * s_fp * s_tp

    def deplete_resources(
        self, fish_order, chosen_cells, available_drift, available_search, **params
    ):
        """Sequential resource depletion (order-dependent). Modifies arrays in place."""
        activities = params["chosen_activities"]
        intakes = params["intake_amounts"]
        lengths = params["fish_lengths"]
        reps = params["superind_reps"]
        shelter = params["available_shelter"]
        hiding = params["available_hiding"]
        for idx in fish_order:
            cell = int(chosen_cells[idx])
            act = int(activities[idx])
            rep = int(reps[idx])
            if act == 0:
                consumed = min(float(intakes[idx]) * rep, float(available_drift[cell]))
                available_drift[cell] -= consumed
                shelter_needed = float(lengths[idx]) ** 2 * rep
                if shelter[cell] >= shelter_needed:
                    shelter[cell] -= shelter_needed
            elif act == 1:
                consumed = min(float(intakes[idx]) * rep, float(available_search[cell]))
                available_search[cell] -= consumed
            elif act == 2:
                if hiding[cell] >= rep:
                    hiding[cell] -= rep

    def spawn_suitability(self, depths, velocities, frac_spawn, **params):
        """Compute spawn suitability for all cells (delegates to NumPy)."""
        area = params["area"]
        depth_suit = np.interp(depths, params["depth_table_x"], params["depth_table_y"])
        vel_suit = np.interp(velocities, params["vel_table_x"], params["vel_table_y"])
        return depth_suit * vel_suit * frac_spawn * area

    def evaluate_logistic(self, x, L1, L9):
        """Standard logistic where f(L1)=0.1 and f(L9)=0.9. Supports array inputs."""
        x = np.atleast_1d(np.asarray(x, dtype=np.float64))
        L1 = np.atleast_1d(np.asarray(L1, dtype=np.float64))
        L9 = np.atleast_1d(np.asarray(L9, dtype=np.float64))
        degenerate = np.abs(L1 - L9) < 1e-15
        b = np.where(degenerate, 1.0, np.log(81.0) / (L9 - L1))
        a = -b * (L1 + L9) / 2.0
        result = 1.0 / (1.0 + np.exp(-(a + b * x)))
        result = np.where(degenerate, np.where(x >= L1, 0.9, 0.1), result)
        return result

    def interp1d(self, x, table_x, table_y):
        """Piecewise-linear interpolation (delegates to np.interp)."""
        return np.interp(x, table_x, table_y)
