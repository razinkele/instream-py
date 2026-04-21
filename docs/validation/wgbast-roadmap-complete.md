# WGBAST-comparability roadmap — Arcs K through Q completion summary

**Dates**: 2026-04-20 → 2026-04-21
**Versions**: v0.34.0 → v0.40.0
**Plans**:
- `docs/superpowers/plans/2026-04-20-arc-K-to-Q-wgbast-roadmap.md` (scope + Arc 0 prerequisite + Arcs K/L detail)
- `docs/superpowers/plans/2026-04-20-arc-M-to-Q-expanded.md` (Arcs M through Q full TDD detail, 3-pass-reviewed)

---

## Overview

The 7-arc roadmap makes SalmoPy's outputs and parameterizations directly
comparable to the ICES Working Group on Baltic Salmon and Sea Trout
(WGBAST) assessment. Each arc is a self-contained feature slice with its
own release tag, tests, and NetLogo InSALMO 7.3 parity preservation. The
full sequence shipped in ~5 days, 7 releases, ~40 new tests, zero
regressions to pre-existing suites.

| Arc | Version | Deliverable | Key file | Tests |
|:---:|:-------:|:------------|:---------|:-----:|
| **K** | 0.34.0 | Per-reach smolt production + % PSPC CSV | `io/output.py::write_smolt_production_by_reach` | 5 |
| **L** | 0.35.0 | WGBAST M74 YSFM cull at egg-emergence | `modules/egg_emergence_m74.py::apply_m74_cull` | 6 |
| **M** | 0.36.0 | 4 Baltic river fixtures (Torne/Simo/Byske/Mörrum) | `configs/example_{tornionjoki,simojoki,byskealven,morrumsan}.yaml` | 4 smoke |
| **N** | 0.37.0 | Post-smolt survival time-varying forcing | `marine/survival_forcing.py`, `marine/survival.py::marine_survival(current_year=)` | 6 |
| **O** | 0.38.0 | Straying + spawner-origin MSA matrix | `marine/config.py::stray_fraction`, `io/output.py::write_spawner_origin_matrix` | 5 |
| **P** | 0.39.0 | HELCOM grey-seal Holling II abundance scaling | `marine/seal_forcing.py`, `marine/survival.py::seal_hazard(current_year=)` | 5 |
| **Q** | 0.40.0 | Bayesian SMC wrapper | `bayesian/{prior,observation_model,smc}.py` | 8 |

---

## Arc-by-arc summary

### Arc K — Per-reach smolt production + PSPC output

Widens `outmigrants.csv` from 3 to 10 NetLogo-compat columns (species,
timestep, reach_idx, natal_reach_idx, natal_reach_name, age_years,
length_category, length_cm, initial_length_cm, superind_rep) and emits
`smolt_production_by_reach_{year}.csv` with `pspc_achieved_pct` — the
canonical WGBAST management metric.

**Infrastructure work:** added `TroutState.initial_length` field (populated
at 5 fish-creation sites); exposed `TimeManager.start_date` as public
property; added `ReachConfig.pspc_smolts_per_year`; added
`require_natal_reach` guard on `write_outmigrants`.

### Arc L — WGBAST M74 year-effect (egg-emergence)

Applies the Vuorinen 2021 + WGBAST 2026 YSFM fraction as a **one-time
binomial cull** at egg→fry emergence keyed by `(year, river_name)`.

**Critical semantic fix** (plan-review iteration 1): M74 is a freshwater
yolk-sac-fry mortality, not a marine hazard. The first-draft plan wired
it into `marine/survival.py`; reviewer flagged that a 0.50 annual
fraction applied as a daily hazard compounds to 0.5^365 ≈ 10⁻¹¹⁰
marine survival. The final implementation applies the cull in
`modules/spawning.py::redd_emergence` via new optional kwargs
(`m74_forcing_csv`, `current_year`, `river_name_by_reach_idx`).

Added `ReachConfig.river_name` + `ReachParams.river_name` + propagation
through `params_from_config`.

### Arc M — Multi-river Baltic fixtures

4 WGBAST-assessment-ready river fixtures at latitudes 56.17°N (Mörrum)
to 65.85°N (Torne), with:

- Per-river temperature offsets: −6.0°C (Torne/Simo) → +3.0°C (Mörrum)
- Per-river flow scaling: 0.05× Nemunas (Mörrum 25 m³/s) → 0.8× (Torne 400 m³/s)
- PSPC totals matching WGBAST 2026 §3: Torne 2.2M, Simo 95k, Byske 180k, Mörrum 60k
- `smolt_min_length` per AU: 14 cm (AU1) → 11 cm (Southern)

