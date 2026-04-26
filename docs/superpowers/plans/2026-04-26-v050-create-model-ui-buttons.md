# v0.50.0 — Create Model UI buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three new buttons (🔍 Find / ✨ Auto-extract / ⚡ Auto-split) to the Create Model panel that wire the v0.47.0 helper modules into a discoverable UX.

**Architecture:** New "Auto:" toolbar row below the existing `cm-toolbar`. Five new input controls. One new helper module (`create_model_geocode.py`). One new function in `create_model_river.py` (`default_reach_names`). One new module-level helper in `create_model_panel.py` (`_pick_mouth_from_sea`). Three new reactive vars + soft-fail toasts on missing prereqs.

**Tech Stack:** Python 3.13, Shiny ≥1.5, geopandas ≥1.0, shapely ≥2.0, requests, pytest, micromamba env `shiny`.

**Spec reference:** `docs/superpowers/specs/2026-04-26-v050-create-model-ui-buttons-design.md`

**Working branch:** `v050-create-model-ui-buttons` (already created from master; spec already committed at `0f6afae`).

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `app/modules/create_model_geocode.py` | Create | Nominatim geocoder helper. ~100 LOC. |
| `tests/test_create_model_geocode.py` | Create | 7 unit tests for `lookup_place_bbox`. ~120 LOC. |
| `app/modules/create_model_river.py` | Modify | Add `default_reach_names` function. |
| `tests/test_create_model_river.py` | Modify | Add 2 cases for `default_reach_names`. |
| `app/modules/create_model_panel.py` | Modify | Add UI controls, 3 new handlers (`_on_find`, `_on_auto_extract`, `_on_auto_split`), 3 new reactive vars, `_pick_mouth_from_sea` module-level helper, edits to `_on_map_click` + `_on_clear_reaches`, lifted `_do_fetch_rivers` + `_do_fetch_water` helpers. |
| `tests/test_pick_mouth_from_sea.py` | Create | 4 unit tests. ~80 LOC. |
| `pyproject.toml` | Modify | Version bump 0.49.0 → 0.50.0. |
| `src/salmopy/__init__.py` | Modify | Version bump 0.49.0 → 0.50.0. |
| `CHANGELOG.md` | Modify | Prepend v0.50.0 entry. |

---

## Task 1: New `create_model_geocode.py` helper + tests

**Files:**
- Create: `app/modules/create_model_geocode.py`
- Create: `tests/test_create_model_geocode.py`

- [ ] **Step 1.1: Write failing tests in `tests/test_create_model_geocode.py`**

```python
"""Unit tests for the create_model_geocode helper module.

Mocks `requests.get` to test the Nominatim wrapper without network.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure app/modules is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from modules.create_model_geocode import lookup_place_bbox

NOMINATIM_KLAIPEDA = [{
    "place_id": 12345,
    "lat": "55.7128",
    "lon": "21.1351",
    "boundingbox": ["55.65", "55.78", "21.05", "21.25"],  # [lat_s, lat_n, lon_w, lon_e]
    "display_name": "Klaipėda, Lithuania",
    "address": {"country_code": "lt", "country": "Lithuania"},
}]


def _mock_response(json_data, content_length=2000):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.headers = {"Content-Length": str(content_length)}
    resp.raise_for_status = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_lookup_place_bbox_klaipeda_success():
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.return_value = _mock_response(NOMINATIM_KLAIPEDA)
        result = lookup_place_bbox("Klaipėda")
    assert result is not None
    country, bbox = result
    assert country == "lithuania"
    assert bbox[0] == pytest.approx(21.05)  # lon_w (NOT lat)
    assert bbox[1] == pytest.approx(55.65)  # lat_s
    assert bbox[2] == pytest.approx(21.25)  # lon_e
    assert bbox[3] == pytest.approx(55.78)  # lat_n


def test_lookup_place_bbox_empty_results():
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.return_value = _mock_response([])
        result = lookup_place_bbox("Klaipėda")
    assert result is None


def test_lookup_place_bbox_unknown_country_code():
    payload = [dict(NOMINATIM_KLAIPEDA[0])]
    payload[0]["address"] = {"country_code": "zz"}
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = lookup_place_bbox("Klaipėda")
    assert result is not None
    country, bbox = result
    assert country is None  # zz not in _ISO_TO_GEOFABRIK
    assert bbox[0] == pytest.approx(21.05)


def test_lookup_place_bbox_network_error(caplog):
    import requests as req
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.side_effect = req.ConnectionError("network down")
        with caplog.at_level(logging.WARNING):
            result = lookup_place_bbox("Klaipėda")
    assert result is None
    assert any("Nominatim lookup failed" in rec.message for rec in caplog.records)


def test_lookup_place_bbox_empty_input():
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        assert lookup_place_bbox("") is None
        assert lookup_place_bbox("   ") is None
        mock_get.assert_not_called()


def test_lookup_place_bbox_special_chars():
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.return_value = _mock_response(NOMINATIM_KLAIPEDA)
        lookup_place_bbox("Mörrumsån")
    assert mock_get.call_args.kwargs["params"]["q"] == "Mörrumsån"


def test_lookup_place_bbox_addressdetails_param():
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.return_value = _mock_response(NOMINATIM_KLAIPEDA)
        lookup_place_bbox("Klaipėda")
    assert mock_get.call_args.kwargs["params"]["addressdetails"] == 1
```

