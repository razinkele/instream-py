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
(one per button), all soft-fail with `ui.notification_show` toasts. No new
reactive vars — the existing `fetched_rivers()`, `fetched_water()`, `fetched_sea()`
flags are reused for prerequisite checks.

**One new helper module** `app/modules/create_model_geocode.py` (~80 LOC):

- `lookup_place_bbox(name: str, timeout_s: int = 10) -> tuple[str | None, tuple[float, float, float, float]] | None`
  — Wraps Nominatim API. Returns `(country_geofabrik_name, bbox_wgs84)` on success,
  `(None, bbox)` if the country has no Geofabrik extract, or `None` on
  empty input / network failure / 0 results.
- `_ISO_TO_GEOFABRIK: dict[str, str]` — ISO 3166-1 alpha-2 to Geofabrik country
  name (e.g., `"lt" → "lithuania"`). Coverage matches the existing
  `GEOFABRIK_COUNTRIES` set in `create_model_osm.py`.
- Pattern mirrors `query_named_sea_polygon` from v0.47.0:
  - User-Agent header per Nominatim ToS (`"inSTREAM-py/<version> (arturas.razinkovas-baziukas@ku.lt)"`).
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
2. await _widget.update(session, layers=[...]) at bbox center, zoom=10
3. set programmatic-trigger reactive var → existing fetch_rivers handler fires
4. set programmatic-trigger reactive var → existing fetch_water handler fires
  ↓
Toast: "Loaded Klaipėda, Lithuania (lat 55.71, lon 21.15). Fetching rivers and water…"
```

Implementation note: the existing `@reactive.event(input.fetch_rivers)` handler
watches a button counter. To trigger it programmatically without a real
click, introduce a separate `_programmatic_fetch_rivers = reactive.value(0)`
counter and a second `@reactive.event(_programmatic_fetch_rivers)` handler
that calls the same internal coroutine. (Or simpler: refactor the existing
handler body into a `_do_fetch_rivers()` async function that both handlers
call.) The plan will lock this in.

### ✨ Auto-extract

```
Prereq: fetched_rivers() AND fetched_water() both True
  ↓
centerline = current rivers GeoDataFrame.geometry  (already in reactive state)
polygons   = current water GeoDataFrame.geometry   (already in reactive state)
  ↓
filter_polygons_by_centerline_connectivity(
    centerline, polygons,
    tolerance_deg=0.0005,  # same as v0.45.3 / WGBAST batch generator
    max_polys=2000,
    label="auto-extract",
)  → returns kept polygons
  ↓
Replace fetched_water reactive var GDF with kept polygons
Re-render water layer on map (existing helper)
  ↓
Toast: "Kept 26 of 92 polygons in the main river system."
```

### ⚡ Auto-split

```
Prereq: Auto-extract has run (fetched_water is the filtered subset)
  ↓
mouth_lon_lat = pick from Sea polygon if fetched_sea() else enter "click mouth" mode
  ↓
groups = partition_polygons_along_channel(
    centerline, polygons,
    mouth_lon_lat=mouth,
    n_reaches=int(input.auto_split_n()),
)
names = default_reach_names(N)
  ↓
Update reaches reactive var: list of {name, polygons, color} dicts
  (one entry per reach, polygons = groups[i], color = matplotlib tab10[i])
Re-render map: each reach in a different color
Update reach table at bottom of panel
  ↓
Toast: "Split into 4 reaches: Mouth (12), Lower (15), Middle (8), Upper (5)."
```

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

**Click-mouth mode** (Auto-split fallback when fetched_sea() is False):

```
Initial:   normal map clicks → existing behavior (sel_river_btn etc.)
After ⚡ click with no Sea polygon:
  → set mouth_click_mode reactive flag = True
  → toolbar shows status text: "Click on the map to set the river mouth, then ⚡ again"
  → next map click sets mouth_lon_lat reactive var, clears flag
  → next ⚡ click runs split with the stored mouth
```

Piggybacks on the existing `map_click_trigger` JS bridge (the same pattern
the `sel_*_btn` selection modes already use — proven since v0.30.x). Click
mode auto-clears if any other selection mode button is pressed (mutual
exclusion with `sel_river_btn` / `sel_lagoon_btn` / `sel_sea_btn`).

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
| `fetched_rivers()` False | Toast "Click 🌊 Rivers first to load the centerline" |
| `fetched_water()` False | Toast "Click 💧 Water first to load polygons" |
| BFS returns empty (centerline doesn't touch any polygon) | Toast "No connected polygons — try lowering Strahler threshold or checking that Rivers + Water cover the same area" |
| Single polygon (no-op) | Run anyway; toast "Kept 1 of 1 polygons" |

### Auto-split

| Case | Behavior |
|------|----------|
| Auto-extract not yet run (water polygons still unfiltered) | Toast "Click ✨ Auto-extract first" |
| N > polygon count | Helper returns mostly-empty groups; toast warning "Only M polygons found — last (N–M) reaches will be empty. Try fewer reaches." Non-fatal. |
| N=1 | Single reach with all polygons; toast "Created 1 reach (try N≥2 for spatial split)" |
| Mouth-click mode timeout | If user enters click mode but doesn't click within 30 s, exit silently (state flag clears on next button press). No timer; just state-driven. |
| Re-running Auto-split | Overwrites prior reach assignment; toast "Re-split into N reaches (previous split discarded)" |

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

1. **Programmatic fetch trigger**: introducing a 2nd reactive var per fetch button is mild plumbing. Plan must spell out exactly how the existing `_do_fetch_rivers` body gets refactored into a callable. Risk: regressing the existing button click path.
2. **`_orient_centerline_mouth_to_source` promotion**: the helper is private in `create_model_river.py`. Promoting it to public means it's part of the v0.50.0 API contract; future changes need backwards-compat. Acceptable risk — the function is small and the algorithm is stable.
3. **Click-mouth state machine** mutual exclusion with selection modes: must verify that pressing `sel_river_btn` while in mouth-click mode clears the flag (and vice versa). Visual test in the plan covers this.
4. **Nominatim ToS compliance**: User-Agent header must include contact info. Hard-coded with the user's email per CLAUDE.md identity is acceptable; alternative is to read from a config file (out of scope).
5. **Map zoom after Find**: the existing `_widget.update(session, layers, view_state=...)` call requires a `view_state` dict. The exact shape of the dict (zoom level, bearing, pitch defaults) is in the panel already — plan must reference the existing zoom-after-fetch_sea path which already does this.
