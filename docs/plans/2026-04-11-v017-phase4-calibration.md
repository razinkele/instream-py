# v0.17.0 Phase 4 — ICES WGBAST Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (recommended for this phase — calibration is iterative with user checkpoints) or `superpowers:subagent-driven-development`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an end-to-end calibration test that runs the full marine-enabled model over a multi-year cohort and asserts emergent smolt-to-adult survival, kelt production, and repeat-spawner fractions land inside ICES-plausible bands — without any test-level hazard overrides. Produce scite MCP-backed `docs/calibration-notes.md` documenting every parameter's provenance.

**Architecture:** A slow-marked E2E test (`tests/test_calibration_ices.py`) pre-seeds ~3000 PARR into dead TroutState slots on an extended 5-year run of `configs/example_marine.yaml` and asserts on `MarineDomain.total_smoltified`, `total_returned`, `total_kelts`, and `total_repeat_spawners`. If the test fails, Task 4.3 iteratively tunes `MarineConfig` defaults until the test passes without overrides. Task 4.5 removes the now-redundant override in `tests/test_marine_survival.py::test_cohort_attrition_matches_iCes_band`. Task 4.6 writes literature-backed provenance notes.

**Tech Stack:** Python 3.13, numpy, pydantic, pytest with `@pytest.mark.slow`, micromamba `shiny` environment, scite MCP (`mcp__claude_ai_scite__search_literature`) via the `netlogo-oracle` skill's scientific-literature workflow.

**Branch / worktree:** work inline on master (v0.17.0 phases 1-3 already committed as `2eed6ae`, `1fb2cbb`, `7ddf28e`).

**Risk budget:** This is the highest-risk phase of v0.17.0. Two risks have been identified during planning and are addressed explicitly:

1. **Trout capacity blocker.** `example_marine.yaml` declares `trout_capacity: 2000`, which is insufficient for a 3000-PARR calibration cohort that must also leave headroom for spawning-produced fry and adult arrivals. **Resolution**: Task 4.1 creates a dedicated `configs/example_calibration.yaml` that inherits from `example_marine.yaml` and bumps capacity to 6000. Main plan's inline fixture allocation (`np.where(~ts.alive)[0][:3000]`) remains correct but now has room.

2. **Simulation horizon blocker.** `example_marine.yaml` hard-codes `end_date: "2013-09-30"` — only 2.5 years from start. Phase 4's 5-year cohort follow-through requires either `end_date_override` at runtime **or** an explicit end date in the calibration config. We use the runtime override and guard against time-series exhaustion: if the hydraulics time series runs out before the simulation end, `TimeManager.is_done` returns True and the run stops cleanly, but the cohort-attrition test may report under-developed SAR. The calibration test therefore asserts on `total_smoltified > 0` as an early gate and skips with a clear message if the time series is too short.

3. **Species mismatch (scientific).** `example_marine.yaml` uses `Chinook-Spring` (Pacific anadromous, semelparous in nature), but Phase 4 asserts against ICES WGBAST Atlantic-salmon bands. Chinook post-smolts enter the ocean smaller than Atlantic smolts (Healey 1991) and Chinook CMax peaks above Baltic post-smolt thermal optima (Handeland et al. 2008, DOI 10.1016/j.aquaculture.2008.03.057), so the same marine hazards applied to a Chinook cohort will run SAR **systematically lower** than Atlantic parity. The test is therefore a **collapse detector / emergent-plausibility check**, not a quantitative Atlantic-salmon calibration. Task 4.6 must flag this explicitly. Dedicated Baltic Atlantic salmon species config is a v0.18.0 candidate.

4. **Band is a collapse detector, not a 5% vs 10% discriminator.** At 3000 smolts and ~150 expected returns, the 2σ noise on SAR is ~0.8 pp. The 2–18% band is ~20× the noise — it cannot distinguish 5% from 10% SAR. This is **intentional** at v0.17.0: we are gating "pipeline does not explode", not matching a point target. If at some future version the species mismatch is fixed and the band is tightened, stat-power becomes a real concern. Task 4.2 docstring and `docs/calibration-notes.md` must both state this explicitly.

5. **Tuning strategy (Task 4.3) — staged, not free-for-all.** Seal hazard is the dominant 1SW+ mortality (acts on fish with length ≥ 40 cm via the logistic). Cormorant hazard is the dominant post-smolt mortality (fish < 40 cm during the 28-day vulnerability window). They act on **disjoint size regimes** so they are independently tunable, but SAR is sensitive to both stages — tuning them in arbitrary order is non-identifiable. Task 4.3 adopts a fixed staged order: cormorant first (diagnosed against day-28 post-smolt survival), seal second (diagnosed against 1SW return fraction), `marine_mort_base` left untouched (Thorstad et al. 2012 DOI 10.1111/j.1095-8649.2012.03370.x backs 0.001/day as literature-standard post-smolt background mortality).

---

## Scope Check

This is a **single subsystem** (calibration validation + parameter tuning + docs). No multi-plan split needed. The phase produces:
- One new test file (`tests/test_calibration_ices.py`)
- One new config file (`configs/example_calibration.yaml`)
- One new docs file (`docs/calibration-notes.md`)
- Parameter tuning edits to `src/instream/marine/config.py`
- Removal of one test-level override in `tests/test_marine_survival.py`

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `configs/example_calibration.yaml` | create | Dedicated calibration config: `trout_capacity: 6000`, inherits `Chinook-Spring` species params, same 3 Baltic zones as `example_marine.yaml` |
| `tests/test_calibration_ices.py` | create | Slow-marked E2E: 5-year run, 3000-PARR cohort, asserts SAR/kelt/repeat bands via `MarineDomain` counters |
| `src/instream/marine/config.py` | modify (lines ~82–115) | Final-pass default tuning if Task 4.1 test fails the bands. May not need changes if v0.15.0 calibrated defaults already work |
| `tests/test_marine_survival.py` | modify (lines ~29–40, ~186–189) | Remove `cfg.model_copy(update=...)` override in `test_cohort_attrition_matches_iCes_band`; update the `cfg` fixture to inherit production defaults |
| `docs/calibration-notes.md` | create | scite MCP-backed APA citations for every parameter that Task 4.3 tunes, plus the species-mismatch disclosure |

