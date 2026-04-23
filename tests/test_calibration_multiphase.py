"""Tests for the multi-phase sequential optimizer."""
import pytest


class TestSinglePhase:
    def test_nelder_mead_finds_optimum(self):
        """Minimize (x - 3)^2 + (y - 7)^2 on [0,10]×[0,10] with
        Nelder-Mead; should converge near (3, 7)."""
        from salmopy.calibration import (
            FreeParameter,
            Transform,
            CalibrationPhase,
            MultiPhaseCalibrator,
        )

        params = [
            FreeParameter("x", 0.0, 10.0, Transform.LINEAR),
            FreeParameter("y", 0.0, 10.0, Transform.LINEAR),
        ]
        phase = CalibrationPhase(
            name="test", free_params=params, algorithm="nelder-mead", max_iter=200, tol=1e-6,
        )

        def eval_fn(ov: dict) -> float:
            return (ov["x"] - 3.0) ** 2 + (ov["y"] - 7.0) ** 2

        cal = MultiPhaseCalibrator([phase], eval_fn)
        results = cal.run()
        assert len(results) == 1
        r = results[0]
        assert r.best_score < 1e-4
        assert abs(r.best_overrides["x"] - 3.0) < 0.05
        assert abs(r.best_overrides["y"] - 7.0) < 0.05

    def test_de_finds_optimum(self):
        """differential-evolution on the same paraboloid."""
        from salmopy.calibration import (
            FreeParameter,
            Transform,
            CalibrationPhase,
            MultiPhaseCalibrator,
        )

        params = [
            FreeParameter("x", 0.0, 10.0, Transform.LINEAR),
            FreeParameter("y", 0.0, 10.0, Transform.LINEAR),
        ]
        phase = CalibrationPhase(
            name="test_de", free_params=params, algorithm="differential-evolution",
            max_iter=30, tol=1e-5,
        )

        def eval_fn(ov: dict) -> float:
            return (ov["x"] - 3.0) ** 2 + (ov["y"] - 7.0) ** 2

        cal = MultiPhaseCalibrator([phase], eval_fn)
        results = cal.run()
        assert results[0].best_score < 1e-2

    def test_log_transform_roundtrip(self):
        """A LOG parameter should hit the correct physical value at optimum."""
        from salmopy.calibration import (
            FreeParameter,
            Transform,
            CalibrationPhase,
            MultiPhaseCalibrator,
        )

        # Optimum at x = 5.0 with LOG transform
        params = [FreeParameter("x", 0.1, 100.0, Transform.LOG)]
        phase = CalibrationPhase(
            name="log_test", free_params=params, algorithm="nelder-mead", max_iter=200,
        )

        def eval_fn(ov: dict) -> float:
            return (ov["x"] - 5.0) ** 2

        cal = MultiPhaseCalibrator([phase], eval_fn)
        r = cal.run()[0]
        assert abs(r.best_overrides["x"] - 5.0) < 0.1

    def test_eval_error_treated_as_inf(self):
        """Exceptions / inf in eval_fn should not crash the calibrator."""
        from salmopy.calibration import (
            FreeParameter,
            Transform,
            CalibrationPhase,
            MultiPhaseCalibrator,
        )

        params = [FreeParameter("x", 0.0, 10.0, Transform.LINEAR)]
        phase = CalibrationPhase(
            name="err", free_params=params, algorithm="nelder-mead", max_iter=30,
        )

        def eval_fn(ov: dict) -> float:
            x = ov["x"]
            if x < 2.0:
                raise RuntimeError("simulated eval crash")
            if x > 8.0:
                return float("nan")
            return (x - 5.0) ** 2

        cal = MultiPhaseCalibrator([phase], eval_fn)
        r = cal.run()[0]
        # Should still land somewhere in [2, 8]
        assert 1.5 < r.best_overrides["x"] < 8.5


class TestSequentialPhases:
    def test_second_phase_sees_first_phase_fix(self):
        """Two-phase: phase 1 optimizes x, phase 2 sees x as fixed."""
        from salmopy.calibration import (
            FreeParameter,
            Transform,
            CalibrationPhase,
            MultiPhaseCalibrator,
        )

        phase1 = CalibrationPhase(
            name="x",
            free_params=[FreeParameter("x", 0.0, 10.0, Transform.LINEAR)],
            algorithm="nelder-mead",
            max_iter=100,
        )
        phase2 = CalibrationPhase(
            name="y",
            free_params=[FreeParameter("y", 0.0, 10.0, Transform.LINEAR)],
            algorithm="nelder-mead",
            max_iter=100,
        )

        # Objective: (x - 3)^2 + (y - 7)^2
        def eval_fn(ov: dict) -> float:
            return (ov.get("x", 0.0) - 3.0) ** 2 + (ov.get("y", 0.0) - 7.0) ** 2

        cal = MultiPhaseCalibrator([phase1, phase2], eval_fn)
        results = cal.run()
        assert len(results) == 2
        # After phase 1, x should be near 3
        assert abs(results[0].best_overrides["x"] - 3.0) < 0.1
        # After phase 2, y should be near 7 AND cal.fixed_params should have x
        assert abs(results[1].best_overrides["y"] - 7.0) < 0.1
        assert abs(cal.fixed_params["x"] - 3.0) < 0.1

    def test_initial_fixed_respected(self):
        from salmopy.calibration import (
            FreeParameter,
            Transform,
            CalibrationPhase,
            MultiPhaseCalibrator,
        )

        phase = CalibrationPhase(
            name="y",
            free_params=[FreeParameter("y", 0.0, 10.0, Transform.LINEAR)],
            algorithm="nelder-mead",
            max_iter=100,
        )

        def eval_fn(ov: dict) -> float:
            # x is fixed in initial_fixed at 1.0; without it, x=0 in ov
            return (ov["x"] - 3.0) ** 2 + (ov["y"] - 7.0) ** 2

        cal = MultiPhaseCalibrator([phase], eval_fn, initial_fixed={"x": 1.0})
        r = cal.run()[0]
        # y should be optimized; x stays at 1.0 (not updated)
        assert abs(r.best_overrides["y"] - 7.0) < 0.1
        assert cal.fixed_params["x"] == 1.0


class TestUnknownAlgorithm:
    def test_raises_value_error(self):
        from salmopy.calibration import (
            FreeParameter,
            Transform,
            CalibrationPhase,
            MultiPhaseCalibrator,
        )

        phase = CalibrationPhase(
            name="bad",
            free_params=[FreeParameter("x", 0.0, 1.0, Transform.LINEAR)],
            algorithm="not-a-real-method",
        )
        cal = MultiPhaseCalibrator([phase], lambda ov: 0.0)
        with pytest.raises(ValueError):
            cal.run()
