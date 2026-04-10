# inSALMON Design Document

**Date:** 2026-04-08
**Status:** Draft
**Scope:** Full anadromous Baltic Atlantic salmon lifecycle model extending inSTREAM-py

---

## 1. Overview

Expand the existing inSTREAM-py individual-based model into **inSALMON** — a full-lifecycle model for Baltic Atlantic salmon (*Salmo salar*). This goes beyond the original inSALMO (Railsback & Harvey), which covers only freshwater stages. inSALMON adds marine phases: smolt outmigration, ocean growth/survival, fishing mortality, and adult return — coupled to real EMODnet/HELCOM oceanographic data.

### Key Decisions

| Aspect | Decision |
|--------|----------|
| **Species** | Baltic Atlantic salmon (*Salmo salar*) |
| **Marine spatial** | 3-5 configurable zones, coupled to EMODnet/HELCOM data |
| **Generations** | Single cohort first, designed for multi-gen later |
| **Integration** | Unified model, domain-dispatched step architecture |
| **Freshwater domain** | Handles fry, parr, returning adults, spawners (+ redds) |
| **Marine domain** | Handles smolts, ocean juveniles, ocean adults |
| **Marine survival** | 7 sources: seal, cormorant, background, temperature, M74, fishing harvest, bycatch |
| **Fishing** | Gear-specific selectivity curves, bycatch mortality, seasonal/zone closures |
| **Environmental drivers** | Static (YAML) -> NetCDF -> WMS (progressive) |
| **Backward compatibility** | Old configs run freshwater-only, existing tests unaffected |

---

## 2. Architecture: Domain-Dispatched Step

The model has two domains: `FreshwaterDomain` (current inSTREAM logic, largely unchanged) and `MarineDomain` (new). Both domains share the same `TroutState` SoA array — a fish is always one row, it just changes which domain processes it based on `life_history`.

```
InSTREAMModel.step()
  |-- FreshwaterDomain.step(trout_state)  # processes life_history 0,1,2,6
  |-- MarineDomain.step(trout_state)      # processes life_history 3,4,5
  +-- lifecycle_transitions(trout_state)  # smolt exit, adult return
```

---

## 3. Lifecycle & Domain Ownership

```
FRESHWATER DOMAIN                    MARINE DOMAIN
-----------------                    -------------
Egg (redd)
  | emergence
Fry (life_history=0)
  | growth
Parr (life_history=1)
  | smoltification trigger
Smolt (life_history=3) ---------->  Estuary (life_history=3)
                                       | transition
                                     Ocean juvenile (life_history=4)
                                       | 1-3 sea-winters
                                     Ocean adult (life_history=5)
                                       | return trigger
Returning adult (life_history=6) <-- Returning adult (life_history=6)
  | upstream migration
Spawner (life_history=2)
  | spawn
  -> Post-spawn death (semelparous)
  -> or kelt survival (iteroparous, optional for multi-gen)
```

### life_history enum

| Value | Stage | Domain | Description |
|-------|-------|--------|-------------|
| 0 | Fry / Resident | Freshwater | Post-emergence juveniles, also used for resident trout |
| 1 | Parr | Freshwater | Anadromous juvenile, pre-smolt |
| 2 | Spawner | Freshwater | Active spawner, dies post-spawn (semelparous) |
| 3 | Smolt | Marine | Transitioning through estuary to ocean |
| 4 | Ocean juvenile | Marine | Feeding in open Baltic |
| 5 | Ocean adult | Marine | Mature, pre-return |
| 6 | Returning adult | Freshwater | Migrating upstream to natal reach |

### MIGRATION NOTE: life_history enum renumbering

The current codebase uses: 0=resident, 1=anad_juve, 2=anad_adult. The new enum
reassigns meanings to values 1 and 2. The following hardcoded sites **must** be
updated during implementation:

