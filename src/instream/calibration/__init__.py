"""Calibration framework for inSTREAM-py.

Ports the core patterns from razinkele/osmopy's calibration module
into an in-process Python/Mesa runner adapted for inSTREAM-py:

  - FreeParameter / Transform: declarative decision variables
  - ParityTarget: ecologist-friendly band/RMSE objective specifications
  - evaluate_candidate: drives InSTREAMModel.run() with parameter overrides
  - multiseed: wraps any candidate eval across multiple seeds
  - losses: banded log-ratio, RMSE, stability penalty
  - history: JSON run persistence
"""
from __future__ import annotations

from instream.calibration.problem import (
    FreeParameter,
    Transform,
    evaluate_candidate,
    apply_overrides,
)
from instream.calibration.targets import ParityTarget, load_targets
from instream.calibration.losses import (
    banded_log_ratio_loss,
    rmse_loss,
    relative_error_loss,
    stability_penalty,
)
from instream.calibration.multiseed import (
    validate_multiseed,
    rank_candidates_multiseed,
)
from instream.calibration.history import save_run, load_run, list_runs
from instream.calibration.multiphase import (
    CalibrationPhase,
    PhaseResult,
    MultiPhaseCalibrator,
)
try:
    from instream.calibration.surrogate import (
        SurrogateCalibrator,
        SurrogateResult,
        CrossValidationResult,
    )
    _HAS_SURROGATE = True
except ImportError:
    _HAS_SURROGATE = False

from instream.calibration.ensemble import (
    aggregate_scalars,
    aggregate_trajectories,
    run_replicates,
)
try:
    from instream.calibration.sensitivity import (
        SensitivityAnalyzer,
        SensitivityResult,
        MorrisAnalyzer,
    )
    from instream.calibration.preflight import (
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

if _HAS_SENSITIVITY:
    __all__.extend([
        "SensitivityAnalyzer", "SensitivityResult", "MorrisAnalyzer",
        "preflight_screen", "format_issues", "PreflightIssue",
        "IssueCategory", "IssueSeverity",
    ])
