"""_ModelEnvironmentMixin -- environment update and survival logic for InSTREAMModel."""

import numpy as np

from instream.modules.reach import update_reach_state
from instream.modules.survival import apply_mortality
from instream.state.life_stage import LifeStage


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
            cells = self._reach_cells[r_idx]
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
                # Cache day length for smolt readiness (last reach wins; all
                # reaches share latitude so values are identical)
                self._day_length = _dl

        # Cell light: ALWAYS recompute (depth changes with flow)
        for r_idx, rname in enumerate(self.reach_order):
            reach_cfg = self.config.reaches[rname]
            cells = self._reach_cells[r_idx]
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

        # 6. Resources: full reset on first sub-step, partial repletion otherwise.
        #
        # Arc F (2026-04-20): available_drift previously omitted velocity and
        # drift_regen_distance, producing ~8,640x less drift per cell than
        # NetLogo InSALMO7.3:1088 for typical example_a conditions (velocity
        # 100 cm/s, regen_distance 1000 cm). This starved the natal cohort
        # via cell-level food depletion. Corrected formula:
        #   cell_available_drift = 86400 * area * depth * velocity * drift_conc
        #                         / drift_regen_distance
        # units: (s/day)(cm^2)(cm)(cm/s)(g/cm^3)/(cm) = g/day
        if substep == 0:
            for r_idx, rname in enumerate(self.reach_order):
                rp = self.reach_params[rname]
                cells = self._reach_cells[r_idx]
                regen = max(rp.drift_regen_distance, 1.0)  # avoid /0
                cs.available_drift[cells] = (
                    86400.0
                    * cs.area[cells]
                    * cs.depth[cells]
                    * cs.velocity[cells]
                    * rp.drift_conc
                    / regen
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
                cells = self._reach_cells[r_idx]
                if len(cells) == 0:
                    continue
                alive = self.trout_state.alive_indices()
                drift_cells = set()
                for i in alive:
                    if (
                        self.trout_state.zone_idx[i] == -1
                        and int(self.trout_state.activity[i]) == 0
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
                cells = self._reach_cells[r_idx]
                cs.available_vel_shelter[cells] = (
                    cs.frac_vel_shelter[cells] * cs.area[cells]
                )
            cs.available_hiding_places[:] = self.mesh.num_hiding_places.copy()

    def _do_survival(self, step_length):
        """Evaluate and apply survival / mortality for all alive trout.

        This covers step 9 of the sub-step loop.
        Marine fish (zone_idx >= 0) are excluded — their survival_probs stay 1.0.
        """
        cs = self.fem_space.cell_state
        alive = self.trout_state.alive_indices()

        # Filter to freshwater fish only (zone_idx == -1)
        marine_domain = getattr(self, '_marine_domain', None)
        if marine_domain is not None:
            fw_mask = self.trout_state.zone_idx[alive] == -1
            alive = alive[fw_mask]

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
                sp_mort_condition_K_crit=_spa["mort_condition_K_crit"][sp_idx],
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

        # ED-based starvation mortality (HexSimPy integration)
        # Applied to all alive freshwater fish including fasting stages
        alive_all = self.trout_state.alive_indices()
        marine_domain_s = getattr(self, '_marine_domain', None)
        if marine_domain_s is not None:
            fw_s = self.trout_state.zone_idx[alive_all] == -1
            starvation_alive = alive_all[fw_s]
        else:
            starvation_alive = alive_all
        if len(starvation_alive) > 0:
            from instream.modules.survival import survival_mass_floor
            sp_idx_s = self.trout_state.species_idx[starvation_alive]
            floor_frac = np.array([
                getattr(self.config.species[self.species_order[si]], 'mass_floor_fraction', 0.5)
                for si in sp_idx_s
            ])
            floor_surv = np.array([
                getattr(self.config.species[self.species_order[si]], 'mass_floor_survival', 0.9)
                for si in sp_idx_s
            ])
            w = self.trout_state.weight[starvation_alive]
            mw = self.trout_state.max_lifetime_weight[starvation_alive]
            starv_surv = np.where(
                (mw > 0) & (w < floor_frac * mw),
                floor_surv,
                1.0,
            )
            survival_probs[starvation_alive] *= starv_surv ** step_length

        # v0.20.0/v0.22.0: protect post-spawn-fasting life stages from
        # juvenile-stack mortality. Both RETURNING_ADULT and KELT are
        # fasting on marine fat reserves while in freshwater:
        #   * RETURNING_ADULT: 4-7 month hold between river entry
        #     (Mar-Jun) and spawn (Oct-Nov).
        #   * KELT: short post-spawn out-migration from natal reach
        #     down to the river mouth (days-weeks), during which the
        #     fish doesn't feed and is heading to ocean recondition.
        # Without these filters, ~93% of returners died pre-spawn
        # (v0.20.0 fix) and 100% of kelts died before reaching the
        # river mouth (v0.22.0 fix — see scripts/diagnose_kelt.py
        # output showing zero OCEAN_ADULT presence after 2013).
        # See docs/diagnostics/2026-04-12-kelt-chain-diagnosis.md.
        fasting_mask = (
            (self.trout_state.life_history == int(LifeStage.RETURNING_ADULT))
            | (self.trout_state.life_history == int(LifeStage.KELT))
        )
        survival_probs[fasting_mask] = 1.0

        # Apply stochastic mortality
        apply_mortality(self.trout_state.alive, survival_probs, self.rng)

        return survival_probs

    def _replenish_resources_partial(self, step_length):
        """Partially replenish drift and search food between sub-steps.

        Resources regenerate proportionally to step_length but are capped
        at the full-day maximum so they never exceed the daily reset value.
        """
        cs = self.fem_space.cell_state
        for r_idx, rname in enumerate(self.reach_order):
            rp = self.reach_params[rname]
            cells = self._reach_cells[r_idx]
            if len(cells) == 0:
                continue
            # Partial replenishment (Arc F: match NetLogo InSALMO7.3:1088 formula)
            regen = max(rp.drift_regen_distance, 1.0)
            _daily_drift_max = (
                86400.0
                * cs.area[cells]
                * cs.depth[cells]
                * cs.velocity[cells]
                * rp.drift_conc
                / regen
            )
            cs.available_drift[cells] += _daily_drift_max * step_length
            cs.available_search[cells] += rp.search_prod * cs.area[cells] * step_length
            # Cap at daily maximum
            cs.available_drift[cells] = np.minimum(cs.available_drift[cells], _daily_drift_max)
            max_search = rp.search_prod * cs.area[cells]
            cs.available_search[cells] = np.minimum(
                cs.available_search[cells], max_search
            )

    def _compute_piscivore_density(self):
        """Compute piscivore density (count / area) per cell (per-species threshold).

        v0.28.0: vectorized with numpy (was per-fish Python loop).
        """
        _pisciv_arr = self._sp_arrays["pisciv_length"]
        n_cells = self.fem_space.num_cells
        alive = self.trout_state.alive_indices()
        if len(alive) == 0:
            cs = self.fem_space.cell_state
            return np.zeros(n_cells, dtype=np.float64)
        cells = self.trout_state.cell_idx[alive]
        sp_idx = self.trout_state.species_idx[alive]
        lengths = self.trout_state.length[alive]
        reps = self.trout_state.superind_rep[alive]
        thresholds = _pisciv_arr[sp_idx]
        valid = (cells >= 0) & (cells < n_cells) & (lengths >= thresholds)
        pisciv_count = np.zeros(n_cells, dtype=np.float64)
        np.add.at(pisciv_count, cells[valid], reps[valid])
        cs = self.fem_space.cell_state
        return np.where(cs.area > 0, pisciv_count / cs.area, 0.0)
