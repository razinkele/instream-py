"""InSTREAMModel -- main simulation model wiring all modules together."""

import numpy as np

import mesa

from instream.model_init import _ModelInitMixin
from instream.model_environment import _ModelEnvironmentMixin
from instream.model_day_boundary import _ModelDayBoundaryMixin
from instream.modules.behavior import select_habitat_and_activity


class InSTREAMModel(_ModelInitMixin, _ModelEnvironmentMixin, _ModelDayBoundaryMixin, mesa.Model):
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
        )

        # 8. Store growth rate in memory (NOT applied to weight yet)
        alive = self.trout_state.alive_indices()
        for i in alive:
            self.trout_state.growth_memory[i, substep] = (
                self.trout_state.last_growth_rate[i]
            )

        # 9. Survival / mortality (vectorized via backend)
        survival_probs = self._do_survival(step_length)

        # Update fitness memory (EMA) using both growth and survival projection
        frac = self._sp_arrays["fitness_memory_frac"]
        alpha_arr = self._sp_arrays["fitness_growth_weight"]
        alive_after = self.trout_state.alive_indices()
        for i in alive_after:
            sp_idx = int(self.trout_state.species_idx[i])
            f = float(frac[sp_idx])
            alpha = float(alpha_arr[sp_idx])
            growth_signal = float(self.trout_state.last_growth_rate[i])
            surv_signal = float(survival_probs[i])
            current = alpha * growth_signal + (1.0 - alpha) * surv_signal
            old = self.trout_state.fitness_memory[i]
            if old == 0.0 and current != 0.0:
                # First real update: seed with current value to avoid day-1 spurious migration
                self.trout_state.fitness_memory[i] = current
            else:
                self.trout_state.fitness_memory[i] = f * old + (1.0 - f) * current

        # ----------------------------------------------------------------
        # B) DAY-BOUNDARY ONLY OPERATIONS
        # ----------------------------------------------------------------
        if is_boundary:
            self._do_day_boundary(step_length)

    def run(self):
        """Run the simulation until the end date."""
        while not self.time_manager.is_done():
            self.step()
        self.write_outputs()
