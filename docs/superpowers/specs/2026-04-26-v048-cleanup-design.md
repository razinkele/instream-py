# v0.48.0 Cleanup Release — Design Spec

**Date:** 2026-04-26
**Branch base:** `master` at `5a32dfb` (post-v0.47.0 merge)
**Release tag (target):** `v0.48.0`
**Status:** Approved after 8 review loops (Loop 8 verdict: CLEAN AT CRIT/IMP THRESHOLD).

## Goal

Two independent on-disk cleanups bundled into one release. **No simulation behavior change.** Cell counts, smolt outputs, fixture-load semantics, and downstream user APIs are all byte-stable across v0.47.0 → v0.48.0.

1. **Template-residue cleanup** — remove 32 unreferenced prototype Depths/Vels CSVs from the 4 WGBAST fixture directories; teach the wire script to source these from `example_baltic` instead of from each WGBAST fixture's own dir.
2. **Marine-region cache de-dup** — collapse 4 river-keyed marine cache JSONs (3× byte-identical Gulf of Bothnia at 17 MB each + 1× Baltic Sea at 4 MB) into 2 IHO-keyed files. Saves ~34 MB of repo footprint.

## Architecture overview

The two cleanups share the v0.47.0 fixture/cache layer but are otherwise mutually independent. Each ships in its own commit to support clean `git bisect`. A third release commit handles version + CHANGELOG + README + tag.

```
commit 1 — sub-task 1 (residue cleanup)        | git rm 32 CSVs + 2 script edits + 2 new tests
commit 2 — sub-task 2 (cache de-dup)           | git rm 4 caches, git add 2 caches + 1 script edit + 2 new tests
commit 3 — release v0.48.0                     | version bump + CHANGELOG + README + annotated tag
```

## Sub-task 1: Template-residue cleanup

### What's wrong today

Each of the 4 WGBAST fixture directories ships 8 prototype-named CSVs that the simulation never reads:

```
tests/fixtures/example_{tornionjoki,simojoki,byskealven,morrumsan}/
    {Atmata,Minija,Nemunas,Sysa}-Depths.csv
    {Atmata,Minija,Nemunas,Sysa}-Vels.csv
```

That's 4 rivers × 4 prototype names × 2 suffixes = **32 files**. Each fixture's YAML config references only `Mouth/Lower/Middle/Upper/BalticCoast-{Depths,Vels}.csv` — the prototype-named files are template residue inherited from the original Lithuanian `example_baltic` template.

### What stays (and why)

The 16 `{proto}-TimeSeriesInputs.csv` files (4 protos × 4 rivers) are NOT residue. `scripts/_scaffold_wgbast_rivers.py` writes per-river temperature/flow offsets into them after `shutil.copytree`:

| River        | T offset | Q multiplier |
|--------------|----------|--------------|
| Tornionjoki  | −6.0 °C  | × 0.8        |
| Simojoki     | −5.5 °C  | × 0.09       |
| Byskeälven   | −3.5 °C  | × 0.08       |
| Mörrumsån    | +3.0 °C  | × 0.05       |

`_wire_wgbast_physical_configs.py::copy_reach_csvs:276` copies these calibrated files via `shutil.copy2(src_ts, dst_ts)` to `{new_name}-TimeSeriesInputs.csv` — which IS what the simulation loads. Replacing the source with `example_baltic` would silently restore the un-offset Lithuanian baseline, destroying the latitudinal calibration. **Verified by Loop 6** through direct content comparison: `example_baltic/Nemunas-TimeSeriesInputs.csv` line 4 has `temperature=7.6`; `example_tornionjoki/Nemunas-TimeSeriesInputs.csv` line 7 has `temperature=1.6` (the −6 °C offset).

### What changes

**File deletions (32):**

```bash
git rm \
  tests/fixtures/example_tornionjoki/{Atmata,Minija,Nemunas,Sysa}-{Depths,Vels}.csv \
  tests/fixtures/example_simojoki/{Atmata,Minija,Nemunas,Sysa}-{Depths,Vels}.csv \
  tests/fixtures/example_byskealven/{Atmata,Minija,Nemunas,Sysa}-{Depths,Vels}.csv \
  tests/fixtures/example_morrumsan/{Atmata,Minija,Nemunas,Sysa}-{Depths,Vels}.csv
```

