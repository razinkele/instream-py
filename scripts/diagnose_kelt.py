"""v0.20.0 kelt-chain diagnosis.

Runs the Baltic 7-year calibration fixture with monkey-patched kelt
instrumentation to locate the gate that produces 108 returns + 0 kelts.
"""
from pathlib import Path
import datetime
import numpy as np

from instream.model import InSTREAMModel
from instream.state.life_stage import LifeStage
from instream.modules import spawning as spawning_mod

CONFIGS = Path(__file__).parent.parent / "configs"
FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"

# Instrument kelt survival with call-level logging
_original_kelt = spawning_mod.apply_post_spawn_kelt_survival
kelt_call_log = []


def instrumented_kelt(trout_state, kelt_survival_prob, min_kelt_condition, rng):
    spawners_mask = (
        trout_state.alive
        & (trout_state.life_history == int(LifeStage.SPAWNER))
        & trout_state.spawned_this_season
    )
    n_spawner_total = int(spawners_mask.sum())
    eligible_mask = spawners_mask & (trout_state.condition >= min_kelt_condition)
    n_eligible = int(eligible_mask.sum())
    n_promoted = _original_kelt(
        trout_state, kelt_survival_prob, min_kelt_condition, rng
    )
    if n_spawner_total > 0 or n_eligible > 0 or n_promoted > 0:
        kelt_call_log.append({
            "n_spawners": n_spawner_total,
            "n_eligible": n_eligible,
            "n_promoted": n_promoted,
        })
    return n_promoted


spawning_mod.apply_post_spawn_kelt_survival = instrumented_kelt
# Also patch the already-bound import in model_day_boundary
import instream.model_day_boundary as mdb
if hasattr(mdb, "apply_post_spawn_kelt_survival"):
    mdb.apply_post_spawn_kelt_survival = instrumented_kelt

m = InSTREAMModel(
    CONFIGS / "example_calibration_baltic.yaml",
    data_dir=FIXTURES / "example_a",
    end_date_override="2018-03-31",
)

ts = m.trout_state
dead = np.where(~ts.alive)[0]
n_parr = min(len(dead), 3000)
parr = dead[:n_parr]
sp_cfg = m.config.species[m.species_order[0]]
ts.alive[parr] = True
ts.species_idx[parr] = 0
ts.life_history[parr] = int(LifeStage.PARR)
ts.age[parr] = 1
ts.length[parr] = 15.0
ts.weight[parr] = sp_cfg.weight_A * 15.0 ** sp_cfg.weight_B
ts.condition[parr] = 1.0
ts.smolt_readiness[parr] = 0.9
ts.fitness_memory[parr] = 0.5
ts.reach_idx[parr] = 0
ts.natal_reach_idx[parr] = 0
ts.zone_idx[parr] = -1
ts.sea_winters[parr] = 0
ts.smolt_date[parr] = -1
ts.is_hatchery[parr] = False

print(f"Seeded {n_parr} PARR. Running 7-year sim with per-day RETURNING_ADULT census...")

# Patch model.step to record RETURNING_ADULT census
returning_census = []  # (date, n_returning_adults, n_spawners)
_original_step = m.step

kelt_census = []  # (date, n_kelt_freshwater, n_oa_marine, max_sea_winters_oa)

# v0.24.0 — natal recruitment: per-year life-stage snapshot + PARR length tracking
from collections import defaultdict
yearly_stage_census = defaultdict(lambda: {s.name: 0 for s in LifeStage})
yearly_parr_lengths = defaultdict(list)  # year -> list of max-length snapshots
_last_census_year = [None]

def instrumented_step():
    _original_step()
    n_ra = int(
        ts.alive.sum()
        and ((ts.life_history == int(LifeStage.RETURNING_ADULT)) & ts.alive).sum()
    )
    n_sp = int(((ts.life_history == int(LifeStage.SPAWNER)) & ts.alive).sum())
    if n_ra > 0 or n_sp > 0:
        returning_census.append((m.time_manager.current_date, n_ra, n_sp))

    # v0.22.0 kelt-recondition diagnostic
    n_kelt = int(((ts.life_history == int(LifeStage.KELT)) & ts.alive).sum())
    n_oa = int(((ts.life_history == int(LifeStage.OCEAN_ADULT)) & ts.alive).sum())
    sw_max = int(ts.sea_winters[ts.alive].max()) if ts.alive.any() else 0
    if n_kelt > 0 or n_oa > 0:
        kelt_census.append((m.time_manager.current_date, n_kelt, n_oa, sw_max))

    # v0.24.0 — yearly life-stage snapshot on Dec 31
    cur = m.time_manager.current_date
    if cur.month == 12 and cur.day == 31 and _last_census_year[0] != cur.year:
        _last_census_year[0] = cur.year
        alive_mask = ts.alive
        for stage in LifeStage:
            cnt = int(((ts.life_history == int(stage)) & alive_mask).sum())
            yearly_stage_census[cur.year][stage.name] = cnt
        # PARR length distribution
        parr_mask = alive_mask & (ts.life_history == int(LifeStage.PARR))
        parr_idx = np.where(parr_mask)[0]
        if len(parr_idx) > 0:
            lengths = ts.length[parr_idx]
            yearly_parr_lengths[cur.year] = {
                "n": len(parr_idx),
                "mean_L": float(lengths.mean()),
                "max_L": float(lengths.max()),
                "pct_ge12": float((lengths >= 12.0).mean() * 100),
            }

