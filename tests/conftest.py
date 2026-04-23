"""Test configuration and shared fixtures for Salmopy test suite."""

import os
from pathlib import Path

import numpy as np
import pytest

collect_ignore = ["_debug_alignment.py"]


def pytest_configure(config):
    """Warn loudly when NetLogo oracle CSVs are missing.

    ~11 validation tests in test_validation.py + test_run_level_parity.py
    use `pytest.skip()` at runtime when their fixture CSV is absent. A
    suite can go 100% green with zero oracle coverage — a real hazard
    for scientific correctness. This hook emits a UserWarning so the
    skip is at least visible in CI logs. Set CI_NO_ORACLE=1 to silence
    when running a deliberately oracle-free subset (e.g., a unit-only
    developer run).
    """
    if os.environ.get("CI_NO_ORACLE") == "1":
        return
    ref_dir = Path(__file__).parent / "fixtures" / "reference"
    if not ref_dir.exists() or not any(ref_dir.glob("*-netlogo.csv")):
        import warnings
        warnings.warn(
            f"NetLogo oracle CSVs missing under {ref_dir}. ~11 validation "
            "tests will silently skip. Set CI_NO_ORACLE=1 to silence this "
            "warning, or regenerate the fixtures with the netlogo-oracle "
            "workflow.",
            UserWarning,
            stacklevel=2,
        )

# Enable JAX float64 if JAX is available
try:
    import jax
    jax.config.update("jax_enable_x64", True)
    HAS_JAX = True
except ImportError:
    HAS_JAX = False

try:
    import numba  # noqa: F401
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False


# ---------------------------------------------------------------------------
# Path fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REFERENCE_DIR = FIXTURES_DIR / "reference"


@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture
def example_a_data_path():
    return FIXTURES_DIR / "example_a"


@pytest.fixture
def example_b_data_path():
    return FIXTURES_DIR / "example_b"


@pytest.fixture
def reference_dir():
    return REFERENCE_DIR


# ---------------------------------------------------------------------------
# Backend parametrization
# ---------------------------------------------------------------------------

def _available_backends():
    """Return list of available backend names."""
    backends = ["numpy"]
    if HAS_NUMBA:
        backends.append("numba")
    if HAS_JAX:
        backends.append("jax")
    return backends


@pytest.fixture(params=_available_backends())
def backend_name(request):
    """Parametric fixture yielding each available backend name."""
    return request.param


# ---------------------------------------------------------------------------
# NetLogo reference data
# ---------------------------------------------------------------------------

def netlogo_reference(test_name: str) -> Path:
    """Return path to NetLogo reference CSV for a given test.

    Usage in tests:
        ref_path = netlogo_reference("cell-depth-test-out")
        if not ref_path.exists():
            pytest.skip("NetLogo reference data not generated yet")
    """
    return REFERENCE_DIR / f"{test_name}.csv"


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

# Tolerance hierarchy:
#   numpy <-> numba: rtol=1e-12 (essentially identical)
#   numpy <-> jax:   rtol=1e-10 (XLA may reorder FP ops)
#   python <-> netlogo: rtol=1e-6

BACKEND_RTOL = {
    ("numpy", "numba"): 1e-12,
    ("numpy", "jax"): 1e-10,
    ("numba", "jax"): 1e-10,
}

NETLOGO_RTOL = 1e-6


def assert_close(actual, expected, rtol=None, atol=0.0, backend=None):
    """Assert arrays are close, with backend-aware default tolerance.

    Parameters
    ----------
    actual, expected : array-like
    rtol : float, optional
        If None, uses NETLOGO_RTOL as default.
    atol : float, optional
    backend : str, optional
        If provided, adjusts tolerance based on backend.
    """
    if rtol is None:
        rtol = NETLOGO_RTOL
    np.testing.assert_allclose(
        np.asarray(actual),
        np.asarray(expected),
        rtol=rtol,
        atol=atol,
    )
