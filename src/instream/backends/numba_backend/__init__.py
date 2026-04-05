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

    def growth_rate(self, *args, **kwargs):
        raise NotImplementedError("Phase 3")

    def survival(self, *args, **kwargs):
        raise NotImplementedError("Phase 5")

    def fitness_all(self, *args, **kwargs):
        raise NotImplementedError("Phase 4")

    def deplete_resources(self, *args, **kwargs):
        raise NotImplementedError("Phase 4")

    def spawn_suitability(self, *args, **kwargs):
        raise NotImplementedError("Phase 6")

    def evaluate_logistic(self, *args, **kwargs):
        raise NotImplementedError("Phase 4")

    def interp1d(self, x, table_x, table_y):
        """Piecewise-linear interpolation (delegates to np.interp)."""
        return np.interp(x, table_x, table_y)