- [ ] **Step 1.2: Run tests to verify they fail**

```
micromamba run -n shiny python -m pytest tests/test_create_model_geocode.py -v
```
Expected: 7 FAIL with `ModuleNotFoundError: No module named 'modules.create_model_geocode'`.

- [ ] **Step 1.3: Create `app/modules/create_model_geocode.py`**

```python
"""Nominatim place-lookup helper for the Create Model panel.

Wraps Nominatim's free geocoding API to return a Geofabrik-compatible
country name plus a WGS84 bounding box for a place name. Used by the
🔍 Find by name button in create_model_panel.py to set the Region
dropdown and zoom the map to a user-typed location.

Pattern mirrors `query_named_sea_polygon` in create_model_marine.py:
  * timeout-bounded `requests.get` inside a `with` block (Windows
    socket-pool hygiene).
  * Content-Length cap to short-circuit on giant responses.
  * Exception logging via `logging.warning(class, message)` before
    swallowing — failure modes go to logs, not the user.
"""
from __future__ import annotations

import logging
import os

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# ISO 3166-1 alpha-2 → Geofabrik country name (subset of GEOFABRIK_COUNTRIES
# in create_model_osm.py). Initial coverage: WGBAST + Baltic countries.
_ISO_TO_GEOFABRIK: dict[str, str] = {
    "lt": "lithuania",
    "lv": "latvia",
    "ee": "estonia",
    "pl": "poland",
    "de": "germany",
    "se": "sweden",
    "fi": "finland",
    "no": "norway",
    "dk": "denmark",
    "ru": "russia",
}

try:
    from salmopy import __version__
except ImportError:
    __version__ = "dev"

_CONTACT = os.environ.get(
    "INSTREAM_NOMINATIM_CONTACT",
    "arturas.razinkovas-baziukas@ku.lt",
)
_USER_AGENT = f"inSTREAM-py/{__version__} ({_CONTACT})"


def lookup_place_bbox(
    name: str,
    timeout_s: int = 10,
) -> tuple[str | None, tuple[float, float, float, float]] | None:
    """Geocode `name` via Nominatim → (geofabrik_country, bbox_wgs84).

    Returns:
      (geofabrik_name, (lon_w, lat_s, lon_e, lat_n)) — happy path.
      (None, bbox) — country recognized but not in GEOFABRIK_COUNTRIES.
      None — empty input, 0 results, parse failure, or network error.
    """
    if not name or not name.strip():
        return None

    params = {
        "q": name.strip(),
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }
    headers = {"User-Agent": _USER_AGENT}

    try:
        with requests.get(
            NOMINATIM_URL, params=params, headers=headers, timeout=timeout_s,
        ) as resp:
            resp.raise_for_status()
            if int(resp.headers.get("Content-Length", 0) or 0) > 5_000_000:
                return None
            results = resp.json()
    except Exception as exc:
        logging.warning(
            "Nominatim lookup failed (%s): %s",
            type(exc).__name__, exc,
        )
        return None

    if not results:
        return None

    item = results[0]
    bb = item.get("boundingbox") or []
    if len(bb) != 4:
        return None
    try:
        lat_s, lat_n, lon_w, lon_e = (float(x) for x in bb)
    except (TypeError, ValueError):
        return None
    bbox_wgs84 = (lon_w, lat_s, lon_e, lat_n)

    iso2 = (item.get("address", {}).get("country_code") or "").lower()
    geofabrik = _ISO_TO_GEOFABRIK.get(iso2)
    return (geofabrik, bbox_wgs84)
```

- [ ] **Step 1.4: Run tests to verify they pass**

```
micromamba run -n shiny python -m pytest tests/test_create_model_geocode.py -v
```
Expected: 7 PASS.

- [ ] **Step 1.5: Commit Task 1**

```
git add app/modules/create_model_geocode.py tests/test_create_model_geocode.py
git commit -m "feat(create_model_geocode): add Nominatim lookup_place_bbox helper

New module wraps Nominatim's free geocoding API for the upcoming 🔍 Find
by name button in the Create Model panel. Returns (geofabrik_country, bbox)
or None on any failure path.

Pattern mirrors query_named_sea_polygon (create_model_marine.py): timeout-
bounded requests.get inside with block + Content-Length cap + exception
logging. User-Agent identifies inSTREAM-py per Nominatim ToS; deployers
override via INSTREAM_NOMINATIM_CONTACT env var.

7 unit tests cover happy path, empty results, unknown ISO-2, network
error, empty input (no API call), special chars (Mörrumsån passes through
unchanged), and addressdetails=1 param requirement.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `default_reach_names` helper + tests in `create_model_river.py`

**Files:**
- Modify: `app/modules/create_model_river.py`
- Modify: `tests/test_create_model_river.py`

- [ ] **Step 2.1: Write failing tests** — append to `tests/test_create_model_river.py`

```python
def test_default_reach_names_n4():
    from modules.create_model_river import default_reach_names
    assert default_reach_names(4) == ["Mouth", "Lower", "Middle", "Upper"]


def test_default_reach_names_other_n():
    from modules.create_model_river import default_reach_names
    assert default_reach_names(2) == ["Reach1", "Reach2"]
    assert default_reach_names(3) == ["Reach1", "Reach2", "Reach3"]
    assert default_reach_names(8) == [f"Reach{i}" for i in range(1, 9)]
