# Arc K–Q WGBAST-Driven Improvements Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Scope note**: This roadmap covers 7 independent subsystems. Each Arc produces working, mergeable software on its own — stop after any Arc if priorities change. Arc K is specified in full TDD detail; Arcs L–Q have enough detail to execute but **should be re-expanded into standalone plans** when their turn comes (just rerun `superpowers:writing-plans` scoped to that Arc). Run each Arc in a dedicated git worktree / branch.

**Goal:** Make SalmoPy directly comparable to ICES WGBAST (Working Group on Baltic Salmon and Sea Trout) outputs by adding the 7 capabilities identified in the 2026-04-20 WGBAST survey.

**Architecture:** Each Arc is a self-contained feature slice touching ≤4 modules. Arcs K, L, N are small (1–2 days); M, O, Q are medium (3–5 days); P is the largest (full Bayesian wrapper, 1–2 weeks). Dependency order is K → (L, M, N in any order) → O → P → Q.

**Tech Stack:** Python 3.11, numpy/pandas, pytest, pydantic YAML configs, existing `src/instream/calibration/` framework, ICES MCP tools (`ices-mcp/ices_clients/`).

**WGBAST reference docs** (pulled 2026-04-20 via ICES MCP):
- WGBAST 2026 report: https://doi.org/10.17895/ices.pub.29118545.v3
- sal.27.22-31 + sal.27.32 stock annex 2025: https://doi.org/10.17895/ices.pub.25869088.v2
- IBPSalmon 2013: https://doi.org/10.17895/ices.pub.19281089
- SAG assessmentKey 13726 (sal.27.22-31), 19019 (sal.27.32)

---

## Arc Dependency Graph

```
Arc 0  (WGBAST PDF data assembly)  ← NEW, blocks L/M/N (see review 2026-04-20)
   ↓
Arc K  (per-reach smolt output)    ← foundation, unblocks everything else
   ↓
   ├── Arc L (M74 year-effect, egg-stage)  — needs Arc 0 data + Arc K
   ├── Arc M (multi-river fixtures)        — needs Arc 0 PSPC + Arc K
   └── Arc N (post-smolt survival forcing) — needs Arc 0 WGBAST Bayesian output
              ↓
              └── Arc O (straying/homing + genetic MSA matrix)
                         ↓
                         └── Arc Q (Bayesian life-cycle wrapper) — needs K,L,M,N,O

Arc P (grey-seal predation) — orthogonal, can run anytime after K.
  Data source: HELCOM Grey Seal Abundance indicator (freely downloadable,
  no registration: https://indicators.helcom.fi/indicator/grey-seal-abundance/)
```

**Recommended merge order**: 0 → K → L → M → N → O → P → Q.

## Review-driven corrections (2026-04-20)

This plan was revised after 4 parallel review passes (code, numerical,
NetLogo-alignment, literature). Key corrections applied inline:

1. **Arc 0 prepended** — WGBAST 2026 per-river PSPC + post-smolt survival
   series + Vuorinen M74 series live inside a 12-MB PDF; they must be
   extracted before Arcs L/M/N can begin.
2. **Arc K CSV schema widened** from 4 to 9 columns to match NetLogo
   InSALMO 7.3 `Outmigrants-<run>.csv` (adds `timestep, age,
   length_category, initial_length, superind_rep`). This makes Arc M's
   `age_years_at_smolt` free and keeps parity-downstream joins trivial.
