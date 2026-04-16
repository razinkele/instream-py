"""Tests for create_model_export."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import pytest


def test_export_yaml_respects_junction_ids():
    from modules.create_model_export import export_yaml
    import yaml

    reaches = {
        "reach_A": {
            "segments": [], "properties": [], "color": [255, 0, 0, 255],
            "type": "river", "upstream_junction": 10, "downstream_junction": 20,
        },
        "reach_B": {
            "segments": [], "properties": [], "color": [0, 255, 0, 255],
            "type": "river", "upstream_junction": 20, "downstream_junction": 30,
        },
    }
    yaml_str = export_yaml(reaches=reaches)
    config = yaml.safe_load(yaml_str)
    assert config["reaches"]["reach_A"]["upstream_junction"] == 10
    assert config["reaches"]["reach_A"]["downstream_junction"] == 20
    assert config["reaches"]["reach_B"]["upstream_junction"] == 20
    assert config["reaches"]["reach_B"]["downstream_junction"] == 30


def test_export_yaml_fallback_sequential_junctions():
    from modules.create_model_export import export_yaml
    import yaml

    reaches = {
        "reach_X": {
            "segments": [], "properties": [], "color": [255, 0, 0, 255],
            "type": "river",
        },
    }
    yaml_str = export_yaml(reaches=reaches)
    config = yaml.safe_load(yaml_str)
    assert config["reaches"]["reach_X"]["upstream_junction"] == 1
    assert config["reaches"]["reach_X"]["downstream_junction"] == 2