---

## Phase 4 Task Dependency Graph

```
Task 4.1 (calibration config)
    │
    v
Task 4.2 (failing test first)
    │
    ├── IF ALL PASS → skip 4.3 entirely
    │
    ├── IF ANY FAIL → Task 4.3 Stage A (cormorant tuning)
    │                     │
    │                     v
    │                 Task 4.3 Stage B (seal tuning)
    │                     │
    │                     v
    │                 Task 4.3 Stage C (regression check, hard stop at 6 edits)
    │
    v
Task 4.5 (remove test_cohort_attrition override — requires Phase 4 defaults to be in place)
    │
    v
Task 4.6 (scite-backed calibration-notes.md — cites whatever defaults ended up committed)
    │
    v
Task 4.7 (full regression run — verification only, no commit)
```

**Note**: the original plan draft listed Task 4.4 as a separate node for "iterate if Task 4.3 didn't converge". Task 4.3 is now structured as three internal stages (A / B / C) with an explicit 6-edit ceiling, so Task 4.4 is folded into Task 4.3. If the staged scheme fails to converge within 6 edits, escalate to user — do NOT add more iterations.

---

## Task 4.1: Create `configs/example_calibration.yaml`

**Files:**
- Create: `configs/example_calibration.yaml`

**Rationale**: `example_marine.yaml` has `trout_capacity: 2000` and `end_date: "2013-09-30"`. Phase 4 needs ≥6000 capacity (3000 cohort + headroom for spawning + arrivals) and an end date 5 years after start. Rather than mutating `example_marine.yaml` (which would break existing tests), fork it into a dedicated calibration config.

- [ ] **Step 1: Inspect `example_marine.yaml` to list fields that differ**

Run from the repo root `C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py`:

```bash
grep -nE "trout_capacity|end_date|start_date|redd_capacity" "configs/example_marine.yaml"
```

Expected output (exact values from the current file):
```
2:  start_date: "2011-04-01"
3:  end_date: "2013-09-30"
17:  trout_capacity: 2000
18:  redd_capacity: 500
```

- [ ] **Step 2: Copy the file**

```bash
cp "configs/example_marine.yaml" "configs/example_calibration.yaml"
```

- [ ] **Step 3: Change `end_date` to 5-year horizon**

Use the Edit tool on `configs/example_calibration.yaml`:

```
old_string: end_date: "2013-09-30"
new_string: end_date: "2016-03-31"
```

- [ ] **Step 4: Change `trout_capacity` to 6000**

Use the Edit tool on `configs/example_calibration.yaml`:

```
old_string:   trout_capacity: 2000
new_string:   trout_capacity: 6000
```

- [ ] **Step 5: Change `redd_capacity` to 1500**

Use the Edit tool on `configs/example_calibration.yaml`:

```
old_string:   redd_capacity: 500
new_string:   redd_capacity: 1500
```

- [ ] **Step 6: Verify the three edits landed and nothing else changed**

```bash
diff "configs/example_marine.yaml" "configs/example_calibration.yaml"
```

Expected output: exactly three unified-diff hunks, one per changed line. Any additional hunks mean a stray edit — re-check Step 3/4/5.

- [ ] **Step 7: Verify the YAML parses and `load_config` surfaces the new values**

```bash
micromamba run -n shiny python -c "from instream.io.config import load_config; from pathlib import Path; c = load_config(Path('configs/example_calibration.yaml')); print(c.performance.trout_capacity, c.simulation.end_date)"
```

Expected output: `6000 2016-03-31`

- [ ] **Step 8: Record the hydraulics time-series coverage window**

```bash
micromamba run -n shiny python -c "import pandas as pd; df = pd.read_csv('tests/fixtures/example_a/Example-Project-A_1Reach-1Species/ExampleA-TimeSeriesInputs.csv'); print('first:', df.iloc[0, 0], 'last:', df.iloc[-1, 0], 'rows:', len(df))"
```

Expected: two dates and a row count. Write the last date down — Task 4.2's fixture will skip the test if the last date is before `start_date + 5 years`. Also note it for Task 4.6's species-mismatch disclosure (doubles as time-series coverage disclosure).

- [ ] **Step 9: Commit**

```bash
git add configs/example_calibration.yaml
git commit -m "config: add example_calibration.yaml (5-year horizon, 6000 capacity)"
```

---

## Task 4.2: Write the failing calibration test

**Files:**
- Create: `tests/test_calibration_ices.py`

**Rationale**: Write the test FIRST so we can see exactly where the v0.15.0/v0.16.0 defaults land on each metric. This gives concrete numbers to tune against in Task 4.3, rather than blind guesswork.

- [ ] **Step 1: Create `tests/test_calibration_ices.py` with full test body**