```

- [ ] **Step 2.2: Run tests to verify they fail**

```
micromamba run -n shiny python -m pytest tests/test_create_model_river.py::test_default_reach_names_n4 tests/test_create_model_river.py::test_default_reach_names_other_n -v
```
Expected: 2 FAIL with `ImportError: cannot import name 'default_reach_names'`.

- [ ] **Step 2.3: Add `default_reach_names` to `create_model_river.py`**

Append at the end of the file (after `_orient_centerline_mouth_to_source`):

```python
def default_reach_names(n_reaches: int) -> list[str]:
    """Smart default for reach names produced by Auto-split.

    For the WGBAST convention N=4 → ["Mouth", "Lower", "Middle", "Upper"].
    For any other N → ["Reach1", "Reach2", ..., "ReachN"]. Users can
    rename via the Edit Model panel after the split runs.
    """
    if n_reaches == 4:
        return ["Mouth", "Lower", "Middle", "Upper"]
    return [f"Reach{i}" for i in range(1, n_reaches + 1)]
```

- [ ] **Step 2.4: Run tests to verify they pass**

```
micromamba run -n shiny python -m pytest tests/test_create_model_river.py -v
```
Expected: 11 PASS (9 pre-existing + 2 new).

- [ ] **Step 2.5: Commit Task 2**

```
git add app/modules/create_model_river.py tests/test_create_model_river.py
git commit -m "feat(create_model_river): add default_reach_names helper

Smart default for reach names produced by the upcoming Auto-split button:
N=4 returns the WGBAST convention [Mouth, Lower, Middle, Upper], any
other N returns generic [Reach1, ..., ReachN]. Users rename via Edit
Model panel afterward.

Lands BEFORE the panel changes in v0.50.0 (subsequent commit) — the
panel's helper-import try/except references default_reach_names; without
this commit, the panel would silently disable Auto-split via None-guard.

2 unit tests cover both branches.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Refactor fetch handlers + add Find button in `create_model_panel.py`

**Files:**
- Modify: `app/modules/create_model_panel.py`

This task lifts the existing `_on_fetch_rivers` and `_on_fetch_water` handler bodies into reusable async helpers so the Find handler can call them, then adds the Find handler + UI controls + reactive vars.

- [ ] **Step 3.1: Add module-level imports** — insert after panel line 17 (existing `from shapely.validation import make_valid`):

```python
from shapely.geometry import Point
from shapely.ops import unary_union
```

- [ ] **Step 3.2: Add geocoder import** — locate the existing helper-import try/except block (panel lines 82-85, around `query_named_sea_polygon`). Add a parallel block:

```python
try:
    from modules.create_model_geocode import lookup_place_bbox
except ImportError:  # pragma: no cover
    lookup_place_bbox = None  # type: ignore[assignment]
```

- [ ] **Step 3.3: Add UI controls** — find the closing `</div>` of the existing single `cm-toolbar` div in `create_model_ui()` (after the existing buttons, around line 268). Insert a SECOND `cm-toolbar` div directly below:

```python
ui.div(
    {"class": "cm-toolbar"},
    ui.tags.span("Auto:", class_="cm-label"),
    ui.input_text(
        "place_name", None,
        placeholder="Place name…",
        width="180px",
    ),
    ui.input_action_button("find_btn", "🔍 Find",
                           class_="btn btn-cm",
                           title="Look up a place via Nominatim and load Rivers + Water"),
    ui.tags.div(class_="cm-sep"),
    ui.input_action_button("auto_extract_btn", "✨ Auto-extract",
                           class_="btn btn-cm",
                           title="Filter water polygons to the centerline-connected component"),
    ui.tags.div(class_="cm-sep"),
    ui.input_action_button("auto_split_btn", "⚡ Auto-split",
                           class_="btn btn-cm",
                           title="Partition extracted polygons into N reaches by along-channel distance"),
    ui.tags.span("N:", class_="cm-label"),
    ui.div(
        ui.input_numeric("auto_split_n", None, value=4, min=2, max=8, step=1, width="70px"),
        style="display:inline-block; vertical-align:middle;",
    ),
),
```

- [ ] **Step 3.4: Add three new reactive vars** — locate the existing reactive var block in `create_model_server` around panel line 350 (after `_workflow_msg`). Insert:

```python
    _auto_extract_done = reactive.value(False)  # Auto-split prereq
    _mouth_lon_lat = reactive.value(None)        # (lon, lat) for Auto-split fallback
    _finding = reactive.value(False)             # Find debounce
```

- [ ] **Step 3.5: Refactor `_on_fetch_rivers`** — split the existing handler body (panel lines 593-674). Replace lines 593-674 with:

