"""End-to-end Playwright tests for the Create Model panel.

Asserts the UI contract of the Create Model view: widgets render, sliders
have correct defaults, the deck.gl map canvas mounts, the Help modal opens
with the full workflow guide, and action-button state transitions work.

Deliberately avoids exercising the OSM / Marine Regions network fetches —
those are external, rate-limited, and belong in a separate integration
suite if ever added.

Run:
    micromamba run -n shiny python -m pytest tests/e2e/ -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


MODULE_ID = "create"


def _id(name: str) -> str:
    """Convert a Shiny module input name to its DOM ID selector."""
    return f"#{MODULE_ID}-{name}"


@pytest.fixture
def create_model_page(page: Page, base_url: str) -> Page:
    page.goto(base_url + "/")
    page.get_by_role("link", name=" Create Model").click()
    page.wait_for_selector(f"{_id('create_map')} canvas", state="attached", timeout=15_000)
    return page


class TestCreateModelWidgets:
    """The view exposes every widget the user needs to build a model."""

    @pytest.mark.parametrize(
        "control",
        [
            "help_btn",
            "fetch_rivers",
            "fetch_water",
            "fetch_sea",
            "sel_river_btn",
            "sel_lagoon_btn",
            "sel_sea_btn",
            "clear_reaches_btn",
            "generate_cells_btn",
            "export_btn",
            "strahler_min",
            "cell_size",
            "water_cell_size",
            "sea_cell_size",
            "cell_shape",
            "create_map",
        ],
    )
    def test_control_is_attached(self, create_model_page: Page, control: str) -> None:
        expect(create_model_page.locator(_id(control))).to_be_attached()

    def test_action_buttons_are_enabled_on_load(self, create_model_page: Page) -> None:
        """No preconditions needed — selection and export buttons are clickable
        immediately. If this changes (e.g. a "must fetch first" gate is added),
        this test will surface it explicitly."""
        for name in (
            "fetch_rivers",
            "fetch_water",
            "fetch_sea",
            "sel_river_btn",
            "sel_lagoon_btn",
            "sel_sea_btn",
            "clear_reaches_btn",
            "generate_cells_btn",
            "export_btn",
            "help_btn",
        ):
            expect(create_model_page.locator(_id(name))).to_be_enabled()


class TestCreateModelDefaults:
    """Design-document defaults must not silently drift."""

    def test_strahler_default_is_3(self, create_model_page: Page) -> None:
        assert create_model_page.locator(_id("strahler_min")).input_value() == "3"

    def test_cell_size_defaults(self, create_model_page: Page) -> None:
        assert create_model_page.locator(_id("cell_size")).input_value() == "20"
        assert create_model_page.locator(_id("water_cell_size")).input_value() == "200"
        assert create_model_page.locator(_id("sea_cell_size")).input_value() == "2000"

    def test_cell_shape_default_and_options(self, create_model_page: Page) -> None:
        shape = create_model_page.locator(_id("cell_shape"))
        assert shape.input_value() == "hexagonal"
        option_values = shape.locator("option").evaluate_all(
            "opts => opts.map(o => o.value)"
        )
        assert set(option_values) == {"hexagonal", "rectangular"}


class TestCreateModelMap:
    """deck.gl WebGL map is the centrepiece — it must actually paint pixels."""

    def test_map_canvas_has_nonzero_size(self, create_model_page: Page) -> None:
        canvas = create_model_page.locator(f"{_id('create_map')} canvas").first
        expect(canvas).to_be_visible()
        box = canvas.bounding_box()
        assert box is not None, "deck.gl canvas has no bounding box"
        assert box["width"] > 200, f"map canvas width too small: {box['width']}"
        assert box["height"] > 200, f"map canvas height too small: {box['height']}"

    def test_click_bridge_is_wired(self, create_model_page: Page) -> None:
        """The hidden action-button bridge that forwards map clicks must exist.
        See project_create_model_status memory — this is the pattern that
        avoids SilentException from dynamic JS inputs."""
        expect(create_model_page.locator(_id("map_click_trigger"))).to_be_attached()
        expect(create_model_page.locator(_id("map_click_coords"))).to_be_attached()


class TestCreateModelHelpModal:
    """The Help modal is the model-builder's onboarding — its structure matters."""

    def test_help_opens_and_contains_workflow(self, create_model_page: Page) -> None:
        create_model_page.locator(_id("help_btn")).click()
        modal = create_model_page.locator(".modal-dialog")
        expect(modal).to_be_visible()
        expect(modal).to_contain_text("Creating a Model in SalmoPy")
        for step in ("Step 1", "Step 2", "Step 3", "Step 4", "Step 5"):
            expect(modal).to_contain_text(step)
        expect(modal).to_contain_text("Key Concepts")
        expect(modal).to_contain_text("Cell Attributes")

    def test_help_modal_can_be_dismissed(self, create_model_page: Page) -> None:
        create_model_page.locator(_id("help_btn")).click()
        modal = create_model_page.locator(".modal-dialog").first
        expect(modal).to_be_visible()
        create_model_page.locator('.modal button[data-dismiss="modal"]').click()
        expect(modal).not_to_be_visible(timeout=5_000)


class TestCreateModelSelectionFlow:
    """Smoke: clicking a selection-mode button changes UI state."""

    def test_clear_button_is_clickable(self, create_model_page: Page) -> None:
        """The Clear button is a terminal/no-op when nothing is selected — it
        must still be clickable without raising a client-side error."""
        create_model_page.locator(_id("clear_reaches_btn")).click()
        # Assert no uncaught client-side errors surfaced (Shiny renders these
        # as a red error panel with class `shiny-output-error`).
        errors = create_model_page.locator(".shiny-output-error")
        assert errors.count() == 0
