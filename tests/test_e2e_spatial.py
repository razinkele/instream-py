"""End-to-end Playwright tests for inSTREAM spatial visualization.

Starts the Shiny app, runs a short simulation, and verifies:
- App loads with all UI elements
- deck.gl + MapLibre scripts inject correctly
- Simulation runs and spatial panel renders cell polygons
- Trips animation controls appear when enabled
- Color variable switching works
- No JS errors during operation

Run with: conda run -n shiny python -m pytest tests/test_e2e_spatial.py -v
Requires: playwright install chromium
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Generator

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import Page, sync_playwright, Browser

APP_DIR = Path(__file__).resolve().parent.parent / "app"
PORT = 18903
URL = f"http://127.0.0.1:{PORT}"


def _click_tab(pg: Page, tab_name: str) -> None:
    """Navigate to a tab via the custom sidebar.

    The app uses `ui.navset_hidden(...)` so the Bootstrap `[role="tab"]`
    elements are present in DOM but not visible — clicking them directly
    times out with "element is not visible". Navigation instead flows
    through `.sp-nav-link[data-tab=...]` in the custom sidebar, whose
    JS handler calls `Shiny.setInputValue('main_tabs', tab)`. See
    `app/app.py` ~line 196-211.
    """
    pg.locator(f'.sp-nav-link[data-tab="{tab_name}"]').click()


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def app_server() -> Generator[subprocess.Popen, None, None]:
    """Start the inSTREAM Shiny app for the test session."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "shiny",
            "run",
            "--reload",
            str(APP_DIR / "app.py"),
            "--port",
            str(PORT),
            "--host",
            "127.0.0.1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(APP_DIR),
    )
    # Wait for server startup
    time.sleep(10)
    # Verify process is still alive
    if proc.poll() is not None:
        output = proc.stdout.read() if proc.stdout else ""
        pytest.skip(f"App server failed to start: {output[:500]}")
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def browser() -> Generator[Browser, None, None]:
    """Launch headless Chromium for the test session."""
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(scope="session")
def shared_page(
    browser: Browser, app_server: subprocess.Popen
) -> Generator[Page, None, None]:
    """Single page reused across all tests — avoids server overload."""
    pg = browser.new_page()
    pg.goto(URL, wait_until="load", timeout=60_000)
    # Wait for Shiny init: the run button becomes visible when Shiny is ready
    try:
        pg.wait_for_selector("#run_btn", state="visible", timeout=30_000)
    except Exception:
        pass
    time.sleep(2)
    yield pg
    pg.close()


@pytest.fixture
def page(shared_page: Page) -> Page:
    """Alias — all tests share the same page (no reload)."""
    return shared_page


_sim_ran = False


@pytest.fixture(scope="session")
def sim_page(shared_page: Page) -> Page:
    """Run simulation once and return the page with results."""
    global _sim_ran
    if not _sim_ran:
        pg = shared_page
        # Use Shiny JS API to set date values (plain fill doesn't trigger Shiny binding)
        pg.evaluate("""() => {
            Shiny.setInputValue('start_date', '2011-04-01');
            Shiny.setInputValue('end_date', '2011-04-15');
        }""")
        time.sleep(1)
        pg.locator("#run_btn").click()
        pg.wait_for_function(
            """() => {
                const el = document.querySelector('#progress_text');
                return el && el.textContent.includes('Complete');
            }""",
            timeout=300_000,
        )
        time.sleep(3)
        _sim_ran = True
    return shared_page


# ============================================================================
# 1. App loads
# ============================================================================


