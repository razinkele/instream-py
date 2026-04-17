# HexSimPy (salmon_ibm) vs inSTREAM-py (salmopy) — Feature Comparison & Integration Opportunities

**Date:** 2026-04-16  
**Purpose:** Compare the two salmon IBM codebases and identify features from HexSimPy that could strengthen inSTREAM-py.

---

## 1. Architecture Comparison

| Aspect | HexSimPy (salmon_ibm) | inSTREAM-py (salmopy) |
|--------|----------------------|----------------------|
| **Framework** | Custom lightweight (numpy/scipy) | Mesa-based with custom extensions |
| **Agent storage** | AgentPool (structure-of-arrays) | TroutState / ReddState (structure-of-arrays) |
| **Time step** | Hourly (fixed) | Flexible sub-daily (1, 2, 4+ steps/day) |
| **Spatial domain** | Triangular mesh (Delaunay) OR HexSim hexagonal grid | FEM mesh (polygon/structured) with KD-tree |
| **Target species** | Baltic salmon (*Salmo salar*) — non-feeding migrants | Multi-species salmonids (trout, salmon, sea trout) |
| **Life cycle scope** | Single migration event (estuary → spawning ground) | Full life cycle (egg → fry → parr → smolt → ocean → spawner → kelt) |
| **Config format** | YAML with validation | Python dataclasses + CSV time-series |
| **Visualization** | Shiny + deck.gl (real-time mesh + agents) | Shiny + deck.gl (cells + agents) |
| **Numba JIT** | Optional for movement kernels (~3×) | Used for candidate building, growth, survival |
| **Modules** | 33 files, event-driven pipeline | ~25 core files, mixin-based model class |

---

## 2. Feature-by-Feature Comparison

| Feature | HexSimPy | inSTREAM-py | Gap |
|---------|----------|-------------|-----|
| **Life stages** | Generic (trait-based, not hardcoded) | 8 explicit stages (FRY→KELT) | inSTREAM more complete |
| **Movement** | 5 gradient-following behaviors on mesh neighbors | Fitness-based habitat selection within radius | Different paradigms |
| **Growth** | Wisconsin bioenergetics (respiration only, non-feeding) | Full bioenergetics (CMax, drift/search intake, respiration) | inSTREAM more complete |
| **Mortality — starvation** | ED < 4.0 kJ/g threshold | Condition-dependent logistic (K < 0.8 → risk) | Both valid, different formulation |
| **Mortality — thermal** | T > 26°C lethal | Logistic (T1=28, T9=24) | Similar |
| **Mortality — predation** | None (fish/terrestrial) | Fish predation + terrestrial predation (full logistics) | **inSTREAM much richer** |
| **Mortality — barriers** | ✅ Edge-based (mortality/deflection/transmission) | ❌ Implicit reach boundaries only | **HexSim advantage** |
| **Mortality — density** | Stage-specific with local density factor | Implicit via resource depletion + piscivore density | Both valid |
| **Spawning** | Basic (Poisson clutch, random grouping) | Rich (suitability scoring, superimposition, defense area, fecundity allometry) | inSTREAM much richer |
| **Redd survival** | None | 4 sources (low-T, high-T, dewatering, scour) | **inSTREAM advantage** |
| **Estuary — salinity** | ✅ Energetic cost function | ❌ Not modeled | **HexSim advantage** |
| **Estuary — DO avoidance** | ✅ Lethal + escape thresholds | ❌ Not modeled | **HexSim advantage** |
| **Estuary — seiche pause** | ✅ SSH rate detection → HOLD | ❌ Not modeled | **HexSim advantage** |
| **Marine domain** | None (migration only) | ✅ Full (3 zones, growth, 7 mortality sources) | **inSTREAM advantage** |
| **Barriers/dams** | ✅ .hbf file, directional outcomes | ❌ No explicit passage mechanics | **HexSim advantage** |
| **Genetics** | ✅ Diploid (Haldane crossover, Mendelian recombination) | ❌ None (sex + hatchery flag only) | **HexSim advantage** |
| **Traits system** | ✅ Generic (4 types: probabilistic, accumulated, genetic) | ❌ Hardcoded species parameters | **HexSim advantage** |
| **Event system** | ✅ Configurable pipeline (12+ event types, triggers) | ❌ Fixed step sequence in model.step() | **HexSim advantage** |
| **Accumulators** | ✅ 27+ updater functions, expression evaluation | ❌ Fixed memory arrays | **HexSim advantage** |
| **Multi-population** | ✅ Predator-prey interactions, spatial hashing | ⚠️ Multi-species but no inter-species interactions | **HexSim advantage** |
| **Ensemble runs** | ✅ Built-in | ⚠️ Via sensitivity module | Similar |
| **Current advection** | ✅ u/v velocity drift on mesh | ❌ Not modeled | **HexSim advantage** |
| **SSH-based migration** | ✅ Follow SSH gradients (upstream/downstream) | ❌ Migration by reach graph only | **HexSim advantage** |
| **Environmental forcing** | NetCDF (T, S, u/v, SSH, DO, discharge, wind) | CSV time-series per reach (T, flow, turbidity) | HexSim more dynamic |
| **Resource depletion** | ❌ Non-feeding model | ✅ Drift + search depletion/regeneration | inSTREAM advantage |
| **Superindividuals** | ❌ Individual agents only | ✅ Rep-based scaling | inSTREAM advantage |
| **Harvest/angling** | ❌ Not modeled (freshwater) | ✅ Size-selective, bag limits, marine fishing | inSTREAM advantage |

