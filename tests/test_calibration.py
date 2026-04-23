"""Tests for the calibration framework.

Covers pure-Python pieces (FreeParameter transforms, apply_overrides,
losses, multiseed aggregation, history). Model-level evaluate_candidate
is tested via one small example_a call marked slow.
"""
import json
import math
from pathlib import Path

import pytest


class TestFreeParameter:
    def test_linear_transform_identity(self):
        from salmopy.calibration import FreeParameter, Transform

        p = FreeParameter("x", 0.0, 10.0, Transform.LINEAR)
        assert p.to_physical(3.0) == 3.0
        assert p.to_optimizer(3.0) == 3.0
        assert p.bounds_optimizer() == (0.0, 10.0)

    def test_log_transform_roundtrip(self):
        from salmopy.calibration import FreeParameter, Transform

        p = FreeParameter("x", 0.1, 10.0, Transform.LOG)
        # bounds: log10(0.1)=-1, log10(10)=1
        assert p.bounds_optimizer() == (-1.0, 1.0)
        assert p.to_physical(0.0) == 1.0  # 10**0 = 1.0
        assert p.to_optimizer(1.0) == 0.0
        for v in [0.1, 0.5, 1.0, 5.0, 10.0]:
            assert p.to_physical(p.to_optimizer(v)) == pytest.approx(v)

    def test_log_transform_rejects_nonpositive(self):
        from salmopy.calibration import FreeParameter, Transform

        p = FreeParameter("x", 0.1, 10.0, Transform.LOG)
        with pytest.raises(ValueError):
            p.to_optimizer(0.0)


class TestApplyOverrides:
    def test_nested_dict_override(self):
        from salmopy.calibration import apply_overrides

        cfg = {"species": {"A": {"cmax_A": 0.6, "cmax_B": 0.7}}}
        apply_overrides(cfg, {"species.A.cmax_A": 0.9})
        assert cfg["species"]["A"]["cmax_A"] == 0.9
        assert cfg["species"]["A"]["cmax_B"] == 0.7  # untouched

    def test_attribute_override(self):
        from salmopy.calibration import apply_overrides
        from types import SimpleNamespace

        inner = SimpleNamespace(cmax_A=0.6)
        outer = SimpleNamespace(simulation=inner)
        apply_overrides(outer, {"simulation.cmax_A": 1.1})
        assert outer.simulation.cmax_A == 1.1

    def test_missing_key_raises(self):
        from salmopy.calibration import apply_overrides

        cfg = {"species": {"A": {}}}
        with pytest.raises(KeyError):
            apply_overrides(cfg, {"species.A.no_such_field": 1.0})


class TestLosses:
    def test_banded_inside_band_zero(self):
        from salmopy.calibration import banded_log_ratio_loss

        assert banded_log_ratio_loss(5.0, 1.0, 10.0) == 0.0
        assert banded_log_ratio_loss(1.0, 1.0, 10.0) == 0.0
        assert banded_log_ratio_loss(10.0, 1.0, 10.0) == 0.0

    def test_banded_below_penalty(self):
        from salmopy.calibration import banded_log_ratio_loss

        # actual=0.1, lower=1.0 → log10(1/0.1)=1, squared=1
        assert banded_log_ratio_loss(0.1, 1.0, 10.0) == pytest.approx(1.0)

    def test_banded_above_penalty(self):
        from salmopy.calibration import banded_log_ratio_loss

        # actual=100, upper=10 → log10(100/10)=1, squared=1
        assert banded_log_ratio_loss(100.0, 1.0, 10.0) == pytest.approx(1.0)

    def test_banded_zero_or_negative_is_inf(self):
        from salmopy.calibration import banded_log_ratio_loss

        assert banded_log_ratio_loss(0.0, 1.0, 10.0) == float("inf")
        assert banded_log_ratio_loss(-1.0, 1.0, 10.0) == float("inf")

    def test_rmse_basic(self):
        from salmopy.calibration import rmse_loss

        # a-r: [1, 0, -1] → sq [1, 0, 1] → mean 2/3 → sqrt ~0.816
        assert rmse_loss([2.0, 3.0, 4.0], [1.0, 3.0, 5.0]) == pytest.approx(
            math.sqrt(2 / 3), rel=1e-6
        )

    def test_rmse_skips_nan(self):
        from salmopy.calibration import rmse_loss

        assert rmse_loss([1.0, float("nan")], [1.0, 2.0]) == 0.0

    def test_relative_error(self):
        from salmopy.calibration import relative_error_loss

        assert relative_error_loss(110.0, 100.0) == pytest.approx(0.1)
        assert relative_error_loss(0.0, 1.0) == 1.0

    def test_stability_stable(self):
        from salmopy.calibration import stability_penalty

        # Constant trajectory → cv=0, trend=0
        assert stability_penalty([5.0] * 10) == 0.0

    def test_stability_trending(self):
        from salmopy.calibration import stability_penalty

        # Monotone increasing → trend > 0
        pen = stability_penalty([1.0, 2.0, 3.0, 4.0, 5.0])
        assert pen > 0.5


