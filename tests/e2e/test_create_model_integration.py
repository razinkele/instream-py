"""Integration e2e tests for the Create Model pipeline.

Covers the full happy-path flow against a *running* Shiny app:
    Fetch Rivers → Select River → Click map → Generate Cells → Export

These tests are slower (end-to-end pipeline is ~60-90 s on a warm machine)
and depend on:
    - The Lithuania OSM PBF being present on disk (app/data/osm/lithuania-latest.osm.pbf)
    - A running Shiny app (default http://127.0.0.1:8001 for the freshly-reloaded
      instance; override with E2E_BASE_URL)
    - The `osmium` CLI being installed in the shiny conda env

Opt-in via env var:
    E2E_INTEGRATION=1 micromamba run -n shiny python -m pytest tests/e2e/test_create_model_integration.py -v

They are **skipped by default** to keep the regular test run fast and
resilient when the app isn't available or the PBF hasn't been downloaded.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

import pytest
from playwright.sync_api import Page, expect


INTEGRATION_ENABLED = os.environ.get("E2E_INTEGRATION") == "1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not INTEGRATION_ENABLED,
        reason="Set E2E_INTEGRATION=1 to run integration e2e (requires local OSM PBF + running app).",
    ),
]


MODULE_ID = "create"


def _id(name: str) -> str:
    return f"#{MODULE_ID}-{name}"


def _base_url_default() -> str:
    # Prefer the freshly-reloaded instance on :8001 when E2E_BASE_URL isn't set.
    # Rationale: on OneDrive, `shiny run --reload` often misses changes on :8000
    # (per CLAUDE.md), so we default integration tests to the known-fresh port.
    return os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8001").rstrip("/")


@pytest.fixture(scope="session")
def integration_base_url() -> str:
    url = _base_url_default()
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    try:
        with socket.create_connection((host, port), timeout=1.0):
            pass
    except OSError:
        pytest.skip(f"Integration app not reachable at {url}. Start it on that port.")
    return url


@pytest.fixture(scope="session", autouse=True)
def _require_lithuania_pbf():
    pbf = Path(__file__).resolve().parents[2] / "app" / "data" / "osm" / "lithuania-latest.osm.pbf"
    if not pbf.exists():
        pytest.skip(f"Lithuania OSM PBF not found at {pbf} — run Fetch Rivers in the app once to download it.")


@pytest.fixture
def on_create_model(page: Page, integration_base_url: str) -> Page:
    """Land on the Create Model view with the deck.gl canvas mounted and
    a fresh reactive state (no selection, no cells)."""
    page.goto(integration_base_url + "/")
    page.get_by_role("link", name=" Create Model").click()
    page.wait_for_selector(f"{_id('create_map')} canvas", state="attached", timeout=15_000)
    # Confirm we're on the refactored build (has the region selector).
    expect(page.locator(_id("osm_country"))).to_be_attached()
    # Defensive cleanup in case a previous test left selections behind.
    page.locator(_id("clear_reaches_btn")).click()
    return page


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _poll_text(
    page: Page,
    selector: str,
    predicate: Callable[[str], bool],
    timeout_s: float,
    interval_s: float = 0.3,
) -> str:
    """Poll a DOM node's text until the predicate is true. Returns the final text
    that satisfied the predicate, or raises AssertionError with the last seen text."""
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        last = (page.locator(selector).text_content() or "").strip()
        if predicate(last):
            return last
        time.sleep(interval_s)
    raise AssertionError(
        f"Timed out after {timeout_s}s waiting on {selector}. Last text: {last!r}"
    )


def _fire_map_click(page: Page, longitude: float, latitude: float) -> None:
    """Simulate the JS bridge: set the coords input as JSON, then fire a native
    click on the hidden action button. Setting the button value via
    Shiny.setInputValue does NOT reliably fire @reactive.event — the click
    binding is attached to the DOM node, so we must click the node itself."""
    payload = json.dumps({"longitude": longitude, "latitude": latitude})
    page.evaluate(
        """([coords]) => {
            Shiny.setInputValue('create-map_click_coords', coords, {priority: 'event'});
        }""",
        [payload],
    )
    # Small debounce so the input value is registered before the trigger fires.
    page.wait_for_timeout(200)
    # The trigger is intentionally hidden (style="display:none") — a programmatic
    # JS bridge, not a user-facing widget. Playwright's Locator.click guards on
    # geometry even with force=True (zero-size box), so dispatch the native DOM
    # click which is what Shiny's ActionButtonBinding listens for anyway.
    page.evaluate("() => document.getElementById('create-map_click_trigger').click()")


def _sample_river_line_coord(page: Page) -> tuple[float, float]:
    """Read a real river LineString midpoint from the live deck.gl layer data.
    Relies on shiny_deckgl exposing layers via `window.__deckgl_instances[id].lastLayers`."""
    coord = page.evaluate(
        """() => {
            const inst = window.__deckgl_instances?.['create-create_map'];
            if (!inst || !Array.isArray(inst.lastLayers)) return null;
            const riverLine = inst.lastLayers.find(
                l => (l?.id || '').includes('river-lines')
            );
            const feats = riverLine?.data?.features;
            if (!feats?.length) return null;
            const coords = feats[0].geometry?.coordinates;
            if (!Array.isArray(coords) || !Array.isArray(coords[0])) return null;
            return coords[Math.floor(coords.length / 2)];
        }"""
    )
    assert coord is not None, "no river-line layer with features found on the map"
    return float(coord[0]), float(coord[1])


# ---------------------------------------------------------------------------
# Granular tests — each covers one UI contract
# ---------------------------------------------------------------------------


class TestFetchRivers:
    """Local OSM PBF extraction via the Fetch Rivers button."""

    def test_fetch_rivers_reports_feature_counts(self, on_create_model: Page) -> None:
        """Fetch Rivers should resolve to a status like
        'Loaded N river polygons + M stream lines + K water bodies.' within ~30 s."""
        on_create_model.locator(_id("fetch_rivers")).click()
        final = _poll_text(
            on_create_model,
            _id("fetch_status"),
            lambda t: t.lower().startswith("loaded"),
            timeout_s=60.0,
        )
        import re

        match = re.search(
            r"Loaded\s+(\d+)\s+river polygons\s*\+\s*(\d+)\s+stream lines",
            final,
        )
        assert match, f"Unexpected status text: {final!r}"
        polys, lines = int(match.group(1)), int(match.group(2))
        # Curonian Lagoon bbox is small but guaranteed to contain features.
        assert polys + lines > 0, "expected at least one river feature in Curonian Lagoon bbox"

    def test_data_summary_renders_after_fetch(self, on_create_model: Page) -> None:
        """Fetch populates the `data_summary` render with a river-data table."""
        on_create_model.locator(_id("fetch_rivers")).click()
        _poll_text(
            on_create_model,
            _id("fetch_status"),
            lambda t: t.lower().startswith("loaded"),
            timeout_s=60.0,
        )
        expect(on_create_model.locator(_id("data_summary"))).to_contain_text("OSM River Data")


class TestSelectionMode:
    """Click-to-select modes and their toolbar/workflow state."""

    def test_river_mode_activates_workflow_message(self, on_create_model: Page) -> None:
        on_create_model.locator(_id("sel_river_btn")).click()
        expect(on_create_model.locator(_id("toolbar_badges"))).to_contain_text("RIVER")
        expect(on_create_model.locator(_id("workflow_status"))).to_contain_text(
            "River selection ON"
        )

    def test_river_mode_is_toggle(self, on_create_model: Page) -> None:
        """Clicking the button a second time exits selection mode."""
        btn = on_create_model.locator(_id("sel_river_btn"))
        btn.click()
        expect(on_create_model.locator(_id("toolbar_badges"))).to_contain_text("RIVER")
        btn.click()
        expect(on_create_model.locator(_id("workflow_status"))).to_contain_text(
            "Selection mode OFF", timeout=5_000
        )

    def test_map_click_without_mode_prompts_user(self, on_create_model: Page) -> None:
        """Clicking the map without first choosing a selection mode should
        surface a clear 'select a mode first' message."""
        _fire_map_click(on_create_model, longitude=21.10, latitude=55.70)
        expect(on_create_model.locator(_id("workflow_status"))).to_contain_text(
            "select a mode first", timeout=5_000
        )


class TestClickToSelect:
    """Actually clicking a river feature must add it to reach_1."""

    def test_click_on_real_river_adds_segment(self, on_create_model: Page) -> None:
        """Pick a real river-line midpoint from the deck.gl layer data, click it,
        and assert the reach/segment counter increments."""
        # Fetch first
        on_create_model.locator(_id("fetch_rivers")).click()
        _poll_text(
            on_create_model,
            _id("fetch_status"),
            lambda t: t.lower().startswith("loaded"),
            timeout_s=60.0,
        )
        # Enter river mode
        on_create_model.locator(_id("sel_river_btn")).click()
        expect(on_create_model.locator(_id("toolbar_badges"))).to_contain_text("RIVER")
        # Snap to a real feature coordinate
        lon, lat = _sample_river_line_coord(on_create_model)
        _fire_map_click(on_create_model, longitude=lon, latitude=lat)
        _poll_text(
            on_create_model,
            _id("workflow_status"),
            lambda t: "Added segment to 'reach_1'" in t,
            timeout_s=10.0,
        )
        expect(on_create_model.locator(_id("toolbar_badges"))).to_contain_text("1 reaches")

    def test_clear_resets_counter(self, on_create_model: Page) -> None:
        """After adding a segment, Clear returns the workflow status to baseline."""
        on_create_model.locator(_id("fetch_rivers")).click()
        _poll_text(
            on_create_model,
            _id("fetch_status"),
            lambda t: t.lower().startswith("loaded"),
            timeout_s=60.0,
        )
        on_create_model.locator(_id("sel_river_btn")).click()
        lon, lat = _sample_river_line_coord(on_create_model)
        _fire_map_click(on_create_model, longitude=lon, latitude=lat)
        _poll_text(
            on_create_model,
            _id("toolbar_badges"),
            lambda t: "1 reaches" in t,
            timeout_s=10.0,
        )
        # Exit selection mode, then clear
        on_create_model.locator(_id("sel_river_btn")).click()
        on_create_model.locator(_id("clear_reaches_btn")).click()
        # toolbar_badges should no longer report the reach count
        _poll_text(
            on_create_model,
            _id("toolbar_badges"),
            lambda t: "1 reaches" not in t,
            timeout_s=5.0,
        )


# ---------------------------------------------------------------------------
# Full pipeline — one monolithic happy path
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestFullPipeline:
    """End-to-end: fetch → select → generate cells → export zip.

    Runs as a single ordered scenario because each step depends on
    the previous one's reactive state. Splitting into smaller tests
    would require re-running the slow Fetch (~10 s) and Generate
    Cells (~45 s) steps for each one. Total runtime: ~70-90 s.
    """

    def test_fetch_select_generate_export(self, on_create_model: Page) -> None:
        page = on_create_model

        # --- 1. Fetch rivers ---
        page.locator(_id("fetch_rivers")).click()
        fetch_status = _poll_text(
            page,
            _id("fetch_status"),
            lambda t: t.lower().startswith("loaded"),
            timeout_s=60.0,
        )
        assert "river polygons" in fetch_status.lower()

        # --- 2. Enter river selection mode ---
        page.locator(_id("sel_river_btn")).click()
        expect(page.locator(_id("toolbar_badges"))).to_contain_text("RIVER")

        # --- 3. Click on a real river centerline ---
        lon, lat = _sample_river_line_coord(page)
        _fire_map_click(page, longitude=lon, latitude=lat)
        _poll_text(
            page,
            _id("workflow_status"),
            lambda t: "Added segment to 'reach_1'" in t,
            timeout_s=10.0,
        )

        # --- 4. Exit selection mode, then generate cells ---
        page.locator(_id("sel_river_btn")).click()
        _poll_text(
            page,
            _id("workflow_status"),
            lambda t: "Selection mode OFF" in t,
            timeout_s=5.0,
        )

        page.locator(_id("generate_cells_btn")).click()
        gen_status = _poll_text(
            page,
            _id("workflow_status"),
            lambda t: "Generated" in t and "habitat cells" in t,
            timeout_s=120.0,
        )
        import re

        match = re.search(r"Generated\s+(\d+)\s+habitat cells", gen_status)
        assert match, f"Unexpected generate status: {gen_status!r}"
        n_cells = int(match.group(1))
        assert n_cells > 0, "expected at least one habitat cell"
        expect(page.locator(_id("toolbar_badges"))).to_contain_text(f"{n_cells} cells")

        # --- 5. Export ---
        page.locator(_id("export_btn")).click()
        export_status = _poll_text(
            page,
            _id("workflow_status"),
            lambda t: t.startswith("Exported to:"),
            timeout_s=30.0,
        )

        # --- 6. Verify the ZIP actually exists on disk ---
        export_path_str = export_status.split("Exported to:", 1)[1].strip().splitlines()[0].strip()
        export_path = Path(export_path_str)
        assert export_path.exists(), f"export zip does not exist: {export_path}"
        assert export_path.suffix == ".zip"
        assert export_path.stat().st_size > 0, "export zip is empty"

        # Spot-check the zip contents: it should be a valid archive with a YAML config.
        import zipfile

        with zipfile.ZipFile(export_path) as zf:
            names = zf.namelist()
            assert any(n.endswith(".yaml") or n.endswith(".yml") for n in names), (
                f"no YAML config in export zip, got: {names}"
            )