---

## 3. Integration Recommendations

### Priority 1 — High Impact, Moderate Effort

#### 3.1 Barrier/Dam Passage System
**Source:** `salmon_ibm/barriers.py` + movement.py barrier resolution  
**What it adds:** Explicit fish passage mechanics at dams, weirs, culverts  
**Why:** inSTREAM currently treats dams as opaque reach boundaries with no passage probability. Baltic rivers (Nemunas, Curonian) have multiple barriers affecting migration.

**Integration approach:**
- Add `BarrierMap` class to `instream/modules/` — edge-based barriers between cells or reaches
- Define barrier classes in species config: `{mortality: 0.1, deflection: 0.8, transmission: 0.1}` per direction
- Apply during migration step: when fish attempts to move between reaches, check barrier outcome
- Support `.hbf` file format or simpler CSV definition

**Estimated scope:** New module (~200 lines) + migration.py integration (~50 lines)

---

#### 3.2 Estuarine Stress Functions
**Source:** `salmon_ibm/estuary.py`  
**What it adds:** Salinity cost, dissolved oxygen avoidance, seiche pause  
**Why:** inSTREAM has a marine domain but no estuarine transition mechanics. Smolts and returning adults pass through estuaries where salinity, DO, and flow reversals affect survival and energy budgets.

**Integration approach:**
- Add `estuary.py` module to `instream/modules/`
- Salinity cost: multiplier on respiration `1 + k × max(S - S_opt - S_tol, 0)`, applied in marine growth step
- DO avoidance: if DO < threshold, force downstream movement or add mortality hazard
- Seiche pause: if SSH rate > threshold, suppress migration for that timestep
- Zone-level salinity/DO already exist in marine config — just need the cost functions

**Estimated scope:** New module (~150 lines) + marine domain integration (~30 lines)

---

#### 3.3 Genetics System (Diploid Mendelian)
**Source:** `salmon_ibm/genetics.py`  
**What it adds:** Heritable genetic traits, allele tracking, recombination  
**Why:** Enables modeling of evolutionary responses to fishing pressure, hatchery effects, climate adaptation. Currently inSTREAM only tracks hatchery origin as a boolean flag.

