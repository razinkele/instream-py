"""Numpy compute backend — reference implementation, no JIT."""

import numpy as np


class NumpyBackend:
    """Pure numpy compute backend. No JIT compilation. Used as reference for correctness."""

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
        depths : 1-D array, shape (C,)
        velocities : 1-D array, shape (C,)
        """
        n_cells = depth_values.shape[0]
        if flow <= 0.0:
            return np.zeros(n_cells), np.zeros(n_cells)

        # Vectorized interpolation using searchsorted + lerp across all cells
        # Clamp to table range (matching np.interp boundary behavior)
        n_flows = len(table_flows)
        if flow <= table_flows[0]:
            depths = depth_values[:, 0].copy()
            vels = vel_values[:, 0].copy()
        elif flow >= table_flows[n_flows - 1]:
            depths = depth_values[:, n_flows - 1].copy()
            vels = vel_values[:, n_flows - 1].copy()
        else:
            idx = np.searchsorted(table_flows, flow, side="right") - 1
            idx = np.clip(idx, 0, n_flows - 2)
            frac = (flow - table_flows[idx]) / (table_flows[idx + 1] - table_flows[idx])
            depths = depth_values[:, idx] + frac * (
                depth_values[:, idx + 1] - depth_values[:, idx]
            )
            vels = vel_values[:, idx] + frac * (
                vel_values[:, idx + 1] - vel_values[:, idx]
            )

        # Clamp negative depths to zero; zero velocity where dry
        depths = np.maximum(depths, 0.0)
        vels = np.where(depths > 0.0, vels, 0.0)
        vels = np.maximum(vels, 0.0)
        return depths, vels

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
        decl = 23.45 * np.sin(np.radians((284 + julian_date) * 360.0 / 365.0))
        decl_rad = np.radians(decl)
        lat_rad = np.radians(latitude)

        # Hour angle at sunrise/sunset
        cos_ha = -np.tan(lat_rad) * np.tan(decl_rad)
        cos_ha = np.clip(cos_ha, -1.0, 1.0)  # handle polar regions
        hour_angle = np.degrees(np.arccos(cos_ha))
        day_length = 2.0 * hour_angle / 360.0  # fraction of day

        # Twilight hour angle
        denom = np.cos(lat_rad) * np.cos(decl_rad)
        if abs(denom) < 1e-15:
            twilight_length = 0.0
        else:
            cos_tw = (
                -np.sin(np.radians(twilight_angle)) - np.sin(lat_rad) * np.sin(decl_rad)
            ) / denom
            cos_tw = np.clip(cos_tw, -1.0, 1.0)
            tw_hour_angle = np.degrees(np.arccos(cos_tw))
            twilight_length = (tw_hour_angle - hour_angle) / 360.0
            twilight_length = max(0.0, float(twilight_length))

        # Mean daytime irradiance via daily integral formula:
        # I = (S0/pi) * (sin(lat)*sin(dec)*H + cos(lat)*cos(dec)*sin(H))
        # where H = hour angle at sunset in radians.
        solar_constant = 1360.0
        ha_rad = np.radians(hour_angle)
        if day_length > 0:
            irradiance = (solar_constant / np.pi) * (
                np.sin(lat_rad) * np.sin(decl_rad) * ha_rad
                + np.cos(lat_rad) * np.cos(decl_rad) * np.sin(ha_rad)
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
        light : 1-D array, shape (C,)
            Light intensity at mid-depth for each cell.
        """
        depths = np.asarray(depths, dtype=float)
        attenuation = turbid_coef * turbidity + turbid_const
        light = irradiance * np.exp(-attenuation * depths / 2.0)
        # Dry cells get night light
        light = np.where(depths > 0, light, light_at_night)
        return light

    def growth_rate(self, lengths, weights, temperatures, velocities, depths, **params):
        raise NotImplementedError("Phase 3")

    def survival(self, lengths, weights, conditions, temperatures, depths, **params):
        """Vectorized survival probability for all alive fish.

        Parameters
        ----------
        lengths : 1-D array (N,) — fish lengths
        weights : 1-D array (N,) — fish weights
        conditions : 1-D array (N,) — body condition factors
        temperatures : 1-D array (N,) — water temperature at each fish's reach
        depths : 1-D array (N,) — water depth at each fish's cell
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
        survival_probs : 1-D array (N,) — combined daily survival probability
        """
        # --- High temperature survival ---
        s_ht = self.evaluate_logistic(
            temperatures,
            params["sp_mort_high_temp_T1"],
            params["sp_mort_high_temp_T9"],
        )

        # --- Stranding survival ---
        s_str = np.where(depths > 0, 1.0, params["sp_mort_strand_survival_when_dry"])

        # --- Condition survival (two-piece linear) ---
        cond = conditions
        S_at_K5 = params["sp_mort_condition_S_at_K5"]
        S_at_K8 = params["sp_mort_condition_S_at_K8"]
        # Upper piece: condition > 0.8
        slope_upper = 5.0 - 5.0 * S_at_K8
        intercept_upper = 5.0 * S_at_K8 - 4.0
        s_upper = cond * slope_upper + intercept_upper
        # Lower piece: condition <= 0.8
        slope_lower = (S_at_K8 - S_at_K5) / 0.3
        intercept_lower = S_at_K5 - 0.5 * slope_lower
        s_lower = cond * slope_lower + intercept_lower
        s_cond = np.where(cond > 0.8, s_upper, s_lower)
        s_cond = np.where(cond <= 0.0, 0.0, s_cond)
        s_cond = np.where(cond >= 1.0, 1.0, s_cond)
        s_cond = np.clip(s_cond, 0.0, 1.0)

        # --- Fish predation survival ---
        activities = params["activities"]
        is_hiding_fish = activities == 2
        hide_factor_fp = np.where(
            is_hiding_fish, params["sp_mort_fish_pred_hiding_factor"], 0.0
        )

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
            * (1.0 - hide_factor_fp)
        )
        fish_pred_min = params["rp_fish_pred_min"]
        s_fp = fish_pred_min + (1.0 - fish_pred_min) * (1.0 - fp_risk)

        # --- Terrestrial predation survival ---
        available_hiding = params["available_hidings"]
        superind_reps = params["superind_reps"]
        is_hiding_terr = is_hiding_fish & (available_hiding >= superind_reps)
        hide_factor_tp = np.where(
            is_hiding_terr, params["sp_mort_terr_pred_hiding_factor"], 0.0
        )

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
            * (1.0 - hide_factor_tp)
        )
        terr_pred_min = params["rp_terr_pred_min"]
        s_tp = terr_pred_min + (1.0 - terr_pred_min) * (1.0 - tp_risk)

        # --- Combined ---
        return s_ht * s_str * s_cond * s_fp * s_tp

    def fitness_all(self, trout_arrays, cell_arrays, candidates, **params):
        raise NotImplementedError("Phase 4")

    def deplete_resources(
        self, fish_order, chosen_cells, available_drift, available_search, **params
    ):
        raise NotImplementedError("Phase 4")

    def spawn_suitability(self, depths, velocities, frac_spawn, **params):
        """Compute spawn suitability scores for all cells.

        Parameters
        ----------
        depths : 1-D array (C,)
        velocities : 1-D array (C,)
        frac_spawn : 1-D array (C,)
        **params : must include area, depth_table_x, depth_table_y, vel_table_x, vel_table_y

        Returns
        -------
        scores : 1-D array (C,)
        """
        area = params["area"]
        depth_suit = np.interp(depths, params["depth_table_x"], params["depth_table_y"])
        vel_suit = np.interp(velocities, params["vel_table_x"], params["vel_table_y"])
        return depth_suit * vel_suit * frac_spawn * area

    def evaluate_logistic(self, x, L1, L9):
        """Standard logistic where f(L1)=0.1 and f(L9)=0.9. Supports array inputs.

        Parameters
        ----------
        x : array-like
            Input values.
        L1 : array-like
            Value(s) where the logistic equals 0.1.
        L9 : array-like
            Value(s) where the logistic equals 0.9.

        Returns
        -------
        result : ndarray, same shape as x (broadcast with L1, L9)
        """
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
        return np.interp(x, table_x, table_y)
