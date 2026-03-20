"""CSV hydraulic table reader for inSTREAM depth and velocity files.

Parses the CSV format used by inSTREAM 7 for hydraulic lookup tables.
The format has comment lines (starting with ; or "), a flow-count line,
a flow-values line, and then cell data lines.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np


def _parse_hydraulic_csv(
    path: Union[str, Path],
    return_cell_ids: bool = False,
) -> tuple:
    """Parse an inSTREAM hydraulic CSV file (depths or velocities).

    Parameters
    ----------
    path : str or Path
        Path to the CSV file.
    return_cell_ids : bool
        If True, return a third element: list of cell ID strings.

    Returns
    -------
    flows : np.ndarray, shape (num_flows,), dtype float64
        Flow breakpoint values.
    values : np.ndarray, shape (num_cells, num_flows), dtype float64
        Depth or velocity values per cell per flow.
    cell_ids : list[str]  (only if return_cell_ids=True)
        Cell identifier strings from the first column of each data row.
    """
    path = Path(path)

    with open(path, "r", encoding="utf-8-sig") as fh:
        lines = fh.readlines()

    # Skip comment lines: lines starting with ; or " or that are blank
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if stripped == "" or stripped.startswith(";") or stripped.startswith('"'):
            idx += 1
        else:
            break

    # Line with flow count: e.g. "26,Number of flows in table,,,..."
    count_line = lines[idx].strip()
    num_flows = int(count_line.split(",")[0])
    idx += 1

    # Flow values line: first column empty, rest are flow values
    flow_parts = lines[idx].strip().split(",")
    # First element is empty (or whitespace), remaining are flow values
    flow_values = [float(x) for x in flow_parts[1:] if x.strip() != ""]
    if len(flow_values) != num_flows:
        raise ValueError(
            f"{path}: expected {num_flows} flow values, got {len(flow_values)}"
        )
    flows = np.array(flow_values, dtype=np.float64)
    idx += 1

    # Data lines: cell_id, value_at_flow_1, value_at_flow_2, ...
    cell_ids: list[str] = []
    rows: list[list[float]] = []

    for line_no, line in enumerate(lines[idx:], start=idx + 1):
        stripped = line.strip()
        if stripped == "" or stripped.startswith(";") or stripped.startswith('"'):
            continue
        parts = stripped.split(",")
        cell_ids.append(parts[0])
        row_values = [x.strip() for x in parts[1 : num_flows + 1] if x.strip() != ""]
        if len(row_values) != num_flows:
            raise ValueError(
                f"{path} line {line_no}: expected {num_flows} values, got {len(row_values)} "
                f"for cell {parts[0]}"
            )
        row = [float(x) for x in row_values]
        rows.append(row)

    values = np.array(rows, dtype=np.float64)

    if return_cell_ids:
        return flows, values, cell_ids
    return flows, values


def read_depth_table(
    path: Union[str, Path],
    return_cell_ids: bool = False,
) -> tuple:
    """Read a depth hydraulic table CSV.

    See :func:`_parse_hydraulic_csv` for details.
    """
    return _parse_hydraulic_csv(path, return_cell_ids=return_cell_ids)


def read_velocity_table(
    path: Union[str, Path],
    return_cell_ids: bool = False,
) -> tuple:
    """Read a velocity hydraulic table CSV.

    See :func:`_parse_hydraulic_csv` for details.
    """
    return _parse_hydraulic_csv(path, return_cell_ids=return_cell_ids)
