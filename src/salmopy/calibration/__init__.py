"""Calibration framework for Salmopy-py.

Ports the core patterns from razinkele/osmopy's calibration module
into an in-process Python/Mesa runner adapted for Salmopy-py:

  - FreeParameter / Transform: declarative decision variables
  - ParityTarget: ecologist-friendly band/RMSE objective specifications
  - evaluate_candidate: drives SalmopyModel.run() with parameter overrides
  - multiseed: wraps any candidate eval across multiple seeds
  - losses: banded log-ratio, RMSE, stability penalty
  - history: JSON run persistence
"""
from __future__ import annotations

from salmopy.calibration.problem import (
    FreeParameter,
    Transform,
    evaluate_candidate,
    apply_overrides,
)
from salmopy.calibration.targets import ParityTarget, load_targets
from salmopy.calibration.losses import (
    banded_log_ratio_loss,
    rmse_loss,
    relative_error_loss,
    stability_penalty,
)
from salmopy.calibration.multiseed import (
    validate_multiseed,
    rank_candidates_multiseed,
)
from salmopy.calibration.history import save_run, load_run, list_runs
from salmopy.calibration.multiphase import (
    CalibrationPhase,
    PhaseResult,
    MultiPhaseCalibrator,
)
try:
    from salmopy.calibration.surrogate import (
        SurrogateCalibrator,
        SurrogateResult,
        CrossValidationResult,
    )
    _HAS_SURROGATE = True
except ImportError:
    _HAS_SURROGATE = False

from salmopy.calibration.ensemble import (
    aggregate_scalars,
    aggregate_trajectories,
    run_replicates,
)
from salmopy.calibration.configure import DiscoveryRule, discover_parameters
from salmopy.calibration.scenarios import Scenario, ScenarioManager
try:
    from salmopy.calibration.sensitivity import (
        SensitivityAnalyzer,
        SensitivityResult,
        MorrisAnalyzer,
    )
    from salmopy.calibration.preflight import (
        preflight_screen,
        format_issues,
        PreflightIssue,
        IssueCategory,
        IssueSeverity,
    )
    _HAS_SENSITIVITY = True
except ImportError:
    # SALib optional; omit sensitivity exports when missing
    _HAS_SENSITIVITY = False

__all__ = [
    "FreeParameter",
    "Transform",
    "evaluate_candidate",
    "apply_overrides",
    "ParityTarget",
    "load_targets",
    "banded_log_ratio_loss",
    "rmse_loss",
    "relative_error_loss",
    "stability_penalty",
    "validate_multiseed",
    "rank_candidates_multiseed",
    "save_run",
    "load_run",
    "list_runs",
    "CalibrationPhase",
    "PhaseResult",
    "MultiPhaseCalibrator",
]

if _HAS_SURROGATE:
    __all__.extend([
        "SurrogateCalibrator",
        "SurrogateResult",
        "CrossValidationResult",
    ])

__all__.extend(["aggregate_scalars", "aggregate_trajectories", "run_replicates"])
__all__.extend([
    "DiscoveryRule", "discover_parameters",
    "Scenario", "ScenarioManager",
])

if _HAS_SENSITIVITY:
    __all__.extend([
        "SensitivityAnalyzer", "SensitivityResult", "MorrisAnalyzer",
        "preflight_screen", "format_issues", "PreflightIssue",
        "IssueCategory", "IssueSeverity",
    ])
