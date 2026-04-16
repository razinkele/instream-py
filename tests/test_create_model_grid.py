"""Tests for create_model_grid hexagon generation."""
import sys
import os

# create_model_grid uses bare `from modules.xxx import ...` which resolves
# relative to the app/ directory — add it to sys.path before importing.
_APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
if _APP_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(_APP_DIR))


def test_hexagon_is_flat_top():
    from app.modules.create_model_grid import _hexagon
    h = _hexagon(0, 0, 10)
    coords = list(h.exterior.coords)[:-1]
    ys = sorted([c[1] for c in coords], reverse=True)
    # Flat-top: top two vertices have the same y-coordinate
    assert abs(ys[0] - ys[1]) < 0.01, f"Not flat-top: top y-values {ys[0]:.2f} vs {ys[1]:.2f}"


def test_hexagon_area():
    import math
    from app.modules.create_model_grid import _hexagon
    h = _hexagon(0, 0, 10)
    expected = (3 * math.sqrt(3) / 2) * 10**2  # regular hexagon area formula
    assert abs(h.area - expected) < 0.1, f"Area {h.area} != expected {expected}"
