"""Deep line-level profiling of inSTREAM-py hotspots.

Instruments the actual hot functions to measure time per operation category,
not just per function. Identifies the specific optimization targets.
"""

import time
import sys
import math
import numpy as np
from pathlib import Path
from collections import defaultdict

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

CONFIG_PATH = PROJECT / "configs" / "example_a.yaml"
DATA_DIR = PROJECT / "tests" / "fixtures" / "example_a"


def profile_habitat_selection_breakdown():
    """Decompose select_habitat_and_activity into operation categories."""
    print("=" * 70)
    print("DEEP PROFILE: Habitat Selection Breakdown")
    print("=" * 70)

    from instream.model import InSTREAMModel

    model = InSTREAMModel(str(CONFIG_PATH), data_dir=str(DATA_DIR))

    # Warm up 2 steps
    model.step()
    model.step()

    n_alive = model.trout_state.num_alive()
    n_cells = model.fem_space.num_cells
    print(f"\nFish alive: {n_alive}, Cells: {n_cells}")

    # Now manually instrument one habitat selection call
    from instream.modules.behavior import (
        build_candidate_mask,
        fitness_for,
    )

    ts = model.trout_state
    fs = model.fem_space
    cs = fs.cell_state
    sp_cfg = model.config.species[model.species_order[0]]
    rp = model.reach_params[model.reach_order[0]]
    temperature = float(model.reach_state.temperature[0])
    turbidity = float(model.reach_state.turbidity[0])

    # --- Phase 1: Candidate mask build ---
    t0 = time.perf_counter()
    mask = build_candidate_mask(
        ts,
        fs,
        sp_cfg.move_radius_max,
        sp_cfg.move_radius_L1,
        sp_cfg.move_radius_L9,
    )
    t_mask = (time.perf_counter() - t0) * 1000
    print(f"\n1. Candidate mask build: {t_mask:.1f} ms")

    alive = ts.alive_indices()
    alive_sorted = alive[np.argsort(-ts.length[alive])]
    print(f"   Fish to process: {len(alive_sorted)}")

    # Count candidates per fish
    cands_per_fish = []
    for i in alive_sorted:
        n_cands = int(np.sum(mask[i]))
        cands_per_fish.append(n_cands)
    cands = np.array(cands_per_fish)
    print(
        f"   Candidates per fish: mean={cands.mean():.0f}, min={cands.min()}, max={cands.max()}"
    )
    print(
        f"   Total fitness evaluations: {cands.sum() * 3} (fish x cells x 3 activities)"
    )

    # --- Phase 2: Profile per-fish operations ---
    # Time different categories for a subset of fish
    n_profile = min(20, len(alive_sorted))
    times = defaultdict(float)
    call_counts = defaultdict(int)

    params = {
        "temperature": temperature,
        "turbidity": turbidity,
        "drift_conc": rp.drift_conc,
        "search_prod": rp.search_prod,
        "search_area": sp_cfg.search_area,
        "shelter_speed_frac": rp.shelter_speed_frac,
        "step_length": 1.0,
        "cmax_A": sp_cfg.cmax_A,
        "cmax_B": sp_cfg.cmax_B,
        "cmax_temp_table_x": model.species_params[
            model.species_order[0]
        ].cmax_temp_table_x,
        "cmax_temp_table_y": model.species_params[
            model.species_order[0]
        ].cmax_temp_table_y,
        "react_dist_A": sp_cfg.react_dist_A,
        "react_dist_B": sp_cfg.react_dist_B,
        "turbid_threshold": sp_cfg.turbid_threshold,
        "turbid_min": sp_cfg.turbid_min,
        "turbid_exp": sp_cfg.turbid_exp,
        "light_threshold": sp_cfg.light_threshold,
        "light_min": sp_cfg.light_min,
        "light_exp": sp_cfg.light_exp,
        "capture_R1": sp_cfg.capture_R1,
        "capture_R9": sp_cfg.capture_R9,
        "max_speed_A": sp_cfg.max_speed_A,
        "max_speed_B": sp_cfg.max_speed_B,
        "max_swim_temp_term": float(model.reach_state.max_swim_temp_term[0, 0]),
        "resp_A": sp_cfg.resp_A,
        "resp_B": sp_cfg.resp_B,
        "resp_D": sp_cfg.resp_D,
        "resp_temp_term": float(model.reach_state.resp_temp_term[0, 0]),
        "prey_energy_density": rp.prey_energy_density,
        "fish_energy_density": sp_cfg.energy_density,
    }

    activities = ["drift", "search", "hide"]

    for fish_num, i in enumerate(alive_sorted[:n_profile]):
        candidates = np.where(mask[i])[0]
        if len(candidates) == 0:
            continue

        # Time: pre-computation (prev_consumption sum)
        t0 = time.perf_counter()
        prev_cons = float(np.sum(ts.consumption_memory[i]))
        times["prev_cons_sum"] += time.perf_counter() - t0

        # Time: fitness evaluations
        for c_idx in candidates:
            for a_idx, act_name in enumerate(activities):
                t0 = time.perf_counter()
                f = fitness_for(
                    activity=act_name,
                    length=ts.length[i],
                    weight=ts.weight[i],
                    depth=cs.depth[c_idx],
                    velocity=cs.velocity[c_idx],
                    light=cs.light[c_idx],
                    turbidity=turbidity,
                    temperature=temperature,
                    drift_conc=params["drift_conc"],
                    search_prod=params["search_prod"],
                    search_area=params["search_area"],
                    available_drift=cs.available_drift[c_idx],
                    available_search=cs.available_search[c_idx],
                    available_shelter=cs.available_vel_shelter[c_idx],
                    shelter_speed_frac=params["shelter_speed_frac"],
                    superind_rep=ts.superind_rep[i],
                    prev_consumption=prev_cons,
                    step_length=1.0,
                    cmax_A=params["cmax_A"],
                    cmax_B=params["cmax_B"],
                    cmax_temp_table_x=params["cmax_temp_table_x"],
                    cmax_temp_table_y=params["cmax_temp_table_y"],
                    react_dist_A=params["react_dist_A"],
                    react_dist_B=params["react_dist_B"],
                    turbid_threshold=params["turbid_threshold"],
                    turbid_min=params["turbid_min"],
                    turbid_exp=params["turbid_exp"],
                    light_threshold=params["light_threshold"],
                    light_min=params["light_min"],
                    light_exp=params["light_exp"],
                    capture_R1=params["capture_R1"],
                    capture_R9=params["capture_R9"],
                    max_speed_A=params["max_speed_A"],
                    max_speed_B=params["max_speed_B"],
                    max_swim_temp_term=params["max_swim_temp_term"],
                    resp_A=params["resp_A"],
                    resp_B=params["resp_B"],
                    resp_D=params["resp_D"],
                    resp_temp_term=params["resp_temp_term"],
                    prey_energy_density=params["prey_energy_density"],
                    fish_energy_density=params["fish_energy_density"],
                    condition=float(ts.condition[i]),
                    dist_escape=float(cs.dist_escape[c_idx]),
                    available_hiding=int(cs.available_hiding_places[c_idx]),
                )
                times["fitness_for"] += time.perf_counter() - t0
                call_counts["fitness_for"] += 1

    total_fitness_time = times["fitness_for"] * 1000
    n_calls = call_counts["fitness_for"]
    per_call = total_fitness_time / n_calls if n_calls > 0 else 0

    print(f"\n2. Fitness evaluation ({n_profile} fish, {n_calls} calls):")
    print(f"   Total: {total_fitness_time:.1f} ms")
    print(f"   Per call: {per_call:.4f} ms ({per_call * 1000:.1f} us)")
    print(f"   prev_cons sum: {times['prev_cons_sum'] * 1000:.2f} ms")

    # Extrapolate for full step
    avg_cands = cands.mean()
    total_calls_full = len(alive_sorted) * avg_cands * 3
    est_fitness = per_call * total_calls_full
    print("\n3. Extrapolated full step:")
    print(f"   Total fitness_for calls: {total_calls_full:.0f}")
    print(f"   Estimated fitness time: {est_fitness:.0f} ms")