```python
"""ICES WGBAST end-to-end calibration test (v0.17.0 Phase 4).

Asserts that the full marine-enabled inSALMON pipeline produces emergent
cohort behaviour inside Atlantic-salmon plausibility bands over a 5-year
run with a 3000-PARR pre-seeded cohort.

Reference: ICES WGBAST 2024 Baltic Salmon and Sea Trout Assessment Working
Group reports 2-15% smolt-to-adult return for Baltic wild rivers. The upper
band here is stretched to 18% to absorb iteroparous-return inflation
(~1.11x at 10% realized repeat rate) and stochastic tail variance.

SPECIES MISMATCH DISCLAIMER: This test runs against a Chinook-Spring config
block because that is the only anadromous species currently in the example
configs. The bioenergetics parameters are nominally Pacific Chinook, not
Baltic Atlantic salmon. The test therefore validates *emergent cohort
plausibility* under the v0.17.0 marine ecology pipeline — not
species-specific NetLogo parity. Full species-specific calibration is
out-of-scope for v0.17.0 and blocked on a dedicated Baltic salmon config
(v0.18.0 candidate).
"""

from __future__ import annotations

import datetime
from pathlib import Path

import numpy as np
import pytest

CONFIGS = Path(__file__).parent.parent / "configs"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.slow
class TestICESCalibration:
    """5-year Baltic salmon cohort calibration against ICES WGBAST bands."""

    @pytest.fixture(scope="class")
    def model(self):
        from instream.model import InSTREAMModel
        from instream.state.life_stage import LifeStage

        # end_date_override is passed as defense-in-depth against a
        # missing or mis-edited example_calibration.yaml. If the YAML's
        # end_date is already 2016-03-31 this override is a no-op; if
        # it was accidentally left at 2013-09-30 the override wins.
        m = InSTREAMModel(
            CONFIGS / "example_calibration.yaml",
            data_dir=FIXTURES / "example_a",
            end_date_override="2016-03-31",
        )

        # Hard skip if the hydraulics time series cannot support a
        # 5-year run. We check the actual CSV last row, NOT
        # m.time_manager._end_date — the latter always reflects
        # end_date_override and so never surfaces the CSV-coverage
        # problem the guard is meant to catch.
        #
        # The CSV lives directly under tests/fixtures/example_a/ with
        # NO subdirectory, and its first two rows are ";"-prefixed
        # comments that pandas must skip or the header parse explodes.
        import pandas as pd
        start = datetime.date(2011, 4, 1)
        required_end = start + datetime.timedelta(days=5 * 365)
        ts_csv = FIXTURES / "example_a" / "ExampleA-TimeSeriesInputs.csv"
        try:
            df = pd.read_csv(ts_csv, comment=";")
            ts_last_raw = df.iloc[-1, 0]
            ts_last = pd.Timestamp(ts_last_raw).date()
        except Exception as exc:
            pytest.skip(
                f"Could not read hydraulics time series last row "
                f"from {ts_csv}: {exc}"
            )
        if ts_last < required_end:
            pytest.skip(
                f"Hydraulics time series ends {ts_last}, before "
                f"required 5-year horizon {required_end}. Either "
                f"extend the time series or shorten the calibration "
                f"horizon — the SAR test cannot run meaningfully "
                f"against a truncated ocean window."
            )

        # Allocate 3000 PARR into dead TroutState capacity. Relabelling
        # pre-alive fish (as the earlier E2E fixture did) yields only
        # 50-200 fish, making the SAR assertion stochastically fragile.
        ts = m.trout_state
        dead = np.where(~ts.alive)[0]
        n_parr = min(len(dead), 3000)
        if n_parr < 1500:
            pytest.skip(
                f"TroutState capacity too small for calibration test "
                f"(only {n_parr} dead slots available, need >=1500). "
                f"Verify configs/example_calibration.yaml has "
                f"trout_capacity >= 6000."
            )
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
        # Fresh marine state — prevents any leftover leakage from the
        # pre-allocation of the TroutState arrays.
        ts.zone_idx[parr] = -1
        ts.sea_winters[parr] = 0
        ts.smolt_date[parr] = -1
        ts.is_hatchery[parr] = False

        m.run()
        return m

    def test_smoltification_happened(self, model):
        """Gate: if no fish smoltified, the pipeline is broken and every
        downstream assertion is moot. Fail fast with a clear message."""
        md = model._marine_domain
        assert md.total_smoltified > 0, (
            "No fish smoltified during the 5-year run. "
            "Either the pre-seeded PARR cohort never reached the river "
            "mouth, or the smolt-readiness / smolt-min-length thresholds "
            "blocked them all. Inspect model._do_migration wiring."
        )

    def test_smolt_to_adult_survival_plausible(self, model):
        """SAR = total_returned / total_smoltified should land in a
        broad plausibility band. This is a **collapse detector**, not a
        quantitative 5% vs 10% discriminator — at a 3000-smolt cohort
        the 2σ noise on SAR is ~0.8 pp, so the 2–18% band width (16 pp)
        is 20× the noise. It cannot distinguish specific target SARs.

        Species mismatch: the test runs against a Chinook-Spring config
        (Pacific semelparous) with Atlantic-salmon hazard parameters.
        Chinook CMax peaks above Baltic thermal optima (Handeland et al.
        2008), so SAR will run **systematically lower** than an Atlantic
        cohort under the same hazards. The lower bound of 2% is therefore
        the fragile edge for THIS species, not 18%.

        The upper bound of 18% is ICES WGBAST 2-15% Baltic-wild stretched
        by ~1.11× for iteroparous-return inflation (Fleming & Reynolds
        2004) plus stochastic tail margin.

        Future work (v0.18.0): add a dedicated Baltic Atlantic salmon
        species config, then tighten this band to 3–12% for genuine
        point calibration.
        """
        md = model._marine_domain
        sar = md.total_returned / md.total_smoltified
        assert 0.02 <= sar <= 0.18, (
            f"Smolt-to-adult return {sar:.4f} outside 2–18% collapse "
            f"band (smoltified={md.total_smoltified}, "
            f"returned={md.total_returned}). "
            f"If SAR < 2%, cohort has collapsed — loosen hazards "
            f"(see Task 4.3 staged tuning). "
            f"If SAR > 18%, hazards are absent — check that "
            f"apply_marine_survival is being called in MarineDomain.daily_step."
        )

    def test_some_fish_became_kelts(self, model):
        """With a 3000-smolt cohort and 0.25 river-exit kelt probability,
        expect roughly 0.25 x (post-spawn survivors ~ 100-500) = 25-125
        kelts over the 5-year horizon. Any value > 0 is a 5-sigma-safe
        assertion given the cohort size — flaking requires catastrophic
        upstream mortality, not kelt-probability tuning."""
        md = model._marine_domain
        assert md.total_kelts > 0, (
            f"No kelts produced (returned={md.total_returned}, "
            f"smoltified={md.total_smoltified}). "
            f"Check apply_post_spawn_kelt_survival wiring in _do_day_boundary "
            f"and verify species.kelt_survival_prob > 0."
        )

    def test_repeat_spawner_fraction_baltic_range(self, model):
        """Baltic repeat-spawner rates: Niemelä et al. 2006 on Teno
        ~5-8%, Simojoki virtually nil in some cohorts, Atlantic-average
        ~10-11% (Fleming & Reynolds 2004). Band 0-12% covers the full
        range of Baltic rivers plus a small rng tail. The Newfoundland
        33% outlier (Campbellton river) is NOT plausible for Baltic
        modelling; the 15% figure from the earlier plan draft was too
        loose and let Newfoundland-level repeat rates pass silently.

        Note statistical power: at 3000-smolt cohort with expected
        150 returns and ~6% realized repeat rate, expected repeats are
        ~9 with 2σ noise ~6 — the estimator has ±4-5 pp noise against
        a 12 pp band. Test will reliably detect a cohort where repeats
        are an order of magnitude off; it will not detect finer drift."""
        md = model._marine_domain
        if md.total_returned == 0:
            pytest.skip("No returns in this run — cannot compute repeat fraction")
        repeat_frac = md.total_repeat_spawners / md.total_returned
        assert 0.0 <= repeat_frac <= 0.12, (
            f"Repeat-spawner fraction {repeat_frac:.4f} outside plausible "
            f"Baltic 0–12% range (repeat={md.total_repeat_spawners}, "
            f"total={md.total_returned}). Tune kelt_survival_prob down if "
            f"repeats are too high, or up if too low."
        )

    def test_counters_are_plain_ints(self, model):
        """Regression guard for the v0.17.0 counter type contract.
        A numpy int0 scalar would pass isinstance(x, int) in some numpy
        versions but fail in others — we want plain Python ints."""
        md = model._marine_domain
        for name in ("total_smoltified", "total_returned", "total_kelts", "total_repeat_spawners"):
            val = getattr(md, name)
            assert type(val) is int, (
                f"MarineDomain.{name} should be a plain int, got {type(val).__name__}"
            )
```

