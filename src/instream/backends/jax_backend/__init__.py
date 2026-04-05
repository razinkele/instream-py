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
        self, depths, irradiance, turbid_coef, turbidity, light_at_night
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

        Returns
        -------
        light : 1-D ndarray, shape (C,)
            Light intensity at mid-depth for each cell.
        """
        depths = jnp.asarray(depths, dtype=jnp.float64)
        attenuation = turbid_coef * turbidity
        light = irradiance * jnp.exp(-attenuation * depths / 2.0)
        # Dry cells get night light
        light = jnp.where(depths > 0, light, light_at_night)
        return np.asarray(light)

    def growth_rate(
        self,
        activity,
        lengths,
        weights,
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
    ):
        """Vectorized growth rate over arrays of fish using JAX element-wise ops.

        All fish-indexed inputs (activity, lengths, weights, depth, velocity,
        light, available_drift, available_search, available_shelter,
        superind_rep, prev_consumption) are 1-D arrays of shape (N,).
        Scalar environmental inputs (turbidity, temperature, drift_conc,
        search_prod, search_area) and model parameters are broadcast.

        Parameters
        ----------
        activity : array, shape (N,)
            Activity code per fish: 0=drift, 1=search, 2=hide.
        lengths : array, shape (N,)
            Fish fork length (cm).
        weights : array, shape (N,)
            Fish weight (g).
        depth : array, shape (N,)
            Water depth at fish's cell (cm).
        velocity : array, shape (N,)
            Water velocity at fish's cell (cm/s).
        light : array, shape (N,)
            Light at fish's cell mid-depth.
        turbidity : float
            Current turbidity (NTU).
        temperature : float
            Water temperature (C).
        drift_conc : float
            Drift food concentration (g/cm^3).
        search_prod : float
            Search food productivity (g/cm^2/d).
        search_area : float
            Search area per cell (cm^2).
        available_drift, available_search, available_shelter : arrays (N,)
            Per-cell resource availability for each fish.
        shelter_speed_frac : float
            Swimming speed reduction fraction when sheltered.
        superind_rep : array (N,)
            Super-individual representation count.
        prev_consumption : array (N,)
            Food already consumed earlier this day (g).
        step_length : float
            Time-step as fraction of day.
        cmax_A, cmax_B : float
            CMax allometric parameters.
        cmax_temp_table_x, cmax_temp_table_y : 1-D arrays
            CMax temperature interpolation table.
        react_dist_A, react_dist_B : float
            Reactive distance parameters.
        turbid_threshold, turbid_min, turbid_exp : float
            Turbidity function parameters.
        light_threshold, light_min, light_exp : float
            Light function parameters.
        capture_R1, capture_R9 : float
            Capture success logistic parameters.
        max_speed_A, max_speed_B, max_swim_temp_term : float
            Max swim speed parameters.
        resp_A, resp_B, resp_D, resp_temp_term : float
            Respiration parameters.
        prey_energy_density, fish_energy_density : float
            Energy density conversion factors (J/g).

        Returns
        -------
        growth : 1-D ndarray, shape (N,)
            Growth rate in g/d for each fish.
        """
        # Convert all fish-indexed inputs to JAX arrays
        activity = jnp.asarray(activity, dtype=jnp.int32)
        lengths = jnp.asarray(lengths)
        weights = jnp.asarray(weights)
        depth = jnp.asarray(depth)
        velocity = jnp.asarray(velocity)
        light = jnp.asarray(light)
        available_drift = jnp.asarray(available_drift)
        available_search = jnp.asarray(available_search)
        available_shelter = jnp.asarray(available_shelter)
        superind_rep = jnp.asarray(superind_rep)
        prev_consumption = jnp.asarray(prev_consumption)
        cmax_temp_table_x = jnp.asarray(cmax_temp_table_x)
        cmax_temp_table_y = jnp.asarray(cmax_temp_table_y)

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

    def survival(
        self,
        lengths,
        depths,
        velocities,
        light,
        temperatures,
        conditions,
        activities,
        dist_escape,
        available_hiding,
        superind_rep,
        pisciv_density,
        *,
        survival_when_dry=0.5,
        high_temp_T1=28.0,
        high_temp_T9=24.0,
        cond_S_at_K5=0.8,
        cond_S_at_K8=0.992,
        fish_pred_min_surv=0.99,
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
        terr_pred_min_surv=0.99,
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
    ):
        """Vectorized survival probability over arrays of fish using JAX.

        Computes four survival components (high temperature, stranding,
        fish predation, terrestrial predation) and returns their product
        as the combined non-starvation survival probability.

        Condition survival is NOT included here (handled separately in
        fitness calculations via mean_condition_survival).

        All fish-indexed inputs are 1-D arrays of shape (N,).
        Temperature is scalar (per time-step).

        Parameters
        ----------
        lengths : array (N,)
            Fish fork length (cm).
        depths : array (N,)
            Water depth at fish's cell (cm).
        velocities : array (N,)
            Water velocity at fish's cell (cm/s).
        light : array (N,)
            Light level at fish's cell.
        temperatures : float or array
            Water temperature (C). Scalar broadcast or per-fish.
        conditions : array (N,)
            Body condition factor (0..1+).
        activities : array (N,)
            Activity code per fish: 0=drift, 1=search, 2=hide.
        dist_escape : array (N,)
            Distance to nearest escape cover (cm).
        available_hiding : array (N,)
            Hiding places available per fish's cell.
        superind_rep : array (N,)
            Super-individual representation count.
        pisciv_density : array (N,) or float
            Piscivore density at each fish's cell.

        Returns
        -------
        survival : 1-D ndarray, shape (N,)
            Combined daily survival probability per fish.
        """
        lengths = jnp.asarray(lengths)
        depths = jnp.asarray(depths)
        velocities = jnp.asarray(velocities)
        light = jnp.asarray(light)
        temperatures = jnp.asarray(temperatures)
        conditions = jnp.asarray(conditions)
        activities = jnp.asarray(activities, dtype=jnp.int32)
        dist_escape = jnp.asarray(dist_escape)
        available_hiding = jnp.asarray(available_hiding)
        superind_rep = jnp.asarray(superind_rep)
        pisciv_density = jnp.asarray(pisciv_density)

        _ln81 = jnp.log(81.0)

        def _logistic(x, L1, L9):
            midpoint = (L1 + L9) / 2.0
            slope = jnp.where(L9 != L1, _ln81 / (L9 - L1), 0.0)
            return 1.0 / (1.0 + jnp.exp(-slope * (x - midpoint)))

        # 1. High temperature survival
        s_high_temp = _logistic(temperatures, high_temp_T1, high_temp_T9)

        # 2. Stranding survival
        s_stranding = jnp.where(depths <= 0.0, survival_when_dry, 1.0)

        # 3. Fish predation survival
        is_hiding = activities == 2
        fish_hide = jnp.where(is_hiding, fish_pred_hiding_factor, 0.0)
        fish_risk = (
            (1.0 - _logistic(lengths, fish_pred_L1, fish_pred_L9))
            * (1.0 - _logistic(depths, fish_pred_D1, fish_pred_D9))
            * (1.0 - _logistic(pisciv_density, fish_pred_P1, fish_pred_P9))
            * (1.0 - _logistic(light, fish_pred_I1, fish_pred_I9))
            * (1.0 - _logistic(temperatures, fish_pred_T1, fish_pred_T9))
            * (1.0 - fish_hide)
        )
        s_fish_pred = fish_pred_min_surv + (1.0 - fish_pred_min_surv) * (
            1.0 - fish_risk
        )

        # 4. Terrestrial predation survival
        in_hiding = is_hiding & (available_hiding >= superind_rep)
        terr_hide = jnp.where(in_hiding, terr_pred_hiding_factor, 0.0)
        terr_risk = (
            (1.0 - _logistic(lengths, terr_pred_L1, terr_pred_L9))
            * (1.0 - _logistic(depths, terr_pred_D1, terr_pred_D9))
            * (1.0 - _logistic(velocities, terr_pred_V1, terr_pred_V9))
            * (1.0 - _logistic(light, terr_pred_I1, terr_pred_I9))
            * (1.0 - _logistic(dist_escape, terr_pred_H1, terr_pred_H9))
            * (1.0 - terr_hide)
        )
        s_terr_pred = terr_pred_min_surv + (1.0 - terr_pred_min_surv) * (
            1.0 - terr_risk
        )

        # Combined non-starvation survival
        survival = s_high_temp * s_stranding * s_fish_pred * s_terr_pred

        return np.asarray(survival)

    def fitness_all(self, trout_arrays, cell_arrays, candidates, **params):
        raise NotImplementedError(
            "JaxBackend.fitness_all not implemented. "
            "Requires sequential resource depletion which is inherently serial. "
            "Options: (a) ignore depletion for approximate parallel eval, "
            "(b) jax.lax.scan over fish in dominance order, "
            "(c) batch by non-competing cell groups. "
            "Use growth_rate() and survival() as building blocks."
        )

    def deplete_resources(
        self, fish_order, chosen_cells, available_drift, available_search, **params
    ):
        raise NotImplementedError("JaxBackend.deplete_resources not implemented.")

    def spawn_suitability(self, depths, velocities, frac_spawn, **params):
        raise NotImplementedError("JaxBackend.spawn_suitability not implemented.")

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
        midpoint = (L1 + L9) / 2.0
        slope = jnp.log(81.0) / (L9 - L1) if L9 != L1 else 0.0
        return np.asarray(1.0 / (1.0 + jnp.exp(-slope * (x - midpoint))))

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
