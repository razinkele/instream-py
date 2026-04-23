"""Output writers for Salmopy simulation results."""

import csv
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
import numpy as np


@contextmanager
def _atomic_write_csv(path):
    """Yield a writable file handle whose contents are atomically renamed
    to `path` on successful close. A killed process never leaves a
    half-written CSV visible to readers.

    Uses tempfile.NamedTemporaryFile in the same directory so os.replace
    is a same-volume rename (atomic on POSIX and Windows).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
        newline="",
        encoding="utf-8",
    )
    try:
        yield tmp
        tmp.flush()
        try:
            os.fsync(tmp.fileno())
        except OSError:
            # fsync not supported (e.g., some virtual filesystems)
            pass
        tmp.close()
        os.replace(tmp.name, str(path))
    except Exception:
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


def write_population_census(records, output_dir, filename="population_census.csv"):
    """Write census records (collected on census days) to CSV."""
    if not records:
        return
    path = Path(output_dir) / filename
    with _atomic_write_csv(path) as f:
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
    with _atomic_write_csv(path) as f:
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
    with _atomic_write_csv(path) as f:
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
    outmigrants,
    species_order,
    output_dir,
    filename="outmigrants.csv",
    reach_names=None,
    require_natal_reach=False,
):
    """Write accumulated outmigrant records (NetLogo InSALMO 7.3 compatible).

    Schema mirrors NetLogo 7.3 `Outmigrants-<run>.csv`:
      species, timestep, reach_idx (exit), natal_reach_idx, natal_reach_name,
      age_years, length_category, length_cm, initial_length_cm, superind_rep

    When `require_natal_reach=True`, raise ValueError on any record with
    natal_reach_idx == -1 — used by callers that have configured PSPC
    (Arc K.4) to surface partial wiring early.
    """
    path = Path(output_dir) / filename
    with _atomic_write_csv(path) as f:
        writer = csv.writer(f)
        writer.writerow([
            "species", "timestep", "reach_idx", "natal_reach_idx",
            "natal_reach_name", "age_years", "length_category",
            "length_cm", "initial_length_cm", "superind_rep",
        ])
        for om in outmigrants:
            sp = (
                species_order[om["species_idx"]]
                if om["species_idx"] < len(species_order)
                else "Unknown"
            )
            natal_idx = int(om.get("natal_reach_idx", -1))
            if require_natal_reach and natal_idx < 0:
                raise ValueError(
                    f"outmigrant record missing natal_reach_idx: {om}"
                )
            natal_name = om.get("natal_reach_name") or (
                reach_names[natal_idx]
                if reach_names is not None and 0 <= natal_idx < len(reach_names)
                else ""
            )
            writer.writerow([
                sp,
                int(om.get("timestep", -1)),
                int(om.get("reach_idx", -1)),
                natal_idx,
                natal_name,
                round(float(om.get("age_years", 0.0)), 4),
                om.get("length_category", ""),
                round(float(om.get("length", 0.0)), 4),
                round(float(om.get("initial_length", 0.0)), 4),
                int(om.get("superind_rep", 1)),
            ])
    return path


def write_smolt_production_by_reach(
    outmigrants,
    reach_names,
    reach_pspc,
    year,
    output_dir,
    filename=None,
):
    """Write per-reach smolt production + PSPC achievement (WGBAST Arc K).

    For each (year, reach) pair, counts the outmigrants whose
    `natal_reach_idx` matches the reach and reports it alongside the
    configured Potential Smolt Production Capacity (PSPC) and the
    resulting % achieved. Reaches with no PSPC configured emit blank
    cells for `pspc_smolts_per_year` and `pspc_achieved_pct` (pandas
    reads these as NaN), but still report `smolts_produced`.

    Parameters
    ----------
    outmigrants : list of dicts
        Each record must include `natal_reach_idx`. See
        `write_outmigrants` for the full schema.
    reach_names : sequence of str
        reach_names[i] is the human-readable label for reach index i.
    reach_pspc : sequence of float or None
        reach_pspc[i] is the configured PSPC (smolts/year); None =
        non-assessment reach.
    year : int
        Simulation year this output covers.
    output_dir : path-like
    filename : str, optional
        Default "smolt_production_by_reach_{year}.csv".

    Returns
    -------
    Path to the CSV.

    References
    ----------
    ICES (2025). WGBAST stock annex for sal.27.22-31 + sal.27.32.
    DOI 10.17895/ices.pub.25869088.v2.
    """
    if filename is None:
        filename = f"smolt_production_by_reach_{year}.csv"
    path = Path(output_dir) / filename

    counts = [0] * len(reach_names)
    for om in outmigrants:
        r = int(om.get("natal_reach_idx", -1))
        if 0 <= r < len(counts):
            counts[r] += int(om.get("superind_rep", 1))

    with _atomic_write_csv(path) as f:
        writer = csv.writer(f)
        writer.writerow([
            "year", "reach_idx", "reach_name",
            "smolts_produced", "pspc_smolts_per_year", "pspc_achieved_pct",
        ])
        for i, name in enumerate(reach_names):
            pspc = reach_pspc[i]
            if pspc is None or pspc <= 0:
                pspc_val = ""
                pct = ""
            else:
                pspc_val = round(float(pspc), 2)
                pct = round(counts[i] / float(pspc) * 100.0, 4)
            writer.writerow([year, i, name, counts[i], pspc_val, pct])
    return path


def write_spawner_origin_matrix(
    spawners,
    reach_names,
    year,
    output_dir,
    filename=None,
):
    """Write a natal × spawning reach matrix (WGBAST genetic-MSA shape).

    Each cell m[natal, spawn] is the rep-weighted count of spawners whose
    `natal_reach_idx` equals the row index and `reach_idx` (spawning
    location) equals the column index. Under perfect homing the matrix is
    diagonal; straying populates off-diagonals.

    Parameters
    ----------
    spawners : list of dicts
        Each must contain `natal_reach_idx`, `reach_idx` (spawning),
        `superind_rep`.
    reach_names : sequence of str
    year : int
    output_dir : path-like
    filename : str, optional
        Default "spawner_origin_matrix_{year}.csv".

    Returns
    -------
    Path to the CSV. Row index is `natal_reach`, columns are spawning
    reaches.

    Reference: Östergren et al. 2021 (DOI 10.1098/rspb.2020.3147) archival-
    DNA homogenization; Säisä et al. 2005 (DOI 10.1139/f05-094) population
    genetic structure. WGBAST apportions mixed sea catches back to rivers
    via the analogous genetic MSA matrix.
    """
    import pandas as pd

    if filename is None:
        filename = f"spawner_origin_matrix_{year}.csv"
    path = Path(output_dir) / filename
    n = len(reach_names)
    m = [[0] * n for _ in range(n)]
    for sp in spawners:
        natal = int(sp.get("natal_reach_idx", -1))
        spawn = int(sp.get("reach_idx", -1))
        rep = int(sp.get("superind_rep", 1))
        if 0 <= natal < n and 0 <= spawn < n:
            m[natal][spawn] += rep
    df = pd.DataFrame(m, index=reach_names, columns=reach_names)
    df.index.name = "natal_reach"
    with _atomic_write_csv(path) as f:
        df.to_csv(f, index=False)
    return path


def write_cell_snapshot(cell_state, current_date, output_dir, filename=None):
    """Write cell hydraulic and resource state."""
    if filename is None:
        filename = "cell_snapshot_{}.csv".format(current_date)
    path = Path(output_dir) / filename
    n = cell_state.area.shape[0]
    with _atomic_write_csv(path) as f:
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
    with _atomic_write_csv(path) as f:
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
    with _atomic_write_csv(path) as f:
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
    with _atomic_write_csv(path) as f:
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
