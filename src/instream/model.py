"""InSTREAMModel -- main simulation model wiring all modules together."""

import numpy as np
import pandas as pd
from pathlib import Path

import mesa

from instream.io.config import load_config, params_from_config
from instream.io.timeseries import read_time_series
from instream.io.hydraulics_reader import read_depth_table, read_velocity_table
from instream.io.population_reader import (
    read_initial_populations,
    build_initial_trout_state,
)
from instream.io.time_manager import TimeManager
from instream.space.polygon_mesh import PolygonMesh
from instream.space.fem_space import FEMSpace
from instream.state.redd_state import ReddState
from instream.state.reach_state import ReachState
from instream.backends import get_backend
from instream.modules.reach import update_reach_state
from instream.modules.growth import (
    apply_growth,
    split_superindividuals,
)
from instream.modules.survival import (
    survival_high_temperature,
    survival_stranding,
    survival_condition,
    survival_fish_predation,
    survival_terrestrial_predation,
    apply_mortality,
)
from instream.modules.spawning import (
    ready_to_spawn,
    spawn_suitability,
    select_spawn_cell,
    create_redd,
    apply_spawner_weight_loss,
    develop_eggs,
    redd_emergence,
)
from instream.modules.survival import apply_redd_survival
from instream.modules.behavior import select_habitat_and_activity
from instream.sync import sync_trout_agents