3. **Arc K file paths corrected** — outmigrant build sites are in
   `src/instream/modules/migration.py:94, 112, 134`, NOT in
   `marine/domain.py:381` (that is the adult-return reach-reassignment
   site, which doesn't append to `_outmigrants`).
4. **Arc K integration tests use `InSTREAMModel` directly** —
   `instream.cli` exposes only an argparse `main()`, there is no public
   `run_simulation(config_path, output_dir, override=...)` function and
   no dot-notation override mechanism. All integration tests in the plan
   now instantiate the model directly.
5. **Arc L life-stage corrected** — WGBAST M74 is a yolk-sac-fry
   mortality (freshwater, pre-swim-up), NOT a marine post-smolt hazard.
   Wiring into `m74_hazard()` in `marine/survival.py` would apply an
   annual fraction as a daily hazard and compound to ~100% kill
   (0.5^365 ≈ 10⁻¹¹⁰ survival). Arc L now targets egg/emergence in
   `src/instream/modules/spawning.py` (redd → fry transition).
6. **Arc L citation fixed** — canonical source is Vuorinen et al. 2021
   (DOI 10.1080/10236244.2021.1941942), which publishes the Simojoki +
   Tornionjoki + Kemijoki annual YSFM series 1985/86–2019/20. Extend to
   2024 from WGBAST 2026 §3. (The earlier "Koski 2002; Mikkonen 2021"
   attribution was wrong — Koski 1999 is a thiamine-treatment study,
   and no Mikkonen 2021 paper exists.)
7. **Arc N data source corrected** — SAG `assessmentKey=13726` returns
   spawners + catches only. The post-smolt survival latent series lives
   in the WGBAST 2026 Bayesian-model PDF output (Figure / Table in §2).
   Olmos 2018 covers North Atlantic stocks, NOT Baltic — not usable for
   Arc N Baltic forcing.
8. **Arc O citation fixed** — Palmé 2012 is on brown trout Ne, not
   Baltic salmon straying. Correct citation is Säisä et al. 2005
   (DOI 10.1139/f05-094), which is already cited.
9. **Added -1 natal_reach_idx guard** in Arc K — `write_outmigrants`
   rejects `-1` entries when any reach has `pspc_smolts_per_year` set,
   to surface partial wiring early.

---

# Arc 0: WGBAST PDF data assembly

**Goal:** Extract three machine-readable CSVs from the WGBAST 2026 report PDF + supporting literature, so Arcs L, M, N have real data to wire into.

**Why added:** The literature/data review (2026-04-20) found that the values Arcs L/M/N depend on live only inside a 12-MB PDF or in papers without open CSVs. Without Arc 0, those Arcs will stall at data-ingest.

**Effort:** S (1 day — mostly PDF table extraction + manual spot-checking).

**Artifacts produced** (all committed to `data/wgbast/`):
- `m74_ysfm_series.csv` — annual yolk-sac-fry mortality, 1985–2024, per river (Vuorinen 2021 extended with WGBAST 2026 §3).
- `pspc_by_river.csv` — per-river PSPC for the ~16 WGBAST assessment rivers (WGBAST 2026 §3 Table).
- `post_smolt_survival_baltic.csv` — Bayesian-model latent post-smolt survival series, sal.27.22-31 + sal.27.32, 1987–2024.

## Tasks

### Task 0.1: Fetch the WGBAST 2026 PDF

- [ ] **Step 0.1.1: Download via the ICES MCP**

Use `get_ices_article(article_id=29118545)` from `ices-mcp/ices_clients/migratory.py` to retrieve the direct PDF URL, then download to `data/wgbast/raw/WGBAST_2026.pdf` (gitignored — tracked via `.gitattributes`).

```bash
micromamba run -n shiny python -c "
from ices_clients.migratory import get_ices_article
art = get_ices_article(article_id=29118545)
print(art['files'][0]['download_url'])" > /tmp/pdf_url.txt
# Then use urllib / curl to fetch the URL into data/wgbast/raw/
```

- [ ] **Step 0.1.2: Commit data/.gitattributes + raw dir scaffold** (NOT the PDF — keep the binary out of git).

### Task 0.2: Extract per-river PSPC table

- [ ] **Step 0.2.1: PDF-extract WGBAST 2026 §3 river table**

Options (pick one):
- `pdfplumber` (already available in `shiny` env? verify with `micromamba run -n shiny python -c "import pdfplumber"`).
- `camelot-py` for table extraction.
- Manual transcription if the table has fewer than 20 rows (it does).

Expected output schema:

```csv
assessment_unit,river,pspc_wild_smolts,pspc_units
1,Tornionjoki,2200000,smolts_per_year
1,Simojoki,95000,smolts_per_year
...
```

- [ ] **Step 0.2.2: Spot-check 3 values against the 2025 stock annex** (DOI 10.17895/ices.pub.25869088.v2). Torne, Simo, Mörrum at minimum. Flag discrepancies >10%.

- [ ] **Step 0.2.3: Commit**

```bash
git add data/wgbast/pspc_by_river.csv
git commit -m "data(Arc 0): WGBAST 2026 §3 per-river PSPC table"
```

### Task 0.3: Extract Vuorinen YSFM series + extend to 2024

- [ ] **Step 0.3.1: Retrieve Vuorinen et al. 2021 supplementary data** via scite or direct DOI (10.1080/10236244.2021.1941942). If supplementary is behind a paywall, transcribe the published figure values (series is short: 3 rivers × ~35 years = ~105 cells).

- [ ] **Step 0.3.2: Extend 2020–2024 from WGBAST 2026 §3 health monitoring table.**

Schema:

```csv
year,river,ysfm_fraction,source
1985,Simojoki,0.02,Vuorinen2021
...
2024,Simojoki,0.08,WGBAST2026
```

- [ ] **Step 0.3.3: Commit**

```bash
git add data/wgbast/m74_ysfm_series.csv
git commit -m "data(Arc 0): Vuorinen2021+WGBAST2026 M74 YSFM series 1985-2024"
```

### Task 0.4: Extract post-smolt survival Bayesian series

- [ ] **Step 0.4.1: Locate WGBAST 2026 post-smolt survival figure/table**

In WGBAST 2026 §2 (Bayesian model outputs), find the post-smolt survival (sometimes labelled "M_post_smolt" or "σ_ps") time series for sal.27.22-31 + sal.27.32. If only a figure, use `WebPlotDigitizer` (web-only; no install) to transcribe ~35 points.

- [ ] **Step 0.4.2: Cross-check with ICES (2023) WGBAST §2.5 3–12% band**

Published median + credible-interval bounds should fall inside 3–12% per the 2023 report.

- [ ] **Step 0.4.3: Commit**

```bash
git add data/wgbast/post_smolt_survival_baltic.csv
git commit -m "data(Arc 0): WGBAST 2026 post-smolt survival series (Bayesian posterior median)"
```

### Task 0.5: Release data snapshot

- [ ] **Step 0.5.1: Write README**

Create `data/wgbast/README.md` listing:
- Source PDF / DOI for each CSV
- Extraction method per file
- Known caveats (e.g. "2020 Simo point is annex median, not posterior mean")
- Refresh cadence (annual, when next WGBAST report lands)

- [ ] **Step 0.5.2: Tag data snapshot**

```bash
git tag data-wgbast-2026-v1
git push origin data-wgbast-2026-v1
```

---

# Arc K: Per-reach smolt production + PSPC output

**Goal:** Emit a `smolt_production_by_reach.csv` artifact per simulation year, plus `pspc_achieved_pct` metric, so a SalmoPy run can be compared directly against WGBAST's % of Potential Smolt Production Capacity by river.

**Why first:** Smallest concrete change (~1 day), unblocks per-river analytics for every subsequent Arc.

## File Structure

**Modify:**
- `src/instream/io/output.py:116-131` — widen `write_outmigrants` schema from 3 to
  9 columns to match NetLogo InSALMO 7.3 (review 2026-04-20 §3).
- `src/instream/modules/migration.py:94, 112, 134` — the three `outmigrants.append(...)`
  call sites must all carry the new fields (NOT `marine/domain.py:381` as the
  first draft claimed — that site is adult-return reach reassignment).
- `src/instream/io/config.py` — add `reach.pspc_smolts_per_year: float | None` field
  (found via `grep -n "class ReachConfig\|reach_segments\|class ReachSegment" src/instream/io/config.py`).
- `configs/example_baltic.yaml` — add PSPC values per reach (placeholder until
  Arc 0's `data/wgbast/pspc_by_river.csv` lands).

**Create:**
- `src/instream/io/output.py` — new `write_smolt_production_by_reach()` function.
- `tests/test_pspc_output.py` — unit + integration tests.
- `docs/validation/v0.34.0-pspc-spec.md` — document the schema + WGBAST mapping.

**NetLogo target schema** (InSALMO 7.3 `Outmigrants-<run>.csv`):
```
BehavSp-Run, End of time step, Species, Natal reach, Age, Length category,
Length, InitialLength, SuperindRep
```

SalmoPy will emit 10 columns — the same 9 NetLogo logical fields (casing
normalised to snake_case), with `Natal reach` split into both
`natal_reach_idx` (int) and `natal_reach_name` (str) for join convenience.

## Tasks

### Task K.1: Widen outmigrant record to NetLogo-compat 9-column schema

**Files:**
- Modify: `src/instream/io/output.py:116-131`
- Modify: `src/instream/modules/migration.py` — all three `outmigrants.append(...)`
  sites (lines ~94, ~112, ~134 per review). Re-grep to confirm exact line numbers.
- Test: `tests/test_pspc_output.py`

- [ ] **Step K.1.1: Find every outmigrant-record construction site**

Run: `micromamba run -n shiny python -c "import pathlib; print(list(pathlib.Path('src/instream').rglob('*.py')))"`
then: `grep -rn "outmigrants.append\|_outmigrants.extend" src/instream/`

Expected: 3 sites in `src/instream/modules/migration.py`, plus a `.extend()` call
in `src/instream/model_day_boundary.py`. Note the exact line numbers — the review
found them at `modules/migration.py:94,112,134` as of master `3ec1858`.

- [ ] **Step K.1.2: Write failing test for widened schema**

```python
# tests/test_pspc_output.py
from pathlib import Path
from instream.io.output import write_outmigrants


def test_outmigrants_csv_9col_netlogo_compat(tmp_path: Path):
    outmigrants = [
        {
            "species_idx": 0,
            "timestep": 180,
            "natal_reach_idx": 2,
            "natal_reach_name": "Nemunas_main",
            "age_years": 1.5,
            "length_category": "Juvenile",
            "length": 12.3,
            "initial_length": 2.5,
            "superind_rep": 100,
            "reach_idx": 0,
        },
    ]
    path = write_outmigrants(outmigrants, ["Salmon"], tmp_path)
    rows = path.read_text().splitlines()
    assert rows[0] == (
        "species,timestep,reach_idx,natal_reach_idx,natal_reach_name,"
        "age_years,length_category,length_cm,initial_length_cm,superind_rep"
    )
    assert rows[1].startswith("Salmon,180,0,2,Nemunas_main,")
    assert rows[1].endswith(",100")
```

- [ ] **Step K.1.3: Run test to confirm it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_pspc_output.py::test_outmigrants_csv_9col_netlogo_compat -v`
Expected: FAIL (header mismatch — current header has only 3 columns).

- [ ] **Step K.1.4: Widen write_outmigrants to 10-column NetLogo-compat schema**

Edit `src/instream/io/output.py:116-131`:

```python
def write_outmigrants(
    outmigrants,
    species_order,
    output_dir,
    filename="outmigrants.csv",
    reach_names=None,
    require_natal_reach=False,
):
    """Write accumulated outmigrant records (NetLogo InSALMO 7.3 compatible).

    Schema mirrors NetLogo 7.3 `Outmigrants-<run>.csv`:
      species, timestep, reach_idx (exit), natal_reach_idx, natal_reach_name,
      age_years, length_category, length_cm, initial_length_cm, superind_rep

    When `require_natal_reach=True`, raise ValueError on any record with
    natal_reach_idx == -1 — used by callers that have configured PSPC
    (Arc K.4) to surface partial wiring early.
    """
    path = Path(output_dir) / filename
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "species", "timestep", "reach_idx", "natal_reach_idx",
            "natal_reach_name", "age_years", "length_category",
            "length_cm", "initial_length_cm", "superind_rep",
        ])
        for om in outmigrants:
            sp = (
                species_order[om["species_idx"]]
                if om["species_idx"] < len(species_order)
                else "Unknown"
            )
            natal_idx = int(om.get("natal_reach_idx", -1))
            if require_natal_reach and natal_idx < 0:
                raise ValueError(
                    f"outmigrant record missing natal_reach_idx: {om}"
                )
            natal_name = om.get("natal_reach_name") or (
                reach_names[natal_idx]
                if reach_names is not None and 0 <= natal_idx < len(reach_names)
                else ""
            )
            writer.writerow([
                sp,
                int(om.get("timestep", -1)),
                int(om.get("reach_idx", -1)),
                natal_idx,
                natal_name,
                round(float(om.get("age_years", 0.0)), 4),
                om.get("length_category", ""),
                round(float(om.get("length", 0.0)), 4),
                round(float(om.get("initial_length", 0.0)), 4),
                int(om.get("superind_rep", 1)),
            ])
    return path
```

- [ ] **Step K.1.5a: Pre-flight — verify state/model attribute names**

Final-review (2026-04-20) found the real attribute names differ from the
first draft. Confirm each via grep before writing code:

```bash
grep -n "^ *age\|^ *initial_length\|^ *superind_rep\|^ *length\b" src/instream/state/trout_state.py
grep -n "current_step\|current_date\|time_manager" src/instream/model.py
grep -n "class ReachParams\|name:.*str" src/instream/io/config.py
```

Confirmed (master `3ec1858`):
- `TroutState.age` exists (int32 days), but `TroutState.initial_length`
  does NOT exist.
- `InSTREAMModel.current_step` does NOT exist; use
  `model.time_manager.current_date` + `start_date` for a day-offset.
- `ReachParams` (frozen dataclass) carries `name: str`; `ReachConfig`
  (pydantic, `extra="allow"`) does not. `config.reach_segments` contains
  `ReachParams`, so `.name` access is fine AT THE MIGRATION SITE.

- [ ] **Step K.1.5b: Add `initial_length` field to TroutState**

Edit `src/instream/state/trout_state.py` — add to the dataclass:

```python
initial_length: np.ndarray  # float32, length at creation (for NetLogo parity)
```

And in `TroutState.zeros(capacity)`:

```python
initial_length=np.zeros(capacity, dtype=np.float32),
```

At fish-creation sites (grep `trout_state.length\[.*\] =` and `spawn` /
emergence modules), add a matching write:

```python
trout_state.initial_length[idx] = trout_state.length[idx]
```

Run: `micromamba run -n shiny python -m pytest tests/ -q` to confirm nothing
breaks from the field addition.

Commit this as its own step before K.1.5c:

```bash
git add src/instream/state/trout_state.py src/instream/modules/spawning.py  # or wherever fry are created
git commit -m "feat(state): add TroutState.initial_length (NetLogo parity)"
```

- [ ] **Step K.1.5c (pre-step): Expose `start_date` on TimeManager**

Third-review (2026-04-20) found `TimeManager` stores `self._start_date`
(private) but exposes no public `start_date` property. The K.1.5d snippet
below needs it. Add the property first.

Edit `src/instream/io/time_manager.py` — near the existing properties:

```python
@property
def start_date(self):
    """Simulation start date (pd.Timestamp)."""
    return self._start_date
