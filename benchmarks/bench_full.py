"""Comprehensive inSTREAM-py performance benchmark.

Profiles individual operations and full model steps,
compares numpy vs numba backends where applicable.
"""
import time
import sys
import numpy as np
from pathlib import Path

# Add project to path
PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

CONFIG_PATH = PROJECT / "configs" / "example_a.yaml"
FIXTURES_DIR = PROJECT / "tests" / "fixtures"
DATA_DIR = FIXTURES_DIR / "example_a"


def bench(func, *args, n=50, warmup=3, **kwargs):
    """Run func n times after warmup, return (median_ms, min_ms, max_ms)."""
    for _ in range(warmup):
        func(*args, **kwargs)
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        func(*args, **kwargs)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    med = times[len(times) // 2]
    return med, times[0], times[-1]


def fmt(med, mn, mx):
    return f"{med:8.2f} ms  (min={mn:.2f}, max={mx:.2f})"


def bench_hydraulics():
    """Benchmark hydraulic interpolation (vectorized searchsorted+lerp)."""
    print("\n=== Hydraulic Interpolation ===")
    from instream.backends.numpy_backend import NumpyBackend

    backend = NumpyBackend()
    rng = np.random.default_rng(42)
    flows = np.linspace(0.1, 20.0, 10)

    for n_cells in [100, 500, 1373]:
        depths = rng.random((n_cells, 10)) * 100
        vels = rng.random((n_cells, 10)) * 50
        med, mn, mx = bench(backend.update_hydraulics, 5.0, flows, depths, vels, n=200)
        print(f"  {n_cells:5d} cells (numpy):  {fmt(med, mn, mx)}")

    # Numba backend
    try:
        from instream.backends.numba_backend import NumbaBackend
        backend_nb = NumbaBackend()
        for n_cells in [100, 500, 1373]:
            depths = rng.random((n_cells, 10)) * 100
            vels = rng.random((n_cells, 10)) * 50
            med, mn, mx = bench(backend_nb.update_hydraulics, 5.0, flows, depths, vels, n=200, warmup=5)
            print(f"  {n_cells:5d} cells (numba):  {fmt(med, mn, mx)}")
    except Exception as e:
        print(f"  numba: skipped ({e})")


def bench_light():
    """Benchmark light computation."""
    print("\n=== Light Computation ===")
    from instream.backends.numpy_backend import NumpyBackend

    backend = NumpyBackend()

    # compute_light (scalar — per reach)
    med, mn, mx = bench(backend.compute_light, 172, 44.0, 1.0, 0.8, 0.01, 6.0, n=500)
    print(f"  compute_light (1 call):   {fmt(med, mn, mx)}")

    # compute_cell_light (vectorized — per cell)
    for n_cells in [100, 500, 1373]:
        depths = np.random.default_rng(42).random(n_cells) * 100
        med, mn, mx = bench(backend.compute_cell_light, depths, 800.0, 0.01, 5.0, 0.01, n=500)
        print(f"  cell_light {n_cells:5d} cells:  {fmt(med, mn, mx)}")


def bench_logistic():
    """Benchmark logistic function (scalar and vectorized)."""
    print("\n=== Logistic Function ===")
    from instream.modules.behavior import evaluate_logistic, evaluate_logistic_array
    from instream.backends.numpy_backend import NumpyBackend

    backend = NumpyBackend()

    # Scalar
    med, mn, mx = bench(evaluate_logistic, 15.0, 10.0, 20.0, n=5000)
    print(f"  scalar (1 call):          {fmt(med, mn, mx)}")

    # Array via behavior module
    x = np.random.default_rng(42).random(1000) * 30
    med, mn, mx = bench(evaluate_logistic_array, x, 10.0, 20.0, n=1000)
    print(f"  array 1000 vals:          {fmt(med, mn, mx)}")

    # Array via backend
    med, mn, mx = bench(backend.evaluate_logistic, x, 10.0, 20.0, n=1000)
    print(f"  backend 1000 vals:        {fmt(med, mn, mx)}")


def bench_growth_functions():
    """Benchmark individual growth functions."""
    print("\n=== Growth Functions (scalar) ===")
    from instream.modules.growth import (
        cmax_temp_function, drift_intake, search_intake, respiration, growth_rate_for
    )

    table_x = np.array([0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0])
    table_y = np.array([0.0, 0.2, 0.5, 0.8, 1.0, 0.7, 0.1])

    med, mn, mx = bench(cmax_temp_function, 12.0, table_x, table_y, n=5000)
    print(f"  cmax_temp_function:       {fmt(med, mn, mx)}")

    med, mn, mx = bench(drift_intake,
        10.0, 50.0, 20.0, 100.0, 0.0, 0.001, 50.0, 1.0, 10.0, 1,
        1.0, 0.1, 10.0, 0.1, -0.1, 50.0, 0.1, -0.1, 1.3, 0.4, n=2000)
    print(f"  drift_intake:             {fmt(med, mn, mx)}")

    med, mn, mx = bench(search_intake, 20.0, 50.0, 0.001, 100.0, 1.0, 10.0, 1, n=5000)
    print(f"  search_intake:            {fmt(med, mn, mx)}")

    med, mn, mx = bench(respiration, 0.5, 1.2, 20.0, 50.0, 0.03, n=5000)
    print(f"  respiration:              {fmt(med, mn, mx)}")

    med, mn, mx = bench(growth_rate_for,
        0, 10.0, 5.0, 50.0, 20.0, 100.0, 0.0, 12.0,
        0.001, 0.001, 100.0, 10.0, 10.0, 1000.0, 0.3, 1, 0.0, 1.0,
        0.628, 0.3, table_x, table_y,
        1.0, 0.1, 10.0, 0.1, -0.1, 50.0, 0.1, -0.1, 1.3, 0.4,
        1.5, 0.0, 1.0, 0.0253, 0.75, 0.03, 1.2, 3500.0, 5500.0, n=1000)
    print(f"  growth_rate_for (full):   {fmt(med, mn, mx)}")


def bench_survival_functions():
    """Benchmark survival functions."""
    print("\n=== Survival Functions (scalar) ===")
    from instream.modules.survival import (
        survival_high_temperature, survival_condition,
        survival_fish_predation, survival_terrestrial_predation,
    )

    med, mn, mx = bench(survival_high_temperature, 20.0, n=5000)
    print(f"  high_temperature:         {fmt(med, mn, mx)}")

    med, mn, mx = bench(survival_condition, 0.85, n=5000)
    print(f"  condition:                {fmt(med, mn, mx)}")

    med, mn, mx = bench(survival_fish_predation,
        10.0, 50.0, 100.0, 0.01, 15.0, 0, 0.99,
        10.0, 3.0, 50.0, 10.0, 0.5, 0.1, 200.0, 50.0, 25.0, 15.0, 0.5, n=2000)
    print(f"  fish_predation:           {fmt(med, mn, mx)}")

    med, mn, mx = bench(survival_terrestrial_predation,
        10.0, 50.0, 20.0, 100.0, 50.0, 0, 10, 1, 0.99,
        15.0, 5.0, 50.0, 10.0, 50.0, 10.0, 200.0, 50.0, 50.0, 10.0, 0.5, n=2000)
    print(f"  terrestrial_predation:    {fmt(med, mn, mx)}")


def bench_full_model():
    """Benchmark full model initialization and stepping."""
    print("\n=== Full Model (Example A) ===")
    from instream.model import InSTREAMModel

    if not CONFIG_PATH.exists():
        print("  SKIP: config not found at", CONFIG_PATH)
        return None

    # Initialization
    t0 = time.perf_counter()
    model = InSTREAMModel(str(CONFIG_PATH), data_dir=str(DATA_DIR))
    init_time = (time.perf_counter() - t0) * 1000
    print(f"  Initialization:           {init_time:8.0f} ms")
    print(f"  Fish alive:               {model.trout_state.num_alive()}")
    print(f"  Cells:                    {model.fem_space.num_cells}")

    # First 10 steps (includes JIT warmup if numba)
    step_times = []
    for i in range(10):
        t0 = time.perf_counter()
        model.step()
        elapsed = (time.perf_counter() - t0) * 1000
        step_times.append(elapsed)
        alive = model.trout_state.num_alive()

    print(f"  Step 1 (cold):            {step_times[0]:8.0f} ms")
    print(f"  Step 2-10 median:         {sorted(step_times[1:])[4]:8.0f} ms")
    print(f"  Step 2-10 min:            {min(step_times[1:]):8.0f} ms")
    print(f"  Step 2-10 max:            {max(step_times[1:]):8.0f} ms")
    print(f"  Fish alive after 10 days: {alive}")

    # Extended run: 30 more steps
    extended_times = []
    for i in range(30):
        t0 = time.perf_counter()
        model.step()
        extended_times.append((time.perf_counter() - t0) * 1000)

    med = sorted(extended_times)[15]
    print(f"\n  Steps 11-40 median:       {med:8.0f} ms")
    print(f"  Steps 11-40 min:          {min(extended_times):8.0f} ms")
    print(f"  Steps 11-40 max:          {max(extended_times):8.0f} ms")
    print(f"  Fish alive after 40 days: {model.trout_state.num_alive()}")

    # Extrapolate for full run
    days_total = 912  # ~2.5 years (2011-04-01 to 2013-09-30)
    est_total = med * days_total / 1000
    print(f"\n  Estimated full run ({days_total}d): {est_total:8.1f} s  ({est_total/60:.1f} min)")

    return med


def bench_profile_step():
    """Profile a single step to find hottest functions."""
    print("\n=== Step Profile (cProfile top-20) ===")
    import cProfile
    import pstats
    import io
    from instream.model import InSTREAMModel

    if not CONFIG_PATH.exists():
        print("  SKIP: config not found")
        return

    model = InSTREAMModel(str(CONFIG_PATH), data_dir=str(DATA_DIR))
    # Warm up
    for _ in range(3):
        model.step()

    # Profile one step
    pr = cProfile.Profile()
    pr.enable()
    model.step()
    pr.disable()

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(20)
    print(s.getvalue())


def compare_with_netlogo():
    """Compare performance estimates with NetLogo."""
    print("\n" + "=" * 70)
    print("=== Python vs NetLogo Performance Comparison ===")
    print("=" * 70)
    print("""
NetLogo inSTREAM 7.4 Reference Performance (from documentation):
  - Example A (1 reach, ~360 fish, ~1373 cells)
  - Full 2.5-year run (~912 days)
  - NetLogo typical runtime: ~30-60 seconds on modern hardware
  - NetLogo is single-threaded Java with optimized agent primitives

Key differences:
  - NetLogo: optimized C-like agent loops, compiled to JVM bytecode
  - Python (numpy): interpreted loops for per-fish operations, vectorized for array ops
  - Python (numba): JIT-compiled loops, approaching C performance
  - Python (jax): GPU-capable vectorization, best for batch ensemble runs

Expected performance profile:
  | Operation              | NetLogo   | Python (numpy) | Python (numba) | Python (jax)  |
  |------------------------|-----------|----------------|----------------|---------------|
  | Hydraulic interp       | ~1 ms     | ~0.1-0.5 ms    | ~0.05 ms       | ~0.01 ms      |
  | Light computation      | ~0.5 ms   | ~0.1 ms        | ~0.05 ms       | ~0.01 ms      |
  | Habitat selection      | ~10-50 ms | ~500-5000 ms   | ~50-200 ms     | ~10-50 ms     |
  | Growth (per fish)      | ~0.01 ms  | ~0.05-0.1 ms   | ~0.01 ms       | vectorized    |
  | Survival (per fish)    | ~0.01 ms  | ~0.05-0.1 ms   | ~0.01 ms       | vectorized    |
  | Full step (~360 fish)  | ~30-60 ms | ~1-10 sec      | ~100-500 ms    | ~50-200 ms    |
  | Full 912-day run       | ~30-60 s  | ~15-150 min    | ~1.5-7.5 min   | ~0.75-3 min   |

Notes:
  - Python's habitat selection is the #1 bottleneck: O(N_fish * N_candidates * 3_activities)
    with per-fish scalar function calls. This is where Numba/JAX would give 10-50x speedup.
  - The vectorized operations (hydraulics, light) are FASTER than NetLogo.
  - The per-fish scalar loops (growth, survival, fitness) are 5-50x SLOWER than NetLogo.
  - Implementing NumpyBackend.growth_rate(), .survival(), .fitness_all() would close the gap.
""")


if __name__ == "__main__":
    print("=" * 70)
    print("inSTREAM-py Performance Benchmark")
    print("=" * 70)
    print(f"Platform: {sys.platform}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"NumPy: {np.__version__}")
    try:
        import numba
        print(f"Numba: {numba.__version__}")
    except ImportError:
        print("Numba: not available")
    try:
        import jax
        print(f"JAX: {jax.__version__}")
    except ImportError:
        print("JAX: not available")

    bench_hydraulics()
    bench_light()
    bench_logistic()
    bench_growth_functions()
    bench_survival_functions()
    step_median = bench_full_model()
    compare_with_netlogo()
    bench_profile_step()

    print("\n" + "=" * 70)
    print("BENCHMARK COMPLETE")
    print("=" * 70)