**Integration approach:**
- Port `GenomeManager` class: `genotypes[n_agents, n_loci, 2]` (int32 array)
- Add loci definitions to species config (name, n_alleles, position in cM)
- Haldane crossover during spawning: `P(xover) = 0.5 × (1 - exp(-2d/100))`
- Link alleles to phenotype via trait maps (e.g., run timing, growth rate, smolt age)
- Initialize randomly or from population-specific allele frequencies

**Estimated scope:** New module (~300 lines) + spawning.py integration (~50 lines)

---

### Priority 2 — Medium Impact, Low-Medium Effort

#### 3.4 Configurable Event Pipeline
**Source:** `salmon_ibm/events.py`, `events_builtin.py`  
**What it adds:** YAML-configurable simulation pipeline instead of hardcoded step sequence  
**Why:** inSTREAM's `model.step()` has a fixed order of operations. An event system would allow users to add/remove/reorder processes without code changes — valuable for scenario exploration.

**Integration approach:**
- Define event types matching existing steps (growth, survival, spawning, migration, etc.)
- Add trigger types: EveryStep, DayBoundary, Periodic, DateWindow
- YAML config section `events:` lists active events and their parameters
- Default config reproduces current fixed pipeline exactly
- Custom events via Python callback registration

**Estimated scope:** New module (~400 lines) + model.py refactor (~200 lines)

---

#### 3.5 Current Advection (Passive Drift)
**Source:** `salmon_ibm/movement.py` (advection kernel)  
**What it adds:** Fish passively transported by water currents (u/v velocity fields)  
**Why:** Important for smolt outmigration (drift with current), returning adults (fight current), and estuary passage. Currently inSTREAM movement is purely fitness-driven.

**Integration approach:**
- Add optional u/v velocity fields to reach state or cell state
- During movement step, apply displacement: `dx = u × dt, dy = v × dt`
- Convert displacement to cell transitions (nearest neighbor in flow direction)
- Scale by behavior: smolts get full advection, upstream migrants get negative advection
- Could use reach-level mean velocity as proxy if no 2D field available

**Estimated scope:** ~100 lines in movement/migration modules

---

#### 3.6 Trait System (Generic Categorical State)
**Source:** `salmon_ibm/traits.py`  
**What it adds:** Flexible per-agent categorical traits beyond hardcoded life_stage/sex  
**Why:** Enables phenotype tracking (early/late run timing, resident/anadromous decision, bold/shy behavioral type) without adding new state arrays for each trait.

**Integration approach:**
- Add `TraitManager` with named traits, each having N categories
- Store as int8 array in TroutState
- Link to accumulators or genetics for automatic evaluation
- Use for event filtering (e.g., "apply this mortality only to late-run fish")

**Estimated scope:** New module (~200 lines) + TroutState extension (~30 lines)

---

### Priority 3 — Niche but Valuable

#### 3.7 Accumulator System
**Source:** `salmon_ibm/accumulators.py`  
**What it adds:** General-purpose per-agent floating-point counters with 27+ updater functions  
**Why:** Useful for tracking arbitrary metrics (days in CWR, cumulative thermal exposure, feeding success) without modifying TroutState for each new variable.

**Integration approach:**
- Add `AccumulatorManager` with named accumulators, float64 arrays
- Updaters: increment, clear, expression-eval, transfer between accumulators
- Expression safety via AST validation
- Use in event conditions and trait evaluation

**Estimated scope:** ~250 lines, standalone module

---

#### 3.8 Multi-Population Interactions
**Source:** `salmon_ibm/interactions.py`  
**What it adds:** Explicit predator-prey spatial interactions between populations  
**Why:** inSTREAM models piscivore density as a per-cell count of large fish, but doesn't model predator agents explicitly. HexSim's approach allows pike, cormorants, or seals as actual agent populations.

**Integration approach:**
- Register secondary populations (predators, competitors)
- Spatial hashing for co-location queries
- InteractionEvent: when predator and prey share a cell, apply predation probability
- Predator agents could have their own simple movement/mortality