- [ ] **Step 2: Run the test to see where the v0.16.0 defaults land**

Run: `micromamba run -n shiny python -m pytest tests/test_calibration_ices.py -v --tb=short`
Expected: SOME tests may fail — record the actual numeric values printed in failure messages. These become the tuning targets for Task 4.3.

Record the four numbers in your working notes:
- `total_smoltified`: actual value
- `total_returned`: actual value
- `total_kelts`: actual value
- `SAR` (computed): actual value
- `repeat_frac` (computed): actual value or "skipped"

- [ ] **Step 3: If ALL tests pass, skip directly to Task 4.5** (the defaults already work — no tuning needed)

- [ ] **Step 4: Commit the test regardless of pass/fail state**

```bash
git add tests/test_calibration_ices.py
git commit -m "test(calibration): ICES WGBAST 5-year cohort calibration test"
```

Committing the test while it may be failing is intentional — it documents the current calibration state and the next task's tuning targets.

---

## Task 4.3: Staged tuning — cormorant first, seal second (ONLY IF Task 4.2 failed)

**Files:**
- Modify: `src/instream/marine/config.py` lines 96–110 (`marine_mort_seal_max_daily`, `marine_mort_cormorant_max_daily`)

**Rationale**: Seal hazard is the dominant 1SW+ mortality (logistic midpoint ~60 cm), cormorant hazard is the dominant post-smolt mortality (logistic midpoint ~27 cm during the 28-day window). They act on **disjoint size regimes**, so they can be tuned independently. `marine_mort_base` is left untouched — its 0.001/day default is literature-backed by Thorstad et al. 2012 (DOI 10.1111/j.1095-8649.2012.03370.x) and tuning it would compound with seal/cormorant and make convergence non-identifiable.

**Expected iterations**: 2–3 (one cormorant, one seal, possibly one refinement). Hard ceiling 6 total edits.

### Stage A — Cormorant tuning (fixes post-smolt survival window)

- [ ] **Step A1: Diagnose from Task 4.2's recorded SAR**

Cormorant is the dominant hazard for fish < 40 cm during days 0–28 post-smolt. If SAR failed on the LOW side (< 0.02), first suspicion is cormorant over-kill of the post-smolt cohort. If SAR is in-band but `test_some_fish_became_kelts` failed with zero kelts, cormorant killed the entire cohort before any returned to spawn.

- [ ] **Step A2: Edit `marine_mort_cormorant_max_daily`**

Use the Edit tool on `src/instream/marine/config.py`:

```
old_string:     marine_mort_cormorant_max_daily: float = 0.010
new_string:     marine_mort_cormorant_max_daily: float = 0.007
```

The 0.010 → 0.007 step halves the expected post-smolt cormorant attrition over the 28-day window from ~25% to ~18%. Adjust the target based on the actual failure direction:
- SAR was < 0.005: try 0.005 instead of 0.007
- SAR was 0.005–0.015: try 0.007
- SAR was > 0.18: tighten the other direction, try 0.013

- [ ] **Step A3: Re-run only the SAR test**

```bash
micromamba run -n shiny python -m pytest tests/test_calibration_ices.py::TestICESCalibration::test_smolt_to_adult_survival_plausible -v
```

Expected: PASS (SAR ≥ 0.02). If still fails low, repeat Step A2 with a smaller value (try 0.005, then 0.003). If SAR is now in-band but kelt/repeat tests still fail, proceed to Stage B (seal). If SAR is now > 0.18, Stage A over-corrected — raise cormorant to 0.012 and proceed to Stage B for fine-tuning.

- [ ] **Step A4: Commit the Stage A change**

```bash
git add src/instream/marine/config.py
git commit -m "tune(marine): stage A cormorant tuning for calibration SAR band"
```

### Stage B — Seal tuning (fixes adult return fraction)

- [ ] **Step B1: Diagnose from the post-Stage-A test run**

If kelt/repeat tests fail and SAR is in-band, seal predation is either killing too many adults before their second run (low repeat count) or not enough (high repeat count).

- [ ] **Step B2: Edit `marine_mort_seal_max_daily`**

Use the Edit tool on `src/instream/marine/config.py`:

