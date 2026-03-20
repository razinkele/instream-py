"""Tests for configuration system."""
from pathlib import Path
import numpy as np
import pytest

CONFIGS_DIR = Path(__file__).parent.parent / "configs"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestLoadConfig:
    def test_load_example_a_yaml(self):
        from instream.io.config import load_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        assert config.simulation.start_date == "2011-04-01"
        assert config.simulation.end_date == "2013-09-30"

    def test_load_example_a_has_species(self):
        from instream.io.config import load_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        assert "Chinook-Spring" in config.species
        sp = config.species["Chinook-Spring"]
        assert sp.cmax_A == pytest.approx(0.628)
        assert sp.cmax_B == pytest.approx(0.7)
        assert sp.is_anadromous is True

    def test_load_example_a_has_reach(self):
        from instream.io.config import load_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        assert "ExampleA" in config.reaches
        r = config.reaches["ExampleA"]
        assert r.drift_conc == pytest.approx(3.2e-10)

    def test_load_example_a_has_interpolation_table(self):
        from instream.io.config import load_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        sp = config.species["Chinook-Spring"]
        assert len(sp.cmax_temp_table) == 7  # 7 temperature-CMax points

    def test_load_config_missing_file_raises(self):
        from instream.io.config import load_config
        with pytest.raises(FileNotFoundError):
            load_config(Path("/nonexistent/config.yaml"))

    def test_load_config_missing_required_field_raises(self, tmp_path):
        from instream.io.config import load_config
        p = tmp_path / "bad.yaml"
        p.write_text("simulation:\n  end_date: '2013-09-30'\n")
        with pytest.raises(Exception):  # pydantic ValidationError
            load_config(p)


class TestParamsFromConfig:
    def test_creates_species_params(self):
        from instream.io.config import load_config, params_from_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        species_params, reach_params = params_from_config(config)
        assert "Chinook-Spring" in species_params
        sp = species_params["Chinook-Spring"]
        assert sp.cmax_A == pytest.approx(0.628)

    def test_creates_reach_params(self):
        from instream.io.config import load_config, params_from_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        species_params, reach_params = params_from_config(config)
        assert "ExampleA" in reach_params

    def test_species_params_has_interp_tables_as_numpy(self):
        from instream.io.config import load_config, params_from_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        species_params, _ = params_from_config(config)
        sp = species_params["Chinook-Spring"]
        assert isinstance(sp.cmax_temp_table_x, np.ndarray)
        assert isinstance(sp.cmax_temp_table_y, np.ndarray)
        assert sp.cmax_temp_table_x.dtype == np.float64


class TestNlsConverter:
    def test_nls_to_yaml_converts_example_a(self):
        from instream.io.config import nls_to_yaml
        nls_path = FIXTURES_DIR / "example_a" / "parameters-ExampleA.nls"
        yaml_str = nls_to_yaml(nls_path)
        assert "Chinook-Spring" in yaml_str
        assert "start_date" in yaml_str

    def test_nls_yaml_roundtrip(self, tmp_path):
        from instream.io.config import nls_to_yaml, load_config
        nls_path = FIXTURES_DIR / "example_a" / "parameters-ExampleA.nls"
        yaml_str = nls_to_yaml(nls_path)
        p = tmp_path / "roundtrip.yaml"
        p.write_text(yaml_str)
        config = load_config(p)
        assert config.simulation.start_date == "2011-04-01"
        assert "Chinook-Spring" in config.species
