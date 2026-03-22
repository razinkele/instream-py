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

        # Mean daytime irradiance (simplified daily average)
        solar_constant = 1360.0
        solar_elevation = 90.0 - abs(latitude - float(decl))
        solar_elevation = min(90.0, max(0.0, solar_elevation))
        irradiance = (
            solar_constant
            * jnp.sin(jnp.radians(solar_elevation))
            * light_correction
            * shading
        )
        irradiance = max(0.0, float(irradiance)) * float(day_length)

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

    def growth_rate(self, lengths, weights, temperatures, velocities, depths, **params):
        raise NotImplementedError(
            "JaxBackend.growth_rate not implemented. "
            "Target: jax.vmap over fish array for vectorized bioenergetics."
        )

    def survival(self, lengths, weights, conditions, temperatures, depths, **params):
        raise NotImplementedError(
            "JaxBackend.survival not implemented. "
            "Target: jax.vmap over fish array for vectorized survival."
        )

    def fitness_all(self, trout_arrays, cell_arrays, candidates, **params):
        raise NotImplementedError(
            "JaxBackend.fitness_all not implemented. "
            "Target: jax.vmap over (fish, cells, activities) tensor. "
            "Key challenge: sequential resource depletion. "
            "Options: (a) ignore depletion (approximate), "
            "(b) jax.lax.scan over fish, (c) batch by non-competing groups."
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