```python
    async def _do_fetch_rivers():
        """Body lift of fetch_rivers — callable from the Find handler too.

        Sets `_auto_extract_done.set(False)` as the first line because fresh
        OSM data invalidates any prior Auto-extract result regardless of who
        triggered the fetch (button or Find).
        """
        _auto_extract_done.set(False)
        country = input.osm_country()
        bbox = _get_view_bbox()
        _fetch_msg.set(f"Extracting river network for {country} (bbox clipped)...")

        import asyncio
        loop = asyncio.get_running_loop()

        def _progress(msg):
            _fetch_msg.set(msg)

        gdf = await loop.run_in_executor(
            None, lambda: query_waterways(country, bbox, progress_cb=_progress)
        )

        if gdf is None or len(gdf) == 0:
            _fetch_msg.set("No river features found. Try zooming in or selecting a different region.")
            return

        is_poly = gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        n_polys = int(is_poly.sum())
        n_lines = len(gdf) - n_polys

        _fetch_msg.set(f"Got {n_polys} river polygons + {n_lines} stream lines. Fetching water bodies...")
        water_gdf = await loop.run_in_executor(
            None, lambda: query_water_bodies(country, bbox)
        )

        if water_gdf is not None and len(water_gdf) > 0:
            _water_gdf.set(water_gdf)
        else:
            water_gdf = None

        clip_types = {"stream", "ditch", "drain"}
        if water_gdf is not None and len(water_gdf) > 0 and n_lines > 0:
            _fetch_msg.set("Clipping small streams to exclude lagoon/lake segments...")
            try:
                valid_geoms = water_gdf.geometry.apply(
                    lambda g: make_valid(g) if g and not g.is_valid else g
                )
                repaired = valid_geoms.apply(lambda g: g.buffer(0) if g and not g.is_empty else g)
                water_union = repaired.unary_union
            except Exception as e:
                logger.warning("Water union failed, skipping stream clipping: %s", e)
                water_union = None

            if water_union is not None:
                keep_mask = []
                for idx, row in gdf.iterrows():
                    geom = row.geometry
                    if geom is None or geom.is_empty:
                        keep_mask.append(False)
                    elif geom.geom_type in ("Polygon", "MultiPolygon"):
                        keep_mask.append(True)
                    elif row.get("waterway", "") not in clip_types:
                        keep_mask.append(True)
                    else:
                        try:
                            inside = geom.intersection(water_union)
                            frac_inside = inside.length / geom.length if geom.length > 0 else 0
                            keep_mask.append(frac_inside < 0.5)
                        except Exception:
                            keep_mask.append(True)
                n_before = len(gdf)
                gdf = gdf[keep_mask].reset_index(drop=True)
                n_clipped = n_before - len(gdf)
                if n_clipped > 0:
                    _fetch_msg.set(f"Clipped {n_clipped} lagoon/lake stream segments.")

        _rivers_gdf.set(gdf)

        await _refresh_map()
        is_poly_final = gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
        water_msg = f" + {len(water_gdf)} water bodies" if water_gdf is not None else ""
        _fetch_msg.set(f"Loaded {int(is_poly_final.sum())} river polygons + {int((~is_poly_final).sum())} stream lines{water_msg}.")

    @reactive.effect
    @reactive.event(input.fetch_rivers)
    async def _on_fetch_rivers():
        await _do_fetch_rivers()
```

- [ ] **Step 3.6: Refactor `_on_fetch_water`** — replace existing lines 676-696 with:

```python
    async def _do_fetch_water():
        """Body lift of fetch_water — callable from Find too.
        Resets _auto_extract_done first since fresh data invalidates prior extract.
        """
        _auto_extract_done.set(False)
        country = input.osm_country()
        bbox = _get_view_bbox()
        _fetch_msg.set(f"Extracting water bodies for {country} (bbox clipped)...")

        import asyncio
        loop = asyncio.get_running_loop()

        gdf = await loop.run_in_executor(
            None, lambda: query_water_bodies(country, bbox)
        )

        if gdf is None or len(gdf) == 0:
            _fetch_msg.set("No water bodies found in this area.")
            return

        _water_gdf.set(gdf)
        await _refresh_map()
        _fetch_msg.set(f"Loaded {len(gdf)} water bodies from local OSM data.")

    @reactive.effect
    @reactive.event(input.fetch_water)
    async def _on_fetch_water():
        await _do_fetch_water()
```

