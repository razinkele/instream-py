"""Numba compute backend — JIT-compiled, CPU multi-threaded."""
import numpy as np
import numba


@numba.njit(parallel=True)
def _update_hydraulics(flow, table_flows, depth_values, vel_values):
    """Interpolate depth and velocity for all cells at given flow."""
    n_cells = depth_values.shape[0]
    depths = np.empty(n_cells, dtype=np.float64)
    vels = np.empty(n_cells, dtype=np.float64)
    if flow <= 0.0:
        depths[:] = 0.0
        vels[:] = 0.0
        return depths, vels
    for i in numba.prange(n_cells):
        depths[i] = np.interp(flow, table_flows, depth_values[i])
        vels[i] = np.interp(flow, table_flows, vel_values[i])
    # Clamp negative depths
    for i in numba.prange(n_cells):
        if depths[i] < 0.0:
            depths[i] = 0.0
        if depths[i] == 0.0:
            vels[i] = 0.0
    return depths, vels


class NumbaBackend:
    """Numba JIT-compiled compute backend."""

    def update_hydraulics(self, flow, table_flows, depth_values, vel_values):
        return _update_hydraulics(float(flow), table_flows, depth_values, vel_values)

    def compute_light(self, *args, **kwargs):
        raise NotImplementedError("Phase 2")

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

    def interp1d(self, *args, **kwargs):
        raise NotImplementedError("Phase 3")