```
old_string:     marine_mort_seal_max_daily: float = 0.003
new_string:     marine_mort_seal_max_daily: float = 0.002
```

The 0.003 → 0.002 step reduces daily adult hazard by ~33%, giving the cohort a better chance to complete a second spawning run. If the repeat fraction was too HIGH instead (> 0.12), invert: 0.003 → 0.004.

- [ ] **Step B3: Re-run the full calibration test class**

```bash
micromamba run -n shiny python -m pytest tests/test_calibration_ices.py -v
```

Expected: all 5 tests PASS (gate, SAR, kelts>0, repeat fraction, counter types). If repeats are still out of band, repeat Step B2 with a different value. If SAR has drifted out of band from the seal change, go back to Stage A with a small adjustment.

- [ ] **Step B4: Commit the Stage B change**

```bash
git add src/instream/marine/config.py
git commit -m "tune(marine): stage B seal tuning for calibration repeat-spawner band"
```

### Stage C — Full regression and convergence check

- [ ] **Step C1: Run the rest of the marine unit suites to catch non-calibration regressions**

```bash
micromamba run -n shiny python -m pytest tests/test_marine_survival.py tests/test_marine.py tests/test_marine_growth.py tests/test_marine_fishing.py tests/test_marine_backend.py tests/test_kelt_survival.py tests/test_hatchery.py -q
```

Expected: 0 failures. If a previously-green test now fails, the tuning broke an explicit numeric assertion in a unit test — most likely `test_cohort_attrition_matches_iCes_band` which Task 4.5 will soon update. Record which test failed and proceed to Task 4.5.

- [ ] **Step C2: Hard stop after 6 total edits**

If Stage A + Stage B + refinements exceed 6 config edits and the calibration test still fails, **stop**. The target is mis-specified. Escalate to user with:
- Every tuning value tried
- Every resulting SAR / kelt / repeat value
- The recorded values from Task 4.2 baseline

Do NOT loosen the test bands as a workaround.

---

## Task 4.5: Remove the `test_cohort_attrition` override

**Files:**
- Modify: `tests/test_marine_survival.py` — the `cfg` fixture (currently lines 20–40) and the `model_copy` override block inside `test_cohort_attrition_matches_iCes_band` (currently lines 182–186). Run `grep -n "@pytest.fixture\|model_copy" tests/test_marine_survival.py` before editing to get current line numbers.

**Rationale**: Before v0.17.0 the `test_cohort_attrition_matches_iCes_band` test had two layers of band-setting: (a) a `cfg` fixture that hard-coded `marine_mort_seal_max_daily=0.02` (the design-doc peak, pre-calibration), and (b) a `model_copy(update={...})` block inside the test that overrode those hard-coded values back down to calibrated numbers. After Phase 4 tuning, the fixture can inherit the production defaults directly and the `model_copy` block becomes redundant.

- [ ] **Step 1: Edit the `cfg` fixture to inherit production defaults**

Use the Edit tool on `tests/test_marine_survival.py`:

```
old_string:
@pytest.fixture
def cfg():
    return MarineConfig(
        zones=[
            ZoneConfig(name="estuary", area_km2=10.0),
            ZoneConfig(name="coastal", area_km2=100.0),
            ZoneConfig(name="baltic", area_km2=1000.0),
        ],
        marine_mort_seal_L1=40.0,
        marine_mort_seal_L9=80.0,
        marine_mort_seal_max_daily=0.02,
        marine_mort_base=0.001,
        marine_mort_cormorant_L1=15.0,
        marine_mort_cormorant_L9=40.0,
        marine_mort_cormorant_max_daily=0.03,
        marine_mort_cormorant_zones=["estuary", "coastal"],
        post_smolt_vulnerability_days=28,
        temperature_stress_threshold=20.0,
        temperature_stress_daily=0.01,
        marine_mort_m74_prob=0.0,
    )
```

```
new_string:
@pytest.fixture
def cfg():
    # v0.17.0 Phase 4 — inherit production hazard defaults from MarineConfig.
    # Prior drafts of this fixture hard-coded the design-doc peak values
    # (seal_max_daily=0.02, cormorant_max_daily=0.03) which collapse a
    # cohort to <1% in 2 years. Phase 4 calibrated the production defaults
    # to land in the ICES WGBAST band natively, so hard-coding here is
    # both redundant and a maintenance trap — the single source of truth
    # is MarineConfig.
    return MarineConfig(
        zones=[
            ZoneConfig(name="estuary", area_km2=10.0),
            ZoneConfig(name="coastal", area_km2=100.0),
            ZoneConfig(name="baltic", area_km2=1000.0),
        ],
        marine_mort_cormorant_zones=["estuary", "coastal"],
    )
```

- [ ] **Step 2: Delete the `model_copy` override inside the cohort-attrition test**

Use the Edit tool on `tests/test_marine_survival.py`:

```
old_string:
        cfg = cfg.model_copy(update={
            "marine_mort_seal_max_daily": 0.003,
            "marine_mort_cormorant_max_daily": 0.010,
            "marine_mort_base": 0.001,
        })
        n = 10_000
```

```
new_string:
        n = 10_000
```

- [ ] **Step 3: Run the cohort-attrition test**

```bash
micromamba run -n shiny python -m pytest tests/test_marine_survival.py::TestMarineSurvivalIntegration::test_cohort_attrition_matches_iCes_band -v
```

Expected: PASS. If it fails, the Phase 4 defaults are incompatible with the cohort-attrition test's `0.01 <= survivorship <= 0.35` band. Do NOT loosen the band as a workaround — Task 4.3 needs another iteration.

- [ ] **Step 4: Run the full marine_survival suite**

```bash
micromamba run -n shiny python -m pytest tests/test_marine_survival.py -v
```

