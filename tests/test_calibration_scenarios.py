"""Tests for scenarios.py — save/load/fork/compare/export."""
import json
import pytest
from pathlib import Path


class TestScenarioRoundtrip:
    def test_save_and_load(self, tmp_path):
        from instream.calibration import Scenario, ScenarioManager

        mgr = ScenarioManager(tmp_path)
        sc = Scenario(
            name="baseline",
            overrides={"species.A.cmax_A": 0.628},
            tags=["v0.32", "NetLogo-match"],
        )
        path = mgr.save(sc)
        assert path.exists()
        loaded = mgr.load("baseline")
        assert loaded.name == "baseline"
        assert loaded.overrides == {"species.A.cmax_A": 0.628}
        assert loaded.tags == ["v0.32", "NetLogo-match"]
        assert loaded.created  # auto-stamped

    def test_list_and_delete(self, tmp_path):
        from instream.calibration import Scenario, ScenarioManager

        mgr = ScenarioManager(tmp_path)
        mgr.save(Scenario(name="a"))
        mgr.save(Scenario(name="b"))
        assert mgr.list() == ["a", "b"]
        mgr.delete("a")
        assert mgr.list() == ["b"]


class TestScenarioValidation:
    def test_rejects_bad_name(self, tmp_path):
        from instream.calibration import Scenario, ScenarioManager

        mgr = ScenarioManager(tmp_path)
        with pytest.raises(ValueError):
            mgr.save(Scenario(name="../etc/passwd"))
        with pytest.raises(ValueError):
            mgr.save(Scenario(name=""))
        with pytest.raises(ValueError):
            mgr.save(Scenario(name="a" * 100))

    def test_accepts_safe_name(self, tmp_path):
        from instream.calibration import Scenario, ScenarioManager

        mgr = ScenarioManager(tmp_path)
        mgr.save(Scenario(name="arc-f_baseline v1.0"))
        assert "arc-f_baseline v1.0" in mgr.list()


class TestFork:
    def test_fork_inherits_and_overrides(self, tmp_path):
        from instream.calibration import Scenario, ScenarioManager

        mgr = ScenarioManager(tmp_path)
        mgr.save(Scenario(
            name="parent",
            overrides={"a": 1.0, "b": 2.0},
            tags=["base"],
        ))
        child = mgr.fork(
            "parent",
            "child",
            overrides_update={"b": 99.0, "c": 3.0},
            tags_add=["experiment"],
        )
        assert child.parent_scenario == "parent"
        assert child.overrides == {"a": 1.0, "b": 99.0, "c": 3.0}
        assert child.tags == ["base", "experiment"]
        # Child persisted
        assert "child" in mgr.list()


class TestCompare:
    def test_compare_diff(self, tmp_path):
        from instream.calibration import Scenario, ScenarioManager

        mgr = ScenarioManager(tmp_path)
        mgr.save(Scenario(name="a", overrides={"x": 1.0, "y": 2.0, "z": 3.0}))
        mgr.save(Scenario(name="b", overrides={"x": 1.0, "y": 99.0, "w": 4.0}))
        diff = mgr.compare("a", "b")
        assert diff["only_in_a"] == {"z": 3.0}
        assert diff["only_in_b"] == {"w": 4.0}
        assert diff["changed"] == {"y": (2.0, 99.0)}


class TestZipRoundtrip:
    def test_export_and_import(self, tmp_path):
        from instream.calibration import Scenario, ScenarioManager

        src_dir = tmp_path / "src"
        mgr_src = ScenarioManager(src_dir)
        mgr_src.save(Scenario(name="alpha", overrides={"a": 1.0}))
        mgr_src.save(Scenario(name="beta", overrides={"b": 2.0}))

        zip_path = tmp_path / "scenarios.zip"
        mgr_src.export_all(zip_path)
        assert zip_path.exists()

        dst_dir = tmp_path / "dst"
        mgr_dst = ScenarioManager(dst_dir)
        imported = mgr_dst.import_all(zip_path)
        assert sorted(imported) == ["alpha", "beta"]
        loaded_alpha = mgr_dst.load("alpha")
        assert loaded_alpha.overrides == {"a": 1.0}

    def test_import_skips_existing_without_overwrite(self, tmp_path):
        from instream.calibration import Scenario, ScenarioManager

        src = ScenarioManager(tmp_path / "src")
        src.save(Scenario(name="alpha", overrides={"a": 1.0}))
        zip_path = tmp_path / "x.zip"
        src.export_all(zip_path)

        dst = ScenarioManager(tmp_path / "dst")
        dst.save(Scenario(name="alpha", overrides={"a": 999.0}))  # existing

        imported = dst.import_all(zip_path, overwrite=False)
        assert imported == []  # skipped
        assert dst.load("alpha").overrides == {"a": 999.0}

        imported2 = dst.import_all(zip_path, overwrite=True)
        assert imported2 == ["alpha"]
        assert dst.load("alpha").overrides == {"a": 1.0}  # overwritten

    def test_import_rejects_path_traversal(self, tmp_path):
        import zipfile
        from instream.calibration import ScenarioManager

        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../evil.json", '{"name": "x"}')

        mgr = ScenarioManager(tmp_path / "dst")
        with pytest.raises(ValueError, match="path separator"):
            mgr.import_all(zip_path)

    def test_import_rejects_malformed_json(self, tmp_path):
        import zipfile
        from instream.calibration import ScenarioManager

        zip_path = tmp_path / "bad.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("garbage.json", "not valid json")

        mgr = ScenarioManager(tmp_path / "dst")
        with pytest.raises(ValueError, match="failed to parse"):
            mgr.import_all(zip_path)
