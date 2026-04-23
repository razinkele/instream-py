"""Dependency-manifest invariants.

These tests enforce that every third-party package unconditionally imported
in src/salmopy is declared in pyproject.toml. A gap here means `pip install
salmopy` into a clean env breaks at first use of the code path.
"""
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def _load_pyproject():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_networkx_declared_in_core_dependencies():
    """v0.43.7: mesa.discrete_space.network imports networkx transitively;
    mesa itself doesn't pin it, so we must. CI on Python 3.13 surfaced
    this when the hardened workflow was activated."""
    data = _load_pyproject()
    core = data["project"]["dependencies"]
    assert any(d.lower().startswith("networkx") for d in core), (
        "networkx is a transitive dep of mesa.discrete_space that mesa "
        "does not itself pin. Declare it in core dependencies."
    )


def test_requests_declared_in_core_dependencies():
    """v0.43.7: requests is used by scripts/generate_baltic_example.py
    (import at module top) and test_marineregions_cache. Must be in
    core so dev installs work."""
    data = _load_pyproject()
    core = data["project"]["dependencies"]
    assert any(d.lower().startswith("requests") for d in core)


def test_dev_extra_includes_frontend():
    """v0.43.7: several tests import from app/modules which require shiny.
    [dev] must pull [frontend] transitively so CI installs include it."""
    data = _load_pyproject()
    dev = data["project"]["optional-dependencies"].get("dev", [])
    assert any("salmopy[frontend]" in d for d in dev), (
        "[dev] extra must include 'salmopy[frontend]' so CI dev installs "
        "can collect app-dependent tests."
    )


def test_meshio_declared_in_core_dependencies():
    """meshio is imported unconditionally in src/salmopy/space/fem_mesh.py;
    it must be a core dependency so fresh installs work."""
    data = _load_pyproject()
    core = data["project"]["dependencies"]
    assert any(d.lower().startswith("meshio") for d in core), (
        "meshio is imported unconditionally at src/salmopy/space/fem_mesh.py:7 "
        "but is not listed in pyproject.toml [project.dependencies]. "
        "Add 'meshio>=5.3' to the core dependencies block."
    )


def test_calibration_extra_declares_salib_and_sklearn():
    """SALib and scikit-learn are imported in src/salmopy/calibration/;
    they must be declared in an optional-dependencies group (canonically
    a new [calibration] extra, and [dev] should depend on that extra)."""
    data = _load_pyproject()
    optional = data["project"].get("optional-dependencies", {})
    declared = []
    for group in optional.values():
        declared.extend(d.lower() for d in group)

    def has(pkg: str) -> bool:
        return any(d.startswith(pkg) for d in declared)

    assert has("salib"), (
        "SALib is imported in src/salmopy/calibration/sensitivity.py. "
        "Declare it in an optional-dependencies group (recommended: [calibration])."
    )
    assert has("scikit-learn") or has("sklearn"), (
        "scikit-learn is imported in src/salmopy/calibration/surrogate.py. "
        "Declare it in an optional-dependencies group (recommended: [calibration])."
    )


def test_dev_extra_pulls_calibration_transitively():
    """[dev] should be the 'install everything a contributor needs' group
    and must include the calibration extra so `pip install -e .[dev]` is
    enough to run the calibration tests."""
    data = _load_pyproject()
    dev = data["project"]["optional-dependencies"].get("dev", [])
    assert any("salmopy[calibration]" in d for d in dev), (
        "The [dev] extra must include 'salmopy[calibration]' so a clean "
        "dev install brings SALib + scikit-learn. Currently dev can't run "
        "the calibration tests from scratch."
    )
