# Baltic Case Study — Real-Data Upgrades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three remaining approximations in the Baltic case study — hand-traced Curonian Lagoon polygon, synthetic per-flow depths, Lithuania-only OSM PBF — with authoritative real-world data from Marine Regions, EMODnet Bathymetry, and the Kaliningrad OSM PBF.

**Architecture:** Three independent sub-projects, each producing a commit-ready change on its own. Sub-project 1 (Marine Regions) is quick and unblocks Sub-project 2 (EMODnet bathymetry) because real depths need the real lagoon footprint. Sub-project 3 (Kaliningrad PBF merge) is an independent data-pipeline upgrade that also retroactively fixes the Curonian Lagoon OSM multipolygon relation — so if #3 ships, #1's polygon becomes a fallback rather than the primary path.

**Recommended execution order:** 1 → 3 → 2. This is why:
- Sub-project 1 is ~30 min, simple HTTP + cache. Ships a real lagoon polygon fast.
- Sub-project 3 is ~2 h, touches the OSM fetch pipeline. May obsolete #1 (if so, demote #1's code path to fallback) and also unlocks the Gilija / Matrosovka delta branches.
- Sub-project 2 is ~3 h, depends on having the correct lagoon footprint (for sampling bathy inside it) — so it benefits from running last.

**Tech Stack:** Python 3.13, geopandas, shapely, pyosmium (OSM), rasterio (already present in `shiny` 1.5.0), requests. Conda env `shiny`.

**Test command:** `micromamba run -n shiny python -m pytest tests/test_model.py::test_adult_arrives_as_returning_adult tests/test_create_model_grid.py tests/test_app_smoke.py -v --tb=short`

**Baseline commit:** `046206d feat: Baltic case study uses real OSM geometry + hand-traced lagoon outline`

**Shell convention:** all `rm -rf` / `cp -r` / `ls` commands assume git-bash (Windows 11 default per CLAUDE.md). PowerShell users swap to `Remove-Item -Recurse -Force`, `Copy-Item -Recurse`, `Get-ChildItem`. No commands use bash-only syntax beyond these primitives.

