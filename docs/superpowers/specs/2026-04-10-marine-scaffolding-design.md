# inSTREAM-py v0.14.0 — Marine Domain Scaffolding Design Spec

**Date:** 2026-04-10 (revised after 3-agent review)
**Current version:** 0.13.0 (729 tests, LifeStage IntEnum, InSALMON foundation)
**Target version:** 0.14.0
**Scope:** Sub-project A — marine domain skeleton, lifecycle transitions, placeholder ecology
**Part of:** InSALMON marine extension (3 sub-projects: A scaffolding, B ecology, C drivers)

---

## Motivation

The HORIZON EUROPE deliverable requires a full anadromous Atlantic salmon lifecycle model. v0.13.0 laid the freshwater foundation (LifeStage enum, outmigration probability, adult holding). v0.14.0 adds the marine domain so fish can leave freshwater as smolts, traverse marine zones, and return as spawning adults — with placeholder ecology (no real growth/survival yet, 100% marine survival).

---

## Architecture: Domain-Dispatched Step

`model.py` step() routes fish to the correct domain based on `zone_idx`:

```
InSTREAMModel.step()
  ├── time_manager.advance()
  ├── Compute freshwater_alive = alive[zone_idx == -1]
  ├── freshwater: _update_environment(freshwater_alive)
  ├── freshwater: habitat selection + fitness + survival (freshwater_alive only)
  ├── marine: marine_domain.daily_step() (zone_idx >= 0 fish only)
  ├── if is_boundary:
  │     ├── freshwater: _do_day_boundary(freshwater_alive)
  │     │     └── includes _do_migration → smolt transition at river mouth
  │     ├── _do_smolt_readiness() (accumulate for PARR fish, check threshold)
  │     ├── _do_adult_return() (check OCEAN_ADULT return conditions)
  │     └── census, sync
```

**Key decisions:**

1. **Shared TroutState**: Marine and freshwater fish in the SAME array. `zone_idx == -1` = freshwater, `zone_idx >= 0` = marine zone. No copying.

2. **Freshwater stays as mixin architecture**: Existing mixins get `freshwater_alive` mask passed through. FreshwaterDomain extraction deferred to v0.15.0.

3. **MarineDomain is a proper class**: Dependency-injected, receives references to shared state.

4. **Smolt exit happens INSIDE migration** (not in a separate lifecycle transitions method): When `migrate_fish_downstream` finds no downstream reach and marine config exists, it transitions the fish to SMOLT instead of killing it. This is the natural integration point — the fish is already at the river mouth.

5. **Smolt readiness accumulation and adult return** are separate methods called after both domains process, since they check conditions across domains.

### Freshwater guards — 10 locations requiring zone_idx filtering

The following alive-fish loops must filter to `zone_idx == -1` to prevent marine fish from corrupting freshwater operations:

| File | Location | Risk if unguarded |
|------|----------|-------------------|
| `model.py:60-73` | `select_habitat_and_activity` call | Crash: cell_idx=-1 lookup |
| `model.py:76-80` | Growth memory loop | Silent: writes meaningless growth |
| `model.py:88-101` | Fitness memory EMA loop | Silent: corrupts fitness_memory |
| `model_environment.py:168` | `_do_survival` reach_idx/cell_idx indexing | **Critical**: reach_idx=-1 wraps to last reach silently |
| `model_environment.py:271` | `_compute_piscivore_density` | Safe: has `0 <= cell < n_cells` guard |
| `model_environment.py:124` | Drift blocking loop | Silent: indexes cell_idx=-1 |
| `model_day_boundary.py:42` | Post-spawn mortality check | Silent: checks wrong fish |
| `model_day_boundary.py:204` | `_do_spawning` alive loop | **Critical**: reach_order[-1] wraps |
| `model_day_boundary.py:411` | `_do_migration` | Safe: life_history guard already present |
| `model_day_boundary.py:151` | `_apply_accumulated_growth` | Safe: cell_idx validity check already present |

**Implementation approach:** Compute `freshwater_alive = alive[self.trout_state.zone_idx[alive] == -1]` once at start of step() and pass it through. For `_do_survival`, explicitly set `survival_probs[marine_alive] = 1.0`.

---

## New State

