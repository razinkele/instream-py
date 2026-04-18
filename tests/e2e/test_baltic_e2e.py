"""End-to-end tests for the Baltic case study.

Covers the user flow for the Nemunas + Curonian Lagoon + Baltic coastal
example config (`configs/example_baltic.yaml`):

    TestBalticSmoke (runs whenever app reachable):
      - example_baltic listed in the sidebar config dropdown
      - Loading it populates the Setup summary with 8 real Nemunas-basin reaches
      - Setup summary mentions the 3 marine zones (Estuary / Coastal / Baltic Proper)
      - Spatial tab mounts the deck.gl map container

    TestBalticSimulation (opt-in via E2E_INTEGRATION=1):
      - Full pipeline: load Baltic config, run a short simulation, wait for
        'Complete', navigate to Spatial view, verify post-sim map renders.
        Takes 3-5 minutes because Baltic has 1,774 cells + 5,000 initial fish.

Requires the Shiny app running externally (default http://127.0.0.1:8000,
override via E2E_BASE_URL). Uses the same base_url fixture as
test_create_model_integration.py (conftest.py skips cleanly if unreachable).

Run:
    micromamba run -n shiny python -m pytest tests/e2e/test_baltic_e2e.py -v
    E2E_INTEGRATION=1 micromamba run -n shiny python -m pytest tests/e2e/test_baltic_e2e.py -v
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect


INTEGRATION_ENABLED = os.environ.get("E2E_INTEGRATION") == "1"

# ASCII reach names as they appear in the shapefile DBF / Setup summary table.
# Real OSM / geography: Nemunas (main), Minija (Klaipėda tributary), Šyša
# (delta branch → Sysa), Skirvytė (middle delta → Skirvyte), Leitė (small
# tributary → Leite), Gilija (southern delta, from Kaliningrad PBF as
# Матросовка), plus the hand-traced Curonian Lagoon and offshore Baltic strip.
BALTIC_REACHES = [
    "Nemunas", "Minija", "Sysa", "Skirvyte", "Leite", "Gilija",
    "CuronianLagoon", "BalticCoast",
]

# Marine zone names declared in configs/example_baltic.yaml under `marine.zones`.
BALTIC_MARINE_ZONES = ["Estuary", "Coastal", "Baltic Proper"]


def _click_tab(pg: Page, tab_name: str) -> None:
    """Navigate via the custom sidebar (app uses ui.navset_hidden, so the
    Bootstrap tab bar is present-but-invisible; navigation goes through
    .sp-nav-link[data-tab=…] which fires Shiny.setInputValue('main_tabs', …)).
    Matches _click_tab in tests/test_e2e_spatial.py.
    """
    pg.locator(f'.sp-nav-link[data-tab="{tab_name}"]').click()


def _select_baltic_config(pg: Page) -> None:
    """Select example_baltic from the sidebar config dropdown and click Load."""
    pg.locator("#config_file").select_option(label="example_baltic")
    pg.locator("#load_config_btn").click()
    # Shiny reactive propagation: setup_summary re-renders after the click.
    # Wait for the output to update via a specific signal — the Baltic config
    # advertises "8 reaches" which is unique to this config.
    pg.wait_for_function(
        """() => {
            const el = document.querySelector('#setup-setup_summary');
            return el && el.textContent.includes('8 reaches');
        }""",
        timeout=20_000,
    )


@pytest.fixture
def baltic_page(page: Page, base_url: str) -> Page:
    page.goto(base_url + "/")
    # Shiny init signal — run button becomes visible once the app is ready.
    page.wait_for_selector("#run_btn", state="visible", timeout=30_000)
    # Setup view is the second nav link; navigate there so setup_summary
    # is in the live DOM for smoke tests.
    _click_tab(page, "Setup")
    return page


class TestBalticSmoke:
    """Fast smoke tests — config load + setup/map render. No simulation."""

    def test_baltic_appears_in_config_dropdown(self, baltic_page: Page) -> None:
        """`example_baltic` must be one of the listable options in #config_file."""
        options = baltic_page.locator("#config_file option").all_text_contents()
        assert "example_baltic" in options, (
            f"Expected 'example_baltic' in config options, got: {options}"
        )

    def test_load_baltic_populates_setup_summary(self, baltic_page: Page) -> None:
        """After loading Baltic, the Setup summary header says 'across 8 reaches'."""
        _select_baltic_config(baltic_page)
        summary = baltic_page.locator("#setup-setup_summary")
        expect(summary).to_be_visible(timeout=10_000)
        expect(summary).to_contain_text("8 reaches")

    def test_setup_summary_lists_real_reach_names(self, baltic_page: Page) -> None:
        """All 8 Baltic-basin reach names appear in the setup-summary table."""
        _select_baltic_config(baltic_page)
        summary = baltic_page.locator("#setup-setup_summary")
        expect(summary).to_be_visible(timeout=10_000)
        summary_text = summary.text_content() or ""
        missing = [r for r in BALTIC_REACHES if r not in summary_text]
        assert not missing, (
            f"Setup summary missing reach names: {missing}\n"
            f"Full text (first 500 chars): {summary_text[:500]}"
        )

    def test_setup_summary_mentions_marine_zones(self, baltic_page: Page) -> None:
        """Baltic config declares 3 marine zones — all should be advertised."""
        _select_baltic_config(baltic_page)
        summary = baltic_page.locator("#setup-setup_summary")
        expect(summary).to_be_visible(timeout=10_000)
        summary_text = summary.text_content() or ""
        missing = [z for z in BALTIC_MARINE_ZONES if z not in summary_text]
        assert not missing, (
            f"Setup summary missing marine zones: {missing}\n"
            f"Full text (first 500 chars): {summary_text[:500]}"
        )

    def test_setup_summary_reports_cell_count(self, baltic_page: Page) -> None:
        """Cell count in summary header is in the expected Baltic range (1400-2200)."""
        _select_baltic_config(baltic_page)
        summary = baltic_page.locator("#setup-setup_summary")
        expect(summary).to_be_visible(timeout=10_000)
        import re

        text = summary.text_content() or ""
        m = re.search(r"Grid:\s*(\d+)\s*cells", text)
        assert m, f"Cell count pattern not found in summary: {text[:200]!r}"
        n_cells = int(m.group(1))
        assert 1800 <= n_cells <= 3000, (
            f"Baltic cell count {n_cells} outside expected 1800-3000 band "
            f"(current baseline 2,022 after Minija tightening + BalticCoast "
            f"repositioning — if you retuned CELL_SIZE_M, RIVER_CLIP_BBOX, or "
            f"per-reach clips, update this bound)"
        )

    def test_spatial_tab_navigable_after_baltic_load(self, baltic_page: Page) -> None:
        """Spatial view is reachable after loading Baltic.

        Pre-simulation the panel shows a "Run a simulation to see results"
        placeholder (not the deck.gl map — that mounts post-sim). Post-sim
        assertion lives in TestBalticSimulation.
        """
        _select_baltic_config(baltic_page)
        _click_tab(baltic_page, "Spatial")
        placeholder = baltic_page.locator("text=Run a simulation")
        expect(placeholder.first).to_be_visible(timeout=10_000)

    def test_setup_panel_has_inline_config_picker(self, baltic_page: Page) -> None:
        """Setup panel exposes its own `setup_config` dropdown + Load button
        so users don't have to hunt for the sidebar's Configuration selector
        (which can be collapsed). Baltic appears in both pickers.
        """
        picker = baltic_page.locator("#setup-setup_config")
        expect(picker).to_be_attached(timeout=10_000)
        options = picker.locator("option").all_text_contents()
        assert "example_baltic" in options, (
            f"Setup panel picker missing example_baltic: {options}"
        )
        expect(baltic_page.locator("#setup-setup_load_btn")).to_be_visible()

    def test_setup_panel_inline_picker_loads_baltic(self, baltic_page: Page) -> None:
        """Selecting Baltic in the Setup panel's own picker + clicking its
        Load button populates the setup_summary with the 8 real reaches."""
        baltic_page.locator("#setup-setup_config").select_option(label="example_baltic")
        baltic_page.locator("#setup-setup_load_btn").click()
        baltic_page.wait_for_function(
            """() => {
                const el = document.querySelector('#setup-setup_summary');
                return el && el.textContent.includes('8 reaches');
            }""",
            timeout=20_000,
        )
        summary_text = (
            baltic_page.locator("#setup-setup_summary").text_content() or ""
        )
        for reach in ("Nemunas", "CuronianLagoon", "BalticCoast"):
            assert reach in summary_text, (
                f"Setup summary missing {reach} after inline-picker load"
            )

    def test_setup_panel_shows_helpful_empty_state(self, baltic_page: Page) -> None:
        """Before any config is loaded, Setup shows a guidance message, not a
        blank panel."""
        # Fresh page fixture — no config loaded yet
        summary = baltic_page.locator("#setup-setup_summary")
        expect(summary).to_be_visible(timeout=10_000)
        expect(summary).to_contain_text("No configuration loaded")


