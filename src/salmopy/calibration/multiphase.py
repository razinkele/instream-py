"""Sequential multi-phase calibration.

Adapted from osmopy's `calibration/multiphase.py`. Runs a user-defined
sequence of phases — each phase optimizes a subset of FreeParameters
and passes the best values forward as fixed params to the next phase.

Supports two scipy algorithms:
  - "nelder-mead" via `scipy.optimize.minimize` (local search, cheap)
  - "differential-evolution" via `scipy.optimize.differential_evolution`
    (global search, more evals)

Use nelder-mead for fine-tuning after a preflight + Sobol has
identified the important params; differential-evolution for a one-shot
global scan when the objective has multiple basins.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from salmopy.calibration.problem import FreeParameter


@dataclass
class CalibrationPhase:
    """One sequential optimization phase.

    Attributes
    ----------
    name : str
        Human-readable label (used in logs + history).
    free_params : list[FreeParameter]
        Parameters this phase will search over. The phase's fixed_params
        (including any values optimized by earlier phases) are passed
        unchanged to eval_fn.
    algorithm : str
        "nelder-mead" or "differential-evolution".
    max_iter : int
        Max iterations / generations.
    tol : float
        Convergence tolerance (xatol/tol for scipy).
    """
    name: str
    free_params: List[FreeParameter]
    algorithm: str = "nelder-mead"
    max_iter: int = 100
    tol: float = 1e-4


@dataclass
class PhaseResult:
    """Outcome of one CalibrationPhase run."""
    name: str
    algorithm: str
    best_overrides: Dict[str, float]     # physical-space values
    best_score: float
    n_evals: int
    converged: bool
    message: str = ""


class MultiPhaseCalibrator:
    """Runs a sequence of CalibrationPhase objects.

    Each phase optimizes its `free_params`; at the end, their best
    physical-space values are added to `fixed_params` for the next
    phase. eval_fn should produce a scalar loss given a dict of
    overrides (physical-space values).

    Parameters
    ----------
    phases : list[CalibrationPhase]
    eval_fn : callable(overrides) -> float
        Takes a dict {key: physical_value} and returns a scalar loss
        (lower = better). NaN / inf are treated as +inf.
    initial_fixed : dict, optional
        Overrides held fixed across all phases (e.g. config knobs
        not being calibrated).
    verbose : bool
        If True, print per-evaluation loss.
    """

    def __init__(
        self,
        phases: Sequence[CalibrationPhase],
        eval_fn: Callable[[Dict[str, float]], float],
        initial_fixed: Optional[Dict[str, float]] = None,
        verbose: bool = False,
    ):
        self.phases = list(phases)
        self.eval_fn = eval_fn
        # v0.43.5 Task D1: save the initial set separately so .run() can
        # cold-start from it. Previously .run() mutated self.fixed_params
        # with each phase's best_overrides, silently warm-starting any
        # subsequent .run() call.
        self._initial_fixed_params: Dict[str, float] = dict(initial_fixed or {})
        self.fixed_params: Dict[str, float] = dict(self._initial_fixed_params)
        self.verbose = verbose
        self._eval_count = 0

    def _safe_eval(self, overrides: Dict[str, float]) -> float:
        self._eval_count += 1
        try:
            val = self.eval_fn(overrides)
        except Exception as e:
            if self.verbose:
                print(f"  eval error: {e}")
            return float("inf")
        if not np.isfinite(val):
            return float("inf")
        if self.verbose:
            print(f"  eval #{self._eval_count}: score={val:.4f}")
        return float(val)

    def _phase_objective(
        self, phase: CalibrationPhase
    ) -> Callable[[np.ndarray], float]:
        """Produce the scalar objective function scipy will minimize.

        `x` is in optimizer space (log10 for LOG params); the function
        converts to physical, merges with fixed_params, calls eval_fn.
        """
        def obj(x: np.ndarray) -> float:
            overrides: Dict[str, float] = dict(self.fixed_params)
            for p, xi in zip(phase.free_params, x):
                overrides[p.key] = p.to_physical(float(xi))
            return self._safe_eval(overrides)
        return obj

    def run_phase(self, phase: CalibrationPhase) -> PhaseResult:
        from scipy.optimize import minimize, differential_evolution

        self._eval_count = 0
        bounds = [p.bounds_optimizer() for p in phase.free_params]
        x0 = np.array([0.5 * (lo + hi) for lo, hi in bounds])
        obj = self._phase_objective(phase)

        if phase.algorithm == "nelder-mead":
            res = minimize(
                obj,
                x0,
                method="Nelder-Mead",
                bounds=bounds,
                options={
                    "maxiter": phase.max_iter,
                    "xatol": phase.tol,
                    "fatol": phase.tol,
                    "disp": False,
                },
            )
            best_x = res.x
            best_score = float(res.fun)
            converged = bool(res.success)
            message = str(res.message)
        elif phase.algorithm == "differential-evolution":
            res = differential_evolution(
                obj,
                bounds,
                maxiter=phase.max_iter,
                tol=phase.tol,
                seed=42,
                polish=True,
            )
            best_x = res.x
            best_score = float(res.fun)
            converged = bool(res.success)
            message = str(res.message)
        else:
            raise ValueError(f"Unknown algorithm: {phase.algorithm!r}")

        best_overrides = {
            p.key: p.to_physical(float(x)) for p, x in zip(phase.free_params, best_x)
        }
        return PhaseResult(
            name=phase.name,
            algorithm=phase.algorithm,
            best_overrides=best_overrides,
            best_score=best_score,
            n_evals=self._eval_count,
            converged=converged,
            message=message,
        )

    def run(self) -> List[PhaseResult]:
        """Execute all phases in order. Best params from each phase feed
        into the next phase's fixed_params.

        v0.43.5 Task D1: resets fixed_params to the initial set at entry
        so repeated .run() calls on the same instance are deterministic
        (previously each subsequent call silently warm-started from the
        prior run's best_overrides).
        """
        self.fixed_params = dict(self._initial_fixed_params)
        self._eval_count = 0
        results: List[PhaseResult] = []
        for phase in self.phases:
            if self.verbose:
                print(f"\n=== Phase: {phase.name} ({phase.algorithm}) ===")
            res = self.run_phase(phase)
            # Merge best values into fixed_params for subsequent phases
            self.fixed_params.update(res.best_overrides)
            results.append(res)
            if self.verbose:
                print(
                    f"  done: score={res.best_score:.4f} evals={res.n_evals} "
                    f"converged={res.converged}"
                )
        return results
