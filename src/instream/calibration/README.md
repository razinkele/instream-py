# Calibration framework

End-to-end parameter calibration for inSTREAM-py, adapted from
[razinkele/osmopy](https://github.com/razinkele/osmopy)'s
`osmose/calibration/` subpackage.

## Quick start

```python
from instream.calibration import (
    FreeParameter, Transform, ParityTarget,
    CalibrationPhase, MultiPhaseCalibrator,
    evaluate_candidate, save_run,
)

# 1. Declare free parameters (in optimizer space; LOG → 10^x behind the scenes)
params = [
    FreeParameter("reaches.ExampleA.drift_conc", 1e-10, 1e-9, Transform.LOG),
    FreeParameter("species.Chinook-Spring.cmax_A", 0.3, 1.0, Transform.LINEAR),
]

# 2. Define targets
targets = [
    ParityTarget(metric="outmigrant_total", reference=41146.0, rtol=0.20),
]

# 3. Build an objective (per-candidate scalar loss)
from instream.calibration.losses import score_against_targets

def metrics_from_model(model):
    outmigs = getattr(model, "_outmigrants", [])
    return {"outmigrant_total": sum(o.get("superind_rep", 1) for o in outmigs)}

def eval_fn(overrides):
    m = evaluate_candidate(
        config_path="configs/example_a.yaml",
        data_dir="tests/fixtures/example_a",
        overrides=overrides,
        metric_fn=metrics_from_model,
        end_date_override="2012-06-30",  # short run for fast iteration
    )
    return score_against_targets(m, targets)

# 4. Optimize
phase = CalibrationPhase("fit", params, algorithm="nelder-mead", max_iter=50)
result = MultiPhaseCalibrator([phase], eval_fn).run()[0]

# 5. Persist
save_run(result.best_overrides, {"score": result.best_score}, algorithm="nelder-mead")
```

Or run the CLI wrapper end-to-end:

```bash
micromamba run -n shiny python scripts/calibrate.py \
    --config configs/example_a.yaml \
    --data-dir tests/fixtures/example_a \
    --end-date 2012-06-30 \
    --targets targets.csv \
    --rules rules.yaml
```

## Module reference

| Module | Purpose | Main API |
|---|---|---|
| `problem.py` | Declare + evaluate candidates | `FreeParameter`, `Transform`, `apply_overrides`, `evaluate_candidate` |
| `targets.py` | Ecologist-friendly targets | `ParityTarget`, `load_targets` |
| `losses.py` | Scalar loss primitives | `banded_log_ratio_loss`, `rmse_loss`, `stability_penalty`, `score_against_targets` |
| `multiseed.py` | Stochastic robustness | `validate_multiseed`, `rank_candidates_multiseed` |
| `history.py` | JSON run persistence | `save_run`, `load_run`, `list_runs` |
| `sensitivity.py` | Global SA (SALib) | `SensitivityAnalyzer`, `MorrisAnalyzer` |
| `preflight.py` | Two-stage Morris→Sobol screen | `preflight_screen`, `PreflightIssue` |
| `multiphase.py` | Sequential scipy optimizer | `CalibrationPhase`, `MultiPhaseCalibrator` |
| `surrogate.py` | GP surrogate for expensive runs | `SurrogateCalibrator` |
| `ensemble.py` | Replicate aggregation | `aggregate_scalars`, `aggregate_trajectories` |
| `configure.py` | Regex param auto-discovery | `DiscoveryRule`, `discover_parameters` |
| `scenarios.py` | Scenario manager | `Scenario`, `ScenarioManager` |

## Typical workflow

1. **Discover**: `discover_parameters(cfg, rules)` — regex scan of
   nested config → list of `FreeParameter`.
2. **Preflight**: `preflight_screen(params, eval_fn)` — drop
   negligible params, flag bound-tight or flat-objective issues before
   burning optimizer cycles.
3. **Optimize**: pick one:
   - `MultiPhaseCalibrator` (scipy Nelder-Mead or differential-
     evolution) for direct cheap-eval calibration.
   - `SurrogateCalibrator` (GP + Latin Hypercube) for expensive
     simulations — train once on ~50 samples, then search the surrogate
     in milliseconds.
4. **Validate**: `validate_multiseed(eval_fn, seeds=(42,123,7,999,2024))`
   — mean/std/CV across seeds.
5. **Persist**: `save_run(...)` → `data/calibration_history/<ts>_<algo>.json`.
6. **Compare**: `ScenarioManager.compare("old", "new")` returns a diff of
   per-key override values.

## Dependencies

Base modules (problem, targets, losses, multiseed, history, ensemble,
configure, scenarios) require only NumPy, scipy, pandas — already
pinned by the core project.

Optional:
- `SALib` (sensitivity.py, preflight.py) — install via
  `micromamba install -n shiny -c conda-forge salib`.
- `scikit-learn` (surrogate.py) — already a core dep.

The `__init__.py` does optional imports so the package still loads if
SALib or sklearn are absent; `SensitivityAnalyzer` etc. are simply
omitted from `__all__` in that case.

## Test coverage

Run the full calibration suite:

```bash
micromamba run -n shiny python -m pytest tests/test_calibration*.py -q
```

75 tests across 8 files — all green in master.

## See also

- `scripts/calibrate.py` — reference end-to-end CLI.
- `scripts/calib_example_a_demo.py` — smallest possible demo.
- `docs/validation/v0.31.0-arc-D-netlogo-comparison.md` — NetLogo
  parity report the framework is designed to close.
- Upstream: https://github.com/razinkele/osmopy (module-level mapping
  in each file's docstring).