**Pragmatic scaffolding**: reach names in YAMLs stay Nemunas-basin
(`Nemunas`, `Atmata`, …) — the shapefile DBF is reused verbatim as
geometric scaffolding. Each reach carries the WGBAST `river_name` + PSPC
so Arc K/L analytics work as designed. Future Arc 0 refinement can
rewrite DBF attributes to real Torne/Simo reach names.

### Arc N — Post-smolt survival time-varying forcing

`marine_survival(current_year=)` overrides `background_hazard` for fish
in the post-smolt window (`days_since_ocean_entry < 365`) using a
per-(smolt-year, stock_unit) annual-survival lookup from
`data/wgbast/post_smolt_survival_baltic.csv`.

**Key semantic choice** (plan-review iteration 2): smolt year, not
calendar year, is the lookup key. A fish emigrating July Y and crossing
into Y+1 gets Y's WGBAST cohort-posterior across its full 365-day
post-smolt window, not a July/January cohort split. Implemented via
`smolt_years = current_year - (days_since_ocean_entry // 365)`.

Mathematical core: `daily_hazard = 1 - S_annual^(1/365)` inverts exactly
(verified in test).

### Arc O — Straying + spawner-origin MSA matrix

Two coordinated changes:

1. **Bug fix**: removed `natal_reach_idx = current_reach` overwrite at
   SMOLT transition in `modules/migration.py:152`. Pre-v0.38 this
   overwrite destroyed the birth-reach signal every smoltifying fish
   carried; Arc K PSPC analytics depended on this signal and had been
   silently miscalibrated.
2. **Feature**: `MarineConfig.stray_fraction` applied in
   `check_adult_return`. On stray (probability `stray_fraction`), fish
   is relocated to a random non-natal freshwater reach via
   `rng.choice(reach_cells.keys() - natal)`. `natal_reach_idx`
   **preserved** (genetic property); only `reach_idx` (spawning
   location) changes.

`write_spawner_origin_matrix` emits a natal × spawning reach matrix
directly comparable to WGBAST's genetic mixed-stock analysis.

### Arc P — HELCOM grey-seal Holling II abundance scaling

`seal_hazard(current_year=)` scales the length-logistic base by a
**Holling Type II saturating multiplier** anchored at
`seal_reference_abundance`:

```
mult(r) = (r / (1 + r/k)) / (1 / (1 + 1/k))
  where r = abundance / reference_abundance
        k = saturation_k_half (default 2.0)
```

At reference: mult = 1.0 (legacy calibration preserved).
At r = 2: mult = 1.5 (sub-linear).
At r → ∞: mult → k+1 = 3.0 (asymptote).

**Ecologically critical** (plan-review iteration 1): linear scaling
would have projected `marine_mort_seal_max_daily × 15` at 2021 seal
levels vs 1988 baseline — effectively marine-salmon extinction. Type II
matches real predator functional responses (handling-time saturation).

Placeholder HELCOM series 1988 (2.8k seals, Harding 2007 baseline)
through 2023 (45k, Westphal 2025).

### Arc Q — Bayesian life-cycle wrapper

`instream.bayesian` subpackage wraps the existing calibration framework
(Sobol/Morris/Nelder-Mead/GP surrogate, 13 modules) in a posterior
shell comparable to the WGBAST Bayesian model (Kuikka 2014).

- **`Prior`** dataclass with `sample(rng, n)`; `BALTIC_SALMON_PRIORS`:
  post_smolt_survival U(0.02, 0.18), m74_baseline U(0, 0.30),
  stray_fraction U(0, 0.25), fecundity_mult U(500, 900).
- **Observation model**: Poisson smolt-trap (`lambda = simulated ×
  trap_efficiency`) and negative-binomial spawner-counter (default
  `overdispersion_k = 50` ≈ CV 15% at mu=100, matching Orell & Erkinaro
  2007 Riverwatcher inter-observer agreement).
- **`run_smc`**: ABC-SMC with tempered log-likelihood, ESS-triggered
  resampling, returns (particles, weights, log_marginal_likelihood,
  param_names).
- **Posterior-recovery toy test** confirms the sampler concentrates
  near a known true value under Gaussian noise within ±0.1 and σ < 0.15.

---

## Cross-arc design patterns

### 1. Opt-in kwargs default to None/0 → NetLogo parity preserved

Every arc's forcing/knob is **disabled by default**:

| Arc | Kwarg | Default |
|-----|-------|---------|
| L | `m74_forcing_csv` | None |
| N | `post_smolt_survival_forcing_csv` | None |
| N | `current_year` (on `marine_survival`) | None |
| O | `stray_fraction` | 0.0 |
| O | `config` (on `check_adult_return`) | None |
| P | `seal_abundance_csv` | None |
| P | `current_year` (on `seal_hazard`) | None |

Any run that doesn't opt in behaves identically to the v0.33.0 baseline.
`tests/test_run_level_parity.py::TestExampleARunVsNetLogo` metrics
remained stable across all 7 releases (except the 3 pre-existing Arc
H/I residual gaps, documented unchanged).

### 2. Consistent CSV forcing schema

All three year-indexed CSVs use `Dict[Tuple[int, str], float]` as the
in-memory shape and comment-tolerant CSV format:

- `data/wgbast/m74_ysfm_series.csv` — `(year, river) → ysfm_fraction`
- `data/wgbast/post_smolt_survival_baltic.csv` — `(year, stock_unit) → survival_pct`
- `data/helcom/grey_seal_abundance_baltic.csv` — `(year, sub_basin) → population_estimate`

Each loader rejects missing columns via `assert required.issubset(df.columns)`
and skips `#`-prefixed lines via `pd.read_csv(..., comment="#")`.

### 3. `current_year` threading

The `current_year` kwarg propagates from `apply_marine_survival` →
`marine_survival` → `seal_hazard` via consistent default-None plumbing.
Callers derive it from `current_date.year`. Arc L uses `current_year`
at the egg-emergence hook (`model_day_boundary.py`), Arc N uses it in
`marine_survival`, Arc P uses it in `seal_hazard`. Same naming everywhere.

---

## NetLogo InSALMO 7.3 parity

Reviewed independently during both plan-writing passes by the
`validation-checker` subagent (see `docs/superpowers/plans/...` for
per-arc parity-risk reports):

- **NetLogo has no M74, straying, or seal-abundance forcing** — Arcs L,
  O, P are pure SalmoPy extensions beyond NetLogo scope.
- **Arc K widened schema** matches NetLogo's 9-column
  `Outmigrants-<run>.csv` (SalmoPy adds 10th `natal_reach_name` for
  join convenience).
- **Arc O.1 natal_reach_idx fix** aligns with NetLogo — NetLogo sets
  birth reach at init/emergence only, never overwrites at smoltification.
- **Arc Q SMC wrapper** is analogous in spirit to WGBAST's own Bayesian
  model; no NetLogo counterpart.

---

## Known placeholders (Arc 0 follow-up)

Four of the shipped CSVs contain preliminary values transcribed from
narrative descriptions or decade-marker interpolation. They must be
replaced via direct WGBAST/HELCOM PDF extraction when time permits:

| CSV | Scope | Replacement source |
|-----|-------|----|
| `data/wgbast/m74_ysfm_series.csv` | Simo/Torne 1985-2024 | Vuorinen 2021 supplementary table, extended via WGBAST 2026 §3 |
| `data/wgbast/post_smolt_survival_baltic.csv` | sal.27.22-31 1987-2024 | WGBAST 2026 §2 Bayesian posterior median figures |
| `data/wgbast/observations/smolt_trap_counts.csv` | Simo/Torne 2010-2015 | WGBAST 2026 §3 Table |
| `data/helcom/grey_seal_abundance_baltic.csv` | Main basin 1988-2023 | HELCOM core-indicator report PDF tables |

**None of these are code changes** — drop-in CSV replacement after
PDF extraction. The code paths that consume them are production-tested.

The Arc M multi-river fixtures similarly ship with the Nemunas-basin
shapefile reused as scaffolding; rewriting the DBF with Torne/Simo/Byske/
Mörrum reach names is another Arc 0 follow-up task (same file-system
shape, just attribute renaming).

---

## Cumulative metrics

| Metric | Value |
|--------|-------|
| Versions released | 7 (v0.34.0 → v0.40.0) |
| Commits on master since v0.33.0 | ~30 (feature + release per arc) |
| New tests | ~40 (pspc, m74, multi-river smoke, post-smolt, straying, seal, bayesian) |
| Regression failures introduced | 0 (1 test fixture updated to not rely on natal_reach_idx bug) |
| Lines of new code | ~2,000 |
| Lines of new docs | ~500 |
| New public APIs | `Prior`, `run_smc`, 3 forcing loaders, 2 output writers |
| New config fields | `pspc_smolts_per_year`, `river_name`, 4× forcing CSV paths, `stray_fraction`, 3× seal scaling params |