class TestScoreAgainstTargets:
    def test_within_rtol_is_zero(self):
        from salmopy.calibration import ParityTarget
        from salmopy.calibration.losses import score_against_targets

        t = ParityTarget("x", 100.0, rtol=0.1)
        # actual=105, ref=100, rel_err=0.05 <= rtol=0.1 → loss 0
        assert score_against_targets({"x": 105.0}, [t]) == 0.0

    def test_within_band_is_zero(self):
        from salmopy.calibration import ParityTarget
        from salmopy.calibration.losses import score_against_targets

        t = ParityTarget("x", 100.0, lower=50.0, upper=200.0)
        assert score_against_targets({"x": 75.0}, [t]) == 0.0

    def test_missing_metric_is_inf(self):
        from salmopy.calibration import ParityTarget
        from salmopy.calibration.losses import score_against_targets

        t = ParityTarget("x", 100.0, rtol=0.1)
        assert score_against_targets({"y": 105.0}, [t]) == float("inf")


class TestMultiseedAggregation:
    def test_validate_single_seed(self):
        from salmopy.calibration import validate_multiseed

        def eval_fn(seed: int) -> dict:
            return {"m": float(seed * 2)}

        stats = validate_multiseed(eval_fn, seeds=[1])
        assert stats["m"]["mean"] == 2.0
        assert stats["m"]["std"] == 0.0
        assert stats["m"]["n"] == 1

    def test_validate_multi_seed(self):
        from salmopy.calibration import validate_multiseed

        def eval_fn(seed: int) -> dict:
            return {"m": float(seed)}

        stats = validate_multiseed(eval_fn, seeds=[1, 2, 3, 4, 5])
        assert stats["m"]["mean"] == pytest.approx(3.0)
        # pstdev of [1..5] = sqrt(2.0) ~ 1.414
        assert stats["m"]["std"] == pytest.approx(math.sqrt(2.0), rel=1e-6)
        assert stats["m"]["cv"] == pytest.approx(math.sqrt(2.0) / 3.0, rel=1e-6)
        assert stats["m"]["worst"] == 5.0
        assert stats["m"]["best"] == 1.0


class TestHistoryRoundtrip:
    def test_save_and_load(self, tmp_path: Path):
        from salmopy.calibration import save_run, load_run, list_runs

        path = save_run(
            {"species.A.cmax_A": 0.9},
            {"outmigrant_total": 20000.0},
            algorithm="nelder-mead",
            seed=42,
            wall_time_s=12.3,
            meta={"note": "test"},
            history_dir=tmp_path,
        )
        rec = load_run(path)
        assert rec["algorithm"] == "nelder-mead"
        assert rec["overrides"] == {"species.A.cmax_A": 0.9}
        assert rec["metrics"]["outmigrant_total"] == 20000.0
        assert rec["meta"] == {"note": "test"}
        assert path in list_runs(tmp_path)

    def test_list_runs_sorts_by_timestamp(self, tmp_path: Path):
        from salmopy.calibration import save_run, list_runs
        import time

        p1 = save_run({}, {}, history_dir=tmp_path)
        time.sleep(0.01)
        p2 = save_run({}, {}, history_dir=tmp_path)
        runs = list_runs(tmp_path)
        assert len(runs) == 2
        assert runs[0] == p1
        assert runs[1] == p2


class TestLoadTargetsCSV:
    def test_basic(self, tmp_path: Path):
        from salmopy.calibration import load_targets

        csv_path = tmp_path / "targets.csv"
        csv_path.write_text(
            "# comment line\n"
            "metric,reference,rtol,atol,lower,upper,weight,source\n"
            "outmig_total,41146,0.2,,,,1.0,NetLogo seed=98\n"
            "juv_length,6.23,0.1,,,,2.0,\n",
            encoding="utf-8",
        )
        targets = load_targets(csv_path)
        assert len(targets) == 2
        assert targets[0].metric == "outmig_total"
        assert targets[0].reference == 41146
        assert targets[0].rtol == 0.2
        assert targets[0].weight == 1.0
        assert targets[1].weight == 2.0
