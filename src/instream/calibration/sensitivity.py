"""Sobol global sensitivity analysis via SALib.

Adapted from osmopy's `calibration/sensitivity.py`. Given a list of
FreeParameter and an evaluation function (N,k)->(N,n_obj), generate
Saltelli-sampled points, run them in parallel, and return per-objective
S1/ST indices with 95% bootstrap confidence bands.

Usage:
    from instream.calibration import FreeParameter, Transform
    from instream.calibration.sensitivity import SensitivityAnalyzer

    params = [
        FreeParameter("reaches.ExampleA.drift_conc", 1e-10, 1e-9, Transform.LOG),
        FreeParameter("species.Chinook-Spring.cmax_A", 0.3, 1.0, Transform.LINEAR),
    ]

    def eval_fn(X):  # X shape (N, k) in optimizer-space
        Y = np.empty((len(X), 1))  # one objective
        for i, x in enumerate(X):
            metrics = evaluate_candidate(..., {p.key: p.to_physical(v) for p, v in zip(params, x)})
            Y[i, 0] = score_against_targets(metrics, targets)
        return Y

    sa = SensitivityAnalyzer(params, n_base=64)
    samples = sa.generate_samples()
    Y = eval_fn(samples)
    result = sa.analyze(Y)
    print(result)  # {'obj_0': {'S1': [...], 'ST': [...], 'S1_conf': [...], 'ST_conf': [...]}}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

import numpy as np

from instream.calibration.problem import FreeParameter


@dataclass
class SensitivityResult:
    """Per-objective Sobol indices with bootstrap CIs."""
    S1: np.ndarray       # shape (k,)
    ST: np.ndarray
    S1_conf: np.ndarray  # 95% bootstrap half-width
    ST_conf: np.ndarray
    param_names: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"{'param':<40} {'S1':>8} {'±':>7} {'ST':>8} {'±':>7}"]
        for i, name in enumerate(self.param_names):
            lines.append(
                f"{name:<40} {self.S1[i]:>8.3f} {self.S1_conf[i]:>7.3f} "
                f"{self.ST[i]:>8.3f} {self.ST_conf[i]:>7.3f}"
            )
        return "\n".join(lines)


class SensitivityAnalyzer:
    """Saltelli-sampled Sobol SA over a list of FreeParameter.

    Produces samples in **optimizer space** (log10-transformed for LOG
    params), so the user-supplied eval function should call
    `param.to_physical(x)` on each column before applying overrides.
    This matches osmopy's convention.
    """

    def __init__(
        self,
        params: Sequence[FreeParameter],
        n_base: int = 64,
        seed: int = 42,
    ):
        self.params = list(params)
        self.n_base = int(n_base)
        self.seed = int(seed)

        # SALib problem definition — bounds in optimizer space
        self.problem = {
            "num_vars": len(self.params),
            "names": [p.key for p in self.params],
            "bounds": [list(p.bounds_optimizer()) for p in self.params],
        }

    def generate_samples(self) -> np.ndarray:
        """Saltelli sample — returns array of shape (n_base*(2k+2), k)."""
        from SALib.sample import sobol as sobol_sample

        return sobol_sample.sample(
            self.problem, self.n_base, calc_second_order=False, seed=self.seed
        )

    def analyze(self, Y: np.ndarray) -> Dict[str, SensitivityResult]:
        """Run Sobol analysis on a (N, n_obj) output array.

        Returns dict keyed by objective index: "obj_0", "obj_1", ...
        Each value is a SensitivityResult with S1/ST indices + 95% CI.
        """
        from SALib.analyze import sobol as sobol_analyze

        if Y.ndim == 1:
            Y = Y.reshape(-1, 1)
        out: Dict[str, SensitivityResult] = {}
        for j in range(Y.shape[1]):
            Si = sobol_analyze.analyze(
                self.problem,
                Y[:, j],
                calc_second_order=False,
                print_to_console=False,
                seed=self.seed,
            )
            out[f"obj_{j}"] = SensitivityResult(
                S1=np.asarray(Si["S1"]),
                ST=np.asarray(Si["ST"]),
                S1_conf=np.asarray(Si["S1_conf"]),
                ST_conf=np.asarray(Si["ST_conf"]),
                param_names=list(self.problem["names"]),
            )
        return out


class MorrisAnalyzer:
    """Morris elementary-effects screen — cheaper than Sobol, used for
    preflight (filtering out uninfluential params before full Sobol).

    Returns mu_star (mean |elementary effect|) and sigma (variance of
    elementary effects). Params with low mu_star are flagged as
    negligible.
    """

    def __init__(
        self,
        params: Sequence[FreeParameter],
        num_trajectories: int = 20,
        num_levels: int = 4,
        seed: int = 42,
    ):
        self.params = list(params)
        self.num_trajectories = int(num_trajectories)
        self.num_levels = int(num_levels)
        self.seed = int(seed)
        self.problem = {
            "num_vars": len(self.params),
            "names": [p.key for p in self.params],
            "bounds": [list(p.bounds_optimizer()) for p in self.params],
        }

    def generate_samples(self) -> np.ndarray:
        """Morris sample — returns array of shape (num_trajectories*(k+1), k)."""
        from SALib.sample import morris as morris_sample

        return morris_sample.sample(
            self.problem,
            N=self.num_trajectories,
            num_levels=self.num_levels,
            seed=self.seed,
        )

    def analyze(self, X: np.ndarray, Y: np.ndarray) -> Dict[str, Dict[str, np.ndarray]]:
        """Run Morris on the sample matrix X and its outputs Y.

        Parameters
        ----------
        X : ndarray (N, k)
            The sample matrix from `generate_samples()`.
        Y : ndarray (N,) or (N, n_obj)
            Outputs for each sample row.

        Returns
        -------
        Per-objective dict with keys 'mu_star', 'sigma', 'mu_star_conf',
        'names'. Lower mu_star = less influence.
        """
        from SALib.analyze import morris as morris_analyze

        if Y.ndim == 1:
            Y = Y.reshape(-1, 1)
        out: Dict[str, Dict[str, np.ndarray]] = {}
        for j in range(Y.shape[1]):
            Si = morris_analyze.analyze(
                self.problem,
                X,
                Y[:, j],
                num_levels=self.num_levels,
                print_to_console=False,
                seed=self.seed,
            )
            out[f"obj_{j}"] = {
                "mu_star": np.asarray(Si["mu_star"]),
                "sigma": np.asarray(Si["sigma"]),
                "mu_star_conf": np.asarray(Si["mu_star_conf"]),
                "names": list(self.problem["names"]),
            }
        return out