```

Commit:
```bash
git add src/instream/io/time_manager.py
git commit -m "feat(time_manager): expose public start_date property"
```

- [ ] **Step K.1.5d: Extend every outmigrant-record build site to carry the new fields**

For each of the 3 sites in `src/instream/modules/migration.py` (and the
`.extend` site in `model_day_boundary.py`), change the dict built per record
from the current minimal shape to:

```python
# Current site (pattern, verify with grep):
#   outmigrants.append({
#       "species_idx": sp, "length": L, "reach_idx": r, "superind_rep": sr
#   })
# New — all fields sourced from existing state:
timestep_int = (
    model.time_manager.current_date - model.time_manager.start_date
).days
natal_idx = int(trout_state.natal_reach_idx[i])
# config.reaches is Dict[str, ReachConfig]; look up the name by
# index via the reach-order list maintained by the model.
reach_names_list = list(config.reaches.keys())
natal_name = (
    reach_names_list[natal_idx]
    if 0 <= natal_idx < len(reach_names_list)
    else ""
)
outmigrants.append({
    "species_idx": sp,
    "timestep": int(timestep_int),
    "reach_idx": int(r),
    "natal_reach_idx": natal_idx,
    "natal_reach_name": natal_name,
    "age_years": float(trout_state.age[i]) / 365.25,
    "length_category": (
        "Juvenile" if trout_state.length[i] < 12.0 else "Smolt"
    ),
    "length": float(trout_state.length[i]),
    "initial_length": float(trout_state.initial_length[i]),
    "superind_rep": int(trout_state.superind_rep[i]),
})
```

- [ ] **Step K.1.6: Run test to verify pass**

Run: `micromamba run -n shiny python -m pytest tests/test_pspc_output.py::test_outmigrants_csv_includes_natal_reach -v`
Expected: PASS.

- [ ] **Step K.1.7: Run the full test suite to confirm no regression**

Run: `micromamba run -n shiny python -m pytest tests/ -q --tb=short -x`
Expected: all tests pass. If any existing test asserted on the 3-column outmigrant CSV, update that test to include the new column.

- [ ] **Step K.1.8: Commit**

```bash
git add src/instream/io/output.py src/instream/marine/domain.py tests/test_pspc_output.py
git commit -m "feat(output): outmigrants.csv carries natal_reach_idx for PSPC analytics"
```

### Task K.2: Add PSPC YAML field per reach

**Files:**
- Modify: `src/instream/io/config.py` (ReachConfig pydantic model)
- Modify: `configs/example_baltic.yaml`
- Test: `tests/test_pspc_output.py`

- [ ] **Step K.2.1: Locate the ReachConfig pydantic class**

Run: `grep -n "class ReachConfig\|reach_segments\|class ReachSegment" src/instream/io/config.py`
Note the line number for the reach model and its existing fields (e.g., `length`, `width`, `frac_spawn`).

- [ ] **Step K.2.2: Write failing test for pspc_smolts_per_year YAML loading**

Note (final review 2026-04-20): the live schema is
`ModelConfig.reaches: Dict[str, ReachConfig]` (dict keyed by reach name),
not a list named `reach_segments`. Top-level YAML key is `simulation:`,
not `run:`.

Append to `tests/test_pspc_output.py`:

```python
from instream.io.config import load_config


def test_reach_config_accepts_pspc(tmp_path: Path):
    yaml_text = """
simulation:
  start_date: "2011-01-01"
  end_date:   "2011-12-31"
species:
  Salmon:
    is_anadromous: true
reaches:
  Nemunas:
    length_m: 10000
    width_m: 50
    pspc_smolts_per_year: 12000
"""
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(yaml_text)
    cfg = load_config(cfg_path)
    assert cfg.reaches["Nemunas"].pspc_smolts_per_year == 12000
```

- [ ] **Step K.2.3: Run test to confirm it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_pspc_output.py::test_reach_config_accepts_pspc -v`
Expected: FAIL with `extra_forbidden` pydantic error on the unknown field.

- [ ] **Step K.2.4: Add pspc_smolts_per_year to ReachConfig**

In the ReachConfig pydantic class (found in Step K.2.1), add the field:

```python
pspc_smolts_per_year: float | None = None
# WGBAST Potential Smolt Production Capacity for this reach/river.
# None = not an assessment reach (skip from PSPC report).
# Source: WGBAST Section 3 river-specific PSPC table, or literature
# (e.g. Torne PSPC ≈ 2,200k smolts/yr; Simo ≈ 95k; Mörrum ≈ 50k).
```

- [ ] **Step K.2.5: Run test to verify pass**

Run: `micromamba run -n shiny python -m pytest tests/test_pspc_output.py::test_reach_config_accepts_pspc -v`
Expected: PASS.

- [ ] **Step K.2.6: Add PSPC values to example_baltic.yaml**

For each reach in `configs/example_baltic.yaml` (top-level key `reaches:`,
keyed by reach name), add `pspc_smolts_per_year:` with a Nemunas-basin estimate
(e.g., 5000 for the main stem, proportional splits for tributaries). Values
are placeholders — engineer cites them as preliminary pending a Nemunas-specific
literature review and notes this in a YAML comment.

```yaml
reaches:
  Nemunas_main:
    length_m: 8000
    width_m: 80
    pspc_smolts_per_year: 5000
      # Preliminary PSPC estimate — pending Kesminas et al. Nemunas
      # smolt-production literature review. WGBAST-comparable reaches
      # (Torne, Simo) use river-specific production surveys; the
      # Nemunas value is order-of-magnitude only.
```

- [ ] **Step K.2.7: Commit**

```bash
git add src/instream/io/config.py configs/example_baltic.yaml tests/test_pspc_output.py
git commit -m "feat(config): add reach.pspc_smolts_per_year for WGBAST comparability"
```

### Task K.3: Write smolt_production_by_reach.csv

**Files:**
- Modify: `src/instream/io/output.py`
- Test: `tests/test_pspc_output.py`

- [ ] **Step K.3.1: Write failing test for the new output function**

```python
# tests/test_pspc_output.py — append
import pandas as pd
from instream.io.output import write_smolt_production_by_reach


def test_smolt_production_by_reach_csv(tmp_path):
    outmigrants = [
        {"species_idx": 0, "length": 12.3, "reach_idx": 0, "natal_reach_idx": 0},
        {"species_idx": 0, "length": 11.1, "reach_idx": 0, "natal_reach_idx": 0},
        {"species_idx": 0, "length": 13.0, "reach_idx": 0, "natal_reach_idx": 2},
    ]
    reach_names = ["Nemunas_main", "Neris", "Zeimena"]
    reach_pspc = [5000.0, 2000.0, 1000.0]
    path = write_smolt_production_by_reach(
        outmigrants, reach_names, reach_pspc, year=2011, output_dir=tmp_path
    )
    df = pd.read_csv(path)
    assert set(df.columns) == {
        "year", "reach_idx", "reach_name",
        "smolts_produced", "pspc_smolts_per_year", "pspc_achieved_pct",
    }
    # Reach 0 produced 2 smolts, PSPC 5000 -> 0.04 %
    row0 = df[df["reach_idx"] == 0].iloc[0]
    assert row0["smolts_produced"] == 2
    assert abs(row0["pspc_achieved_pct"] - (2 / 5000 * 100)) < 1e-6
    # Reach 1 produced 0 smolts -> 0 %
    row1 = df[df["reach_idx"] == 1].iloc[0]
    assert row1["smolts_produced"] == 0
    assert row1["pspc_achieved_pct"] == 0.0
```