### TroutState new fields

```python
zone_idx: np.ndarray          # int32, -1 = freshwater, 0+ = marine zone index
sea_winters: np.ndarray       # int32, years spent at sea
smolt_date: np.ndarray        # int32, ordinal date of ocean entry (-1 = never)
natal_reach_idx: np.ndarray   # int32, birth reach index (for homing), -1 = unset
smolt_readiness: np.ndarray   # float64, 0-1, accumulates with photoperiod+temp
```

**IMPORTANT:** `TroutState.zeros()` is a manual `@classmethod` that lists every field. All 5 new fields MUST be added to `zeros()` or model instantiation will crash with `TypeError`.

Initialization: `zone_idx=-1`, `smolt_date=-1`, `natal_reach_idx=-1`, `sea_winters=0`, `smolt_readiness=0.0`.

`natal_reach_idx` is set at emergence in `redd_emergence()` to the redd's `reach_idx`.

### ZoneState

```python
@dataclass
class ZoneState:
    """Environmental conditions per marine zone."""
    num_zones: int
    name: np.ndarray              # str array
    temperature: np.ndarray       # float64 (num_zones,) deg C
    salinity: np.ndarray          # float64 (num_zones,) PSU
    prey_index: np.ndarray        # float64 (num_zones,) 0-1
    predation_risk: np.ndarray    # float64 (num_zones,) 0-1
    area_km2: np.ndarray          # float64 (num_zones,)
```

---

## Marine Config Schema

```yaml
marine:
  zones:
    - name: "Estuary"
      area_km2: 50
    - name: "Coastal"
      area_km2: 500
    - name: "Baltic Proper"
      area_km2: 5000
  zone_connectivity: [[0,1], [1,2], [2,1]]
  smolt_min_length: 12.0
  smolt_readiness_threshold: 0.8
  smolt_photoperiod_weight: 0.6
  smolt_temperature_weight: 0.4
  smolt_temperature_optimal: 10.0
  smolt_window_start_doy: 90     # April 1 — earliest smoltification
  smolt_window_end_doy: 180      # June 30 — latest smoltification
  return_sea_winters: 2
  return_condition_min: 0.0      # Set to 0.0 for scaffolding (no marine growth → condition unchanged)
  static_driver:
    Estuary:
      temperature: [2,4,8,12,15,16,15,12,8,5,3,2]
      salinity: [5,5,5,5,5,5,5,5,5,5,5,5]
      prey_index: [0.2,0.3,0.5,0.7,0.8,0.8,0.7,0.5,0.3,0.2,0.1,0.1]
      predation_risk: [0.1,0.1,0.3,0.5,0.3,0.2,0.1,0.1,0.1,0.1,0.1,0.1]
    Coastal:
      temperature: [3,3,5,8,12,15,16,14,10,7,4,3]
      salinity: [7,7,7,7,7,7,7,7,7,7,7,7]
      prey_index: [0.3,0.3,0.4,0.6,0.7,0.8,0.8,0.7,0.5,0.3,0.2,0.2]
      predation_risk: [0.05,0.05,0.1,0.2,0.1,0.05,0.05,0.05,0.05,0.05,0.05,0.05]
    Baltic Proper:
      temperature: [3,2,3,5,9,13,16,15,12,8,5,3]
      salinity: [7,7,7,7,7,7,7,7,7,7,7,7]
      prey_index: [0.2,0.2,0.3,0.5,0.7,0.8,0.9,0.8,0.6,0.4,0.2,0.2]
      predation_risk: [0.02,0.02,0.02,0.05,0.05,0.05,0.05,0.05,0.02,0.02,0.02,0.02]
```

**Key fixes from review:**
- `return_condition_min: 0.0` (not 0.7) — since there's no marine growth in the scaffolding, condition stays at smoltification value. A 0.7 threshold would trap fish at sea indefinitely.
- `smolt_window_start_doy/end_doy` added — prevents unrealistic autumn smolts. Readiness only accumulates during the spring window.
- `salinity` added to static_driver tables (was missing, but ZoneState has a salinity field).

`marine` is `Optional[MarineConfig] = None` in `ModelConfig`. When absent, model runs freshwater-only (full backward compatibility).

---

## Lifecycle Transitions

