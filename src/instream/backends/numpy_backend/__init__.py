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

        depths = np.array([np.interp(flow, table_flows, depth_values[i])
                           for i in range(depth_values.shape[0])])
        vels = np.array([np.interp(flow, table_flows, vel_values[i])
                         for i in range(vel_values.shape[0])])

        # Clamp negative depths to zero; zero velocity where dry
        depths = np.maximum(depths, 0.0)
        vels = np.where(depths > 0.0, vels, 0.0)
        return depths, vels

    def compute_light(self, julian_date, latitude, light_correction, shading,
                      light_at_night, twilight_angle):
        raise NotImplementedError("Phase 2")

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