- [ ] **Step 3.7: Add `_on_find` handler** — insert after `_on_fetch_water` (where the new `@reactive.event(input.find_btn)` makes sense in the file's structure):

```python
    @reactive.effect
    @reactive.event(input.find_btn)
    async def _on_find():
        import asyncio
        import math

        if lookup_place_bbox is None:
            ui.notification_show(
                "Geocoder helper unavailable (create_model_geocode failed to import)",
                type="error",
            )
            return
        if _finding():
            return
        _finding.set(True)
        try:
            name = input.place_name() or ""
            if not name.strip():
                ui.notification_show("Type a place name first", type="warning")
                return

            result = await asyncio.to_thread(lookup_place_bbox, name)
            if result is None:
                ui.notification_show(f"No place found for '{name}'", type="warning")
                return

            country_geofabrik, bbox = result
            lon_w, lat_s, lon_e, lat_n = bbox
            cx = (lon_w + lon_e) / 2.0
            cy = (lat_s + lat_n) / 2.0
            span = max(lon_e - lon_w, lat_n - lat_s)
            zoom = int(max(5, min(13, 9 - math.log2(max(span, 0.05)))))

            if country_geofabrik is None:
                ui.notification_show(
                    f"Place found at ({cy:.2f}, {cx:.2f}) but its country has no "
                    "Geofabrik OSM extract; map zoomed but Rivers/Water not auto-fetched",
                    type="warning",
                )
                _pending_fly_to.set((cx, cy, zoom))
                return

            ui.update_select("osm_country", selected=country_geofabrik)
            _pending_fly_to.set((cx, cy, zoom))
            ui.notification_show(
                f"Loaded {name} (lat {cy:.2f}, lon {cx:.2f}). Fetching rivers and water…",
                type="message",
            )
            await _do_fetch_rivers()
        finally:
            _finding.set(False)
```

- [ ] **Step 3.8: Manual smoke test**

```
micromamba run -n shiny python -m shiny run --reload --port 9050 app/app.py
```

In a browser at `http://localhost:9050`:
1. Open Create Model panel — verify the new "Auto:" toolbar row is visible below the existing one.
2. Type "Klaipėda" in the place name field → click 🔍 Find.
3. Verify: Region dropdown updates to "lithuania", map zooms to Klaipėda area, "Loaded Klaipėda…" toast appears, Rivers and Water layers appear within ~10s.
4. Type "xyzzyfoo" → click 🔍 Find → toast "No place found for 'xyzzyfoo'" appears, no other state changes.
5. Click 🔍 Find with empty input → toast "Type a place name first".
6. Stop the server.

- [ ] **Step 3.9: Run pytest to verify no regressions**

```
micromamba run -n shiny python -m pytest tests/ -k "create_model" -v
```
Expected: all PASS (no new tests added in this task; just verifying refactor didn't break existing).

- [ ] **Step 3.10: Commit Task 3**

```
git add app/modules/create_model_panel.py
git commit -m "feat(create_model_panel): add 🔍 Find by name button + lift fetch helpers

Adds the new \"Auto:\" toolbar row with the Find button (Auto-extract +
Auto-split land in the next commit). Refactors _on_fetch_rivers and
_on_fetch_water by lifting their bodies into _do_fetch_rivers() and
_do_fetch_water() helpers — the Find handler calls these directly without
simulating button clicks. Original @reactive.event handlers shrink to
one-line delegates.

_auto_extract_done reset moves into the lifted helpers (was implicit in
the @reactive.event handlers). Both fresh-data paths (button click +
Find) reset the flag — single source of truth.

Three new reactive vars: _auto_extract_done (Auto-split prereq),
_mouth_lon_lat (click-fallback waypoint), _finding (Nominatim ToS
debounce).

UI: place_name text input, find_btn, auto_extract_btn (handler in next
commit), auto_split_btn (handler in next commit), auto_split_n numeric
spinner (default 4, range 2-8 to match REACH_COLORS palette length).

Module-level imports added: Point, unary_union (for the next commit's
_pick_mouth_from_sea); helper try/except for lookup_place_bbox.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `_pick_mouth_from_sea` module-level helper + tests

**Files:**
- Modify: `app/modules/create_model_panel.py` (add module-level helper)
- Create: `tests/test_pick_mouth_from_sea.py`

- [ ] **Step 4.1: Write failing tests** — create `tests/test_pick_mouth_from_sea.py`

```python
"""Unit tests for _pick_mouth_from_sea (create_model_panel module-level helper)."""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, MultiLineString, Polygon

# Ensure app/modules importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))


def _sea_gdf(polygon):
    return gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")


def test_pick_mouth_returns_endpoint_near_sea_offshore_gap():
    """Endpoint sits ~1 km outside the sea polygon, simulating the
    Simojoki regression where the v0.47.0 batch generator's centerline
    endpoint was 945 m offshore. Polygon offset to (2.015, 2.015) so
    (2.0, 2.0) is OUTSIDE the polygon's nearest edge."""
    from modules.create_model_panel import _pick_mouth_from_sea
    line = LineString([(1.0, 1.0), (2.0, 2.0)])
    sea = Polygon([
        (1.99, 1.99), (2.04, 1.99), (2.04, 2.04), (1.99, 2.04), (1.99, 1.99)
    ]).buffer(0.005)  # offset slightly so (2.0, 2.0) is just outside
    # Actually use a clearly-offshore polygon:
    sea = Polygon([
        (2.005, 2.005), (2.05, 2.005), (2.05, 2.05), (2.005, 2.05), (2.005, 2.005)
    ])
    result = _pick_mouth_from_sea([line], _sea_gdf(sea))
    assert result is not None
    lon, lat = result
    assert lon == pytest.approx(2.0, abs=0.001)
    assert lat == pytest.approx(2.0, abs=0.001)


def test_pick_mouth_returns_none_if_far_from_sea():
    from modules.create_model_panel import _pick_mouth_from_sea
    line = LineString([(1.0, 1.0), (2.0, 2.0)])
    # Sea polygon ~50 km away (>>5 km threshold)
    sea = Polygon([
        (5.0, 5.0), (5.5, 5.0), (5.5, 5.5), (5.0, 5.5), (5.0, 5.0)
    ])
    result = _pick_mouth_from_sea([line], _sea_gdf(sea))
    assert result is None


def test_pick_mouth_handles_multilinestring():
    from modules.create_model_panel import _pick_mouth_from_sea
    line1 = LineString([(0.0, 0.0), (1.0, 1.0)])
    line2 = LineString([(1.0, 1.0), (2.0, 2.0)])
    mls = MultiLineString([line1, line2])
    sea = Polygon([
        (2.005, 2.005), (2.05, 2.005), (2.05, 2.05), (2.005, 2.05), (2.005, 2.005)
    ])
    result = _pick_mouth_from_sea([mls], _sea_gdf(sea))
    assert result is not None
    lon, lat = result
    # Should pick the (2.0, 2.0) endpoint of the MultiLineString — the closest one to sea
    assert lon == pytest.approx(2.0, abs=0.001)
    assert lat == pytest.approx(2.0, abs=0.001)


def test_pick_mouth_handles_unavailable_detect_utm_epsg(monkeypatch):
    from modules import create_model_panel as panel_mod
    monkeypatch.setattr(panel_mod, "detect_utm_epsg", None)
    line = LineString([(1.0, 1.0), (2.0, 2.0)])
    sea = Polygon([
        (2.005, 2.005), (2.05, 2.005), (2.05, 2.05), (2.005, 2.05), (2.005, 2.005)
    ])
    result = panel_mod._pick_mouth_from_sea([line], _sea_gdf(sea))
    assert result is None
```

- [ ] **Step 4.2: Run tests to verify they fail**

```
micromamba run -n shiny python -m pytest tests/test_pick_mouth_from_sea.py -v
```
Expected: 4 FAIL with `ImportError: cannot import name '_pick_mouth_from_sea'`.

- [ ] **Step 4.3: Add `_pick_mouth_from_sea` to `create_model_panel.py`**

Insert at module level immediately AFTER the `REACH_COLORS` block (around panel line 80) and BEFORE the `try: from modules.create_model_marine ...` block:

```python
def _pick_mouth_from_sea(centerline_geoms, sea_gdf):
    """Pick the centerline endpoint closest to any sea polygon.

    Args:
      centerline_geoms: list of LineString / MultiLineString.
      sea_gdf: GeoDataFrame of one or more sea polygons (EPSG:4326).

    Returns:
      (lon, lat) WGS84 of the closest endpoint, or None if all endpoints
      are >5 km from any sea polygon, or if `detect_utm_epsg` is unavailable.
    """
    if detect_utm_epsg is None:
        return None
    if not centerline_geoms or len(sea_gdf) == 0:
        return None

    centerline = unary_union(centerline_geoms)
    sea_union = unary_union(list(sea_gdf.geometry))

    if centerline.geom_type == "LineString":
        endpoints = [Point(centerline.coords[0]), Point(centerline.coords[-1])]
    elif centerline.geom_type == "MultiLineString":
        endpoints = []
        for sub in centerline.geoms:
            endpoints.append(Point(sub.coords[0]))
            endpoints.append(Point(sub.coords[-1]))
    else:
        return None

    centroid = centerline.centroid
    utm_epsg = detect_utm_epsg(centroid.x, centroid.y)
    ep_gdf = gpd.GeoDataFrame(
        geometry=endpoints, crs="EPSG:4326"
    ).to_crs(epsg=utm_epsg).reset_index(drop=True)
    sea_utm = gpd.GeoDataFrame(
        geometry=[sea_union], crs="EPSG:4326"
    ).to_crs(epsg=utm_epsg)
    distances = ep_gdf.geometry.distance(sea_utm.geometry.iloc[0])

    min_pos = int(distances.values.argmin())
    if distances.iloc[min_pos] > 5000:
        return None
    closest = endpoints[min_pos]
    return (closest.x, closest.y)
```

- [ ] **Step 4.4: Run tests to verify they pass**

```
micromamba run -n shiny python -m pytest tests/test_pick_mouth_from_sea.py -v
```
Expected: 4 PASS.

(No commit yet — Task 5 adds the Auto-extract / Auto-split handlers that consume this helper, all in one logical commit.)

---

## Task 5: Auto-extract + Auto-split handlers + click-mode state machine

**Files:**
- Modify: `app/modules/create_model_panel.py`

- [ ] **Step 5.1: Add helper imports for create_model_river** — find the existing helper-import try/except block in `create_model_panel.py` (where `query_named_sea_polygon` and `lookup_place_bbox` are imported from Task 3). Add a parallel block:

```python
try:
    from modules.create_model_river import (
        filter_polygons_by_centerline_connectivity,
        partition_polygons_along_channel,
        default_reach_names,
    )
except ImportError:  # pragma: no cover
    filter_polygons_by_centerline_connectivity = None
    partition_polygons_along_channel = None
    default_reach_names = None
```

- [ ] **Step 5.2: Add `_on_auto_extract` handler** — insert after `_on_find` (Task 3's handler):

```python
    @reactive.effect
    @reactive.event(input.auto_extract_btn)
    async def _on_auto_extract():
        if filter_polygons_by_centerline_connectivity is None:
            ui.notification_show("create_model_river module not available", type="error")
            return
        if _rivers_gdf() is None:
            ui.notification_show("Click 🌊 Rivers first to load the centerline", type="warning")
            return
        if _water_gdf() is None:
            ui.notification_show("Click 💧 Water first to load polygons", type="warning")
            return

        rivers_gdf = _rivers_gdf()
        water_gdf  = _water_gdf()
        n_before   = len(water_gdf)

        centerline_mask = rivers_gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])
        centerline_geoms = list(rivers_gdf[centerline_mask].geometry)
        if not centerline_geoms:
            ui.notification_show(
                "Rivers layer has no LineString geometries — cannot extract main system",
                type="warning",
            )
            return

        kept = filter_polygons_by_centerline_connectivity(
            centerline_geoms,
            list(water_gdf.geometry),
            tolerance_deg=0.0005,
            max_polys=2000,
            label="auto-extract",
        )
        if not kept:
            ui.notification_show(
                "No connected polygons — try lowering Strahler threshold or "
                "checking that Rivers + Water cover the same area",
                type="warning",
            )
            return

        # Preserve original attribute columns (nameText etc.) by id-based mask
        kept_ids = {id(g) for g in kept}
        mask = water_gdf.geometry.apply(lambda g: id(g) in kept_ids)
        filtered_gdf = water_gdf[mask].reset_index(drop=True)
        _water_gdf.set(filtered_gdf)
        _auto_extract_done.set(True)

        await _refresh_map()
        ui.notification_show(
            f"Kept {len(kept)} of {n_before} polygons in the main river system.",
            type="message",
        )