**`scripts/_wire_wgbast_physical_configs.py::copy_reach_csvs` line 291**

Before:
```python
for suffix in ("Depths", "Vels"):
    src = fixture_dir / f"{proto}-{suffix}.csv"
    dst = fixture_dir / f"{new_name}-{suffix}.csv"
    _expand_per_cell_csv(src, dst, n_new)
```

After (only `src` line changes, plus a `FileNotFoundError` guard):
```python
for suffix in ("Depths", "Vels"):
    src = ROOT / "tests" / "fixtures" / "example_baltic" / f"{proto}-{suffix}.csv"
    if not src.exists():
        raise FileNotFoundError(
            f"WGBAST wire script source missing: {src}. "
            f"example_baltic is the canonical Lithuanian template — "
            f"did it get cleaned up by mistake?"
        )
    dst = fixture_dir / f"{new_name}-{suffix}.csv"
    _expand_per_cell_csv(src, dst, n_new)
```

Line 276 (`src_ts = fixture_dir / f"{proto}-TimeSeriesInputs.csv"`) is **left unchanged** — calibration must continue to source from each river's own directory.

**`scripts/_scaffold_wgbast_rivers.py` after `shutil.copytree(TEMPLATE, out_dir)`** (around line 68):

```python
# Strip prototype Depths/Vels: the wire script reads these from
# example_baltic directly. Keep PROTO TimeSeriesInputs (Mouth/Lower/
# Middle/Upper sources for per-river T/Q calibration applied below).
# Fully drop FULLY_ORPHAN reaches (Lithuanian distributary names that
# have no WGBAST counterpart) — their TimeSeriesInputs were git-deleted
# in fc08578 (v0.47.0) and must not be re-introduced by re-runs.
PROTO = ("Nemunas", "Atmata", "Minija", "Sysa")
FULLY_ORPHAN = ("Skirvyte", "Leite", "Gilija", "CuronianLagoon")
for proto in PROTO:
    for suffix in ("Depths", "Vels"):
        (out_dir / f"{proto}-{suffix}.csv").unlink(missing_ok=True)
for orphan in FULLY_ORPHAN:
    for suffix in ("Depths", "Vels", "TimeSeriesInputs"):
        (out_dir / f"{orphan}-{suffix}.csv").unlink(missing_ok=True)
```

The `unlink(missing_ok=True)` makes the loop idempotent against already-absent files — required because `FULLY_ORPHAN` files were already removed in v0.47.0 commit `fc08578`.

### Tests added in commit 1

Both extend the existing file `tests/test_wgbast_river_extents.py` (NOT a new file):

**`test_no_orphan_prototype_csvs`** — 80 parametrized cases (4 rivers × (PROTO 4×2 + FULLY_ORPHAN 4×3) = 4 × 20). Asserts each forbidden filename is absent from each fixture directory. Docstring:

> "PROTO cases (32) drive the v0.48.0 cleanup itself. FULLY_ORPHAN cases (48) are trivially-PASS today (v0.47.0 fc08578 already deleted them) but become load-bearing forward regression guards against future re-scaffolds without the deletion loop."

**`test_example_baltic_prototype_csvs_present`** — 8 parametrized cases (4 protos × 2 suffixes). Asserts `tests/fixtures/example_baltic/{proto}-{suffix}.csv` exists. Guards the wire-script source against accidental cleanup.

## Sub-task 2: Marine-region cache de-dup

### What's wrong today

`tests/fixtures/_osm_cache/` ships 4 marine-region cache files keyed by river short_name:

```
example_tornionjoki_marineregions.json    17 MB    Gulf of Bothnia
example_simojoki_marineregions.json       17 MB    Gulf of Bothnia (byte-identical to tornionjoki)
example_byskealven_marineregions.json     17 MB    Gulf of Bothnia (byte-identical to tornionjoki)
example_morrumsan_marineregions.json       4 MB    Baltic Sea
```

