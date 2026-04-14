# Gap Closure Design — v0.30.0

## Overview

Close 5 known gaps across 3 independent work streams, ordered by impact:

- **Stream A** — Smolt lifecycle closure (natal self-sustaining population)
- **Stream B** — App state management fix (post-simulation tabs render)
- **Stream C** — Adult holding + reach-junction enforcement (movement realism)

Each stream is independently testable and deployable.

---

## Stream A: Smolt Lifecycle Closure

### Problem

Parr never smoltify in the Baltic example. The 25-year calibration shows zero SMOLT, zero natal OCEAN_ADULT returns. The population sustains only via CSV adult arrivals.

**Root cause:** `marine/domain.py:285` gates readiness accumulation on `length >= smolt_min_length` (8cm). Parr emerge at 3-4cm in spring and don't reach 8cm within the DOY 90-180 smolt window of the same year. Since readiness never accumulates, the emigration trigger (`readiness >= 0.8` at `migration.py:74`) never fires.

### Design

#### A1. Decouple readiness accumulation from length gate

**File:** `src/instream/marine/domain.py`, function `accumulate_smolt_readiness()`

Current (line 285-286):
```python
if lengths[i] < min_length:
    continue  # Skip undersized parr entirely
```

Change: Remove the length check from readiness accumulation. Parr accumulate readiness based on photoperiod and temperature regardless of size. The length check remains **only** at the emigration gate in `migration.py:74`:

```python
# migration.py:74 — keep this gate
if length < smolt_min_length or smolt_readiness < 0.8:
    continue  # Must be both big enough AND physiologically ready
```

**Biology:** Physiological smoltification (silvering, Na+/K+ ATPase upregulation, osmoregulatory changes) begins months before the fish is large enough to migrate. Decoupling readiness from size matches published Atlantic salmon smolt physiology (McCormick et al. 1998, Hoar 1988).

#### A2. Persist readiness across years

**File:** `src/instream/marine/domain.py`, function `accumulate_smolt_readiness()`

Current: Readiness only accumulates during DOY 90-180. Outside this window, it doesn't change. But the daily increment of 0.05 means a single spring (90 days) yields readiness of ~4.5, instantly capping at 1.0. This means any parr that passes the length gate in spring immediately smoltifies — no multi-year build-up.

Change: Reduce the daily increment and add a winter decay so readiness builds over 2-3 springs:

```python
# Spring accumulation (DOY 90-180): slower rate
daily_increment = 0.015  # Was 0.05 — now takes ~55 days to reach 0.8
                         # But parr must survive 2-3 springs to accumulate

# Winter decay (DOY 270-365): partial reset
if doy > 270:
    smolt_readiness[i] *= 0.997  # ~30% decay over winter (90 days)
```

With this rate: Year 1 spring → 0.5 readiness. Winter decay → ~0.35. Year 2 spring → 0.35 + 0.5 = 0.85, exceeding 0.8 threshold. Fish that also exceed 8cm length will emigrate in their second spring — matching Baltic 2-year parr residency (Kallio-Nyberg et al. 2020).

#### A3. Baltic config — no changes needed

The existing `smolt_min_length: 8.0` and food parameters should work once readiness accumulates properly. Parr grow to ~9-10cm over 2 years at current drift_conc levels.

### Verification

- 25-year calibration run: SMOLT > 0 by year 3-4
- Natal OCEAN_ADULT returns by year 6-7 (2 years freshwater + 2 years sea)
- Self-sustaining population without CSV adult arrivals by year 8-10
- New test: `test_smolt_readiness_accumulates_across_years()`
- New test: `test_smolt_emigration_requires_both_length_and_readiness()`

---

## Stream B: App State Management Fix

### Problem

After simulation completes, status shows "Error — see notification" and post-simulation tabs (Population, Spatial, Size Distribution) show "Run a simulation to see results." The Dashboard live-streams correctly via the metrics queue, but `results_rv` never gets set.

**Root cause:** Shiny's `extended_task._done_callback` uses `asyncio.create_task()` which returns before the status update executes. When `_poll_progress` reads `run_sim_task.status()`, it can see stale "running" state, miss the "success" window, and the reactive chain breaks.

### Design

#### B1. Add completion signaling via queue

**File:** `app/app.py`

Instead of relying on `run_sim_task.status()` (which depends on async callback timing), have the simulation itself signal completion through the existing `_progress_q`:

```python
# In run_sim_task (line 431-439):
@reactive.extended_task
async def run_sim_task(config_path, overrides):
    data_dir = _resolve_data_dir(config_path)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: run_simulation(
            config_path, overrides, _progress_q, _metrics_q, data_dir
        ),
    )
    # Signal completion through progress queue (synchronous, no race)
    _progress_q.put(("__DONE__", result))
    return result
```

```python
# In _poll_progress (line 518-547):
# Check progress queue for completion signal
while not _progress_q.empty():
    item = _progress_q.get_nowait()
    if isinstance(item, tuple) and item[0] == "__DONE__":
        # Task completed — set results directly
        _sim_state.set("success")
        _active_task.set("none")
        results_rv.set(item[1])
        ui.notification_show("Simulation complete!", type="message", duration=3)
        return
    step, total = item
    # ... normal progress update
```

