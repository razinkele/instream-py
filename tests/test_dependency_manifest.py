"""Dependency-manifest invariants.

These tests enforce that every third-party package unconditionally imported
in src/instream is declared in pyproject.toml. A gap here means `pip install
instream` into a clean env breaks at first use of the code path.
"""
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def _load_pyproject():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_meshio_declared_in_core_dependencies():
    """meshio is imported unconditionally in src/instream/space/fem_mesh.py;
    it must be a core dependency so fresh installs work."""
    data = _load_pyproject()
    core = data["project"]["dependencies"]
    assert any(d.lower().startswith("meshio") for d in core), (
        "meshio is imported unconditionally at src/instream/space/fem_mesh.py:7 "
        "but is not listed in pyproject.toml [project.dependencies]. "
        "Add 'meshio>=5.3' to the core dependencies block."
    )


def test_calibration_extra_declares_salib_and_sklearn():
    """SALib and scikit-learn are imported in src/instream/calibration/;
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
        "SALib is imported in src/instream/calibration/sensitivity.py. "
        "Declare it in an optional-dependencies group (recommended: [calibration])."
    )
    assert has("scikit-learn") or has("sklearn"), (
        "scikit-learn is imported in src/instream/calibration/surrogate.py. "
        "Declare it in an optional-dependencies group (recommended: [calibration])."
    )


def test_dev_extra_pulls_calibration_transitively():
    """[dev] should be the 'install everything a contributor needs' group
    and must include the calibration extra so `pip install -e .[dev]` is
    enough to run the calibration tests."""
    data = _load_pyproject()
    dev = data["project"]["optional-dependencies"].get("dev", [])
    assert any("instream[calibration]" in d for d in dev), (
        "The [dev] extra must include 'instream[calibration]' so a clean "
        "dev install brings SALib + scikit-learn. Currently dev can't run "
        "the calibration tests from scratch."
    )
