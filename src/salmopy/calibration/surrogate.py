"""Gaussian Process surrogate for expensive calibrations.

Adapted from osmopy's `calibration/surrogate.py`. Key use case: one
Salmopy-py example_a run takes 3-20 minutes. A full Nelder-Mead
calibration with 200 evaluations costs 10-60 hours. A GP surrogate
trained on ~50-100 Latin-Hypercube samples can then explore the
parameter space in milliseconds per candidate.

Workflow:
    1. SurrogateCalibrator(params, n_samples=50)
    2. X = cal.generate_samples()          # (n_samples, k) LHS
    3. Y = run_expensive_eval(X)           # (n_samples, n_obj)
    4. cal.fit(X, Y)
    5. best = cal.find_optimum(strategy="weighted_sum", weights=[1.0])
       or cal.find_optimum(strategy="pareto")  # non-dominated set
    6. cal.cross_validate(X, Y, k_folds=5)  # R^2, RMSE diagnostics
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

import numpy as np

from salmopy.calibration.problem import FreeParameter

if TYPE_CHECKING:
    from sklearn.gaussian_process import GaussianProcessRegressor


@dataclass
class SurrogateResult:
    """Output of find_optimum + cross_validate."""
    best_x_optimizer: np.ndarray   # optimizer-space (log10 for LOG)
    best_x_physical: Dict[str, float]
    predicted_y: np.ndarray        # shape (n_obj,)
    strategy: str = "weighted_sum"
    pareto_set: Optional[np.ndarray] = None  # (n_pareto, k) when strategy=pareto


@dataclass
class CrossValidationResult:
    """Per-objective k-fold cross-validation metrics."""
    r2: np.ndarray        # shape (n_obj,)
    rmse: np.ndarray      # shape (n_obj,)
    per_fold: List[Dict[str, np.ndarray]] = field(default_factory=list)


class SurrogateCalibrator:
    """Latin Hypercube + Gaussian Process surrogate.

    Fits one GP per objective column (osmopy convention: decouples
    GP fit failures per-objective). Uses Matern(nu=2.5) kernel
    — common ecologist default for smooth-but-not-infinitely-smooth
    response surfaces.

    Parameters
    ----------
    params : list of FreeParameter
    n_samples : int
        Size of Latin Hypercube. Rule of thumb: 10k where k = len(params),
        so 50 samples for 5 params is plenty.
    seed : int
        Controls LHS sampling and GP optimizer restart (not the GP
        kernel's internal RNG).
    """

    def __init__(
        self,
        params: Sequence[FreeParameter],
        n_samples: int = 50,
        seed: int = 42,
    ):
        self.params = list(params)
        self.n_samples = int(n_samples)
        self.seed = int(seed)
        self._gps: List[GaussianProcessRegressor] = []

    def generate_samples(self) -> np.ndarray:
        """Latin Hypercube Sample in **optimizer space** (log10 for LOG params).

        Returns (n_samples, k) array. Caller converts each column via
        FreeParameter.to_physical before applying overrides.
        """
        from scipy.stats import qmc

        k = len(self.params)
        sampler = qmc.LatinHypercube(d=k, seed=self.seed)
        unit = sampler.random(self.n_samples)  # shape (N, k) in [0, 1]
        X = np.empty_like(unit)
        for j, p in enumerate(self.params):
            lo, hi = p.bounds_optimizer()
            X[:, j] = lo + unit[:, j] * (hi - lo)
        return X

    def fit(self, X: np.ndarray, Y: np.ndarray) -> None:
        """Fit one GP per objective. X is (N, k) in optimizer space;
        Y is (N,) or (N, n_obj)."""
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import Matern, ConstantKernel

        if Y.ndim == 1:
            Y = Y.reshape(-1, 1)
        # One GP per output dim
        self._gps = []
        self.X_train = X.copy()
        self.Y_train = Y.copy()
        kernel = ConstantKernel(1.0, (1e-3, 1e3)) * Matern(
            length_scale=np.ones(X.shape[1]),
            length_scale_bounds=(1e-2, 1e3),
            nu=2.5,
        )
        for j in range(Y.shape[1]):
            gp = GaussianProcessRegressor(
                kernel=kernel,
                n_restarts_optimizer=5,
                normalize_y=True,
                random_state=self.seed + j,
            )
            gp.fit(X, Y[:, j])
            self._gps.append(gp)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict per-objective means. X is (N, k) in optimizer space."""
        if not self._gps:
            raise RuntimeError("call fit() before predict()")
        preds = [gp.predict(X) for gp in self._gps]
        return np.column_stack(preds)

    def find_optimum(
        self,
        strategy: str = "weighted_sum",
        weights: Optional[Sequence[float]] = None,
        n_candidates: int = 10000,
    ) -> SurrogateResult:
        """Search for optimum over the surrogate.

        Strategies:
          - "single" / "weighted_sum": minimize weighted sum of predictions.
            For a single objective this is just argmin of the GP mean.
          - "pareto": return the Pareto non-dominated set of surrogate
            predictions, plus the "best" by weighted_sum as representative.

        Parameters
        ----------
        strategy : str
        weights : sequence of float, optional
            Per-objective weights for weighted_sum. Default = uniform.
        n_candidates : int
            Monte-Carlo candidates in optimizer space.

        Returns
        -------
        SurrogateResult
        """
        if not self._gps:
            raise RuntimeError("call fit() before find_optimum()")

        k = len(self.params)
        bounds = np.array([p.bounds_optimizer() for p in self.params])
        # v0.43.5 Task D2: Latin Hypercube candidates (was uniform MC,
        # which misses narrow optima at parameter bounds). Consistent
        # with the LHS used for training-sample generation.
        from scipy.stats import qmc
        sampler = qmc.LatinHypercube(d=k, seed=self.seed)
        u = sampler.random(n=n_candidates)
        X_cand = bounds[:, 0] + u * (bounds[:, 1] - bounds[:, 0])
        Y_pred = self.predict(X_cand)
        n_obj = Y_pred.shape[1]

        if strategy in ("single", "weighted_sum"):
            w = np.asarray(weights if weights else np.ones(n_obj))
            score = Y_pred @ w
            i = int(np.argmin(score))
            best_x = X_cand[i]
            best_y = Y_pred[i]
            return SurrogateResult(
                best_x_optimizer=best_x,
                best_x_physical={
                    p.key: p.to_physical(float(x))
                    for p, x in zip(self.params, best_x)
                },
                predicted_y=best_y,
                strategy=strategy,
            )
        elif strategy == "pareto":
            dominated = np.zeros(n_candidates, dtype=bool)
            for i in range(n_candidates):
                if dominated[i]:
                    continue
                # y_i dominated if exists j with Y[j] <= Y[i] elementwise and < for some
                less_eq = np.all(Y_pred <= Y_pred[i], axis=1)
                strictly_less = np.any(Y_pred < Y_pred[i], axis=1)
                dominates_i = less_eq & strictly_less
                dominates_i[i] = False
                if dominates_i.any():
                    dominated[i] = True
            pareto_mask = ~dominated
            pareto_X = X_cand[pareto_mask]
            pareto_Y = Y_pred[pareto_mask]
            # Representative: argmin of sum of objectives in the Pareto set
            rep_idx = int(np.argmin(pareto_Y.sum(axis=1)))
            best_x = pareto_X[rep_idx]
            best_y = pareto_Y[rep_idx]
            return SurrogateResult(
                best_x_optimizer=best_x,
                best_x_physical={
                    p.key: p.to_physical(float(x))
                    for p, x in zip(self.params, best_x)
                },
                predicted_y=best_y,
                strategy=strategy,
                pareto_set=pareto_X,
            )
        else:
            raise ValueError(f"unknown strategy: {strategy!r}")

    def cross_validate(
        self,
        X: np.ndarray,
        Y: np.ndarray,
        k_folds: int = 5,
    ) -> CrossValidationResult:
        """K-fold CV per objective. Returns R^2 and RMSE per objective."""
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import Matern, ConstantKernel

        if Y.ndim == 1:
            Y = Y.reshape(-1, 1)
        n, k = X.shape
        n_obj = Y.shape[1]
        k_folds = min(k_folds, n)
        rng = np.random.default_rng(self.seed)
        idx = rng.permutation(n)
        fold_size = n // k_folds
        per_fold: List[Dict[str, np.ndarray]] = []
        ss_res = np.zeros(n_obj)
        ss_tot = np.zeros(n_obj)
        se = np.zeros(n_obj)
        count = 0

        y_mean = Y.mean(axis=0)
        for f in range(k_folds):
            test_idx = idx[f * fold_size: (f + 1) * fold_size]
            if f == k_folds - 1:
                test_idx = idx[f * fold_size:]
            train_idx = np.setdiff1d(idx, test_idx)
            X_tr, X_te = X[train_idx], X[test_idx]
            Y_tr, Y_te = Y[train_idx], Y[test_idx]
            kernel = ConstantKernel(1.0, (1e-3, 1e3)) * Matern(
                length_scale=np.ones(k),
                length_scale_bounds=(1e-2, 1e3),
                nu=2.5,
            )
            fold_preds = []
            for j in range(n_obj):
                gp = GaussianProcessRegressor(
                    kernel=kernel,
                    n_restarts_optimizer=3,
                    normalize_y=True,
                    random_state=self.seed + f * 7 + j,
                )
                gp.fit(X_tr, Y_tr[:, j])
                fold_preds.append(gp.predict(X_te))
            pred = np.column_stack(fold_preds)
            per_fold.append({"X_test": X_te, "Y_test": Y_te, "Y_pred": pred})
            ss_res += ((Y_te - pred) ** 2).sum(axis=0)
            ss_tot += ((Y_te - y_mean) ** 2).sum(axis=0)
            se += ((Y_te - pred) ** 2).sum(axis=0)
            count += len(test_idx)

        r2 = 1.0 - ss_res / np.where(ss_tot > 1e-12, ss_tot, 1e-12)
        rmse = np.sqrt(se / max(count, 1))
        return CrossValidationResult(r2=r2, rmse=rmse, per_fold=per_fold)