---

## References

### Scientific

- Kuikka, S., Vanhatalo, J., Pulkkinen, H., et al. (2014). Experiences
  in Bayesian Inference in Baltic Salmon Management. *Statistical
  Science* 29(1). [DOI 10.1214/13-sts431](https://doi.org/10.1214/13-sts431).
- Vuorinen, P. J., Rokka, M., Nikonen, S., et al. (2021). Model for
  estimating thiamine-deficiency-related mortality of Atlantic salmon.
  *Marine and Freshwater Behaviour and Physiology* 54(3), 97-131.
  [DOI 10.1080/10236244.2021.1941942](https://doi.org/10.1080/10236244.2021.1941942).
- Skoglund, S. (2024). Population regulatory processes in the Baltic
  salmon. SLU PhD thesis.
  [DOI 10.54612/a.58aq72nqq6](https://doi.org/10.54612/a.58aq72nqq6).
- Lai, T.-Y., Lindroos, M., & Grønbæk, L. (2021). The role of food web
  interactions in multispecies fisheries management. *Environmental and
  Resource Economics* 79(3), 511-549.
  [DOI 10.1007/s10640-021-00571-z](https://doi.org/10.1007/s10640-021-00571-z).
- Östergren, J., et al. (2021). A century of genetic homogenization in
  Baltic salmon. *Proc. R. Soc. B* 288(1949).
  [DOI 10.1098/rspb.2020.3147](https://doi.org/10.1098/rspb.2020.3147).
- Säisä, M., et al. (2005). Population genetic structure in Baltic
  salmon. *CJFAS* 62(8).
  [DOI 10.1139/f05-094](https://doi.org/10.1139/f05-094).
- Poćwierz-Kotus, A., et al. (2015). Restitution and genetic
  differentiation of salmon populations in the southern Baltic.
  *Genetics Selection Evolution* 47:39.
  [DOI 10.1186/s12711-015-0121-9](https://doi.org/10.1186/s12711-015-0121-9).
- Anttila, P., et al. (2008). Epidemiology of *Gyrodactylus salaris* in
  the River Tornionjoki. *J. Fish Diseases* 31(5), 373-382.
  [DOI 10.1111/j.1365-2761.2008.00916.x](https://doi.org/10.1111/j.1365-2761.2008.00916.x).
- Westphal, L., von Vietinghoff, V., & Moritz, T. (2025). By-catch of
  grey seals in fish traps in the German Baltic. *Aquatic Conservation*
  35(5). [DOI 10.1002/aqc.70147](https://doi.org/10.1002/aqc.70147).
- Orell, P. & Erkinaro, J. (2007). Inter-observer variability in
  counting Atlantic salmon in a northern European river. ICES CM
  2007/Q:16.
- Sisson, S., Fan, Y., & Tanaka, M. (2007). Sequential Monte Carlo
  without likelihoods. *PNAS* 104(6), 1760-1765.
  [DOI 10.1073/pnas.0607208104](https://doi.org/10.1073/pnas.0607208104).
- Carroll, D., et al. (2024). 120-years of ecological monitoring data
  (Baltic grey seal). *J. Animal Ecology* 93(5), 525-539.
  [DOI 10.1111/1365-2656.14065](https://doi.org/10.1111/1365-2656.14065).

### ICES / HELCOM

- ICES (2023). *WGBAST*. ICES Scientific Reports 5(26).
  [DOI 10.17895/ices.pub.22328542](https://doi.org/10.17895/ices.pub.22328542).
- ICES (2025). *WGBAST stock annex, sal.27.22-31 + sal.27.32*.
  [DOI 10.17895/ices.pub.25869088.v2](https://doi.org/10.17895/ices.pub.25869088.v2).
- ICES (2026). *WGBAST*. ICES Scientific Reports.
  [DOI 10.17895/ices.pub.29118545.v3](https://doi.org/10.17895/ices.pub.29118545.v3).
- HELCOM. *Grey seal abundance core indicator*.
  <https://indicators.helcom.fi/indicator/grey-seal-abundance/>.

### Project internal

- Arc K spec: `docs/validation/v0.34.0-pspc-spec.md`
- Arc M spec: `docs/validation/v0.36.0-multi-river-baltic.md`
- Original K-Q plan (reviewed 8 iterations):
  `docs/superpowers/plans/2026-04-20-arc-K-to-Q-wgbast-roadmap.md`
- Expanded M-Q plan (reviewed 3 iterations):
  `docs/superpowers/plans/2026-04-20-arc-M-to-Q-expanded.md`