- [ ] **Step K.3.2: Run test to confirm it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_pspc_output.py::test_smolt_production_by_reach_csv -v`
Expected: FAIL with `ImportError` / `AttributeError`.

- [ ] **Step K.3.3: Implement write_smolt_production_by_reach**

Add to `src/instream/io/output.py`:

```python
def write_smolt_production_by_reach(
    outmigrants,
    reach_names,
    reach_pspc,
    year,
    output_dir,
    filename=None,
):
    """Write per-reach smolt production + PSPC achievement.

    WGBAST-comparable output: each row is one (year, reach) pair with
    the count of smolts produced whose natal_reach_idx == that reach,
    alongside the reach's configured PSPC and the resulting
    pspc_achieved_pct.

    Parameters
    ----------
    outmigrants : list of dicts
        Each record must include "natal_reach_idx".
    reach_names : sequence[str]
        reach_names[i] = human-readable label for reach i.
    reach_pspc : sequence[float | None]
        reach_pspc[i] = configured PSPC; None/NaN is emitted as NaN.
    year : int
    output_dir : path-like
    filename : str, optional
        Default "smolt_production_by_reach_{year}.csv".

    Returns
    -------
    Path to the CSV.
    """
    if filename is None:
        filename = f"smolt_production_by_reach_{year}.csv"
    path = Path(output_dir) / filename

    counts = [0] * len(reach_names)
    for om in outmigrants:
        r = om.get("natal_reach_idx", -1)
        if 0 <= r < len(counts):
            counts[r] += 1

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "year", "reach_idx", "reach_name",
            "smolts_produced", "pspc_smolts_per_year", "pspc_achieved_pct",
        ])
        for i, name in enumerate(reach_names):
            pspc = reach_pspc[i]
            if pspc is None or pspc <= 0:
                pct = ""
                pspc_val = ""
            else:
                pct = round(counts[i] / float(pspc) * 100.0, 4)
                pspc_val = round(float(pspc), 2)
            writer.writerow([year, i, name, counts[i], pspc_val, pct])
    return path
```

- [ ] **Step K.3.4: Run test to verify pass**

Run: `micromamba run -n shiny python -m pytest tests/test_pspc_output.py::test_smolt_production_by_reach_csv -v`
Expected: PASS.

- [ ] **Step K.3.5: Commit**

```bash
git add src/instream/io/output.py tests/test_pspc_output.py
git commit -m "feat(output): write_smolt_production_by_reach emits WGBAST-style PSPC table"
```

### Task K.4: Wire write_smolt_production_by_reach into the model end-of-year hook

**Files:**
- Modify: `src/instream/model.py` (or wherever end-of-year writes live — find via grep)
- Test: `tests/test_pspc_output.py` (integration)

- [ ] **Step K.4.1: Find existing end-of-year / end-of-run write calls**

Run: `grep -rn "write_outmigrants\|end_of_year\|end_of_run" src/instream/`
Pick the hook that fires once per simulation year (or at end-of-run if no per-year hook — fine for Arc K, year-slicing can happen in analysis).

- [ ] **Step K.4.2: Write failing integration test**

Note (final review 2026-04-20): `InSTREAMModel.__init__` signature confirmed as
`(config_path, data_dir=None, end_date_override=None, output_dir=None)` — it
takes a **path string**, not a pydantic config. Outputs are written by `run()`
via an internal `write_outputs()` call; there is no separate `finalise()`
method. The test must write a modified YAML to a temp path and pass that path.

```python
# tests/test_pspc_output.py — append
import pandas as pd
import yaml
from instream.model import InSTREAMModel


def test_end_to_end_pspc_on_tiny_baltic(tmp_path):
    """Run example_baltic at reduced scale and confirm the PSPC CSV appears."""
    # Read the example YAML, patch run dates + seed, write back to tmp_path
    with open("configs/example_baltic.yaml") as f:
        cfg_dict = yaml.safe_load(f)
    cfg_dict["run"]["end_date"] = "2011-06-30"
    cfg_dict["run"]["seed"] = 42
    cfg_path = tmp_path / "example_baltic_short.yaml"
    with open(cfg_path, "w") as f:
        yaml.safe_dump(cfg_dict, f)

    model = InSTREAMModel(
        config_path=str(cfg_path),
        output_dir=str(tmp_path),
    )
    model.run()  # run() calls write_outputs() internally

    pspc_files = list(tmp_path.glob("smolt_production_by_reach_*.csv"))
    assert len(pspc_files) >= 1
    df = pd.read_csv(pspc_files[0])
    assert {"reach_idx", "smolts_produced", "pspc_achieved_pct"}.issubset(df.columns)
```

- [ ] **Step K.4.3: Run test to confirm it fails**

Run: `micromamba run -n shiny python -m pytest tests/test_pspc_output.py::test_end_to_end_pspc_on_tiny_baltic -v`
Expected: FAIL (no CSV emitted).

- [ ] **Step K.4.4: Wire the call into the end-of-year / end-of-run hook**

At the hook site found in Step K.4.1, after the existing `write_outmigrants(...)`
call, add the PSPC write. Also activate the guard flag on `write_outmigrants`
when any reach has a configured PSPC, so partial wiring (natal_reach_idx=-1)
surfaces immediately rather than silently.

```python
from instream.io.output import write_smolt_production_by_reach

# config.reaches is Dict[str, ReachConfig] — use dict-order for reach_idx
reach_names = list(config.reaches.keys())
reach_pspc = [config.reaches[n].pspc_smolts_per_year for n in reach_names]
has_pspc = any(p for p in reach_pspc)

# Pass the new guard when PSPC is configured
write_outmigrants(
    model._outmigrants,
    species_order,
    output_dir,
    reach_names=reach_names,
    require_natal_reach=has_pspc,
)

write_smolt_production_by_reach(
    model._outmigrants,
    reach_names,
    reach_pspc,
    year=model.time_manager.current_date.year,
    output_dir=output_dir,
)
```

- [ ] **Step K.4.5: Run test to verify pass**

Run: `micromamba run -n shiny python -m pytest tests/test_pspc_output.py -v`
Expected: all 4 tests PASS.

- [ ] **Step K.4.6: Run full suite**

Run: `micromamba run -n shiny python -m pytest tests/ -q --tb=short`
Expected: all PASS (no regressions).

- [ ] **Step K.4.7: Commit**

```bash
git add src/instream/model.py tests/test_pspc_output.py
git commit -m "feat(model): emit smolt_production_by_reach_{year}.csv at end-of-run"
```

### Task K.5: Documentation + CHANGELOG

**Files:**
- Create: `docs/validation/v0.34.0-pspc-spec.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/user-manual.md` (add a section on PSPC output)

- [ ] **Step K.5.1: Write v0.34.0 PSPC spec doc**

Create `docs/validation/v0.34.0-pspc-spec.md` with sections:
1. Purpose (WGBAST comparability)
2. CSV schema (exact columns + units)
3. How to derive PSPC values for a custom reach (Torne/Simo/Mörrum examples from WGBAST 2026 Section 3)
4. Caveats (super-individual rep-weight handling when `rep_weight != 1`)

- [ ] **Step K.5.2: Update CHANGELOG.md**

Add under a new `## [0.34.0] - YYYY-MM-DD` heading:

```markdown
### Added
- **Per-reach smolt production output (Arc K)**: end-of-run writes
  `smolt_production_by_reach_{year}.csv` with columns `reach_idx`,
  `reach_name`, `smolts_produced`, `pspc_smolts_per_year`,
  `pspc_achieved_pct`. Makes SalmoPy output directly comparable to
  WGBAST's % of Potential Smolt Production Capacity (WGBAST 2026 §3).
- **`ReachConfig.pspc_smolts_per_year`** YAML field (optional).
- **`outmigrants.csv` `natal_reach_idx` column**: exposes the birth
  reach of each outmigrant for downstream analytics.
```

- [ ] **Step K.5.3: Commit**

```bash
git add docs/validation/v0.34.0-pspc-spec.md CHANGELOG.md docs/user-manual.md
git commit -m "docs(Arc K): v0.34.0 PSPC spec + changelog"
```

### Task K.6: Tag & release v0.34.0

- [ ] **Step K.6.1: Bump version**

Edit `pyproject.toml` and `src/instream/__init__.py` to version `0.34.0`.

- [ ] **Step K.6.2: Run full test suite one more time**

