---
name: profile
description: Use when investigating slow simulation steps, optimizing hot paths, or diagnosing why a model run takes longer than expected. Triggers on "profile", "slow", "bottleneck", "optimize performance", "why is it slow", "speed up".
---

# Performance Profiling

Profile the inSTREAM-py simulation to identify bottlenecks and guide optimization.

**Project root:** `C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py`

## When to Use

- Simulation runs slower than expected
- After adding new per-fish or per-cell logic
- Before optimizing — to identify the actual bottleneck
- After optimization — to verify speedup
- User says "profile", "slow", "bottleneck", "speed up"

**Use bench-regression instead** if you just need to check for regressions against a saved baseline.

## Architecture Quick Reference

| Component | File | % of runtime | Call frequency |
|-----------|------|-------------|----------------|
| Habitat selection | `modules/behavior.py` | ~75% | 1/step, loops over all fish |
| Fitness evaluation | `backends/numba_backend/fitness.py` | nested in above | ~910K calls/step |
| Growth calculation | `modules/growth.py` | ~10% | 1/fish/step |
| Survival functions | `modules/survival.py` | ~5% | 1/fish/step |
| Hydraulic interp | `backends/*/hydraulics` | ~2% | 1/step |
| Environment update | `model_environment.py` | ~3% | 1/step |

## Profiling Levels

Pick the right level for the question being asked:

### Level 1: Quick Timing (30 seconds)

**Question:** "How fast is a single step? How does it compare to baseline?"

```bash
micromamba run -n shiny python benchmarks/bench_full.py 2>&1 | tee /tmp/bench_current.txt
```

Compare against `.benchmarks/baseline.txt` (832ms init, 40ms step median on example_a).

### Level 2: cProfile Function Breakdown (2 minutes)

**Question:** "Which functions are the bottleneck?"

Write a temporary script to `/tmp/profile_run.py`:

```python
import cProfile, pstats, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
# Adjust path if running from /tmp
sys.path.insert(0, r"C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py\src")

from instream.model import InSTREAMModel

CONFIG = r"C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py\configs\example_a.yaml"
DATA = r"C:\Users\arturas.baziukas\OneDrive - ku.lt\HORIZON_EUROPE\inSTREAM\instream-py\tests\fixtures\example_a"

model = InSTREAMModel(CONFIG, data_dir=DATA)
model.step()  # warm up

pr = cProfile.Profile()
pr.enable()
for _ in range(10):
    model.step()
pr.disable()

stats = pstats.Stats(pr)
stats.sort_stats("cumulative")
stats.print_stats(30)
```

Run with: `micromamba run -n shiny python /tmp/profile_run.py`

**Key functions to watch:**
- `select_habitat_and_activity` — should dominate (~75%)
- `fitness_for` / `_evaluate_all_cells` — nested hot path
- `evaluate_logistic` — called ~5000x/step
- `growth_rate_for` — called per fish per candidate cell

### Level 3: Deep Operation Breakdown (5 minutes)

**Question:** "What inside the hot function is slow? Where exactly should I optimize?"

```bash
micromamba run -n shiny python benchmarks/profile_deep.py
```

This instruments individual operations inside habitat selection and fitness evaluation. Reports time breakdown by category (candidate masking, growth calc, survival calc, logistic calls, dict lookups).

### Level 4: Line-Level Profiling (10 minutes)

**Question:** "Which exact lines of code are slow?"

Use py-spy (if installed) for sampling profiler — no code changes needed:

```bash
micromamba run -n shiny py-spy record -o /tmp/profile.svg -- python /tmp/profile_run.py
```

Or use line_profiler for targeted functions:

```python
# Add @profile decorator to target function, then:
# micromamba run -n shiny kernprof -l -v /tmp/profile_run.py
```

## Interpreting Results

### Healthy Step Profile (example_a, ~360 fish, 1373 cells)

| Metric | Expected | Investigate if |
|--------|----------|---------------|
| Init time | ~800ms | >1500ms |
| Step median (warm) | ~40ms | >80ms |
| Habitat selection % | ~75% | >85% (regression) or <50% (new bottleneck elsewhere) |
| Full run (912d) | ~37s | >60s |

### Common Bottleneck Patterns

| Symptom | Likely cause | Where to look |
|---------|-------------|---------------|
| Step time scales with fish count | Per-fish loop in behavior.py | `select_habitat_and_activity` |
| Step time scales with cell count | Candidate evaluation | `fitness_for`, `_evaluate_all_cells` |
| Init time regression | Config parsing or mesh loading | `model_init.py`, `fem_space.py` |
| Many small function calls | Python call overhead | Switch scalar ops to Numba `@njit` |
| Dict/attribute lookup overhead | Hot-path uses kwargs/getattr | Pre-extract to locals before loop |

### Known Optimization Tiers (from profile_deep.py)

**Tier 1 — Quick wins:** Replace np.clip/np.interp with scalar math in hot path, pre-extract dict params to locals.

**Tier 2 — Moderate:** Pre-compute per-fish invariants once (not per candidate cell), cache logistic tables per step.

**Tier 3 — Major:** Batch outer fish loop into Numba kernel (already done for `_evaluate_all_cells`), full vectorization.

## Reporting

After profiling, report a summary table:

```
## Profile Results

| Metric | Value | vs Baseline | Status |
|--------|-------|-------------|--------|
| Init | Xms | +Y% | OK/WARN |
| Step median | Xms | +Y% | OK/WARN |
| Hot path % | X% | — | Normal/Shifted |
| Estimated full run | Xs | +Y% | OK/WARN |

### Bottleneck: [function name]
- Called N times per step
- Accounts for X% of step time
- Root cause: [description]
- Suggested fix: [approach]
```

Thresholds: **WARN** at >15% regression, **FAIL** at >30% (same as bench-regression).

## After Profiling

1. If bottleneck identified → implement fix → re-profile to verify
2. If performance improved → run `bench-regression` skill to update baseline
3. If no clear bottleneck → check if the issue is I/O, config size, or fish count rather than compute
