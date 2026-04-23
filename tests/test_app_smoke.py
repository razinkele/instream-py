"""Smoke test: app module imports and UI renders without errors."""

import sys
from pathlib import Path
import pytest

pytest.importorskip("shiny")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))


def test_simulation_imports():
    from simulation import run_simulation

    assert callable(run_simulation)


def test_panel_modules_import():
    from modules.population_panel import population_ui
    from modules.spatial_panel import spatial_server

    assert callable(population_ui)
    assert callable(spatial_server)


def test_app_creates():
    from app import app

    assert app is not None