Total **~55 MB**, with 34 MB of redundancy (3× duplicate Gulf of Bothnia polygon).

The redundancy is safe to dedup because IHO sea-area polygons returned by Marine Regions WFS are **global features**, not bbox-clipped — `query_named_sea_polygon`'s upstream centroid disambiguation already narrows multi-polygon responses to a single polygon, and that polygon is the same regardless of which river's bbox triggered the query.

### What changes

**Cache rename — git operation explicit:**

The implementer must complete the script changes (helper + 3 update points) FIRST so the regenerator writes to the new IHO-keyed paths. Then:

```bash
# Step 1: remove the 4 old river-keyed caches
git rm \
  tests/fixtures/_osm_cache/example_tornionjoki_marineregions.json \
  tests/fixtures/_osm_cache/example_simojoki_marineregions.json \
  tests/fixtures/_osm_cache/example_byskealven_marineregions.json \
  tests/fixtures/_osm_cache/example_morrumsan_marineregions.json

# Step 2: regenerate. Requires Marine Regions WFS reachability
# (verify with `curl -sf --max-time 30 -o /dev/null -w "%{http_code}\n" \
# "https://geo.vliz.be/geoserver/MarineRegions/wfs?service=WFS&request=GetCapabilities"`
# expecting HTTP 200). The script's first run after the helper change
# writes both new IHO-keyed cache files in one pass through the 4 rivers.
micromamba run -n shiny python scripts/_generate_wgbast_physical_domains.py

# Step 3: stage the 2 new IHO-keyed caches
git add \
  tests/fixtures/_osm_cache/gulf_of_bothnia_marineregions.json \
  tests/fixtures/_osm_cache/baltic_sea_marineregions.json
```

If WFS is unreachable at regen time, defer commit 2 until WFS recovers — the helper change alone (without the new cache files) leaves the regenerator unable to load any sea polygon for fixture work.

**`scripts/_generate_wgbast_physical_domains.py` — new module-level dict and helper:**

Place these after the `RIVERS` list (line 193), before `COLUMN_RENAME` (line ~196). The `BALTICCOAST_*` constants are at lines 71–87 and are deliberately NOT colocated — the new dict references `river.short_name` values that are first introduced by the `RIVERS` list, so it reads better immediately after that list.

```python
# Map each WGBAST river to the IHO sea-area name returned by Marine
# Regions WFS for its mouth bbox. Used to derive a shared cache path —
# rivers in the same IHO area share one cached polygon (saves ~34 MB
# vs the per-river caching scheme used pre-v0.48).
RIVER_TO_IHO_NAME = {
    "example_tornionjoki": "Gulf of Bothnia",
    "example_simojoki":    "Gulf of Bothnia",
    "example_byskealven":  "Gulf of Bothnia",
    "example_morrumsan":   "Baltic Sea",
}


def _marineregions_cache_path(river: "River") -> Path:
    """Return the IHO-keyed cache path for `river`'s sea polygon.

    IHO polygons are sea-level global features (not bbox-clipped), so
    rivers in the same IHO area can share one cache file safely. The
    cache path is derived from `RIVER_TO_IHO_NAME[river.short_name]`
    via lowercase + space-to-underscore slug.

    Raises:
      RuntimeError: if `river.short_name` is not in `RIVER_TO_IHO_NAME`,
        or if the mapped IHO name is empty/whitespace (likely a
        copy-paste error).
    """
    try:
        iho_name = RIVER_TO_IHO_NAME[river.short_name]
    except KeyError:
        raise RuntimeError(
            f"River {river.short_name!r} not in RIVER_TO_IHO_NAME; "
            f"add a mapping in {__file__} before regenerating."
        ) from None
    if not iho_name or not iho_name.strip():
        raise RuntimeError(
            f"RIVER_TO_IHO_NAME[{river.short_name!r}] is empty; "
            f"populate with the IHO sea-area name (e.g. 'Gulf of Bothnia')."
        )
    slug = iho_name.lower().replace(" ", "_")
    return OSM_CACHE / f"{slug}_marineregions.json"