Expected: all 16 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_marine_survival.py
git commit -m "test(marine_survival): rely on Phase 4 calibrated defaults"
```

---

## Task 4.6: Write `docs/calibration-notes.md` with scite-backed citations

**Files:**
- Create: `docs/calibration-notes.md`

**Rationale**: Every tuned parameter in `MarineConfig` needs peer-reviewed provenance retrievable via scite MCP. This is the `netlogo-oracle` skill's "science validation" axis applied to v0.17.0 parameters.

- [ ] **Step 1: Invoke the `netlogo-oracle` skill**

Call the Skill tool with `skill: netlogo-oracle`. Follow the "Scientific Literature Validation" workflow section, specifically the 7-step process.

- [ ] **Step 2: Run scite searches for each tuned parameter**

For each parameter that appears in the final-state `MarineConfig` (from v0.17.0 Phase 4 tuning), run `mcp__claude_ai_scite__search_literature` with at least one targeted query. Suggested starting queries:

| Parameter | Query |
|---|---|
| `marine_mort_seal_max_daily` | `"grey seal predation" "Atlantic salmon" Baltic Hansson` |
| `marine_mort_cormorant_max_daily` | `cormorant predation "post-smolt" Dalälven OR Simojoki` |
| `marine_mort_base` | `"Atlantic salmon" "post-smolt" natural mortality marine` |
| `hatchery_predator_naivety_multiplier` | `hatchery reared wild salmon recapture Kallio-Nyberg` |
| `kelt_survival_prob` | `"Atlantic salmon" iteroparous kelt survival Baltic` |
| `marine_cmax_A`/`marine_cmax_B` | `"Fish Bioenergetics" Hanson salmon CMax` |
| SAR target band | `"smolt-to-adult return" Baltic ICES WGBAST wild` |

Each query returns up to 5 hits. For each hit:
1. Check `editorialNotices` — skip retracted papers.
2. Retrieve full-text excerpts for the most relevant hit via scite's DOI-based full-text tool with `term="results"` or `term="methods"`.
3. Record: DOI, author/year, direct quote supporting the parameter value.

- [ ] **Step 3: Populate `docs/calibration-notes.md` with real content**

Create the file with the following structure. Every `<text>`, `<direct quote>`, `<doi>`, and `[citation N]` placeholder MUST be replaced by content retrieved in Step 2 — do NOT commit the template as-is.

```markdown
# v0.17.0 Marine Calibration Notes

This document records the peer-reviewed provenance of every tuned
default parameter in `instream.marine.config.MarineConfig`. Every
numeric value below is backed by at least one peer-reviewed source
retrieved via the scite MCP integration (see the `netlogo-oracle`
skill for the verification workflow).

## Species mismatch disclaimer

The calibration test at `tests/test_calibration_ices.py` runs against
a `Chinook-Spring` species config (the only anadromous species in the
example configs at v0.17.0 release time). Chinook is a Pacific
semelparous species while the parameter bands below are sourced from
Atlantic salmon / Baltic Sea literature. Chinook CMax peaks above
Baltic post-smolt thermal optima (Handeland et al. 2008) and Chinook
post-smolts enter the ocean smaller than Atlantic smolts (Healey 1991),
so the same hazard parameters run SAR systematically lower for this
species. The calibration test is therefore a collapse detector and
emergent-plausibility check, not species-specific validation. A
dedicated Baltic Atlantic salmon config is a v0.18.0 candidate.

## Time-series coverage disclaimer

The hydraulics time series at
`tests/fixtures/example_a/Example-Project-A_1Reach-1Species/ExampleA-TimeSeriesInputs.csv`
covers the period [FILL FROM TASK 4.1 STEP 8]. The calibration test
uses `end_date_override="2016-03-31"` to run a 5-year horizon; if the
time series ends before that date, `TimeManager.is_done` stops the
run cleanly and the test's pytest.skip gate in the fixture fires with
an explicit message.

## Calibration targets (ICES WGBAST 2024)

| Metric | Target band | Source DOI |
|---|---|---|
| Smolt-to-adult return (SAR) | 2-15% Baltic wild | [FILL — cite scite hit] |
| Repeat-spawner fraction | 5-10% Baltic | [FILL — cite scite hit] |
| Mean post-smolt length at ocean entry | 12-18 cm | [FILL — cite scite hit] |

## Tuned parameters

### `marine_mort_seal_max_daily = [FILL current value from config.py after Task 4.3]`

Rationale: [FILL — 2-3 sentences from a paper retrieved via scite
search_literature that justifies the chosen value against Baltic
grey seal predation rates on Atlantic salmon]

Supporting excerpt (scite full-text, DOI [FILL]):

> "[FILL — direct quoted sentence or paragraph from the paper]"

