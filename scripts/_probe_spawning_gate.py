"""Focused diagnostic: run example_tornionjoki to Nov 1 of year 1
(mid-spawn-window) and dump every RETURNING_ADULT's state to see which
gate blocks spawning.

After v0.52.0 step 1 (spawn_min_temp=1, AdultArrivals remap), the B5
probe still shows init_cum=0 redds. This script runs ~213 days (faster
than the 1095-day cohort probe) and inspects per-fish state directly:
reach assignment, cell assignment, freshwater flag, sex, conditions.

Usage:
    micromamba run -n shiny python scripts/_probe_spawning_gate.py
"""
from __future__ import annotations

import datetime as _dt
import logging
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
logging.getLogger("salmopy.spawning").setLevel(logging.ERROR)


def main():
    from salmopy.model import SalmopyModel
    from salmopy.state.life_stage import LifeStage

    start = _dt.date(2011, 4, 1)
    end = _dt.date(2011, 11, 1)
    print(f"Running example_tornionjoki to {end} (~{(end - start).days} days)...")
    model = SalmopyModel(
        config_path=str(ROOT / "configs/example_tornionjoki.yaml"),
        data_dir=str(ROOT / "tests/fixtures/example_tornionjoki"),
        end_date_override=end.isoformat(),
    )
    model.rng = np.random.default_rng(42)

    while not model.time_manager.is_done():
        model.step()

    ts = model.trout_state
    alive = ts.alive_indices()
    print(f"\nFinal date: {model.time_manager.current_date}")
    print(f"Total alive: {len(alive)}")

    # ----- Per-life-stage breakdown -----
    stage_counts = Counter(int(s) for s in ts.life_history[alive])
    print("\nLife stages:")
    for stage_val, count in sorted(stage_counts.items()):
        try:
            name = LifeStage(stage_val).name
        except ValueError:
            name = f"unknown_{stage_val}"
        print(f"  {name}: {count}")

    # ----- Returning adults specifically -----
    returning_mask = ts.life_history[alive] == int(LifeStage.RETURNING_ADULT)
    returning = alive[returning_mask]
    print(f"\nRETURNING_ADULTs: {len(returning)}")
    if len(returning) == 0:
        print("(no returning adults — adult arrivals not loading)")
        return 1

    # Per-reach distribution
    reach_counts = Counter(int(r) for r in ts.reach_idx[returning])
    print("\nReturning adult per-reach distribution (reach_idx → count):")
    for r_idx in sorted(reach_counts):
        rname = model.reach_order[r_idx] if 0 <= r_idx < len(model.reach_order) else f"INVALID({r_idx})"
        print(f"  reach_idx={r_idx} ({rname}): {reach_counts[r_idx]}")

    # Cell-idx distribution: any fish with cell_idx == -1?
    cell_idx_arr = ts.cell_idx[returning]
    n_no_cell = int((cell_idx_arr < 0).sum())
    print(f"\nReturning adults with cell_idx < 0 (no cell assignment): {n_no_cell}/{len(returning)}")

    # Zone-idx distribution: must be -1 (freshwater) for spawn
    zone_idx_arr = ts.zone_idx[returning]
    zone_counts = Counter(int(z) for z in zone_idx_arr)
    print(f"Returning adults zone_idx counts: {dict(zone_counts)}")

    # Sex breakdown (only sex==0 spawns)
    sex_arr = ts.sex[returning]
    n_female = int((sex_arr == 0).sum())
    n_male = int((sex_arr == 1).sum())
    print(f"Returning adults: {n_female} female, {n_male} male")

    # Spawn-readiness check: try ready_to_spawn for first 5 females
    from salmopy.modules.spawning import ready_to_spawn
    sp_cfg = model.config.species["BalticAtlanticSalmon"]
    spawn_start_doy, spawn_end_doy = model._spawn_doy_cache.get("BalticAtlanticSalmon", (288, 334))
    doy = model.time_manager.julian_date

    females = returning[sex_arr == 0]
    print(f"\nSpawn-readiness for first 10 females (doy={doy}):")
    print(f"  spawn window: doy {spawn_start_doy}-{spawn_end_doy}")
    print(f"  spawn_min_temp={sp_cfg.spawn_min_temp}, spawn_max_temp={sp_cfg.spawn_max_temp}")
    print(f"  spawn_prob={sp_cfg.spawn_prob}")

    for i in females[:10]:
        r_idx = int(ts.reach_idx[i])
        rname = model.reach_order[r_idx] if 0 <= r_idx < len(model.reach_order) else "INVALID"
        rp = model.reach_params[rname] if rname in model.reach_params else None
        temp = float(model.reach_state.temperature[r_idx]) if 0 <= r_idx < len(model.reach_state.temperature) else float('nan')
        flow = float(model.reach_state.flow[r_idx]) if 0 <= r_idx < len(model.reach_state.flow) else float('nan')
        max_flow = rp.max_spawn_flow if rp else float('nan')
        cell = int(ts.cell_idx[i])
        zone = int(ts.zone_idx[i])

        # Walk through ready_to_spawn checks one at a time
        gates: list[str] = []
        if int(ts.sex[i]) != 0:
            gates.append("not female")
        if bool(ts.spawned_this_season[i]):
            gates.append("spawned_this_season")
        if temp < sp_cfg.spawn_min_temp or temp > sp_cfg.spawn_max_temp:
            gates.append(f"temp {temp:.2f} outside [{sp_cfg.spawn_min_temp}, {sp_cfg.spawn_max_temp}]")
        if doy < spawn_start_doy or doy > spawn_end_doy:
            gates.append(f"doy {doy} outside window")
        if not np.isnan(flow) and flow >= max_flow:
            gates.append(f"flow {flow:.2f} >= max_spawn_flow {max_flow}")
        if cell < 0:
            gates.append(f"cell_idx={cell}")
        if zone != -1:
            gates.append(f"zone_idx={zone}")
        gates_str = ", ".join(gates) if gates else "PASS (deterministic gates)"

        print(f"  fish[{i}] reach={rname}, cell={cell}, zone={zone}, "
              f"temp={temp:.2f}, flow={flow:.2f}: {gates_str}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