```

- [ ] **Step 5.3: Add `_on_auto_split` handler** — insert after `_on_auto_extract`:

```python
    @reactive.effect
    @reactive.event(input.auto_split_btn)
    async def _on_auto_split():
        if partition_polygons_along_channel is None or default_reach_names is None:
            ui.notification_show("create_model_river module not available", type="error")
            return
        if not _auto_extract_done():
            ui.notification_show("Click ✨ Auto-extract first", type="warning")
            return

        n_reaches = int(input.auto_split_n() or 4)
        rivers_gdf = _rivers_gdf()
        water_gdf  = _water_gdf()

        centerline_mask = rivers_gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])
        centerline_geoms = list(rivers_gdf[centerline_mask].geometry)
        polys_list = list(water_gdf.geometry)

        if n_reaches > len(polys_list):
            ui.notification_show(
                f"N={n_reaches} exceeds polygon count ({len(polys_list)}); "
                "some reaches will be empty. Consider lowering N.",
                type="warning",
            )

        # Determine mouth waypoint
        sea_gdf = _sea_gdf()
        if sea_gdf is not None and len(sea_gdf) > 0:
            mouth = _pick_mouth_from_sea(centerline_geoms, sea_gdf)
            if mouth is None:
                ui.notification_show(
                    "River centerline doesn't reach any sea polygon — click on map to set mouth",
                    type="warning",
                )
                _current_reach_name.set("")
                _selection_mode.set("mouth_pick")
                _workflow_msg.set("Click on the map to set the river mouth, then ⚡ Auto-split again")
                return
        elif _mouth_lon_lat() is not None:
            mouth = _mouth_lon_lat()
        else:
            _current_reach_name.set("")
            _selection_mode.set("mouth_pick")
            _workflow_msg.set("Click on the map to set the river mouth, then ⚡ Auto-split again")
            return

        groups = partition_polygons_along_channel(
            centerline_geoms, polys_list,
            mouth_lon_lat=mouth, n_reaches=n_reaches,
        )
        names = default_reach_names(n_reaches)

        reaches = {}
        for i, polys in enumerate(groups):
            if not polys:
                continue
            reaches[names[i]] = {
                "segments": polys,
                "properties": [{} for _ in polys],
                "color": REACH_COLORS[i % len(REACH_COLORS)],
                "type": "water",
            }
        _reaches_dict.set(reaches)
        _cells_gdf.set(None)
        _mouth_lon_lat.set(None)

        await _refresh_map()
        counts_str = ", ".join(f"{n} ({len(reaches[n]['segments'])})" for n in names if n in reaches)
        ui.notification_show(
            f"Split into {len(reaches)} reaches: {counts_str}.",
            type="message",
        )
