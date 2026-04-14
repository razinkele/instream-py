"""_ModelInitMixin -- initialization logic extracted from InSTREAMModel."""

import numpy as np
import pandas as pd
from pathlib import Path

from instream.io.config import ModelConfig, load_config, params_from_config
from instream.io.timeseries import read_time_series
from instream.io.hydraulics_reader import read_depth_table, read_velocity_table
from instream.io.population_reader import (
    read_initial_populations,
)
from instream.io.arrival_reader import read_adult_arrivals, compute_daily_arrivals  # noqa: E402
from instream.io.time_manager import TimeManager, detect_frequency
from instream.space.polygon_mesh import PolygonMesh
from instream.space.fem_space import FEMSpace
from instream.state.redd_state import ReddState
from instream.state.reach_state import ReachState
from instream.backends import get_backend


class _ModelInitMixin:
    """Mixin that provides _build_model and _assign_initial_positions."""

    def _build_model(self, config_path, data_dir=None, end_date_override=None, output_dir=None):
        # Accept either a file path or a pre-loaded ModelConfig object
        if isinstance(config_path, ModelConfig):
            self.config = config_path
            config_path = Path(".")  # placeholder for data_dir resolution
        else:
            config_path = Path(config_path)
            self.config = load_config(config_path)
        self.species_params, self.reach_params = params_from_config(self.config)
        self.output_dir = output_dir  # None = no file output

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

        # Pre-compute per-reach cell indices (reach_idx never changes)
        self._reach_cells = {}
        for r_idx in range(len(self.reach_order)):
            self._reach_cells[r_idx] = np.where(
                self.fem_space.cell_state.reach_idx == r_idx
            )[0]

        # Load time-series data per reach
        time_series = {}
        for rname, rcfg in self.config.reaches.items():
            ts_path = self.data_dir / rcfg.time_series_input_file
            if not ts_path.exists():
                ts_path = self.data_dir / Path(rcfg.time_series_input_file).name
            time_series[rname] = read_time_series(ts_path)

        # Detect sub-daily frequency from first reach's time series
        first_ts = next(iter(time_series.values()))
        self.steps_per_day = detect_frequency(first_ts)

        # Time manager
        end_date = end_date_override or self.config.simulation.end_date
        self.time_manager = TimeManager(
            start_date=self.config.simulation.start_date,
            end_date=end_date,
            time_series=time_series,
        )

        # Year shuffler (stochastic year resampling)
        self._year_shuffler = None
        if self.config.simulation.shuffle_years:
            from instream.io.time_manager import YearShuffler

            first_ts = next(iter(self.time_manager._time_series.values()))
            available_years = sorted(set(first_ts.index.year))
            self._year_shuffler = YearShuffler(
                available_years,
                seed=self.config.simulation.shuffle_seed,
            )

        # Reach state
        self.reach_state = ReachState.zeros(
            num_reaches=len(self.reach_order),
            num_species=len(self.species_order),
        )

        # Previous flow for peak detection
        self._prev_flow = np.zeros(len(self.reach_order), dtype=np.float64)

        # Pre-build per-species parameter arrays for fast per-fish lookup
        n_sp = len(self.species_order)
        self._sp_arrays = {}
        for field in [
            "cmax_A",
            "cmax_B",
            "weight_A",
            "weight_B",
            "resp_A",
            "resp_B",
            "resp_D",
            "react_dist_A",
            "react_dist_B",
            "max_speed_A",
            "max_speed_B",
            "capture_R1",
            "capture_R9",
            "turbid_threshold",
            "turbid_min",
            "turbid_exp",
            "light_threshold",
            "light_min",
            "light_exp",
            "energy_density",
            "search_area",
            "move_radius_max",
            "move_radius_L1",
            "move_radius_L9",
            "superind_max_length",
            "mort_high_temp_T1",
            "mort_high_temp_T9",
            "mort_condition_S_at_K5",
            "mort_condition_S_at_K8",
            "mort_condition_K_crit",
            "mort_strand_survival_when_dry",
            "pisciv_length",
            "mort_fish_pred_L1",
            "mort_fish_pred_L9",
            "mort_fish_pred_D1",
            "mort_fish_pred_D9",
            "mort_fish_pred_P1",
            "mort_fish_pred_P9",
            "mort_fish_pred_I1",
            "mort_fish_pred_I9",
            "mort_fish_pred_T1",
            "mort_fish_pred_T9",
            "mort_fish_pred_hiding_factor",
            "mort_terr_pred_L1",
            "mort_terr_pred_L9",
            "mort_terr_pred_D1",
            "mort_terr_pred_D9",
            "mort_terr_pred_V1",
            "mort_terr_pred_V9",
            "mort_terr_pred_I1",
            "mort_terr_pred_I9",
            "mort_terr_pred_H1",
            "mort_terr_pred_H9",
            "mort_terr_pred_hiding_factor",
            "migrate_fitness_L1",
            "migrate_fitness_L9",
            "fitness_memory_frac",
            "fitness_growth_weight",
        ]:
            self._sp_arrays[field] = np.array(
                [
                    getattr(self.config.species[s], field, 0.0)
                    for s in self.species_order
                ],
                dtype=np.float64,
            )

        # Pre-compute geometry candidate cache for fast habitat selection
        _max_move = float(np.max(self._sp_arrays["move_radius_max"]))
        if _max_move > 0:
            self.fem_space.precompute_geometry_candidates(_max_move)

        # Per-species cmax temp tables (list of arrays, indexed by species_idx)
        self._sp_cmax_table_x = [
            self.species_params[s].cmax_temp_table_x for s in self.species_order
        ]
        self._sp_cmax_table_y = [
            self.species_params[s].cmax_temp_table_y for s in self.species_order
        ]

        # Pre-build per-reach parameter arrays
        n_r = len(self.reach_order)
        self._rp_arrays = {}
        for field in [
            "drift_conc",
            "search_prod",
            "shelter_speed_frac",
            "prey_energy_density",
            "fish_pred_min",
            "terr_pred_min",
            "max_spawn_flow",
            "shear_A",
            "shear_B",
        ]:
            self._rp_arrays[field] = np.array(
                [getattr(self.reach_params[r], field, 0.0) for r in self.reach_order],
                dtype=np.float64,
            )

        # Load initial trout population
        pop_file = self.config.simulation.population_file
        if pop_file:
            pop_path = self.data_dir / pop_file
            if not pop_path.exists():
                pop_path = self.data_dir / Path(pop_file).name
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
        total = sum(p["number"] for p in populations)
        if total > self.config.performance.trout_capacity:
            raise ValueError(
                "Total fish ({}) exceeds capacity ({}).".format(
                    total, self.config.performance.trout_capacity
                )
            )

        from instream.state.trout_state import TroutState

        self.trout_state = TroutState.zeros(
            self.config.performance.trout_capacity,
            max_steps_per_day=self.steps_per_day,
        )
        rng_pop = np.random.default_rng(self.config.simulation.seed)
        idx = 0
        for pop in populations:
            sp_name = pop["species"]
            sp_idx = self._species_name_to_idx.get(sp_name, 0)
            if sp_name not in self._species_name_to_idx:
                import warnings

                warnings.warn(
                    "Species '{}' in population file not found in config. "
                    "Mapping to '{}' (index 0).".format(sp_name, self.species_order[0]),
                    stacklevel=2,
                )
            sp_cfg = self.config.species.get(
                sp_name, self.config.species[self.species_order[0]]
            )
            n = pop["number"]
            lengths = rng_pop.triangular(
                pop["length_min"], pop["length_mode"], pop["length_max"], n
            )
            weights = sp_cfg.weight_A * lengths**sp_cfg.weight_B
            end = idx + n
            self.trout_state.alive[idx:end] = True
            self.trout_state.species_idx[idx:end] = sp_idx
            self.trout_state.age[idx:end] = pop["age"]
            self.trout_state.length[idx:end] = lengths
            self.trout_state.weight[idx:end] = weights
            self.trout_state.condition[idx:end] = 1.0
            self.trout_state.superind_rep[idx:end] = 1
            self.trout_state.sex[idx:end] = rng_pop.integers(
                0, 2, size=n, dtype=np.int32
            )
            idx = end

        # Assign initial cell and reach indices to fish
        self._assign_initial_positions()

        # Redd state
        self.redd_state = ReddState.zeros(self.config.performance.redd_capacity)

        # Adult arrival schedule
        arrival_file = self.config.simulation.adult_arrival_file
        if arrival_file:
            arrival_path = self.data_dir / arrival_file
            if not arrival_path.exists():
                arrival_path = self.data_dir / Path(arrival_file).name
            self._arrival_records = read_adult_arrivals(arrival_path)
        else:
            self._arrival_records = []

        # v0.17.0 — hatchery stocking queue (InSALMON extension).
        # Each entry fires on its ISO date during day-boundary processing
        # and injects hatchery fish into dead TroutState slots.
        self._hatchery_stocking_queue: list[dict] = []
        for sp_idx, sp_name in enumerate(self.species_order):
            sp_cfg = self.config.species[sp_name]
            stocking = getattr(sp_cfg, "hatchery_stocking", None)
            if stocking is None:
                continue
            self._hatchery_stocking_queue.append({
                "species_idx": sp_idx,
                "num_fish": int(stocking.num_fish),
                "reach": stocking.reach,
                "date": stocking.date,
                "length_mean": float(stocking.length_mean),
                "length_sd": float(stocking.length_sd),
                "release_shock_survival": float(stocking.release_shock_survival),
            })

        # Reach connectivity graph for migration
        from instream.modules.migration import build_reach_graph

        upstream = [self.config.reaches[r].upstream_junction for r in self.reach_order]
        downstream = [
            self.config.reaches[r].downstream_junction for r in self.reach_order
        ]
        self._reach_graph = build_reach_graph(upstream, downstream)

        # Pre-compute allowed reaches per reach (self + forward + reverse neighbors)
        self._reach_allowed = {}
        for r_idx in range(len(self.reach_order)):
            allowed = {r_idx}
            allowed.update(self._reach_graph.get(r_idx, []))
            for other, neighbors in self._reach_graph.items():
                if r_idx in neighbors:
                    allowed.add(other)
            self._reach_allowed[r_idx] = np.array(sorted(allowed), dtype=np.int32)

        self._outmigrants = []

        # Harvest schedule
        self._harvest_schedule = {}
        if self.config.simulation.harvest_file:
            hf = self.data_dir / self.config.simulation.harvest_file
            if hf.exists():
                df = pd.read_csv(hf, parse_dates=["date"])
                for _, row in df.iterrows():
                    self._harvest_schedule[row["date"].strftime("%Y-%m-%d")] = float(
                        row["num_anglers"]
                    )
        self._harvest_records = []

        # Marine domain initialization
        self._marine_domain = None
        if self.config.marine is not None:
            from instream.marine.domain import MarineDomain, ZoneState
            mc = self.config.marine
            zone_names = [z.name for z in mc.zones]
            zone_areas = np.array([z.area_km2 for z in mc.zones])
            zs = ZoneState.zeros(len(mc.zones))
            zs.name[:] = zone_names
            zs.area_km2[:] = zone_areas
            self._marine_domain = MarineDomain(self.trout_state, zs, mc, rng=self.rng)
            # v0.17.0 Phase 4 fix — pass species weight_A/weight_B arrays
            # so apply_marine_growth can update length from weight (without
            # this, smolts stay at 12-15 cm their entire ocean phase and
            # seal predation — with L1=40 cm — never activates).
            try:
                sp_weight_A = np.array(
                    [self.config.species[n].weight_A for n in self.species_order],
                    dtype=np.float64,
                )
                sp_weight_B = np.array(
                    [self.config.species[n].weight_B for n in self.species_order],
                    dtype=np.float64,
                )
                self._marine_domain.species_weight_A = sp_weight_A
                self._marine_domain.species_weight_B = sp_weight_B
            except Exception:
                pass

        # Mesa agent dict (for sync_trout_agents)
        from instream.sync import sync_trout_agents

        self._trout_agents = {}
        sync_trout_agents(self)

        # Light config
        self._light_cfg = self.config.light
        self._cached_solar = {}  # solar irradiance cache (computed once per day)

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
        # Set natal_reach_idx for initial fish (used by marine adult return)
        self.trout_state.natal_reach_idx[alive] = self.fem_space.cell_state.reach_idx[cells]