### Smoltification: Two-Step Process

**Step 1 — Readiness accumulation** (`_do_smolt_readiness`, called after day boundary):

Daily check on PARR fish, only during smolt window (DOY between `smolt_window_start_doy` and `smolt_window_end_doy`):

```python
photoperiod_signal = day_length / max_day_length  # requires caching day_length in _update_environment
temp_signal = max(0, 1 - abs(temp - optimal_temp) / optimal_temp)
smolt_readiness += photoperiod_weight * photoperiod_signal + temperature_weight * temp_signal
```

Readiness resets to 0 on Jan 1. Only PARR fish checked.

**Note:** `day_length` is computed in `_update_environment` by `backend.compute_light()` but currently discarded. Must cache `self._day_length` for the smoltification trigger to use.

**Step 2 — Smolt exit at river mouth** (inside `_do_migration` → `migrate_fish_downstream`):

When a PARR fish with `smolt_readiness >= threshold AND length >= smolt_min_length` reaches a reach with no downstream neighbor:

```python
if marine_config is not None and life_history == LifeStage.PARR:
    life_history = LifeStage.SMOLT
    zone_idx = 0  # estuary
    natal_reach_idx = reach_idx  # remember home
    smolt_date = current_date.toordinal()
    cell_idx = -1
    reach_idx = -1
    # still record outmigrant statistics
else:
    alive = False  # original behavior: fish leaves system
```

This happens INSIDE the existing migration flow, not in a separate lifecycle method.

### Zone Migration (marine internal)

During `marine_domain.daily_step()`, time-based zone progression:

| Life Stage | Zone Progression | Timing |
|-----------|-----------------|--------|
| SMOLT (3) | Estuary → Coastal | After 14 days in estuary |
| SMOLT→OCEAN_JUVENILE (4) | Coastal → Baltic Proper | After 30 days in coastal |
| OCEAN_JUVENILE→OCEAN_ADULT (5) | Stays in Baltic Proper | After 1 sea-winter |

### Adult Return (marine → freshwater)

Daily check on OCEAN_ADULT fish in `_do_adult_return()`:

```python
if sea_winters >= return_sea_winters AND condition >= return_condition_min AND is_spring:
    life_history = LifeStage.RETURNING_ADULT
    zone_idx = -1
    reach_idx = natal_reach_idx
    cell_idx = random wet cell in natal reach  # MUST assign valid cell_idx
```

**Critical:** `cell_idx` MUST be set to a valid cell in the natal reach, not left at -1. Otherwise the fish will crash freshwater habitat selection on the next step. Implementation: find all cells where `cell_state.reach_idx == natal_reach_idx AND depth > 0`, pick one randomly.

`is_spring` = DOY between 90 and 180.

### Placeholder marine daily step

`marine_domain.daily_step()`:
1. Zone migration (time-based)
2. Life stage transitions (SMOLT→OCEAN_JUVENILE→OCEAN_ADULT)
3. Sea-winters increment on Jan 1
4. **No growth, no survival** — 100% survival, condition unchanged (placeholder)

Adult return check is a separate method, not inside MarineDomain.

---

## File Structure

### New files — single module for scaffolding

Review recommended a single `marine.py` instead of a 6-file package for placeholder functionality. **Compromise:** use a package but with only 3 files:

| File | Responsibility |
|------|---------------|
| `src/instream/marine/__init__.py` | Exports MarineDomain, ZoneState, StaticDriver, MarineConfig |
| `src/instream/marine/domain.py` | `MarineDomain` class + `ZoneState` dataclass + `StaticDriver` + transition functions |
| `src/instream/marine/config.py` | `MarineConfig`, `ZoneConfig` Pydantic models |
| `tests/test_marine.py` | All marine unit tests (domain, transitions, driver) |
| `tests/test_marine_e2e.py` | End-to-end lifecycle test |
| `configs/example_marine.yaml` | Example A extended with marine section |

Consolidating `zone_state.py`, `drivers.py`, and `transitions.py` into `domain.py` for the scaffolding. Decompose in v0.15.0 when Sub-project B adds real content.

### Modified files

