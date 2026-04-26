# v0.50.0 — Create Model UI buttons (Find by name + Auto-extract + Auto-split)

**Status:** Design — pending review
**Date:** 2026-04-26
**Origin:** PR-3 deferred from v0.47.0 follow-ups list (also flagged in v0.48.0/v0.49.0 release notes).

## Summary

Add three new buttons to the Create Model panel that wire the v0.47.0 helper modules
(`app/modules/create_model_marine.py`, `create_model_river.py`) into a discoverable UX:

1. **🔍 Find by name** — Nominatim place lookup → set Region dropdown + zoom map + auto-trigger fetch_rivers + fetch_water.
2. **✨ Auto-extract** — `filter_polygons_by_centerline_connectivity` on the loaded Rivers + Water layers; replaces the unfiltered Water polygons with the connected-component subset.
3. **⚡ Auto-split** — `partition_polygons_along_channel` partitions the extracted polygons into N reaches by along-channel distance from the river mouth.

These buttons collapse the manual workflow used in v0.45–v0.47 (find a place on
Google Maps → copy waypoint → hand-edit `RIVERS` table in `_generate_wgbast_physical_domains.py`
→ regenerate fixture) into 3 clicks inside the panel. v0.51.0 will exercise the buttons
end-to-end by adding the Danė river to `example_baltic`.

## Out of scope (deferred)

- Danė fixture itself (v0.51.0).
- Tornionjoki juvenile-growth calibration (v0.52.0).
- Reach renaming UI (already handled by Edit Model panel since v0.45.3).
- Per-reach `frac_spawn` / `BalticCoast` calibration — Auto-split produces reach
  geometry only.
- Playwright e2e tests — no precedent in this codebase; defer until v0.51.0
  when Danė is the natural full-pipeline fixture.
- Undo for destructive Auto-extract polygon replacement — Edit Model handles
  undo; Create Model is a one-shot wizard.

## Architecture

**One new toolbar row** added below the existing single-row `cm-toolbar`:

```
Auto:  [text input: Place name        ] 🔍 Find  ·  ✨ Auto-extract  ·  ⚡ Auto-split  [N: 4 ⬍]
```

**Three new reactive event handlers** in `app/modules/create_model_panel.py`
(one per button), all soft-fail with `ui.notification_show` toasts.

**Reactive vars reused** (verified against `create_model_panel.py:324-350`):
- `_rivers_gdf = reactive.value(None)` — Rivers OSM GDF (truthy via `is not None`).
- `_water_gdf = reactive.value(None)` — Water OSM GDF.
- `_sea_gdf = reactive.value(None)` — Sea polygon GDF.
- `_reaches_dict = reactive.value({})` — `{reach_name: [LineString, ...]}` — Auto-split writes here.
- `_selection_mode = reactive.value("")` — currently `""/"river"/"lagoon"/"sea"`; add fourth value `"mouth_pick"` for click-mouth fallback (mutual exclusion with existing values is automatic).
- `_pending_fly_to = reactive.value(None)` — `(lon, lat, zoom)` tuple — existing
  mechanism for programmatic map navigation. Find handler writes here.

**One new reactive var** added:
- `_auto_extract_done = reactive.value(False)` — set to True after Auto-extract
  successfully runs; reset to False when `_water_gdf` is reassigned by a fresh
  fetch_water click. Auto-split's prereq check reads this flag.

**One new helper module** `app/modules/create_model_geocode.py` (~80 LOC):

- `lookup_place_bbox(name: str, timeout_s: int = 10) -> tuple[str | None, tuple[float, float, float, float]] | None`
  — Wraps Nominatim API. Returns `(country_geofabrik_name, bbox_wgs84)` on success,
  `(None, bbox)` if the country has no Geofabrik extract, or `None` on
  empty input / network failure / 0 results.
- `_ISO_TO_GEOFABRIK: dict[str, str]` — ISO 3166-1 alpha-2 to Geofabrik country
  name (e.g., `"lt" → "lithuania"`). Coverage matches the existing
  `GEOFABRIK_COUNTRIES` set in `create_model_osm.py`.
- Pattern mirrors `query_named_sea_polygon` from v0.47.0:
  - User-Agent header per Nominatim ToS, format: `f"inSTREAM-py/{salmopy.__version__} (arturas.razinkovas-baziukas@ku.lt)"`. The version is read once at module import time from `src/salmopy/__init__.py`.
  - `requests.get` with `timeout_s` and `with`-block to ensure connection-pool
    socket return on Windows.
  - Content-Length cap (5 MB — Nominatim responses are typically <50 KB).
  - Exception logging via `logging.warning` (class + message) before swallowing.

