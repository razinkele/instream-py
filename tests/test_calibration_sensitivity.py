"""Tests for the sensitivity module (SALib Sobol + Morris).

Skipped if SALib isn't installed — it's an optional dep.
"""
import pytest

SALib = pytest.importorskip("SALib")


class TestSensitivityAnalyzer:
    def test_sample_shape(self):
        from salmopy.calibration import FreeParameter, Transform, SensitivityAnalyzer

        params = [
            FreeParameter("a", 0.0, 1.0, Transform.LINEAR),
            FreeParameter("b", 0.1, 10.0, Transform.LOG),
        ]
        sa = SensitivityAnalyzer(params, n_base=16, seed=42)
        X = sa.generate_samples()
        # Saltelli without second-order: N*(k+2) rows
        assert X.shape == (16 * (2 + 2), 2)
        # Column 0 (a, linear) bounded 0..1
        assert X[:, 0].min() >= -1e-9
        assert X[:, 0].max() <= 1 + 1e-9
        # Column 1 (b, log) bounded -1..1 in log10 space
        assert X[:, 1].min() >= -1 - 1e-9
        assert X[:, 1].max() <= 1 + 1e-9

    def test_analyze_single_obj(self):
        """Monotone linear response → S1 close to 1 for influential param,
        ~0 for irrelevant one."""
        from salmopy.calibration import FreeParameter, Transform, SensitivityAnalyzer

        params = [
            FreeParameter("influential", 0.0, 1.0, Transform.LINEAR),
            FreeParameter("noise", 0.0, 1.0, Transform.LINEAR),
        ]
        sa = SensitivityAnalyzer(params, n_base=256, seed=42)
        X = sa.generate_samples()
        # Y depends only on column 0
        Y = X[:, 0] * 10.0
        results = sa.analyze(Y)
        r = results["obj_0"]
        assert r.param_names == ["influential", "noise"]
        # S1 for 'influential' should be near 1, for 'noise' near 0
        assert r.S1[0] > 0.7
        assert abs(r.S1[1]) < 0.3

    def test_summary_renders(self):
        from salmopy.calibration import FreeParameter, Transform, SensitivityAnalyzer

        params = [FreeParameter("x", 0.0, 1.0, Transform.LINEAR)]
        sa = SensitivityAnalyzer(params, n_base=16, seed=42)
        X = sa.generate_samples()
        Y = X[:, 0]
        r = sa.analyze(Y)["obj_0"]
        txt = r.summary()
        assert "x" in txt
        assert "S1" in txt


class TestMorrisAnalyzer:
    def test_sample_shape(self):
        from salmopy.calibration import FreeParameter, Transform, MorrisAnalyzer

        params = [
            FreeParameter("a", 0.0, 1.0, Transform.LINEAR),
            FreeParameter("b", 0.0, 1.0, Transform.LINEAR),
        ]
        m = MorrisAnalyzer(params, num_trajectories=10, seed=42)
        X = m.generate_samples()
        # Morris: N * (k+1) rows
        assert X.shape == (10 * 3, 2)

    def test_analyze_detects_influential(self):
        from salmopy.calibration import FreeParameter, Transform, MorrisAnalyzer

        params = [
            FreeParameter("influential", 0.0, 1.0, Transform.LINEAR),
            FreeParameter("noise", 0.0, 1.0, Transform.LINEAR),
        ]
        m = MorrisAnalyzer(params, num_trajectories=50, seed=42)
        X = m.generate_samples()
        Y = X[:, 0] * 10.0  # depends only on col 0
        results = m.analyze(X, Y)
        mu_star = results["obj_0"]["mu_star"]
        # 'influential' should have much larger mu_star than 'noise'
        assert mu_star[0] > mu_star[1] * 5