```

**Three update points in `_load_or_fetch_marineregions` and downstream:**

1. **Line 247 (functional cache path)** — currently `cache = OSM_CACHE / f"{river.short_name}_marineregions.json"`. Replace with:
   ```python
   cache = _marineregions_cache_path(river)
   ```
   This is the load-bearing change. Without it, the cache rename produces a permanent cache-miss.

2. **Line 544 (RuntimeError message inside `write_river_shapefile`)** — currently `f"... at tests/fixtures/_osm_cache/{river.short_name}_marineregions.json ..."`. Replace with `_marineregions_cache_path(river)` in the f-string so the error message stays correct after the rename.

3. **Line 238 (docstring of `_load_or_fetch_marineregions`)** — update the path format example to reference `<iho_slug>_marineregions.json` instead of `<short_name>_marineregions.json`.

**Empty-IHO-name guard on cache-miss** — placed on the WFS-fetch branch only (NOT the cache-load branch — an empty-name response would have triggered the guard at first-fetch time and never been written to disk). After the WFS returns a non-empty gdf, but before writing the cache file: if `gdf["name"].iloc[0]` is empty or whitespace, raise:

```python
RuntimeError(
    f"Marine Regions returned a polygon with no name; cannot derive "
    f"cache filename for {river.short_name}. Service may have changed; "
    f"re-run with --refresh and inspect the WFS response."
)
```

This catches the WFS-schema-change scenario where `query_named_sea_polygon` returns its `gdf["name"] = ""` fallback. Caching to `_marineregions.json` (degenerate slug) would silently corrupt cross-river cache sharing.

### Tests added in commit 2

Both extend the existing file `tests/test_marineregions_cache.py` (NOT a new file). The current file imports only from `generate_baltic_example` via a `sys.path.insert(0, SCRIPTS_DIR)`. Both new tests need to import from `_generate_wgbast_physical_domains` (same `scripts/` directory, so the existing `sys.path.insert` already works). Add the module-level import at the top of the file (avoids re-importing on every parametrized case):

```python
from _generate_wgbast_physical_domains import (
    _marineregions_cache_path,
    RIVERS,
)
```

(The leading-underscore module name is importable normally; the underscore is a project convention for "internal CLI script", not a package-private marker.)

The existing module docstring of `tests/test_marineregions_cache.py` reads `"""Tests for the Marine Regions cache+fetch helper inside generate_baltic_example.py."""` — update it to also mention `_generate_wgbast_physical_domains`, e.g. `"""Tests for the Marine Regions cache+fetch helpers (generate_baltic_example.py + _generate_wgbast_physical_domains.py)."""`.

**`test_marineregions_cache_path_returns_iho_keyed_path`** — 4 parametrized cases. For each WGBAST river, asserts `_marineregions_cache_path(river).name` equals the expected IHO-keyed filename (3 → `gulf_of_bothnia_marineregions.json`, 1 → `baltic_sea_marineregions.json`). Catches typos in the slug derivation.

**`test_iho_cache_paths_collapse_to_unique_slugs`** — single test, set-equality assertion:
```python
paths = {_marineregions_cache_path(r).name for r in RIVERS}
assert paths == {
    "gulf_of_bothnia_marineregions.json",
    "baltic_sea_marineregions.json",
}, f"Unique IHO cache filenames drifted: {paths}"
```
Catches "added a 5th river but `RIVER_TO_IHO_NAME` slug is wrong".

## Release commit (commit 3)

- Bump `pyproject.toml` `version` from `0.47.0` to `0.48.0`.
- Bump `src/salmopy/__init__.py` `__version__` from `"0.47.0"` to `"0.48.0"`.
- Prepend CHANGELOG entry under `## [0.48.0] — 2026-04-26` with these subsections (matches v0.47.0's `### Internal changes` precedent at CHANGELOG line 111):

  ```markdown
  ## [0.48.0] — 2026-04-26

  ### Internal changes — repo cleanup

  No simulation behavior change, no breaking change for downstream users.

  - Deleted 32 prototype Depths/Vels CSVs from 4 WGBAST fixture directories
    (`{Atmata,Minija,Nemunas,Sysa}-{Depths,Vels}.csv`). Wire script now
    sources these from `example_baltic` directly. The 16
    `{proto}-TimeSeriesInputs.csv` files are kept (per-river T/Q calibration).
  - De-duplicated 4 marine-region cache files to 2 IHO-keyed files
    (`gulf_of_bothnia_marineregions.json` + `baltic_sea_marineregions.json`).
    Saves ~34 MB of repo footprint. New helper
    `_marineregions_cache_path(river)` centralises the IHO-name lookup +
    path derivation.
  - Both cleanups protected by new regression tests
    (`test_no_orphan_prototype_csvs`, `test_example_baltic_prototype_csvs_present`,
    `test_marineregions_cache_path_returns_iho_keyed_path`,
    `test_iho_cache_paths_collapse_to_unique_slugs`).

  ### Required dependency

  No new dependencies; floors unchanged from v0.47.0.

  ### Verified

  All 80 + 8 + 4 + 1 new test cases PASS. Pre-existing tests unchanged
  (no behavior change).
  ```

