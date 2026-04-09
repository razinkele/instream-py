---
name: bench-regression
description: Run performance benchmarks and compare against saved baselines after modifying backend code or hot-path modules. Use after performance-sensitive changes to detect regressions.
---

# Benchmark Regression Check

Run the full benchmark suite and compare results against saved baselines.

**Project root:** `C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py`

## Steps

### 1. Run benchmarks

```bash
conda run -n shiny python benchmarks/bench_full.py 2>&1 | tee /tmp/bench_current.txt
```

### 2. Check for existing baseline

Look in `.benchmarks/` for a saved baseline file (`baseline.txt`).

- If no baseline exists, save the current run as the new baseline:
  ```bash
  cp /tmp/bench_current.txt .benchmarks/baseline.txt
  ```
  Report: "No baseline found — saved current run as baseline."

### 3. Compare against baseline

If a baseline exists, compare the key metrics:

- **Full model step median** (Steps 11-40 median)
- **Initialization time**
- **Hydraulic interpolation** times per cell count
- **Growth/survival function** times

Flag any metric that regressed by **>15%** from baseline as a warning.
Flag any metric that regressed by **>30%** as a failure.

### 4. Report

Output a summary table:

```
| Metric                  | Baseline | Current | Delta  | Status |
|-------------------------|----------|---------|--------|--------|
| Step median (40 steps)  | X ms     | Y ms    | +Z%    | OK/WARN/FAIL |
| Init time               | ...      | ...     | ...    | ...    |
```

### 5. Update baseline (optional)

If the user confirms, overwrite the baseline:
```bash
cp /tmp/bench_current.txt .benchmarks/baseline.txt
```
