# Arcs B + C Implementation Plan

**Date:** 2026-04-19
**Context:** v0.30.2 was just shipped (spawning pipeline fixed, 220-day
bench shows 853 redds + 317k eggs, natal FRY emerge at day ~380).
Two follow-up validation arcs to prove the full lifecycle + reference
parity.

---

## Arc B — 730-day natal cohort validation

**Goal:** Demonstrate that the v0.30.2 Baltic case study produces a
complete 2-year lifecycle: initial population → first spawn → natal FRY
emerge → natal FRY mature → second spawn cycle.

**Why:** v0.25.0 claimed "self-sustaining Baltic population" as a major
release milestone. v0.30.1 refactored geometry (9 reaches, real coast).
v0.30.2 fixed the spawning bug that silently broke reproduction. Need a
single end-to-end run that proves the self-sustaining property still
holds after all that change.

**Expected milestones** (extrapolating from the 400-day bench):

| Day | Month (sim) | Expected stage |
|-----|------|----------|
| 198 | Oct yr1 | First SPAWNER, REDD, EGGS appear |
| 270 | Dec yr1 | Peak redds (~900), eggs (~50k) |
| 380 | Apr yr2 | First natal FRY emerge from hatched redds |
| 413 | May yr2 | Second wave of RETURNING_ADULT (year 2 adult run) |
| 563 | Oct yr2 | Second spawn cycle opens; mixed natal+initial cohort |
| 600 | Nov yr2 | Natal FRY (from yr1) mature to PARR |
| 730 | Mar yr3 | Year-2 eggs overwintering; year-1 natal cohort at PARR or SMOLT |

**Steps:**

1. Run `bench_baltic.py 730` with JSON output at
   `benchmarks/baselines/v0.30.2-baltic-730day.json`. Runtime ~20 min at
   the measured 36 days/min throughput.
2. Read the JSON + diff against the 220-day baseline using
   `compare_baseline.py` to see how the stage histogram evolves.
3. Commit the new baseline file so future releases can compare against
   the 2-year reference.
4. Add an entry to the v0.30.2 status memory recording the observed
   natal cohort dynamics.

**Success criteria:**

- Natal FRY appear between day 365 and day 400
- Year-2 adult arrivals start around day 413 (or earlier if adult
  arrivals CSV supplies them continuously)
- Second cohort of SPAWNERS appears around day 563
- Day-730 histogram contains at least one of: natal PARR cohort, second
  REDD wave, year-2 EGGS

**Failure modes and fallbacks:**

- If natal FRY don't emerge by day 400 → redd dewatering / scour killed
  all eggs. Check redd_state.eggs_scour / eggs_dewatering counters
  before concluding the fix is broken.
- If the 730-day run OOMs or takes >45 min → cap at the furthest
  milestone that completed; document the limit.

---

## Arc C — NetLogo cross-validation

**Goal:** Quantitatively compare v0.30.2 Python outputs against the
NetLogo inSALMO 7.3 reference for a shared test fixture
(example_a is the only overlapping fixture; Baltic is Python-only).

**Why:** The memory notes this as pending since v0.19.0. NetLogo is
the "source of truth" for salmonid IBM behaviour; if the Python port
has drifted from it on calibrated test runs, we need to know.

**Constraints:**

- NetLogo 6.4.0 installed per memory; inSALMO 7.3 model available
- Baltic case study does NOT exist in NetLogo — Python-only
- Shared fixture must be `example_a` or `example_b`
- Can only validate behaviours present in both (excludes marine +
  iteroparity — NetLogo ends at adult return, doesn't model KELT)

**Steps:**

1. Dispatch `validation-checker` agent to identify:
   - Which fixture (example_a vs example_b) has NetLogo parity
   - Which Python tests already run that fixture in a comparable config
   - Which metrics to compare (alive count, length means, spawning
     counts, mortality rates) at matched DOY snapshots
   - Known gaps from prior validation efforts
2. Based on agent findings, pick one fixture + one run length + 3–5
   comparison metrics
3. If NetLogo outputs already cached (look for `*.nlogo` run artefacts
   in tests/fixtures/): read and compare
4. If not cached: document what would be needed, but don't block the
   arc on a NetLogo run (can be a follow-up)
5. Produce a validation report at
   `docs/validation/v0.30.2-netlogo-comparison.md` listing the compared
   metrics + any drift observed + pass/fail verdict

**Success criteria:**

- Report committed at `docs/validation/v0.30.2-netlogo-comparison.md`
- Each compared metric has a drift bound and verdict (pass/fail)
- Open gaps are listed as follow-up items (not glossed over)

---

## Execution order

1. Kick off Arc B's 730-day bench in background immediately (longest
   tail; everything else fits inside its runtime)
2. While B runs: dispatch the validation-checker agent for Arc C
3. While B still runs + C is waiting on agent: review Arc C agent
   output, decide scope
4. When B finishes: analyze, commit baseline, update memory
5. When C agent finishes: produce report, commit

## Stopping criteria per-arc

- **Arc B**: baseline JSON committed + memory updated
- **Arc C**: validation report committed + follow-up items listed in
  memory if NetLogo runs aren't already cached
