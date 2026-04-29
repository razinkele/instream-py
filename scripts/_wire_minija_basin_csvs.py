"""One-shot CSV regenerator for example_minija_basin (v0.54.0).

Calls `_wire_wgbast_physical_configs.copy_reach_csvs` to expand the
inherited (Byskealven) hydraulic CSVs to match Minija's larger
shapefile cell counts. Without this step, the loader rejects the
fixture with "hydraulic table has N rows but cell count is M".

Use after `_generate_wgbast_physical_domains.py --only example_minija_basin`.

Side effects: rewrites
  tests/fixtures/example_minija_basin/{Mouth,Lower,Middle,Upper,BalticCoast}-{Depths,Vels,TimeSeriesInputs}.csv
"""
from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# Reuse the WGBAST helper as-is — its `copy_reach_csvs` is parameterized by
# `short_name` + `stem` and works for any fixture that follows the
# Mouth/Lower/Middle/Upper/BalticCoast contract.
from _wire_wgbast_physical_configs import copy_reach_csvs  # noqa: E402

if __name__ == "__main__":
    copy_reach_csvs(short_name="example_minija_basin", stem="MinijaBasinExample")
    print("OK: regenerated per-cell CSVs for example_minija_basin")
