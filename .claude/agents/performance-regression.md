---
name: performance-regression
description: Compare benchmark results against saved baselines after changes to backend code or hot-path modules. Flags regressions >15% as warnings, >30% as failures.
---

# Performance Regression Checker

Detect performance regressions by comparing current benchmark results against saved baselines.

## Scope

Focus on files in:
- `src/instream/backends/` — all three compute backends (numpy, numba, jax)
- `src/instream/agents/trout.py` — growth, survival, movement hot paths
- `src/instream/agents/redd.py` — egg development calculations
- `src/instream/modules/` — bioenergetics, hydraulics interpolation
- `src/instream/space/` — spatial operations

## Steps

### 1. Identify what changed

Check `git diff --name-only HEAD~1` or the current unstaged changes to see which files were modified. If no backend/hot-path files changed, report "No performance-sensitive files modified" and exit.

### 2. Run benchmarks

```bash
conda run -n shiny python benchmarks/bench_full.py 2>&1
```

Capture the full output.

### 3. Load baseline

Read `.benchmarks/baseline.txt` if it exists.

### 4. Compare metrics

Extract and compare these key metrics:
- **Full model step median** (Steps 11-40 median)
- **Initialization time**
- **Hydraulic interpolation** times per cell count
- **Growth/survival function** times

### 5. Report

| Metric | Baseline | Current | Delta | Status |
|--------|----------|---------|-------|--------|
| ... | X ms | Y ms | +Z% | OK / WARN / FAIL |

Thresholds:
- **OK**: Delta <= 15%
- **WARN**: 15% < Delta <= 30%
- **FAIL**: Delta > 30%

If no baseline exists, report current values and suggest saving as baseline.
