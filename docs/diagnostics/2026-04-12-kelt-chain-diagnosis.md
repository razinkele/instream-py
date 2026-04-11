# v0.20.0 Kelt-Chain Diagnosis — 2026-04-12

## Summary

The v0.19.0 Baltic 7-year calibration run produces **108 returns + 0 kelts**. Instrumented diagnostic (`scripts/diagnose_kelt.py`) confirms the kelt roll mechanism is **correctly wired**; the upstream `RETURNING_ADULT → SPAWNER` path is starved because returning adults die during the 4–7 month freshwater hold between return (March–June) and spawn (October–November).

## Diagnostic Output

```
total_smoltified:     2994
total_returned:       108
total_kelts:          0
total_repeat_spawners:0

Kelt roll call log: 8 non-empty calls
  Cumulative SPAWNER sightings:  8
  Cumulative eligible (cond>=0.5):5
  Cumulative kelts promoted:      0

RETURNING_ADULT presence census:
  Year  RA-days   RA-max    SP-days
  2011  0         0         251
  2012  0         0         228
  2013  184       108       217
  2014  0         0         188
  2015  0         0         233
  2016  0         0         188
  2017  0         0         260
  2018  0         0         21
  First RA date: 2013-03-31, last: 2013-09-30
```

## Key Findings

### 1. Kelt roll mechanism works

The v0.17.0 `apply_post_spawn_kelt_survival` function fires correctly. With `kelt_survival_prob = 0.25` and 5 eligible SPAWNERs observed, the binomial(5, 0.25) = 0 outcome has probability **~0.24** — statistically unlucky, not structurally broken. A 20× larger eligible pool (5 → 100 SPAWNERs) would produce ~25 kelts in expectation.

### 2. All 108 returns happen in a single cohort year (2013)

The fixture seeds 3000 PARR → 2994 smoltify in 2011 → return after 1–2 sea winters in 2013. **No secondary marine cohort forms** in 2014-2018: the spawned redds in 2013 hatch into FRY, but those second-generation FRY don't re-seed the marine pipeline because the fixture's manual `smolt_readiness = 0.9` overrides are only applied to the initial 3000 seeded fish.

### 3. Catastrophic freshwater-hold attrition

Of 108 returners to freshwater in March-June 2013, only **~8 reach SPAWNER state** by Oct-Nov 2013 — a **~93% attrition** over the 4-7 month hold period. Census shows RA presence from 2013-03-31 to 2013-09-30 (184 days); max concurrent RAs at any time = 108, meaning they peak early in the return window and decay monotonically.

### 4. Root cause: no freshwater-hold energetics for returning adults

`RETURNING_ADULT` fish are subject to the same 5 survival sources as juveniles (condition-based mortality, fish predation, terrestrial predation, stranding, high-temperature). Real Atlantic salmon rely on **marine fat reserves** to survive a non-feeding freshwater hold phase — the current model has no fasting energetics and no life-stage-specific survival-source filter, so returners starve over 4-7 months.

### 5. The 38 alive redds at end-of-run come from the initial population

`configs/example_calibration_baltic.yaml` loads `ExampleA-InitialPopulations.csv` which pre-seeds ~2500 natal-cohort adults that remain in life_history = SPAWNER year-round (confirmed by 188–260 SP-days/year in all 8 years even when RA count = 0). These are the fish creating the 2011-2017 redds, **not** the marine cohort.

## v0.20.0 Fix Candidates

### Option A — Life-stage survival filter (smallest surgery)

Add a `life_history == RETURNING_ADULT` exclusion to the 5 survival-source applies in `src/instream/modules/survival.py`. Rationale: returning adults are fasting on marine fat reserves and are not subject to drift-based predation risk models designed for juveniles. Risk: oversimplifies — real returners do die from disease, obstruction, and terrestrial predation during the hold.

**Estimated scope**: 5-10 LOC + test for "RA survives 6-month hold in a stable freshwater environment".

### Option B — Fasting energy pool (ecologically correct)

Add a `fasting_reserve_J` field to `TroutState` populated at return time from `weight × energy_density × fasting_fraction`, consumed at a daily metabolic rate, triggering mortality only when depleted. Rationale: matches Atlantic salmon biology. Risk: requires parameter retrieval for Baltic fasting metabolic rate, fasting_fraction (typical 30-40% of body mass), and ecological validation.

**Estimated scope**: 40-80 LOC + 3-5 new tests + 2-3 scite-retrieved citations for fasting metabolism (Jonsson et al., Bordeleau et al., etc.).

### Option C — Shorten the hold window (workaround)

Move the spawn window earlier (e.g. July-August) so returners spawn shortly after arrival. Rationale: trivial config change, restores kelt counter to non-zero. Risk: **ecologically incorrect** — Baltic Atlantic salmon genuinely spawn Oct-Nov, this would be a cosmetic fix that breaks the biological interpretation.

**Not recommended except as a debugging aid.**

### Option D — Seed more returners directly

Expand the `TestICESCalibrationBaltic` fixture to seed a direct RETURNING_ADULT cohort at high `fitness_memory` and `condition`, bypassing the hold-attrition bottleneck. Rationale: tests the kelt roll in isolation without requiring ecological changes. Risk: moves the test further from a realistic Baltic lifecycle simulation.

**Estimated scope**: 10-15 LOC in the fixture + potentially weakened ecological fidelity claim on the calibration test.

## Recommendation

**Option B** (fasting energy pool) is the correct long-term fix but is substantial scope. **Option A** (life-stage survival filter) is a pragmatic v0.20.0 interim that unblocks the kelt counter and can be refined into Option B in v0.21.0 once parameters are scite-retrieved.

v0.20.0 plan should:

1. Implement Option A with a focused life-stage filter on `survival.py::apply_condition_mortality`, `apply_fish_predation`, `apply_terrestrial_predation` — exclude RETURNING_ADULT only.
2. Keep high-temperature and stranding survival active for RAs (these affect fasting adults too).
3. Add a test asserting a RA cohort with condition=1.0 survives a 180-day freshwater hold with >50% retention.
4. Re-run the Baltic 7-year calibration and expect ~50-80 SPAWNERs (of 108 returns), ~12-20 kelts, non-zero repeat-spawn fraction in the next run (though still below 1% due to one-cohort horizon issue).
5. Document the temporary nature of Option A in `calibration-notes.md` with a scite-retrieved rationale (e.g., Fleming 1996 on Atlantic salmon freshwater fasting metabolism).

## Diagnostic Script

`scripts/diagnose_kelt.py` — reproducible diagnostic. Run with:

```bash
micromamba run -n shiny python scripts/diagnose_kelt.py
```

Runtime: ~5-6 minutes for the 7-year Baltic run.
