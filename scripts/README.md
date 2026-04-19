# scripts/

Utility scripts that sit outside the package (`src/instream/`) and
the test suite (`tests/`). Two categories by filename prefix.

## Public scripts (no prefix)

Run these directly — they're the stable entry points for case-study
generation, benchmarking, and release ops.

| File | Purpose |
|---|---|
| `generate_baltic_example.py` | Regenerate the Baltic case-study fixtures from OSM + EMODnet. Produces `tests/fixtures/example_baltic/`. |
| `generate_analytical_reference.py` | Generate deterministic-function NetLogo reference outputs for `tests/fixtures/reference/`. |
| `generate_subdaily_fixture.py` | Build sub-daily example fixtures. |
| `bench_3yr.py` | 3-year headless benchmark (complements `benchmarks/bench_baltic.py`). |
| `diagnose_kelt.py` | KELT-chain lifecycle diagnostic. |
| `test_parr_growth_rate.py` | Standalone PARR growth sanity check. |
| `release.py` | Release automation (tag + push). |

## Internal tools (`_*` prefix)

**Convention:** Scripts with a leading underscore are *internal*:
one-shot probes, regenerator hooks called by other scripts, or
long-lived diagnostic tools invoked by hand when a specific bug class
recurs. They are NOT entry points a casual user should run.

Subcategories:

### `_fetch_*` — one-time data cache fetchers

These hit external services (OSM Nominatim, Lithuania PBF via osmium)
and write a cached artefact to `app/data/marineregions/`. Run once
per data source; the outputs are committed to the repo. Do NOT rerun
for every generator invocation.

| File | Produces | Source |
|---|---|---|
| `_fetch_curonian_lagoon_osm.py` | `curonian_lagoon.geojson` | OSM relation 7546467 via Nominatim |
| `_fetch_curonian_spit_osm.py` | `curonian_spit.geojson` | OSM relation 309762 via Nominatim |
| `_fetch_lithuania_coastline.py` | `lithuania_coastline.geojson` + `lithuania_land_real.geojson` | `natural=coastline` from cached Lithuania PBF |

### `_audit_*` — geometry sanity checks

Post-regeneration QA. Each reads the current `BalticExample.shp`
fixture and prints structural summaries. Safe to rerun anytime.

| File | Purpose |
|---|---|
| `_audit_reach_centroids.py` | Per-reach centroid + bbox span + distance-to-Klaipėda audit. Flags reaches that drift outside the salmon-relevant area. |
| `_audit_baltic_geometry.py` | Sentinel-point geometry audit (reaches-that-should-contain / reaches-that-shouldn't). |

### `_probe_*` — investigative probes

These were written to answer specific questions during development.
Most are still useful if the same question comes up again; a few
are effectively one-shot archaeology. Listed with their current
value rating.

| File | Rating | Purpose |
|---|---|---|
| `_probe_connectivity.py` | **Keep** | Inter-reach cell-grid distance probe with documented-gap classification. Mirrored by `tests/test_baltic_geometry.py`. |
| `_probe_atmata.py` | **Keep** | Per-reach OSM feature + width audit; flags linestring-only reaches needing tighter `BUFFER_FACTOR`. |
| `_probe_emodnet.py` | Keep | EMODnet WCS probe — useful when bathymetry fetch misbehaves. |
| `_probe_marineregions.py` | Keep | Marine Regions WFS probe — useful if the lagoon polygon source changes. |
| `_probe_kaliningrad.py` | Keep | Kaliningrad PBF extraction smoke test. |
| `_probe_gilija.py` | One-shot | Gilija / Матросовка feature resolution; answered during v0.30.0 upgrade. |
| `_probe_lagoon.py` | One-shot | Lagoon polygon comparison; answered during v0.30.1 upgrade. |
| `_probe_baltic_osm.py` | One-shot | Initial Baltic OSM scoping. |
| `_probe_osmium_optional.py` | One-shot | Osmium-optional-import pathway probe; captured in `app/modules/create_model_osm.py` structure. |

### `_diag_*` — diagnostic walkers

Used when a specific pipeline silently under-produces. Referenced in
`docs/case-studies/baltic-workflow.md` Gotcha 8.

| File | Purpose |
|---|---|
| `_diag_spawn_pipeline.py` | Walk each spawn-pipeline gate (ready_to_spawn, cell lookup, suitability tolerance, defense exclusion, create_redd). Reports per-gate drop counts. Used to diagnose the v0.30.0→v0.30.2 `frac_spawn=0` silent-failure bug. |

### `_inspect_*` — quick column/schema audits

| File | Purpose |
|---|---|
| `_inspect_baltic_shp_columns.py` | DBF column range audit for `BalticExample.shp`. Referenced in Gotcha 8. |

### `_test_*` — in-place hypothesis tests

| File | Purpose |
|---|---|
| `_test_fracspawn_hypothesis.py` | Phase-3 systematic-debugging hypothesis test. Patches the Baltic shapefile's FRACSPWN column in-place, runs a 220-day sim, reports redd count, restores backup. Used to confirm the v0.30.2 fix would work before applying it. Safe to rerun; has try/finally backup restore. |

## When to add a script vs a `tests/` module vs an `src/` module

| Goal | Destination |
|---|---|
| One-time data regeneration | `scripts/generate_*.py` |
| One-shot curiosity / debugging | `scripts/_probe_*.py` |
| Permanent pipeline gate walker | `scripts/_diag_*.py` (keep) |
| Assertion-based regression guard | `tests/test_*.py` |
| Reusable model logic | `src/instream/` |
| Reusable app logic | `app/modules/` |

A `_probe_*.py` can graduate to `_audit_*.py` or into the test
suite once the question it answered becomes a recurring concern.
Consider that promotion before writing a new probe from scratch.