| File | Line | Current code | Required change |
|------|------|-------------|-----------------|
| `model.py` | ~1325 | `lh_val = 2` for adult arrivals | Change to `lh_val = 6` (returning_adult), add upstream migration before spawner transition |
| `model.py` | ~750 | `life_history[i] == 2` post-spawn death | Stays 2 (spawner) — semantically correct under new enum |
| `migration.py` | 24 | `life_history != 1` guards migration | Stays 1 (parr) — semantically correct, but add smolt (3) check |
| `app/simulation.py` | ~399 | `_LIFE_HISTORY_COLORS` dict maps 0/1/2 | Extend with entries for 3-6 (marine stages) |
| `tests/test_spawning.py` | ~357 | Hardcoded `life_history=2` | Update to use named constants, not magic numbers |

**Recommendation**: Introduce a `LifeStage` IntEnum to replace magic numbers across
the codebase. This eliminates silent breakage from enum renumbering:

```python
class LifeStage(IntEnum):
    FRY = 0
    PARR = 1
    SPAWNER = 2
    SMOLT = 3
    OCEAN_JUVENILE = 4
    OCEAN_ADULT = 5
    RETURNING_ADULT = 6
```

---

## 4. Spatial Architecture

### Freshwater (unchanged)

```
FEMSpace
+-- CellState (depth, velocity, area, light per cell)
+-- Reach grouping (cells belong to reaches)
+-- Hydraulic tables (flow -> depth/velocity interpolation)
+-- KD-tree neighbor queries
+-- Reach graph (upstream/downstream connectivity)
```

### Marine: MarineSpace (new)

```
MarineSpace
+-- ZoneState (per-zone environmental conditions)
|   +-- temperature (from HELCOM/EMODnet SST)
|   +-- salinity
|   +-- prey_index (derived from chlorophyll-a)
|   +-- predation_risk (seal density, cormorant pressure)
|   +-- area_km2 (zone extent)
+-- Zone connectivity graph
+-- Seasonal migration routes (zone sequences by month)
+-- Environmental driver interface
```

### Proposed Baltic zones

| Zone | Name | Description |
|------|------|-------------|
| 0 | Estuary | River mouth, brackish transition |
| 1 | Coastal nearshore | First sea-year feeding |
| 2 | Southern Baltic Proper | Main feeding ground |
| 3 | Central Baltic Proper | Main feeding ground |
| 4 | Return corridor | Logical zone for return navigation |

Zones are configured in YAML, not hardcoded. A simpler setup could use just 2 zones (estuary + open Baltic).

### Domain boundary

The river mouth is where `FEMSpace` meets `MarineSpace`:
- **Smolt exit**: Currently `migrate_fish_downstream` (migration.py:42-43) kills fish
  with no downstream reach and records them as outmigrants. This function **must be
  modified** to detect anadromous smolts and instead set `life_history=3`, `zone_idx=0`,
  keeping the fish alive. The outmigrant record should still be created for statistics.
- **Adult return**: Marine domain triggers return -> sets `life_history=6`, `reach_idx` = most-downstream reach

### Environmental data coupling

```
EnvironmentalDriver (protocol)
+-- get_zone_conditions(zone_id, date) -> ZoneConditions
+-- Implementations:
    +-- StaticDriver  -- fixed seasonal tables from YAML (for testing)
    +-- NetCDFDriver  -- reads pre-downloaded HELCOM/Copernicus netCDF files
    +-- WMSDriver     -- fetches from EMODnet/HELCOM WMS (for live runs)
```

---

## 5. State Management

### New fields in TroutState

```python
zone_idx: np.ndarray          # int32, -1 when in freshwater
sea_winters: np.ndarray       # int32, years spent at sea
smolt_date: np.ndarray        # int32, julian day of ocean entry (ordinal)
natal_reach_idx: np.ndarray   # int32, birth reach (for homing)
smolt_readiness: np.ndarray   # float64, 0-1, accumulates with photoperiod+temp
```

