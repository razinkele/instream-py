"""SalmopyModel -- main simulation model wiring all modules together."""

import numpy as np

import mesa

from salmopy.model_init import _ModelInitMixin
from salmopy.model_environment import _ModelEnvironmentMixin
from salmopy.model_day_boundary import _ModelDayBoundaryMixin
from salmopy.modules.behavior import select_habitat_and_activity


class SalmopyModel(_ModelInitMixin, _ModelEnvironmentMixin, _ModelDayBoundaryMixin, mesa.Model):
    """Main inSTREAM simulation model.

    Parameters
    ----------
    config_path : str or Path
        Path to the YAML configuration file.
    data_dir : str or Path, optional
        Directory containing data files (shapefile, CSVs). Defaults to
        the config file's parent directory.
    end_date_override : str, optional
        Override the end date from config (for short test runs).
    """

    def __init__(
        self, config_path, data_dir=None, end_date_override=None, output_dir=None
    ):
        super().__init__()
        self._build_model(config_path, data_dir, end_date_override, output_dir)

    def step(self):
        """Advance the simulation by one sub-step (or full day if daily).

        Operations are split into two groups:
        A) Every sub-step: hydraulics, light, resources, habitat, survival.
        B) Day boundary only: growth application, spawning, redds, migration,
           census, age increment, memory reset.

        When steps_per_day == 1, substep_index is always 0 and
        is_day_boundary is always True, so every step executes both A and B
        (backward compatible with the original daily loop).
        """
        # ----------------------------------------------------------------
        # A) EVERY SUB-STEP
        # ----------------------------------------------------------------

        # 1. Advance time
        step_length = self.time_manager.advance()
        substep = self.time_manager.substep_index
        is_boundary = self.time_manager.is_day_boundary

        # 2-6. Environment: reach state, hydraulics, light, resources
        self._update_environment(step_length, substep, is_boundary)

        # 7. Habitat selection & activity (per-fish species/reach dispatch)
        pisciv_densities = self._compute_piscivore_density()

        select_habitat_and_activity(
            self.trout_state,
            self.fem_space,
            temperature=self.reach_state.temperature,
            turbidity=self.reach_state.turbidity,
            max_swim_temp_term=self.reach_state.max_swim_temp_term,
            resp_temp_term=self.reach_state.resp_temp_term,
            sp_arrays=self._sp_arrays,
            sp_cmax_table_x=self._sp_cmax_table_x,
            sp_cmax_table_y=self._sp_cmax_table_y,
            rp_arrays=self._rp_arrays,
            step_length=step_length,
            pisciv_densities=pisciv_densities,
            reach_allowed=getattr(self, '_reach_allowed', None),
        )

        # 8. Store growth rate in memory (NOT applied to weight yet)
        #    Skip marine fish (zone_idx >= 0) — they don't use freshwater cells
        alive = self.trout_state.alive_indices()
        marine_domain = getattr(self, '_marine_domain', None)
        if marine_domain is not None:
            fw_mask = self.trout_state.zone_idx[alive] == -1
            freshwater_alive = alive[fw_mask]
        else:
            freshwater_alive = alive
        # v0.26.0 — vectorized growth_memory store (was per-fish Python loop)
        self.trout_state.growth_memory[freshwater_alive, substep] = (
            self.trout_state.last_growth_rate[freshwater_alive]
        )

        # 9. Survival / mortality (vectorized via backend)
        survival_probs = self._do_survival(step_length)

        # v0.26.0 — vectorized fitness memory EMA (was per-fish Python loop)
        alive_after = self.trout_state.alive_indices()
        if marine_domain is not None:
            fw_mask_after = self.trout_state.zone_idx[alive_after] == -1
            fw_alive_after = alive_after[fw_mask_after]
        else:
            fw_alive_after = alive_after
        if len(fw_alive_after) > 0:
            sp_idx = self.trout_state.species_idx[fw_alive_after]
            frac = self._sp_arrays["fitness_memory_frac"]
            alpha_arr = self._sp_arrays["fitness_growth_weight"]
            f = frac[sp_idx]
            alpha = alpha_arr[sp_idx]
            growth_signal = self.trout_state.last_growth_rate[fw_alive_after]
            surv_signal = survival_probs[fw_alive_after]
            current = alpha * growth_signal + (1.0 - alpha) * surv_signal
            old = self.trout_state.fitness_memory[fw_alive_after]
            new_mem = np.where(
                (old == 0.0) & (current != 0.0),
                current,
                f * old + (1.0 - f) * current,
            )
            self.trout_state.fitness_memory[fw_alive_after] = new_mem

        # Marine domain daily step (zone migration, environment update)
        if self._marine_domain is not None:
            self._marine_domain.daily_step(self.time_manager.current_date)

        # ----------------------------------------------------------------
        # B) DAY-BOUNDARY ONLY OPERATIONS
        # ----------------------------------------------------------------
        if is_boundary:
            self._do_day_boundary(step_length)

            # Marine lifecycle: smolt readiness + adult return
            marine_domain = getattr(self, '_marine_domain', None)
            if marine_domain is not None:
                from salmopy.marine.domain import accumulate_smolt_readiness, check_adult_return

                current_date = self.time_manager.current_date
                doy = self.time_manager.julian_date

                # Reset readiness on Jan 1
                if doy == 1:
                    self.trout_state.smolt_readiness[:] = 0.0

                # Smolt readiness accumulation
                alive_idx = self.trout_state.alive_indices()
                if len(alive_idx) > 0:
                    day_length = getattr(self, '_day_length', 0.5)
                    # Max day length at summer solstice (~0.67 for 60N)
                    max_day_length = getattr(self, '_max_day_length', 0.67)
                    # P3.3: vectorized per-fish reach temperature gather with
                    # explicit bounds check. A fish with an invalid
                    # reach_idx (out of range, -1 sentinel) previously got
                    # temps[i]=0.0 via silent fall-through; we now flag
                    # that case explicitly via a debug assertion over alive
                    # PARR fish (the only cohort that actually uses temps
                    # in accumulate_smolt_readiness) and keep the 0.0
                    # fall-back for dead/invalid entries so a stale index
                    # on a non-alive fish can't propagate NaN into the
                    # readiness vector.
                    n_reaches = len(self.reach_state.temperature)
                    reach_idx = self.trout_state.reach_idx
                    valid = (reach_idx >= 0) & (reach_idx < n_reaches)
                    safe_idx = np.where(valid, reach_idx, 0)
                    temps = self.reach_state.temperature[safe_idx].astype(
                        np.float64, copy=True
                    )
                    temps[~valid] = 0.0
                    if __debug__:
                        from salmopy.state import LifeStage as _LS
                        parr_alive_invalid = (
                            (~valid)
                            & self.trout_state.alive
                            & (self.trout_state.life_history == int(_LS.PARR))
                        )
                        assert not np.any(parr_alive_invalid), (
                            "alive PARR trout with invalid reach_idx during "
                            "smolt-readiness accumulation: "
                            f"{np.where(parr_alive_invalid)[0][:10].tolist()}"
                        )
                    accumulate_smolt_readiness(
                        self.trout_state.smolt_readiness,
                        self.trout_state.life_history,
                        self.trout_state.length,
                        day_length,
                        max_day_length,
                        temps,
                        optimal_temp=10.0,
                        doy=doy,
                        min_length=marine_domain.config.smolt_min_length,
                    )

                # Adult return from marine
                cs = self.fem_space.cell_state
                reach_cells = {}
                for r_idx in range(len(self.reach_order)):
                    wet = np.where(
                        (cs.reach_idx == r_idx) & (cs.depth > 0)
                    )[0]
                    if len(wet) > 0:
                        reach_cells[r_idx] = wet
                n_ret, n_repeat = check_adult_return(
                    self.trout_state,
                    reach_cells,
                    return_sea_winters=marine_domain.config.return_min_sea_winters,
                    return_condition_min=0.0,
                    current_date=current_date,
                    rng=self.rng,
                    barrier_map=getattr(self, '_barrier_map', None),
                    reverse_reach_graph=getattr(self, '_reverse_reach_graph', None),
                    estuary_reach=getattr(self, "_estuary_reach_idx", 0),
                    config=marine_domain.config,
                )
                marine_domain.total_returned += n_ret
                marine_domain.total_repeat_spawners += n_repeat

    def run(self):
        """Run the simulation until the end date."""
        while not self.time_manager.is_done():
            self.step()
        self.write_outputs()