Run: `micromamba run -n shiny python -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step K.6.3: Commit version bump + tag**

```bash
git add pyproject.toml src/instream/__init__.py
git commit -m "chore: bump version to 0.34.0 (Arc K)"
git tag v0.34.0
git push origin master v0.34.0
```

---

# Arc L: Stochastic M74 year-effect (egg/emergence stage)

**Goal:** Apply a year-indexed WGBAST M74 yolk-sac-fry mortality fraction as a
one-time binomial cull at egg→fry emergence, replacing the current constant
marine-stage `marine_mort_m74_prob`.

**Why:** WGBAST 2026 §3 (Vuorinen et al. 2021 extended) supplies an annual
YSFM fraction for Simojoki, Tornionjoki, Kemijoki 1985/86–2024. This is a
**freshwater yolk-sac stage** mortality (pre-swim-up), NOT a marine-adult
hazard. The current `m74_hazard()` in `src/instream/marine/survival.py:100-102`
is applied per-day in the marine survival product — wiring an annual fraction
there would compound to effectively 100% marine kill.

**Critical correction (review 2026-04-20 numerical pass):** the M74 wiring
must be moved from `marine/survival.py` to the egg-emergence hook. The
existing `marine_mort_m74_prob` field is kept at 0.0 (backward-compatible)
and deprecated.

**Effort:** M (2–3 days — includes the life-stage move + caller audit).

## File Structure

**Uses (from Arc 0):**
- `data/wgbast/m74_ysfm_series.csv` — year, river, ysfm_fraction, source

**Create:**
- `src/instream/io/m74_forcing.py` — loader + per-year + per-river lookup.
- `src/instream/modules/egg_emergence_m74.py` — the cull function called
  at redd → fry transition.
- `tests/test_m74_forcing.py` — loader + kernel tests.
- `tests/test_egg_emergence_m74.py` — life-stage integration tests.

**Modify:**
- `src/instream/io/config.py` — add `m74_forcing_csv: Optional[str] = None`
  to `SimulationConfig` (NOT marine config — it's a freshwater hazard).
  Concrete edit step: **L.2.0** below.
- `src/instream/modules/spawning.py` — call the egg-emergence cull at the
  egg→fry transition. Find the right hook via
  `grep -n "def.*emerge\|eggs_to_fry\|egg_emergence\|create_fry" src/instream/modules/spawning.py`.
- `configs/baltic_salmon_species.yaml` — `m74_forcing_csv: data/wgbast/m74_ysfm_series.csv`.
- `src/instream/marine/config.py:134-135` — mark `marine_mort_m74_prob` as
  deprecated (keep scalar for backward compat but default 0.0 and add a
  YAML comment pointing to Arc L).

## Tasks

### Task L.1: Ship the M74 CSV

Deferred to **Arc 0.3** — the canonical Vuorinen 2021 + WGBAST 2026 YSFM
series lives at `data/wgbast/m74_ysfm_series.csv` after Arc 0 completes.
Arc L assumes that CSV exists and is committed before starting.

- [ ] **Step L.1.1: Verify Arc 0.3 CSV exists**

Run: `ls -la data/wgbast/m74_ysfm_series.csv`
Expected: file present, ~40 rows × 3 rivers.

- [ ] **Step L.1.2: Spot-check contents**

Run: `head data/wgbast/m74_ysfm_series.csv`
Expected schema: `year, river, ysfm_fraction, source`.

### Task L.2: Loader module (TDD)

- [ ] **Step L.2.0 (mandatory pre-step): Add `m74_forcing_csv` to SimulationConfig**

Fourth-review found no concrete edit step existed for this field. Add now so
`config.simulation.m74_forcing_csv` is a real attribute before L.3.6 tries
to read it.

Edit `src/instream/io/config.py` — find `class SimulationConfig(BaseModel)`
at line 26 and add:

```python
m74_forcing_csv: Optional[str] = None
# Path (string or None) to the WGBAST M74 YSFM CSV. When set, the
# egg→fry emergence hook applies per-(year, river) binomial cull.
# See: docs/superpowers/plans/2026-04-20-arc-K-to-Q-wgbast-roadmap.md Arc L.
```

Commit:
```bash
git add src/instream/io/config.py
git commit -m "feat(config): add simulation.m74_forcing_csv for Arc L"
```

- [ ] **Step L.2.1: Write failing test**

```python
# tests/test_m74_forcing.py
from pathlib import Path
from instream.io.m74_forcing import load_m74_forcing, ysfm_for_year_river


def test_load_m74_forcing(tmp_path: Path):
    csv = tmp_path / "m74.csv"
    csv.write_text(
        "year,river,ysfm_fraction,source\n"
        "2010,Simojoki,0.05,Vuorinen2021\n"
        "2011,Simojoki,0.12,Vuorinen2021\n"
        "2011,Tornionjoki,0.08,Vuorinen2021\n"
    )
    s = load_m74_forcing(csv)
    assert s[(2010, "Simojoki")] == 0.05
    assert s[(2011, "Simojoki")] == 0.12
    assert s[(2011, "Tornionjoki")] == 0.08


def test_ysfm_lookup_falls_back_to_river_mean_when_unknown(tmp_path: Path):
    csv = tmp_path / "m74.csv"
    csv.write_text(
        "year,river,ysfm_fraction,source\n"
        "2011,Simojoki,0.10,Vuorinen2021\n"
        "2012,Simojoki,0.20,Vuorinen2021\n"
    )
    s = load_m74_forcing(csv)
    # Exact match
    assert ysfm_for_year_river(s, 2011, "Simojoki") == 0.10
    # Year unknown → 0.0 (no forcing)
    assert ysfm_for_year_river(s, 2099, "Simojoki") == 0.0
    # River unknown → 0.0
    assert ysfm_for_year_river(s, 2011, "UnknownRiver") == 0.0
```

- [ ] **Step L.2.2: Run test → FAIL**

Run: `micromamba run -n shiny python -m pytest tests/test_m74_forcing.py -v`

- [ ] **Step L.2.3: Implement loader**

Create `src/instream/io/m74_forcing.py`:

```python
"""WGBAST M74 (thiamine-deficiency yolk-sac-fry mortality) forcing loader.

Reference: Vuorinen et al. 2021 (DOI 10.1080/10236244.2021.1941942),
Simojoki + Tornionjoki + Kemijoki annual YSFM 1985/86–2019/20, extended
through 2024 from WGBAST 2026 §3 (DOI 10.17895/ices.pub.29118545.v3).

M74 is a freshwater yolk-sac-fry mortality (pre-swim-up). This module's
output feeds into `src/instream/modules/egg_emergence_m74.py`, which
applies the fraction as a one-time binomial cull at egg→fry emergence,
NOT into the marine survival kernel.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Tuple
import pandas as pd


def load_m74_forcing(path: Path | str) -> Dict[Tuple[int, str], float]:
    df = pd.read_csv(path, comment="#")
    required = {"year", "river", "ysfm_fraction"}
    assert required.issubset(df.columns), f"missing columns: {required - set(df.columns)}"
    return {
        (int(r.year), str(r.river)): float(r.ysfm_fraction)
        for r in df.itertuples()
    }


def ysfm_for_year_river(
    series: Dict[Tuple[int, str], float],
    year: int,
    river: str,
) -> float:
    """Return the YSFM fraction, or 0.0 if (year, river) is unknown."""
    return float(series.get((int(year), str(river)), 0.0))
```

- [ ] **Step L.2.4: Run test → PASS; commit**

```bash
git add src/instream/io/m74_forcing.py tests/test_m74_forcing.py
git commit -m "feat(io): Vuorinen/WGBAST M74 YSFM loader (year x river)"
```

### Task L.3: Apply M74 cull at egg→fry emergence

- [ ] **Step L.3.0 (mandatory pre-step): Add `river_name` to ReachConfig AND propagate through `params_from_config`**

Sixth-review found `params_from_config` at `src/instream/io/config.py:591-610`
is a MANUAL field-by-field constructor, NOT `model_dump()`-based. Adding
`river_name` to `ReachConfig` alone silently drops it because
`params_from_config` must be updated in the same edit.

Three coordinated changes in `src/instream/io/config.py`:

```python
# 1) Add to ReachConfig (pydantic class near line 326):
class ReachConfig(BaseModel, extra="allow"):
    # … existing fields …
    river_name: str | None = None
    # WGBAST river key (e.g. "Simojoki", "Tornionjoki"). Used by Arc L to
    # look up the per-(year, river) M74 YSFM fraction. None = non-WGBAST
    # reach (no M74 cull applied).

# 2) Add to ReachParams frozen dataclass:
@dataclass(frozen=True)
class ReachParams:
    name: str
    # … existing fields …
    river_name: str | None = None

# 3) Carry through params_from_config at line ~593:
#    In the ReachParams(...) kwargs list, add:
#        river_name=r.river_name
#    where `r` is the ReachConfig being converted.
```

Commit as its own step:

```bash
git add src/instream/io/config.py
git commit -m "feat(config): add river_name to ReachConfig+Params+conversion (Arc L prereq)"
```

- [ ] **Step L.3.1: Locate the emergence hook**

Run: `grep -n "def.*emerge\|eggs_to_fry\|egg_emergence\|create_fry\|spawn_fry" src/instream/modules/spawning.py src/instream/model_day_boundary.py`
Expected: a function that converts eggs in a redd into fry super-individuals.
Note the exact signature (inputs: redd_state, trout_state, config, current_date
or similar; output: number of fry created).

If no emergence hook exists in `spawning.py`, check `model_day_boundary.py`
and `modules/recruitment.py`. The M74 cull belongs wherever eggs_developed
→ fry super-individuals happens.

- [ ] **Step L.3.2: Write failing end-to-end emergence test**

```python
# tests/test_egg_emergence_m74.py
import numpy as np
from pathlib import Path
from instream.modules.egg_emergence_m74 import apply_m74_cull


def test_m74_cull_scales_by_forcing_fraction(tmp_path: Path):
    """A 0.50 YSFM fraction should cull ~50 % of fry from that year's cohort."""
    csv = tmp_path / "m74.csv"
    csv.write_text(
        "year,river,ysfm_fraction,source\n"
        "2011,Simojoki,0.50,test\n"
    )
    # Simulate 10,000 emerging fry in Simojoki in 2011
    n_fry = 10000
    survivors = apply_m74_cull(
        n_fry=n_fry,
        year=2011,
        river="Simojoki",
        forcing_csv=csv,
        rng=np.random.default_rng(42),
    )
    # Binomial with p_survive=0.50, expect 4800–5200 at 2-sigma
    assert 4800 < survivors < 5200


