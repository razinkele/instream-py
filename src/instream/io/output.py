"""Output writers for inSTREAM simulation results."""

import csv
from pathlib import Path
import numpy as np


def write_population_census(records, output_dir, filename="population_census.csv"):
    """Write census records (collected on census days) to CSV."""
    if not records:
        return
    path = Path(output_dir) / filename
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    return path


def write_fish_snapshot(
    trout_state, species_order, current_date, output_dir, filename=None
):
    """Write individual fish state at a point in time."""
    if filename is None:
        filename = "fish_snapshot_{}.csv".format(current_date)
    path = Path(output_dir) / filename
    alive = trout_state.alive_indices()
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "fish_idx",
                "species",
                "age",
                "length_cm",
                "weight_g",
                "condition",
                "cell_idx",
                "reach_idx",
                "activity",
                "sex",
            ]
        )
        for i in alive:
            sp = (
                species_order[int(trout_state.species_idx[i])]
                if int(trout_state.species_idx[i]) < len(species_order)
                else "Unknown"
            )
            writer.writerow(
                [
                    int(i),
                    sp,
                    int(trout_state.age[i]),
                    round(float(trout_state.length[i]), 4),
                    round(float(trout_state.weight[i]), 4),
                    round(float(trout_state.condition[i]), 4),
                    int(trout_state.cell_idx[i]),
                    int(trout_state.reach_idx[i]),
                    int(trout_state.activity[i]),
                    int(trout_state.sex[i]),
                ]
            )
    return path


def write_redd_snapshot(
    redd_state, species_order, current_date, output_dir, filename=None
):
    """Write redd state at a point in time."""
    if filename is None:
        filename = "redd_snapshot_{}.csv".format(current_date)
    path = Path(output_dir) / filename
    alive_redds = np.where(redd_state.alive)[0]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "redd_idx",
                "species",
                "cell_idx",
                "reach_idx",
                "num_eggs",
                "frac_developed",
                "eggs_initial",
                "eggs_lo_temp",
                "eggs_hi_temp",
                "eggs_dewatering",
                "eggs_scour",
            ]
        )
        for i in alive_redds:
            sp = (
                species_order[int(redd_state.species_idx[i])]
                if int(redd_state.species_idx[i]) < len(species_order)
                else "Unknown"
            )
            writer.writerow(
                [
                    int(i),
                    sp,
                    int(redd_state.cell_idx[i]),
                    int(redd_state.reach_idx[i]),
                    int(redd_state.num_eggs[i]),
                    round(float(redd_state.frac_developed[i]), 6),
                    int(redd_state.eggs_initial[i]),
                    int(redd_state.eggs_lo_temp[i]),
                    int(redd_state.eggs_hi_temp[i]),
                    int(redd_state.eggs_dewatering[i]),
                    int(redd_state.eggs_scour[i]),
                ]
            )
    return path


def write_outmigrants(
    outmigrants, species_order, output_dir, filename="outmigrants.csv"
):
    """Write accumulated outmigrant records."""
    path = Path(output_dir) / filename
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["species", "length_cm", "reach_idx"])
        for om in outmigrants:
            sp = (
                species_order[om["species_idx"]]
                if om["species_idx"] < len(species_order)
                else "Unknown"
            )
            writer.writerow([sp, round(om["length"], 4), om["reach_idx"]])
    return path


def write_cell_snapshot(cell_state, current_date, output_dir, filename=None):
    """Write cell hydraulic and resource state."""
    if filename is None:
        filename = "cell_snapshot_{}.csv".format(current_date)
    path = Path(output_dir) / filename
    n = cell_state.area.shape[0]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "cell_idx",
                "reach_idx",
                "depth_cm",
                "velocity_cms",
                "light",
                "available_drift",
                "available_search",
            ]
        )
        for i in range(n):
            writer.writerow(
                [
                    i,
                    int(cell_state.reach_idx[i]),
                    round(float(cell_state.depth[i]), 4),
                    round(float(cell_state.velocity[i]), 4),
                    round(float(cell_state.light[i]), 4),
                    round(float(cell_state.available_drift[i]), 6),
                    round(float(cell_state.available_search[i]), 6),
                ]
            )
    return path