- README: append a sentence after the v0.47.0 BalticCoast paragraph in the WGBAST section:

  > **v0.48.0:** prototype-named Depths/Vels CSVs (Atmata/Minija/Nemunas/Sysa) removed from WGBAST fixture directories — the wire script now reads these from `example_baltic` directly. Marine-region caches de-duplicated to two IHO-keyed files (saves ~34 MB).

- Annotated tag:
  ```bash
  git tag -a v0.48.0 -m "v0.48.0: cleanup release — template-residue + marine cache de-dup"
  ```

## Error handling

All new error paths surface as `RuntimeError` with actionable text:

| Source | Trigger | Message hint |
|---|---|---|
| `_marineregions_cache_path` | River missing from `RIVER_TO_IHO_NAME` | "add a mapping in this file before regenerating" |
| `_marineregions_cache_path` | Empty IHO name string | "populate with the IHO sea-area name" |
| `_load_or_fetch_marineregions` | WFS returns polygon with no name | "service may have changed; re-run with --refresh" |
| `copy_reach_csvs:291` | `example_baltic/{proto}-{suffix}.csv` missing | "did example_baltic get cleaned up by mistake?" |

## Testing strategy

- **No new behavior**, no new simulation tests.
- 4 new test functions, 93 new test cases total (80 + 8 + 4 + 1).
- Tests partitioned across two existing test files (one per sub-task) so each commit is independently green:
  - Commit 1 tests in `tests/test_wgbast_river_extents.py` (no import dependency on commit 2's helper).
  - Commit 2 tests in `tests/test_marineregions_cache.py` (extend the existing file by appending).
- Existing tests verified to remain green: 25 fixture-shape regression cases (`test_wgbast_river_extents.py`) + 4 fixture-load cases (`test_multi_river_baltic.py::test_fixture_loads_and_runs_3_days`) + 8 marine helper cases (`test_create_model_marine.py`) + 9 river helper cases (`test_create_model_river.py`) + 2 marine-cache cases (`test_marineregions_cache.py`) + the rest of the suite.

## Out of scope

These follow-ups are explicitly deferred per the brainstorming session decision (option C from earlier discussion):

- **v0.49.0**: PR-4 — fix `create_model_export.py::export_template_csvs` CSV format mismatch.
- **v0.50.0**: PR-3 — Create Model UI buttons consuming the `app/modules/create_model_marine.py` and `create_model_river.py` helpers.
- **Future cleanup**: marine cache polygon simplification (`shapely.simplify(0.0001)`) — could shrink Gulf of Bothnia 5-10× more but would shift BalticCoast cell counts at the coastline, requiring fixture regeneration. Deferred to keep v0.48.0 byte-stable for cell counts.

## Approval

8 review loops completed (Loops 1-8). Final verdict: CLEAN AT CRIT/IMP THRESHOLD. User approved at brainstorm conclusion.