**Derived field**: `days_since_ocean_entry` is NOT stored — it is computed on-the-fly
in `MarineDomain.daily_step()` as `current_date.toordinal() - smolt_date[i]` before
passing to `marine_survival()`. This avoids an extra array that would need daily
updates. The derivation is only needed for the post-smolt vulnerability window
(first ~60 days at sea; Thorstad et al. 2012).

### Domain-aware indexing

- `zone_idx >= 0` -> fish is in marine domain, `cell_idx`/`reach_idx` ignored
- `zone_idx == -1` -> fish is in freshwater domain, `cell_idx`/`reach_idx` active

Smoltification transition:
```python
trout_state.life_history[i] = 3
trout_state.zone_idx[i] = 0
trout_state.natal_reach_idx[i] = trout_state.reach_idx[i]
```

Adult return transition:
```python
trout_state.life_history[i] = 6
trout_state.zone_idx[i] = -1
trout_state.reach_idx[i] = trout_state.natal_reach_idx[i]
```

### New: ZoneState

```python
@dataclass
class ZoneState:
    temperature: np.ndarray      # deg C
    salinity: np.ndarray         # PSU
    prey_index: np.ndarray       # 0-1, normalized from chlorophyll-a
    predation_risk: np.ndarray   # 0-1, seal/cormorant pressure
    area_km2: np.ndarray         # zone extent
```

### ReddState -- unchanged

---

## 6. Model Step Sequence

```python
def step(self):
    self.time_manager.advance()

    # Update environmental conditions for both domains
    self.freshwater_domain.update_environment(self.time_manager)
    self.marine_domain.update_environment(self.time_manager)

    # Sub-daily loop (freshwater only)
    for substep in range(self.steps_per_day):
        self.freshwater_domain.substep(self.trout_state, substep)

    # Daily boundary
    self.freshwater_domain.daily_step(self.trout_state, self.redd_state)
    self.marine_domain.daily_step(self.trout_state)

    # Lifecycle transitions
    self._do_lifecycle_transitions()

    # Census & sync
    self._collect_census_if_needed()
    sync_trout_agents(self)
```

### FreshwaterDomain

Refactored extraction of current `model.py` step logic:
- `update_environment()`: reach state, hydraulics, light
- `substep()`: resource init, habitat selection, growth memory, survival (only zone_idx == -1 fish)
- `daily_step()`: growth application, splitting, spawning, post-spawn death, redd step, migration (smolt trigger instead of death), adult arrival handling (life_history 6->2), age increment

**Extraction approach**: `FreshwaterDomain.__init__` receives references to shared
model state via dependency injection — not copies. This keeps coupling explicit:

```python
class FreshwaterDomain:
    def __init__(self, fem_space, reach_state, reach_graph, reach_hydraulic_data,
                 backend, species_params, reach_params, spawn_tables, rng,
                 time_manager, outmigrant_tracker):
        # All references, not copies — domain mutates shared state
```

The 227+ `self.` accesses in current `model.py` map to these ~11 injected dependencies.
`InSTREAMModel` becomes a thin orchestrator that owns the state and delegates to domains.

### MarineDomain

New, simpler than freshwater:
- `update_environment()`: fetch zone conditions from driver
- `daily_step()`: marine growth, marine survival (7 sources incl. cormorant), seasonal zone movement, maturation check, sea_winters increment

---

## 7. Backend Architecture

### Freshwater: ComputeBackend (unchanged)

All 10 existing methods remain. numpy/jax/numba implementations untouched.

### Marine: MarineBackend (new protocol)

