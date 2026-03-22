"""JAX compute backend — GPU-capable vectorization for ensemble runs.

Requires: pip install instream[jax]
"""


class JaxBackend:
    """JAX compute backend with vmap vectorization and GPU support.

    Not yet implemented. Install jax/jaxlib and implement the methods.
    Key advantage: vmap over fish x cells x activities for massive parallelism,
    and vmap over parameter sets for ensemble batch runs.
    """

    def update_hydraulics(self, flow, table_flows, depth_values, vel_values):
        raise NotImplementedError(
            "JaxBackend.update_hydraulics not implemented. "
            "Use NumpyBackend or NumbaBackend, or implement with jnp.interp."
        )

    def compute_light(
        self,
        julian_date,
        latitude,
        light_correction,
        shading,
        light_at_night,
        twilight_angle,
    ):
        raise NotImplementedError("JaxBackend.compute_light not implemented.")

    def compute_cell_light(
        self, depths, irradiance, turbid_coef, turbidity, light_at_night
    ):
        raise NotImplementedError("JaxBackend.compute_cell_light not implemented.")

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
        raise NotImplementedError("JaxBackend.evaluate_logistic not implemented.")

    def interp1d(self, x, table_x, table_y):
        raise NotImplementedError("JaxBackend.interp1d not implemented.")
