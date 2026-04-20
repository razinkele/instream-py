"""Help panel — model documentation and built-in test cases."""

from shiny import module, reactive, render, ui


# ============================================================================
# Test case definitions
# ============================================================================

TEST_CASES = {
    "quick_smoke": {
        "name": "Quick Smoke Test",
        "description": "14-day run to verify the model starts, fish survive, and all panels render.",
        "start_date": "2011-04-01",
        "end_date": "2011-04-14",
        "overrides": {},
        "checks": [
            ("Fish alive > 0", lambda r: r["summary"]["fish_alive"] > 0),
            ("Daily records collected", lambda r: len(r["daily"]) > 0),
            ("Trajectories recorded", lambda r: not r["trajectories"].empty),
            ("Cells GeoDataFrame non-empty", lambda r: not r["cells"].empty),
            ("Environment data present", lambda r: not r["environment"].empty),
        ],
    },
    "population_stable": {
        "name": "Population Stability (90 days)",
        "description": "Run 3 months and check that the population doesn't crash to zero. "
        "Tests that growth, feeding, and survival are balanced.",
        "start_date": "2011-04-01",
        "end_date": "2011-06-30",
        "overrides": {},
        "checks": [
            ("Fish alive > 0 at end", lambda r: r["summary"]["fish_alive"] > 0),
            ("Population didn't crash below 10%", lambda r: _min_pop_fraction(r) > 0.1),
            ("Mean length increased", lambda r: _length_increased(r)),
        ],
    },
    "high_food": {
        "name": "High Food Availability",
        "description": "Increase drift concentration and search productivity by 10x. "
        "Fish should grow faster and population should be higher than baseline.",
        "start_date": "2011-04-01",
        "end_date": "2011-06-30",
        "overrides": {
            "drift_conc": -8.5,
            "search_prod": -5.0,
        },
        "checks": [
            ("Fish alive > 0", lambda r: r["summary"]["fish_alive"] > 0),
            ("Population survived 90 days", lambda r: len(r["daily"]) > 80),
        ],
    },
    "low_food": {
        "name": "Low Food — Starvation Stress",
        "description": "Reduce food availability by 100x. Fish should lose condition "
        "and mortality should increase, but the model shouldn't crash.",
        "start_date": "2011-04-01",
        "end_date": "2011-06-30",
        "overrides": {
            "drift_conc": -11.5,
            "search_prod": -8.0,
        },
        "checks": [
            (
                "Model completed without error",
                lambda r: r["summary"]["final_date"] != "",
            ),
            ("Daily records collected", lambda r: len(r["daily"]) > 0),
        ],
    },
    "high_predation": {
        "name": "High Predation Pressure",
        "description": "Set predation minimums low (more predation). "
        "Population should decline faster than baseline.",
        "start_date": "2011-04-01",
        "end_date": "2011-06-30",
        "overrides": {
            "fish_pred_min": 0.85,
            "terr_pred_min": 0.85,
        },
        "checks": [
            ("Model completed", lambda r: r["summary"]["final_date"] != ""),
            (
                "Higher mortality than baseline (population < initial)",
                lambda r: _final_less_than_initial(r),
            ),
        ],
    },
    "no_shade": {
        "name": "No Canopy Shade",
        "description": "Remove all riparian shading (shading=0). Tests light-dependent "
        "feeding and predation avoidance behaviour.",
        "start_date": "2011-04-01",
        "end_date": "2011-06-30",
        "overrides": {
            "shading": 0.0,
        },
        "checks": [
            ("Model completed", lambda r: r["summary"]["final_date"] != ""),
            ("Fish alive > 0", lambda r: r["summary"]["fish_alive"] > 0),
        ],
    },
    "spawning_season": {
        "name": "Full Spawning Season",
        "description": "Run through autumn spawning (Sep-Oct for Chinook). "
        "Tests redd creation, egg development, and fry emergence.",
        "start_date": "2011-04-01",
        "end_date": "2012-04-01",
        "overrides": {},
        "checks": [
            ("Model completed 1 year", lambda r: r["summary"]["final_date"] != ""),
            ("Redds were created", lambda r: not r["redds"].empty),
        ],
    },
    "outmigration": {
        "name": "Juvenile Outmigration",
        "description": "Run 1 year and check that some juveniles outmigrate downstream "
        "when habitat fitness drops below migration threshold.",
        "start_date": "2011-04-01",
        "end_date": "2012-04-01",
        "overrides": {},
        "checks": [
            ("Model completed 1 year", lambda r: r["summary"]["final_date"] != ""),
            (
                "Some outmigrants recorded",
                lambda r: r["summary"]["total_outmigrants"] > 0,
            ),
        ],
    },
}


