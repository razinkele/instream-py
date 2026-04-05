"""Sensitivity analysis — Morris screening for parameter importance."""

import numpy as np
import pandas as pd


def morris_screening(
    config_path,
    data_dir,
    param_specs,
    num_trajectories=10,
    output_metric="mean_population",
    num_steps=100,
    seed=42,
):
    """Run Morris one-at-a-time sensitivity screening.

    Parameters
    ----------
    config_path : str
        Path to base YAML configuration.
    data_dir : str
        Path to data directory.
    param_specs : list of dict
        Each dict: {"name": "species.Chinook-Spring.cmax_A", "min": 0.3, "max": 0.9}
        Dot-path notation: "species.<name>.<field>" or "reaches.<name>.<field>"
    num_trajectories : int
        Number of Morris trajectories (higher = more stable estimates).
    output_metric : str
        One of: "mean_population", "final_population", "mean_length", "total_mortality"
    num_steps : int
        Number of simulation steps per run.
    seed : int
        Random seed for trajectory generation.

    Returns
    -------
    results : pd.DataFrame
        Columns: parameter, mu_star (mean absolute elementary effect),
        sigma (std of elementary effects), mu (mean elementary effect).
    """
    from instream.model import InSTREAMModel
    from instream.io.config import load_config

    rng = np.random.default_rng(seed)
    k = len(param_specs)
    p = 4  # number of levels

    # Generate Morris trajectories
    trajectories = _generate_trajectories(k, num_trajectories, p, rng)

    # Map parameter levels to actual values
    all_effects = {i: [] for i in range(k)}

    for traj in trajectories:
        # Each trajectory has (k+1) points
        prev_output = None
        prev_changed = None

        for point_idx, point in enumerate(traj):
            # Set parameter values
            config = load_config(config_path)
            for i, spec in enumerate(param_specs):
                level = point[i]
                value = spec["min"] + level * (spec["max"] - spec["min"]) / (p - 1)
                _set_param(config, spec["name"], value)

            # Run simulation
            model = InSTREAMModel(config, data_dir=data_dir)
            for _ in range(num_steps):
                if model.time_manager.is_done():
                    break
                model.step()

            output = _extract_metric(model, output_metric)

            if prev_output is not None and prev_changed is not None:
                # Elementary effect
                delta = point[prev_changed] - traj[point_idx - 1][prev_changed]
                if abs(delta) > 0:
                    ee = (output - prev_output) / (delta / (p - 1))
                    all_effects[prev_changed].append(ee)

            prev_output = output
            # Find which parameter changed
            if point_idx < len(traj) - 1:
                diff = traj[point_idx + 1] - point
                changed = np.argmax(np.abs(diff))
                prev_changed = changed

    # Compute Morris statistics
    rows = []
    for i, spec in enumerate(param_specs):
        effects = all_effects[i]
        if len(effects) == 0:
            rows.append(
                {"parameter": spec["name"], "mu_star": 0.0, "sigma": 0.0, "mu": 0.0}
            )
        else:
            effects = np.array(effects)
            rows.append(
                {
                    "parameter": spec["name"],
                    "mu_star": float(np.mean(np.abs(effects))),
                    "sigma": float(np.std(effects)),
                    "mu": float(np.mean(effects)),
                }
            )

    return pd.DataFrame(rows)


def _generate_trajectories(k, r, p, rng):
    """Generate r Morris trajectories for k parameters with p levels."""
    trajectories = []
    for _ in range(r):
        # Random starting point (levels 0 to p-1)
        base = rng.integers(0, p, size=k)
        traj = [base.copy()]

        # Random permutation of parameter indices
        order = rng.permutation(k)
        for idx in order:
            new_point = traj[-1].copy()
            # Move up or down by 1 level
            if new_point[idx] < p - 1:
                new_point[idx] += 1
            else:
                new_point[idx] -= 1
            traj.append(new_point)

        trajectories.append(np.array(traj))
    return trajectories


def _set_param(config, dotpath, value):
    """Set a parameter value using dot-path notation.

    Examples: "species.Chinook-Spring.cmax_A" or "reaches.MainReach.drift_conc"
    """
    parts = dotpath.split(".")
    if len(parts) == 3 and parts[0] == "species":
        species_name, field = parts[1], parts[2]
        if species_name in config.species:
            setattr(config.species[species_name], field, value)
    elif len(parts) == 3 and parts[0] == "reaches":
        reach_name, field = parts[1], parts[2]
        if reach_name in config.reaches:
            setattr(config.reaches[reach_name], field, value)
    elif len(parts) == 2 and parts[0] == "simulation":
        setattr(config.simulation, parts[1], value)


def _extract_metric(model, metric):
    """Extract a scalar output metric from a completed model run."""
    alive = model.trout_state.alive_indices()
    if metric == "mean_population":
        return float(len(alive))
    elif metric == "final_population":
        return float(len(alive))
    elif metric == "mean_length":
        if len(alive) == 0:
            return 0.0
        return float(np.mean(model.trout_state.length[alive]))
    elif metric == "total_mortality":
        total = model.trout_state.alive.shape[0]
        return float(total - len(alive))
    else:
        raise ValueError(f"Unknown metric: {metric}")
