"""InSTREAMModel -- main simulation model wiring all modules together."""

import numpy as np
import pandas as pd
from pathlib import Path

import mesa

from instream.io.arrival_reader import compute_daily_arrivals  # noqa: E402
from instream.model_init import _ModelInitMixin
from instream.modules.reach import update_reach_state
from instream.modules.growth import (
    apply_growth,
    split_superindividuals,
)
from instream.modules.survival import (
    apply_mortality,
)
from instream.modules.spawning import (
    ready_to_spawn,
    spawn_suitability,
    select_spawn_cell,
    create_redd,
    apply_superimposition,
    apply_spawner_weight_loss,
    develop_eggs,
    redd_emergence,
)
from instream.modules.survival import apply_redd_survival
from instream.modules.behavior import select_habitat_and_activity
from instream.sync import sync_trout_agents


class InSTREAMModel(_ModelInitMixin, mesa.Model):
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

    def _reset_spawn_season_if_needed(self, spawn_start_doy):
        """Reset spawned_this_season when the spawn season begins.

        Uses a transition check (not exact DOY match) to handle multi-day
        steps or model restarts that might skip the exact start day.
        """
        current_doy = self.time_manager.julian_date
        prev_doy = getattr(self, "_prev_doy", current_doy)
        if prev_doy < spawn_start_doy <= current_doy:
            self.trout_state.spawned_this_season[:] = False
        elif prev_doy > current_doy and current_doy >= spawn_start_doy:
            self.trout_state.spawned_this_season[:] = False
        self._prev_doy = current_doy

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

        # Update fitness memory (EMA)
        frac = self._sp_arrays["fitness_memory_frac"]
        for i in alive:
            sp_idx = int(self.trout_state.species_idx[i])
            f = float(frac[sp_idx])
            current = float(self.trout_state.last_growth_rate[i])
            old = self.trout_state.fitness_memory[i]
            if old == 0.0 and current != 0.0:
                # First real update: seed with current value to avoid day-1 spurious migration
                self.trout_state.fitness_memory[i] = current
            else:
                self.trout_state.fitness_memory[i] = f * old + (1.0 - f) * current

        # 9. Survival / mortality (vectorized via backend)
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

        # ----------------------------------------------------------------
        # B) DAY-BOUNDARY ONLY OPERATIONS
        # ----------------------------------------------------------------
        if is_boundary:
            # Apply habitat restoration events scheduled for today
            self._apply_restoration_events()

            # Harvest
            self._do_harvest()

            # Apply accumulated growth (sum growth_memory across sub-steps)
            self._apply_accumulated_growth()

            # Split superindividuals (per-species max length)
            split_superindividuals(
                self.trout_state, self._sp_arrays["superind_max_length"]
            )

            # Spawning (per-fish species/reach dispatch)
            self._do_spawning(step_length)

            # Post-spawn mortality for anadromous adults (NetLogo behavior)
            alive = self.trout_state.alive_indices()
            for i in alive:
                if (
                    self.trout_state.life_history[i] == 2
                    and self.trout_state.spawned_this_season[i]
                ):
                    self.trout_state.alive[i] = False

            # Redd survival, development, emergence (per-redd species/reach)
            self._do_redd_step(step_length)

            # Migration
            self._do_migration()

            # Increment age on January 1
            self._increment_age_if_new_year()

            # Adult arrivals (stub for multi-reach/species)
            self._do_adult_arrivals()

            # Census data collection
            self._collect_census_if_needed()

            # Sync Mesa agents
            sync_trout_agents(self)

            # Reset memory for next day
            self.trout_state.growth_memory[:] = 0.0
            self.trout_state.consumption_memory[:] = 0.0

    def _apply_restoration_events(self):
        """Apply habitat restoration events scheduled for the current date."""
        current = self.time_manager.current_date
        date_str = current.strftime("%Y-%m-%d")
        cs = self.fem_space.cell_state

        for r_idx, rname in enumerate(self.reach_order):
            reach_cfg = self.config.reaches[rname]
            events = getattr(reach_cfg, "restoration_events", [])
            for event in events:
                if event.get("date") != date_str:
                    continue
                # Determine target cells
                cells_spec = event.get("cells", "all")
                if cells_spec == "all":
                    cells = np.where(cs.reach_idx == r_idx)[0]
                else:
                    cells = np.array(cells_spec, dtype=np.int32)

                # Apply changes
                changes = event.get("changes", {})
                for attr, value in changes.items():
                    if hasattr(cs, attr):
                        getattr(cs, attr)[cells] = value

    def _do_harvest(self):
        """Apply angler harvest if scheduled for today."""
        if not self._harvest_schedule:
            return
        from instream.modules.harvest import compute_harvest

        date_str = self.time_manager.current_date.strftime("%Y-%m-%d")
        num_anglers = self._harvest_schedule.get(date_str, 0.0)
        if num_anglers <= 0:
            return
        # Check season
        cfg = self.config.simulation
        if cfg.harvest_season_start and cfg.harvest_season_end:
            jd = self.time_manager.julian_date
            try:
                from datetime import datetime

                start_jd = (
                    datetime.strptime(cfg.harvest_season_start, "%m-%d")
                    .timetuple()
                    .tm_yday
                )
                end_jd = (
                    datetime.strptime(cfg.harvest_season_end, "%m-%d")
                    .timetuple()
                    .tm_yday
                )
                if not (start_jd <= jd <= end_jd):
                    return
            except ValueError:
                pass
        records = compute_harvest(
            self.trout_state,
            num_anglers,
            cfg.harvest_catch_rate,
            cfg.harvest_min_length,
            cfg.harvest_bag_limit,
            self.rng,
        )
        self._harvest_records.extend(records)

    def _apply_accumulated_growth(self):
        """Sum growth_memory across sub-steps and apply to weight/length/condition."""
        alive = self.trout_state.alive_indices()
        if len(alive) == 0:
            return
        steps = self.steps_per_day
        sl = 1.0 / max(self.steps_per_day, 1)

        _wA = self._sp_arrays["weight_A"]
        _wB = self._sp_arrays["weight_B"]

        # Vectorized: sum growth across sub-steps for all alive fish at once
        total_growth = self.trout_state.growth_memory[alive, :steps].sum(axis=1) * sl

        # Filter out fish with invalid cells
        cell_idx = self.trout_state.cell_idx[alive]
        valid = (cell_idx >= 0) & (cell_idx < self.fem_space.num_cells)
        valid_alive = alive[valid]
        valid_growth = total_growth[valid]

        if len(valid_alive) == 0:
            return

        # Per-fish species weight params
        sp_idx = self.trout_state.species_idx[valid_alive]
        wA = _wA[sp_idx]
        wB = _wB[sp_idx]

        # Apply growth per fish (scalar apply_growth has conditional logic)
        for j in range(len(valid_alive)):
            i = valid_alive[j]
            new_w, new_l, new_k = apply_growth(
                float(self.trout_state.weight[i]),
                float(self.trout_state.length[i]),
                float(self.trout_state.condition[i]),
                float(valid_growth[j]),
                float(wA[j]),
                float(wB[j]),
            )
            self.trout_state.weight[i] = new_w
            self.trout_state.length[i] = new_l
            self.trout_state.condition[i] = new_k

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

    def _do_spawning(self, step_length):
        """Check spawning readiness and create redds (per-fish species/reach)."""
        doy = self.time_manager.julian_date

        # Pre-parse spawn season DOY per species
        spawn_doy_cache = {}
        for sp_name, sp_cfg in self.config.species.items():
            try:
                start_parts = sp_cfg.spawn_start_day.split("-")
                spawn_start_doy = int(
                    pd.Timestamp(
                        "2000-{}-{}".format(start_parts[0], start_parts[1])
                    ).day_of_year
                )
                end_parts = sp_cfg.spawn_end_day.split("-")
                spawn_end_doy = int(
                    pd.Timestamp(
                        "2000-{}-{}".format(end_parts[0], end_parts[1])
                    ).day_of_year
                )
            except (ValueError, IndexError, AttributeError):
                spawn_start_doy = 244  # Sep 1
                spawn_end_doy = 304  # Oct 31
            spawn_doy_cache[sp_name] = (spawn_start_doy, spawn_end_doy)

        # Reset spawn season using earliest start across species
        earliest_start = min(v[0] for v in spawn_doy_cache.values())
        self._reset_spawn_season_if_needed(earliest_start)

        alive = self.trout_state.alive_indices()
        cs = self.fem_space.cell_state

        for i in alive:
            sp_idx = int(self.trout_state.species_idx[i])
            sp_name = self.species_order[sp_idx]
            sp_cfg = self.config.species[sp_name]
            r_idx = int(self.trout_state.reach_idx[i])
            rname = self.reach_order[r_idx]
            rp = self.reach_params[rname]
            temperature = float(self.reach_state.temperature[r_idx])
            flow = float(self.reach_state.flow[r_idx])
            spawn_start_doy, spawn_end_doy = spawn_doy_cache[sp_name]

            depth_xs, depth_ys, vel_xs, vel_ys = self._spawn_tables[sp_name]

            if not ready_to_spawn(
                sex=int(self.trout_state.sex[i]),
                age=int(self.trout_state.age[i]),
                length=float(self.trout_state.length[i]),
                condition=float(self.trout_state.condition[i]),
                temperature=temperature,
                flow=flow,
                spawned_this_season=bool(self.trout_state.spawned_this_season[i]),
                day_of_year=doy,
                spawn_min_age=sp_cfg.spawn_min_age,
                spawn_min_length=sp_cfg.spawn_min_length,
                spawn_min_cond=sp_cfg.spawn_min_cond,
                spawn_min_temp=sp_cfg.spawn_min_temp,
                spawn_max_temp=sp_cfg.spawn_max_temp,
                spawn_prob=sp_cfg.spawn_prob,
                max_spawn_flow=rp.max_spawn_flow,
                spawn_start_doy=spawn_start_doy,
                spawn_end_doy=spawn_end_doy,
                rng=self.rng,
            ):
                continue

            # Find best spawn cell near this fish
            cell = self.trout_state.cell_idx[i]
            if cell < 0:
                continue
            candidates = self.fem_space.cells_in_radius(
                cell, sp_cfg.move_radius_max * 0.1
            )
            if len(candidates) == 0:
                candidates = np.array([cell])

            scores = np.array(
                [
                    spawn_suitability(
                        float(cs.depth[c]),
                        float(cs.velocity[c]),
                        float(cs.frac_spawn[c]),
                        float(cs.area[c]),
                        depth_xs,
                        depth_ys,
                        vel_xs,
                        vel_ys,
                    )
                    for c in candidates
                ]
            )

            if np.max(scores) <= sp_cfg.spawn_suitability_tol:
                continue

            # Gather alive redd positions for defense area check
            alive_redds = self.redd_state.alive
            redd_cells = self.redd_state.cell_idx[alive_redds]
            defense_area = getattr(sp_cfg, "spawn_defense_area", 0.0)

            best_cell = select_spawn_cell(
                scores,
                candidates,
                redd_cells=redd_cells,
                centroids_x=cs.centroid_x,
                centroids_y=cs.centroid_y,
                defense_area=defense_area,
            )
            if best_cell < 0:
                continue  # all candidates excluded by defense area
            reach_idx = int(cs.reach_idx[best_cell])

            new_redd_slot = create_redd(
                self.redd_state,
                species_idx=sp_idx,
                cell_idx=best_cell,
                reach_idx=reach_idx,
                weight=float(self.trout_state.weight[i]),
                fecund_mult=sp_cfg.spawn_fecund_mult,
                fecund_exp=sp_cfg.spawn_fecund_exp,
                egg_viability=sp_cfg.spawn_egg_viability,
            )
            if new_redd_slot >= 0:
                apply_superimposition(
                    self.redd_state,
                    new_redd_slot,
                    float(cs.area[best_cell]),
                )
                new_w = apply_spawner_weight_loss(
                    float(self.trout_state.weight[i]),
                    sp_cfg.spawn_wt_loss_fraction,
                )
                self.trout_state.weight[i] = new_w
                self.trout_state.spawned_this_season[i] = True
                healthy_wt = (
                    sp_cfg.weight_A
                    * float(self.trout_state.length[i]) ** sp_cfg.weight_B
                )
                if healthy_wt > 0:
                    self.trout_state.condition[i] = new_w / healthy_wt

    def _do_redd_step(self, step_length):
        """Redd survival, egg development, and emergence (per-redd species/reach)."""
        cs = self.fem_space.cell_state

        alive_redds = np.where(self.redd_state.alive)[0]
        if len(alive_redds) == 0:
            return

        n_redd_cap = len(self.redd_state.alive)

        # Build per-redd condition arrays from each redd's reach
        redd_temps = np.zeros(n_redd_cap, dtype=np.float64)
        redd_depths = np.zeros(n_redd_cap, dtype=np.float64)
        redd_flows = np.zeros(n_redd_cap, dtype=np.float64)
        redd_peaks = np.zeros(n_redd_cap, dtype=bool)

        for i in alive_redds:
            r_idx = int(self.redd_state.reach_idx[i])
            redd_temps[i] = float(self.reach_state.temperature[r_idx])
            redd_flows[i] = float(self.reach_state.flow[r_idx])
            redd_peaks[i] = bool(self.reach_state.is_flow_peak[r_idx])
            cell = self.redd_state.cell_idx[i]
            if 0 <= cell < self.fem_space.num_cells:
                redd_depths[i] = cs.depth[cell]

        # Apply redd survival per redd (species/reach-specific params)
        # Process each redd individually to use correct species/reach params
        for i in alive_redds:
            sp_idx = int(self.redd_state.species_idx[i])
            sp_name = self.species_order[sp_idx]
            sp_cfg = self.config.species[sp_name]
            r_idx = int(self.redd_state.reach_idx[i])
            rname = self.reach_order[r_idx]
            rp_cfg = self.config.reaches[rname]
            temperature = redd_temps[i]

            # Single-redd survival (wrap in 1-element arrays for apply_redd_survival)
            eggs_arr = np.array([self.redd_state.num_eggs[i]], dtype=np.float64)
            frac_arr = np.array([self.redd_state.frac_developed[i]], dtype=np.float64)
            temp_arr = np.array([temperature], dtype=np.float64)
            depth_arr = np.array([redd_depths[i]], dtype=np.float64)
            flow_arr = np.array([redd_flows[i]], dtype=np.float64)
            peak_arr = np.array([redd_peaks[i]], dtype=bool)

            new_eggs, lo, hi, dw, sc = apply_redd_survival(
                eggs_arr,
                frac_arr,
                temp_arr,
                depth_arr,
                flow_arr,
                peak_arr,
                step_length=step_length,
                lo_T1=sp_cfg.mort_redd_lo_temp_T1,
                lo_T9=sp_cfg.mort_redd_lo_temp_T9,
                hi_T1=sp_cfg.mort_redd_hi_temp_T1,
                hi_T9=sp_cfg.mort_redd_hi_temp_T9,
                dewater_surv=sp_cfg.mort_redd_dewater_surv,
                shear_A=rp_cfg.shear_A,
                shear_B=rp_cfg.shear_B,
                scour_depth=sp_cfg.mort_redd_scour_depth,
            )
            self.redd_state.num_eggs[i] = int(np.round(new_eggs[0]))
            self.redd_state.eggs_lo_temp[i] += int(np.round(lo[0]))
            self.redd_state.eggs_hi_temp[i] += int(np.round(hi[0]))
            self.redd_state.eggs_dewatering[i] += int(np.round(dw[0]))
            self.redd_state.eggs_scour[i] += int(np.round(sc[0]))

            # Develop eggs
            self.redd_state.frac_developed[i] = develop_eggs(
                float(self.redd_state.frac_developed[i]),
                temperature,
                step_length,
                sp_cfg.redd_devel_A,
                sp_cfg.redd_devel_B,
                sp_cfg.redd_devel_C,
            )

        # Kill redds with 0 eggs
        for i in alive_redds:
            if self.redd_state.num_eggs[i] <= 0:
                self.redd_state.alive[i] = False

        # Emergence: per-species emergence params
        # Group redds by species for emergence
        for sp_idx, sp_name in enumerate(self.species_order):
            sp_cfg = self.config.species[sp_name]
            redd_emergence(
                self.redd_state,
                self.trout_state,
                self.rng,
                sp_cfg.emerge_length_min,
                sp_cfg.emerge_length_mode,
                sp_cfg.emerge_length_max,
                sp_cfg.weight_A,
                sp_cfg.weight_B,
                species_index=sp_idx,
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

    def _increment_age_if_new_year(self):
        """Increment fish age by 1 on January 1."""
        if self.time_manager.julian_date == 1:
            alive = self.trout_state.alive_indices()
            self.trout_state.age[alive] += 1

    def _do_migration(self):
        """Evaluate migration fitness and move fish downstream if warranted."""
        from instream.modules.migration import (
            migration_fitness,
            should_migrate,
            migrate_fish_downstream,
        )

        sp_mig_L1 = self._sp_arrays["migrate_fitness_L1"]
        sp_mig_L9 = self._sp_arrays["migrate_fitness_L9"]
        alive = self.trout_state.alive_indices()
        for i in alive:
            lh = int(self.trout_state.life_history[i])
            if lh != 1:
                continue
            sp_idx = int(self.trout_state.species_idx[i])
            mig_fit = migration_fitness(
                float(self.trout_state.length[i]),
                float(sp_mig_L1[sp_idx]),
                float(sp_mig_L9[sp_idx]),
            )
            best_hab = float(self.trout_state.fitness_memory[i])
            if should_migrate(mig_fit, best_hab, lh):
                out = migrate_fish_downstream(self.trout_state, i, self._reach_graph)
                self._outmigrants.extend(out)

    def _collect_census_if_needed(self):
        """Record census data on configured census days."""
        from instream.io.time_manager import is_census

        if not hasattr(self, "_census_records"):
            self._census_records = []
        current_date = self.time_manager._current_date
        # Config census_days use "MM-dd" format; is_census expects "M/d"
        census_days_slash = []
        for spec in self.config.simulation.census_days:
            parts = spec.split("-")
            if len(parts) == 2:
                census_days_slash.append("{}/{}".format(int(parts[0]), int(parts[1])))
            else:
                census_days_slash.append(spec)
        if is_census(
            current_date,
            census_days_slash,
            self.config.simulation.census_years_to_skip,
            pd.Timestamp(self.config.simulation.start_date),
        ):
            alive = self.trout_state.alive_indices()
            self._census_records.append(
                {
                    "date": str(current_date.date()),
                    "num_alive": len(alive),
                    "mean_length": float(np.mean(self.trout_state.length[alive]))
                    if len(alive) > 0
                    else 0.0,
                    "mean_weight": float(np.mean(self.trout_state.weight[alive]))
                    if len(alive) > 0
                    else 0.0,
                    "num_redds": int(self.redd_state.num_alive())
                    if hasattr(self.redd_state, "num_alive")
                    else 0,
                }
            )

    def _do_adult_arrivals(self):
        """Add arriving adults if adult arrival data is configured.

        For each arrival record whose window includes the current date,
        compute the number of adults arriving today using a triangular
        temporal distribution, then allocate them into dead TroutState slots.

        Uses a CDF-based approach with cumulative tracking to avoid
        rounding losses when total arrivals are small relative to the window.
        """
        if not self._arrival_records:
            return

        current_date = self.time_manager._current_date
        sim_year = current_date.year
        ts = self.trout_state
        n_cells = self.fem_space.num_cells

        # Initialize arrival tracking dict on first call
        if not hasattr(self, "_arrival_counts"):
            self._arrival_counts = {}

        # Only process records whose year matches the current sim year
        year_records = [r for r in self._arrival_records if r["year"] == sim_year]
        if not year_records:
            # Fall back: if no exact year match, use the nearest available year
            available_years = sorted(set(r["year"] for r in self._arrival_records))
            if available_years:
                nearest = min(available_years, key=lambda y: abs(y - sim_year))
                year_records = [
                    r for r in self._arrival_records if r["year"] == nearest
                ]

        for idx, rec in enumerate(year_records):
            # Track cumulative arrivals per record per year
            key = (sim_year, idx)
            arrived_so_far = self._arrival_counts.get(key, 0)
            n_today = compute_daily_arrivals(rec, current_date, arrived_so_far)
            if n_today <= 0:
                continue

            # Resolve species index (fall back to 0 if unknown)
            sp_name = rec["species"]
            sp_idx = self._species_name_to_idx.get(sp_name, 0)
            if sp_name in self.config.species:
                sp_cfg = self.config.species[sp_name]
            else:
                sp_cfg = self.config.species[self.species_order[0]]

            # Resolve reach index
            r_name = rec["reach"]
            r_idx = self.reach_order.index(r_name) if r_name in self.reach_order else 0

            # Find dead slots
            dead_slots = np.where(~ts.alive)[0]
            n_add = min(n_today, len(dead_slots))
            if n_add <= 0:
                continue

            slots = dead_slots[:n_add]

            # Generate lengths and weights
            lengths = self.rng.triangular(
                rec["length_min"], rec["length_mode"], rec["length_max"], size=n_add
            )
            weights = sp_cfg.weight_A * lengths**sp_cfg.weight_B

            # Assign sex based on fraction female
            frac_female = rec["frac_female"]
            sex = (self.rng.random(n_add) < frac_female).astype(np.int32)

            # Assign to random cells within the target reach
            reach_cells = np.where(self.fem_space.cell_state.reach_idx == r_idx)[0]
            if len(reach_cells) == 0:
                reach_cells = np.arange(n_cells)
            cell_choices = self.rng.choice(reach_cells, size=n_add)

            # Fill slots
            ts.alive[slots] = True
            ts.species_idx[slots] = sp_idx
            ts.length[slots] = lengths
            ts.weight[slots] = weights
            ts.condition[slots] = 1.0
            ts.age[slots] = 3  # mature adults
            ts.cell_idx[slots] = cell_choices
            ts.reach_idx[slots] = r_idx
            ts.sex[slots] = sex
            ts.superind_rep[slots] = 1
            lh_val = 2 if getattr(sp_cfg, "is_anadromous", False) else 0
            ts.life_history[slots] = lh_val
            ts.in_shelter[slots] = False
            ts.spawned_this_season[slots] = False
            ts.activity[slots] = 0
            ts.growth_memory[slots, :] = 0.0
            ts.consumption_memory[slots, :] = 0.0
            ts.survival_memory[slots, :] = 0.0
            ts.last_growth_rate[slots] = 0.0
            ts.fitness_memory[slots] = 0.0

            # Track cumulative arrivals
            self._arrival_counts[key] = arrived_so_far + n_add

    def write_outputs(self, output_dir=None):
        """Write all output files to the specified directory."""
        out = output_dir or self.output_dir
        if out is None:
            return
        from instream.io.output import (
            write_population_census,
            write_fish_snapshot,
            write_redd_snapshot,
            write_outmigrants,
            write_summary,
        )

        Path(out).mkdir(parents=True, exist_ok=True)
        write_population_census(getattr(self, "_census_records", []), out)
        write_fish_snapshot(
            self.trout_state,
            self.species_order,
            str(self.time_manager._current_date.date()),
            out,
        )
        write_redd_snapshot(
            self.redd_state,
            self.species_order,
            str(self.time_manager._current_date.date()),
            out,
        )
        write_outmigrants(getattr(self, "_outmigrants", []), self.species_order, out)
        write_summary(self, out)

    def run(self):
        """Run the simulation until the end date."""
        while not self.time_manager.is_done():
            self.step()
        self.write_outputs()
