"""Preflight screen — Morris → Sobol funnel with structured issues.

Adapted from osmopy's `calibration/preflight.py`. Two-stage filter
before an expensive optimization campaign:

  1. Morris elementary effects on the full parameter list; flag any
     param whose `mu_star + conf < 0.1 * max(mu_star)` as negligible.
  2. Run Sobol on the survivors only. Flag additional issues from
     Sobol: S1 near zero (flat objective), ST near bound (bound tight).

Returns a list of `PreflightIssue` records with severity + category +
auto-fixable flag. Intended to feed a UI traffic-light or a
`scripts/preflight.py` CLI that suggests YAML edits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from salmopy.calibration.problem import FreeParameter


class IssueCategory(str, Enum):
    NEGLIGIBLE = "negligible"       # Morris flagged param as no-effect
    FLAT_OBJECTIVE = "flat_objective"  # Sobol S1 + ST both ~ 0
    BOUND_TIGHT = "bound_tight"     # Sobol indicates param wants to go past bound
    BLOWUP = "blowup"               # Eval returned inf/NaN for many samples
    ALL_NEGLIGIBLE = "all_negligible"  # Every param flagged as negligible


class IssueSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


@dataclass
class PreflightIssue:
    """One structured preflight finding.

    Attributes
    ----------
    category : IssueCategory
        What kind of issue this is.
    severity : IssueSeverity
        WARNING (calibration will run, but results suspect) or
        ERROR (calibration cannot proceed usefully).
    param : str
        The parameter key. Empty for global issues like ALL_NEGLIGIBLE.
    message : str
        Human-readable summary suitable for a CLI or UI.
    auto_fixable : bool
        True when the preflight code can suggest a concrete remediation
        (e.g. drop param from calibration set).
    metadata : dict
        Free-form numerical evidence (mu_star, S1, etc.).
    """
    category: IssueCategory
    severity: IssueSeverity
    param: str
    message: str
    auto_fixable: bool = False
    metadata: Dict[str, float] = field(default_factory=dict)


def preflight_screen(
    params: Sequence[FreeParameter],
    eval_fn: Callable[[np.ndarray], np.ndarray],
    *,
    morris_trajectories: int = 20,
    sobol_n_base: int = 32,
    negligible_frac: float = 0.1,
    seed: int = 42,
) -> List[PreflightIssue]:
    """Run the two-stage Morris→Sobol screen.

    Parameters
    ----------
    params : list of FreeParameter
    eval_fn : callable(X) -> Y
        X is (N, k) in optimizer space; Y is (N,) or (N, n_obj).
        Caller is responsible for converting optimizer-space values
        to physical via `p.to_physical(x)` before applying overrides.
    morris_trajectories : int
        Morris sample count. Default 20 (a few hundred model evals).
    sobol_n_base : int
        Saltelli base for the second pass. Default 32.
    negligible_frac : float
        Param is negligible if mu_star + conf < negligible_frac * max(mu_star).
    seed : int
        RNG seed for reproducibility.

    Returns
    -------
    list of PreflightIssue
    """
    from salmopy.calibration.sensitivity import (
        MorrisAnalyzer,
        SensitivityAnalyzer,
    )

    issues: List[PreflightIssue] = []

    # ---- Stage 1: Morris on all params ----
    morris = MorrisAnalyzer(params, num_trajectories=morris_trajectories, seed=seed)
    X_m = morris.generate_samples()
    Y_m = eval_fn(X_m)
    if Y_m.ndim == 1:
        Y_m = Y_m.reshape(-1, 1)

    # Detect blowup: any fraction of Y non-finite?
    nonfinite_frac = float(np.mean(~np.isfinite(Y_m)))
    if nonfinite_frac > 0.05:
        issues.append(
            PreflightIssue(
                category=IssueCategory.BLOWUP,
                severity=IssueSeverity.ERROR if nonfinite_frac > 0.5 else IssueSeverity.WARNING,
                param="",
                message=(
                    f"{nonfinite_frac:.0%} of Morris samples produced "
                    f"inf/NaN output — check parameter bounds."
                ),
                metadata={"nonfinite_frac": nonfinite_frac},
            )
        )
        # Replace non-finite with 0 for further analysis
        Y_m = np.where(np.isfinite(Y_m), Y_m, 0.0)

    # Use the first objective column for the screening (ports osmopy)
    m_result = morris.analyze(X_m, Y_m[:, 0])["obj_0"]
    mu_star = m_result["mu_star"]
    conf = m_result["mu_star_conf"]
    names = m_result["names"]
    max_mu = float(mu_star.max()) if mu_star.size else 0.0

    # If max_mu is ~0, the objective is constant — all params are negligible.
    _ALL_NEGLIGIBLE_EPS = 1e-12
    if max_mu < _ALL_NEGLIGIBLE_EPS:
        issues.append(
            PreflightIssue(
                category=IssueCategory.ALL_NEGLIGIBLE,
                severity=IssueSeverity.ERROR,
                param="",
                message=(
                    "Morris mu_star is ~0 for every parameter — objective "
                    "is flat. Review metric_fn or bounds."
                ),
                metadata={"max_mu_star": max_mu},
            )
        )
        return issues

    survivors: List[int] = []
    for i, name in enumerate(names):
        bound = mu_star[i] + conf[i]
        if bound < negligible_frac * max_mu:
            issues.append(
                PreflightIssue(
                    category=IssueCategory.NEGLIGIBLE,
                    severity=IssueSeverity.WARNING,
                    param=name,
                    message=(
                        f"Morris mu_star={mu_star[i]:.3g} (+conf {conf[i]:.3g}) "
                        f"< {negligible_frac:.0%} of max {max_mu:.3g}. Drop."
                    ),
                    auto_fixable=True,
                    metadata={
                        "mu_star": float(mu_star[i]),
                        "mu_star_conf": float(conf[i]),
                        "max_mu_star": max_mu,
                    },
                )
            )
        else:
            survivors.append(i)

    if not survivors:
        issues.append(
            PreflightIssue(
                category=IssueCategory.ALL_NEGLIGIBLE,
                severity=IssueSeverity.ERROR,
                param="",
                message=(
                    "All parameters flagged as negligible by Morris. Objective "
                    "may be flat; review bounds or metric_fn."
                ),
            )
        )
        return issues

    # ---- Stage 2: Sobol on survivors ----
    sobol_params = [params[i] for i in survivors]
    sobol = SensitivityAnalyzer(sobol_params, n_base=sobol_n_base, seed=seed)
    X_s = sobol.generate_samples()
    # Pin non-survivors to their midpoint
    full_X = np.empty((X_s.shape[0], len(params)), dtype=np.float64)
    for j, p in enumerate(params):
        lo, hi = p.bounds_optimizer()
        full_X[:, j] = 0.5 * (lo + hi)
    for k, src in enumerate(survivors):
        full_X[:, src] = X_s[:, k]
    Y_s = eval_fn(full_X)
    if Y_s.ndim == 1:
        Y_s = Y_s.reshape(-1, 1)
    s_result = sobol.analyze(Y_s[:, 0])["obj_0"]

    for k, src in enumerate(survivors):
        name = names[src]
        S1 = float(s_result.S1[k])
        ST = float(s_result.ST[k])
        # Flat objective: both S1 and ST ~ 0 means param has no effect
        if abs(S1) < 0.01 and abs(ST) < 0.01:
            issues.append(
                PreflightIssue(
                    category=IssueCategory.FLAT_OBJECTIVE,
                    severity=IssueSeverity.WARNING,
                    param=name,
                    message=(
                        f"Sobol S1={S1:.3f}, ST={ST:.3f}. Objective is flat "
                        f"in this param's range."
                    ),
                    auto_fixable=True,
                    metadata={"S1": S1, "ST": ST},
                )
            )
        # Bound-tight heuristic: ST > 0.5 but S1 << ST means strong
        # non-linear interaction, potentially pushing to bound
        if ST > 0.5 and S1 < 0.1 * ST:
            issues.append(
                PreflightIssue(
                    category=IssueCategory.BOUND_TIGHT,
                    severity=IssueSeverity.WARNING,
                    param=name,
                    message=(
                        f"Sobol ST={ST:.3f} but S1={S1:.3f}: strong nonlinear "
                        f"interaction suggests bounds may clip optimum."
                    ),
                    metadata={"S1": S1, "ST": ST},
                )
            )

    return issues


def format_issues(issues: Sequence[PreflightIssue]) -> str:
    """Render a list of issues as a human-readable report."""
    if not issues:
        return "No preflight issues detected."
    lines = [f"Preflight: {len(issues)} issue(s)"]
    for issue in issues:
        marker = "✗" if issue.severity is IssueSeverity.ERROR else "!"
        who = issue.param if issue.param else "<global>"
        lines.append(
            f"  [{marker}] {issue.category.value:<18} {who:<40} {issue.message}"
        )
    return "\n".join(lines)