@pytest.mark.integration
@pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="Set E2E_INTEGRATION=1 to run Baltic simulation (3-5 min).",
)
class TestBalticSimulation:
    """Full pipeline: load Baltic, run short simulation, verify completion."""

    def test_baltic_short_sim_completes_and_renders(self, baltic_page: Page) -> None:
        """Load Baltic, run 2-week sim, wait for Complete, verify Spatial renders.

        Uses the shortest meaningful window (2 weeks of spring flow) so the
        test caps around 5 minutes even with 1,774 cells + 5,000 fish.
        """
        _select_baltic_config(baltic_page)

        # Short window — Shiny date inputs need Shiny.setInputValue, not plain fill.
        baltic_page.evaluate(
            """() => {
                Shiny.setInputValue('start_date', '2011-04-01');
                Shiny.setInputValue('end_date',   '2011-04-15');
            }"""
        )
        baltic_page.wait_for_timeout(1000)
        baltic_page.locator("#run_btn").click()

        # Wait for progress_text to include 'Complete'. 10 min ceiling matches
        # existing tests/test_e2e_spatial.py pattern; actual runtime expected 3-5 min.
        baltic_page.wait_for_function(
            """() => {
                const el = document.querySelector('#progress_text');
                return el && el.textContent.includes('Complete');
            }""",
            timeout=600_000,
        )
        expect(baltic_page.locator("#progress_text")).to_contain_text("Complete")

        # Post-sim: Spatial map should render with the deck.gl canvas mounted.
        _click_tab(baltic_page, "Spatial")
        map_el = baltic_page.locator("#spatial-spatial_map")
        expect(map_el).to_be_visible(timeout=15_000)
        canvas = baltic_page.locator("#spatial-spatial_map canvas").first
        expect(canvas).to_be_visible(timeout=15_000)
        box = canvas.bounding_box()
        assert box is not None and box["width"] > 200 and box["height"] > 200, (
            f"deck.gl canvas has unexpected bounding box: {box}"
        )
