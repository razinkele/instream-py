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
call. A 912-day Example A simulation completes in ~50 seconds.
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