```

- [ ] **Step 5.4: Edit `_on_map_click`** — insert mouth_pick branch between the existing `if not sel:` early-return at panel line 883 and the `from shapely.geometry import Point as _Pt` at line 885:

```python
        # NEW: mouth_pick branch handled before reach_name guard (no associated reach)
        if sel == "mouth_pick":
            _mouth_lon_lat.set((lon, lat))
            _selection_mode.set("")
            _workflow_msg.set(
                f"River mouth set to ({lon:.4f}, {lat:.4f}). Click ⚡ Auto-split to run."
            )
            return
```

- [ ] **Step 5.5: Edit `_on_clear_reaches`** — find the existing handler at panel line 783-790. Insert `_mouth_lon_lat.set(None)` immediately after the existing `_selection_mode.set("")` line (was line 787):

```python
        _reaches_dict.set({})
        _cells_gdf.set(None)
        _selection_mode.set("")
        _mouth_lon_lat.set(None)  # NEW: also clear pending mouth pick
        _current_reach_name.set("")
        _workflow_msg.set("All reaches and cells cleared.")
        await _refresh_map()
```

- [ ] **Step 5.6: Run tests for the module-level helper**

```
micromamba run -n shiny python -m pytest tests/test_pick_mouth_from_sea.py -v
```
Expected: 4 PASS.

- [ ] **Step 5.7: Run full Create Model test suite**

```
micromamba run -n shiny python -m pytest tests/ -k "create_model or pick_mouth" -v
```
Expected: all PASS, no regressions.

- [ ] **Step 5.8: Manual smoke test — full pipeline**

```
micromamba run -n shiny python -m shiny run --reload --port 9050 app/app.py
```

In a browser:
1. Type "Klaipėda" → 🔍 Find → wait for Rivers + Water layers to appear.
2. Click ✨ Auto-extract → toast shows polygon count drop ("Kept N of M polygons in the main river system."); map redraws to show only connected-component water polygons.
3. Click ⚡ Auto-split with N=4 (default) → toast "Split into 4 reaches: Mouth (X), Lower (Y), Middle (Z), Upper (W)."; 4 colored polygon overlays appear over the water layer.
4. Change N to 2 → click ⚡ Auto-split again → toast "Split into 2 reaches"; the 4-reach overlay is replaced by 2 reaches.
5. Click 🗑 Clear → all reaches and cells clear.
6. Click 🌊 Rivers (without Sea fetched first); skip Sea fetch; click ✨ Auto-extract; click ⚡ Auto-split → toast "Click on the map to set the river mouth, then ⚡ Auto-split again"; click somewhere on the map → workflow message shows "River mouth set to..."; click ⚡ Auto-split again → split runs.
7. Stop server.

- [ ] **Step 5.9: Commit Task 5**

```
git add app/modules/create_model_panel.py tests/test_pick_mouth_from_sea.py
git commit -m "feat(create_model_panel): add Auto-extract + Auto-split buttons