| File | Change |
|------|--------|
| `src/instream/state/trout_state.py` | Add 5 fields to dataclass AND to `zeros()` factory |
| `src/instream/io/config.py` | Add `marine: Optional[MarineConfig] = None` to `ModelConfig` |
| `src/instream/model.py` | Compute `freshwater_alive` mask, pass to environment/behavior/survival/fitness loops. Add marine_domain.daily_step() call. Add `_do_smolt_readiness()` and `_do_adult_return()`. Cache `_day_length` from compute_light. |
| `src/instream/model_init.py` | Initialize MarineDomain if marine config present |
| `src/instream/model_environment.py` | Cache day_length. `_do_survival`: set survival_probs=1.0 for marine fish. |
| `src/instream/model_day_boundary.py` | Guard 5 alive-fish loops with freshwater_alive mask |
| `src/instream/modules/migration.py` | `migrate_fish_downstream`: smolt transition if marine config + PARR |
| `src/instream/modules/spawning.py` | `redd_emergence`: set `natal_reach_idx` on new fish |

---

## Testing

### Unit tests (`test_marine.py`)

- ZoneState creation and field access
- StaticDriver returns correct monthly temperatures and salinity
- MarineDomain.daily_step processes only zone_idx >= 0 fish
- Sea-winters increment on Jan 1
- `smoltify()` sets all fields correctly (zone_idx, smolt_date, natal_reach_idx, cell_idx=-1, reach_idx=-1)
- Below-min-length fish don't smoltify
- Smolt readiness only accumulates during smolt window (not autumn)
- Readiness resets on Jan 1
- Zone migration advances through zones on schedule
- Zone connectivity prevents invalid transitions
- Adult return sets valid cell_idx (not -1) in natal reach
- Return only in spring (DOY 90-180)
- Return blocked when condition < return_condition_min
- Return blocked when sea_winters < threshold
- **Condition-gate test:** with return_condition_min=0.0, fish always return (scaffolding default)
- **cell_idx validity test:** returned adult has cell_idx in range [0, num_cells) with correct reach

### End-to-end test (`test_marine_e2e.py`)

- Load `example_marine.yaml` with 3 zones
- Seed 100 PARR fish at length 13 cm
- Run 730 days (2 years)
- Assert: some fish smoltified
- Assert: some fish returned as RETURNING_ADULT
- Assert: returned adults have valid cell_idx (not -1)
- Assert: returned adults have natal_reach_idx matching birth reach
- Assert: freshwater-only fish still work normally
- Marked `@pytest.mark.slow`

### Backward compatibility test (in `test_marine_e2e.py`)

- Run existing Example A config (no `marine` key) for 30 days
- Assert: zone_idx stays -1 for all fish
- Assert: test count and behavior identical to v0.13.0

### Edge case tests

- Fish entering marine mid-December → sea_winters increments after ~2 weeks (not a full winter)
- Misconfigured zone_connectivity with unreachable zone → fish stays in current zone
- All fish smoltify and leave → freshwater empty but simulation continues

---

## Timeline Estimate

| Days | Task | Deliverable |
|------|------|-------------|
| 1-2 | TroutState fields (+ zeros() update) + ZoneState + MarineConfig | State layer complete |
| 3-4 | StaticDriver + MarineDomain skeleton + transition functions | Marine domain processes fish |
| 5-6 | Freshwater zone_idx guards (10 locations) + _do_survival marine exclusion | Freshwater safe with marine fish present |
| 7-8 | Smolt readiness + smolt exit in migration.py + day_length caching | Fish transition freshwater→marine |
| 9-10 | Adult return + valid cell_idx assignment + natal_reach_idx at emergence | Fish return marine→freshwater |
| 11-12 | End-to-end test + backward compat + edge cases | Full lifecycle verified |
| 13-14 | Documentation and release | v0.14.0 shipped |

**Expected: 14 working days.** Best case 11, worst case 18.

---

## Out of Scope (v0.15.0+)

- Marine growth bioenergetics (Sub-project B)
- 7 marine survival sources (Sub-project B)
- Fishing module with gear selectivity (Sub-project B)
- NetCDF environmental driver (Sub-project C)
- WMS environmental driver (Sub-project C)
- FreshwaterDomain class extraction from mixins (retires zone_idx guard debt)
- Multi-generation simulation