**Estimated scope:** Major feature (~500+ lines), best as a v2.0 item

---

#### 3.9 Starvation Mortality (Mass-Based Threshold)  
**Source:** `salmon_ibm/bioenergetics.py` (ED < 4.0 kJ/g, mass floor 50%)  
**What it adds:** Alternative starvation metric complementary to condition factor  
**Why:** inSTREAM uses condition K (weight/expected_weight) for starvation risk. HexSim uses energy density (kJ/g). Both are valid; using both could improve robustness.

**Integration approach:**
- Add `energy_density` field to TroutState (computed from weight + lipid reserves)
- Track `max_lifetime_mass` for 80%-of-max threshold (SalmonidNetworkIBM approach)
- Apply as additional mortality source in survival module
- Particularly relevant for non-feeding RETURNING_ADULT and KELT stages

**Estimated scope:** ~50 lines in survival.py + TroutState field

---

## 4. Summary Matrix

| Feature | Priority | Effort | Impact | Dependencies |
|---------|----------|--------|--------|--------------|
| Barrier/dam passage | **P1** | Medium | High | migration.py |
| Estuarine stress | **P1** | Low-Med | High | marine domain |
| Genetics (diploid) | **P1** | Medium | High | spawning.py |
| Event pipeline | **P2** | Med-High | Medium | model.py refactor |
| Current advection | **P2** | Low | Medium | movement, reach state |
| Trait system | **P2** | Low-Med | Medium | TroutState |
| Accumulators | **P3** | Medium | Low-Med | standalone |
| Multi-population | **P3** | High | Medium | major new feature |
| ED-based starvation | **P3** | Low | Low-Med | survival.py |

---

## 5. What inSTREAM Already Does Better

These areas are **stronger in inSTREAM** and should NOT be replaced by HexSim equivalents:

| Feature | inSTREAM Advantage |
|---------|-------------------|
| **Full life cycle** | 8 stages vs. single migration event |
| **Feeding bioenergetics** | CMax, drift/search intake, prey capture — HexSim has respiration only |
| **Predation mortality** | Fish + terrestrial predation with full logistic models — HexSim has none |
| **Spawning mechanics** | Suitability scoring, superimposition, defense area — HexSim is basic |
| **Redd survival** | 4 mortality sources — HexSim has none |
| **Resource dynamics** | Drift/search depletion and regeneration — HexSim is non-feeding |
| **Marine domain** | 3-zone growth + 7 mortality sources — HexSim has no marine |
| **Superindividuals** | Rep-based scaling for computational efficiency |
| **Harvest/angling** | Size-selective with bag limits |
| **Sub-daily resolution** | Flexible steps_per_day vs. fixed hourly |
| **Hydraulic habitat** | Per-cell depth/velocity from flow lookup tables |

---

## 6. Recommended Integration Roadmap

**Phase 1 (Near-term):** Barrier passage + Estuarine stress  
→ Directly improves Baltic salmon migration realism  
→ Low risk, self-contained modules

**Phase 2 (Medium-term):** Genetics + Traits + Accumulators  
→ Enables evolutionary ecology scenarios  
→ Requires TroutState extensions but no core refactoring

**Phase 3 (Long-term):** Event pipeline + Multi-population + Current advection  
→ Architectural improvements for extensibility  
→ Larger refactoring scope, best combined with a major version release

---

## References

- Snyder, M.N. et al. (2019). Migration corridor simulation model. *Landscape Ecology*.
- Forseth, T. et al. (2001). Bioenergetics model for Atlantic salmon. *Can. J. Fish. Aquat. Sci.* 58:419-432.
- Railsback, S.F. & Harvey, B.C. (2020). Modeling Populations of Adaptive Individuals. Princeton University Press.
- Neuswanger, J. SalmonidNetworkIBM. GitHub: SouthForkResearch/SalmonidNetworkIBM.
