"""Regression for model_day_boundary.py:252-255.

A RETURNING_ADULT fish that fails readiness (e.g. temperature outside
spawn range) must remain RETURNING_ADULT — not be bulk-promoted to SPAWNER
at season-open. Per v0.17.0: promotion only on actual redd deposit.
"""
import numpy as np
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def test_returning_adult_not_promoted_without_redd_deposit(monkeypatch):
    from salmopy.model import SalmopyModel
    from salmopy.state.life_stage import LifeStage

    model = SalmopyModel(
        config_path=str(CONFIGS_DIR / "example_a.yaml"),
        data_dir=str(FIXTURES_DIR / "example_a"),
    )

    # Pick an alive fish and mark it RETURNING_ADULT
    alive = np.where(model.trout_state.alive)[0]
    assert len(alive) > 0, "fixture must seed alive fish"
    fish_i = int(alive[0])
    model.trout_state.life_history[fish_i] = int(LifeStage.RETURNING_ADULT)

    # Force temperature outside spawn range so ready_to_spawn will return False
    sp_name = model.species_order[0]
    sp_cfg = model.config.species[sp_name]
    r_idx = int(model.trout_state.reach_idx[fish_i])
    model.reach_state.temperature[r_idx] = sp_cfg.spawn_min_temp - 5.0

    # Force julian_date into the spawn window. Parse directly from the
    # config (NOT from model._spawn_doy_cache — that is lazy-initialized
    # on first call to _do_spawning). Example_a's Chinook-Spring has
    # spawn_start_day: "09-01" -> DOY 244.
    import pandas as pd
    month, day = sp_cfg.spawn_start_day.split("-")
    spawn_start_doy = int(
        pd.Timestamp(f"2000-{month}-{day}").day_of_year
    )
    monkeypatch.setattr(
        type(model.time_manager),
        "julian_date",
        property(lambda self: spawn_start_doy),
    )

    model._do_spawning(step_length=1.0)

    assert int(model.trout_state.life_history[fish_i]) == int(LifeStage.RETURNING_ADULT), (
        "Fish was promoted to SPAWNER without depositing a redd — bulk promotion "
        "at model_day_boundary.py:252-255 is shadowing the v0.17.0 per-fish fix."
    )
