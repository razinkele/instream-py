"""v0.43.5 Task A1: output writers must use atomic write-then-rename so
a killed process can never leave a half-written CSV."""
import inspect

from salmopy.io import output


def test_atomic_helper_exists():
    assert hasattr(output, "_atomic_write_csv"), (
        "output module must expose _atomic_write_csv context manager"
    )


def test_write_population_census_uses_atomic_pattern():
    src = inspect.getsource(output.write_population_census)
    assert "_atomic_write_csv" in src, (
        "write_population_census must use _atomic_write_csv. "
        f"source snippet:\n{src[:500]}"
    )


def test_write_smolt_production_uses_atomic_pattern():
    src = inspect.getsource(output.write_smolt_production_by_reach)
    assert "_atomic_write_csv" in src, (
        "write_smolt_production_by_reach must use _atomic_write_csv."
    )


def test_atomic_write_creates_file_and_removes_temp(tmp_path):
    """_atomic_write_csv leaves no sibling tempfile after successful write."""
    path = tmp_path / "out.csv"
    with output._atomic_write_csv(path) as f:
        f.write("hello,world\n")
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "hello,world\n"
    # No leftover .tmp file
    leftovers = list(tmp_path.glob("*.tmp"))
    assert not leftovers, f"Expected no tempfiles, got {leftovers}"


def test_atomic_write_rollback_on_error(tmp_path):
    """Exception inside the context manager must leave the destination
    path untouched (no partial write visible)."""
    path = tmp_path / "out.csv"
    path.write_text("original\n", encoding="utf-8")
    try:
        with output._atomic_write_csv(path) as f:
            f.write("partial,")
            raise RuntimeError("simulated failure")
    except RuntimeError:
        pass
    # Original content must survive
    assert path.read_text(encoding="utf-8") == "original\n"
    # No leftover .tmp file
    leftovers = list(tmp_path.glob("*.tmp"))
    assert not leftovers
