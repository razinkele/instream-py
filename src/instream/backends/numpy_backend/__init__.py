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
        if flow <= 0.0:
            n_cells = depth_values.shape[0]
            return np.zeros(n_cells), np.zeros(n_cells)

        # NOTE: np.interp is 1D only, so we loop over cells. This is O(C) Python
        # calls and will be vectorized in the Numba/JAX backends (Phase 1+) using
        # np.searchsorted + manual lerp across all cells simultaneously.
        n_cells = depth_values.shape[0]
        depths = np.empty(n_cells)
        vels = np.empty(n_cells)
        for i in range(n_cells):
            depths[i] = np.interp(flow, table_flows, depth_values[i])
            vels[i] = np.interp(flow, table_flows, vel_values[i])

        # Clamp negative depths to zero; zero velocity where dry
        depths = np.maximum(depths, 0.0)
        vels = np.where(depths > 0.0, vels, 0.0)
        vels = np.maximum(vels, 0.0)
        return depths, vels

    def compute_light(self, julian_date, latitude, light_correction, shading,
                      light_at_night, twilight_angle):
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
            cos_tw = (-np.sin(np.radians(twilight_angle))
                      - np.sin(lat_rad) * np.sin(decl_rad)) / denom
            cos_tw = np.clip(cos_tw, -1.0, 1.0)
            tw_hour_angle = np.degrees(np.arccos(cos_tw))
            twilight_length = (tw_hour_angle - hour_angle) / 360.0
            twilight_length = max(0.0, float(twilight_length))

        # Mean daytime irradiance (simplified daily average)
        # TODO: Phase 3 — replace with daily-integral irradiance from NetLogo
        # calcDayLength/calcDailyMeanSolar. Current formula uses noon elevation
        # approximation which overestimates irradiance (avg elevation < noon).
        # Correct noon elevation: 90 - |latitude - declination|.
        solar_constant = 1360.0
        solar_elevation = 90.0 - abs(latitude - decl)  # noon elevation
        solar_elevation = min(90.0, max(0.0, solar_elevation))
        irradiance = (solar_constant * np.sin(np.radians(solar_elevation))
                      * light_correction * shading)
        irradiance = max(0.0, float(irradiance)) * day_length  # scale by day fraction

        return float(day_length), float(twilight_length), float(irradiance)

    def compute_cell_light(self, depths, irradiance, turbid_coef, turbidity,
                           light_at_night):
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
        light : 1-D array, shape (C,)
            Light intensity at mid-depth for each cell.
        """
        depths = np.asarray(depths, dtype=float)
        attenuation = turbid_coef * turbidity
        light = irradiance * np.exp(-attenuation * depths / 2.0)
        # Dry cells get night light
        light = np.where(depths > 0, light, light_at_night)
        return light

    def growth_rate(self, lengths, weights, temperatures, velocities, depths, **params):
        raise NotImplementedError("Phase 3")

    def survival(self, lengths, weights, conditions, temperatures, depths, **params):
        raise NotImplementedError("Phase 5")

    def fitness_all(self, trout_arrays, cell_arrays, candidates, **params):
        raise NotImplementedError("Phase 4")

    def deplete_resources(self, fish_order, chosen_cells, available_drift,
                          available_search, **params):
        raise NotImplementedError("Phase 4")

    def spawn_suitability(self, depths, velocities, frac_spawn, **params):
        raise NotImplementedError("Phase 6")

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
        x = np.asarray(x, dtype=float)
        midpoint = (L1 + L9) / 2.0
        if L9 == L1:
            return np.full_like(x, 0.5)
        slope = np.log(81.0) / (L9 - L1)
        return 1.0 / (1.0 + np.exp(-slope * (x - midpoint)))

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
