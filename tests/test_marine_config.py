import yaml
from instream.io.config import ModelConfig

MINIMAL_MARINE_YAML = """
simulation:
  start_date: "2024-01-01"
  end_date: "2028-12-31"
  seed: 42
  population_file: "pop.csv"
spatial:
  mesh_file: "mesh.shp"
species:
  atlantic_salmon:
    is_anadromous: true
reaches:
  lower:
    depth_file: "d.csv"
    velocity_file: "v.csv"
    upstream_junction: 1
    downstream_junction: 2
    is_river_mouth: true
marine:
  enabled: true
  time_step: daily
  zones:
    estuary:
      area_km2: 50
      connections: [coastal]
    coastal:
      area_km2: 5000
      connections: [estuary]
  environment:
    driver: static
    static:
      estuary:
        temperature: {1: 2.0, 7: 18.0}
      coastal:
        temperature: {1: 3.0, 7: 15.0}
"""


def test_marine_config_loads():
    raw = yaml.safe_load(MINIMAL_MARINE_YAML)
    cfg = ModelConfig(**raw)
    assert cfg.marine is not None
    assert cfg.marine.enabled is True
    assert "estuary" in cfg.marine.zones
    assert cfg.marine.zones["estuary"].area_km2 == 50


def test_no_marine_section_returns_none():
    raw = yaml.safe_load(MINIMAL_MARINE_YAML)
    del raw["marine"]
    cfg = ModelConfig(**raw)
    assert cfg.marine is None


def test_reach_is_river_mouth():
    raw = yaml.safe_load(MINIMAL_MARINE_YAML)
    cfg = ModelConfig(**raw)
    assert cfg.reaches["lower"].is_river_mouth is True