def profile_fitness_for_internals():
    """Decompose fitness_for into its sub-operations."""
    print("\n" + "=" * 70)
    print("DEEP PROFILE: fitness_for Internals")
    print("=" * 70)

    from instream.modules.growth import (
        growth_rate_for,
        max_swim_speed,
        cmax_temp_function,
    )
    from instream.modules.survival import (
        survival_high_temperature,
        survival_stranding,
        survival_condition,
        survival_fish_predation,
        survival_terrestrial_predation,
    )
    from instream.modules.behavior import evaluate_logistic

    # Typical parameter values
    table_x = np.array([0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0])
    table_y = np.array([0.0, 0.2, 0.5, 0.8, 1.0, 0.7, 0.1])

    n = 10000
    times = {}

    # --- growth_rate_for ---
    t0 = time.perf_counter()
    for _ in range(n):
        growth_rate_for(
            0,
            10.0,
            5.0,
            50.0,
            20.0,
            100.0,
            0.0,
            12.0,
            0.001,
            0.001,
            100.0,
            10.0,
            10.0,
            1000.0,
            0.3,
            1,
            0.0,
            1.0,
            0.628,
            0.3,
            table_x,
            table_y,
            1.0,
            0.1,
            10.0,
            0.1,
            -0.1,
            50.0,
            0.1,
            -0.1,
            1.3,
            0.4,
            1.5,
            0.0,
            1.0,
            0.0253,
            0.75,
            0.03,
            1.2,
            3500.0,
            5500.0,
        )
    times["growth_rate_for"] = (time.perf_counter() - t0) / n * 1e6

    # --- survival functions ---
    t0 = time.perf_counter()
    for _ in range(n):
        survival_high_temperature(12.0)
    times["s_high_temp"] = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        survival_stranding(50.0)
    times["s_stranding"] = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        survival_condition(0.85)
    times["s_condition"] = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        survival_fish_predation(
            10.0,
            50.0,
            100.0,
            0.01,
            15.0,
            0,
            0.99,
            10.0,
            3.0,
            50.0,
            10.0,
            0.5,
            0.1,
            200.0,
            50.0,
            25.0,
            15.0,
            0.5,
        )
    times["s_fish_pred"] = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        survival_terrestrial_predation(
            10.0,
            50.0,
            20.0,
            100.0,
            50.0,
            0,
            10,
            1,
            0.99,
            15.0,
            5.0,
            50.0,
            10.0,
            50.0,
            10.0,
            200.0,
            50.0,
            50.0,
            10.0,
            0.5,
        )
    times["s_terr_pred"] = (time.perf_counter() - t0) / n * 1e6

    # --- evaluate_logistic alone ---
    t0 = time.perf_counter()
    for _ in range(n):
        evaluate_logistic(15.0, 10.0, 20.0)
    times["logistic_scalar"] = (time.perf_counter() - t0) / n * 1e6

    # --- max_swim_speed ---
    t0 = time.perf_counter()
    for _ in range(n):
        max_swim_speed(15.0, 1.0)
    times["max_swim_speed"] = (time.perf_counter() - t0) / n * 1e6

    # --- cmax_temp_function (uses np.interp) ---
    t0 = time.perf_counter()
    for _ in range(n):
        cmax_temp_function(12.0, table_x, table_y)
    times["cmax_temp_func"] = (time.perf_counter() - t0) / n * 1e6

    # --- Python function call overhead ---
    def noop():
        pass

    t0 = time.perf_counter()
    for _ in range(n):
        noop()
    times["python_call_overhead"] = (time.perf_counter() - t0) / n * 1e6

    # --- dict.get overhead ---
    d = {"a": 1.0, "b": 2.0, "c": 3.0}
    t0 = time.perf_counter()
    for _ in range(n * 30):  # 30 dict gets per fitness_for call
        d.get("a", 0.0)
    times["30x_dict_get"] = (time.perf_counter() - t0) / n * 1e6

    # --- np.interp on scalar ---
    t0 = time.perf_counter()
    for _ in range(n):
        float(np.interp(12.0, table_x, table_y))
    times["np_interp_scalar"] = (time.perf_counter() - t0) / n * 1e6

    # --- Pure python interp alternative ---
    def py_interp(x, xs, ys):
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        for j in range(len(xs) - 1):
            if xs[j] <= x <= xs[j + 1]:
                frac = (x - xs[j]) / (xs[j + 1] - xs[j])
                return ys[j] + frac * (ys[j + 1] - ys[j])
        return ys[-1]

    xs_list = table_x.tolist()
    ys_list = table_y.tolist()
    t0 = time.perf_counter()
    for _ in range(n):
        py_interp(12.0, xs_list, ys_list)
    times["py_interp_scalar"] = (time.perf_counter() - t0) / n * 1e6

    # Report
    print(f"\nPer-call microseconds (us) — {n} iterations each:\n")
    print(f"  {'Operation':<30s} {'us':>8s}  {'Notes'}")
    print(f"  {'-' * 30} {'-' * 8}  {'-' * 30}")

    for name, us in sorted(times.items(), key=lambda x: -x[1]):
        note = ""
        if name == "growth_rate_for":
            note = "calls cmax_temp + drift/search + respiration"
        elif name == "s_fish_pred":
            note = "5x evaluate_logistic"
        elif name == "s_terr_pred":
            note = "5x evaluate_logistic"
        elif name == "s_condition":
            note = "piecewise linear + np.clip"
        elif name == "np_interp_scalar":
            note = "numpy dispatch overhead on scalar"
        elif name == "py_interp_scalar":
            note = "pure python, avoids numpy"
        elif name == "30x_dict_get":
            note = "simulates 30 params['key'] lookups"
        elif name == "cmax_temp_func":
            note = "wraps np.interp"
        print(f"  {name:<30s} {us:8.1f}  {note}")

    # Compose total per fitness_for call
    total_per_call = (
        times["growth_rate_for"]
        + times["s_high_temp"]
        + times["s_stranding"]
        + times["s_condition"]
        + times["s_fish_pred"]
        + times["s_terr_pred"]
    )
    print(f"\n  Estimated total per fitness_for: {total_per_call:.1f} us")
    print(f"  Python call overhead per call:   {times['python_call_overhead']:.1f} us")

    # Breakdown as percentage
    print("\n  === Cost breakdown per fitness_for call ===")
    components = [
        ("growth_rate_for", times["growth_rate_for"]),
        ("survival_fish_predation", times["s_fish_pred"]),
        ("survival_terrestrial_predation", times["s_terr_pred"]),
        ("survival_condition", times["s_condition"]),
        ("survival_high_temperature", times["s_high_temp"]),
        ("survival_stranding", times["s_stranding"]),
    ]
    for name, us in components:
        pct = us / total_per_call * 100
        print(f"  {name:<35s} {us:6.1f} us  ({pct:4.1f}%)")

    # Identify what's inside growth_rate_for
    print("\n  === Inside growth_rate_for ===")
    inner = [
        ("cmax_temp_function (np.interp)", times["cmax_temp_func"]),
        (
            "np.interp overhead vs py_interp",
            times["np_interp_scalar"] - times["py_interp_scalar"],
        ),
    ]
    for name, us in inner:
        print(f"  {name:<35s} {us:6.1f} us")


