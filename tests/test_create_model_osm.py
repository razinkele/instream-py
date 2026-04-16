"""Unit tests for app.modules.create_model_osm (no PBF file required)."""


def test_geofabrik_url():
    from app.modules.create_model_osm import geofabrik_url

    assert geofabrik_url("lithuania") == "https://download.geofabrik.de/europe/lithuania-latest.osm.pbf"


def test_pbf_path():
    from app.modules.create_model_osm import pbf_path

    p = pbf_path("lithuania")
    assert p.name == "lithuania-latest.osm.pbf"
    assert "osm" in str(p)


def test_waterway_strahler():
    from app.modules.create_model_osm import WATERWAY_STRAHLER

    assert WATERWAY_STRAHLER["river"] == 6
    assert WATERWAY_STRAHLER["stream"] == 2
    assert WATERWAY_STRAHLER["ditch"] == 1
