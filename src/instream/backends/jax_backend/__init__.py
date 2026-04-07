"""JAX compute backend — GPU-capable vectorization for ensemble runs.

Requires: pip install instream[jax]
"""

import numpy as np
import jax

jax.config.update("jax_enable_x64", True)
import jax.numpy as jnp


class JaxBackend:
    """JAX compute backend with vmap vectorization and GPU support.

    Implements hydraulics, light, logistic, and interpolation using JAX.
    Complex methods (growth, survival, fitness, resources, spawning) are
    left as NotImplementedError pending full vectorization design.
    """

    def update_hydraulics(self, flow, table_flows, depth_values, vel_values):
        """Interpolate depth and velocity for each cell at the given flow.

        Parameters
        ----------
        flow : float
            Current discharge value.
        table_flows : 1-D array, shape (F,)
            Tabulated flow breakpoints (sorted ascending).
        depth_values : 2-D array, shape (C, F)
            Depth at each cell for each tabulated flow.
        vel_values : 2-D array, shape (C, F)
            Velocity at each cell for each tabulated flow.

        Returns
        -------
        depths : 1-D ndarray, shape (C,)
        velocities : 1-D ndarray, shape (C,)
        """
        n_cells = depth_values.shape[0]
        if flow <= 0.0:
            return np.zeros(n_cells), np.zeros(n_cells)

        table_flows = jnp.asarray(table_flows)
        depth_values = jnp.asarray(depth_values)
        vel_values = jnp.asarray(vel_values)

        # Vectorized interp across all cells
        depths = jax.vmap(lambda row: jnp.interp(flow, table_flows, row))(depth_values)
        vels = jax.vmap(lambda row: jnp.interp(flow, table_flows, row))(vel_values)

        # Clamp negative depths to zero; zero velocity where dry
        depths = jnp.maximum(depths, 0.0)
        vels = jnp.where(depths > 0, vels, 0.0)
        vels = jnp.maximum(vels, 0.0)

        return np.asarray(depths), np.asarray(vels)

    def compute_light(
        self,
        julian_date,
        latitude,
        light_correction,
        shading,
        light_at_night,
        twilight_angle,
    ):
        """Compute day length, twilight length, and mean daytime irradiance.

        Parameters
        ----------
        julian_date : int
            Day of year (1-365).
        latitude : float
            Site latitude in degrees.
        light_correction : float
            Multiplicative correction for irradiance.
        shading : float
            Fraction of light reaching water surface (0-1).
        light_at_night : float
            Background light level for night / dry cells.
        twilight_angle : float
            Sun angle below horizon defining twilight (degrees, e.g. 6).

        Returns
        -------
        day_length : float
            Fraction of 24h that is daylight (0-1).
        twilight_length : float
            Morning twilight duration as fraction of day.
        irradiance : float
            Mean daytime irradiance at surface (W/m^2, scaled).
        """
        # Solar declination
        decl = 23.45 * jnp.sin(jnp.radians((284 + julian_date) * 360.0 / 365.0))
        decl_rad = jnp.radians(decl)
        lat_rad = jnp.radians(latitude)

        # Hour angle at sunrise/sunset
        cos_ha = -jnp.tan(lat_rad) * jnp.tan(decl_rad)
        cos_ha = jnp.clip(cos_ha, -1.0, 1.0)
        hour_angle = jnp.degrees(jnp.arccos(cos_ha))
        day_length = 2.0 * hour_angle / 360.0

        # Twilight hour angle
        denom = jnp.cos(lat_rad) * jnp.cos(decl_rad)
        if abs(float(denom)) < 1e-15:
            twilight_length = 0.0
        else:
            cos_tw = (
                -jnp.sin(jnp.radians(twilight_angle))
                - jnp.sin(lat_rad) * jnp.sin(decl_rad)
            ) / denom
            cos_tw = jnp.clip(cos_tw, -1.0, 1.0)
            tw_hour_angle = jnp.degrees(jnp.arccos(cos_tw))
            twilight_length = (tw_hour_angle - hour_angle) / 360.0
            twilight_length = max(0.0, float(twilight_length))

        # Mean daytime irradiance via daily integral formula
        solar_constant = 1360.0
        ha_rad = jnp.radians(hour_angle)
        if float(day_length) > 0:
            irradiance = (solar_constant / jnp.pi) * (
                jnp.sin(lat_rad) * jnp.sin(decl_rad) * ha_rad
                + jnp.cos(lat_rad) * jnp.cos(decl_rad) * jnp.sin(ha_rad)
            )
            irradiance = max(0.0, float(irradiance)) * light_correction * shading
        else:
            irradiance = 0.0

        return float(day_length), float(twilight_length), float(irradiance)

    def compute_cell_light(
        self,
        depths,
        irradiance,
        turbid_coef,
        turbidity,
        light_at_night,
        turbid_const=0.0,
    ):
        """Compute light at mid-depth for each cell using Beer-Lambert law.

        Parameters
        ----------
        depths : 1-D array, shape (C,)
            Water depth at each cell (cm).
        irradiance : float
            Surface irradiance (W/m^2 scaled).
        turbid_coef : float
            Turbidity coefficient for attenuation.
        turbidity : float
            Current turbidity value (NTU).
        light_at_night : float
            Light value assigned to dry cells (depth=0).
        turbid_const : float, optional
            Additive turbidity constant for attenuation (default 0.0).

        Returns
        -------
        light : 1-D ndarray, shape (C,)
            Light intensity at mid-depth for each cell.
        """
        depths = jnp.asarray(depths, dtype=jnp.float64)
        attenuation = turbid_coef * turbidity + turbid_const
        light = irradiance * jnp.exp(-attenuation * depths / 2.0)
        # Dry cells get night light
        light = jnp.where(depths > 0, light, light_at_night)
        return np.asarray(light)

    def growth_rate(self, lengths, weights, temperatures, velocities, depths, **params):
        """Vectorized growth rate over arrays of fish using JAX element-wise ops.

        Signature matches the Protocol and numpy/numba backends exactly.

        Parameters
        ----------
        lengths : 1-D array (N,) -- fish fork length (cm)
        weights : 1-D array (N,) -- fish weight (g)
        temperatures : 1-D array (N,) -- water temperature (C)
        velocities : 1-D array (N,) -- water velocity at fish's cell (cm/s)
        depths : 1-D array (N,) -- water depth at fish's cell (cm)
        **params : per-fish arrays and shared scalars/tables

        Returns
        -------
        growth : 1-D ndarray, shape (N,) -- growth rate in g/d for each fish
        """
        # Extract all parameters from **params (same keys as numpy backend)
        activity = jnp.asarray(params["activities"], dtype=jnp.int32)
        lengths = jnp.asarray(lengths)
        weights = jnp.asarray(weights)
        depth = jnp.asarray(depths)
        velocity = jnp.asarray(velocities)
        light = jnp.asarray(params["lights"])
        turbidity = jnp.asarray(params["turbidities"])
        temperature = jnp.asarray(temperatures, dtype=jnp.float64)
        drift_conc = jnp.asarray(params["drift_concs"])
        search_prod = jnp.asarray(params["search_prods"])
        search_area = jnp.asarray(params["search_areas"])
        available_drift = jnp.asarray(params["available_drifts"])
        available_search = jnp.asarray(params["available_searches"])
        available_shelter = jnp.asarray(params["available_shelters"])
        shelter_speed_frac = jnp.asarray(params["shelter_speed_fracs"])
        superind_rep = jnp.asarray(params["superind_reps"])
        prev_consumption = jnp.asarray(params["prev_consumptions"])
        step_length = params["step_length"]
        cmax_A = jnp.asarray(params["cmax_As"])
        cmax_B = jnp.asarray(params["cmax_Bs"])
        # Known single-species limitation: use first table
        cmax_temp_table_x = jnp.asarray(params["cmax_temp_table_xs"][0])
        cmax_temp_table_y = jnp.asarray(params["cmax_temp_table_ys"][0])
        react_dist_A = jnp.asarray(params["react_dist_As"])
        react_dist_B = jnp.asarray(params["react_dist_Bs"])
        turbid_threshold = jnp.asarray(params["turbid_thresholds"])
        turbid_min = jnp.asarray(params["turbid_mins"])
        turbid_exp = jnp.asarray(params["turbid_exps"])
        light_threshold = jnp.asarray(params["light_thresholds"])
        light_min = jnp.asarray(params["light_mins"])
        light_exp = jnp.asarray(params["light_exps"])
        capture_R1 = jnp.asarray(params["capture_R1s"])
        capture_R9 = jnp.asarray(params["capture_R9s"])
        max_speed_A = jnp.asarray(params["max_speed_As"])
        max_speed_B = jnp.asarray(params["max_speed_Bs"])
        max_swim_temp_term = jnp.asarray(params["max_swim_temp_terms"])
        resp_A = jnp.asarray(params["resp_As"])
        resp_B = jnp.asarray(params["resp_Bs"])
        resp_D = jnp.asarray(params["resp_Ds"])
        resp_temp_term = jnp.asarray(params["resp_temp_terms"])
        prey_energy_density = jnp.asarray(params["prey_energy_densities"])
        fish_energy_density = jnp.asarray(params["fish_energy_densities"])

        # --- CMax ---
        cmax_wt = cmax_A * weights**cmax_B
        cmax_temp = jnp.interp(temperature, cmax_temp_table_x, cmax_temp_table_y)
        c_max_daily = cmax_wt * cmax_temp
        cstepmax = jnp.maximum(
            0.0, (c_max_daily - prev_consumption) / jnp.maximum(step_length, 1e-30)
        )

        # --- Max swim speed ---
        max_speed = (max_speed_A * lengths + max_speed_B) * max_swim_temp_term

        # --- Standard respiration weight term ---
        resp_std = resp_A * weights**resp_B

        # --- Detection distance ---
        detect_dist = react_dist_A + react_dist_B * lengths
        turbid_func = jnp.where(
            turbidity <= turbid_threshold,
            1.0,
            turbid_min
            + (1.0 - turbid_min) * jnp.exp(turbid_exp * (turbidity - turbid_threshold)),
        )
        light_func = jnp.where(
            light >= light_threshold,
            1.0,
            light_min
            + (1.0 - light_min) * jnp.exp(light_exp * (light_threshold - light)),
        )
        detect_dist = detect_dist * turbid_func * light_func

        # --- Capture success (logistic on velocity ratio) ---
        cap_h = jnp.minimum(depth, detect_dist)
        cap_area = 2.0 * detect_dist * cap_h
        vel_ratio = jnp.where(max_speed > 0, velocity / max_speed, 999.0)
        cap_mid = (capture_R1 + capture_R9) / 2.0
        cap_slope = jnp.where(
            capture_R9 != capture_R1,
            jnp.log(81.0) / (capture_R9 - capture_R1),
            0.0,
        )
        cap_success = 1.0 / (1.0 + jnp.exp(-cap_slope * (vel_ratio - cap_mid)))

        # --- Drift intake ---
        d_intake = cap_area * drift_conc * velocity * 86400.0 * cap_success
        d_intake = jnp.minimum(d_intake, cstepmax)
        d_intake = jnp.minimum(d_intake, available_drift / jnp.maximum(superind_rep, 1))
        d_intake = jnp.where((depth > 0) & (velocity > 0), d_intake, 0.0)

        # --- Search intake ---
        search_vel_ratio = jnp.where(
            max_speed > 0, (max_speed - velocity) / max_speed, 0.0
        )
        s_intake = search_prod * search_area * jnp.maximum(search_vel_ratio, 0.0)
        s_intake = jnp.minimum(s_intake, cstepmax)
        s_intake = jnp.minimum(
            s_intake, available_search / jnp.maximum(superind_rep, 1)
        )

        # --- Swim speeds per activity ---
        shelter_ok = available_shelter > lengths**2
        drift_swim = jnp.where(shelter_ok, velocity * shelter_speed_frac, velocity)

        # --- Respiration helper (vectorized) ---
        def _resp(swim_speed):
            ratio = jnp.where(max_speed > 0, swim_speed / max_speed, 20.0)
            ratio = jnp.minimum(ratio, 20.0)
            return resp_std * resp_temp_term * jnp.exp(resp_D * ratio**2)

        # --- Growth per activity ---
        growth_drift = (
            d_intake * prey_energy_density - _resp(drift_swim)
        ) / fish_energy_density
        growth_search = (
            s_intake * prey_energy_density - _resp(velocity)
        ) / fish_energy_density
        growth_hide = -_resp(0.0) / fish_energy_density

        # Select by activity code: 0=drift, 1=search, 2=hide
        growth = jnp.where(
            activity == 0,
            growth_drift,
            jnp.where(activity == 1, growth_search, growth_hide),
        )

        return np.asarray(growth)

    def survival(self, lengths, weights, conditions, temperatures, depths, **params):
        """Vectorized survival probability for all alive fish using JAX.

        Signature matches the Protocol and numpy/numba backends exactly.

        Parameters
        ----------
        lengths : 1-D array (N,) -- fish lengths (cm)
        weights : 1-D array (N,) -- fish weights (g)
        conditions : 1-D array (N,) -- body condition factors
        temperatures : 1-D array (N,) -- water temperature at each fish's reach
        depths : 1-D array (N,) -- water depth at each fish's cell (cm)
        **params : dict containing:
            velocities, lights, activities, pisciv_densities, dist_escapes,
            available_hidings, superind_reps,
            sp_mort_high_temp_T1, sp_mort_high_temp_T9,
            sp_mort_strand_survival_when_dry,
            sp_mort_condition_S_at_K5, sp_mort_condition_S_at_K8,
            rp_fish_pred_min, sp_mort_fish_pred_* (L1/L9/D1/D9/P1/P9/I1/I9/T1/T9/hiding_factor),
            rp_terr_pred_min, sp_mort_terr_pred_* (L1/L9/D1/D9/V1/V9/I1/I9/H1/H9/hiding_factor)

        Returns
        -------
        survival_probs : 1-D ndarray (N,) -- combined daily survival probability
        """
        lengths = jnp.asarray(lengths)
        depths = jnp.asarray(depths)
        temperatures = jnp.asarray(temperatures)
        cond = jnp.asarray(conditions)
        velocities = jnp.asarray(params["velocities"])
        lights = jnp.asarray(params["lights"])
        activities = jnp.asarray(params["activities"], dtype=jnp.int32)
        pisciv_densities = jnp.asarray(params["pisciv_densities"])
        dist_escapes = jnp.asarray(params["dist_escapes"])
        available_hidings = jnp.asarray(params["available_hidings"])
        superind_reps = jnp.asarray(params["superind_reps"])

        def _logistic(x, L1, L9):
            """Standard logistic with degenerate-case step function."""
            x = jnp.asarray(x)
            L1 = jnp.asarray(L1)
            L9 = jnp.asarray(L9)
            degenerate = jnp.abs(L1 - L9) < 1e-15
            b = jnp.where(
                degenerate, 1.0, jnp.log(81.0) / jnp.where(degenerate, 1.0, L9 - L1)
            )
            a = -b * (L1 + L9) / 2.0
            raw = 1.0 / (1.0 + jnp.exp(-(a + b * x)))
            return jnp.where(degenerate, jnp.where(x >= L1, 0.9, 0.1), raw)

        # --- 1. High temperature survival ---
        s_ht = _logistic(
            temperatures,
            params["sp_mort_high_temp_T1"],
            params["sp_mort_high_temp_T9"],
        )

        # --- 2. Stranding survival ---
        s_str = jnp.where(depths > 0, 1.0, params["sp_mort_strand_survival_when_dry"])

        # --- 3. Condition survival (two-piece linear) ---
        S_at_K5 = jnp.asarray(params["sp_mort_condition_S_at_K5"])
        S_at_K8 = jnp.asarray(params["sp_mort_condition_S_at_K8"])
        slope_upper = 5.0 - 5.0 * S_at_K8
        intercept_upper = 5.0 * S_at_K8 - 4.0
        s_upper = cond * slope_upper + intercept_upper
        slope_lower = (S_at_K8 - S_at_K5) / 0.3
        intercept_lower = S_at_K5 - 0.5 * slope_lower
        s_lower = cond * slope_lower + intercept_lower
        s_cond = jnp.where(cond > 0.8, s_upper, s_lower)
        s_cond = jnp.where(cond <= 0.0, 0.0, s_cond)
        s_cond = jnp.where(cond >= 1.0, 1.0, s_cond)
        s_cond = jnp.clip(s_cond, 0.0, 1.0)

        # --- 4. Fish predation survival ---
        is_hiding = activities == 2
        hide_factor_fp = jnp.where(
            is_hiding, params["sp_mort_fish_pred_hiding_factor"], 0.0
        )
        fp_risk = (
            (
                1.0
                - _logistic(
                    lengths,
                    params["sp_mort_fish_pred_L1"],
                    params["sp_mort_fish_pred_L9"],
                )
            )
            * (
                1.0
                - _logistic(
                    depths,
                    params["sp_mort_fish_pred_D1"],
                    params["sp_mort_fish_pred_D9"],
                )
            )
            * (
                1.0
                - _logistic(
                    pisciv_densities,
                    params["sp_mort_fish_pred_P1"],
                    params["sp_mort_fish_pred_P9"],
                )
            )
            * (
                1.0
                - _logistic(
                    lights,
                    params["sp_mort_fish_pred_I1"],
                    params["sp_mort_fish_pred_I9"],
                )
            )
            * (
                1.0
                - _logistic(
                    temperatures,
                    params["sp_mort_fish_pred_T1"],
                    params["sp_mort_fish_pred_T9"],
                )
            )
            * (1.0 - hide_factor_fp)
        )
        fish_pred_min = jnp.asarray(params["rp_fish_pred_min"])
        s_fp = fish_pred_min + (1.0 - fish_pred_min) * (1.0 - fp_risk)

        # --- 5. Terrestrial predation survival ---
        is_hiding_terr = is_hiding & (available_hidings >= superind_reps)
        hide_factor_tp = jnp.where(
            is_hiding_terr, params["sp_mort_terr_pred_hiding_factor"], 0.0
        )
        tp_risk = (
            (
                1.0
                - _logistic(
                    lengths,
                    params["sp_mort_terr_pred_L1"],
                    params["sp_mort_terr_pred_L9"],
                )
            )
            * (
                1.0
                - _logistic(
                    depths,
                    params["sp_mort_terr_pred_D1"],
                    params["sp_mort_terr_pred_D9"],
                )
            )
            * (
                1.0
                - _logistic(
                    velocities,
                    params["sp_mort_terr_pred_V1"],
                    params["sp_mort_terr_pred_V9"],
                )
            )
            * (
                1.0
                - _logistic(
                    lights,
                    params["sp_mort_terr_pred_I1"],
                    params["sp_mort_terr_pred_I9"],
                )
            )
            * (
                1.0
                - _logistic(
                    dist_escapes,
                    params["sp_mort_terr_pred_H1"],
                    params["sp_mort_terr_pred_H9"],
                )
            )
            * (1.0 - hide_factor_tp)
        )
        terr_pred_min = jnp.asarray(params["rp_terr_pred_min"])
        s_tp = terr_pred_min + (1.0 - terr_pred_min) * (1.0 - tp_risk)

        # --- Combined (all 5 components) ---
        return np.asarray(s_ht * s_str * s_cond * s_fp * s_tp)

    def deplete_resources(
        self, fish_order, chosen_cells, available_drift, available_search, **params
    ):
        """Sequential resource depletion (inherently serial, uses NumPy)."""
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
        """Compute spawn suitability for all cells."""
        area = params["area"]
        depth_suit = np.interp(
            np.asarray(depths), params["depth_table_x"], params["depth_table_y"]
        )
        vel_suit = np.interp(
            np.asarray(velocities), params["vel_table_x"], params["vel_table_y"]
        )
        return depth_suit * vel_suit * np.asarray(frac_spawn) * np.asarray(area)

    def evaluate_logistic(self, x, L1, L9):
        """Standard logistic where f(L1)=0.1 and f(L9)=0.9.

        Parameters
        ----------
        x : array-like
            Input values.
        L1 : float
            Value where the logistic equals 0.1.
        L9 : float
            Value where the logistic equals 0.9.

        Returns
        -------
        result : ndarray, same shape as x
        """
        x = jnp.asarray(x)
        L1 = jnp.asarray(L1)
        L9 = jnp.asarray(L9)
        midpoint = (L1 + L9) / 2.0
        degenerate = jnp.abs(L9 - L1) < 1e-15
        slope = jnp.where(
            degenerate, 0.0, jnp.log(81.0) / jnp.where(degenerate, 1.0, L9 - L1)
        )
        raw = 1.0 / (1.0 + jnp.exp(-slope * (x - midpoint)))
        # For degenerate case (L1==L9): step function 0.9 if x >= L1, else 0.1
        result = jnp.where(degenerate, jnp.where(x >= L1, 0.9, 0.1), raw)
        return np.asarray(result)

    def interp1d(self, x, table_x, table_y):
        """Piecewise-linear interpolation with clamping outside range.

        Parameters
        ----------
        x : array-like
            Query points.
        table_x : 1-D array
            Breakpoints (sorted ascending).
        table_y : 1-D array
            Values at breakpoints.

        Returns
        -------
        result : ndarray, same shape as x
        """
        return np.asarray(
            jnp.interp(jnp.asarray(x), jnp.asarray(table_x), jnp.asarray(table_y))
        )