```python
@runtime_checkable
class MarineBackend(Protocol):

    def marine_growth(
        self, lengths, weights, temperatures, prey_indices, **species_params
    ) -> np.ndarray: ...

    def marine_survival(
        self, lengths, weights, conditions, temperatures,
        predation_risks, zone_indices, days_since_ocean_entry,
        **species_params
    ) -> np.ndarray:
        """Returns survival probability (0-1). Includes seal, cormorant,
        background, temperature, M74. Cormorant active only in estuary/coastal.
        Post-smolt vulnerability multiplier decays with days_since_ocean_entry."""
        ...

    def fishing_mortality(
        self, lengths, zone_indices, current_date, gear_configs
    ) -> tuple[np.ndarray, np.ndarray]: ...

    def maturation_check(
        self, lengths, conditions, sea_winters, **species_params
    ) -> np.ndarray: ...
```

### Marine growth model

Simplified bioenergetics (no cell-level competition):
```
daily_consumption = CMax(weight, temp) * prey_index * condition_modifier
daily_respiration = Resp(weight, temp)
daily_growth = (consumption - respiration) * growth_efficiency
```

### Marine survival: 7 mortality sources

| # | Source | Function | Baltic notes |
|---|--------|----------|-------------|
| 1 | Seal predation | Size-dependent logistic (larger = more risk) | Grey seal ~50,000 in Baltic; direct mortality 5-15%, scar prevalence up to 30% (Hansson et al.) |
| 2 | Cormorant predation | Size-dependent, active in estuary/coastal zones | 23-79% smolt loss in estuaries (Dalalven study, Fielder et al. 2009); primarily affects post-smolts <20 cm |
| 3 | Background mortality | Constant daily rate | Disease, other predators |
| 4 | Temperature stress | Threshold-based (>20 deg C) | Climate change scenarios |
| 5 | M74 syndrome | Probability per cohort | Thiamine deficiency; 50-80% fry mortality in 1990s, <10% in 2003-2005; linked to sprat abundance |
| 6 | Fishing: legal harvest | Gear selectivity + effort, removes fish | ICES TAC regulated |
| 7 | Fishing: bycatch | Sublegal catch + handling mortality | Gear-dependent |

**Post-smolt vulnerability window**: The first 2-4 weeks at sea are the critical
survival bottleneck (Thorstad et al. 2012). Cormorant predation and size-dependent
background mortality should be elevated during the estuary/coastal transition
(life_history=3, zone 0-1). Implement as a multiplier on mortality sources that
decays with days-since-ocean-entry.

---

## 8. Fishing Mortality

### Gear types with selectivity curves

```yaml
gear_types:
  trap_net:
    selectivity_type: "logistic"      # knife-edge retention above L50
    selectivity_L50: 55.0             # cm
    selectivity_slope: 3.0
    bycatch_mortality: 0.10           # 10% undersized die from handling
    zones: [estuary, coastal]
    open_months: [6, 7, 8, 9]
    daily_effort: 0.003

  drift_net:
    selectivity_type: "normal"        # bell curve size range
    selectivity_mean: 70.0
    selectivity_sd: 8.0
    bycatch_mortality: 0.85           # high mortality, gill entanglement
    zones: [coastal, south_baltic]
    open_months: []                   # BANNED: EU drift net ban since 2008
    daily_effort: 0.002

  longline:
    selectivity_type: "logistic"
    selectivity_L50: 50.0
    selectivity_slope: 5.0
    bycatch_mortality: 0.30
    zones: [south_baltic, central_baltic]
    open_months: []                   # banned under current Baltic policy
    daily_effort: 0.001

  trolling:
    selectivity_type: "logistic"      # hook-based, size-selective
    selectivity_L50: 60.0             # cm, similar to legal size
    selectivity_slope: 4.0
    bycatch_mortality: 0.15           # moderate handling mortality
    zones: [coastal, south_baltic]
    open_months: [5, 6, 7, 8, 9]     # recreational/commercial trolling season
    daily_effort: 0.002               # significant near Bornholm
```

### Per-encounter logic

```
encounter = random() < daily_effort
if encounter:
    retention = selectivity(length, gear_params)
    if random() < retention:
        if length >= min_legal_length:
            -> LANDED (removed, counted in harvest statistics)
        else:
            -> RELEASED, but random() < bycatch_mortality -> DEAD
    else:
        -> ESCAPED
```