def test_m74_cull_zero_when_no_forcing(tmp_path: Path):
    csv = tmp_path / "m74.csv"
    csv.write_text("year,river,ysfm_fraction,source\n")
    survivors = apply_m74_cull(
        n_fry=10000,
        year=2011,
        river="UnknownRiver",
        forcing_csv=csv,
        rng=np.random.default_rng(42),
    )
    # No forcing → no cull
    assert survivors == 10000


def test_m74_cull_zero_when_csv_none():
    """None csv means no forcing, same as empty."""
    survivors = apply_m74_cull(
        n_fry=10000,
        year=2011,
        river="Simojoki",
        forcing_csv=None,
        rng=np.random.default_rng(42),
    )
    assert survivors == 10000
```

- [ ] **Step L.3.3: Run test → FAIL** (module does not exist)

Run: `micromamba run -n shiny python -m pytest tests/test_egg_emergence_m74.py -v`

- [ ] **Step L.3.4: Implement `apply_m74_cull`**

Create `src/instream/modules/egg_emergence_m74.py`:

```python
"""Apply WGBAST M74 yolk-sac-fry mortality as a one-time binomial cull
at egg→fry emergence.

This is the correct life-stage for M74 (thiamine-deficiency): freshwater,
yolk-sac phase, pre-swim-up. Wiring at marine stage would compound an
annual fraction as a daily hazard (0.5^365 ≈ 10^-110 survival).

Reference: Vuorinen et al. 2021 (DOI 10.1080/10236244.2021.1941942);
WGBAST 2026 §3 (DOI 10.17895/ices.pub.29118545.v3).
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Tuple
import numpy as np

from instream.io.m74_forcing import load_m74_forcing, ysfm_for_year_river

_CACHE: Dict[Path, Dict[Tuple[int, str], float]] = {}


def apply_m74_cull(
    n_fry: int,
    year: int,
    river: str,
    forcing_csv: Path | str | None,
    rng: np.random.Generator,
) -> int:
    """Return the number of fry surviving M74 YSFM for (year, river).

    Binomial(n_fry, p_survive) where p_survive = 1 - YSFM_fraction.
    Returns n_fry unchanged if forcing_csv is None or (year, river) is
    not in the series.
    """
    if forcing_csv is None or n_fry <= 0:
        return int(n_fry)
    path = Path(forcing_csv)
    if path not in _CACHE:
        _CACHE[path] = load_m74_forcing(path)
    ysfm = ysfm_for_year_river(_CACHE[path], year, river)
    if ysfm <= 0.0:
        return int(n_fry)
    p_survive = max(0.0, 1.0 - float(ysfm))
    return int(rng.binomial(int(n_fry), p_survive))
```

- [ ] **Step L.3.5: Run test → PASS**

Run: `micromamba run -n shiny python -m pytest tests/test_egg_emergence_m74.py -v`

- [ ] **Step L.3.6: Extend `redd_emergence` signature with M74 kwargs**

Sixth review confirmed `redd_emergence` at `src/instream/modules/spawning.py`
has signature:
```python
def redd_emergence(
    redd_state, trout_state, rng,
    emerge_length_min, emerge_length_mode, emerge_length_max,
    weight_A, weight_B, species_index, superind_max_rep=10,
):
    ...
    rs = redd_state
    for i in range(len(rs.alive)):
        # … alive/frac checks …
        n_eggs_today = …   # local var holding eggs emerging this step
        # … fry super-individual creation below …
```

No `config`, `current_date`, or `model` is available in scope. To apply
M74 here, **extend the signature** with 3 optional kwargs, and reduce
`n_eggs_today` before fry creation.

Edit `src/instream/modules/spawning.py`:

```python
def redd_emergence(
    redd_state, trout_state, rng,
    emerge_length_min, emerge_length_mode, emerge_length_max,
    weight_A, weight_B, species_index, superind_max_rep=10,
    # --- New Arc L kwargs (all optional, default = no-op) ---
    m74_forcing_csv=None,       # str | None
    current_year: int | None = None,  # int
    river_name_by_reach_idx=None,     # Sequence[str|None] | None
):
    ...
    rs = redd_state
    for i in range(len(rs.alive)):
        # … existing alive/frac checks unchanged …
        n_eggs_today = …   # existing computation

        # Arc L: apply WGBAST M74 YSFM cull to this cohort
        if (
            m74_forcing_csv is not None
            and current_year is not None
            and river_name_by_reach_idx is not None
            and n_eggs_today > 0
        ):
            from instream.modules.egg_emergence_m74 import apply_m74_cull
            redd_reach_idx = int(rs.reach_idx[i])
            river = (
                river_name_by_reach_idx[redd_reach_idx]
                if 0 <= redd_reach_idx < len(river_name_by_reach_idx)
                else None
            ) or ""
            n_eggs_today = apply_m74_cull(
                n_fry=int(n_eggs_today),
                year=current_year,
                river=river,
                forcing_csv=m74_forcing_csv,
                rng=rng,
            )

        # … existing fry super-individual creation unchanged, using n_eggs_today …
```

- [ ] **Step L.3.7: Wire caller to pass new kwargs**

Find the caller of `redd_emergence` (grep
`grep -rn "redd_emergence(" src/instream/` — typically in
`model_day_boundary.py` or a scheduler). At the call site, compute the
three new args from the surrounding scope and pass them:

The concrete call site is the per-species loop at
`src/instream/model_day_boundary.py:456-467`. Keep existing positional
args unchanged, append the 3 new kwargs:

```python
# Inside the per-species loop (for sp_idx, sp_name in enumerate(self.species_order))
# in model_day_boundary.py. sp_cfg = self.config.species[sp_name].
river_name_by_reach_idx = [
    rc.river_name for rc in self.config.reaches.values()
]
redd_emergence(
    self.redd_state, self.trout_state, self.rng,
    sp_cfg.emerge_length_min, sp_cfg.emerge_length_mode, sp_cfg.emerge_length_max,
    sp_cfg.weight_A, sp_cfg.weight_B,
    species_index=sp_idx,
    superind_max_rep=int(getattr(sp_cfg, "superind_max_rep", 10) or 10),
    # --- Arc L new kwargs ---
    m74_forcing_csv=self.config.simulation.m74_forcing_csv,
    current_year=self.time_manager.current_date.year,
    river_name_by_reach_idx=river_name_by_reach_idx,
)
```

(Compare to the existing call before this change via
`grep -n "redd_emergence(" src/instream/model_day_boundary.py` and keep
all previously-passed arguments intact.)

(`river_name` is already present on ReachConfig + ReachParams + conversion
after Step L.3.0.)

- [ ] **Step L.3.8: Run the full suite to confirm no parity regression**

Run: `micromamba run -n shiny python -m pytest tests/ -q --tb=short`
Expected: all PASS. `tests/test_run_level_parity.py::TestExampleARunVsNetLogo`
should still pass because `example_a.yaml` does not set `m74_forcing_csv`
(default None → cull skipped → NetLogo parity preserved).

- [ ] **Step L.3.9: Commit**

```bash
git add src/instream/modules/egg_emergence_m74.py src/instream/modules/spawning.py src/instream/model_day_boundary.py src/instream/io/config.py tests/test_egg_emergence_m74.py
git commit -m "feat(m74): apply WGBAST YSFM at egg-emergence (correct life-stage)"
```

### Task L.4: Deprecate marine_mort_m74_prob + Baltic wiring + release

- [ ] **Step L.4.1: Deprecate the marine-stage M74 scalar**

Edit `src/instream/marine/config.py:134-135`:

```python
# DEPRECATED (Arc L, 2026-04-20): M74 was incorrectly modelled as a
# marine-stage daily hazard here. It is now applied as a one-time
# binomial cull at egg→fry emergence in src/instream/modules/egg_emergence_m74.py
# driven by the per-(year,river) WGBAST YSFM series. Setting this field
# to a non-zero value issues a deprecation warning.
marine_mort_m74_prob: float = 0.0
```

Add a `__post_init__` (or pydantic validator) that warns if a user sets
a non-zero value.

- [ ] **Step L.4.2: Wire into configs/example_baltic.yaml**

Under the `simulation:` block (which maps to `SimulationConfig`), add:
```yaml
simulation:
  # … existing fields …
  m74_forcing_csv: data/wgbast/m74_ysfm_series.csv
    # [Vuorinen et al. 2021 + WGBAST 2026 §3 — applied at egg→fry
    #  emergence per Arc L]
```

Note: `baltic_salmon_species.yaml` is the species-parameter block and
is merged into a full config. The `m74_forcing_csv` field lives on
SimulationConfig (top-level `simulation:` key), not under species, so
set it in the parent config (e.g. `example_baltic.yaml`), not in
`baltic_salmon_species.yaml`.

- [ ] **Step L.4.3: CHANGELOG + release v0.35.0**

Pattern identical to Task K.5 / K.6.

```bash
git tag v0.35.0
git push origin master v0.35.0
```

---

# Arc M: Multi-river Baltic fixtures

**Goal:** Add named configs + fixture data for Tornionjoki (AU 1, 3–4 yr smolts), Simojoki (AU 1, trap-counted), Byskeälven (AU 2, Skoglund 2024 homing dataset), and Mörrumsån (southern, 1–2 yr smolts at 11–15 cm). Together these span the WGBAST latitudinal smolt-age gradient.

**Why:** Arc K emits per-reach PSPC but a single Nemunas fixture covers only one river. Multi-river fixtures let a single SalmoPy run produce a WGBAST-comparable table across 4 stock-assessment rivers.

**Effort:** M–L (3–5 days). Each river is ~1 day: geometry scaffolding, hydrology approximation, per-river YAML with species overrides (smolt_min_length, spawn_start_day).

## File Structure

**Create per river** (repeat pattern for each of 4):
- `tests/fixtures/tornionjoki/` — reach CSV, hydraulics CSV, Shapefile stub
- `tests/fixtures/simojoki/`
- `tests/fixtures/byskealven/`
- `tests/fixtures/morrumsan/`
- `configs/example_tornionjoki.yaml` — references the fixture + BalticAtlanticSalmon species with river-specific overrides
- `configs/example_simojoki.yaml`
- `configs/example_byskealven.yaml`
- `configs/example_morrumsan.yaml`
- `docs/validation/v0.36.0-multi-river-baltic.md`

## Tasks

### Task M.1: Per-river geometry + hydrology scaffolding

For each river:

- [ ] **Step M.1.1: Pull river geometry via the ICES MCP + OpenStreetMap**

Use `ices_get_rectangles` for the bounding box, then the OSM fetcher (already in `app/modules/create_model_osm.py`) to grab the river centerline.

- [ ] **Step M.1.2: Hand-edit the reach CSV** to ~5–10 reaches matching WGBAST assessment resolution.

- [ ] **Step M.1.3: Pull WGBAST PSPC per reach** from WGBAST 2026 Section 3 river-specific table. Torne ≈ 2,200k; Simo ≈ 95k; Byske ≈ 180k; Mörrum ≈ 50k. Populate `pspc_smolts_per_year` in the config.

### Task M.2: Per-river species overrides

Latitudinal smolt-age gradient (from v0.33.0 validation doc §2.4):

- [ ] **Step M.2.1: Tornionjoki + Simojoki**: `smolt_min_length: 14` (AU 1 produces 14–18 cm smolts at 3–4 years, Skoglund 2024 Paper III).

- [ ] **Step M.2.2: Byskeälven**: `smolt_min_length: 13` (AU 2 intermediate).

- [ ] **Step M.2.3: Mörrumsån**: `smolt_min_length: 11` (southern, 11–15 cm at 1–2 years).

### Task M.3: Per-river run + cross-validation test

**Correction (final review 2026-04-20):** `InSTREAMModel.__init__` takes
`config_path` (a YAML path string), not a pydantic config object. Outputs are
written by `run()`; no `finalise()` exists. Use the same temp-YAML-copy
pattern as Arc K.4.2. Also: `age_years` + `length_category` are already
emitted in Arc K.1.4's widened outmigrants schema — no separate column-add
task is needed.

- [ ] **Step M.3.1: Write failing test**

```python
# tests/test_multi_river_baltic.py
import pandas as pd
import pytest
import yaml
from instream.model import InSTREAMModel


@pytest.mark.parametrize("config,expected_smolt_age_mode", [
    ("configs/example_tornionjoki.yaml", 4),   # 3-4 yr
    ("configs/example_simojoki.yaml", 3),
    ("configs/example_byskealven.yaml", 2),
    ("configs/example_morrumsan.yaml", 2),     # 1-2 yr
])
def test_latitudinal_smolt_age_gradient(config, expected_smolt_age_mode, tmp_path):
    with open(config) as f:
        cfg_dict = yaml.safe_load(f)
    cfg_dict["run"]["end_date"] = "2015-12-31"
    cfg_dict["run"]["seed"] = 42
    cfg_path = tmp_path / "short_cfg.yaml"
    with open(cfg_path, "w") as f:
        yaml.safe_dump(cfg_dict, f)

    model = InSTREAMModel(config_path=str(cfg_path), output_dir=str(tmp_path))
    model.run()

    df = pd.read_csv(tmp_path / "outmigrants.csv")
    smolts = df[df["length_category"] == "Smolt"]
    modal_age = int(smolts["age_years"].round().mode()[0])
    assert abs(modal_age - expected_smolt_age_mode) <= 1, (
        f"{config}: expected modal age {expected_smolt_age_mode}, got {modal_age}"
    )
```

- [ ] **Step M.3.2: Run tests → expect all 4 to pass**. If any fails, check
  species override + YAML wiring.

### Task M.4: Docs + release v0.36.0

Pattern identical to Arc K's doc/release tasks.

---

# Arc N: Post-smolt survival time-varying forcing

**Goal:** Feed the WGBAST post-smolt survival series (SAG `assessmentKey=13726`) into the marine module per simulated smolt-year, replacing the single-point calibration (3.61 %).

**Why:** WGBAST 2026 shifted its projection baseline to post-smolt cohort 2020–2023; a retrospective SalmoPy run across 1987–2023 needs the year-by-year survival curve, not a constant.

**Effort:** M (2–3 days). Pattern very similar to Arc L but targets marine survival (not M74) and the data series is richer (per-river + per-year).

## File Structure

**Create:**
- `data/wgbast/post_smolt_survival.csv` — columns `year, survival_pct, stock_unit` (stock_unit ∈ {sal.27.22-31, sal.27.32})
- `src/instream/marine/survival_forcing.py` — loader + per-year kernel hook
- `tests/test_post_smolt_forcing.py`

**Modify:**
- `src/instream/marine/config.py` — add `post_smolt_survival_forcing_csv: Path | None` + `stock_unit: str | None`
- `src/instream/marine/survival.py` — per-year override of the post-smolt kernel

## Tasks

**Data source correction (review 2026-04-20):** SAG `assessmentKey=13726` returns
only spawners + catches, NOT a post-smolt survival series. The Bayesian-model
latent post-smolt survival series lives inside the WGBAST 2026 report PDF
(§2 figures/tables). Olmos 2018 (DOI 10.1111/faf.12345) covers North Atlantic
stocks only (not Baltic) — not usable for Baltic forcing.

1. **Arc 0.4 prerequisite**: depend on `data/wgbast/post_smolt_survival_baltic.csv`
   emitted by Arc 0 Task 0.4 (PDF extraction via WebPlotDigitizer of the §2
   Bayesian posterior-median figure). Schema: `year, survival_pct, stock_unit`.
2. TDD-extend `MarineConfig` with `post_smolt_survival_forcing_csv: Path | None`
   and `stock_unit: str | None = "sal.27.22-31"`.
3. TDD-extend `integrated_marine_survival()` in `src/instream/marine/survival.py`
   to override the default post-smolt daily hazard with the per-(year, stock_unit)
   value from the CSV when it's set. Semantics: the CSV value is an annual
   survival fraction; daily hazard = `1 - survival^(1/365)`.
4. Integration test: `tests/test_post_smolt_forcing.py::test_annual_survival_matches_forcing`
   — run example_baltic 2000–2005 with a stub CSV that forces 6% post-smolt
   survival uniformly; measure actual outmigrant→adult-return ratio; assert
   within ±1 pp of 6%.
5. Validate against ICES (2023) WGBAST §2.5 3–12% published band — the 2000–2024
   series must stay inside that envelope.
6. Docs + release v0.37.0.

---

# Arc O: Straying/homing knob + genetic-MSA spawner-origin matrix

**Goal:** Add a `stray_fraction: float` parameter that controls what fraction of
returning adults stray from their natal river, and emit a per-run
`spawner_origin_matrix.csv` that is structurally comparable to WGBAST's
genetic mixed-stock analysis (Säisä et al. 2005; Östergren et al. 2021).

**Citation correction (review 2026-04-20):** the first draft cited Palmé et al.
2012 as a Baltic salmon straying reference — that paper is actually on brown
trout effective population size in Swedish mountain lakes. Removed. The correct
Baltic-salmon population-genetics reference is **Säisä et al. 2005**
(DOI 10.1139/f05-094, postglacial colonisation + genetic structure) + **Östergren
et al. 2021** (DOI 10.1098/rspb.2020.3147, century of archival-DNA-based
homogenisation).

**Why:** WGBAST apportions mixed sea catches back to rivers via genetic MSA.
A model with a single-river homing default (current SalmoPy) biases recruitment
estimates when spawner behavior is actually mixed. The 2025 stock annex
explicitly flags homing/straying structure as a known uncertainty.

**Effort:** M (3–4 days). Harder than L/N because it changes the marine-return kernel (`src/instream/marine/domain.py:381-410`).

## File Structure

**Modify:**
- `src/instream/marine/config.py` — add `stray_fraction: float = 0.0`
- `src/instream/marine/domain.py:381` — when returning, with probability `stray_fraction`, reassign `trout_state.reach_idx[i]` to a randomly chosen OTHER reach (weighted by reach size or uniformly, per a documented scheme).
- `src/instream/io/output.py` — new `write_spawner_origin_matrix()` that builds a natal-reach × spawning-reach matrix.

## Tasks

1. TDD: `test_stray_fraction_zero_means_perfect_homing` + `test_stray_fraction_one_means_uniform_mixing`.
2. Implement straying at the marine-return site — keep `natal_reach_idx` fixed (it's a genetic/birth property) but relocate `reach_idx` (the spawning location).
3. TDD: `test_spawner_origin_matrix_is_identity_under_perfect_homing`.
4. Implement `write_spawner_origin_matrix(spawners, reach_names, output_dir)` → emits a DataFrame where row=natal_reach, col=spawning_reach, cell=count.
5. Integration test on a 2-river toy config with stray_fraction=0.15: verify the off-diagonal mass in the matrix is ~15 % of total.
6. Docs + release v0.38.0.

---

# Arc P: Grey-seal predation as explicit mortality term

**Goal:** Split grey-seal predation (currently absorbed into `marine_mort_natural`) into its own mortality hazard with a seal-abundance time series (HELCOM/ICES WGBIFS).

**Why:** Lai, Lindroos & Grønbæk (2021) — DOI 10.1007/s10640-021-00571-z — argue grey-seal predation should be explicit in bio-economic salmon models; WGBAST 2025 stock annex flags seal abundance as a growing uncertainty in the Main Basin.

**Effort:** M (3 days). Orthogonal to Arcs L/N/O — can run anytime after K.

## File Structure

**Create:**
- `data/helcom/grey_seal_abundance_baltic.csv` — year, estimated_population (HELCOM SEAL expert group series)
- `src/instream/marine/seal_predation.py` — hazard as function of seal abundance + salmon size class

**Modify:**
- `src/instream/marine/config.py` — add `seal_predation_rate_per_seal: float`, `seal_abundance_csv: Path | None`
- `src/instream/marine/survival.py` — add `seal_predation_hazard()` multiplied into the post-smolt + adult survival product
- `configs/baltic_salmon_species.yaml` — seal params + CSV reference

## Tasks

1. Pull HELCOM grey-seal abundance from the Baltic seal monitoring series (1988–present, 5k → 40k).
2. TDD: `test_seal_hazard_scales_with_abundance` (2x population → 2x hazard under linear model).
3. Implement `seal_predation_hazard(n, size_class, year, config)`.
4. Integrate into `integrated_marine_survival(...)` product in `src/instream/marine/survival.py:145+`.
5. Validation: with seal term ON and equivalent total mortality, SAR should stay within ±0.5 pp of Arc K baseline.
6. Release v0.39.0.

---

# Arc Q: Bayesian life-cycle wrapper

**Goal:** Wrap the existing `src/instream/calibration/` framework in a Bayesian life-cycle shell comparable to the WGBAST Bayesian model (Kuikka, Vanhatalo & Pulkkinen 2014, DOI 10.1214/13-sts431). The wrapper produces posterior distributions over key latent parameters (post-smolt survival, M74 variance, straying fraction) conditioned on smolt trap counts + spawner counter data.

**Why:** Completes the WGBAST-parallel analytical stack. Enables retrospective hindcasts and probabilistic stock projections.

**Effort:** L (1–2 weeks). Biggest Arc — **re-expand into its own plan before execution**.

## File Structure (high-level)

**Create:**
- `src/instream/bayesian/` — new subpackage
  - `observation_model.py` — likelihood for smolt-trap + spawner-counter observations
  - `prior.py` — priors on latent params (post-smolt survival, M74, straying)
  - `inference.py` — SMC or VI wrapper around the SalmoPy forward model
- `data/wgbast/observations/` — trap counts + counter data (Simo, Torne, Byske, Mörrum)
- `tests/test_bayesian_wrapper.py`

## Tasks (sketch — expand before executing)

1. Specify observation likelihoods (Poisson on smolt traps; negative-binomial on counters).
2. Wire the `src/instream/calibration/sensitivity.py` Sobol/Morris ranking as the prior-design step.
3. Implement an SMC particle filter or variational posterior over the top-ranked latent params.
4. Validate: posterior median post-smolt survival for sal.27.22-31 should align with WGBAST's published posterior (3–12 %) within the reported uncertainty band.
5. Release v0.40.0.

**Stop here and re-run `superpowers:writing-plans` scoped to Arc Q when its turn comes.**

---

# Self-Review (post-revision 2026-04-20)

**Spec coverage** (checks against the 7 WGBAST options from the exploration):
- [x] Option 1: Per-reach PSPC → Arc K
- [x] Option 2: Stochastic M74 year-effect → Arc L (egg-stage, corrected)
- [x] Option 3: Multi-river Baltic fixtures → Arc M
- [x] Option 4: Post-smolt survival forcing → Arc N (WGBAST PDF source)
- [x] Option 5: Straying/homing + genetic MSA matrix → Arc O
- [x] Option 6: Grey-seal predation → Arc P
- [x] Option 7: Bayesian wrapper → Arc Q
- [x] **+ Arc 0 data assembly (prepended from review)**

All 7 covered plus data prerequisite.

**Type consistency**:
- `natal_reach_idx` (int) used consistently across K.1 (outmigrant dict), K.3
  (reach-grouping), O (spawner-origin matrix).
- `natal_reach_name` (str) added in K.1 widened schema; consumed by Arc L
  (M74 river-key lookup) and Arc M (per-river outmigrant filtering).
- `pspc_smolts_per_year` (float | None) used consistently across K.2
  (ReachConfig field), K.3 (CSV column), M.1.3 (per-river YAML).
- `(year, river)` tuple key for M74 forcing (Arc L) matches the CSV schema
  produced by Arc 0.3.
- `stock_unit: str` on post-smolt forcing (Arc N) matches CSV emitted by Arc 0.4.

**Review-pass findings** (2026-04-20, 4 parallel reviewers + 1 final sanity pass):

First pass (4 reviewers):
- **Fixed** Arc L life-stage mismatch: M74 now at egg-emergence, not marine kernel.
- **Fixed** Arc K file paths: `modules/migration.py:94,112,134`, not `marine/domain.py`.
- **Fixed** Arc K schema: widened to 10 columns (NetLogo-compat).
- **Fixed** Arc K integration test: `InSTREAMModel` direct, no fake `run_simulation`.
- **Fixed** Arc M override mechanism: pydantic YAML write-to-tmp, not dot-notation.
- **Fixed** Arc N data source: WGBAST PDF Bayesian posterior, not SAG key 13726.
- **Fixed** Arc L citation: Vuorinen 2021 (not Koski/Mikkonen).
- **Fixed** Arc O citation: Säisä 2005 + Östergren 2021 (Palmé 2012 removed).
- **Added** Arc 0 prerequisite data-assembly task.
- **Added** -1 natal_reach_idx guard in `write_outmigrants`.

Final sanity pass (fix-in-plan):
- **Fixed** `trout_state.age_days` → `trout_state.age` (real attribute name).
- **Added** pre-step K.1.5b to add `initial_length` field to `TroutState`
  (did not exist).
- **Fixed** `model.current_step` → day-offset from
  `model.time_manager.current_date`.
- **Fixed** `InSTREAMModel(cfg, …)` → `InSTREAMModel(config_path=str(path), …)`
  (constructor takes path, not pydantic object).
- **Removed** `model.finalise()` calls; `run()` writes outputs internally.
- **Fixed** "9-column" descriptive text → "10-column" (schema emits both
  natal_reach_idx + natal_reach_name).
- **Added** `require_natal_reach=has_pspc` conditional activation in K.4.4
  (was previously dead-code).
- **Added** mandatory Step L.3.0 to introduce `river_name: str | None` on
  `ReachConfig` + `ReachParams` before the Arc L wiring touches it.

**Placeholder scan**: Arcs M–Q intentionally compress detail (see top-of-doc
scope note). Arcs 0, K, L — the first concrete work — are fully TDD-specified
with code in every step.

**Known compressions** (intentional, per scope note):
- Arcs N, O, P list tasks as numbered bullets, not bite-sized TDD steps.
  Re-expand before execution.
- Arc Q is a sketch only.

---

# Execution Handoff

Plan saved to `docs/superpowers/plans/2026-04-20-arc-K-to-Q-wgbast-roadmap.md`.

**Two execution options:**

**1. Subagent-Driven (recommended for Arc K)** — dispatch a fresh subagent per task in Arc K (6 tasks × ~5 steps), review between tasks, fast iteration. Use `superpowers:subagent-driven-development`.

**2. Inline Execution** — execute Arc K tasks in one session using `superpowers:executing-plans`, checkpoint at task boundaries.

For Arcs L–Q: re-run `superpowers:writing-plans` scoped to each Arc when its turn comes to regenerate full TDD detail.

**Which approach for Arc K?**
