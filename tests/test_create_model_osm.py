"""Tests for app.modules.create_model_osm."""
import pytest
from pathlib import Path

PBF = Path("app/data/osm/lithuania-latest.osm.pbf")


def test_geofabrik_url():
    from app.modules.create_model_osm import geofabrik_url

    assert geofabrik_url("lithuania") == "https://download.geofabrik.de/europe/lithuania-latest.osm.pbf"
    assert geofabrik_url("kaliningrad") == "https://download.geofabrik.de/europe/russia/kaliningrad-latest.osm.pbf"


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


@pytest.mark.skipif(not PBF.exists(), reason="Lithuania PBF not downloaded")
def test_bbox_query_klaipeda():
    """Query Klaipeda area via clip+extract and verify river polygons."""
    from app.modules.create_model_osm import query_waterways, query_water_bodies

    bbox = (20.9, 55.5, 21.3, 55.85)
    ww = query_waterways("lithuania", bbox)

    assert len(ww) > 50, f"Expected >50 waterways, got {len(ww)}"
    is_poly = ww.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    assert is_poly.sum() > 0, "No river polygons found"
    assert "nameText" in ww.columns
    assert "STRAHLER" in ww.columns
    assert "DFDD" in ww.columns

    wb = query_water_bodies("lithuania", bbox)
    assert len(wb) > 0, "No water bodies found"
    assert "nameText" in wb.columns
