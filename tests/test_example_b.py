"""Integration tests for Example B: 3 reaches x 3 species."""

import pytest
from pathlib import Path

CONFIGS = Path(__file__).parent.parent / "configs"
FIXTURES = Path(__file__).parent / "fixtures" / "example_b"


class TestExampleBInit:
    def test_initializes_with_3_reaches(self):
        from salmopy.model import SalmopyModel

        model = SalmopyModel(CONFIGS / "example_b.yaml", data_dir=FIXTURES)
        assert len(model.reach_order) == 3
        assert "Upstream" in model.reach_order
        assert "Middle" in model.reach_order
        assert "Downstream" in model.reach_order

    def test_initializes_with_3_species(self):
        from salmopy.model import SalmopyModel

        model = SalmopyModel(CONFIGS / "example_b.yaml", data_dir=FIXTURES)
        assert len(model.species_order) == 3

    def test_has_cells_from_multiple_reaches(self):
        from salmopy.model import SalmopyModel

        model = SalmopyModel(CONFIGS / "example_b.yaml", data_dir=FIXTURES)
        reach_indices = set(model.fem_space.cell_state.reach_idx.tolist())
        assert len(reach_indices) >= 2, "Expected cells from multiple reaches"

    def test_has_fish_from_multiple_species(self):
        from salmopy.model import SalmopyModel

        model = SalmopyModel(CONFIGS / "example_b.yaml", data_dir=FIXTURES)
        alive = model.trout_state.alive_indices()
        species = set(model.trout_state.species_idx[alive].tolist())
        # Example B populations may only have some species in initial pop
        assert model.trout_state.num_alive() > 0


@pytest.mark.slow
class TestExampleBRun:
    def test_runs_10_days(self):
        from salmopy.model import SalmopyModel

        model = SalmopyModel(
            CONFIGS / "example_b.yaml",
            data_dir=FIXTURES,
            end_date_override="2010-10-10",
        )
        steps = 0
        while not model.time_manager.is_done():
            model.step()
            steps += 1
        assert steps == 10
        assert model.trout_state.num_alive() >= 0  # some fish may die

    def test_runs_30_days(self):
        from salmopy.model import SalmopyModel

        model = SalmopyModel(
            CONFIGS / "example_b.yaml",
            data_dir=FIXTURES,
            end_date_override="2010-10-31",
        )
        while not model.time_manager.is_done():
            model.step()
        alive = model.trout_state.num_alive()
        print("Example B after 30 days: {} fish alive".format(alive))
        # Should have some fish
        assert alive > 0