Citation: [FILL — APA-formatted reference with DOI link as
https://doi.org/{doi}]

### `marine_mort_cormorant_max_daily = [FILL current value from config.py after Task 4.3]`

Rationale: [FILL — 2-3 sentences justifying the chosen value against
nearshore post-smolt cormorant predation rates in Baltic rivers]

Supporting excerpt (scite full-text, DOI [FILL]):

> "[FILL — direct quoted sentence or paragraph]"

Citation: [FILL — APA]

### `marine_mort_base = 0.001` (untouched in Phase 4)

Rationale: [FILL — 2-3 sentences citing Thorstad et al. 2012 on
Atlantic salmon post-smolt background mortality]

Supporting excerpt (scite full-text, DOI [FILL]):

> "[FILL — direct quoted sentence]"

Citation: [FILL — APA; expected Thorstad, E. B. et al. 2012,
Journal of Fish Biology, DOI 10.1111/j.1095-8649.2012.03370.x]

### `hatchery_predator_naivety_multiplier = 2.5`

Rationale: [FILL — 2-3 sentences citing Kallio-Nyberg et al. 2004
Simojoki wild-vs-reared recapture ratio]

Supporting excerpt (scite full-text, DOI [FILL]):

> "[FILL — direct quoted sentence]"

Citation: [FILL — APA; expected Kallio-Nyberg et al. 2004,
Journal of Fish Biology, DOI 10.1111/j.0022-1112.2004.00435.x]

### `kelt_survival_prob = 0.25`

Rationale: [FILL — 2-3 sentences citing Fleming & Reynolds 2004 and
Bordeleau et al. 2019 on Atlantic salmon iteroparous survival, and
Niemelä et al. 2006 on Teno for Baltic-specific rates]

Supporting excerpt (scite full-text, DOI [FILL]):

> "[FILL — direct quoted sentence]"

Citation: [FILL — APA; expected Bordeleau et al. 2019, CJFAS,
DOI 10.1139/cjfas-2018-0236 and/or Niemelä et al. 2006, JFB,
DOI 10.1111/j.1095-8649.2006.00967.x]

## References

[FILL — APA-formatted list of all papers cited above, each with DOI
link as https://doi.org/{doi}. Every unique DOI appearing in the
Rationale / Citation blocks above must appear here exactly once.]
```

- [ ] **Step 4: Verify no `[FILL` placeholders remain**

```bash
grep -nE "\\[FILL|<text>|<direct quote>|<doi[^>]*>|<current value>|\\(same structure\\)" docs/calibration-notes.md
```

Expected: ZERO matches. If any placeholder remains, the document is incomplete — do NOT commit until Step 2/3 produced real content for every `[FILL` token.

- [ ] **Step 5: Run Sphinx build to verify the doc doesn't break nitpicky mode**

Run: `micromamba run -n shiny sphinx-build -b html -W --keep-going -n docs/source docs/_build/html`
Expected: `build succeeded`. Note: `calibration-notes.md` is not in `docs/source/`, so it is NOT rendered by Sphinx by default — the build should be unchanged. If it fails, Phase 1's Sphinx tightening has regressed and the failure is unrelated to Phase 4.

- [ ] **Step 6: Commit**

```bash
git add docs/calibration-notes.md
git commit -m "docs(calibration): scite-backed v0.17.0 parameter provenance"
```

---

## Task 4.7: Full regression run

**Files:** none (verification only).

- [ ] **Step 1: Run the complete test suite**

Run: `micromamba run -n shiny python -m pytest tests/ -q`
Expected: all green. Record exact counts for the CHANGELOG update in Phase 6.

Expected runtime on the X1 Carbon: **~45 min** (Phases 1–3 added ~25 tests; Phase 4 adds a class-scoped fixture that runs a 5-year simulation — roughly 2× the Phase 3 E2E 2.5-year run, adding ~30 min on top of the 15 min baseline).

- [ ] **Step 2: If anything fails, diagnose and fix without loosening bands**

Common failure modes:
1. `test_cohort_attrition_matches_iCes_band` now fails → Task 4.3 tuning was too aggressive in one direction. Revisit Task 4.3.
2. `test_marine_e2e.py::test_some_fish_returned` now fails → SAR tuning reduced returners below the E2E smoke test's threshold. Verify the E2E test uses the durable counter (`total_returned > 0`), not a specific numeric.
3. `test_behavioral_validation.py::TestPopulationDynamicsExampleB` now fails → unlikely, but possible if a tuning change touched a freshwater parameter by accident. Revert any non-marine edits.

- [ ] **Step 3: No commit at this task** — verification only. Next work is Phase 5 (docs refresh).

---

## Self-Review Checklist

1. **Spec coverage**: all four items from the main v0.17.0 plan Phase 4 (calibration config + test, hazard tuning, override removal, scite-backed docs) have their own task. Tasks 4.1, 4.2, 4.5 are test-or-verify-first. Task 4.3 is only triggered by Task 4.2 failures (code-after-test). Task 4.6 is docs-only, verified by a grep gate. Task 4.7 is verify-only.

2. **Placeholder scan**: `docs/calibration-notes.md` has explicit `[FILL...]` placeholders for every scite-retrievable item (target-band DOIs, parameter rationale, quoted excerpts, citations, reference list, time-series coverage window). Task 4.6 Step 4's grep pattern `\[FILL|<text>|<direct quote>|<doi[^>]*>|<current value>|\(same structure\)` catches all of them. No other task leaves undeclared placeholders.

3. **Type consistency**: `MarineDomain.total_smoltified`, `total_returned`, `total_kelts`, `total_repeat_spawners` — all four counters are verified to be plain Python int via Task 4.2's `test_counters_are_plain_ints` regression guard. Types consistent across all tasks.

4. **Test-first discipline**: Task 4.2 is explicitly test-first and commits the failing test intentionally. Task 4.3 edits config only to make Task 4.2's test pass (code-after-test). Task 4.5's edits are tested by re-running `test_cohort_attrition_matches_iCes_band`.

5. **Commit discipline**: 5–7 commits expected across the phase:
   - 4.1 config file (always)
   - 4.2 failing calibration test (always)
   - 4.3 Stage A cormorant tune (only if 4.2 failed)
   - 4.3 Stage B seal tune (only if 4.2 failed)
   - 4.5 override removal (always)
   - 4.6 calibration notes (always)
   4.7 is verify-only with no commit.

6. **Backward compatibility**: all changes are additive (new file, new test) or removal-of-redundancy (override). No breaking signature changes. `example_marine.yaml` is untouched — only `example_calibration.yaml` is new.

7. **Risk coverage**: the three risks flagged in the header have explicit mitigations:
   - **Trout capacity (risk 1)**: Task 4.1 Step 4 bumps `trout_capacity: 2000 → 6000`. Task 4.2 fixture has a hard `pytest.skip` at < 1500 dead slots.
   - **Time-series horizon (risk 2)**: Task 4.1 Step 8 records the coverage window. Task 4.2 fixture passes `end_date_override="2016-03-31"` as defense-in-depth AND reads the actual hydraulics CSV's last row via `pd.read_csv(ts_csv, comment=";").iloc[-1, 0]`, skipping with a clear message if the CSV ends before the required 5-year horizon. The guard reads the CSV directly (not `TimeManager._end_date`, which always reflects the override and so is inert for this purpose).
   - **Species mismatch (risk 3)**: Task 4.2 SAR test docstring calls it a collapse detector, not a quantitative match. Task 4.6 `docs/calibration-notes.md` has a dedicated "Species mismatch disclaimer" section citing Handeland et al. 2008 and Healey 1991.

8. **Staged tuning convergence**: Task 4.3's A/B/C stages are provably decoupled (cormorant acts on size < 40 cm in 28-day window, seal acts on size ≥ 40 cm year-round), so the two 1-D tuning sub-problems are independent. 6-edit hard stop prevents runaway.

---

## Execution Handoff

**Plan saved to `docs/plans/2026-04-11-v017-phase4-calibration.md`.**

Two execution options:

1. **Inline execution** — continue in this session. Appropriate if Task 4.2's test happens to pass first-shot (defaults already work); then only Tasks 4.5 and 4.6 need real work and the phase completes in one sitting.

2. **Subagent-driven execution** — fresh subagent per task with review checkpoints. Appropriate if Task 4.2 fails, because Task 4.3's iterative tuning may need multiple rounds with user feedback on direction, and keeping each round in its own subagent context prevents context bloat.

**Recommendation**: Start inline. If Task 4.2 fails and Task 4.3 Stage A doesn't converge in 2 edits, escalate to subagent for Task 4.3 only — the rest of the phase stays inline.

---

## Review Cycle Log

### Cycle 1 — Three parallel reviewers (numerical, feature-dev, superpowers)

| Axis | Findings | Disposition |
|---|---|---|
| Scientific (numerical-reviewer) | Species mismatch makes SAR systematically low; 2-18% band can't distinguish 5% from 10%; repeat band 0-15% permits Newfoundland outliers; tuning strategy non-convergent; 3000 cohort marginal for repeat fraction; time-series exhaustion silent | All fixed. SAR band kept at 2–18% but docstring rewritten as collapse detector; repeat band tightened to 0–12%; tuning rewritten as Stage A (cormorant) → Stage B (seal) with `marine_mort_base` untouched (Thorstad 2012 literature backing); 6-edit hard ceiling; species mismatch explained in risk budget |
| Structural (feature-dev:code-reviewer) | Task 4.6 grep pattern missed `<doi1>`/`<doi2>`/`<doi3>`; Task 4.5 had hand-wavy line numbers; runtime estimate possibly optimistic; `end_date_override` absent from fixture | Grep pattern fixed to `<doi[^>]*>` plus `[FILL` alternation; Task 4.5 rewritten with exact 22-line `old_string` matching current `tests/test_marine_survival.py` lines 20–40; `end_date_override="2016-03-31"` added to fixture as defense-in-depth |
| Skill compliance (superpowers:code-reviewer) | Task 4.1 Step 2 bundled cp+edit; Task 4.3 used "example" code; Task 4.4 was a placeholder; Task 4.5 had non-actionable "record/confirm" steps; Task 4.6 template had `(same structure)` repetition; graph missing 4.6 and 4.7; self-review claims inaccurate | Task 4.1 unbundled into 9 steps; Task 4.3 rewritten with concrete old/new_string edits; Task 4.4 folded into Task 4.3 Stage C; Task 4.5 uses Edit-tool-ready blocks from grepped current content; Task 4.6 template uses explicit `[FILL ...]` tokens at every site; graph redrawn with full flow; self-review checklist rewritten |

### Cycle 2 — Single verification reviewer (feature-dev)

| Issue | Severity | Disposition |
|---|---|---|
| Time-series skip guard compared against `m.time_manager._end_date` (which always reflects `end_date_override`, making the guard permanently inert) | HIGH — false safety net | Fixed — guard now reads the actual CSV last row and compares against `start + 5 years`. See cycle 3 for further bugs this fix introduced |
| Execution Handoff still referenced "Task 4.3/4.4" | LOW — stale text | Fixed — rewritten as "Task 4.3" with a concrete escalation trigger (Stage A > 2 edits) |
| All 13 cycle-1 issues | Verified | All showed FIXED in cycle-2 verification table |

### Cycle 3 — Verification reviewer caught self-inflicted bugs in the cycle-2 fix

The cycle-2 CSV-reading guard had two **critical** bugs that would have turned the calibration test into a silent skip-bomb:

| Issue | Severity | Disposition |
|---|---|---|
| Wrong CSV path — guard used `example_a / "Example-Project-A_1Reach-1Species" / "ExampleA-TimeSeriesInputs.csv"` but the file actually lives directly at `example_a / "ExampleA-TimeSeriesInputs.csv"` with no intermediate directory | CRITICAL — `FileNotFoundError` silently caught as `pytest.skip`, test permanently skipped | Fixed — path corrected to `FIXTURES / "example_a" / "ExampleA-TimeSeriesInputs.csv"`. Verified by `ls` on the actual fixture tree |
| Missing `comment=";"` argument to `pd.read_csv` — the CSV begins with two `;`-prefixed comment rows, so without the argument pandas reads the first comment row as the header, making `df.iloc[-1, 0]` garbage that `pd.Timestamp` can't parse → `ValueError` silently caught as `pytest.skip` | CRITICAL — same silent-skip symptom as above | Fixed — `pd.read_csv(ts_csv, comment=";")`. Verified by `head -4` on the CSV showing the two `;` comment rows and the `Date,temperature,flow,turbidity` header on row 3 |
| Runtime estimate was "~20 min" but realistic is ~45 min for a class-scoped 5-year simulation fixture | MODERATE — CI time-budget risk | Fixed — raised to ~45 min with rationale |
| Self-review item 7 still described the old inert guard ("`pytest.skip` if `TimeManager._end_date` is before...") | LOW — stale text | Fixed — item 7 now describes the CSV-reading guard with the `comment=";"` detail |

**Lesson logged**: cycle 2 introduced bugs that cycle 3 caught. The writing-plans skill's "complete code in every step" rule is not enough on its own — when test fixtures read external files, the plan must either (a) have the file paths verified against `ls`/`head` output, or (b) be executed by an agent that runs the fixture against the real repo before committing. For v0.17.0 we accept the latter: Task 4.2 Step 2 actually runs the test, so a path/parse bug would surface as a skip on the first run and be flagged before commit. The plan is now safe to execute because the executor will catch any remaining guard bug at Task 4.2 Step 2, not silently mask it.

Awaiting go/redirect.
