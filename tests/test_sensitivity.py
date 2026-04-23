"""Tests for sensitivity analysis framework."""

import numpy as np
import pytest
from pathlib import Path

FIXTURES_A = Path(__file__).parent / "fixtures" / "example_a"
CONFIG_A = Path(__file__).parent.parent / "configs" / "example_a.yaml"


class TestMorrisScreening:
    @pytest.mark.slow
    def test_morris_returns_dataframe(self):
        """Morris screening should return a DataFrame with mu_star, sigma, mu."""
        from salmopy.modules.sensitivity import morris_screening

        param_specs = [
            {"name": "species.Chinook-Spring.cmax_A", "min": 0.3, "max": 0.9},
            {"name": "species.Chinook-Spring.resp_A", "min": 0.01, "max": 0.05},
        ]
        result = morris_screening(
            str(CONFIG_A),
            str(FIXTURES_A),
            param_specs,
            num_trajectories=2,
            num_steps=5,
            seed=42,
        )
        assert len(result) == 2
        assert "mu_star" in result.columns
        assert "sigma" in result.columns
        assert "parameter" in result.columns
        assert result.iloc[0]["parameter"] == "species.Chinook-Spring.cmax_A"

    def test_generate_trajectories_shape(self):
        """Each trajectory should have k+1 points of dimension k."""
        from salmopy.modules.sensitivity import _generate_trajectories

        rng = np.random.default_rng(42)
        trajs = _generate_trajectories(k=3, r=5, p=4, rng=rng)
        assert len(trajs) == 5
        for t in trajs:
            assert t.shape == (4, 3)  # k+1 points, k dimensions

    def test_set_param_species(self):
        """_set_param should modify species config fields."""
        from salmopy.io.config import load_config
        from salmopy.modules.sensitivity import _set_param

        config = load_config(str(CONFIG_A))
        _set_param(config, "species.Chinook-Spring.cmax_A", 0.999)
        assert config.species["Chinook-Spring"].cmax_A == 0.999

    def test_extract_metric_population(self):
        """_extract_metric should return population count."""
        from salmopy.model import SalmopyModel
        from salmopy.modules.sensitivity import _extract_metric

        model = SalmopyModel(str(CONFIG_A), data_dir=str(FIXTURES_A))
        pop = _extract_metric(model, "mean_population")
        assert pop > 0