Wires the v0.47.0 helper modules (filter_polygons_by_centerline_connectivity
+ partition_polygons_along_channel) into two new buttons:

✨ Auto-extract drops disconnected water polygons from the loaded set
(BFS from rivers centerline, 0.0005° tolerance, max 2000 polys). Preserves
original attribute columns (nameText etc.) by id-based mask filter.

⚡ Auto-split partitions the extracted polygons into N reaches by
along-channel distance from the river mouth. Mouth = closest centerline
endpoint to any Sea polygon (UTM-meters distance, 5km threshold). If no
Sea fetched, falls back to click-mouth mode via _selection_mode.set('mouth_pick').
Reach names: Mouth/Lower/Middle/Upper for N=4, Reach1..ReachN otherwise.

New module-level helper _pick_mouth_from_sea (placed near REACH_COLORS
for testability) implements the multi-LineString + UTM distance
algorithm. None-guards detect_utm_epsg unavailable + empty inputs +
GeometryCollection edge cases.

Edits to existing _on_map_click (mouth_pick branch BEFORE the reach_name
guard) and _on_clear_reaches (also reset _mouth_lon_lat).

4 unit tests for _pick_mouth_from_sea cover offshore-gap (Simojoki-class
regression), far-from-sea rejection, MultiLineString endpoint enumeration,
and detect_utm_epsg=None graceful degradation.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Release commit + tag

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/salmopy/__init__.py`
- Modify: `CHANGELOG.md`

- [ ] **Step 6.1: Bump version in `pyproject.toml`** — line 7

Change `version = "0.49.0"` to `version = "0.50.0"`.

- [ ] **Step 6.2: Bump version in `src/salmopy/__init__.py`** — line 3

Change `__version__ = "0.49.0"` to `__version__ = "0.50.0"`.

- [ ] **Step 6.3: Prepend CHANGELOG entry**

Add at the top of `CHANGELOG.md`:

```markdown
## [0.50.0] — 2026-04-26

### Added
- **🔍 Find by name** button in Create Model panel. Looks up a place via
  Nominatim → sets Region dropdown → zooms map → auto-loads Rivers + Water.
- **✨ Auto-extract** button. Filters loaded water polygons to the
  centerline-connected component using `filter_polygons_by_centerline_connectivity`
  (v0.47.0 helper).
- **⚡ Auto-split** button. Partitions extracted polygons into N reaches
  by along-channel distance from the mouth. Mouth auto-detected from Sea
  polygon if fetched, else click-mouth fallback.
- New module `app/modules/create_model_geocode.py` (Nominatim wrapper).
- New helper `default_reach_names(n_reaches)` in `create_model_river.py`
  (Mouth/Lower/Middle/Upper for N=4, Reach1..ReachN otherwise).

### Tests
- 7 cases for `lookup_place_bbox` (network error, special chars, ISO-2 mapping).
- 2 cases for `default_reach_names`.
- 4 cases for `_pick_mouth_from_sea` (offshore gap, far-from-sea rejection,
  MultiLineString, detect_utm_epsg=None).

### Notes
- Closes PR-3 deferred from v0.47.0 follow-ups list.
- v0.51.0 (next): use these buttons end-to-end to add the Danė river
  to `example_baltic`.
```

- [ ] **Step 6.4: Verify tests one final time**

```
micromamba run -n shiny python -m pytest tests/ -k "create_model or pick_mouth or default_reach" -v
```
Expected: all PASS.

- [ ] **Step 6.5: Commit Task 6**

```
git add pyproject.toml src/salmopy/__init__.py CHANGELOG.md
git commit -m "release(v0.50.0): Create Model UI buttons

Adds Find by name, Auto-extract, and Auto-split buttons to the Create
Model panel. Closes PR-3 deferred from v0.47.0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6.6: Create annotated tag**

```
git tag -a v0.50.0 -m "v0.50.0: Create Model UI buttons (Find by name + Auto-extract + Auto-split)"
```

- [ ] **Step 6.7: Verify final state**

```
git log --oneline -10
git tag -l v0.50.0
```

Expected:
- HEAD points to release commit.
- Tag `v0.50.0` resolves to that commit.
- 6 implementation commits on the branch (1 per task).
