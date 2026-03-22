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
