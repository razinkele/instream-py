# inSTREAM-py v0.14.0 — Marine Domain Scaffolding Design Spec

**Date:** 2026-04-10
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
  ├── freshwater: _update_environment() (zone_idx == -1 fish only)
  ├── freshwater: habitat selection + survival (zone_idx == -1 fish only)
  ├── marine: marine_domain.daily_step() (zone_idx >= 0 fish only)
  ├── if is_boundary:
  │     ├── freshwater: _do_day_boundary() (growth, spawning, redds, migration)
  │     ├── _do_lifecycle_transitions() (smolt exit, adult return)
  │     └── census, sync
```

**Key decisions:**

1. **Shared TroutState**: Marine and freshwater fish live in the SAME array. `zone_idx == -1` = freshwater, `zone_idx >= 0` = marine zone index. No copying between arrays.

2. **Freshwater stays as mixin architecture**: The existing `_ModelInitMixin`, `_ModelEnvironmentMixin`, `_ModelDayBoundaryMixin` are NOT refactored into a `FreshwaterDomain` class. Freshwater logic gets `zone_idx == -1` guards added to fish loops. FreshwaterDomain extraction is a v0.15.0 cleanup.

3. **MarineDomain is a proper class**: Not a mixin — a class with dependency injection receiving references to `trout_state`, `zone_state`, `time_manager`, `marine_config`.

4. **Lifecycle transitions centralized**: Smoltification and adult return happen in `_do_lifecycle_transitions()` on the model, AFTER both domains process their fish.

---

## New State

### TroutState new fields

```python
zone_idx: np.ndarray          # int32, -1 = freshwater, 0+ = marine zone index
sea_winters: np.ndarray       # int32, years spent at sea
smolt_date: np.ndarray        # int32, ordinal date of ocean entry (-1 = never)
natal_reach_idx: np.ndarray   # int32, birth reach index (for homing)
smolt_readiness: np.ndarray   # float64, 0-1, accumulates with photoperiod+temp
```

All initialized to -1 (zone_idx, smolt_date) or 0 (sea_winters, smolt_readiness). `natal_reach_idx` set to `reach_idx` at emergence.

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
  return_sea_winters: 2
  return_condition_min: 0.7
  static_driver:
    Estuary:
      temperature: [2,4,8,12,15,16,15,12,8,5,3,2]
      prey_index: [0.2,0.3,0.5,0.7,0.8,0.8,0.7,0.5,0.3,0.2,0.1,0.1]
      predation_risk: [0.1,0.1,0.3,0.5,0.3,0.2,0.1,0.1,0.1,0.1,0.1,0.1]
    Coastal:
      temperature: [3,3,5,8,12,15,16,14,10,7,4,3]
      prey_index: [0.3,0.3,0.4,0.6,0.7,0.8,0.8,0.7,0.5,0.3,0.2,0.2]
      predation_risk: [0.05,0.05,0.1,0.2,0.1,0.05,0.05,0.05,0.05,0.05,0.05,0.05]
    Baltic Proper:
      temperature: [3,2,3,5,9,13,16,15,12,8,5,3]
      prey_index: [0.2,0.2,0.3,0.5,0.7,0.8,0.9,0.8,0.6,0.4,0.2,0.2]
      predation_risk: [0.02,0.02,0.02,0.05,0.05,0.05,0.05,0.05,0.02,0.02,0.02,0.02]
```

`marine` key is `Optional[MarineConfig] = None` in `ModelConfig`. When absent, model runs freshwater-only (full backward compatibility).

---

## Lifecycle Transitions

### Smoltification (freshwater → marine)

Daily check on PARR fish during `_do_lifecycle_transitions()`:

```python
smolt_readiness += photoperiod_weight * photoperiod_signal + temperature_weight * temp_signal
if smolt_readiness >= threshold AND length >= smolt_min_length:
    life_history = LifeStage.SMOLT
    zone_idx = 0  # estuary
    natal_reach_idx = reach_idx  # remember home
    smolt_date = current_date.toordinal()
    cell_idx = -1  # no longer in freshwater
    reach_idx = -1
```

- `photoperiod_signal`: normalized increasing day length (spring trigger)
- `temp_signal`: `1 - abs(temp - optimal_temp) / optimal_temp`, clamped [0,1]
- Readiness accumulates daily, resets to 0 on Jan 1
- Only PARR fish checked

**Integration with existing migration:** `migrate_fish_downstream` currently kills fish with no downstream reach. Modify: if fish is PARR and marine config exists, transition to SMOLT instead of killing. Still record outmigrant statistics.

### Zone Migration (marine internal)

During `marine_domain.daily_step()`, time-based zone progression:

| Life Stage | Zone Progression | Timing |
|-----------|-----------------|--------|
| SMOLT (3) | Estuary → Coastal | After 14 days in estuary |
| SMOLT→OCEAN_JUVENILE (4) | Coastal → Baltic Proper | After 30 days in coastal |
| OCEAN_JUVENILE→OCEAN_ADULT (5) | Stays in Baltic Proper | After 1 sea-winter |