def _min_pop_fraction(results):
    """Return minimum population as fraction of initial."""
    df = results["daily"]
    if df.empty:
        return 0
    grouped = df.groupby("date")["alive"].sum()
    if len(grouped) < 2:
        return 1.0
    initial = grouped.iloc[0]
    if initial == 0:
        return 0
    return float(grouped.min() / initial)


def _length_increased(results):
    """Check if mean fish length increased over the simulation (across all species)."""
    df = results["daily"]
    if df.empty or "mean_length" not in df.columns:
        return False
    daily = df[df["alive"] > 0]
    if len(daily) < 2:
        return False
    by_date = daily.groupby("date")["mean_length"].mean()
    return float(by_date.iloc[-1]) > float(by_date.iloc[0])


def _final_less_than_initial(results):
    """Check if final population is less than initial."""
    df = results["daily"]
    if df.empty:
        return False
    grouped = df.groupby("date")["alive"].sum()
    if len(grouped) < 2:
        return False
    return grouped.iloc[-1] < grouped.iloc[0]


# ============================================================================
# UI
# ============================================================================


@module.ui
def help_ui():
    return ui.navset_card_tab(
        ui.nav_panel(
            "Model Guide",
            ui.card(
                ui.card_header("SalmoPy Model Overview"),
                ui.markdown(_MODEL_HELP),
            ),
        ),
        ui.nav_panel(
            "Framework & References",
            ui.card(
                ui.card_header(
                    "Mathematical framework, inSALMO ↔ SalmoPy "
                    "differences, and peer-reviewed references"
                ),
                ui.markdown(_FRAMEWORK_HELP),
            ),
        ),
        ui.nav_panel(
            "Parameters",
            ui.card(
                ui.card_header("Parameter Reference"),
                ui.markdown(_PARAMETER_HELP),
            ),
        ),
        ui.nav_panel(
            "Test Cases",
            ui.card(
                ui.card_header("Built-in Test Scenarios"),
                ui.p(
                    "Run predefined scenarios to verify model behaviour. "
                    "Each test sets specific parameters, runs a short simulation, "
                    "and checks expected outcomes."
                ),
                ui.input_select(
                    "test_case",
                    "Select Test Case:",
                    choices={k: v["name"] for k, v in TEST_CASES.items()},
                ),
                ui.output_ui("test_description"),
                ui.input_action_button("run_test", "Run Test", class_="btn-warning"),
                ui.output_ui("test_results"),
            ),
        ),
    )


# ============================================================================
# Server
# ============================================================================


