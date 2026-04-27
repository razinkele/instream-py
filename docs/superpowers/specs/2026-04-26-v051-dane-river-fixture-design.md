# v0.51.0 — Add Danė river to example_baltic fixture

**Status:** Design — pending review
**Date:** 2026-04-26
**Origin:** Deferred from v0.50.0 release notes ("v0.51.0: use these new buttons end-to-end to add the Danė river to example_baltic"). The natural integration test for v0.50.0's three new Create Model panel buttons.

## Summary

Add the Danė river (~110 km, flows through Klaipėda directly into the Klaipėda
Strait → Baltic Sea, NOT through the Nemunas delta) to `example_baltic` as
**5 new reaches**: Dane_Mouth, Dane_Lower, Dane_Middle, Dane_Upper, plus
KlaipedaStrait. example_baltic grows from 9 reaches (1591 cells per v0.30.1)
to 14 reaches.

This is a **fixture-extension release** — no code changes to `app/modules/`
or `src/salmopy/`. The work is the v0.50.0 buttons performed end-to-end on
real Klaipėda OSM data, plus a manual merge of the exported reaches into
the existing example_baltic fixture, plus a smoke probe to defend against
silent breakage.

## Out of scope (deferred)

- "Merge fixture A into fixture B" UI button — v0.52+.
- Per-param Danė biological calibration beyond clone-and-tune-pspc — v0.51.x or v0.52.x.
- Lithuanian-language reach segment names (Klaipėda/Kretinga/Kūlupėnai/Vyžuonai) — not in scope; English `Dane_*` matches the existing reach-naming convention (Nemunas/Atmata/Minija are river-named, Skirvyte/Leite/Gilija are tributary-named).
- Updating `BalticExample-InitialPopulations.csv` for Danė-natal cohort — defaults to 0 (returners populate via AdultArrivals).
- Tornionjoki juvenile-growth calibration (Workstream B from v0.46+) — v0.52.0.

## Architecture

**One operator workflow** (Section 2 below) using the v0.50.0 Create Model
panel buttons end-to-end on Klaipėda OSM data, plus a manual YAML/CSV/shapefile
merge into the existing example_baltic fixture, plus a smoke probe.

**Five new reaches** added to example_baltic:

| Reach | Calibration source | Pspc smolts/yr | Junction (up→dn) |
|-------|-------------------|----------------|-------------------|
| Dane_Upper | clone Minija | ~150 | 10 → 11 |
| Dane_Middle | clone Minija | ~100 | 11 → 12 |
| Dane_Lower | clone Minija | ~50 | 12 → 13 |
| Dane_Mouth | clone Minija (pspc=0; salmon don't spawn at the mouth) | 0 | 13 → 14 |
| KlaipedaStrait | clone CuronianLagoon (`fish_pred_min: 0.800`, brackish-zone params) | n/a (sea reach) | 14 → existing BalticCoast.upstream |

Total Danė pspc = ~300 smolts/yr (small historical population, smaller than
Minija's 1200 — Danė has urban/pollution pressures from Klaipėda city).

**Junction wiring** is a linear chain. New IDs start at 10 to clearly separate
from the existing 1–9 range used by the Nemunas delta system. Plan task
verifies the existing max junction ID at spec-time before locking IDs.

**Files modified/created** (concrete list):

| File | Action | Notes |
|------|--------|-------|
| `configs/example_baltic.yaml` | Modify | +5 reach blocks at the appropriate position in the `reaches:` section |
| `tests/fixtures/example_baltic/Dane_Mouth-Depths.csv` | Create | from Create Model export |
| `tests/fixtures/example_baltic/Dane_Mouth-Vels.csv` | Create | from export |
| `tests/fixtures/example_baltic/Dane_Mouth-TimeSeriesInputs.csv` | Create | from export |
| (same 3 files × 3 more reaches) | Create | Dane_Lower, Dane_Middle, Dane_Upper |
| `tests/fixtures/example_baltic/KlaipedaStrait-Depths.csv` | Create | hand-written (sea reach) |
| `tests/fixtures/example_baltic/KlaipedaStrait-Vels.csv` | Create | hand-written |
| `tests/fixtures/example_baltic/KlaipedaStrait-TimeSeriesInputs.csv` | Create | hand-written |
| `tests/fixtures/example_baltic/Shapefile/example_baltic.shp` (and .dbf/.shx/.prj) | Modify | append 5 polygons |
| `tests/fixtures/example_baltic/BalticExample-AdultArrivals.csv` | Modify | add Danė-bound rows (~5–10 fish/yr; 1.5–2% of total arrivals) |
| `scripts/_probe_baltic_with_dane.py` | Create | smoke probe ~50 LOC, 7 assertions |
| `pyproject.toml` | Modify | version bump 0.50.0 → 0.51.0 |
| `src/salmopy/__init__.py` | Modify | version bump |
| `CHANGELOG.md` | Modify | prepend v0.51.0 entry |

## Components & data flow (the workflow)

Step-by-step operator runbook:

1. Start local Shiny:
   `micromamba run -n shiny python -m shiny run --port 9050 app/app.py`

2. In browser, open Create Model panel.

3. Type "Klaipėda" → click 🔍 Find.
   - Region dropdown auto-sets to "lithuania".
   - Map zooms to bbox (~lat 55.71, lon 21.15, zoom ~13).
   - Rivers + Water layers auto-fetched (~10 s).

4. Click 🌊 Sea.
   - Marine Regions WFS returns Baltic Sea polygon.
   - `_sea_gdf` populated; Sea layer rendered.

5. (Optional) Adjust Strahler slider down to ≥2 if Danė centerline doesn't
   appear at default ≥3 (Danė is small; per OSM Strahler tagging, mainstem
   may be Strahler 2 in upper sections).

6. Click ✨ Auto-extract.
   - `filter_polygons_by_centerline_connectivity` drops polygons not
     connected to Danė centerline (Klaipėda area has many small lakes,
     harbors, distillation ponds that aren't part of Danė).
   - Toast: "Kept N of M polygons in the main river system."
   - **Visual checkpoint**: inspect map — should show only Danė channel
     polygons + Klaipėda Strait / coastal water that's connected via the
     strait. If unwanted polygons remain, manual click-deselect via the
     existing 💧 Lagoon mode.

7. Click ⚡ Auto-split with N=4 (default).
   - Mouth auto-detected: closest centerline endpoint to Sea polygon
     (Klaipėda mouth, ~0 m offshore).
   - 4 reaches produced: Mouth, Lower, Middle, Upper.
   - Toast: "Split into 4 reaches: Mouth (X), Lower (Y), Middle (Z), Upper (W)."

8. Switch to Edit Model panel → load the in-memory fixture → rename:
   - Mouth → Dane_Mouth
   - Lower → Dane_Lower
   - Middle → Dane_Middle
   - Upper → Dane_Upper

   (Uses the v0.45.3 reach-rename feature.)

9. In Create Model, click 📦 Export → save as temp fixture
   `tests/fixtures/_dane_temp/`. Per v0.49.0, the export now produces
   loader-compatible per-cell CSVs.

10. Manual merge into `tests/fixtures/example_baltic/`:
    a. Copy `_dane_temp/Dane_*.csv` (12 files: 4 reaches × 3 file types) →
       `tests/fixtures/example_baltic/`.
    b. Copy `_dane_temp/Shapefile/*.shp/dbf/shx/prj` → merge into
       `tests/fixtures/example_baltic/Shapefile/` (append rows; reach name
       column distinguishes them).
    c. Manual edit to `configs/example_baltic.yaml`: 5 reach YAML blocks
       (4 Danė reaches cloned from Minija + KlaipedaStrait cloned from
       CuronianLagoon). Pspc values per Architecture table above.
    d. Hand-write KlaipedaStrait CSVs (3 files) — small reach (~5–10 cells),
       can be near-uniform Depths/Vels and a flat TimeSeriesInputs.
    e. Add KlaipedaStrait polygon to shapefile (a small ~5 km² polygon at the
       strait between Klaipėda and Smiltynė).

11. Run smoke probe:
    `micromamba run -n shiny python scripts/_probe_baltic_with_dane.py`
    → loads merged fixture, asserts 14 reaches, asserts CSVs match, asserts
      shapefile reaches match YAML, asserts junction graph is connected.

12. Run regression test:
    `micromamba run -n shiny python -m pytest tests/test_baltic_example.py::test_fixture_loads_and_runs_3_days -v`
    → 3-day sim succeeds with 14 reaches, no crashes.

13. (Optional) Update `BalticExample-AdultArrivals.csv` — add ~5–10 fish/yr
    Danė-bound arrival rows (1.5–2% of total). Re-run the 3-day smoke.

## Calibration plan (per Q4 — clone-and-go)

**Dane_Upper, Middle, Lower, Mouth**: clone Minija's params verbatim
(`drift_conc: 1.5e-08`, `search_prod: 1.80e-06`, `shelter_speed_frac: 0.22`,
`prey_energy_density: 4000`, `drift_regen_distance: 700`, `shading: 0.72`,
`fish_pred_min: 0.980`, etc.). Tune `pspc_smolts_per_year` per the
Architecture table.

Per-reach pspc rationale:
- **Dane_Mouth: 0** — salmon don't spawn at the river mouth (brackish water,
  no gravel substrate).
- **Dane_Lower: 50** — small contribution; lower Danė runs through Klaipėda
  city limits (~5 km), urban pollution + reduced spawning habitat.
- **Dane_Middle: 100** — main spawning zone if any; rural mid-river.
- **Dane_Upper: 150** — best spawning habitat; cooler water, less pollution.

Total = 300 smolts/yr. Smaller than Minija's 1200 — Danė is shorter and
has had documented salmon-population declines from urban pressures (per
fisheries reports in the area).

**KlaipedaStrait**: clone CuronianLagoon's params:
- `fish_pred_min: 0.800` (brackish-zone pike, perch, cormorants)
- `terr_pred_min: 0.965` (cormorants, herons)
- Other brackish-zone params identical.

KlaipedaStrait is a sea-edge transition reach (similar role to CuronianLagoon
but on the seaward side of the strait); cloning the lagoon's calibration
gives a defensible starting point.

## Junction wiring (linear chain)

New IDs start at 10 to clearly separate from the existing 1–9 range:

```
Dane_Upper:     upstream=10, downstream=11
Dane_Middle:    upstream=11, downstream=12
Dane_Lower:     upstream=12, downstream=13
Dane_Mouth:     upstream=13, downstream=14
KlaipedaStrait: upstream=14, downstream=<existing_BalticCoast.upstream>
```

Plan task verifies the existing max junction ID before locking these. The
smoke probe asserts each junction is referenced consistently (every
`downstream_junction` matches an `upstream_junction` of another reach OR
matches the BalticCoast sea-edge pattern).

## Error handling & edge cases

| Risk | Mitigation |
|------|------------|
| Auto-extract drops Danė centerline (Strahler too high; Danė is small) | Workflow step 5: lower Strahler to ≥2 before Auto-extract. Smoke probe step 11 asserts all 4 Dane_* reaches non-empty. |
| Auto-split assigns wrong polygons to Upper vs Lower (along-channel direction backwards) | `_orient_centerline_mouth_to_source` proven since v0.47.0. Manual visual check at step 7 — if Upper looks like Mouth on the map, the centerline orientation failed; rename via Edit Model post-hoc. |
| Mouth auto-detection picks wrong endpoint (Danė splits in Klaipėda port; centerline may have multiple endpoints) | `_pick_mouth_from_sea` uses closest endpoint to Sea. If wrong endpoint chosen, use click-mouth fallback: deselect 🌊 Sea before clicking ⚡, then click the actual mouth on the map. |
| OSM data sparse (Danė shows only 2-3 polygons; Auto-split N=4 produces empty reaches) | The N>polygons toast warns upfront. Workflow contingency: rerun with N=2 (Mouth + Upper). Document the actual N in release notes. |
| Junction ID collision with existing example_baltic IDs | Spec uses IDs 10+; verify at spec-time. Smoke probe asserts each `upstream_junction`/`downstream_junction` is referenced consistently (graph integrity). |
| YAML formatting mismatch between exported reach blocks and example_baltic style | Existing example_baltic uses 2-space indent + comments. Hand-edit during merge to match. |
| Shapefile DBF column-set mismatch | Both produced by the same Create Model export pipeline; columns should match. Smoke probe asserts shapefile column-set is identical pre- and post-merge. |
| CSV stem collision in `tests/fixtures/example_baltic/` | Reach names start with `Dane_` or are `KlaipedaStrait` — no collision with existing 9 reach names. |
| Klaipėda Strait polygon overlap with existing BalticCoast cells | Manual: define KlaipedaStrait polygon to be the narrow channel BETWEEN the lagoon and the open Baltic, NOT overlapping existing BalticCoast. Visual inspection during merge. |
| 3-day fixture-load smoke fails after merge | Most likely: junction wiring inconsistency. Probe outputs which assertion failed; fix manually, rerun. |
| `export_template_csvs` format mismatch (would have been a v0.49.0-era bug) | Closed by v0.49.0; per-cell CSVs now load through `_parse_hydraulic_csv`. Smoke probe verifies by loading each new CSV. |

## Smoke probe responsibilities

`scripts/_probe_baltic_with_dane.py` (~50 LOC) checks:

1. `configs/example_baltic.yaml` parses cleanly with all 14 reaches.
2. Each reach has its 3 CSVs (Depths, Vels, TimeSeriesInputs) at expected filenames.
3. Each per-cell CSV loads through `_parse_hydraulic_csv` (validates v0.49.0 format).
4. Junction graph is connected: every `downstream_junction` points to an
   existing `upstream_junction` of another reach OR matches BalticCoast's
   sea-edge pattern.
5. Shapefile feature count matches `len(reaches)` (one polygon per reach).
6. Shapefile reach name column contains all 14 reach names exactly once.
7. Total fixture cell count is in expected range (existing ~1591 cells +
   new 5 reaches estimated +200–400 cells).

If any assertion fails, the probe prints the specific reach/file/junction
that's broken so the operator can fix the merge and rerun.

## Testing

### Existing test gates

`tests/test_baltic_example.py::test_fixture_loads_and_runs_3_days[example_baltic]`
must continue to PASS after the merge. Loads YAML, instantiates simulation,
runs 3 simulated days, verifies no crashes. Does NOT check biological
correctness — just structural integrity.

### New smoke probe

Per Section 3, ~50 LOC, 7 assertions. Run manually post-merge as a self-check
before committing. NOT a pytest fixture — one-shot probe that prints
PASS/FAIL per assertion.

### No new pytest cases

Deliberately. The work is data-addition, not code-addition. Existing tests
cover the loaders. Auto-extract/Auto-split/Find handlers are tested in
v0.50.0 (38 unit tests). A "Danė-specific behavior" test would be premature
— biological calibration is out of scope per Q4.

### Manual verification checklist

Run before commit:

1. **Workflow walkthrough** — perform Section 2 steps 1–13 in a clean checkout. Verify each step produces expected toast / state change.
2. **Smoke probe** — `micromamba run -n shiny python scripts/_probe_baltic_with_dane.py` → 7/7 PASS.
3. **3-day fixture-load** — `micromamba run -n shiny python -m pytest tests/test_baltic_example.py::test_fixture_loads_and_runs_3_days -v` → PASS.
4. **Other example fixtures unaffected** — `micromamba run -n shiny python -m pytest tests/test_baltic_example.py tests/test_fixture_loads.py -v` → all existing tests PASS (no regression in example_a, example_b, the WGBAST four).
5. **Visual map QA** — load the merged fixture in the Edit Model panel; verify all 14 reach polygons render at sensible Klaipėda+Nemunas geography; no overlap; no orphan polygons.

## Commit cadence

Per the v0.47–v0.50 pattern, but lighter (data-addition release):

1. `feat(example_baltic): add Danė river (4 reaches) + Klaipėda Strait` —
   single commit covering YAML edit + 15 new CSVs + shapefile changes +
   smoke probe + AdultArrivals update.

2. `release(v0.51.0): Danė river fixture` — version bump + CHANGELOG.

Two commits total.

## Required dependencies

No new dependencies. Existing geopandas, shapely, pyyaml, pytest cover
everything.

## Risks / open questions for plan-time review

1. **Auto-extract may include unintended polygons** at the Klaipėda port (the
   port has dredged channels connected to the Danė centerline by the strait).
   Plan-time check: dry-run the Auto-extract step on Klaipėda and inspect.
   If port channels surface, manual click-deselect via 💧 Lagoon mode is
   the documented workaround.

2. **Auto-split mouth detection may pick the wrong endpoint** if the Danė
   has tributary forks within the city limits (smaller streams join the
   main Danė in Klaipėda). The `_pick_mouth_from_sea` helper picks the
   closest centerline endpoint to the sea polygon — should hit the actual
   river mouth at Klaipėda harbor, but the click-mouth fallback handles
   this if it picks wrong. Plan task: verify visually after step 7.

3. **KlaipedaStrait polygon definition is manual-geographic**. The plan
   needs a concrete instruction: "the strait polygon is the narrow channel
   between Smiltynė (north) and Klaipėda (south), bounded by the Curonian
   Spit on the west and Klaipėda's port quay on the east, ~1 km wide,
   ~5 km long". Plan-time decision: hand-trace from OpenStreetMap or QGIS,
   or use a Marine Regions sub-polygon (the Klaipėda Strait may not have
   its own Marine Regions identifier — it's part of the Baltic Sea
   IHO area).

4. **CSV stems for KlaipedaStrait** are hand-written. The plan needs to
   spec what depth/velocity/time-series values to use. Reasonable starting
   defaults: depth 5–15 m (varies by sub-cell), velocity 0.1–0.3 m/s
   (tidal-influenced; the strait has weak tidal currents from the Baltic),
   uniform daily TimeSeriesInputs matching CuronianLagoon's pattern.

5. **AdultArrivals update**: the small Danė-bound returner fraction (1.5–2%
   of total arrivals) needs concrete daily-arrival rows. Plan task: read the
   existing AdultArrivals CSV, distribute ~5–10 fish/yr across the existing
   arrival schedule, append new rows tagged for Dane_Mouth (returners
   navigate to natal river via the Mouth reach).

6. **Existing max junction ID verification**: spec uses IDs 10+ but the
   actual max in current example_baltic.yaml may be 8 or 9 (Lagoon-strait
   outlet at junction 5, BalticCoast at 6 or 7). Plan task: read the YAML
   and confirm the max before locking 10+.