class InSTREAMModel(mesa.Model):
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

    def __init__(self, config_path, data_dir=None, end_date_override=None):
        super().__init__()
        config_path = Path(config_path)
        self.config = load_config(config_path)
        self.species_params, self.reach_params = params_from_config(self.config)

        if data_dir is None:
            data_dir = config_path.parent
        self.data_dir = Path(data_dir)

        # RNG
        self.rng = np.random.default_rng(self.config.simulation.seed)

        # Backend
        backend_name = self.config.performance.backend
        self.backend = get_backend(backend_name)

        # Species and reach ordering
        self.species_order = list(self.config.species.keys())
        self.reach_order = list(self.config.reaches.keys())
        self._species_name_to_idx = {n: i for i, n in enumerate(self.species_order)}
        self._reach_name_to_idx = {n: i for i, n in enumerate(self.reach_order)}

        # Load spatial mesh
        gis = self.config.spatial.gis_properties
        mesh_path = self.data_dir / self.config.spatial.mesh_file
        # If mesh_file has directory structure, try to resolve it; if not found,
        # try just the filename in Shapefile/ subfolder
        if not mesh_path.exists():
            # Try the fixture layout: Shapefile/ExampleA.shp
            alt = self.data_dir / "Shapefile" / Path(self.config.spatial.mesh_file).name
            if alt.exists():
                mesh_path = alt

        self.mesh = PolygonMesh(
            mesh_path,
            id_field=gis.get("cell_id", "ID_TEXT"),
            reach_field=gis.get("reach_name", "REACH_NAME"),
            area_field=gis.get("area", "AREA"),
            dist_escape_field=gis.get("dist_escape", "M_TO_ESC"),
            hiding_field=gis.get("num_hiding_places", "NUM_HIDING"),
            shelter_field=gis.get("frac_vel_shelter", "FRACVSHL"),
            spawn_field=gis.get("frac_spawn", "FRACSPWN"),
        )

        # Load hydraulic tables for ALL reaches
        self._reach_hydraulic_data = {}
        for rname in self.reach_order:
            rcfg = self.config.reaches[rname]
            d_path = self.data_dir / rcfg.depth_file
            if not d_path.exists():
                d_path = self.data_dir / Path(rcfg.depth_file).name
            v_path = self.data_dir / rcfg.velocity_file
            if not v_path.exists():
                v_path = self.data_dir / Path(rcfg.velocity_file).name
            d_flows, d_vals = read_depth_table(d_path)
            v_flows, v_vals = read_velocity_table(v_path)
            d_vals = d_vals * 100.0  # m -> cm
            v_vals = v_vals * 100.0  # m/s -> cm/s
            self._reach_hydraulic_data[rname] = {
                "depth_flows": d_flows,
                "depth_values": d_vals,
                "vel_flows": v_flows,
                "vel_values": v_vals,
            }

        # Build CellState using the first reach's tables for FEMSpace init
        # (backward compat; per-reach updates happen in step())
        first_hdata = self._reach_hydraulic_data[self.reach_order[0]]
        cell_state = self.mesh.to_cell_state(
            first_hdata["depth_flows"],
            first_hdata["depth_values"],
            first_hdata["vel_flows"],
            first_hdata["vel_values"],
        )

        # Remap cell reach_idx to match model's reach_order (config ordering).
        # The mesh assigns reach_idx based on first-appearance in shapefile,
        # which may differ from config ordering.  Use a temp array to avoid
        # collision when swapping indices.
        mesh_unique = list(dict.fromkeys(self.mesh.reach_names))
        needs_remap = any(
            self._reach_name_to_idx.get(rname, mesh_idx) != mesh_idx
            for mesh_idx, rname in enumerate(mesh_unique)
        )
        if needs_remap:
            new_reach_idx = cell_state.reach_idx.copy()
            for mesh_idx, rname in enumerate(mesh_unique):
                model_idx = self._reach_name_to_idx[rname]
                mask = cell_state.reach_idx == mesh_idx
                new_reach_idx[mask] = model_idx
            cell_state.reach_idx[:] = new_reach_idx

        self.fem_space = FEMSpace(cell_state, self.mesh.neighbor_indices)

        # Load time-series data per reach
        time_series = {}
        for rname, rcfg in self.config.reaches.items():
            ts_path = self.data_dir / rcfg.time_series_input_file
            if not ts_path.exists():
                ts_path = self.data_dir / Path(rcfg.time_series_input_file).name
            time_series[rname] = read_time_series(ts_path)

        # Time manager
        end_date = end_date_override or self.config.simulation.end_date
        self.time_manager = TimeManager(
            start_date=self.config.simulation.start_date,
            end_date=end_date,
            time_series=time_series,
        )

        # Reach state
        self.reach_state = ReachState.zeros(
            num_reaches=len(self.reach_order),
            num_species=len(self.species_order),
        )

        # Previous flow for peak detection
        self._prev_flow = np.zeros(len(self.reach_order), dtype=np.float64)

        # Load initial trout population
        pop_file = self.config.simulation.population_file
        if pop_file:
            pop_path = self.data_dir / pop_file
        else:
            pop_candidates = list(self.data_dir.glob("*InitialPopulations*"))
            if not pop_candidates:
                raise FileNotFoundError(
                    "No population file configured and no *InitialPopulations* file in {}".format(
                        self.data_dir
                    )
                )
            pop_path = pop_candidates[0]

        populations = read_initial_populations(pop_path)

        # Use first species' weight params for initial population
        first_sp_name = self.species_order[0]
        first_sp_cfg = self.config.species[first_sp_name]

        self.trout_state = build_initial_trout_state(
            populations=populations,
            capacity=self.config.performance.trout_capacity,
            weight_A=first_sp_cfg.weight_A,
            weight_B=first_sp_cfg.weight_B,
            species_index=0,
            seed=self.config.simulation.seed,
        )

        # Assign initial cell and reach indices to fish
        self._assign_initial_positions()

        # Redd state
        self.redd_state = ReddState.zeros(self.config.performance.redd_capacity)

        # Reach connectivity graph for migration
        from instream.modules.migration import build_reach_graph

        upstream = [self.config.reaches[r].upstream_junction for r in self.reach_order]
        downstream = [
            self.config.reaches[r].downstream_junction for r in self.reach_order
        ]
        self._reach_graph = build_reach_graph(upstream, downstream)
        self._outmigrants = []

        # Mesa agent dict (for sync_trout_agents)
        self._trout_agents = {}
        sync_trout_agents(self)

        # Light config
        self._light_cfg = self.config.light

        # Pre-compute spawn suitability tables (avoid dict-to-array per step)
        self._spawn_tables = {}
        for sp_name, sp_cfg_item in self.config.species.items():
            sp_depth_tbl = sp_cfg_item.spawn_depth_table
            depth_xs = np.array(sorted(sp_depth_tbl.keys()), dtype=np.float64)
            depth_ys = np.array(
                [sp_depth_tbl[k] for k in sorted(sp_depth_tbl.keys())], dtype=np.float64
            )
            sp_vel_tbl = sp_cfg_item.spawn_vel_table
            vel_xs = np.array(sorted(sp_vel_tbl.keys()), dtype=np.float64)
            vel_ys = np.array(
                [sp_vel_tbl[k] for k in sorted(sp_vel_tbl.keys())], dtype=np.float64
            )
            self._spawn_tables[sp_name] = (depth_xs, depth_ys, vel_xs, vel_ys)

    def _assign_initial_positions(self):
        """Randomly assign alive fish to wet or available cells."""
        alive = self.trout_state.alive_indices()
        n_cells = self.fem_space.num_cells
        if n_cells == 0 or len(alive) == 0:
            return
        # Distribute fish across all cells
        cells = self.rng.integers(0, n_cells, size=len(alive))
        self.trout_state.cell_idx[alive] = cells
        # Set reach_idx from cell's reach_idx
        self.trout_state.reach_idx[alive] = self.fem_space.cell_state.reach_idx[cells]

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
        """Advance the simulation by one time step."""
        # 1. Advance time
        step_length = self.time_manager.advance()

        # 1b. Increment age on January 1
        self._increment_age_if_new_year()

        # 1c. Adult arrivals (stub for multi-reach/species)
        self._do_adult_arrivals()

        # 2. Get conditions for each reach
        conditions = {}
        for rname in self.reach_order:
            conditions[rname] = self.time_manager.get_conditions(rname)

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

        # 4. Update hydraulics for each reach's flow
        # Use the first reach's flow (single-reach model for now)
        flow = float(self.reach_state.flow[0])
        self.fem_space.update_hydraulics(flow, self.backend)

        # 5. Compute light
        jd = self.time_manager.julian_date
        reach_cfg_0 = self.config.reaches[self.reach_order[0]]
        day_length, twilight_length, irradiance = self.backend.compute_light(
            jd,
            self._light_cfg.latitude,
            self._light_cfg.light_correction,
            reach_cfg_0.shading,
            self._light_cfg.light_at_night,
            self._light_cfg.twilight_angle,
        )
        cell_light = self.backend.compute_cell_light(
            self.fem_space.cell_state.depth,
            irradiance,
            reach_cfg_0.light_turbid_coef,
            float(self.reach_state.turbidity[0]),
            self._light_cfg.light_at_night,
        )
        self.fem_space.cell_state.light[:] = cell_light

        # 6. Reset cell resources
        cs = self.fem_space.cell_state
        rp = self.reach_params[self.reach_order[0]]
        cs.available_drift[:] = rp.drift_conc * cs.area * cs.depth
        cs.available_search[:] = rp.search_prod * cs.area
        cs.available_vel_shelter[:] = cs.frac_vel_shelter * cs.area
        cs.available_hiding_places[:] = self.mesh.num_hiding_places.copy()

        # 7. Habitat selection & activity
        sp_cfg = self.config.species[self.species_order[0]]
        temperature = float(self.reach_state.temperature[0])
        turbidity = float(self.reach_state.turbidity[0])

        # Compute piscivore density for fitness evaluation
        pisciv_densities = self._compute_piscivore_density()

        select_habitat_and_activity(
            self.trout_state,
            self.fem_space,
            move_radius_max=sp_cfg.move_radius_max,
            move_radius_L1=sp_cfg.move_radius_L1,
            move_radius_L9=sp_cfg.move_radius_L9,
            temperature=temperature,
            turbidity=turbidity,
            drift_conc=rp.drift_conc,
            search_prod=rp.search_prod,
            search_area=sp_cfg.search_area,
            shelter_speed_frac=rp.shelter_speed_frac,
            step_length=step_length,
            cmax_A=sp_cfg.cmax_A,
            cmax_B=sp_cfg.cmax_B,
            cmax_temp_table_x=self.species_params[
                self.species_order[0]
            ].cmax_temp_table_x,
            cmax_temp_table_y=self.species_params[
                self.species_order[0]
            ].cmax_temp_table_y,
            react_dist_A=sp_cfg.react_dist_A,
            react_dist_B=sp_cfg.react_dist_B,
            turbid_threshold=sp_cfg.turbid_threshold,
            turbid_min=sp_cfg.turbid_min,
            turbid_exp=sp_cfg.turbid_exp,
            light_threshold=sp_cfg.light_threshold,
            light_min=sp_cfg.light_min,
            light_exp=sp_cfg.light_exp,
            capture_R1=sp_cfg.capture_R1,
            capture_R9=sp_cfg.capture_R9,
            max_speed_A=sp_cfg.max_speed_A,
            max_speed_B=sp_cfg.max_speed_B,
            max_swim_temp_term=float(self.reach_state.max_swim_temp_term[0, 0]),
            resp_A=sp_cfg.resp_A,
            resp_B=sp_cfg.resp_B,
            resp_D=sp_cfg.resp_D,
            resp_temp_term=float(self.reach_state.resp_temp_term[0, 0]),
            prey_energy_density=rp.prey_energy_density,
            fish_energy_density=sp_cfg.energy_density,
            # Survival parameters (Phase 5)
            mort_high_temp_T1=sp_cfg.mort_high_temp_T1,
            mort_high_temp_T9=sp_cfg.mort_high_temp_T9,
            mort_condition_S_at_K5=sp_cfg.mort_condition_S_at_K5,
            mort_condition_S_at_K8=sp_cfg.mort_condition_S_at_K8,
            mort_strand_survival_when_dry=sp_cfg.mort_strand_survival_when_dry,
            fish_pred_min=rp.fish_pred_min,
            fish_pred_L1=sp_cfg.mort_fish_pred_L1,
            fish_pred_L9=sp_cfg.mort_fish_pred_L9,
            fish_pred_D1=sp_cfg.mort_fish_pred_D1,
            fish_pred_D9=sp_cfg.mort_fish_pred_D9,
            fish_pred_P1=sp_cfg.mort_fish_pred_P1,
            fish_pred_P9=sp_cfg.mort_fish_pred_P9,
            fish_pred_I1=sp_cfg.mort_fish_pred_I1,
            fish_pred_I9=sp_cfg.mort_fish_pred_I9,
            fish_pred_T1=sp_cfg.mort_fish_pred_T1,
            fish_pred_T9=sp_cfg.mort_fish_pred_T9,
            fish_pred_hiding_factor=sp_cfg.mort_fish_pred_hiding_factor,
            pisciv_densities=pisciv_densities,
            terr_pred_min=rp.terr_pred_min,
            terr_pred_L1=sp_cfg.mort_terr_pred_L1,
            terr_pred_L9=sp_cfg.mort_terr_pred_L9,
            terr_pred_D1=sp_cfg.mort_terr_pred_D1,
            terr_pred_D9=sp_cfg.mort_terr_pred_D9,
            terr_pred_V1=sp_cfg.mort_terr_pred_V1,
            terr_pred_V9=sp_cfg.mort_terr_pred_V9,
            terr_pred_I1=sp_cfg.mort_terr_pred_I1,
            terr_pred_I9=sp_cfg.mort_terr_pred_I9,
            terr_pred_H1=sp_cfg.mort_terr_pred_H1,
            terr_pred_H9=sp_cfg.mort_terr_pred_H9,
            terr_pred_hiding_factor=sp_cfg.mort_terr_pred_hiding_factor,
        )

        # 8. Growth: use growth rate from habitat selection (not recomputed)
        alive = self.trout_state.alive_indices()
        for i in alive:
            cell = self.trout_state.cell_idx[i]
            if cell < 0 or cell >= self.fem_space.num_cells:
                continue
            growth = self.trout_state.last_growth_rate[i]
            daily_growth = growth * step_length
            new_w, new_l, new_k = apply_growth(
                float(self.trout_state.weight[i]),
                float(self.trout_state.length[i]),
                float(self.trout_state.condition[i]),
                daily_growth,
                sp_cfg.weight_A,
                sp_cfg.weight_B,
            )
            self.trout_state.weight[i] = new_w
            self.trout_state.length[i] = new_l
            self.trout_state.condition[i] = new_k

        # Split superindividuals
        split_superindividuals(self.trout_state, sp_cfg.superind_max_length)

        # 9. Survival / mortality
        alive = self.trout_state.alive_indices()
        n_capacity = self.trout_state.alive.shape[0]
        survival_probs = np.ones(n_capacity, dtype=np.float64)

        # Compute piscivore density for survival evaluation
        pisciv_densities_surv = self._compute_piscivore_density()

        for i in alive:
            cell = self.trout_state.cell_idx[i]
            if cell < 0 or cell >= self.fem_space.num_cells:
                continue
            act_idx = int(self.trout_state.activity[i])

            s_ht = survival_high_temperature(
                temperature, sp_cfg.mort_high_temp_T1, sp_cfg.mort_high_temp_T9
            )
            s_str = survival_stranding(
                float(cs.depth[cell]), sp_cfg.mort_strand_survival_when_dry
            )
            s_cond = survival_condition(
                float(self.trout_state.condition[i]),
                sp_cfg.mort_condition_S_at_K5,
                sp_cfg.mort_condition_S_at_K8,
            )

            # Fish predation with computed piscivore density
            s_fp = survival_fish_predation(
                float(self.trout_state.length[i]),
                float(cs.depth[cell]),
                float(cs.light[cell]),
                float(pisciv_densities_surv[cell]),
                temperature,
                act_idx,
                rp.fish_pred_min,
                sp_cfg.mort_fish_pred_L1,
                sp_cfg.mort_fish_pred_L9,
                sp_cfg.mort_fish_pred_D1,
                sp_cfg.mort_fish_pred_D9,
                sp_cfg.mort_fish_pred_P1,
                sp_cfg.mort_fish_pred_P9,
                sp_cfg.mort_fish_pred_I1,
                sp_cfg.mort_fish_pred_I9,
                sp_cfg.mort_fish_pred_T1,
                sp_cfg.mort_fish_pred_T9,
                sp_cfg.mort_fish_pred_hiding_factor,
            )

            # Terrestrial predation
            s_tp = survival_terrestrial_predation(
                float(self.trout_state.length[i]),
                float(cs.depth[cell]),
                float(cs.velocity[cell]),
                float(cs.light[cell]),
                float(cs.dist_escape[cell]),
                act_idx,
                int(cs.available_hiding_places[cell]),
                int(self.trout_state.superind_rep[i]),
                rp.terr_pred_min,
                sp_cfg.mort_terr_pred_L1,
                sp_cfg.mort_terr_pred_L9,
                sp_cfg.mort_terr_pred_D1,
                sp_cfg.mort_terr_pred_D9,
                sp_cfg.mort_terr_pred_V1,
                sp_cfg.mort_terr_pred_V9,
                sp_cfg.mort_terr_pred_I1,
                sp_cfg.mort_terr_pred_I9,
                sp_cfg.mort_terr_pred_H1,
                sp_cfg.mort_terr_pred_H9,
                sp_cfg.mort_terr_pred_hiding_factor,
            )

            daily_surv = s_ht * s_str * s_cond * s_fp * s_tp
            survival_probs[i] = daily_surv**step_length

        # Apply stochastic mortality
        apply_mortality(self.trout_state.alive, survival_probs, self.rng)

        # 10. Spawning
        self._do_spawning(step_length, temperature, turbidity, flow)

        # 11. Redd survival, development, emergence
        self._do_redd_step(step_length, temperature)

        # 12. Migration
        self._do_migration()

        # 13. Sync Mesa agents
        sync_trout_agents(self)

        # 14. Census data collection
        self._collect_census_if_needed()

    def _do_spawning(self, step_length, temperature, turbidity, flow):
        """Check spawning readiness and create redds."""
        sp_cfg = self.config.species[self.species_order[0]]
        rp = self.reach_params[self.reach_order[0]]
        doy = self.time_manager.julian_date

        # Parse spawn season DOY
        try:
            start_parts = sp_cfg.spawn_start_day.split("-")
            spawn_start_doy = int(
                pd.Timestamp(f"2000-{start_parts[0]}-{start_parts[1]}").day_of_year
            )
            end_parts = sp_cfg.spawn_end_day.split("-")
            spawn_end_doy = int(
                pd.Timestamp(f"2000-{end_parts[0]}-{end_parts[1]}").day_of_year
            )
        except (ValueError, IndexError, AttributeError) as e:
            import logging

            logging.getLogger(__name__).warning(
                "Could not parse spawn dates (%s), using defaults Sep 1 - Oct 31", e
            )
            spawn_start_doy = 244  # Sep 1
            spawn_end_doy = 304  # Oct 31

        self._reset_spawn_season_if_needed(spawn_start_doy)

        alive = self.trout_state.alive_indices()
        cs = self.fem_space.cell_state

        # Pre-computed spawn depth/velocity table arrays
        depth_xs, depth_ys, vel_xs, vel_ys = self._spawn_tables[self.species_order[0]]

        for i in alive:
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

            best_cell = select_spawn_cell(scores, candidates)
            reach_idx = int(cs.reach_idx[best_cell])

            created = create_redd(
                self.redd_state,
                species_idx=0,
                cell_idx=best_cell,
                reach_idx=reach_idx,
                weight=float(self.trout_state.weight[i]),
                fecund_mult=sp_cfg.spawn_fecund_mult,
                fecund_exp=sp_cfg.spawn_fecund_exp,
                egg_viability=sp_cfg.spawn_egg_viability,
            )
            if created:
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

    def _do_redd_step(self, step_length, temperature):
        """Redd survival, egg development, and emergence."""
        sp_cfg = self.config.species[self.species_order[0]]
        rp_cfg = self.config.reaches[self.reach_order[0]]
        cs = self.fem_space.cell_state

        alive_redds = np.where(self.redd_state.alive)[0]
        if len(alive_redds) == 0:
            return

        # Get conditions at each redd's cell
        redd_temps = np.full(len(self.redd_state.alive), temperature)
        redd_depths = np.zeros(len(self.redd_state.alive))
        redd_flows = np.full(
            len(self.redd_state.alive), float(self.reach_state.flow[0])
        )
        redd_peaks = np.full(
            len(self.redd_state.alive), bool(self.reach_state.is_flow_peak[0])
        )

        for i in alive_redds:
            cell = self.redd_state.cell_idx[i]
            if 0 <= cell < self.fem_space.num_cells:
                redd_depths[i] = cs.depth[cell]

        # Apply redd survival
        new_eggs, lo, hi, dw, sc = apply_redd_survival(
            self.redd_state.num_eggs,
            self.redd_state.frac_developed,
            redd_temps,
            redd_depths,
            redd_flows,
            redd_peaks,
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
        self.redd_state.num_eggs[:] = np.round(new_eggs).astype(np.int32)

        # Track mortality
        self.redd_state.eggs_lo_temp[:] += np.round(lo).astype(np.int32)
        self.redd_state.eggs_hi_temp[:] += np.round(hi).astype(np.int32)
        self.redd_state.eggs_dewatering[:] += np.round(dw).astype(np.int32)
        self.redd_state.eggs_scour[:] += np.round(sc).astype(np.int32)

        # Develop eggs
        for i in alive_redds:
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

        # Emergence
        redd_emergence(
            self.redd_state,
            self.trout_state,
            self.rng,
            sp_cfg.emerge_length_min,
            sp_cfg.emerge_length_mode,
            sp_cfg.emerge_length_max,
            sp_cfg.weight_A,
            sp_cfg.weight_B,
            species_index=0,
        )

    def _compute_piscivore_density(self):
        """Compute piscivore density (count / area) per cell."""
        sp_cfg = self.config.species[self.species_order[0]]
        pisciv_length = getattr(sp_cfg, "pisciv_length", 999.0)
        n_cells = self.fem_space.num_cells
        pisciv_count = np.zeros(n_cells, dtype=np.float64)
        alive = self.trout_state.alive_indices()
        for i in alive:
            cell = self.trout_state.cell_idx[i]
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

        sp_cfg = self.config.species[self.species_order[0]]
        mig_L1 = getattr(sp_cfg, "migrate_fitness_L1", 999.0)
        mig_L9 = getattr(sp_cfg, "migrate_fitness_L9", 999.0)
        alive = self.trout_state.alive_indices()
        for i in alive:
            lh = int(self.trout_state.life_history[i])
            if lh != 1:
                continue
            mig_fit = migration_fitness(
                float(self.trout_state.length[i]), mig_L1, mig_L9
            )
            best_hab = float(self.trout_state.last_growth_rate[i])
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
        """Add arriving adults if adult arrival data is configured."""
        pass  # TODO: implement when multi-reach/species is added

    def run(self):
        """Run the simulation until the end date."""
        while not self.time_manager.is_done():
            self.step()