@module.server
def help_server(input, output, session, run_test_callback):
    """Server logic for help panel.

    Parameters
    ----------
    run_test_callback : callable
        Function(test_key) that triggers a simulation with the test case
        overrides and returns results. Called from the main server.
    """
    _test_results = reactive.value(None)

    @output
    @render.ui
    def test_description():
        key = input.test_case()
        tc = TEST_CASES.get(key)
        if tc is None:
            return ui.TagList()
        overrides_text = ""
        if tc["overrides"]:
            items = ", ".join(
                "**{}** = {}".format(k, v) for k, v in tc["overrides"].items()
            )
            overrides_text = "\n\nParameter changes: " + items
        return ui.markdown(
            "**{}**\n\n{}\n\nPeriod: {} to {}{}\n\nChecks: {}".format(
                tc["name"],
                tc["description"],
                tc["start_date"],
                tc["end_date"],
                overrides_text,
                ", ".join(c[0] for c in tc["checks"]),
            )
        )

    @reactive.effect
    @reactive.event(input.run_test)
    def _on_run_test():
        key = input.test_case()
        _test_results.set(None)
        run_test_callback(key)

    def set_test_results(results, test_key):
        """Called by main server when test simulation completes."""
        tc = TEST_CASES.get(test_key)
        if tc is None:
            _test_results.set([("Error", False, "Unknown test case")])
            return
        outcomes = []
        for check_name, check_fn in tc["checks"]:
            try:
                passed = check_fn(results)
                outcomes.append((check_name, passed, ""))
            except Exception as e:
                outcomes.append((check_name, False, str(e)))
        _test_results.set(outcomes)

    @output
    @render.ui
    def test_results():
        outcomes = _test_results()
        if outcomes is None:
            return ui.TagList()
        rows = []
        all_pass = True
        for name, passed, err in outcomes:
            icon = "PASS" if passed else "FAIL"
            color = "green" if passed else "red"
            detail = "" if not err else " ({})".format(err)
            rows.append(
                ui.tags.tr(
                    ui.tags.td(
                        ui.tags.span(
                            icon,
                            style="color:{}; font-weight:bold;".format(color),
                        )
                    ),
                    ui.tags.td(name + detail),
                )
            )
            if not passed:
                all_pass = False
        summary_color = "green" if all_pass else "red"
        summary_text = "All checks passed!" if all_pass else "Some checks failed."
        return ui.TagList(
            ui.tags.table(
                ui.tags.thead(ui.tags.tr(ui.tags.th("Status"), ui.tags.th("Check"))),
                ui.tags.tbody(*rows),
                class_="table table-sm table-bordered",
            ),
            ui.tags.p(
                ui.tags.strong(summary_text),
                style="color:{};".format(summary_color),
            ),
        )

    return set_test_results


# ============================================================================
# Help content
# ============================================================================