This bypasses the async status race entirely. The queue is thread-safe and checked synchronously in the poll loop.

#### B2. Clean up stale error state on new run

**File:** `app/app.py`, function `_launch()` (line 491)

Add explicit state reset before starting a new simulation:

```python
_sim_state.set("running")
results_rv.set(None)  # Clear previous results
```

### Verification

- Run Baltic example in app, verify "Complete!" status
- Switch to Population tab — should show data
- Switch to Spatial tab — should show WebGL map with cells
- Run a second simulation — should clear previous results and show new ones
- Playwright E2E test covering all tabs post-simulation

---

## Stream C: Adult Holding + Reach-Junction Enforcement

### Problem (Gap 3)

Adults arrive as `LifeStage.SPAWNER` (`model_day_boundary.py:768`) instead of `RETURNING_ADULT`. The holding behavior code in `behavior.py:633-653` (lowest-velocity cell selection, activity=4) exists but never executes because the life stage is wrong.

### Problem (Gap 4)

Daily habitat selection uses pure distance-based candidate lists. Fish cross reach boundaries freely if cells are within movement radius. Junction topology (`upstream_junction`, `downstream_junction`) is only enforced during downstream migration, not during daily movement.

### Design

#### C1. Fix adult arrival life stage (one-line fix)

**File:** `src/instream/model_day_boundary.py:768`

Change:
```python
lh_val = int(LifeStage.SPAWNER) if getattr(sp_cfg, "is_anadromous", False) else int(LifeStage.FRY)
```
To:
```python
lh_val = int(LifeStage.RETURNING_ADULT) if getattr(sp_cfg, "is_anadromous", False) else int(LifeStage.FRY)
```

#### C2. Add RETURNING_ADULT → SPAWNER transition

**File:** `src/instream/model_day_boundary.py`, function `_do_spawning()`

Before the existing spawning readiness check, add a life-stage transition:

```python
# Transition RA → SPAWNER when spawn season opens
if spawn_start_doy <= doy <= spawn_end_doy:
    ra_mask = ts.life_history[alive] == int(LifeStage.RETURNING_ADULT)
    ts.life_history[alive[ra_mask]] = int(LifeStage.SPAWNER)
```

This means:
- Adults arrive May-Aug as RETURNING_ADULT → hold in low-velocity cells (activity=4)
- When spawn season opens (Oct 15), they transition to SPAWNER
- SPAWNER fish evaluate spawn suitability and create redds (existing logic)

#### C3. Reach-aware candidate filtering

**File:** `src/instream/modules/behavior.py`, function `build_candidate_lists()`

Add a reach-connectivity filter after the distance-based candidate search:

```python
def build_candidate_lists(trout_state, fem_space, move_radius_max,
                          move_radius_L1, move_radius_L9,
                          reach_graph=None):
    # ... existing distance-based candidate building ...

    # Post-filter: restrict to current reach + connected reaches
    if reach_graph is not None:
        for i in range(n_fish):
            if candidate_lists[i] is None:
                continue
            fish_reach = int(trout_state.reach_idx[i])
            allowed_reaches = set([fish_reach]) | set(reach_graph.get(fish_reach, []))
            # Also allow upstream reaches (reverse graph)
            for r, neighbors in reach_graph.items():
                if fish_reach in neighbors:
                    allowed_reaches.add(r)
            cell_reaches = fem_space.cell_state.reach_idx[candidate_lists[i]]
            mask = np.isin(cell_reaches, list(allowed_reaches))
            candidate_lists[i] = candidate_lists[i][mask]
    
    return candidate_lists
```

**Caller update:** Pass `reach_graph=self._reach_graph` from `select_habitat_and_activity()`.

### Verification

- Test: adult arrives as RETURNING_ADULT, holds until spawn season, transitions to SPAWNER
- Test: fish in WestTrib cannot select EastTrib cells even if within radius
- Test: fish can move to connected downstream reach (WestTrib → MainStem)
- Baltic 25-year run: adults hold in river May-Oct, spawn Oct-Nov (same as current behavior but with correct life stages)

---

## Implementation Order

1. **Stream A** (smolt lifecycle) — 2 files changed, 2 new tests
2. **Stream B** (app fix) — 1 file changed, Playwright E2E
3. **Stream C** (holding + junctions) — 3 files changed, 3 new tests

Each stream is a separate commit. Deploy after all three.

---

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| SMOLT count (25yr) | 0 | > 0 by year 3-4 |
| Natal OCEAN_ADULT returns | 0 | > 0 by year 6-7 |
| Self-sustaining without CSV arrivals | No | Yes by year 8-10 |
| App post-sim tabs | "Run a simulation" | Render data |
| Adult life stage on arrival | SPAWNER | RETURNING_ADULT |
| Cross-reach movement | Unrestricted | Junction-enforced |
