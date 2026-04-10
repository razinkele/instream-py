"""Day-boundary mixin -- spawning, redds, migration, census, outputs."""

import numpy as np
import pandas as pd
from pathlib import Path

from instream.modules.growth import apply_growth, split_superindividuals
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
from instream.state.life_stage import LifeStage
from instream.sync import sync_trout_agents


class _ModelDayBoundaryMixin:
    """Methods executed once per day at the day boundary."""

    # ------------------------------------------------------------------
    # Wrapper called from step()
    # ------------------------------------------------------------------
    def _do_day_boundary(self, step_length):
        """Execute all day-boundary operations in order."""
        self._apply_restoration_events()
        self._do_harvest()
        self._apply_accumulated_growth()

        split_superindividuals(
            self.trout_state, self._sp_arrays["superind_max_length"]
        )

        self._do_spawning(step_length)

        # Post-spawn mortality for anadromous adults
        alive = self.trout_state.alive_indices()
        for i in alive:
            if (
                self.trout_state.life_history[i] == LifeStage.SPAWNER
                and self.trout_state.spawned_this_season[i]
            ):
                self.trout_state.alive[i] = False

        self._do_redd_step(step_length)
        self._do_migration()
        self._increment_age_if_new_year()
        self._do_adult_arrivals()
        self._collect_census_if_needed()

        sync_trout_agents(self)

        # Reset memory for next day
        self.trout_state.growth_memory[:] = 0.0
        self.trout_state.consumption_memory[:] = 0.0

    # ------------------------------------------------------------------
    # Individual day-boundary methods
    # ------------------------------------------------------------------
    def _reset_spawn_season_if_needed(self, spawn_start_doy):
        """Reset spawned_this_season when the spawn season begins."""
        current_doy = self.time_manager.julian_date
        prev_doy = getattr(self, "_prev_doy", current_doy)
        if prev_doy < spawn_start_doy <= current_doy:
            self.trout_state.spawned_this_season[:] = False
        elif prev_doy > current_doy and current_doy >= spawn_start_doy:
            self.trout_state.spawned_this_season[:] = False
        self._prev_doy = current_doy

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
                cells_spec = event.get("cells", "all")
                if cells_spec == "all":
                    cells = np.where(cs.reach_idx == r_idx)[0]
                else:
                    cells = np.array(cells_spec, dtype=np.int32)

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

        total_growth = self.trout_state.growth_memory[alive, :steps].sum(axis=1) * sl

        cell_idx = self.trout_state.cell_idx[alive]
        valid = (cell_idx >= 0) & (cell_idx < self.fem_space.num_cells)
        valid_alive = alive[valid]
        valid_growth = total_growth[valid]

        if len(valid_alive) == 0:
            return

        sp_idx = self.trout_state.species_idx[valid_alive]
        wA = _wA[sp_idx]
        wB = _wB[sp_idx]

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

    def _do_spawning(self, step_length):
        """Check spawning readiness and create redds (per-fish species/reach)."""
        doy = self.time_manager.julian_date

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
                spawn_start_doy = 244
                spawn_end_doy = 304
            spawn_doy_cache[sp_name] = (spawn_start_doy, spawn_end_doy)

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
                spawn_date_jitter_days=getattr(sp_cfg, "spawn_date_jitter_days", 0),
            ):
                continue

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
                continue
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
                fecundity_noise=getattr(sp_cfg, "fecundity_noise", 0.0),
                rng=self.rng,
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
        """Redd survival, egg development, and emergence."""
        cs = self.fem_space.cell_state

        alive_redds = np.where(self.redd_state.alive)[0]
        if len(alive_redds) == 0:
            return

        n_redd_cap = len(self.redd_state.alive)

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

        for i in alive_redds:
            sp_idx = int(self.redd_state.species_idx[i])
            sp_name = self.species_order[sp_idx]
            sp_cfg = self.config.species[sp_name]
            r_idx = int(self.redd_state.reach_idx[i])
            rname = self.reach_order[r_idx]
            rp_cfg = self.config.reaches[rname]
            temperature = redd_temps[i]

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

            self.redd_state.frac_developed[i] = develop_eggs(
                float(self.redd_state.frac_developed[i]),
                temperature,
                step_length,
                sp_cfg.redd_devel_A,
                sp_cfg.redd_devel_B,
                sp_cfg.redd_devel_C,
            )

        for i in alive_redds:
            if self.redd_state.num_eggs[i] <= 0:
                self.redd_state.alive[i] = False

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
            outmigration_probability,
        )

        sp_mig_L1 = self._sp_arrays["migrate_fitness_L1"]
        sp_mig_L9 = self._sp_arrays["migrate_fitness_L9"]
        alive = self.trout_state.alive_indices()
        for i in alive:
            lh = int(self.trout_state.life_history[i])
            if lh != LifeStage.PARR:
                continue
            sp_idx = int(self.trout_state.species_idx[i])
            sp_name = self.species_order[sp_idx]
            sp_cfg = self.config.species[sp_name]
            fish_length = float(self.trout_state.length[i])
            mig_fit = migration_fitness(
                fish_length,
                float(sp_mig_L1[sp_idx]),
                float(sp_mig_L9[sp_idx]),
            )
            best_hab = float(self.trout_state.fitness_memory[i])
            if should_migrate(mig_fit, best_hab, lh):
                out = migrate_fish_downstream(self.trout_state, i, self._reach_graph)
                self._outmigrants.extend(out)
            elif not self.trout_state.alive[i]:
                pass  # already dead
            else:
                # Supplementary fitness-based outmigration check
                p_out = outmigration_probability(
                    best_hab,
                    fish_length,
                    sp_cfg.outmigration_min_length,
                    sp_cfg.outmigration_max_prob,
                )
                if p_out > 0.0 and self.rng.random() < p_out:
                    out = migrate_fish_downstream(self.trout_state, i, self._reach_graph)
                    self._outmigrants.extend(out)

    def _collect_census_if_needed(self):
        """Record census data on configured census days."""
        from instream.io.time_manager import is_census

        if not hasattr(self, "_census_records"):
            self._census_records = []
        current_date = self.time_manager._current_date
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
        """Add arriving adults if adult arrival data is configured."""
        if not self._arrival_records:
            return

        from instream.io.arrival_reader import compute_daily_arrivals

        current_date = self.time_manager._current_date
        sim_year = current_date.year
        ts = self.trout_state
        n_cells = self.fem_space.num_cells

        if not hasattr(self, "_arrival_counts"):
            self._arrival_counts = {}

        year_records = [r for r in self._arrival_records if r["year"] == sim_year]
        if not year_records:
            available_years = sorted(set(r["year"] for r in self._arrival_records))
            if available_years:
                nearest = min(available_years, key=lambda y: abs(y - sim_year))
                year_records = [
                    r for r in self._arrival_records if r["year"] == nearest
                ]

        for idx, rec in enumerate(year_records):
            key = (sim_year, idx)
            arrived_so_far = self._arrival_counts.get(key, 0)
            n_today = compute_daily_arrivals(rec, current_date, arrived_so_far)
            if n_today <= 0:
                continue

            sp_name = rec["species"]
            sp_idx = self._species_name_to_idx.get(sp_name, 0)
            if sp_name in self.config.species:
                sp_cfg = self.config.species[sp_name]
            else:
                sp_cfg = self.config.species[self.species_order[0]]

            r_name = rec["reach"]
            r_idx = self.reach_order.index(r_name) if r_name in self.reach_order else 0

            dead_slots = np.where(~ts.alive)[0]
            n_add = min(n_today, len(dead_slots))
            if n_add <= 0:
                continue

            slots = dead_slots[:n_add]

            lengths = self.rng.triangular(
                rec["length_min"], rec["length_mode"], rec["length_max"], size=n_add
            )
            weights = sp_cfg.weight_A * lengths**sp_cfg.weight_B

            frac_female = rec["frac_female"]
            sex = (self.rng.random(n_add) < frac_female).astype(np.int32)

            reach_cells = np.where(self.fem_space.cell_state.reach_idx == r_idx)[0]
            if len(reach_cells) == 0:
                reach_cells = np.arange(n_cells)
            cell_choices = self.rng.choice(reach_cells, size=n_add)

            ts.alive[slots] = True
            ts.species_idx[slots] = sp_idx
            ts.length[slots] = lengths
            ts.weight[slots] = weights
            ts.condition[slots] = 1.0
            ts.age[slots] = 3
            ts.cell_idx[slots] = cell_choices
            ts.reach_idx[slots] = r_idx
            ts.sex[slots] = sex
            ts.superind_rep[slots] = 1
            # TODO: Change to LifeStage.RETURNING_ADULT when holding behavior is implemented (Task 12)
            lh_val = int(LifeStage.SPAWNER) if getattr(sp_cfg, "is_anadromous", False) else int(LifeStage.FRY)
            ts.life_history[slots] = lh_val
            ts.in_shelter[slots] = False
            ts.spawned_this_season[slots] = False
            ts.activity[slots] = 0
            ts.growth_memory[slots, :] = 0.0
            ts.consumption_memory[slots, :] = 0.0
            ts.survival_memory[slots, :] = 0.0
            ts.last_growth_rate[slots] = 0.0
            ts.fitness_memory[slots] = 0.0

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