_MODEL_HELP = """\
## What is SalmoPy?

SalmoPy is an individual-based model (IBM) that simulates populations of
stream-dwelling and anadromous salmonids. It is a Python port of
[inSTREAM 7](https://www.fs.usda.gov/treesearch/pubs/65856) / inSALMO,
originally developed by Steve Railsback and Bret Harvey, extended with
marine lifecycle, Baltic Atlantic salmon calibration, and
Numba-accelerated computation.

## Model Structure

### Spatial Domain
- **Cells**: The stream is divided into habitat cells (polygons from a
  shapefile or triangles from a FEM mesh).
- **Reaches**: Groups of cells sharing the same environmental conditions
  (flow, temperature, turbidity).
- **Hydraulics**: Each cell has depth and velocity lookup tables indexed by
  flow — updated daily from time-series inputs.
- **Marine domain**: Anadromous fish that outmigrate enter a simplified
  ocean stage with size-dependent growth and survival.

### Fish Agents
Each fish is an individual (or super-individual) with:
- **Physical state**: length (cm), weight (g), condition factor (K = W/L^3)
- **Location**: current cell index in the spatial mesh (or marine zone)
- **Activity**: drift feeding, search feeding, hiding, holding, or migrating
- **Life stage**: FRY, PARR, SMOLT, OCEAN, RETURNING_ADULT, KELT, or
  REPEAT_SPAWNER

### Daily Cycle
Each simulation day, freshwater fish:
1. **Evaluate habitat** — scan cells within a length-dependent movement radius
2. **Select best cell** — choose the cell + activity maximising expected
   fitness (growth rate weighted by survival probability)
3. **Feed** — consume drift or search food based on chosen activity
4. **Grow** — update length and weight from net energy intake
5. **Survive or die** — face mortality risks from:
   - High temperature
   - Poor condition (starvation)
   - Terrestrial predation (birds, mammals)
   - Aquatic predation (piscivorous fish)
   - Stranding (dewatered cells)
6. **Spawn** (if in season and mature) — create redds with eggs
7. **Migrate** (smolts) — move downstream when fitness is low

Marine fish experience daily growth based on prey availability and
face mortality from seals, cormorants, fishing, bycatch, M74 syndrome,
background mortality, and thermal stress.

### Redds (Egg Nests)
- Created by spawning adults in suitable cells (depth, velocity, substrate)
- Develop based on accumulated temperature (degree-days)
- Face mortality from: high temperature, low temperature, dewatering, scour
- Emerge as fry when development fraction reaches 1.0

### Life Cycle (Anadromous)
FRY → PARR → SMOLT → OCEAN → RETURNING_ADULT → spawning → KELT →
(optionally) REPEAT_SPAWNER. The full lifecycle is simulated for
Baltic Atlantic salmon with ICES-calibrated parameters.

### Key Ecological Processes

| Process | Mechanism |
|---------|-----------|
| **Feeding** | Drift encounter rate = f(velocity, depth, fish size, turbidity, light) |
| **Growth** | Bioenergetics: intake - respiration - excretion |
| **Movement** | Fitness-based habitat selection within search radius |
| **Mortality** | Logistic survival functions for each risk factor |
| **Spawning** | Conditional on season, size, condition, temperature |
| **Migration** | Downstream movement when habitat fitness < migration fitness |
| **Marine survival** | Size-dependent seal/cormorant predation, fishing, M74 |

## Visualisation Panels

| Panel | Shows |
|-------|-------|
| **Dashboard** | Live metrics (alive, deaths, feeding activity, redds) updated during simulation |
| **Movement** | Animated fish movement on the river map with daily step-through |
| **Population** | Fish count over time by species |
| **Spatial** | Map with cell polygons coloured by depth/velocity/food + fish trails |
| **Environment** | Temperature, flow, and turbidity time series |
| **Size Distribution** | Length and weight histograms at census dates |
| **Redds** | Active redd counts, total eggs, emergence tracking |
| **Help & Tests** | This documentation + built-in test scenarios |

## Performance

Habitat selection (the dominant cost at ~90% of step time) is accelerated
via a batch Numba JIT kernel that processes all fish in a single compiled
call. A 912-day Example A simulation completes in ~50 seconds — a
350–1,290× speedup over the NetLogo reference.
"""


# ============================================================================
# Framework & Equations — detailed model math + inSALMO ↔ SalmoPy diff
# ============================================================================