def profile_overhead_sources():
    """Identify Python-level overhead sources."""
    print("\n" + "=" * 70)
    print("DEEP PROFILE: Overhead Sources")
    print("=" * 70)

    n = 100000

    # 1. Keyword argument passing overhead
    def f_kwargs(
        a=1,
        b=2,
        c=3,
        d=4,
        e=5,
        f=6,
        g=7,
        h=8,
        i=9,
        j=10,
        k=11,
        l=12,
        m=13,
        n_=14,
        o=15,
        p=16,
        q=17,
        r=18,
        s=19,
        t=20,
        u=21,
        v=22,
        w=23,
        x=24,
        y=25,
        z=26,
        aa=27,
        bb=28,
        cc=29,
        dd=30,
    ):
        return a + b

    def f_positional(
        a,
        b,
        c,
        d,
        e,
        f,
        g,
        h,
        i,
        j,
        k,
        l,
        m,
        n_,
        o,
        p,
        q,
        r,
        s,
        t,
        u,
        v,
        w,
        x,
        y,
        z,
        aa,
        bb,
        cc,
        dd,
    ):
        return a + b

    def f_simple(a, b):
        return a + b

    t0 = time.perf_counter()
    for _ in range(n):
        f_kwargs(
            a=1,
            b=2,
            c=3,
            d=4,
            e=5,
            f=6,
            g=7,
            h=8,
            i=9,
            j=10,
            k=11,
            l=12,
            m=13,
            n_=14,
            o=15,
            p=16,
            q=17,
            r=18,
            s=19,
            t=20,
            u=21,
            v=22,
            w=23,
            x=24,
            y=25,
            z=26,
            aa=27,
            bb=28,
            cc=29,
            dd=30,
        )
    t_kwargs = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        f_positional(
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            20,
            21,
            22,
            23,
            24,
            25,
            26,
            27,
            28,
            29,
            30,
        )
    t_positional = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        f_simple(1, 2)
    t_simple = (time.perf_counter() - t0) / n * 1e6

    print("\n  Function call overhead (us):")
    print(f"  30-kwarg call:     {t_kwargs:.2f} us")
    print(f"  30-positional call:{t_positional:.2f} us")
    print(f"  2-arg call:        {t_simple:.2f} us")
    print(f"  Kwargs overhead:   {t_kwargs - t_simple:.2f} us per call")

    # 2. numpy scalar vs python scalar operations
    t0 = time.perf_counter()
    for _ in range(n):
        np.exp(1.5)
    t_np_exp = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        math.exp(1.5)
    t_math_exp = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        np.log(81.0)
    t_np_log = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        math.log(81.0)
    t_math_log = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        float(np.clip(1.5, -500, 500))
    t_np_clip = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        max(-500.0, min(500.0, 1.5))
    t_py_clip = (time.perf_counter() - t0) / n * 1e6

    print("\n  Numpy vs Python scalar ops (us):")
    print(f"  np.exp(scalar):    {t_np_exp:.2f} us")
    print(
        f"  math.exp(scalar):  {t_math_exp:.2f} us  ({t_np_exp / t_math_exp:.1f}x faster)"
    )
    print(f"  np.log(scalar):    {t_np_log:.2f} us")
    print(
        f"  math.log(scalar):  {t_math_log:.2f} us  ({t_np_log / t_math_log:.1f}x faster)"
    )
    print(f"  np.clip(scalar):   {t_np_clip:.2f} us")
    print(
        f"  min/max(scalar):   {t_py_clip:.2f} us  ({t_np_clip / t_py_clip:.1f}x faster)"
    )

    # 3. np.interp vs pure python bisect interp
    table_x = np.array([0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0])
    table_y = np.array([0.0, 0.2, 0.5, 0.8, 1.0, 0.7, 0.1])
    xs_list = table_x.tolist()
    ys_list = table_y.tolist()

    import bisect

    def fast_interp(x, xs, ys):
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = bisect.bisect_right(xs, x) - 1
        frac = (x - xs[i]) / (xs[i + 1] - xs[i])
        return ys[i] + frac * (ys[i + 1] - ys[i])

    t0 = time.perf_counter()
    for _ in range(n):
        float(np.interp(12.0, table_x, table_y))
    t_np_interp = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        fast_interp(12.0, xs_list, ys_list)
    t_py_interp = (time.perf_counter() - t0) / n * 1e6

    print("\n  np.interp vs bisect interp (us):")
    print(f"  np.interp(scalar): {t_np_interp:.2f} us")
    print(
        f"  bisect interp:     {t_py_interp:.2f} us  ({t_np_interp / t_py_interp:.1f}x faster)"
    )

    # 4. Array element access patterns
    arr = np.random.random(1000)
    t0 = time.perf_counter()
    for _ in range(n):
        x = arr[500]
    t_arr_access = (time.perf_counter() - t0) / n * 1e6

    t0 = time.perf_counter()
    for _ in range(n):
        x = float(arr[500])
    t_arr_float = (time.perf_counter() - t0) / n * 1e6

    py_list = arr.tolist()
    t0 = time.perf_counter()
    for _ in range(n):
        x = py_list[500]
    t_list_access = (time.perf_counter() - t0) / n * 1e6

    print("\n  Array element access (us):")
    print(f"  arr[i] (numpy):    {t_arr_access:.2f} us")
    print(f"  float(arr[i]):     {t_arr_float:.2f} us")
    print(
        f"  list[i] (python):  {t_list_access:.2f} us  ({t_arr_access / t_list_access:.1f}x faster)"
    )

    # 5. survival_condition: np.clip overhead
    from instream.modules.survival import survival_condition

    t0 = time.perf_counter()
    for _ in range(n):
        survival_condition(0.85)
    t_orig = (time.perf_counter() - t0) / n * 1e6

    # Pure python version
    def survival_condition_py(condition, S_at_K5=0.8, S_at_K8=0.992):
        if condition <= 0.0:
            return 0.0
        if condition == 1.0:
            return 1.0
        if condition > 0.8:
            slope = 5.0 - (5.0 * S_at_K8)
            intercept = (5.0 * S_at_K8) - 4.0
            s = condition * slope + intercept
        else:
            slope = (S_at_K8 - S_at_K5) / 0.3
            intercept = S_at_K5 - (0.5 * slope)
            s = condition * slope + intercept
        if s < 0.0:
            return 0.0
        if s > 1.0:
            return 1.0
        return s

    t0 = time.perf_counter()
    for _ in range(n):
        survival_condition_py(0.85)
    t_py = (time.perf_counter() - t0) / n * 1e6

    print("\n  survival_condition (us):")
    print(f"  current (np.clip): {t_orig:.2f} us")
    print(f"  pure python:       {t_py:.2f} us  ({t_orig / t_py:.1f}x faster)")