### Harvest tracking

```python
@dataclass
class HarvestRecord:
    date: date
    zone: str
    gear_type: str
    num_landed: int
    num_bycatch_killed: int
    mean_length_landed: float
    total_weight_landed_kg: float
```

---

## 9. Configuration

### New YAML sections (additions to existing config)

```yaml
reaches:
  lower_river:
    is_river_mouth: true              # NEW: marks smolt exit point

species:
  atlantic_salmon:
    is_anadromous: true
    # existing freshwater params unchanged...

    # Smoltification parameters
    smolt_min_length: 12.0
    smolt_photoperiod_threshold: 14
    smolt_temp_min: 6.0
    smolt_temp_max: 16.0
    smolt_readiness_rate: 0.02          # ~50 qualifying days (~350-400 degree-days at 7-8°C; Handeland et al. 1998)
    smolt_window_start: "04-01"
    smolt_window_end: "06-30"

    # Marine biology
    marine_cmax_A: 0.303              # Hanson et al. 1997, Fish Bioenergetics 3.0
    marine_cmax_B: -0.275             # Hanson et al. 1997
    marine_growth_efficiency: 0.50    # K2 net growth efficiency (conservative)
    marine_mort_seal_L1: 40.0
    marine_mort_seal_L9: 80.0
    marine_mort_seal_max_daily: 0.02  # max 2% daily mortality for largest fish
    marine_mort_base: 0.001
    marine_mort_cormorant_L1: 15.0    # cormorant predation logistic (Jepsen et al. 2019)
    marine_mort_cormorant_L9: 40.0    # primarily affects smolts <40 cm
    marine_mort_cormorant_max_daily: 0.03  # max 3% daily mortality for smallest smolts
    marine_mort_cormorant_zones: [estuary, coastal]  # only active in nearshore
    marine_mort_m74_prob: 0.0
    maturation_min_sea_winters: 1
    # Conditional maturation probabilities: probability of maturing GIVEN the
    # fish has survived to this sea-winter and has not yet matured.
    # Worked example (ignoring marine mortality for clarity):
    #   1000 smolts enter ocean
    #   After 1SW: 0.15 * 1000 = 150 return (15%), 850 remain
    #   After 2SW: 0.59 * 850  = 501 return (50% of original), 349 remain
    #   After 3SW: 0.86 * 349  = 300 return (30% of original), 49 remain
    #   After 4SW: 0.99 * 49   =  49 return (5% of original), ~0 remain
    maturation_prob_1SW: 0.15          # conditional: P(mature | survived 1SW)
    maturation_prob_2SW: 0.59          # conditional: P(mature | survived 2SW, not yet mature)
    maturation_prob_3SW: 0.86          # conditional: P(mature | survived 3SW, not yet mature)
    maturation_prob_4SW: 0.99          # conditional: P(mature | survived 4SW, not yet mature)
    maturation_min_length: 55.0
    maturation_min_condition: 0.8

    # Fishing (see Section 8 for gear_types detail)
    marine_fishing:
      min_legal_length: 60.0
      gear_types: { ... }

marine:
  enabled: true
  time_step: "daily"

  zones:
    estuary:
      area_km2: 50
      connections: [coastal]
      residence_days: [14, 30]
    coastal:
      area_km2: 5000
      connections: [estuary, south_baltic]
    south_baltic:
      area_km2: 120000
      connections: [coastal, central_baltic]
    central_baltic:
      area_km2: 150000
      connections: [south_baltic]

  environment:
    driver: "static"
    static:
      estuary:
        temperature: {1: 2.0, 4: 6.0, 7: 18.0, 10: 10.0}
        salinity: {1: 7.0, 7: 6.5}
        prey_index: {1: 0.2, 5: 0.8, 8: 0.6, 11: 0.3}
        predation_risk: {1: 0.3, 6: 0.5, 10: 0.3}
    netcdf:
      sst_file: "baltic_sst.nc"
      chl_file: "baltic_chl.nc"
      zone_polygons: "zone_boundaries.geojson"
    wms:
      sst_endpoint: "https://nrt.cmems-du.eu/thredds/wms/..."
      chl_endpoint: "https://nrt.cmems-du.eu/thredds/wms/..."
```

