"""Tests for configuration system."""
from pathlib import Path
import numpy as np
import pytest

CONFIGS_DIR = Path(__file__).parent.parent / "configs"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestLoadConfig:
    def test_load_example_a_yaml(self):
        from salmopy.io.config import load_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        assert config.simulation.start_date == "2011-04-01"
        assert config.simulation.end_date == "2013-09-30"

    def test_load_example_a_has_species(self):
        from salmopy.io.config import load_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        assert "Chinook-Spring" in config.species
        sp = config.species["Chinook-Spring"]
        assert sp.cmax_A == pytest.approx(0.628)
        assert sp.cmax_B == pytest.approx(0.7)
        assert sp.is_anadromous is True

    def test_load_example_a_has_reach(self):
        from salmopy.io.config import load_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        assert "ExampleA" in config.reaches
        r = config.reaches["ExampleA"]
        assert r.drift_conc == pytest.approx(3.2e-10)

    def test_load_example_a_has_interpolation_table(self):
        from salmopy.io.config import load_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        sp = config.species["Chinook-Spring"]
        assert len(sp.cmax_temp_table) == 7  # 7 temperature-CMax points

    def test_load_config_missing_file_raises(self):
        from salmopy.io.config import load_config
        with pytest.raises(FileNotFoundError):
            load_config(Path("/nonexistent/config.yaml"))

    def test_load_config_missing_required_field_raises(self, tmp_path):
        from salmopy.io.config import load_config
        p = tmp_path / "bad.yaml"
        p.write_text("simulation:\n  end_date: '2013-09-30'\n")
        with pytest.raises(Exception):  # pydantic ValidationError
            load_config(p)


class TestParamsFromConfig:
    def test_creates_species_params(self):
        from salmopy.io.config import load_config, params_from_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        species_params, reach_params = params_from_config(config)
        assert "Chinook-Spring" in species_params
        sp = species_params["Chinook-Spring"]
        assert sp.cmax_A == pytest.approx(0.628)

    def test_creates_reach_params(self):
        from salmopy.io.config import load_config, params_from_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        species_params, reach_params = params_from_config(config)
        assert "ExampleA" in reach_params

    def test_species_params_has_interp_tables_as_numpy(self):
        from salmopy.io.config import load_config, params_from_config
        config = load_config(CONFIGS_DIR / "example_a.yaml")
        species_params, _ = params_from_config(config)
        sp = species_params["Chinook-Spring"]
        assert isinstance(sp.cmax_temp_table_x, np.ndarray)
        assert isinstance(sp.cmax_temp_table_y, np.ndarray)
        assert sp.cmax_temp_table_x.dtype == np.float64


class TestNlsConverter:
    def test_nls_to_yaml_converts_example_a(self):
        from salmopy.io.config import nls_to_yaml
        nls_path = FIXTURES_DIR / "example_a" / "parameters-ExampleA.nls"
        yaml_str = nls_to_yaml(nls_path)
        assert "Chinook-Spring" in yaml_str
        assert "start_date" in yaml_str

    def test_nls_yaml_roundtrip(self, tmp_path):
        from salmopy.io.config import nls_to_yaml, load_config
        nls_path = FIXTURES_DIR / "example_a" / "parameters-ExampleA.nls"
        yaml_str = nls_to_yaml(nls_path)
        p = tmp_path / "roundtrip.yaml"
        p.write_text(yaml_str)
        config = load_config(p)
        assert config.simulation.start_date == "2011-04-01"
        assert "Chinook-Spring" in config.species


class TestDefenseAreaSemanticReconciliation:
    """v0.19.0 Phase 3: NetLogo InSALMO uses ``spawn_defense_area`` as an
    actual m² area; Python has shipped it as a cm Euclidean distance since
    v0.12.0. Users can now specify the NetLogo-semantic value via the
    explicit ``spawn_defense_area_m2`` field and the Pydantic validator
    converts it to the equivalent circular-disk radius in cm.
    """

    def test_m2_field_converts_to_cm_radius(self):
        import math
        from salmopy.io.config import SpeciesConfig

        # 1 m² defended area → equivalent circular radius
        # r = sqrt(1 m² / π) = sqrt(10_000 cm² / π) ≈ 56.4189 cm
        sp = SpeciesConfig(spawn_defense_area_m2=1.0)
        expected_radius_cm = math.sqrt(10_000.0 / math.pi)
        assert sp.spawn_defense_area == pytest.approx(expected_radius_cm, rel=1e-12)

    def test_cm_field_wins_when_both_set(self):
        from salmopy.io.config import SpeciesConfig

        sp = SpeciesConfig(spawn_defense_area=42.0, spawn_defense_area_m2=1.0)
        assert sp.spawn_defense_area == 42.0

    def test_both_zero_stays_zero(self):
        from salmopy.io.config import SpeciesConfig

        sp = SpeciesConfig()
        assert sp.spawn_defense_area == 0.0
        assert sp.spawn_defense_area_m2 == 0.0


class TestParamsFromConfigDefenseArea:
    """Regression for config.py:544 + params.py:102.

    The Pydantic SpeciesConfig stores spawn_defense_area_m (meters, the Arc E
    canonical unit). The frozen runtime SpeciesParams must expose the same
    field so callers that go through params_from_config do not silently fall
    back to the legacy cm field.
    """

    def test_species_params_has_spawn_defense_area_m_field(self):
        from salmopy.state.params import SpeciesParams
        params = SpeciesParams(name="test")
        assert hasattr(params, "spawn_defense_area_m"), (
            "SpeciesParams must expose spawn_defense_area_m to prevent "
            "Arc E regression"
        )

    def test_params_from_config_propagates_spawn_defense_area_m(self):
        from salmopy.io.config import load_config, params_from_config
        cfg = load_config(CONFIGS_DIR / "example_a.yaml")
        sp_name = next(iter(cfg.species))
        cfg.species[sp_name].spawn_defense_area_m = 3.5
        species_params, _ = params_from_config(cfg)
        assert species_params[sp_name].spawn_defense_area_m == pytest.approx(3.5)