**One smart-naming helper** added to `app/modules/create_model_river.py`:

- `default_reach_names(n_reaches: int) -> list[str]` — Returns
  `["Mouth", "Lower", "Middle", "Upper"]` when `n_reaches == 4`, else
  `[f"Reach{i+1}" for i in range(n_reaches)]`.

## Components & data flow

### 🔍 Find by name

```
User types "Klaipėda" → clicks 🔍 Find
  ↓
lookup_place_bbox("Klaipėda")
  → GET https://nominatim.openstreetmap.org/search?q=Klaipėda&format=json&limit=1
  → returns ("lithuania", (21.05, 55.65, 21.25, 55.78))
  ↓
1. ui.update_select("osm_country", selected="lithuania")
2. _pending_fly_to.set((bbox_center_lon, bbox_center_lat, 10))
   — the existing fly-to effect handler at create_model_panel.py:758 picks this
   up and calls _widget.update(session, layers, view_state=…)
3. await _do_fetch_rivers(session)  # see refactor note below
4. await _do_fetch_water(session)
  ↓
Toast: "Loaded Klaipėda, Lithuania (lat 55.71, lon 21.15). Fetching rivers and water…"
```

**Implementation note — programmatic fetch trigger**: the existing
`@reactive.event(input.fetch_rivers)` handler (panel line 593) and
`input.fetch_water` handler (line 676) need to be callable from the Find
handler without simulating a button click. The plan refactors each handler
body into a `async def _do_fetch_rivers(session)` (and `_do_fetch_water`)
helper that takes the session as an argument and updates `_rivers_gdf` /
`_water_gdf`. The original `@reactive.event` handlers shrink to a one-line
delegating call: `await _do_fetch_rivers(session)`. The Find handler awaits
both helpers sequentially. **No new reactive counter vars** — direct
function calls only. Risk is small (the refactor is purely lifting code into
a function); the regression test is the manual checklist (steps 1–6).

### ✨ Auto-extract

```
Prereq: _rivers_gdf() is not None AND _water_gdf() is not None
  ↓
centerline = _rivers_gdf().geometry  (LineString sequence)
polygons   = _water_gdf().geometry   (Polygon/MultiPolygon sequence)
  ↓
filter_polygons_by_centerline_connectivity(
    centerline, polygons,
    tolerance_deg=0.0005,  # same as v0.45.3 / WGBAST batch generator
    max_polys=2000,
    label="auto-extract",
)  → returns kept polygons
  ↓
filtered_gdf = gpd.GeoDataFrame(geometry=kept_polygons, crs=_water_gdf().crs)
_water_gdf.set(filtered_gdf)
_auto_extract_done.set(True)
  → existing render_water_layer effect (panel line ~595) re-fires on _water_gdf change
  ↓
Toast: "Kept 26 of 92 polygons in the main river system."
```

### ⚡ Auto-split

```
Prereq: _auto_extract_done() is True
  ↓
mouth_lon_lat = pick from _sea_gdf() if _sea_gdf() is not None
                else enter "click mouth" mode (set _selection_mode("mouth_pick"))
  ↓
groups = partition_polygons_along_channel(
    _rivers_gdf().geometry, _water_gdf().geometry,
    mouth_lon_lat=mouth,
    n_reaches=int(input.auto_split_n()),
)
names = default_reach_names(N)  # ["Mouth","Lower","Middle","Upper"] for N=4
  ↓
reaches = {names[i]: groups[i] for i in range(N) if groups[i]}
_reaches_dict.set(reaches)  # existing reactive var; render_reach_layer
                            # effect re-fires on change
  ↓
Toast: "Split into 4 reaches: Mouth (12), Lower (15), Middle (8), Upper (5)."
```

**Reach color palette**: a hardcoded module-level constant in
`create_model_panel.py`:
```python
_REACH_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
    "#bcbd22", "#17becf",  # matplotlib tab10 hex values, no dependency
]
```
Indexed cyclically by reach order (`_REACH_COLORS[i % 10]`). No matplotlib
import needed.

**Mouth-from-Sea-polygon algorithm** (when fetched_sea() is True):

1. Get sea polygon from current reactive state.
2. Use `_orient_centerline_mouth_to_source` (already in `create_model_river.py`
   as a private helper) to get a single oriented LineString.
3. Compare both endpoints' distance to the sea polygon — pick the closer
   endpoint as the mouth waypoint.
4. If both endpoints are >5000 m from the sea (in UTM meters), warn via
   toast: "River centerline doesn't reach the sea — using closest endpoint
   anyway." Continue with the closer one (graceful degradation).