### Backward compatibility

- `marine` section absent -> model runs freshwater-only
- New TroutState fields default to inert values (-1, 0)
- All existing tests pass without modification

**Config loader note**: The root `ModelConfig` Pydantic model in `io/config.py` (line
~237) is a plain `BaseModel` with no `extra` setting — Pydantic v2 defaults to
`extra='ignore'`, so unknown YAML keys are silently dropped. This means adding a
`marine:` section to YAML without updating the code would appear to work but the
marine config would never be loaded. `ModelConfig` **must** be updated to add
`marine: Optional[MarineConfig] = None` so the section is validated and populated.
A new `MarineConfig` Pydantic model (with `ZoneConfig`, `GearConfig`, etc.) should
be added to `io/config.py` or a new `io/marine_config.py`.

---

## 10. Testing & Validation

### Unit tests

| Module | Approach |
|--------|----------|
| `marine_growth` | Known inputs -> expected weight change vs published growth curves |
| `marine_survival` | Each source isolated; seal predation increases with length |
| `fishing_mortality` | Selectivity curves match analytical shape; bycatch only undersized |
| `maturation_check` | 1SW/2SW/3SW probabilities match config |
| Smoltification | Photoperiod + temp + length thresholds; only within window |
| Domain transitions | State consistency; natal_reach preserved |

### Integration tests

| Test | Verifies |
|------|----------|
| Single fish lifecycle | Egg -> fry -> parr -> smolt -> ocean -> return -> spawn -> death |
| Cohort survival | 10k smolts, 5-10% return after 2y (matches ICES data) |
| Freshwater unchanged | Existing tests pass with no marine config |
| Fishing scenarios | Close fisheries -> higher returns; increase effort -> lower returns |
| Driver parity | Static tables vs synthetic netCDF -> identical results |

### Empirical validation targets

| Metric | Expected range | Source |
|--------|---------------|--------|
| Smolt-to-adult return rate | 2-15% | ICES WGBAST reports |
| 1SW return length | 55-70 cm | Todd et al. 2008, Jutila et al. |
| 2SW return length | 70-90 cm | Same sources |
| Sea age at return | ~15% 1SW, ~50% 2SW, ~30% 3SW, ~5% 4SW+ | ICES WGBAST; Tornionjoki data (Jutila et al. 2003) |
| Fishing mortality rate | F = 0.1-0.4 | ICES advice |
| Seal predation: direct mortality | 5-15% | Hansson et al. 2018 |
| Seal predation: scar prevalence | up to 30% | Lundstrom et al. |
| Cormorant smolt predation | 23-79% in estuaries | Fielder et al. 2009 (Dalalven) |

---

## 11. File Structure (new/modified)

```
src/instream/
+-- domains/                         # NEW
|   +-- __init__.py
|   +-- freshwater.py                # FreshwaterDomain (extracted from model.py)
|   +-- marine.py                    # MarineDomain
|   +-- transitions.py               # lifecycle_transitions logic
+-- space/
|   +-- fem_space.py                 # unchanged
|   +-- marine_space.py              # NEW: MarineSpace + ZoneState
+-- backends/
|   +-- _interface.py                # unchanged
|   +-- _marine_interface.py         # NEW: MarineBackend protocol
|   +-- numpy_backend/
|   |   +-- __init__.py              # unchanged
|   |   +-- marine.py                # NEW: NumpyMarineBackend
+-- modules/
|   +-- migration.py                 # MODIFIED: smolt transition instead of death at river mouth
|   +-- (all other existing unchanged)
|   +-- marine_growth.py             # NEW
|   +-- marine_survival.py           # NEW
|   +-- marine_fishing.py            # NEW
|   +-- smoltification.py            # NEW
|   +-- marine_migration.py          # NEW: zone-to-zone movement
+-- io/
|   +-- config.py                    # MODIFIED: add MarineConfig, ZoneConfig, GearConfig
|   +-- env_drivers/                 # NEW
|   |   +-- __init__.py
|   |   +-- static_driver.py
|   |   +-- netcdf_driver.py
|   |   +-- wms_driver.py
+-- state/
|   +-- trout_state.py               # MODIFIED: 5 new fields
|   +-- cell_state.py                # unchanged
|   +-- redd_state.py                # unchanged
|   +-- zone_state.py                # NEW
+-- model.py                         # MODIFIED: domain dispatch
```

