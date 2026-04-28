"""v0.51.6 smoke: run example_baltic for 400 days and confirm it
doesn't fail on time-series lookups past 2011-12-31.

The user reported a simulation error:
  "Nearest date 2011-12-31 is 2.0 days from 2012-01-02 for reach
   Dane_Lower — date is outside time-series range"

This was caused by the v0.51.x regen scripts writing only 365 days of
TimeSeriesInputs.csv (vs the 28-year baseline used by the rest of
example_baltic). v0.51.6 extends to 2038-12-31. This smoke test
verifies the fix.
"""
from __future__ import annotations

import datetime as _dt
import logging
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
logging.getLogger("salmopy").setLevel(logging.ERROR)


def main() -> int:
    from salmopy.model import SalmopyModel

    start = _dt.date(2011, 4, 1)
    end = (start + _dt.timedelta(days=400))
    print(f"Running example_baltic for 400 days ({start} → {end})...")
    model = SalmopyModel(
        config_path=str(ROOT / "configs/example_baltic.yaml"),
        data_dir=str(ROOT / "tests/fixtures/example_baltic"),
        end_date_override=end.isoformat(),
    )
    model.rng = np.random.default_rng(42)

    last_progress = 0
    while not model.time_manager.is_done():
        model.step()
        cur = model.time_manager.current_date
        cur_date = cur.date() if hasattr(cur, "date") else cur
        days_in = (cur_date - start).days
        if days_in - last_progress >= 50:
            print(f"  day {days_in:>4}  ({cur_date})  alive={len(model.trout_state.alive_indices())}")
            last_progress = days_in

    print(f"\nFinal date: {model.time_manager.current_date}")
    print(f"Total alive: {len(model.trout_state.alive_indices())}")
    print("PASS — simulation ran past 2011-12-31 without time-series error.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