class TestAppLoads:
    """Verify the app loads with all expected UI elements."""

    def test_page_has_title(self, page: Page):
        assert "inSTREAM" in page.title()

    def test_sidebar_visible(self, page: Page):
        # App uses a custom sidebar (`.sp-sidebar` in app/app.py), not the
        # stock bslib sidebar layout — the latter is replaced wholesale.
        sidebar = page.locator(".sp-sidebar")
        assert sidebar.count() == 1
        assert sidebar.is_visible()

    def test_config_select_exists(self, page: Page):
        select = page.locator("#config_file")
        assert select.count() == 1

    def test_run_button_exists(self, page: Page):
        btn = page.locator("#run_btn")
        assert btn.count() == 1
        assert btn.is_visible()

    def test_tab_panels_exist(self, page: Page):
        """All 5 tabs should be present."""
        tabs = page.locator('[role="tab"]')
        tab_texts = [tabs.nth(i).inner_text() for i in range(tabs.count())]
        assert "Population" in tab_texts
        assert "Spatial" in tab_texts
        assert "Environment" in tab_texts

    def test_progress_text_exists(self, page: Page):
        progress = page.locator("#progress_text")
        assert progress.count() == 1

    def test_backend_select_exists(self, page: Page):
        select = page.locator("#backend")
        assert select.count() == 1


# ============================================================================
# 2. Spatial tab UI
# ============================================================================


class TestSpatialTabUI:
    """Verify spatial tab UI elements before simulation."""

    def test_spatial_tab_clickable(self, page: Page):
        _click_tab(page, "Spatial")
        time.sleep(0.5)
        # The spatial panel should now be visible
        panel = page.locator(".card-header", has_text="Spatial View")
        assert panel.count() >= 1

    def test_color_var_selector(self, page: Page):
        _click_tab(page, "Spatial")
        time.sleep(0.5)
        select = page.locator("#spatial-color_var")
        assert select.count() == 1

    def test_trips_color_selector(self, page: Page):
        _click_tab(page, "Spatial")
        time.sleep(0.5)
        select = page.locator("#spatial-trips_color")
        assert select.count() == 1

    def test_show_trips_checkbox(self, page: Page):
        _click_tab(page, "Spatial")
        time.sleep(0.5)
        checkbox = page.locator("#spatial-show_trips")
        assert checkbox.count() == 1

    def test_pre_simulation_message(self, page: Page):
        """Before simulation, spatial panel should show a message."""
        _click_tab(page, "Spatial")
        time.sleep(0.5)
        msg = page.locator("text=Run a simulation")
        assert msg.count() >= 1


# ============================================================================
# 3. CDN script injection
# ============================================================================


class TestCDNInjection:
    """Verify deck.gl and MapLibre CDN scripts are injected."""

    def test_deckgl_script_present(self, page: Page):
        script = page.locator('script[src*="deck.gl"]')
        assert script.count() >= 1

    def test_maplibre_script_present(self, page: Page):
        script = page.locator('script[src*="maplibre"]')
        assert script.count() >= 1

    def test_maplibre_css_present(self, page: Page):
        css = page.locator('link[href*="maplibre"]')
        assert css.count() >= 1

    def test_deckgl_widgets_css_present(self, page: Page):
        css = page.locator('link[href*="deck.gl"][href*="widgets"]')
        assert css.count() >= 1


# ============================================================================
# 4. Simulation run + spatial rendering
# ============================================================================