_FRAMEWORK_HELP = """\
## Mathematical framework

SalmoPy reproduces the core equations of **inSTREAM 7** (Railsback &
Harvey 2020) and **inSALMO 7.3/7.4** (Railsback et al. 2013) with
targeted extensions for marine lifecycle, Baltic calibration, and
high-performance execution. This page documents the equations, explains
where SalmoPy diverges from the NetLogo reference, and lists peer-
reviewed sources.

### 1. Bioenergetics (Wisconsin model)

Daily growth is net energy intake converted to body mass:

```
growth_g_per_day = (intake_g_per_day · prey_ED − respiration_g_per_day)
                   / fish_ED
```

where `prey_ED`, `fish_ED` are energy densities (J/g). **Intake**
depends on activity:

- **Drift feeding**:
  `intake = capture_area · drift_conc · velocity · 86400 · capture_success`
  capped at Cmax (temperature × weight-dependent max consumption) and
  cell-level `available_drift`.
- **Search feeding**: `intake = search_prod · search_area · vel_ratio`
  where `vel_ratio = (max_swim − velocity) / max_swim`.
- **Hiding**: intake = 0 (respiration cost only).

**Respiration** (Hewett-Johnson-style):
```
R = resp_A · W^resp_B · exp(resp_D · (v / v_max)²) · exp(resp_C · T²)
```

**Cmax temperature function** is a species-specific piecewise-linear
table in T ∈ [0, 30] °C. Identical to NetLogo's
`trout-cmax-temp-table` interpolation (passes rtol 1e-10 on a 330 k-row
reference, `tests/test_validation.py::TestGrowthReportMatchesNetLogo`).

### 2. Habitat selection (fitness-based)

At every step a fish evaluates every candidate cell × activity triple
and picks the one maximising **expected fitness to the time horizon**:

```
fitness = (daily_survival · mean_condition_survival)^horizon_days
        × length_penalty(length_at_horizon, fitness_length)
```

Here `daily_survival` is the product of five sub-terms (hi-temp,
stranding, condition, fish-predation, terrestrial-predation) raised to
the current step length, and `length_penalty < 1` when the fish won't
reach maturity length by horizon. This matches NetLogo `fitness-for`
(InSALMO7.3:2798–2840) exactly.

The fitness produced here is bounded in [0, 1] — which is why SalmoPy's
**migration comparator** (`should_migrate`) was rewritten in v0.31.0 to
compare `migration_fitness` against this per-tick `best_habitat_fitness`
rather than the older `fitness_memory` EMA. The EMA mixed raw growth
(g/day, unbounded) with survival probability, producing a scale
mismatch that silently blocked small-fish outmigration.

### 3. Migration decision

For each anadromous juvenile at each daily boundary:

```
migrate = (migration_fit > best_habitat_fit) AND life_history == PARR
```

where `migration_fit = logistic(length, L1, L9)` (species-specific
size logistic). SalmoPy's v0.31.0 **continuous FRY → PARR promotion**
lets an anadromous fry become PARR as soon as `length ≥ 4.0 cm OR
age ≥ 1`, replacing the legacy Jan-1-only gate (which had silently
blocked emergence-year outmigration, contributing to a 21× outmigrant
deficit against NetLogo example_a).

### 4. Spawning & redd emergence

Spawners lay `num_eggs = fecund_mult · length^fecund_exp ·
egg_viability` (SalmoPy v0.32: was `weight^fecund_exp` pre-fix, over-
producing ~13× for a 60 cm / 6.9 kg adult).

Redd development accumulates with temperature:
```
d_frac/dt = devel_A · (T² · devel_B + T · devel_C)  [per day]
```

When `frac_developed ≥ 1.0`, emergence spreads over 10 days
(NetLogo InSALMO7.3:4228–4287):
```
eggs_this_day = ceil(remaining_eggs · emerge_day / 10)
```

Eggs are aggregated into super-individuals of size `superind_max_rep`.
Pre-v0.32 SalmoPy emerged all eggs on day 1 with `superind_rep = 1` —
a 10× density spike that starved the natal cohort.

### 5. Drift food replenishment (v0.33 fix)

Daily `available_drift` per cell:

```
drift_supply = 86400 · area · depth · velocity · drift_conc
             / drift_regen_distance   [g/day]
```

Before v0.33 the formula was `drift_conc · area · depth · step_length`
— missing `86400 · velocity / drift_regen_distance` (an **8,640×
factor for example_a**). Fish computed correct per-capture intake but
hit a drastically undersized cell pool cap, throttling growth to ~0.003
g/day. The fix alone closed the headline `outmigrant_cumulative` parity
metric.

### 6. Marine module (SalmoPy extension)

No NetLogo counterpart. Daily marine fish:

```
weight_gain ∝ prey_ED · forage_efficiency(length)
smolt_to_adult_return_mortality = seal · cormorant · fishing · bycatch · M74 · background · thermal
```

Calibrated against ICES Baltic Atlantic salmon stock assessments
(ICES WGBAST). Smolt → adult return (SAR) for Teno-like populations
falls in the 3–12 % band (ICES 2023).

---

## inSALMO (NetLogo) vs SalmoPy (this port)

### Matched components (function-level rtol ≤ 1e-10)

| Component | NetLogo | SalmoPy |
|---|---|---|
| Cmax temperature interp | piecewise linear | piecewise linear |
| Wisconsin respiration | eq. (12)-(14) Railsback 2020 | same |
| Logistic risk terms | `logistic-with` | `evaluate_logistic` |
| Habitat fitness `fitness-for` | daily_survival^horizon | `expected_fitness` (v0.31.0) |
| Redd development | degree-day | degree-day |
| Fecundity | `fecund_mult · L^exp` | `fecund_mult · L^exp` (fixed v0.32) |
| Emergence spread | ceil(N · days / 10) | same (v0.32) |
| Drift food supply | `86400·A·d·v·C/regen` | same (fixed v0.33) |

### Implementation differences

| Aspect | NetLogo inSALMO 7.3/7.4 | SalmoPy |
|---|---|---|
| Language | NetLogo 6.4 / 7.0.3 (JVM, Mersenne Twister RNG) | Python 3.11+ + Numba JIT (PCG64 RNG) |
| Concurrency | single-threaded | per-fish Numba `prange` parallel pass |
| State layout | one object per fish (agent-based) | Structure-of-Arrays (contiguous NumPy) |
| Habitat selection throughput | ~5 s/step (example_a) | ~48 ms/step (~100× faster) |
| Reach topology | directed adjacency list | same + KD-tree spatial index |
| I/O | BehaviorSpace CSV | YAML config + Pydantic validation + CSV time series |
| Outmigrant counting | `+ trout-superind-rep` (rep-weighted) | `superind_rep` on each outmigrant record (matches) |

### Ecological extensions in SalmoPy

1. **Marine domain**: 7 mortality sources + size-dependent growth for
   smolts/ocean adults/returning spawners. No NetLogo equivalent.
2. **Iteroparous KELT lifecycle**: post-spawn survival + repeat-spawner
   return, critical for Atlantic salmon and steelhead populations.
3. **Hatchery stocking**: release-shock survival + straying back to
   natal reaches. Drives stocking scenarios for ICES assessments.
4. **Angler harvest**: length-selective + catch-and-release mortality.
5. **Barriers**: inter-reach transmission / deflection / mortality
   probabilities for dams, culverts, fish ladders.
6. **OSM-driven geography**: fetch rivers + waterbodies from
   OpenStreetMap via PBF; EMODnet bathymetry for marine cells;
   Marine Regions WFS for named water bodies. Enables any European
   Geofabrik region as a case study.
7. **Sub-daily scheduling**: hourly peaking-flow support via the
   inSTREAM-SD extension (Railsback & Harvey 2022).
8. **Calibration framework**: Morris + Sobol sensitivity, Nelder-Mead
   + differential-evolution + GP surrogate optimization, multi-seed
   validation, JSON history, scenario manager. Adapted from
   razinkele/osmopy (Razinkovas-Baziukas 2026). See the Calibration
   section of `README.md`.

### Historical parity drift closed by Arcs D–I (2026-04)

| Arc | Root cause | Metric impact |
|---|---|---|
| D | fitness_memory EMA used as migration comparator (scale mismatch) | outmigrants 1,943 → 12,090 |
| E | Fecundity formula used weight (not length); single-redd spawning; single-day emergence | 12,090 → 20,117 |
| F | `available_drift` missing velocity + regen_distance (8,640× too small) | **PASS** (~41,146) |
| G | Parity test treated 0.0 juv_length as data, not sentinel | juv_length apparent 0 → 5.21 cm |
| H | Cohort-survival probe: size-selective migration + shorter cohort lifetime explain residual 16 % | diagnostic |
| I | Calibration-framework PoC: Morris ranks migration params top; seed-0 minimum not robust | framework validated |

After Arc G the headline parity metric `test_outmigrant_cumulative`
passes for the first time since the NetLogo cross-validation test was
written. Two of five metrics pass; three remain with identified causes
(15–25 % residual drift).

See `docs/validation/v0.31.0-arc-D-netlogo-comparison.md` for the full
report.

---

## References

### Model foundations

- **Railsback, S. F.** & **Harvey, B. C.** (2020). *Modeling Populations
  of Adaptive Individuals*. Monographs in Population Biology 63,
  Princeton University Press. DOI:
  [10.1515/9780691195285](https://doi.org/10.1515/9780691195285).
- **Railsback, S. F.**, **Harvey, B. C.**, **Jackson, S. K.** &
  **Lamberson, R. H.** (2009). *InSTREAM: the individual-based stream
  trout research and environmental assessment model*. USDA Forest
  Service PSW-GTR-218.
- **Railsback, S. F.**, **Harvey, B. C.**, **Ayllón, D.** (2013).
  InSALMO: A model of anadromous Pacific salmon life history for
  assessing restoration actions. Humboldt State University report.
- **Railsback, S. F.** & **Harvey, B. C.** (2022). Importance of the
  daily light cycle in population-habitat relations: a simulation study.
  *Transactions of the American Fisheries Society* 151(1), 3–14.
  DOI: [10.1002/tafs.10331](https://doi.org/10.1002/tafs.10331).

### Bioenergetics

- **Hewett, S. W.** & **Johnson, B. L.** (1992). *Fish Bioenergetics
  Model 2*. Wisconsin Sea Grant WIS-SG-92-250.
- **Hanson, P. C.**, **Johnson, T. B.**, **Schindler, D. E.** &
  **Kitchell, J. F.** (1997). *Fish Bioenergetics 3.0*. Wisconsin Sea
  Grant WISCU-T-97-001.

### Anadromous & marine

- **ICES** (2023). *Working Group on Baltic Salmon and Sea Trout
  (WGBAST)*. ICES Scientific Reports 5(26).
  DOI: [10.17895/ices.pub.22328542](https://doi.org/10.17895/ices.pub.22328542).
- **Niemelä, E.** et al. (2006). Previous life-history traits affecting
  adult Atlantic salmon repeat spawning in the Teno River. *ICES
  Journal of Marine Science* 63(9), 1565–1576.
  DOI: [10.1016/j.icesjms.2006.06.008](https://doi.org/10.1016/j.icesjms.2006.06.008).
- **Brännäs, E.** (1988). Emergence of Baltic salmon (*Salmo salar* L.)
  in relation to temperature: a laboratory study. *Journal of Fish
  Biology* 33(4), 589–600.
  DOI: [10.1111/j.1095-8649.1988.tb05502.x](https://doi.org/10.1111/j.1095-8649.1988.tb05502.x).
- **Kallio-Nyberg, I.**, **Saloniemi, I.** et al. (2004). Effects of
  sea temperatures and climatic phases on growth and maturation of
  sea-ranched Atlantic salmon. *Boreal Environment Research* 9,
  43–56.

### Computing & methods

- **Masad, D.** & **Kazil, J.** (2015). *MESA: An Agent-Based Modeling
  Framework*. 14th PYTHON in Science Conference.
- **Lam, S. K.**, **Pitrou, A.** & **Seibert, S.** (2015). Numba: A
  LLVM-based Python JIT compiler. LLVM-HPC 2015 Workshop.
  DOI: [10.1145/2833157.2833162](https://doi.org/10.1145/2833157.2833162).
- **Saltelli, A.** et al. (2010). Variance based sensitivity analysis
  of model output: Design and estimator for the total sensitivity
  index. *Computer Physics Communications* 181(2), 259–270.
  DOI: [10.1016/j.cpc.2009.09.018](https://doi.org/10.1016/j.cpc.2009.09.018).
- **Morris, M. D.** (1991). Factorial sampling plans for preliminary
  computational experiments. *Technometrics* 33(2), 161–174.
  DOI: [10.1080/00401706.1991.10484804](https://doi.org/10.1080/00401706.1991.10484804).
- **Iwanaga, T.**, **Usher, W.** & **Herman, J.** (2022). Toward SALib
  2.0: Advancing the accessibility and interpretability of global
  sensitivity analyses. *Socio-Environmental Systems Modelling* 4,
  18155. DOI:
  [10.18174/sesmo.18155](https://doi.org/10.18174/sesmo.18155).

### Calibration framework

- **Razinkovas-Baziukas, A.** (2026). *osmopy: calibration toolkit for
  the OSMOSE end-to-end fish community model*. GitHub:
  [razinkele/osmopy](https://github.com/razinkele/osmopy). SalmoPy's
  `src/instream/calibration/` subpackage is an in-process Python/Mesa
  port of this framework.

### Geography & data

- **OpenStreetMap contributors** (2026). River and waterbody geometry
  via Geofabrik regional PBF extracts.
- **EMODnet Bathymetry Consortium** (2022). *EMODnet Digital
  Bathymetry (DTM 2022)*.
  DOI: [10.12770/ff3aff8a-cff1-44a3-a2c8-1910bf109f85](https://doi.org/10.12770/ff3aff8a-cff1-44a3-a2c8-1910bf109f85).
- **Flanders Marine Institute (VLIZ)** (2024). *Marine Regions*.
  URL: <https://marineregions.org/>.

### SalmoPy release

- **Razinkovas-Baziukas, A.** and contributors (2026). *inSTREAM-py:
  high-performance Python port of inSTREAM/inSALMO 7.4*. GitHub:
  [razinkele/instream-py](https://github.com/razinkele/instream-py).
  Version 0.33.0.
"""