This needs `_orient_centerline_mouth_to_source` to be promoted to a public
function (rename: drop the leading underscore) — it's already battle-tested
by the WGBAST batch generator since v0.47.0.

**Click-mouth mode** (Auto-split fallback when `_sea_gdf() is None`):

```
Initial:   _selection_mode() == "" or "river"/"lagoon"/"sea"
After ⚡ click with _sea_gdf() is None:
  → _selection_mode.set("mouth_pick")
  → status text: "Click on the map to set the river mouth, then ⚡ again"
  → existing @reactive.event(input.map_click_trigger) handler at panel line 859
    branches on _selection_mode() — add "mouth_pick" branch that:
      1. captures click lon/lat into a new reactive var _mouth_lon_lat
      2. resets _selection_mode.set("")
  → next ⚡ click reads _mouth_lon_lat() and runs split
```

Piggybacks on the existing `_selection_mode` reactive var (panel line 348)
and `map_click_trigger` JS bridge — same pattern as `sel_river_btn` /
`sel_lagoon_btn` / `sel_sea_btn` (proven since v0.30.x). Mutual exclusion
with the three sel_* modes is automatic since they all write to the same
reactive var.

**One additional reactive var** added for click-mouth mode:
- `_mouth_lon_lat = reactive.value(None)` — `(lon, lat)` tuple set by the
  click-mode handler. Read by Auto-split when `_sea_gdf() is None`.

## Error handling

### Find by name

| Case | Behavior |
|------|----------|
| Empty input | Toast "Type a place name first" — no API call |
| Nominatim 0 results | Toast "No place found for '<name>'" |
| Country code unknown to Geofabrik | Toast "Country '<X>' has no Geofabrik OSM extract; map zoomed but Rivers/Water not auto-fetched". Map zoom still happens; Region dropdown unchanged. |
| Network/HTTP error | Toast "Geocoding failed (check connection)"; log exception class+message |
| Rate limit (1 req/sec ToS) | One-shot per click. No retry loop. User-Agent header set. |

### Auto-extract