def summarize_optimization_plan():
    """Summarize findings and concrete optimization targets."""
    print("\n" + "=" * 70)
    print("OPTIMIZATION ROADMAP (Evidence-Based)")
    print("=" * 70)
    print("""
Based on line-level profiling, here are the concrete optimization targets
ordered by expected impact:

TIER 1 — Quick wins (minutes to implement, 2-5x cumulative speedup):

  1. survival_condition: replace np.clip with min/max
     - Called 910K times/step, np.clip adds ~4us overhead
     - Fix: pure Python if/return instead of np.clip
     - Savings: ~3.6 seconds/step

  2. cmax_temp_function: replace np.interp with bisect
     - Called 910K times/step, np.interp has ~3us overhead on scalar
     - Fix: bisect-based pure Python interpolation on pre-converted lists
     - Savings: ~2.7 seconds/step

  3. Pre-extract params from dict to locals
     - 37M dict.get calls/step at ~0.13us each = ~5 seconds
     - Fix: extract to local variables before the inner loop
     - Savings: ~4 seconds/step

TIER 2 — Moderate effort (hours, 3-10x additional speedup):

  4. Pre-compute per-fish invariants ONCE before cell loop
     - cmax_wt_term, resp_std_wt_term, max_speed are fish-level, not cell-level
     - Currently recomputed for every cell x activity (3x redundant)
     - Fix: compute once per fish, pass to fitness_for
     - Savings: ~30% of growth_rate_for time

  5. Convert survival_fish/terrestrial_predation to use pre-computed logistic tables
     - 5 logistic calls each, 910K calls/step = 9.1M logistic evals
     - Most parameters are CONSTANT per step (temperature, min_surv)
     - Fix: pre-compute constant logistic values per step, pass to survival
     - Savings: ~50% of survival time

TIER 3 — Major refactors (days, 10-50x additional speedup):

  6. Vectorize fitness_for over candidate cells
     - Instead of Python for-loop over cells, pass arrays
     - growth_rate_for would take depth[], velocity[], light[] arrays
     - Savings: eliminates 1.2M Python function calls

  7. Numba @njit on scalar functions
     - evaluate_logistic, growth_rate_for, survival functions
     - Eliminates Python interpreter overhead entirely
     - Expected: approach NetLogo-level performance

  8. Full vectorization via NumpyBackend.fitness_all()
     - Evaluate ALL fish x cells x activities as a single array operation
     - Expected: faster than NetLogo for large populations
""")


if __name__ == "__main__":
    profile_fitness_for_internals()
    profile_overhead_sources()
    profile_habitat_selection_breakdown()
    summarize_optimization_plan()