_PARAMETER_HELP = """\
## Sidebar Controls

### Simulation Settings
| Control | Description | Default |
|---------|-------------|---------|
| **Configuration** | YAML config file defining species, reaches, and spatial setup | example_a |
| **Start Date** | First day of simulation | 2011-04-01 |
| **End Date** | Last day of simulation | 2013-09-30 |
| **Backend** | Computation backend: numpy (portable) or numba (faster) | numpy |

## Species Parameters (from config YAML)

### Feeding
| Parameter | Description |
|-----------|-------------|
| cmax_A, cmax_B | Maximum consumption allometry: Cmax = A * W^B |
| cmax_temp_table | Temperature-dependent consumption multiplier |
| react_dist_A, B | Reactive distance for prey detection (cm) |
| turbid_threshold/min/exp | Turbidity effect on feeding efficiency |
| light_threshold/min/exp | Light effect on feeding efficiency |
| search_area | Area searched per time step (cm^2) |

### Growth & Metabolism
| Parameter | Description |
|-----------|-------------|
| resp_A, B, D | Respiration parameters (standard metabolic rate) |
| weight_A, B | Length-weight relationship: W = A * L^B |
| energy_density | Energy content of fish tissue (J/g) |
| prey_energy_density | Energy content of prey (J/g) |

### Movement
| Parameter | Description |
|-----------|-------------|
| move_radius_max | Maximum habitat search radius (CRS units) |
| move_radius_L1, L9 | Fish lengths where search radius = 10% / 90% of max |

### Mortality
| Parameter | Description |
|-----------|-------------|
| mort_high_temp_T1, T9 | Temperature thresholds for thermal mortality |
| mort_condition_S_at_K8, K5 | Survival at condition factors K=0.8, K=0.5 |
| mort_terr_pred_* | Terrestrial predation logistic parameters |
| mort_fish_pred_* | Aquatic predation logistic parameters |

### Spawning
| Parameter | Description |
|-----------|-------------|
| spawn_start_day, end_day | Spawning season window (MM-dd) |
| spawn_min_temp, max_temp | Temperature range for spawning |
| spawn_fecund_mult, exp | Fecundity: eggs = mult * length^exp |
| spawn_wt_loss_fraction | Body weight lost to egg production |
| redd_devel_A, B, C | Egg development rate = f(temperature) |

## Reach Parameters (from config YAML)

| Parameter | Description | Units |
|-----------|-------------|-------|
| drift_conc | Density of drifting invertebrate prey | g/cm^3 |
| search_prod | Rate at which search-feeding fish find benthic prey | g/cm^2/hr |
| shelter_speed_frac | Velocity reduction in sheltered microhabitats | fraction |
| prey_energy_density | Energy content of invertebrate prey | J/g |
| fish_pred_min | Minimum daily survival from aquatic predation | probability |
| terr_pred_min | Minimum daily survival from terrestrial predation | probability |

### How Parameters Interact

**Food supply** (drift_conc, search_prod):
- Determines daily energy intake -> growth rate -> condition factor
- Low food -> poor condition -> higher starvation mortality
- Very high food -> fish grow fast, reach larger sizes

**Predation** (fish_pred_min, terr_pred_min):
- These set the floor for daily survival probability
- Actual survival depends on fish size, depth, velocity, hiding cover
- Small fish in shallow water with no cover face the highest risk
"""