---

## 12. Known Gaps for Future Work (Multi-Generation Phase)

| Gap | Notes | Priority |
|-----|-------|----------|
| **Straying** | Baltic salmon stray to non-natal rivers at 1-5% rate. Not needed for single-river single-cohort, critical for multi-river multi-gen scenarios. | Phase 2 |
| **Kelt survival** | Iteroparous repeat spawning. Some Baltic salmon survive post-spawn and return to sea. Add as optional pathway from spawner -> kelt -> ocean. | Phase 2 |
| **Density dependence** | Freshwater carrying capacity limits on returning adults/redds. Required for population equilibrium in multi-gen runs. | Phase 2 |
| **Hatchery fish** | Many Baltic rivers have supplementary stocking. Model hatchery-origin vs wild-origin fish with different fitness/survival. | Phase 2 |
| **Gyrodactylus salaris** | Devastating parasite in some Norwegian rivers; not established in most Baltic salmon rivers. Monitor but low priority. | Phase 3 |

---

## 13. References

### Key publications

- ICES WGBAST. Baltic Salmon and Trout Assessment Working Group reports. https://ices-library.figshare.com/articles/report/Baltic_Salmon_and_Trout_Assessment_Working_Group_WGBAST_/25868665
- Todd, C.D. et al. (2008). Detrimental effects of recent ocean surface warming on growth condition of Atlantic salmon. *Global Change Biology* 14(5):958-970.
- Jutila, E. et al. (2003). Postsmolt migration of Atlantic salmon in the northern Baltic Sea area. *ICES Journal of Marine Science* 60(2):329-335.
- Hansson, S. et al. (2018). Competition for the fish — fish extraction from the Baltic Sea by humans, aquatic mammals, and birds. *ICES Journal of Marine Science* 75(3):999-1008.
- Fielder, D. et al. (2009). Great cormorant predation on fish in a Swedish river. *Fisheries Management and Ecology* 16(3):193-199.
- Thorstad, E.B. et al. (2012). A critical life stage of the Atlantic salmon *Salmo salar*: behaviour and survival during the smolt and initial post-smolt migration. *Journal of Fish Biology* 81(2):500-542.
- Jacobson, P. et al. (2020). Genetic and environmental influences on the distribution of Atlantic salmon (*Salmo salar*) at sea. *ICES Journal of Marine Science* 77(3):1037-1049. https://pmc.ncbi.nlm.nih.gov/articles/PMC7028083/
- Keinanen, M. et al. (2024). M74 syndrome in Baltic salmon. *Fishes* 9(2):58. https://www.mdpi.com/2410-3888/9/2/58
- Railsback, S.F. & Harvey, B.C. inSTREAM 7 and inSALMO 7 model descriptions. https://www.humboldt.edu/ecological-modeling/instream-and-insalmo

### Data sources

- ICES WGBAST: Stock-specific smolt-to-adult return rates, sea-age distributions, fishing mortality estimates
- Copernicus Marine Service (CMEMS): Baltic SST, chlorophyll-a for environmental drivers
- EMODnet: Bathymetry, habitat layers
- HELCOM: Environmental monitoring data, seal population estimates