def write_habitat_summary(cell_state, reach_idx_map, output_dir, date_str):
    """Write habitat summary: total area in each depth/velocity class per reach.

    Parameters
    ----------
    cell_state : CellState
    reach_idx_map : dict mapping reach_idx -> reach_name
    output_dir : str or Path
    date_str : str
    """
    depth_bins = [0, 10, 30, 60, 100, 200, 500]  # cm
    vel_bins = [0, 5, 15, 30, 60, 100]  # cm/s
    depth_labels = ["0-10", "10-30", "30-60", "60-100", "100-200", "200+"]
    vel_labels = ["0-5", "5-15", "15-30", "30-60", "60-100", "100+"]

    path = Path(output_dir) / f"habitat-summary-{date_str}.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["reach", "depth_class", "velocity_class", "total_area_cm2", "num_cells"]
        )
        for r_idx, rname in reach_idx_map.items():
            cells = np.where(cell_state.reach_idx == r_idx)[0]
            for di in range(len(depth_labels)):
                d_lo = depth_bins[di]
                d_hi = depth_bins[di + 1] if di + 1 < len(depth_bins) else float("inf")
                for vi in range(len(vel_labels)):
                    v_lo = vel_bins[vi]
                    v_hi = vel_bins[vi + 1] if vi + 1 < len(vel_bins) else float("inf")
                    mask = (
                        (cell_state.depth[cells] >= d_lo)
                        & (cell_state.depth[cells] < d_hi)
                        & (cell_state.velocity[cells] >= v_lo)
                        & (cell_state.velocity[cells] < v_hi)
                    )
                    total_area = float(np.sum(cell_state.area[cells[mask]]))
                    num_cells = int(np.sum(mask))
                    writer.writerow(
                        [rname, depth_labels[di], vel_labels[vi], total_area, num_cells]
                    )
    return str(path)


def write_growth_report(trout_state, species_order, output_dir, date_str):
    """Write growth/bioenergetics diagnostic report per species.

    Parameters
    ----------
    trout_state : TroutState
    species_order : list of str
    output_dir : str or Path
    date_str : str
    """
    path = Path(output_dir) / f"growth-report-{date_str}.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "species",
                "num_alive",
                "mean_length",
                "mean_weight",
                "mean_condition",
                "mean_growth_rate",
                "min_growth_rate",
                "max_growth_rate",
            ]
        )
        for sp_idx, sp_name in enumerate(species_order):
            alive = trout_state.alive_indices()
            sp_mask = trout_state.species_idx[alive] == sp_idx
            sp_alive = alive[sp_mask]
            if len(sp_alive) == 0:
                writer.writerow([sp_name, 0, 0, 0, 0, 0, 0, 0])
                continue
            writer.writerow(
                [
                    sp_name,
                    len(sp_alive),
                    float(np.mean(trout_state.length[sp_alive])),
                    float(np.mean(trout_state.weight[sp_alive])),
                    float(np.mean(trout_state.condition[sp_alive])),
                    float(np.mean(trout_state.last_growth_rate[sp_alive])),
                    float(np.min(trout_state.last_growth_rate[sp_alive])),
                    float(np.max(trout_state.last_growth_rate[sp_alive])),
                ]
            )
    return str(path)


def write_summary(model, output_dir, filename="simulation_summary.csv"):
    """Write end-of-simulation summary."""
    path = Path(output_dir) / filename
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerow(["final_date", str(model.time_manager._current_date.date())])
        writer.writerow(["fish_alive", model.trout_state.num_alive()])
        writer.writerow(["redds_alive", int(np.sum(model.redd_state.alive))])
        writer.writerow(["total_outmigrants", len(model._outmigrants)])
        writer.writerow(["num_reaches", len(model.reach_order)])
        writer.writerow(["num_species", len(model.species_order)])
        writer.writerow(["num_cells", model.fem_space.num_cells])
    return path
