"""_ModelEnvironmentMixin -- environment update and survival logic for InSTREAMModel."""

import numpy as np

from instream.modules.reach import update_reach_state
from instream.modules.survival import apply_mortality


class _ModelEnvironmentMixin:
    """Mixin providing environment update and survival methods."""

    def _update_environment(self, step_length, substep, is_boundary):
        """Update environment: reach state, hydraulics, light, and resources.

        This covers steps 2-6 of the sub-step loop.
        """
        # 2. Get conditions for each reach
        year_override = None
        if self._year_shuffler is not None:
            year_override = self._year_shuffler.get_year(
                self.time_manager.current_date.year
            )
        conditions = {}
        for rname in self.reach_order:
            conditions[rname] = self.time_manager.get_conditions(
                rname, year_override=year_override
            )

        # 3. Update reach state (flow, temp, turbidity, intermediates)
        update_reach_state(
            self.reach_state,
            conditions,
            self.reach_order,
            self.species_params,
            self.backend,
            species_order=self.species_order,
        )

        # Peak flow detection (simple: current > previous)
        for i, rname in enumerate(self.reach_order):
            current_flow = self.reach_state.flow[i]
            self.reach_state.is_flow_peak[i] = current_flow > self._prev_flow[i]
            self._prev_flow[i] = current_flow

        # 4. Update hydraulics per reach (each reach has its own flow & tables)
        cs = self.fem_space.cell_state
        for r_idx, rname in enumerate(self.reach_order):
            flow = float(self.reach_state.flow[r_idx])
            hdata = self._reach_hydraulic_data[rname]
            cells = np.where(cs.reach_idx == r_idx)[0]
            if len(cells) == 0:
                continue
            n_rows = len(hdata["depth_values"])
            if n_rows != len(cells):
                raise ValueError(
                    f"Reach '{rname}': hydraulic table has {n_rows} rows "
                    f"but cell count is {len(cells)} — check that the hydraulic "
                    f"CSV rows match the shapefile cells for this reach"
                )
            depths, vels = self.backend.update_hydraulics(
                flow,
                hdata["depth_flows"],
                hdata["depth_values"],
                hdata["vel_values"],
            )
            cs.depth[cells] = depths
            cs.velocity[cells] = vels

        # 5. Light: solar irradiance computed once per day, cell light every sub-step
        jd = self.time_manager.julian_date
        if substep == 0:
            # Compute solar irradiance once per day
            self._cached_solar = {}
            for r_idx, rname in enumerate(self.reach_order):
                reach_cfg = self.config.reaches[rname]
                _dl, _tl, irr = self.backend.compute_light(
                    jd,
                    self._light_cfg.latitude,
                    self._light_cfg.light_correction,
                    reach_cfg.shading,
                    self._light_cfg.light_at_night,
                    self._light_cfg.twilight_angle,
                )
                self._cached_solar[rname] = irr

        # Cell light: ALWAYS recompute (depth changes with flow)
        for r_idx, rname in enumerate(self.reach_order):
            reach_cfg = self.config.reaches[rname]
            cells = np.where(cs.reach_idx == r_idx)[0]
            if len(cells) == 0:
                continue
            cell_light = self.backend.compute_cell_light(
                cs.depth[cells],
                self._cached_solar[rname],
                reach_cfg.light_turbid_coef,
                float(self.reach_state.turbidity[r_idx]),
                self._light_cfg.light_at_night,
                reach_cfg.light_turbid_const,
            )
            cs.light[cells] = cell_light

        # 6. Resources: full reset on first sub-step, partial repletion otherwise
        if substep == 0:
            for r_idx, rname in enumerate(self.reach_order):
                rp = self.reach_params[rname]
                cells = np.where(cs.reach_idx == r_idx)[0]
                cs.available_drift[cells] = (
                    rp.drift_conc * cs.area[cells] * cs.depth[cells]
                )
                cs.available_search[cells] = rp.search_prod * cs.area[cells]
                cs.available_vel_shelter[cells] = (
                    cs.frac_vel_shelter[cells] * cs.area[cells]
                )
            cs.available_hiding_places[:] = self.mesh.num_hiding_places.copy()

            # Block drift regen for cells near feeding fish
            for r_idx, rname in enumerate(self.reach_order):
                rp = self.reach_params[rname]
                if rp.drift_regen_distance <= 0:
                    continue
                cells = np.where(cs.reach_idx == r_idx)[0]
                if len(cells) == 0:
                    continue
                alive = self.trout_state.alive_indices()
                drift_cells = set()
                for i in alive:
                    if (
                        int(self.trout_state.activity[i]) == 0
                        and int(self.trout_state.reach_idx[i]) == r_idx
                    ):
                        drift_cells.add(int(self.trout_state.cell_idx[i]))
                if not drift_cells:
                    continue
                for oc in drift_cells:
                    dx = cs.centroid_x[cells] - cs.centroid_x[oc]
                    dy = cs.centroid_y[cells] - cs.centroid_y[oc]
                    dist = np.sqrt(dx**2 + dy**2)
                    blocked = (dist <= rp.drift_regen_distance) & (dist > 0)
                    cs.available_drift[cells[blocked]] = 0.0
        else:
            self._replenish_resources_partial(step_length)
            # Vel shelter and hiding places reset fully each sub-step
            for r_idx, rname in enumerate(self.reach_order):
                cells = np.where(cs.reach_idx == r_idx)[0]
                cs.available_vel_shelter[cells] = (
                    cs.frac_vel_shelter[cells] * cs.area[cells]
                )
            cs.available_hiding_places[:] = self.mesh.num_hiding_places.copy()

    def _do_survival(self, step_length):
        """Evaluate and apply survival / mortality for all alive trout.

        This covers step 9 of the sub-step loop.
        """
        cs = self.fem_space.cell_state
        alive = self.trout_state.alive_indices()
        n_capacity = self.trout_state.alive.shape[0]
        survival_probs = np.ones(n_capacity, dtype=np.float64)

        if len(alive) > 0:
            pisciv_densities_surv = self._compute_piscivore_density()

            _spa = self._sp_arrays
            _rpa = self._rp_arrays

            # Gather per-fish arrays by indexing with species_idx and reach_idx
            sp_idx = self.trout_state.species_idx[alive]
            r_idx = self.trout_state.reach_idx[alive]
            cell_idx = self.trout_state.cell_idx[alive]

            # Clamp cell indices to valid range
            valid_cells = np.clip(cell_idx, 0, self.fem_space.num_cells - 1)

            # Per-fish temperatures from reach
            temps = self.reach_state.temperature[r_idx]

            surv = self.backend.survival(
                self.trout_state.length[alive],
                self.trout_state.weight[alive],
                self.trout_state.condition[alive],
                temps,
                cs.depth[valid_cells],
                velocities=cs.velocity[valid_cells],
                lights=cs.light[valid_cells],
                activities=self.trout_state.activity[alive],
                pisciv_densities=pisciv_densities_surv[valid_cells],
                dist_escapes=cs.dist_escape[valid_cells],
                available_hidings=cs.available_hiding_places[valid_cells],
                superind_reps=self.trout_state.superind_rep[alive],
                # Per-species params indexed by sp_idx
                sp_mort_high_temp_T1=_spa["mort_high_temp_T1"][sp_idx],
                sp_mort_high_temp_T9=_spa["mort_high_temp_T9"][sp_idx],
                sp_mort_strand_survival_when_dry=_spa["mort_strand_survival_when_dry"][
                    sp_idx
                ],
                sp_mort_condition_S_at_K5=_spa["mort_condition_S_at_K5"][sp_idx],
                sp_mort_condition_S_at_K8=_spa["mort_condition_S_at_K8"][sp_idx],
                rp_fish_pred_min=_rpa["fish_pred_min"][r_idx],
                sp_mort_fish_pred_L1=_spa["mort_fish_pred_L1"][sp_idx],
                sp_mort_fish_pred_L9=_spa["mort_fish_pred_L9"][sp_idx],
                sp_mort_fish_pred_D1=_spa["mort_fish_pred_D1"][sp_idx],
                sp_mort_fish_pred_D9=_spa["mort_fish_pred_D9"][sp_idx],
                sp_mort_fish_pred_P1=_spa["mort_fish_pred_P1"][sp_idx],
                sp_mort_fish_pred_P9=_spa["mort_fish_pred_P9"][sp_idx],
                sp_mort_fish_pred_I1=_spa["mort_fish_pred_I1"][sp_idx],
                sp_mort_fish_pred_I9=_spa["mort_fish_pred_I9"][sp_idx],
                sp_mort_fish_pred_T1=_spa["mort_fish_pred_T1"][sp_idx],
                sp_mort_fish_pred_T9=_spa["mort_fish_pred_T9"][sp_idx],
                sp_mort_fish_pred_hiding_factor=_spa["mort_fish_pred_hiding_factor"][
                    sp_idx
                ],
                rp_terr_pred_min=_rpa["terr_pred_min"][r_idx],
                sp_mort_terr_pred_L1=_spa["mort_terr_pred_L1"][sp_idx],
                sp_mort_terr_pred_L9=_spa["mort_terr_pred_L9"][sp_idx],
                sp_mort_terr_pred_D1=_spa["mort_terr_pred_D1"][sp_idx],
                sp_mort_terr_pred_D9=_spa["mort_terr_pred_D9"][sp_idx],
                sp_mort_terr_pred_V1=_spa["mort_terr_pred_V1"][sp_idx],
                sp_mort_terr_pred_V9=_spa["mort_terr_pred_V9"][sp_idx],
                sp_mort_terr_pred_I1=_spa["mort_terr_pred_I1"][sp_idx],
                sp_mort_terr_pred_I9=_spa["mort_terr_pred_I9"][sp_idx],
                sp_mort_terr_pred_H1=_spa["mort_terr_pred_H1"][sp_idx],
                sp_mort_terr_pred_H9=_spa["mort_terr_pred_H9"][sp_idx],
                sp_mort_terr_pred_hiding_factor=_spa["mort_terr_pred_hiding_factor"][
                    sp_idx
                ],
            )

            # Skip fish with invalid cells
            valid_mask = (cell_idx >= 0) & (cell_idx < self.fem_space.num_cells)
            surv = np.where(valid_mask, surv, 1.0)

            survival_probs[alive] = surv**step_length

        # Apply stochastic mortality
        apply_mortality(self.trout_state.alive, survival_probs, self.rng)

    def _replenish_resources_partial(self, step_length):
        """Partially replenish drift and search food between sub-steps.

        Resources regenerate proportionally to step_length but are capped
        at the full-day maximum so they never exceed the daily reset value.
        """
        cs = self.fem_space.cell_state
        for r_idx, rname in enumerate(self.reach_order):
            rp = self.reach_params[rname]
            cells = np.where(cs.reach_idx == r_idx)[0]
            if len(cells) == 0:
                continue
            # Partial replenishment
            cs.available_drift[cells] += (
                rp.drift_conc * cs.area[cells] * cs.depth[cells] * step_length
            )
            cs.available_search[cells] += rp.search_prod * cs.area[cells] * step_length
            # Cap at daily maximum
            max_drift = rp.drift_conc * cs.area[cells] * cs.depth[cells]
            cs.available_drift[cells] = np.minimum(cs.available_drift[cells], max_drift)
            max_search = rp.search_prod * cs.area[cells]
            cs.available_search[cells] = np.minimum(
                cs.available_search[cells], max_search
            )

    def _compute_piscivore_density(self):
        """Compute piscivore density (count / area) per cell (per-species threshold)."""
        _pisciv_arr = self._sp_arrays["pisciv_length"]
        n_cells = self.fem_space.num_cells
        pisciv_count = np.zeros(n_cells, dtype=np.float64)
        alive = self.trout_state.alive_indices()
        for i in alive:
            cell = self.trout_state.cell_idx[i]
            sp_idx = int(self.trout_state.species_idx[i])
            pisciv_length = float(_pisciv_arr[sp_idx])
            if 0 <= cell < n_cells and self.trout_state.length[i] >= pisciv_length:
                pisciv_count[cell] += self.trout_state.superind_rep[i]
        cs = self.fem_space.cell_state
        return np.where(cs.area > 0, pisciv_count / cs.area, 0.0)