**Rollback strategy:** Each sub-project's commits are atomic. If a sub-project aborts mid-execution:
- Staged-but-uncommitted edits: `git restore .` (scoped to touched files listed in each Task's `git add` step)
- Untracked probe scripts: `git clean -fd scripts/_probe_*.py`
- EMODnet cache (large, gitignored): `rm -rf app/data/emodnet/` (re-downloaded on next run)
- Marine Regions cache (small, committed): leave committed — it's useful as offline fallback regardless of OSM merge outcome

---

## File Map

| File | Sub-project | Changes |
|------|-----|---------|
| `scripts/generate_baltic_example.py` | 1 | `fetch_curonian_lagoon()` rewritten to fetch MRGID 3642 polygon from Marine Regions; cached to `app/data/marineregions/` |
| `app/data/marineregions/curonian_lagoon.geojson` | 1 | New — cached Marine Regions polygon (committed) |
| `tests/test_marineregions_cache.py` | 1 | New — 2 unit tests for the fetcher |
| `app/modules/create_model_osm.py` | 3 | `ensure_pbf`, `_clip_pbf`, `_extract_hydro`, `query_waterways`, `query_water_bodies` accept list of regions; internal caching keyed on region-set hash |
| `scripts/generate_baltic_example.py` | 3 | Fetchers call with `("lithuania", "kaliningrad")`; add `Gilija` reach (real OSM name "Матросовка" or "Gilija", whichever present) |
| `configs/example_baltic.yaml` | 3 | Add `Gilija` reach block |
| `tests/test_create_model_osm.py` | 3 | New test: multi-region merge assembles a border-spanning feature |
| `app/modules/bathymetry.py` | 2 | New — `fetch_emodnet_dtm(bbox)` + `sample_depth(gdf, dtm_path)` |
| `scripts/generate_baltic_example.py` | 2 | `generate_hydraulics()` for `CuronianLagoon` + `BalticCoast` samples EMODnet per cell, keeps per-flow scaling |
| `app/data/emodnet/` | 2 | New cache dir for downloaded GeoTIFF (gitignored — it's 50-200 MB) |
| `.gitignore` | 2 | Add `app/data/emodnet/*.tif` |
| `tests/test_bathymetry.py` | 2 | New — 4 unit tests covering cache key, sign-flip sampling, land clamp, missing-file error |
| `environment.yml` or `pyproject.toml` | 2 | Add `rasterio` (conda-forge) |

---

## Sub-project 1: Curonian Lagoon polygon via Marine Regions

**Why:** The current hand-traced 18-coord polygon reports 2 585 km² — 63 % larger than the real 1 584 km² lagoon. Marine Regions gazetteer MRGID 3642 publishes the authoritative polygon.

**Approach:** Fetch once via the Marine Regions WFS (`https://geo.vliz.be/geoserver/MarineRegions/wfs`), cache to a tracked GeoJSON, reuse on subsequent generator runs. If the API is down, fall back to the hand-traced polygon with a WARN log.

**NB on API endpoints (verified 2026-04-18):**
- The REST endpoint `rest/getGazetteerGeometries.json/<MRGID>/` returns **404** — *do not* use it. The earlier plan draft called this endpoint; it's dead.
- `rest/getGazetteerRecordsByName.json/<name>/` works for discovery (returned MRGID 3642 for "Curonian Lagoon").
- `rest/getGazetteerRecordByMRGID.json/<MRGID>/` returns metadata (lat/lon center, bbox) but **not** polygon geometry.
- Polygon geometry is only reliably available via **WFS**. Multiple typeNames may host it — probe several in sequence (Task 1.1 Step 2 lists the candidates).

### Task 1.1: Probe Marine Regions API to verify MRGID and geometry

**Files:**
- Create: `scripts/_probe_marineregions.py`

- [ ] **Step 1: Write the probe script**

```python
"""Probe Marine Regions WFS to find a typeName that returns Curonian Lagoon
(MRGID 3642) as a polygon.

NB — REST geometry endpoints (`getGazetteerGeometries.json/<MRGID>/`) returned
404 during plan review (2026-04-18). Use WFS at geo.vliz.be instead.
"""
from __future__ import annotations

import json
import requests

WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"
MRGID = 3642  # Curonian Lagoon (verified via getGazetteerRecordsByName.json)

# Marine Regions hosts many polygon layers. Probe these in order; record the
# first that returns a non-empty FeatureCollection for our MRGID.
TYPE_NAMES = [
    "MarineRegions:iho",
    "MarineRegions:iho_v3",
    "MarineRegions:eez_iho_union_v2",
    "MarineRegions:goas",
    "MarineRegions:marbound",
    "MarineRegions:gaz_records",
]


def main() -> None:
    for tn in TYPE_NAMES:
        params = {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": tn,
            "cql_filter": f"MRGID={MRGID}",
            "outputFormat": "application/json",
            "count": "1",
        }
        try:
            resp = requests.get(WFS, params=params, timeout=30)
        except Exception as exc:
            print(f"{tn}: FAIL ({exc})")
            continue
        print(f"{tn}: HTTP {resp.status_code}")
        if resp.status_code != 200:
            continue
        try:
            data = resp.json()
        except Exception:
            continue
        feats = data.get("features", [])
        if feats:
            print(f"  -> {len(feats)} feature(s), geom type: "
                  f"{feats[0].get('geometry', {}).get('type', '?')}")
            print("  first 200 chars of geometry JSON:")
            print("  " + json.dumps(feats[0].get("geometry"))[:200])
            return
    print(f"No typeName returned MRGID {MRGID}.")
    print("Fallback: download shapefile manually from "
          f"https://marineregions.org/gazetteer.php?p=details&id={MRGID}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the probe**

```bash
micromamba run -n shiny python scripts/_probe_marineregions.py
```

Expected: one `MarineRegions:...` line prints `-> 1 feature(s), geom type: MultiPolygon` (or `Polygon`). Record that typeName — you'll hardcode it as `MARINEREGIONS_TYPENAME` in Task 1.2. If *every* candidate returns 0 features, follow the printed fallback instructions (download the Marine Regions shapefile manually from the gazetteer detail page and commit the GeoJSON at `app/data/marineregions/curonian_lagoon.geojson`; Task 1.2's cache-first logic will use it).

- [ ] **Step 3: Do NOT commit the probe script** — it lives for diagnostic value only, underscore-prefixed so pytest skips it. Add to `.gitignore` if you want it purged: `scripts/_probe_*.py`.

---

### Task 1.2: Write the Marine Regions fetcher + cache

**Files:**
- Modify: `scripts/generate_baltic_example.py` (replace `fetch_curonian_lagoon()`)
- Create: `app/data/marineregions/` (new cache dir)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_marineregions_cache.py
"""Tests for the Marine Regions cache+fetch helper inside generate_baltic_example.py."""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

# Import the generator module; function name follows the existing pattern.
from generate_baltic_example import fetch_curonian_lagoon, CURONIAN_CACHE_PATH  # noqa: E402


def test_fetch_curonian_lagoon_uses_cache(monkeypatch, tmp_path):
    """If the cache file exists, fetch_curonian_lagoon must NOT hit the network."""
    monkeypatch.setattr("generate_baltic_example.CURONIAN_CACHE_PATH", tmp_path / "lagoon.geojson")
    # Seed cache with a valid tiny polygon
    import geopandas as gpd
    from shapely.geometry import Polygon
    poly = Polygon([(21.0, 55.2), (21.3, 55.2), (21.3, 55.5), (21.0, 55.5), (21.0, 55.2)])
    gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326").to_file(
        tmp_path / "lagoon.geojson", driver="GeoJSON"
    )
    # Monkeypatch requests.get to fail — cache path must not call it.
    import requests

    def fail(*_args, **_kwargs):
        raise AssertionError("network hit when cache exists")
    monkeypatch.setattr(requests, "get", fail)

    result = fetch_curonian_lagoon()
    assert result.geom_type in ("Polygon", "MultiPolygon")
    assert result.area > 0


def test_fetch_curonian_lagoon_falls_back_on_http_error(monkeypatch, tmp_path):
    """If the cache is missing AND the API fails, return the hand-traced fallback
    with a WARN log — must not raise."""
    monkeypatch.setattr("generate_baltic_example.CURONIAN_CACHE_PATH", tmp_path / "missing.geojson")
    import requests

    class FakeResponse:
        status_code = 503

        def raise_for_status(self):
            raise requests.HTTPError("Service Unavailable")

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())
    result = fetch_curonian_lagoon()
    # Fallback returns ~2585 km² hand-traced polygon; any valid Polygon is fine
    assert result.geom_type == "Polygon"
    assert result.area > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
micromamba run -n shiny python -m pytest tests/test_marineregions_cache.py -v --tb=short
```

Expected: FAIL on `ImportError: cannot import name 'CURONIAN_CACHE_PATH'` (symbol doesn't exist yet).

- [ ] **Step 3: Confirm generator's existing imports**

The replacement in Step 4 uses `requests`, `shape` (from shapely.geometry), `unary_union`, `make_valid`, `gpd`, `Polygon`, and `_log`. Open `scripts/generate_baltic_example.py` and verify every one is already imported at module top. At the baseline commit `046206d` all seven ARE present — if anything is missing at execution time, add the import before the replacement.

Quick check command:

```bash
grep -nE "^import|^from" scripts/generate_baltic_example.py | head -20
```

Expected to see: `import requests`, `from shapely.geometry import Point, Polygon, box, shape`, `from shapely.ops import unary_union`, `from shapely.validation import make_valid`, `import geopandas as gpd`, plus the local `_log` helper defined later in the file.

- [ ] **Step 4: Implement fetcher + cache in generate_baltic_example.py**

Replace the existing `fetch_curonian_lagoon()` (at **line 195** in baseline commit `046206d`; grep for `^def fetch_curonian_lagoon` to confirm before patching) with:

```python
# Near the top-level constants block (after BBOX / RIVER_CLIP_BBOX):
CURONIAN_CACHE_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "marineregions" / "curonian_lagoon.geojson"
CURONIAN_MRGID = 3642  # Marine Regions gazetteer ID for Kuršių marios
MARINEREGIONS_WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"
# Set to the typeName that the Task 1.1 probe reported as returning
# MRGID 3642. Task 1.1's probe prints the first-working typeName. If this
# constant is WRONG at run time, the WFS returns 0 features and the hand-
# traced fallback kicks in automatically — no NotImplementedError needed;
# the fallback chain is maximally robust by design.
MARINEREGIONS_TYPENAME = "MarineRegions:iho"  # UPDATE after probe (comment only — no fail-fast)


def _fetch_curonian_from_marineregions() -> object | None:
    """Try to fetch the Curonian Lagoon polygon from Marine Regions WFS.
    Returns None on any failure so the caller can fall back."""
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": MARINEREGIONS_TYPENAME,
        "cql_filter": f"MRGID={CURONIAN_MRGID}",
        "outputFormat": "application/json",
    }
    try:
        resp = requests.get(MARINEREGIONS_WFS, params=params, timeout=60)
        resp.raise_for_status()
    except Exception as exc:
        print(f"  WARN: Marine Regions fetch failed ({exc}); using fallback", flush=True)
        return None

    try:
        data = resp.json()
    except Exception as exc:
        print(f"  WARN: Marine Regions response not JSON ({exc}); using fallback", flush=True)
        return None

    feats = data.get("features", [])
    geoms: list = []
    for f in feats:
        g = f.get("geometry")
        if g is None:
            continue
        geom = shape(g)
        if not geom.is_valid:
            geom = make_valid(geom)
        geoms.append(geom)
    if not geoms:
        print(f"  WARN: Marine Regions returned 0 features for MRGID={CURONIAN_MRGID}; "
              f"using fallback", flush=True)
        return None
    return unary_union(geoms)


def _write_curonian_cache(geom) -> None:
    CURONIAN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326").to_file(
        CURONIAN_CACHE_PATH, driver="GeoJSON"
    )


def _fallback_curonian_polygon() -> object:
    """18-coord hand-traced polygon (pre-2026-04-18 implementation, kept as fallback)."""
    lagoon_coords = [
        (21.128, 55.720), (21.155, 55.620), (21.300, 55.480),
        (21.340, 55.350), (21.260, 55.240), (21.220, 55.100),
        (21.150, 54.950), (21.050, 54.810), (20.900, 54.720),
        (20.640, 54.715), (20.520, 54.780), (20.570, 54.900),
        (20.740, 55.080), (20.890, 55.250), (20.990, 55.430),
        (21.050, 55.580), (21.095, 55.680), (21.128, 55.720),
    ]
    return Polygon(lagoon_coords)


def fetch_curonian_lagoon() -> object:
    """Return the Curonian Lagoon polygon. Cache-first, Marine-Regions WFS next,
    hand-traced fallback last. Published authority: MRGID 3642."""
    if CURONIAN_CACHE_PATH.exists():
        _log(f"Loading cached Curonian Lagoon polygon from {CURONIAN_CACHE_PATH.name}...")
        gdf = gpd.read_file(CURONIAN_CACHE_PATH)
        return gdf.geometry.iloc[0]

    _log(f"Fetching Curonian Lagoon from Marine Regions WFS (MRGID {CURONIAN_MRGID})...")
    geom = _fetch_curonian_from_marineregions()
    if geom is None:
        _log("Using hand-traced fallback polygon...")
        geom = _fallback_curonian_polygon()
    else:
        _write_curonian_cache(geom)
        _log(f"  Cached to {CURONIAN_CACHE_PATH}")

    area_km2 = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326").to_crs(
        "EPSG:32634"
    ).geometry.iloc[0].area / 1e6
    _log(f"  CuronianLagoon: {geom.geom_type} area={area_km2:.0f} km² (real ~1,584 km²)")
    return geom
```

- [ ] **Step 5: Run tests, expect pass**

```bash
micromamba run -n shiny python -m pytest tests/test_marineregions_cache.py -v --tb=short
```

Expected: 2 passed.

---

### Task 1.3: Run the generator once to populate the cache

- [ ] **Step 1: Delete the old cache if present (first-run case)**

```bash
rm -f "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py/app/data/marineregions/curonian_lagoon.geojson"
```

- [ ] **Step 2: Run generator to hit Marine Regions and write the cache**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
micromamba run -n shiny python scripts/generate_baltic_example.py 2>&1 | tail -20
```

Expected log line: `Fetching Curonian Lagoon polygon from Marine Regions (MRGID 3642)...` followed by `Cached to ...curonian_lagoon.geojson` and an area readout close to `1584 km²` (within ±10 %).

- [ ] **Step 3: Verify cache file exists and is valid**

```bash
ls -la "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py/app/data/marineregions/curonian_lagoon.geojson"
micromamba run -n shiny python -c "import geopandas as gpd; g = gpd.read_file('app/data/marineregions/curonian_lagoon.geojson'); print(g.geometry.iloc[0].geom_type, g.to_crs('EPSG:32634').area.iloc[0] / 1e6, 'km²')"
```

Expected: a GeoJSON file of ~50–500 kB, printing `Polygon ~1584 km²` (or close).

---

### Task 1.4: Regenerate fixtures + run Baltic model test

- [ ] **Step 1: Sync fixtures to app/data**

```bash
rm -rf "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py/app/data/fixtures/example_baltic"
cp -r "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py/tests/fixtures/example_baltic" "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py/app/data/fixtures/example_baltic"
```

- [ ] **Step 2: Run Baltic end-to-end model test**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
micromamba run -n shiny python -m pytest tests/test_model.py::test_adult_arrives_as_returning_adult -v --tb=short
```

Expected: PASSED in ~150–200 s.

---

### Task 1.5: Commit

- [ ] **Step 1: Stage files**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
git add scripts/generate_baltic_example.py tests/test_marineregions_cache.py
git add app/data/marineregions/curonian_lagoon.geojson
git add tests/fixtures/example_baltic app/data/fixtures/example_baltic
git add -u tests/fixtures/example_baltic app/data/fixtures/example_baltic
```

- [ ] **Step 2: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat: fetch Curonian Lagoon polygon from Marine Regions (MRGID 3642)

Replaces the 18-coord hand-traced polygon (2585 km², ~63% too large) with
the authoritative polygon from Marine Regions gazetteer entry 3642 via
the WFS endpoint at geo.vliz.be/geoserver/MarineRegions/wfs.

Fetch priority: cache file (if present) -> Marine Regions WFS ->
hand-traced fallback. On the success path, the WFS polygon is cached to
app/data/marineregions/curonian_lagoon.geojson; on failure paths nothing
is written and the hand-traced polygon is returned with a WARN log. If
this commit is made without a successful live fetch, the cache file is
the hand-traced polygon (Task 1.3 will print which path ran).

Two unit tests cover cache-hit and API-failure paths.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Sub-project 3: Kaliningrad PBF merge

**Why:** The Curonian Lagoon's OSM relation spans the Lithuania-Russia border; pyosmium's single-PBF multipolygon assembly silently drops it. Same issue blocks Gilija (Матросовка), a real southern Nemunas-delta branch on the Kaliningrad side.

**Approach:** Accept a *list* of Geofabrik regions in the OSM fetchers. Download each PBF independently, then run pyosmium across all of them so multipolygon relations see every ring. No merge step needed — pyosmium handlers can process multiple files in sequence and accumulate rows.

### Task 3.1: Verify osmium CLI + pyosmium multi-file reader

**Files:**
- Create: `scripts/_probe_kaliningrad.py`

- [ ] **Step 1: Write the probe**

```python
"""Verify pyosmium can handle multiple PBFs in sequence, and Kaliningrad PBF exists."""
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

from modules.create_model_osm import ensure_pbf, GEOFABRIK_REGIONS  # noqa: E402

assert "kaliningrad" in GEOFABRIK_REGIONS, "kaliningrad region must be registered"
print("Geofabrik URL:", GEOFABRIK_REGIONS["kaliningrad"])

# Download both PBFs (idempotent)
for country in ("lithuania", "kaliningrad"):
    pbf = ensure_pbf(country)
    print(f"{country}: {pbf} ({pbf.stat().st_size / 1_000_000:.1f} MB)")

# Test that pyosmium can apply_file() twice — each call processes one PBF
import osmium
class CountingHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.n = 0

    def way(self, w):
        self.n += 1

h = CountingHandler()
h.apply_file(str(ensure_pbf("lithuania")))
lt = h.n
h.apply_file(str(ensure_pbf("kaliningrad")))
total = h.n
print(f"Lithuania ways: {lt}, +Kaliningrad ways: {total - lt}, total: {total}")
```

- [ ] **Step 2: Run the probe**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
micromamba run -n shiny python scripts/_probe_kaliningrad.py
```

Expected: Kaliningrad PBF downloads (~30–80 MB), both apply_file calls succeed, total ways > Lithuania ways alone. If pyosmium throws on the second apply_file, a new handler instance must be created per file — update the probe and note that constraint in Task 3.2.

---

### Task 3.2: Multi-region support in create_model_osm.py

**Files:**
- Modify: `app/modules/create_model_osm.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_create_model_osm.py — append to existing file
def test_query_waterways_accepts_multi_region(tmp_path):
    """query_waterways should accept a tuple of regions and return features from all."""
    from modules.create_model_osm import query_waterways
    bbox = (20.80, 54.90, 22.20, 55.95)  # spans LT + Kaliningrad

    # Single region
    lt_only = query_waterways("lithuania", bbox)
    # Both regions
    both = query_waterways(("lithuania", "kaliningrad"), bbox)

    assert len(both) > len(lt_only), (
        f"Expected merged fetch to have more features than LT alone: "
        f"{len(both)} vs {len(lt_only)}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
micromamba run -n shiny python -m pytest tests/test_create_model_osm.py::test_query_waterways_accepts_multi_region -v
```

Expected: FAIL because `query_waterways` currently rejects tuples (tries to use as country name).

- [ ] **Step 3: Fix `_clip_pbf` cache key first (pre-existing bug)**

`_clip_pbf` currently caches clipped PBFs by **bbox hash only** (line 168: `bbox_hash = hashlib.md5(bbox_str.encode()).hexdigest()[:12]`). When Task 3.2 adds multi-region support, the second call — Kaliningrad.pbf + same bbox — would return Lithuania's already-cached clip. Fix first:

```python
# In app/modules/create_model_osm.py:_clip_pbf, replace lines 167-169:
# NB use .name (full basename) not .stem — Path.stem strips only the last
# suffix, so lithuania.osm.pbf has stem "lithuania.osm" which happens to
# differ from kaliningrad.osm.pbf today but relies on a Path quirk. .name
# is collision-proof.
cache_key = f"{pbf_file.name}|{bbox_str}"
cache_hash = hashlib.sha1(cache_key.encode(), usedforsecurity=False).hexdigest()[:12]
clipped = _OSM_DIR / f"clip_{cache_hash}.osm.pbf"
```

This keys the clip cache on the full PBF basename plus the bbox, and opportunistically switches `hashlib.md5` → `hashlib.sha1(..., usedforsecurity=False)` for FIPS compatibility.

- [ ] **Step 4: Refactor to accept tuples**

In `app/modules/create_model_osm.py`, change the three public fetchers. Near line 95 (after `geofabrik_url` helper), add:

```python
from typing import Iterable  # add to imports if not already present


def _normalize_regions(countries: str | Iterable[str]) -> tuple[str, ...]:
    """Accept str or iterable of str; return tuple."""
    if isinstance(countries, str):
        return (countries,)
    return tuple(countries)
```

Modify `ensure_pbf`, `_clip_pbf`, `_extract_hydro`, `query_waterways`, `query_water_bodies` so `country` param becomes `countries: str | Iterable[str]`. Core change in `_extract_hydro` — apply handler to each PBF:

```python
def _extract_hydro(
    pbf_files: list[Path],
    progress_cb: Optional[Callable[[str], None]] = None,
) -> tuple[list, list]:
    """Accept one or many PBFs. Cache key is sorted tuple of paths.

    NB: the existing cache is intentionally size-1 ("keep only the most recent
    entry to bound memory" per the original code comment). We preserve that
    behavior — if you need multi-entry caching, change _hydro_cache to an LRU
    and update this function separately.
    """
    key = tuple(sorted(str(p) for p in pbf_files))
    if key in _hydro_cache:
        return _hydro_cache[key]
    if progress_cb:
        progress_cb(f"Extracting hydrology features from {len(pbf_files)} PBF(s)...")
    handler = _HydroHandler()
    for p in pbf_files:
        handler.apply_file(str(p), locations=True)
    result = (handler.waterway_rows, handler.water_body_rows)
    _hydro_cache.clear()  # size-1 cache (see docstring above)
    _hydro_cache[key] = result
    return result
```

And `query_waterways` / `query_water_bodies` become:

```python
def query_waterways(
    countries: str | Iterable[str],
    bbox_wgs84: tuple[float, float, float, float],
    progress_cb: Optional[Callable[[str], None]] = None,
) -> gpd.GeoDataFrame:
    regions = _normalize_regions(countries)
    clipped_files = []
    for r in regions:
        pbf = ensure_pbf(r, progress_cb)
        clipped_files.append(_clip_pbf(pbf, bbox_wgs84, progress_cb))
    ww_rows, _ = _extract_hydro(clipped_files, progress_cb)
    return _rows_to_gdf(ww_rows, "waterway")
```

(`query_water_bodies` mirrors this.)

(`from typing import Iterable` was already added at the top of `_normalize_regions` above — confirm it's in the import block.)

- [ ] **Step 5: Run test to verify it passes**

```bash
micromamba run -n shiny python -m pytest tests/test_create_model_osm.py::test_query_waterways_accepts_multi_region -v
```

Expected: PASS. If the Curonian Lagoon still doesn't appear in `query_water_bodies` even with merged PBFs, log it — may need a pyosmium workaround (see Task 3.4).

- [ ] **Step 6: Commit this slice separately**

```bash
git add app/modules/create_model_osm.py tests/test_create_model_osm.py
git commit -m "feat: create_model_osm fetchers accept multiple Geofabrik regions

- ensure_pbf / _clip_pbf / _extract_hydro / query_waterways / query_water_bodies
  all accept str or Iterable[str]
- _clip_pbf cache key now keyed on (pbf_stem, bbox) not bbox alone —
  fixes a pre-existing bug where a second region would get the first
  region's cached clip
- hashlib.md5 -> hashlib.sha1(..., usedforsecurity=False) for FIPS envs
- Cache key in _extract_hydro is now sorted tuple of clipped-PBF paths
  (size-1 cache preserved from existing behavior)
- One new test asserts merged (lithuania, kaliningrad) fetch returns more
  features than lithuania alone

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.3: Verify Curonian Lagoon assembles from merged PBFs

**Files:**
- Modify: `scripts/_probe_kaliningrad.py`

- [ ] **Step 1: Append to the probe**

```python
# Add to scripts/_probe_kaliningrad.py
from modules.create_model_osm import query_water_bodies  # noqa: E402
from shapely.geometry import Point

bbox = (20.50, 54.40, 22.20, 55.95)  # wide enough to fully enclose lagoon
wb = query_water_bodies(("lithuania", "kaliningrad"), bbox)
lagoon_seed = Point(21.05, 55.20)
hits = wb[wb.geometry.contains(lagoon_seed)]
print(f"Water bodies containing lagoon seed: {len(hits)}")
if len(hits) > 0:
    biggest = hits.to_crs("EPSG:32634").geometry.area.max() / 1e6
    print(f"Largest containing polygon: {biggest:.0f} km²")
```

- [ ] **Step 2: Run it**

```bash
micromamba run -n shiny python scripts/_probe_kaliningrad.py
```

Expected either:
- **Success**: `Water bodies containing lagoon seed: 1` with area close to `1584 km²`. This means OSM's multipolygon relation now assembles cleanly, and Sub-project 1's Marine Regions fetch becomes redundant (demote to fallback only).
- **Still fails**: The relation contains ways outside the two PBFs' coverage — document this outcome in the commit message and keep Sub-project 1's polygon as primary.

---

### Task 3.4: Add Gilija reach + regenerate

**Files:**
- Modify: `scripts/generate_baltic_example.py`
- Modify: `configs/example_baltic.yaml`

- [ ] **Step 1: Probe Gilija / Matrosovka presence**

```bash
micromamba run -n shiny python -c "
from pathlib import Path
import sys
sys.path.insert(0, str(Path('app').resolve()))
from modules.create_model_osm import query_waterways
ww = query_waterways(('lithuania', 'kaliningrad'), (20.50, 54.40, 22.20, 55.95))
for n in ('Gilija', 'Матросовка', 'Matrosovka'):
    n_hits = (ww['nameText'] == n).sum()
    print(f'{n}: {n_hits} features')
"
```

Expected: at least one non-zero count. Use whichever name matches for the reach.

- [ ] **Step 2: Add Gilija to REACH_OSM, REACH_ORDER, REACH_PARAMS, CELL_SIZE_M**

In `scripts/generate_baltic_example.py`:

```python
# In REACH_OSM (add after Leite):
    "Gilija":   ("waterway", ("Gilija", "Матросовка", "Matrosovka")),
# In REACH_ORDER (add after Leite):
    "Nemunas", "Minija", "Sysa", "Skirvyte", "Leite", "Gilija",
    "CuronianLagoon", "BalticCoast",
# In CELL_SIZE_M:
    "Gilija": 250,
# In REACH_PARAMS (copy Leite params as baseline, then adjust):
    "Gilija": {
        "temp_mean": 10.0, "temp_amp": 9.5, "flow_base": 3.0, "turb_base": 4,
        "flows": [0.6, 1.2, 2.0, 3.0, 5.0, 7.0, 12.0, 22.0, 55.0, 250.0],
        "depth_base": 2.5, "depth_flood": 4.0,
        "vel_base": 0.10, "vel_flood": 0.6,
    },
```

In `generate_populations()` weights dict:

```python
    weights = {"Nemunas": 0.35, "Minija": 0.16, "Sysa": 0.13,
               "Skirvyte": 0.13, "Leite": 0.11, "Gilija": 0.12}
    adult_weights = {"Nemunas": 0.35, "Minija": 0.16, "Sysa": 0.12,
                     "Skirvyte": 0.14, "Leite": 0.11, "Gilija": 0.12}
```

Also change the fetcher call:

```python
# Replace
    ww = query_waterways("lithuania", BBOX)
# With
    ww = query_waterways(("lithuania", "kaliningrad"), BBOX)
```

- [ ] **Step 3: Add matching Gilija block to configs/example_baltic.yaml**

Insert before the `CuronianLagoon` block:

```yaml
  Gilija:                      # southern Nemunas-Delta branch (Kaliningrad side)
    drift_conc: 3.5e-09
    search_prod: 5.50e-07
    shelter_speed_frac: 0.12
    prey_energy_density: 3000
    drift_regen_distance: 1200
    shading: 0.45
    fish_pred_min: 0.955
    terr_pred_min: 0.960
    light_turbid_coef: 0.0035
    light_turbid_const: 0.0015
    max_spawn_flow: 10
    shear_A: 0.006
    shear_B: 0.28
    upstream_junction: 1
    downstream_junction: 5
    time_series_input_file: "Gilija-TimeSeriesInputs.csv"
    depth_file: "Gilija-Depths.csv"
    velocity_file: "Gilija-Vels.csv"
```

- [ ] **Step 4: Regenerate**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
micromamba run -n shiny python scripts/generate_baltic_example.py 2>&1 | tail -25
```

Expected: Gilija appears in the per-reach cell counts. Total cells land between 1 500 and 2 000.

- [ ] **Step 5: Sync fixtures**

```bash
rm -rf app/data/fixtures/example_baltic
cp -r tests/fixtures/example_baltic app/data/fixtures/example_baltic
```

- [ ] **Step 6: Run end-to-end test**

```bash
micromamba run -n shiny python -m pytest tests/test_model.py::test_adult_arrives_as_returning_adult -v --tb=short
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/generate_baltic_example.py configs/example_baltic.yaml
git add tests/fixtures/example_baltic app/data/fixtures/example_baltic
git add -u tests/fixtures/example_baltic app/data/fixtures/example_baltic
git commit -m "feat: add Gilija delta branch from merged LT+Kaliningrad PBFs

Uses the new multi-region fetcher support to pull the OSM waterway named
'Gilija' (or 'Матросовка'/'Matrosovka' on the Russian side) — the southern
Nemunas-Delta branch missing from the Lithuania-only PBF.

Hydraulic params copied from Leite as a starting point (similar small-delta
channel characteristics). Reach populations/arrivals weight adjusted.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3.5: Demote Sub-project 1 to fallback (conditional, only if Task 3.3 succeeded)

Only execute if Task 3.3 Step 2 printed `Water bodies containing lagoon seed: 1` with area ≈ 1 584 km². Otherwise skip this task — Sub-project 1 remains the primary path.

**Files:**
- Modify: `scripts/generate_baltic_example.py` (`fetch_curonian_lagoon`)
- Modify: `configs/example_baltic.yaml` (header comment)

- [ ] **Step 1: Swap `fetch_curonian_lagoon` priority**

In `scripts/generate_baltic_example.py`, rename the existing cache-first implementation to `_fetch_curonian_from_marineregions_or_cache`, then make `fetch_curonian_lagoon` try OSM first and delegate to it on miss:

```python
# Wider bbox for lagoon assembly — matches the bbox used in Task 3.3's probe.
# The run bbox (BBOX = 20.80, 54.90, 22.20, 55.95) is too narrow on the
# south side to capture the Kaliningrad-half rings of the lagoon relation.
LAGOON_ASSEMBLY_BBOX = (20.50, 54.40, 22.20, 55.95)


def _fetch_curonian_from_osm_merged() -> object | None:
    """Try the OSM route (merged LT+Kaliningrad PBFs). Returns None on miss.

    Uses LAGOON_ASSEMBLY_BBOX (wider than BBOX) because pyosmium needs every
    ring of the cross-border multipolygon relation present to assemble it.
    Requires query_water_bodies and make_valid to be importable — both
    already live at module top (from the baseline imports).
    """
    wb = query_water_bodies(("lithuania", "kaliningrad"), LAGOON_ASSEMBLY_BBOX)
    from shapely.geometry import Point as _Pt
    hits = wb[wb.geometry.contains(_Pt(21.05, 55.20))]
    if len(hits) == 0:
        return None
    hits_utm = hits.to_crs("EPSG:32634")
    # Use iloc+argmax instead of loc+idxmax so we don't depend on index alignment
    # between `hits` and `hits_utm` (to_crs preserves index today but that's
    # an implementation detail, not a guarantee).
    pos = int(hits_utm.geometry.area.values.argmax())
    geom = hits.geometry.iloc[pos]
    if not geom.is_valid:
        geom = make_valid(geom)
    area_km2 = float(hits_utm.geometry.area.iloc[pos]) / 1e6
    # Sanity: if the largest polygon is <500 km², it's not the lagoon — fall back.
    if area_km2 < 500:
        return None
    _log(f"  CuronianLagoon: {geom.geom_type} area={area_km2:.0f} km² "
         f"(from merged OSM LT+Kaliningrad PBFs)")
    return geom


def _fetch_curonian_from_marineregions_or_cache() -> object:
    """Cache-first / Marine-Regions / hand-traced — body from Task 1.2 Step 4,
    renamed verbatim (no logic change)."""
    # <<< paste the entire body of the Task 1.2 Step 4 `fetch_curonian_lagoon`
    #     function here unchanged — only the outer function name changes. >>>


def fetch_curonian_lagoon() -> object:
    """Priority:
      1. OSM water polygon from merged (lithuania, kaliningrad) PBFs —
         authoritative once the multipolygon relation assembles (Task 3.3).
      2. Marine Regions WFS / cache / hand-traced fallback chain.
    """
    geom = _fetch_curonian_from_osm_merged()
    if geom is not None:
        return geom
    _log("OSM merged PBFs did not yield lagoon; falling back...")
    return _fetch_curonian_from_marineregions_or_cache()
```

This splits responsibilities cleanly and removes the "..." placeholder hazard — the fallback chain is now a single `_fetch_curonian_from_marineregions_or_cache()` call.

- [ ] **Step 2a: Update existing Task 1.2 tests to skip OSM path via monkeypatch**

Task 3.5 makes `fetch_curonian_lagoon` try `_fetch_curonian_from_osm_merged` first, which calls `query_water_bodies(("lithuania", "kaliningrad"), ...)`. The existing tests in `tests/test_marineregions_cache.py` were written assuming the function starts at the cache branch — without mocking, they'll now trigger real PBF downloads.

Add a shared fixture to both existing tests that short-circuits OSM:

```python
# Add to tests/test_marineregions_cache.py (top of file, after imports)
@pytest.fixture(autouse=True)
def _skip_osm_path(monkeypatch):
    """Task 3.5 made fetch_curonian_lagoon try OSM first. For unit tests we
    want to stay on the Marine Regions / cache code path, so stub OSM out."""
    monkeypatch.setattr(
        "generate_baltic_example._fetch_curonian_from_osm_merged",
        lambda: None,
    )
```

`autouse=True` means every test in the file picks up the stub without needing to list the fixture.

- [ ] **Step 2: Update config header comment + function docstring**

In `configs/example_baltic.yaml`, change the line mentioning "hand-traced" or "Marine Regions" to read:

```yaml
#   CuronianLagoon — Kuršių marios, from merged OSM LT+Kaliningrad relations
#                    (Marine Regions MRGID 3642 + hand-traced remain as fallbacks)
```

Also update `fetch_curonian_lagoon`'s docstring in `scripts/generate_baltic_example.py` — the Task 1.2 docstring said "Cache-first, Marine-Regions WFS next, hand-traced fallback last." Task 3.5 reorders priority, so the docstring must reflect OSM-first (already written correctly in Task 3.5 Step 1 above).

- [ ] **Step 3: Regenerate + sync + test + commit**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
micromamba run -n shiny python scripts/generate_baltic_example.py
rm -rf app/data/fixtures/example_baltic
cp -r tests/fixtures/example_baltic app/data/fixtures/example_baltic
micromamba run -n shiny python -m pytest tests/test_model.py::test_adult_arrives_as_returning_adult -v --tb=short
```

Expected: PASS, with CuronianLagoon log line saying `from merged OSM LT+Kaliningrad PBFs`.

The Marine Regions cache (`app/data/marineregions/curonian_lagoon.geojson`) stays committed — it's now a fallback, not the primary, but keeping it means offline users and CI without internet can still generate fixtures. No delete step needed.

```bash
git add scripts/generate_baltic_example.py configs/example_baltic.yaml
git add tests/fixtures/example_baltic app/data/fixtures/example_baltic
git add -u tests/fixtures/example_baltic app/data/fixtures/example_baltic
git commit -m "refactor: Curonian Lagoon from merged OSM, Marine Regions as fallback

Once the LT+Kaliningrad PBF merge (sub-project 3) landed, pyosmium can
assemble the full Curonian Lagoon multipolygon relation from OSM. The
Marine Regions fetch and the hand-traced 18-coord polygon drop to
fallbacks behind it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Sub-project 2: EMODnet bathymetry grid

**Why:** Per-flow depth tables for `CuronianLagoon` and `BalticCoast` currently scale a single published base depth (3.8 m / 10.0 m). Real bathymetry varies from 0 m at the shore to 5.8 m in the lagoon center, and 0 m to 40+ m in 10 km across the Baltic coastal strip. Real cell-by-cell depths improve habitat-selection realism for lagoon and sea reaches.

**Approach:** Download EMODnet Bathymetry 1/16 arc-minute DTM for the bbox once via WCS, cache as GeoTIFF. For each cell in `CuronianLagoon` and `BalticCoast`, sample depth at the centroid. Use that real depth as the `depth_base` for the per-flow table; retain existing flood-scaling relation since per-flow bathymetry isn't available at this scale.

### Task 2.1: Install rasterio + verify EMODnet WCS

**Files:**
- Modify: repository root `environment.yml` (or `pyproject.toml`) if rasterio is pinned there
- Create: `scripts/_probe_emodnet.py`

- [ ] **Step 1: Check if rasterio is already in env**

```bash
micromamba run -n shiny python -c "import rasterio; print(rasterio.__version__)"
```

If ImportError, install:

```bash
micromamba install -n shiny -c conda-forge rasterio
```

Expected: rasterio >= 1.3 imports cleanly. Verified on 2026-04-18: `shiny` env has rasterio 1.5.0 already — this step should be a no-op; skip to Step 2.

- [ ] **Step 2: Write EMODnet WCS probe**

```python
# scripts/_probe_emodnet.py
"""Verify EMODnet Bathymetry WCS serves a usable GeoTIFF for the Nemunas/Baltic bbox."""
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "emodnet"
OUT.mkdir(parents=True, exist_ok=True)
dst = OUT / "probe_baltic.tif"

# EMODnet Bathymetry WCS 2.0 service
# Coverage ID confirmed at https://emodnet.ec.europa.eu/geoviewer/#!/bathymetry
url = "https://ows.emodnet-bathymetry.eu/wcs"
params = {
    "service": "WCS",
    "version": "2.0.1",
    "request": "GetCoverage",
    "coverageId": "emodnet__mean",
    "format": "image/tiff",
    "subset": ["Long(20.0,22.5)", "Lat(54.5,56.0)"],
}
print("Requesting EMODnet WCS GetCoverage...")
resp = requests.get(url, params=params, timeout=120, stream=True)
print(f"HTTP {resp.status_code}, Content-Type: {resp.headers.get('Content-Type')}")
resp.raise_for_status()
with open(dst, "wb") as f:
    for chunk in resp.iter_content(1 << 20):
        f.write(chunk)
print(f"Saved: {dst} ({dst.stat().st_size / 1_000_000:.1f} MB)")

import rasterio
with rasterio.open(dst) as src:
    print(f"CRS: {src.crs}")
    print(f"Bounds: {src.bounds}")
    print(f"Resolution: {src.res}")
    print(f"Shape: {src.shape}")
    print(f"Dtype: {src.dtypes}")
    arr = src.read(1)
    print(f"Depth range: min={arr.min()}, max={arr.max()} (EMODnet: negative = below sea level)")
```

- [ ] **Step 3: Run it**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
micromamba run -n shiny python scripts/_probe_emodnet.py
```

Expected: a GeoTIFF of 5–50 MB, CRS `EPSG:4326`, resolution around 0.00104° (~115 m at this latitude). Depth min around -80 m (Baltic deeps), max small positive (coastal shallows / spit above sea level).

Coverage IDs verified 2026-04-18 via GetCapabilities — available IDs use **double underscore**, not colon:
  `emodnet__mean`, `emodnet__mean_2016`, `emodnet__mean_2018`, `emodnet__mean_2020`, `emodnet__mean_2022`, `emodnet__mean_atlas_land`, `emodnet__mean_multicolour`, `emodnet__mean_rainbowcolour`.
`emodnet__mean` is the latest composite — use that. If it ever 404s, hit `?service=WCS&request=GetCapabilities` and update `_EMODNET_COVERAGE_ID` in `app/modules/bathymetry.py` (Task 2.2).

- [ ] **Step 4: Attribution requirement for Task 2.4 commit**

EMODnet data requires attribution. Task 2.4's commit message must include the line: `Data source: EMODnet Bathymetry Consortium. https://emodnet.ec.europa.eu/en/bathymetry`.

---

### Task 2.2: Bathymetry fetcher + sampler module

**Files:**
- Create: `app/modules/bathymetry.py`
- Create: `tests/test_bathymetry.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add gitignore rule for cached GeoTIFFs**

Append to `.gitignore`:

```
# Cached EMODnet DTM (50-200 MB, not committed — regenerate via fetch_emodnet_dtm)
app/data/emodnet/*.tif
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_bathymetry.py
"""Tests for app/modules/bathymetry.py — EMODnet DTM fetch + sample."""
from pathlib import Path
import sys

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point, Polygon

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

from modules.bathymetry import sample_depth, _cache_path_for_bbox  # noqa: E402


def test_cache_path_deterministic():
    bbox = (20.0, 54.5, 22.5, 56.0)
    p1 = _cache_path_for_bbox(bbox)
    p2 = _cache_path_for_bbox(bbox)
    assert p1 == p2
    assert p1.suffix == ".tif"


def test_sample_depth_on_synthetic_raster(tmp_path):
    """Write a synthetic GeoTIFF over Baltic coordinates with EMODnet-style
    negative elevations, sample known cells, verify sign-flip + clamp.

    Coords stay in the Baltic (lat 55-56, lon 20-22) so gdf.estimate_utm_crs()
    picks a real UTM zone — avoids the "UTM 34N at equator" extrapolation that
    makes centroid round-trips bogus.
    """
    import rasterio
    from rasterio.transform import from_bounds

    tif = tmp_path / "synth.tif"
    # 3x3 raster over Baltic bbox (lon 20-23, lat 54-57). EMODnet encodes
    # elevation, negative below sea level; values -1..-9 -> depths 1..9m.
    # rasterio row 0 = north (max lat).
    data = -np.arange(1, 10, dtype=np.float32).reshape(3, 3)
    transform = from_bounds(20.0, 54.0, 23.0, 57.0, 3, 3)
    with rasterio.open(
        tif, "w", driver="GTiff", height=3, width=3, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)

    # Two polygons whose centroids land in known pixels. Each pixel covers
    # 1° × 1°. Row 0 = north (lat 56-57), row 2 = south (lat 54-55).
    # Centroid (20.5, 56.5) -> row 0 col 0 -> elev -1 -> depth 1m.
    # Centroid (22.5, 54.5) -> row 2 col 2 -> elev -9 -> depth 9m.
    gdf = gpd.GeoDataFrame(
        geometry=[
            Polygon([(20.0, 56.0), (21.0, 56.0), (21.0, 57.0), (20.0, 57.0)]),
            Polygon([(22.0, 54.0), (23.0, 54.0), (23.0, 55.0), (22.0, 55.0)]),
        ],
        crs="EPSG:4326",
    )
    depths = sample_depth(gdf, tif)
    assert len(depths) == 2
    # Top-left polygon (far NW) should sample the shallowest pixel (depth 1m).
    # Bottom-right polygon should sample the deepest pixel (depth 9m).
    # Use loose tolerance because UTM centroid round-trip may shift <100 m,
    # still inside the original pixel given 1° (~110km) pixel size.
    assert depths[0] == pytest.approx(1.0, abs=0.01)
    assert depths[1] == pytest.approx(9.0, abs=0.01)


def test_sample_depth_clamps_land_to_minimum(tmp_path):
    """Positive elevation (land) becomes negative depth; code must clamp to 0.1 m."""
    import rasterio
    from rasterio.transform import from_bounds

    tif = tmp_path / "land.tif"
    # All positive elevation → all land → all clamped to 0.1m
    data = np.full((3, 3), 5.0, dtype=np.float32)
    transform = from_bounds(20.0, 54.0, 23.0, 57.0, 3, 3)
    with rasterio.open(
        tif, "w", driver="GTiff", height=3, width=3, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)

    gdf = gpd.GeoDataFrame(
        geometry=[Polygon([(20.0, 54.0), (21.0, 54.0), (21.0, 55.0), (20.0, 55.0)])],
        crs="EPSG:4326",
    )
    depths = sample_depth(gdf, tif)
    assert len(depths) == 1
    assert depths[0] == pytest.approx(0.1)


def test_sample_depth_missing_raster_raises(tmp_path):
    # Use a Baltic-area point so an eventual estimate_utm_crs call (if any
    # upstream logic triggers it) doesn't hit equatorial extrapolation.
    gdf = gpd.GeoDataFrame(geometry=[Point(21.0, 55.0)], crs="EPSG:4326")
    with pytest.raises(FileNotFoundError):
        sample_depth(gdf, tmp_path / "does_not_exist.tif")
```

- [ ] **Step 3: Run tests, expect fail**

```bash
micromamba run -n shiny python -m pytest tests/test_bathymetry.py -v
```

Expected: ImportError on `app/modules/bathymetry.py`.

- [ ] **Step 4: Implement the module**

```python
# app/modules/bathymetry.py
"""EMODnet Bathymetry DTM fetch + per-cell depth sampler.

Workflow:
    1. fetch_emodnet_dtm(bbox) downloads a 1/16 arc-minute GeoTIFF once,
       caches it under app/data/emodnet/ keyed by bbox hash.
    2. sample_depth(gdf, tif_path) reads each cell's centroid depth.

Depths are reported as positive metres below sea surface (EMODnet stores
elevation as negative below datum; we flip the sign).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import geopandas as gpd
import numpy as np
import requests

_EMODNET_WCS = "https://ows.emodnet-bathymetry.eu/wcs"
_EMODNET_COVERAGE_ID = "emodnet__mean"  # verified via scripts/_probe_emodnet.py
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "emodnet"


def _cache_path_for_bbox(bbox: tuple[float, float, float, float]) -> Path:
    """Cache path for a bbox (hash of bbox coords).

    Uses SHA-1 with `usedforsecurity=False` for FIPS-mode Windows compatibility;
    the hash is a cache key, not a security boundary.
    """
    key = ",".join(f"{v:.4f}" for v in bbox)
    h = hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:12]
    return _CACHE_DIR / f"emodnet_{h}.tif"


def fetch_emodnet_dtm(bbox: tuple[float, float, float, float]) -> Path:
    """Download EMODnet DTM for bbox (lon_min, lat_min, lon_max, lat_max) if
    not already cached. Returns the local GeoTIFF path."""
    dst = _cache_path_for_bbox(bbox)
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    params = {
        "service": "WCS",
        "version": "2.0.1",
        "request": "GetCoverage",
        "coverageId": _EMODNET_COVERAGE_ID,
        "format": "image/tiff",
        "subset": [
            f"Long({bbox[0]},{bbox[2]})",
            f"Lat({bbox[1]},{bbox[3]})",
        ],
    }
    tmp = dst.with_suffix(".tif.part")
    resp = requests.get(_EMODNET_WCS, params=params, timeout=300, stream=True)
    resp.raise_for_status()
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(1 << 20):
            f.write(chunk)
    tmp.replace(dst)
    return dst


def sample_depth(gdf, tif_path: Path) -> np.ndarray:
    """Return an array of depths (positive metres below surface), one per row
    in *gdf*, sampled at each row's geometry centroid.

    Uses an *adaptive* projection to avoid shapely's "Geometry is in a
    geographic CRS" warning for centroid computation:
      - if the raster CRS is projected: reproject gdf to raster CRS, take
        centroid there, sample directly
      - if the raster CRS is geographic (EMODnet is EPSG:4326): use
        gdf.estimate_utm_crs() so coverage extends beyond UTM 34N
        (handles bboxes that cross into zone 33 or 35)
    """
    import rasterio
    import warnings

    if not Path(tif_path).exists():
        raise FileNotFoundError(tif_path)

    with rasterio.open(tif_path) as src:
        src_crs = src.crs
        if src_crs is not None and src_crs.is_projected:
            # Easy path — centroid in the raster's own projected CRS, no warning.
            gdf_proj = gdf.to_crs(src_crs) if gdf.crs != src_crs else gdf
            centroids = gdf_proj.geometry.centroid
            coords = [(c.x, c.y) for c in centroids]
        else:
            # Raster is geographic (e.g. EMODnet EPSG:4326). Compute centroids
            # in an appropriate UTM (derived from the data, not hardcoded) so
            # the "geographic CRS centroid" warning doesn't fire.
            try:
                utm_crs = gdf.estimate_utm_crs()
            except Exception:
                utm_crs = "EPSG:32634"  # fallback for Baltic
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # last-resort guard if UTM covers edge
                gdf_utm = gdf.to_crs(utm_crs)
                centroids_utm = gdf_utm.geometry.centroid
            centroids_wgs = gpd.GeoSeries(centroids_utm, crs=utm_crs).to_crs(src_crs or "EPSG:4326")
            coords = [(c.x, c.y) for c in centroids_wgs]
        samples = np.array([v[0] for v in src.sample(coords)])

    # EMODnet stores elevation (negative below sea level) — flip sign to depth
    depths = -samples.astype(np.float64)
    # Land cells (elevation > 0) become negative depth → clamp to 0.1 m
    depths = np.where(depths < 0.1, 0.1, depths)
    return depths
```

- [ ] **Step 5: Run tests, expect pass**

```bash
micromamba run -n shiny python -m pytest tests/test_bathymetry.py -v
```

Expected: 4 passed.

---

### Task 2.3: Integrate EMODnet sampling into generate_hydraulics

**Files:**
- Modify: `scripts/generate_baltic_example.py`

- [ ] **Step 1: Modify generate_hydraulics signature + logic**

Current function signature:

```python
def generate_hydraulics(reach_name: str, n_cells: int) -> None:
```

Change to accept an optional real-depth array for lagoon/coast reaches. In the main() flow, fetch EMODnet once and pass the per-cell sampled array.

Near the top of the file, add imports:

```python
sys.path.insert(0, str(APP_DIR))   # already present
from modules.bathymetry import fetch_emodnet_dtm, sample_depth  # noqa: E402
```

Modify `generate_hydraulics`:

```python
def generate_hydraulics(
    reach_name: str, n_cells: int, depths_by_cell: np.ndarray | None = None
) -> None:
    p = REACH_PARAMS[reach_name]
    flows = p["flows"]
    n_flows = len(flows)
    rng = np.random.default_rng(777 + abs(hash(reach_name)) % 10000)
    f_frac = np.array([
        (math.log(fl) - math.log(flows[0])) / (math.log(flows[-1]) - math.log(flows[0]))
        for fl in flows
    ])
    for kind, base_key, flood_key, unit in [
        ("Depths", "depth_base", "depth_flood", "METERS"),
        ("Vels",   "vel_base",   "vel_flood",   "M/S"),
    ]:
        fpath = OUT / f"{reach_name}-{kind}.csv"
        v_base = p[base_key]
        v_flood = p[flood_key]
        with open(fpath, "w", newline="") as f:
            f.write(f"; {kind} for Baltic example — {reach_name}\n")
            real_bathy = kind == "Depths" and depths_by_cell is not None
            if real_bathy:
                f.write("; per-cell depth_base from EMODnet DTM (1/16 arc-min); "
                        "per-flow scaling synthetic\n")
            else:
                f.write("; depth_base/vel_base are real published means; "
                        "per-flow scaling is synthetic\n")
            f.write(f"; CELL {kind.upper()} IN {unit}\n")
            f.write(f"{n_flows},Number of flows in table" + ",," * (n_flows - 1) + "\n")
            f.write("," + ",".join(f"{fl}" for fl in flows) + "\n")
            for c in range(1, n_cells + 1):
                if real_bathy:
                    # Per-cell real base depth; flood scale via same ratio as synthetic.
                    cell_base = float(depths_by_cell[c - 1])
                    # Preserve original flood:base ratio so per-flow interpolation
                    # behaves sensibly for cells that are land-adjacent (0.1 m).
                    ratio = p["depth_flood"] / p["depth_base"]
                    cell_flood = cell_base * ratio
                    vals = []
                    for fi in range(n_flows):
                        v = cell_base + (cell_flood - cell_base) * f_frac[fi]
                        vals.append(f"{max(0.001, v):.6f}")
                    f.write(f"{c}," + ",".join(vals) + "\n")
                else:
                    cell_var = 0.7 + 0.6 * rng.random()
                    vals = []
                    for fi in range(n_flows):
                        v = cell_var * (v_base + (v_flood - v_base) * f_frac[fi])
                        vals.append(f"{max(0.001, v):.6f}")
                    f.write(f"{c}," + ",".join(vals) + "\n")
```

- [ ] **Step 2: Modify main() to fetch DTM + sample per cell for lagoon/coast**

Find `main()` (starts at line 446 in baseline `046206d`). `gdf` is built at line 458, `counts` at line 461, and the per-reach loop is at line 474. Insert the new block between line 471 (`gdf.to_file(...)`) and line 474:

```python
    # Fetch EMODnet DTM once for the whole run bbox
    bbox_dtm = (BBOX[0] - 0.1, BBOX[1] - 0.1, BBOX[2] + 0.1, BBOX[3] + 0.1)
    _log("Fetching EMODnet DTM for lagoon + coast reaches...")
    dtm_path = fetch_emodnet_dtm(bbox_dtm)

    # Build a per-reach cell GeoDataFrame (reproject shapefile back to WGS84
    # for sampling in EMODnet's native CRS)
    gdf_wgs = gdf.to_crs("EPSG:4326")
    depths_by_reach: dict[str, np.ndarray] = {}
    for reach in ("CuronianLagoon", "BalticCoast"):
        mask = gdf_wgs["REACH_NAME"] == reach
        if mask.any():
            depths_by_reach[reach] = sample_depth(gdf_wgs[mask], dtm_path)
            _log(f"  {reach}: sampled {len(depths_by_reach[reach])} depths "
                 f"(min {depths_by_reach[reach].min():.1f} m, "
                 f"max {depths_by_reach[reach].max():.1f} m)")
```

And change the hydraulics call to:

```python
    for reach_name, n_cells in counts.items():
        generate_time_series(reach_name)
        generate_hydraulics(reach_name, n_cells, depths_by_reach.get(reach_name))
        _log(f"CSVs: {reach_name}")
```

- [ ] **Step 3: Regenerate + inspect lagoon depths**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
micromamba run -n shiny python scripts/generate_baltic_example.py 2>&1 | tail -20
head -5 tests/fixtures/example_baltic/CuronianLagoon-Depths.csv
```

Expected: First line of CuronianLagoon-Depths.csv says "per-cell depth_base from EMODnet DTM". Per-cell values vary (not uniform scaling anymore). Depth histogram centered around 3.8 m.

- [ ] **Step 4: Sync + run test**

```bash
rm -rf app/data/fixtures/example_baltic
cp -r tests/fixtures/example_baltic app/data/fixtures/example_baltic
micromamba run -n shiny python -m pytest tests/test_model.py::test_adult_arrives_as_returning_adult -v --tb=short
```

Expected: PASS.

---

### Task 2.4: Commit

- [ ] **Step 1: Stage and commit**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
git add app/modules/bathymetry.py tests/test_bathymetry.py .gitignore
git add scripts/generate_baltic_example.py
git add tests/fixtures/example_baltic app/data/fixtures/example_baltic
git add -u tests/fixtures/example_baltic app/data/fixtures/example_baltic
git commit -m "$(cat <<'EOF'
feat: Curonian Lagoon + Baltic coast cells use real EMODnet bathymetry

Adds app/modules/bathymetry.py with two helpers:
  - fetch_emodnet_dtm(bbox) downloads EMODnet 1/16 arc-min DTM via WCS,
    caches to app/data/emodnet/ (gitignored)
  - sample_depth(gdf, tif) returns per-centroid depth in metres below surface

The Baltic example generator now samples real depth per cell for the
CuronianLagoon and BalticCoast reaches; river reaches keep the published
mean-depth scaling (EMODnet coverage is marine-only).

Per-flow scaling preserved for CSV compatibility; each cell's flood depth
is derived from its real base depth using the reach's published
flood:base ratio.

Data source: EMODnet Bathymetry Consortium. https://emodnet.ec.europa.eu/en/bathymetry

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.5: Benchmark-regression check

The generator's `generate_hydraulics` is now called with per-cell EMODnet sampling, which adds rasterio I/O. Verify no significant regression in simulation hot paths.

- [ ] **Step 1: Run the bench-regression skill**

```bash
cd "C:/Users/arturas.baziukas/OneDrive - ku.lt/HORIZON_EUROPE/inSTREAM/instream-py"
micromamba run -n shiny python benchmarks/bench_full.py --baseline HEAD~5 --current HEAD 2>&1 | tail -20
```

Or invoke via `/bench-regression` per CLAUDE.md's skill registration. Expected: no hot-path regression >5% on `model.step` — this commit adds I/O only at generate time, not simulation time.

- [ ] **Step 2: If regression detected**, profile which new call became hot:

```bash
micromamba run -n shiny python -m cProfile -s cumulative scripts/generate_baltic_example.py 2>&1 | head -40
```

Note: generate-time cost is a one-time hit (fixtures regenerated once, then reused), not a per-simulation cost — a modest increase here is acceptable. Reject only if `model.step` or the test suite itself slowed down.

---

## Shared test-utilities note (M1 fix)

All three new test files (`tests/test_marineregions_cache.py`, `tests/test_create_model_osm.py` addition, `tests/test_bathymetry.py`) do `sys.path.insert(0, ...)` to reach `app/modules` or `scripts/`. This mutates `sys.path` globally for the pytest run. The existing `tests/test_create_model_grid.py` has the same pattern and no conftest — follow that precedent.

If the plan is executed and multiple test files' `sys.path` conflict, hoist the common insertion into `tests/conftest.py`:

```python
# Add to tests/conftest.py if not already present
import sys
from pathlib import Path
_APP = (Path(__file__).resolve().parent.parent / "app").resolve()
_SCRIPTS = (Path(__file__).resolve().parent.parent / "scripts").resolve()
for p in (_APP, _SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
```

This is a low-risk cleanup — do it as a throwaway follow-up commit only if conflicts surface.

---

## Self-Review Checklist

Pre-flight checks completed 2026-04-18:

- [x] All three sub-projects have concrete commands — no "TBD" or "similar to above"
- [x] Test commands specify exact pytest paths
- [x] Commit messages are scoped per-task, not a single monster commit
- [x] Fallback paths documented where external services are involved (Marine Regions WFS offline → hand-traced polygon; EMODnet offline → rasterio FileNotFoundError raised cleanly)
- [x] `_probe_*.py` scratch scripts are marked as "don't commit" (underscore prefix keeps pytest quiet)
- [x] The Kaliningrad task 3.3 has a branching outcome: if lagoon assembles from merged PBFs, Task 3.5 demotes Sub-project 1 to fallback
- [x] External API endpoints verified live on 2026-04-18:
  - Marine Regions REST `getGazetteerGeometries.json/NNN/` returns **404** — plan uses WFS `geo.vliz.be/geoserver/MarineRegions/wfs` instead
  - Marine Regions MRGID for Curonian Lagoon is **3642**, not 3478
  - EMODnet WCS coverageId is **`emodnet__mean`** (double underscore), not `emodnet:mean`
  - Geofabrik Kaliningrad PBF URL returns 302 redirect (normal; download proceeds)
  - `rasterio 1.5.0` already present in `shiny` env — Task 2.1 Step 1 is a no-op
- [x] Codebase line references verified: `fetch_curonian_lagoon` at line **195**, `main()` at **446**, `gdf` assigned at **458**, `counts` at **461**, insertion point for Task 2.3 Step 2 is between lines **471 and 474** — all in baseline commit `046206d`
- [x] Pre-existing `_clip_pbf` cache-by-bbox-only bug diagnosed — Task 3.2 Step 3 fixes it first (keys on `(pbf_stem, bbox)` + switches MD5→SHA1 for FIPS)
- [x] `MARINEREGIONS_TYPENAME` default (`MarineRegions:iho`) is non-blocking — the fallback chain absorbs a wrong value (WFS returns 0 features → hand-traced polygon + WARN log) without NotImplementedError (removed in 3rd pass — it leaked into the fallback path)
- [x] Task 3.5's `fetch_curonian_lagoon` rewrite uses an explicit `_fetch_curonian_from_marineregions_or_cache()` delegation, no `# ...` placeholder
- [x] `sample_depth` computes centroids in a data-derived UTM CRS (`gdf.estimate_utm_crs()` with EPSG:32634 fallback) to avoid shapely's geographic-CRS warning without hardcoding a zone
- [x] Shell convention + rollback strategy documented at the top of the plan
- [x] Benchmark check added as Task 2.5
- [x] `app/modules/bathymetry.py` imports `geopandas as gpd` at module top (was missing after centroid-reproject rewrite — caught in 3rd pass)
- [x] Task 3.5's `_fetch_curonian_from_osm_merged` uses `LAGOON_ASSEMBLY_BBOX` (wider), NOT the narrow run `BBOX` — matches the bbox Task 3.3 probe needed for cross-border relation assembly
- [x] Dropped the `NotImplementedError` fail-fast guard on `MARINEREGIONS_TYPENAME` — it leaked into the fallback chain, and false-positived for the legitimate `MarineRegions:iho` value. Fallback path now maximally robust: unknown typeName → 0 features → hand-traced polygon with WARN log
- [x] `_clip_pbf` cache key uses `pbf_file.name` (full basename `lithuania-latest.osm.pbf`), not `.stem` (which strips only last suffix)
- [x] `sample_depth` uses `gdf.estimate_utm_crs()` instead of hardcoded EPSG:32634 — correct for bboxes outside zone 34 (e.g. future extensions east of 24°E)
- [x] `sample_depth` uses raster-CRS centroids directly when raster is projected, avoiding the reproject-for-centroid detour entirely
- [x] Synthetic-raster test uses Baltic coordinates (lat 54-57, lon 20-23) so `estimate_utm_crs` picks a valid UTM zone; asserts exact depths (1.0 m and 9.0 m within 0.01 m tolerance) rather than the tautological "max > min + 1.0"
- [x] Task 3.5 added Step 2a: monkeypatch `_fetch_curonian_from_osm_merged` → None in SP1 tests so they stay on cache/WFS path (otherwise SP1 unit tests become network-bound after SP3)
- [x] Task 1.5 commit message reworded — no longer falsely claims the cache is always written
- [x] `_fetch_curonian_from_osm_merged` uses `iloc+argmax` instead of `loc+idxmax` to avoid index-alignment assumption between `hits` and `hits_utm`
- [x] `_fetch_curonian_from_osm_merged` includes a 500 km² size sanity check so an OSM tributary sliver doesn't masquerade as the lagoon

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-18-baltic-real-data-upgrades.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