Zone transitions are time-based for the scaffolding. Sub-project B adds condition-based triggers.

### Adult Return (marine → freshwater)

Daily check on OCEAN_ADULT fish:

```python
if sea_winters >= return_sea_winters AND condition >= return_condition_min AND is_spring:
    life_history = LifeStage.RETURNING_ADULT
    zone_idx = -1  # back to freshwater
    reach_idx = natal_reach_idx  # home river
    cell_idx = random cell in natal reach
```

`is_spring` = day of year between 90 and 180 (April-June).

Returning adults enter freshwater and use holding behavior (v0.13.0 Task 12) until spawn season.

### Placeholder marine daily step

For the scaffolding, `marine_domain.daily_step()`:
1. Zone migration (time-based)
2. Life stage transitions (SMOLT→OCEAN_JUVENILE→OCEAN_ADULT)
3. Sea-winters increment on Jan 1
4. Adult return check
5. **No growth, no survival** — 100% marine survival (placeholder). Sub-project B adds real mortality.

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `src/instream/marine/__init__.py` | Package init |
| `src/instream/marine/domain.py` | `MarineDomain` class |
| `src/instream/marine/zone_state.py` | `ZoneState` dataclass |
| `src/instream/marine/drivers.py` | `EnvironmentalDriver` Protocol + `StaticDriver` |
| `src/instream/marine/transitions.py` | `smoltify()`, `migrate_zone()`, `return_adult()` pure functions |
| `src/instream/marine/config.py` | `MarineConfig`, `ZoneConfig` Pydantic models |
| `tests/test_marine_domain.py` | Unit tests for MarineDomain |
| `tests/test_marine_transitions.py` | Unit tests for lifecycle transitions |
| `tests/test_marine_e2e.py` | End-to-end: freshwater → marine → return |
| `configs/example_marine.yaml` | Example A extended with marine section |

### Modified files

| File | Change |
|------|--------|
| `src/instream/state/trout_state.py` | Add 5 marine fields |
| `src/instream/io/config.py` | Add `marine: Optional[MarineConfig]` to `ModelConfig` |
| `src/instream/model.py` | Marine domain init + `_do_lifecycle_transitions()` in step() |
| `src/instream/model_init.py` | Initialize MarineDomain if marine config present |
| `src/instream/model_day_boundary.py` | Guard freshwater ops with `zone_idx == -1` |
| `src/instream/modules/migration.py` | Smolt transition instead of kill at river mouth |
| `src/instream/modules/spawning.py` | Set `natal_reach_idx` on emergence |

---

## Testing

### Unit tests

**`test_marine_domain.py`:**
- ZoneState creation and field access
- StaticDriver returns correct monthly temperatures
- MarineDomain.daily_step processes only zone_idx >= 0 fish
- Sea-winters increment on Jan 1

**`test_marine_transitions.py`:**
- `smoltify()` sets correct fields
- Below-min-length fish don't smoltify
- Smolt readiness accumulation responds to photoperiod and temperature
- Readiness resets on Jan 1
- `migrate_zone()` advances through zones on schedule
- Zone connectivity prevents invalid transitions
- `return_adult()` sets correct fields and targets natal reach
- Return only in spring (DOY 90-180)
- Return requires minimum condition and sea-winters

### End-to-end test (`test_marine_e2e.py`)

- Load `example_marine.yaml` with 3 zones
- Seed 100 PARR fish at length 13 cm (above smolt_min_length)
- Run 730 days (2 years)
- Assert: some fish smoltified (zone_idx >= 0 at some point)
- Assert: some fish returned (life_history == RETURNING_ADULT)
- Assert: freshwater fish still work normally
- Assert: returned adults have natal_reach_idx matching birth reach
- Marked `@pytest.mark.slow`

### Backward compatibility test

- Run existing Example A config (no `marine` key) for 30 days
- Assert: identical behavior to v0.13.0 (zone_idx stays -1 for all fish)

---

## Timeline Estimate

| Days | Task | Deliverable |
|------|------|-------------|
| 1-2 | TroutState fields + ZoneState + MarineConfig | State layer complete |
| 3-4 | StaticDriver + MarineDomain skeleton | Marine domain processes fish |
| 5-6 | Lifecycle transitions (smoltify, zone migrate, return) | Fish cross domain boundary |
| 7-8 | Domain-dispatched step + freshwater guards | Both domains integrated |
| 9 | Modify migration.py (smolt exit at river mouth) | Natural smolt transition |
| 10-11 | End-to-end test + backward compat test | Full lifecycle verified |
| 12 | Documentation and release | v0.14.0 shipped |

**Expected: 12 working days.** Best case 10, worst case 16.

---

## Out of Scope (v0.15.0+)

- Marine growth bioenergetics (Sub-project B)
- 7 marine survival sources (Sub-project B)
- Fishing module with gear selectivity (Sub-project B)
- NetCDF environmental driver (Sub-project C)
- WMS environmental driver (Sub-project C)
- FreshwaterDomain class extraction from mixins
- Multi-generation simulation
