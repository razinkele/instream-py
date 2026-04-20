"""Tests for the GP surrogate calibrator."""
import pytest

sklearn = pytest.importorskip("sklearn")


class TestLatinHypercubeSampling:
    def test_shape_and_bounds(self):
        from instream.calibration import (
            FreeParameter,
            Transform,
            SurrogateCalibrator,
        )

        params = [
            FreeParameter("a", 0.0, 1.0, Transform.LINEAR),
            FreeParameter("b", 0.1, 10.0, Transform.LOG),
        ]
        cal = SurrogateCalibrator(params, n_samples=30, seed=42)
        X = cal.generate_samples()
        assert X.shape == (30, 2)
        # a in [0, 1]
        assert X[:, 0].min() >= -1e-9 and X[:, 0].max() <= 1.0 + 1e-9
        # b in log10 space: log10(0.1)=-1, log10(10)=1
        assert X[:, 1].min() >= -1.0 - 1e-9 and X[:, 1].max() <= 1.0 + 1e-9


class TestGPFitAndPredict:
    def test_fit_predict_recovers_linear(self):
        """Surrogate on a noise-free linear response should predict
        within 5% of the true value on held-out points."""
        import numpy as np
        from instream.calibration import (
            FreeParameter,
            Transform,
            SurrogateCalibrator,
        )

        params = [FreeParameter("x", 0.0, 10.0, Transform.LINEAR)]
        cal = SurrogateCalibrator(params, n_samples=40, seed=42)
        X = cal.generate_samples()
        Y = (X[:, 0] * 2.0 + 1.0).reshape(-1, 1)  # y = 2x + 1
        cal.fit(X, Y)

        X_test = np.array([[2.5], [5.0], [7.5]])
        Y_pred = cal.predict(X_test)
        expected = np.array([6.0, 11.0, 16.0])
        assert np.allclose(Y_pred.flatten(), expected, rtol=0.05)

    def test_multi_obj_fit(self):
        """Two-column Y: fits two GPs independently."""
        import numpy as np
        from instream.calibration import (
            FreeParameter,
            Transform,
            SurrogateCalibrator,
        )

        params = [FreeParameter("x", 0.0, 10.0, Transform.LINEAR)]
        cal = SurrogateCalibrator(params, n_samples=30, seed=42)
        X = cal.generate_samples()
        Y = np.column_stack([X[:, 0], X[:, 0] ** 2])
        cal.fit(X, Y)

        X_test = np.array([[5.0]])
        pred = cal.predict(X_test)
        assert pred.shape == (1, 2)
        assert abs(pred[0, 0] - 5.0) < 0.5
        assert abs(pred[0, 1] - 25.0) < 2.5

    def test_predict_before_fit_raises(self):
        import numpy as np
        from instream.calibration import (
            FreeParameter,
            Transform,
            SurrogateCalibrator,
        )

        params = [FreeParameter("x", 0.0, 1.0, Transform.LINEAR)]
        cal = SurrogateCalibrator(params, n_samples=10, seed=42)
        with pytest.raises(RuntimeError):
            cal.predict(np.array([[0.5]]))


class TestFindOptimum:
    def test_weighted_sum_finds_min(self):
        """For y = (x-3)^2, surrogate + Monte-Carlo search should land
        near x=3."""
        import numpy as np
        from instream.calibration import (
            FreeParameter,
            Transform,
            SurrogateCalibrator,
        )

        params = [FreeParameter("x", 0.0, 10.0, Transform.LINEAR)]
        cal = SurrogateCalibrator(params, n_samples=40, seed=42)
        X = cal.generate_samples()
        Y = ((X[:, 0] - 3.0) ** 2).reshape(-1, 1)
        cal.fit(X, Y)
        res = cal.find_optimum(strategy="weighted_sum", n_candidates=5000)
        assert abs(res.best_x_physical["x"] - 3.0) < 0.5

    def test_pareto_returns_non_dominated(self):
        """For conflicting objectives, pareto strategy returns a set."""
        import numpy as np
        from instream.calibration import (
            FreeParameter,
            Transform,
            SurrogateCalibrator,
        )

        params = [FreeParameter("x", 0.0, 10.0, Transform.LINEAR)]
        cal = SurrogateCalibrator(params, n_samples=40, seed=42)
        X = cal.generate_samples()
        # y1 = x, y2 = 10 - x — perfectly conflicting
        Y = np.column_stack([X[:, 0], 10.0 - X[:, 0]])
        cal.fit(X, Y)
        res = cal.find_optimum(strategy="pareto", n_candidates=500)
        assert res.pareto_set is not None
        # For 1D conflicting objectives over a range, most candidates are Pareto-optimal
        assert len(res.pareto_set) > 10


class TestCrossValidation:
    def test_cv_returns_sane_r2(self):
        """On a clean linear response, 5-fold CV R^2 should be high."""
        import numpy as np
        from instream.calibration import (
            FreeParameter,
            Transform,
            SurrogateCalibrator,
        )

        params = [FreeParameter("x", 0.0, 10.0, Transform.LINEAR)]
        cal = SurrogateCalibrator(params, n_samples=40, seed=42)
        X = cal.generate_samples()
        Y = (X[:, 0] * 2.0 + 1.0).reshape(-1, 1)
        cv = cal.cross_validate(X, Y, k_folds=5)
        assert cv.r2.shape == (1,)
        assert cv.r2[0] > 0.9
        assert cv.rmse.shape == (1,)
        assert cv.rmse[0] < 1.0
        assert len(cv.per_fold) == 5
