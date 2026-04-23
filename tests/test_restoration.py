"""Tests for habitat restoration scenarios."""

import numpy as np
from pathlib import Path


class TestRestorationEvents:
    def test_restoration_changes_cell_properties(self):
        """Restoration event should modify cell state on the target date."""
        from salmopy.model import SalmopyModel

        fixtures = Path(__file__).parent / "fixtures" / "example_a"
        config_path = Path(__file__).parent.parent / "configs" / "example_a.yaml"

        model = SalmopyModel(str(config_path), data_dir=str(fixtures))
        cs = model.fem_space.cell_state

        # Record original values
        original_shelter = cs.frac_vel_shelter[0].copy()

        # Manually inject a restoration event for today's date
        date_str = model.time_manager.current_date.strftime("%Y-%m-%d")
        rname = model.reach_order[0]
        reach_cfg = model.config.reaches[rname]
        reach_cfg.restoration_events = [
            {
                "date": date_str,
                "cells": [0, 1, 2],
                "changes": {"frac_vel_shelter": 0.99},
            }
        ]

        model._apply_restoration_events()

        assert cs.frac_vel_shelter[0] == 0.99
        assert cs.frac_vel_shelter[1] == 0.99
        assert cs.frac_vel_shelter[2] == 0.99

    def test_restoration_no_effect_wrong_date(self):
        """Restoration event on a different date should have no effect."""
        from salmopy.model import SalmopyModel

        fixtures = Path(__file__).parent / "fixtures" / "example_a"
        config_path = Path(__file__).parent.parent / "configs" / "example_a.yaml"

        model = SalmopyModel(str(config_path), data_dir=str(fixtures))
        cs = model.fem_space.cell_state

        original = cs.frac_vel_shelter[0].copy()

        rname = model.reach_order[0]
        reach_cfg = model.config.reaches[rname]
        reach_cfg.restoration_events = [
            {"date": "2099-01-01", "cells": [0], "changes": {"frac_vel_shelter": 0.99}}
        ]

        model._apply_restoration_events()

        assert cs.frac_vel_shelter[0] == original

    def test_restoration_all_cells_in_reach(self):
        """cells='all' should modify all cells in the reach."""
        from salmopy.model import SalmopyModel

        fixtures = Path(__file__).parent / "fixtures" / "example_a"
        config_path = Path(__file__).parent.parent / "configs" / "example_a.yaml"

        model = SalmopyModel(str(config_path), data_dir=str(fixtures))
        cs = model.fem_space.cell_state

        date_str = model.time_manager.current_date.strftime("%Y-%m-%d")
        rname = model.reach_order[0]
        reach_cfg = model.config.reaches[rname]
        n_cells = np.sum(cs.reach_idx == 0)
        reach_cfg.restoration_events = [
            {"date": date_str, "cells": "all", "changes": {"frac_spawn": 0.77}}
        ]

        model._apply_restoration_events()

        reach_cells = np.where(cs.reach_idx == 0)[0]
        assert np.all(cs.frac_spawn[reach_cells] == 0.77)
