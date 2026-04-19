"""Arc E redd/egg probe — compare Python year-1 spawning output vs NetLogo.

Context (from _probe_arc_e_growth findings):
  - Python emerges ~1988 juveniles on 2012-01-27; NetLogo ~236-462
    peak. Python's natal cohort is ~8x denser.
  - NetLogo 2.5-year total: 15 redds, 77,031 eggs, 41,189 emerged.
  - Hypothesis: Python produces more eggs per female or better
    egg-to-emergence survival than NetLogo.

This probe runs Python example_a through year-1 spawning window
(450 days, Apr 2011 -> Jun 2012) and emits:
  - Total redds created in year 1
  - Total eggs laid
  - Total eggs lost to thermal mortality / dewatering / scour
  - Total eggs emerged as FRY

Usage:
    micromamba run -n shiny python scripts/_probe_arc_e_redds.py
"""
from __future__ import annotations

from pathlib import Path
import datetime

import numpy as np

from instream.model import InSTREAMModel

PROJECT = Path(__file__).resolve().parent.parent
CONFIGS = PROJECT / "configs"
FIXTURES = PROJECT / "tests" / "fixtures"


def main() -> None:
    start = datetime.date(2011, 4, 1)
    end = (start + datetime.timedelta(days=450)).isoformat()
    model = InSTREAMModel(
        CONFIGS / "example_a.yaml",
        data_dir=FIXTURES / "example_a",
        end_date_override=end,
    )

    max_redds_seen = 0
    max_eggs_seen = 0
    max_fry_seen = 0
    first_redd_day = None
    first_fry_day = None
    day_idx = 0

    while not model.time_manager.is_done():
        model.step()
        if not model.time_manager.is_day_boundary:
            continue
        day_idx += 1
        ts = model.trout_state
        rs = model.redd_state
        try:
            n_redds = int(rs.num_alive())
        except Exception:
            n_redds = 0
        try:
            n_eggs = int(rs.num_eggs.sum()) if hasattr(rs, "num_eggs") else 0
        except Exception:
            n_eggs = 0
        n_fry = int(
            ((ts.life_history == 0) & ts.alive).sum()
        )  # LifeStage.FRY = 0
        if n_redds > 0 and first_redd_day is None:
            first_redd_day = model.time_manager.current_date.date()
            print(
                f"day {day_idx} first redd: {first_redd_day} n_redds={n_redds} n_eggs={n_eggs}"
            )
        if n_fry > 100 and first_fry_day is None:
            first_fry_day = model.time_manager.current_date.date()
            print(
                f"day {day_idx} first FRY cohort: {first_fry_day} n_fry={n_fry}"
            )
        max_redds_seen = max(max_redds_seen, n_redds)
        max_eggs_seen = max(max_eggs_seen, n_eggs)
        max_fry_seen = max(max_fry_seen, n_fry)

    print("\n=== Python example_a year-1 spawn summary ===")
    print(f"Peak concurrent redds: {max_redds_seen}")
    print(f"Peak concurrent eggs: {max_eggs_seen}")
    print(f"Peak concurrent FRY: {max_fry_seen}")
    print(f"First redd day: {first_redd_day}")
    print(f"First FRY cohort day (>100): {first_fry_day}")

    print("\n=== NetLogo reference (from ReddEventsOut 2.5-year run) ===")
    print("Total redds created: 15")
    print("Total eggs laid: 77,031")
    print("Total eggs emerged (cumulative): 41,189")
    print("Eggs died hi-temp: 1,049")
    print("Eggs died low-temp: 844")
    print("Peak CH-S-juve-abund: 462 on 2012-01-29 (single-day snapshot)")


if __name__ == "__main__":
    main()