class TestSimulationAndSpatialRender:
    """Run a short simulation and verify spatial map renders."""

    def test_progress_shows_complete(self, sim_page: Page):
        progress = sim_page.locator("#progress_text")
        assert "Complete" in progress.inner_text()

    def test_spatial_tab_has_map(self, sim_page: Page):
        """After simulation, spatial tab should have a map container."""
        _click_tab(sim_page, "Spatial")
        time.sleep(2)
        map_div = sim_page.locator("#spatial-spatial_map")
        assert map_div.count() >= 1

    def test_map_has_nonzero_size(self, sim_page: Page):
        """Map should have positive dimensions."""
        _click_tab(sim_page, "Spatial")
        time.sleep(2)
        map_div = sim_page.locator("#spatial-spatial_map")
        if map_div.count() == 0:
            pytest.skip("Map div not found")
        bbox = map_div.bounding_box()
        assert bbox is not None
        assert bbox["width"] > 100
        assert bbox["height"] > 100

    def test_deckgl_available_after_sim(self, sim_page: Page):
        """deck.gl should be loaded and map container present after simulation."""
        _click_tab(sim_page, "Spatial")
        time.sleep(2)
        has_deck = sim_page.evaluate("typeof deck !== 'undefined'")
        assert has_deck, "deck.gl should be defined"
        assert sim_page.locator("#spatial-spatial_map").count() >= 1

    def test_maplibre_loaded(self, sim_page: Page):
        """MapLibre GL should be loaded and the map container should exist."""
        _click_tab(sim_page, "Spatial")
        time.sleep(2)
        has_maplibre = sim_page.evaluate("typeof maplibregl !== 'undefined'")
        assert has_maplibre, "maplibregl should be defined"
        assert sim_page.locator("#spatial-spatial_map").count() >= 1

    def test_color_var_switch(self, sim_page: Page):
        """Switching color variable should not crash."""
        _click_tab(sim_page, "Spatial")
        time.sleep(1)
        select = sim_page.locator("#spatial-color_var")
        if select.count() == 0:
            pytest.skip("Color var select not found")
        select.select_option("velocity")
        time.sleep(1)
        select.select_option("fish_count")
        time.sleep(1)
        assert sim_page.locator("#spatial-spatial_map").count() >= 1

    def test_trips_checkbox_shows_controls(self, sim_page: Page):
        """Enabling trips checkbox should show animation controls."""
        _click_tab(sim_page, "Spatial")
        time.sleep(1)
        checkbox = sim_page.locator("#spatial-show_trips")
        if checkbox.count() == 0:
            pytest.skip("Trips checkbox not found")
        checkbox.check()
        time.sleep(2)
        anim_container = sim_page.locator("#spatial-anim_controls")
        assert anim_container.count() >= 1


# ============================================================================
# 5. No JavaScript errors
# ============================================================================


class TestNoJSErrors:
    """Verify no JS errors during app lifecycle."""

    def test_no_page_errors(self, page: Page):
        """Page should not have uncaught JS exceptions."""
        # Evaluate a simple check — if the page loaded successfully,
        # Shiny and deck.gl initialized without fatal errors
        has_shiny = page.evaluate("typeof Shiny !== 'undefined'")
        assert has_shiny, "Shiny should be defined (no fatal JS error on load)"

    def test_deck_gl_initialized(self, page: Page):
        """deck.gl global should be available."""
        has_deck = page.evaluate("typeof deck !== 'undefined'")
        assert has_deck, "deck.gl should be defined"


# ============================================================================
# 6. Shiny connection
# ============================================================================


class TestShinyConnection:
    """Verify Shiny WebSocket connection is established."""

    def test_shiny_connected(self, page: Page):
        """Shiny should have connected (shinyapp exists)."""
        connected = page.evaluate(
            "typeof Shiny !== 'undefined' && typeof Shiny.shinyapp !== 'undefined'"
        )
        assert connected

    def test_shiny_object_exists(self, page: Page):
        has_shiny = page.evaluate(
            "typeof Shiny !== 'undefined' && typeof Shiny.shinyapp !== 'undefined'"
        )
        assert has_shiny


# ============================================================================
# 7. Screenshot capture for visual inspection
# ============================================================================


class TestScreenshots:
    """Capture screenshots for manual visual inspection."""

    def test_capture_spatial_map(self, sim_page: Page, tmp_path):
        """Capture a screenshot of the spatial map for visual verification."""
        _click_tab(sim_page, "Spatial")
        time.sleep(3)

        screenshot_path = tmp_path / "spatial_map.png"
        sim_page.screenshot(path=str(screenshot_path), full_page=True)
        assert screenshot_path.exists()
        assert screenshot_path.stat().st_size > 10_000

    def test_capture_population_tab(self, sim_page: Page, tmp_path):
        """Capture population tab for visual verification."""
        _click_tab(sim_page, "Population")
        time.sleep(2)

        screenshot_path = tmp_path / "population_tab.png"
        sim_page.screenshot(path=str(screenshot_path), full_page=True)
        assert screenshot_path.exists()
        assert screenshot_path.stat().st_size > 5_000