m.step = instrumented_step
m.run()

md = m._marine_domain
print()
print("=== MarineDomain counters ===")
print(f"  total_smoltified:     {md.total_smoltified}")
print(f"  total_returned:       {md.total_returned}")
print(f"  total_kelts:          {md.total_kelts}")
print(f"  total_repeat_spawners:{md.total_repeat_spawners}")
print()
print("=== End-of-run life_history distribution (alive only) ===")
alive = ts.alive_indices()
for stage in LifeStage:
    cnt = int((ts.life_history[alive] == int(stage)).sum())
    if cnt > 0:
        print(f"  {stage.name:20s} {cnt}")
print()
print(f"=== Kelt roll call log: {len(kelt_call_log)} non-empty calls ===")
if kelt_call_log:
    totals = {
        "n_spawners": sum(c["n_spawners"] for c in kelt_call_log),
        "n_eligible": sum(c["n_eligible"] for c in kelt_call_log),
        "n_promoted": sum(c["n_promoted"] for c in kelt_call_log),
    }
    print(f"  Cumulative SPAWNER sightings:  {totals['n_spawners']}")
    print(f"  Cumulative eligible (cond>=0.5):{totals['n_eligible']}")
    print(f"  Cumulative kelts promoted:      {totals['n_promoted']}")
    print(f"  First 5 non-empty calls: {kelt_call_log[:5]}")
else:
    print("  ZERO non-empty calls — no fish ever reached SPAWNER state during spawning.")

print()
print(f"=== RETURNING_ADULT presence census: {len(returning_census)} days ===")
if returning_census:
    # Group by year
    from collections import defaultdict
    by_year = defaultdict(lambda: {"ra_days": 0, "ra_max": 0, "sp_days": 0})
    for date, n_ra, n_sp in returning_census:
        by_year[date.year]["ra_days"] += 1 if n_ra > 0 else 0
        by_year[date.year]["ra_max"] = max(by_year[date.year]["ra_max"], n_ra)
        by_year[date.year]["sp_days"] += 1 if n_sp > 0 else 0
    print(f"{'Year':<6}{'RA-days':<10}{'RA-max':<10}{'SP-days':<10}")
    for year in sorted(by_year):
        r = by_year[year]
        print(f"{year:<6}{r['ra_days']:<10}{r['ra_max']:<10}{r['sp_days']:<10}")
    # First arrival + last sighting
    ra_dates = [d for d, n_ra, _ in returning_census if n_ra > 0]
    if ra_dates:
        print(f"First RA date: {ra_dates[0]}, last: {ra_dates[-1]}")

print()
print(f"=== KELT/OCEAN_ADULT census: {len(kelt_census)} days with KELT or OA present ===")
if kelt_census:
    from collections import defaultdict
    by_year_k = defaultdict(lambda: {"kelt_days": 0, "kelt_max": 0, "oa_days": 0, "oa_max": 0, "sw_max": 0})
    for date, n_kelt, n_oa, sw_max in kelt_census:
        r = by_year_k[date.year]
        if n_kelt > 0:
            r["kelt_days"] += 1
            r["kelt_max"] = max(r["kelt_max"], n_kelt)
        if n_oa > 0:
            r["oa_days"] += 1
            r["oa_max"] = max(r["oa_max"], n_oa)
        r["sw_max"] = max(r["sw_max"], sw_max)
    print(f"{'Year':<6}{'K-days':<10}{'K-max':<10}{'OA-days':<10}{'OA-max':<10}{'SW-max':<10}")
    for year in sorted(by_year_k):
        r = by_year_k[year]
        print(f"{year:<6}{r['kelt_days']:<10}{r['kelt_max']:<10}{r['oa_days']:<10}{r['oa_max']:<10}{r['sw_max']:<10}")
    kelt_dates = [d for d, n_k, _, _ in kelt_census if n_k > 0]
    if kelt_dates:
        print(f"First KELT date: {kelt_dates[0]}, last: {kelt_dates[-1]}")

print()
print("=== v0.24.0 Yearly life-stage census (Dec 31 snapshots) ===")
if yearly_stage_census:
    stages = [s.name for s in LifeStage]
    header = f"{'Year':<6}" + "".join(f"{s:<10}" for s in stages)
    print(header)
    for year in sorted(yearly_stage_census):
        row = yearly_stage_census[year]
        line = f"{year:<6}" + "".join(f"{row.get(s, 0):<10}" for s in stages)
        print(line)

print()
print("=== v0.24.0 PARR length distribution (Dec 31 snapshots) ===")
if yearly_parr_lengths:
    print(f"{'Year':<6}{'n_PARR':<10}{'mean_L':<10}{'max_L':<10}{'%>=12cm':<10}")
    for year in sorted(yearly_parr_lengths):
        d = yearly_parr_lengths[year]
        print(f"{year:<6}{d['n']:<10}{d['mean_L']:<10.1f}{d['max_L']:<10.1f}{d['pct_ge12']:<10.1f}")
else:
    print("  No PARR observed at any Dec 31 snapshot.")

print()
print("=== Redd state ===")
print(f"  Alive redds at end: {int(m.redd_state.alive.sum())}")
print(f"  Total redd slots:   {len(m.redd_state.alive)}")