| Case | Behavior |
|------|----------|
| `_rivers_gdf() is None` | Toast "Click 🌊 Rivers first to load the centerline" |
| `_water_gdf() is None` | Toast "Click 💧 Water first to load polygons" |
| BFS returns empty (centerline doesn't touch any polygon) | Toast "No connected polygons — try lowering Strahler threshold or checking that Rivers + Water cover the same area"; `_auto_extract_done` stays False |
| Single polygon (no-op) | Run anyway; toast "Kept 1 of 1 polygons"; `_auto_extract_done.set(True)` |

### Auto-split

| Case | Behavior |
|------|----------|
| `_auto_extract_done() is False` | Toast "Click ✨ Auto-extract first" |
| `_sea_gdf() is None and _mouth_lon_lat() is None` (no Sea, no prior click) | Set `_selection_mode.set("mouth_pick")`; status text "Click on the map to set the river mouth, then ⚡ again". Skip split this time. |
| N > polygon count | Helper returns mostly-empty groups; toast warning "Only M polygons found — last (N–M) reaches will be empty. Try fewer reaches." Non-fatal. |
| N=1 | Single reach with all polygons; toast "Created 1 reach (try N≥2 for spatial split)" |
| Re-running Auto-split | Overwrites `_reaches_dict`; toast "Re-split into N reaches (previous split discarded)" |
| `fetch_water` clicked after Auto-extract (resets `_water_gdf`) | Existing `_water_gdf` watch effect resets `_auto_extract_done.set(False)` — Auto-split prereq fails until user re-runs Auto-extract |

## Testing

### New unit tests — `tests/test_create_model_geocode.py` (~80 LOC, 6 cases)

| Test | Mocks | Asserts |
|------|-------|---------|
| `test_lookup_place_bbox_klaipeda_success` | `requests.get` returns Nominatim JSON for Klaipėda | returns `("lithuania", (lon_min, lat_min, lon_max, lat_max))` with bbox in correct order |
| `test_lookup_place_bbox_empty_results` | `requests.get` returns `[]` | returns `None` |
| `test_lookup_place_bbox_unknown_country_code` | Nominatim returns ISO-2 not in `_ISO_TO_GEOFABRIK` | returns `(None, bbox)` — caller handles "no extract" toast |
| `test_lookup_place_bbox_network_error` | `requests.get` raises `ConnectionError` | returns `None`, logs warning |
| `test_lookup_place_bbox_empty_input` | none | returns `None` (no API call made — assert mock not called) |
| `test_lookup_place_bbox_special_chars` | input `"Mörrumsån"` | mocked URL contains `M%C3%B6rrums%C3%A5n` (URL-encoded UTF-8) |

### Smart-naming helper test — extend `tests/test_create_model_river.py` (+2 cases)

| Test | Asserts |
|------|---------|
| `test_default_reach_names_n4` | helper returns `["Mouth", "Lower", "Middle", "Upper"]` |
| `test_default_reach_names_other_n` | N=3 → `["Reach1", "Reach2", "Reach3"]`; N=9 → `["Reach1", …, "Reach9"]`; N=2 → `["Reach1", "Reach2"]` |

### Reused tests (no changes needed)

- `test_create_model_marine.py` (8 cases, v0.47.0)
- `test_create_model_river.py` (9 cases pre-existing, +2 from above)

### Manual verification checklist

Run before commit (and again post-deploy on laguna):

1. `shiny run app/app.py` → Create Model panel loads with new "Auto:" row visible.
2. Type "Klaipėda" → 🔍 Find → Region dropdown updates to "lithuania", map zooms to Klaipėda area, Rivers + Water layers appear within 10 s.
3. Click ✨ Auto-extract → polygon count drops in toast (e.g., "Kept 26 of 92"); map updates to show only the connected-component water polygons.
4. Click ⚡ Auto-split with N=4 → 4 reaches appear in different colors, reach table shows 4 rows with names "Mouth/Lower/Middle/Upper".
5. Click ⚡ Auto-split again with N=2 → resplit works; toast confirms "previous split discarded".
6. Edge case: type a fake place ("xyzzyfoo") → toast "No place found for 'xyzzyfoo'", panel state unchanged.

## Commit cadence

Per the v0.47–v0.49 pattern:

1. `feat(create_model_geocode): add lookup_place_bbox helper + tests` (new module + tests)
2. `feat(create_model_panel): add 🔍 Find by name button` (Find handler + auto-fetch trigger refactor)
3. `feat(create_model_panel): add ✨ Auto-extract + ⚡ Auto-split buttons` (extract + split handlers + click-mode state machine)
4. `release(v0.50.0): Create Model UI buttons` (version bump + CHANGELOG + annotated tag)

## Required dependencies

No new dependencies. Uses already-present:
- `requests` (already used by `query_named_sea_polygon`)
- `shapely ≥ 2.0` (already used; `_orient_centerline_mouth_to_source` is shapely-based)
- `geopandas ≥ 1.0` (already used)

## Risks / open questions for plan-time review

1. **Fetch handler refactor**: extracting `_do_fetch_rivers(session)` and
   `_do_fetch_water(session)` from the existing `@reactive.event` handlers
   (panel lines 593, 676) is a mechanical lift. Risk: capturing closure
   variables (e.g., `input.osm_country()`, `input.strahler_min()`) — the
   helpers must read these from `input` directly, not from a captured snapshot.
   Plan to verify by reading lines 593–700 in detail before refactoring.
2. **`_orient_centerline_mouth_to_source` promotion**: the helper is private
   in `create_model_river.py`. Promoting to public means it's part of the
   v0.50.0 API contract; future changes need backwards-compat. Acceptable
   risk — the function is small and the algorithm is stable since v0.45.3.
   Plan to add a one-line module docstring entry noting the public surface.
3. **`_auto_extract_done` reset on fresh fetch**: the spec says fetch_water
   re-running resets `_auto_extract_done` to False. The plan must add this
   reset either as an explicit `_auto_extract_done.set(False)` line at the
   end of `_do_fetch_water`, or via a separate `@reactive.effect` that
   watches `_water_gdf` and resets the flag on any change other than
   Auto-extract's own assignment (using a "this assignment is from auto-extract"
   sentinel — fragile). Plan picks the explicit reset (option A).
4. **Nominatim ToS compliance**: User-Agent must include contact info.
   `f"inSTREAM-py/{salmopy.__version__} (arturas.razinkovas-baziukas@ku.lt)"`
   per CLAUDE.md identity. Plan must verify import path
   (`from salmopy import __version__` works from `app/modules/`).
5. **Map fly-to mechanism**: existing `_pending_fly_to = reactive.value(None)`
   at panel line 738 is the contract; Find handler writes
   `_pending_fly_to.set((lon, lat, zoom))`. Plan to read the consumer effect
   handler around line 758 to confirm the signature exactly.
6. **`_REACH_COLORS` placement**: a module-level constant in
   `create_model_panel.py` near the top (after imports). Plan to verify no
   name collision with existing constants.
