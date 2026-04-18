"""Tests for app.modules.create_model_osm."""
import pytest
from pathlib import Path

PBF = Path("app/data/osm/lithuania-latest.osm.pbf")


def test_geofabrik_url():
    from app.modules.create_model_osm import geofabrik_url

    assert geofabrik_url("lithuania") == "https://download.geofabrik.de/europe/lithuania-latest.osm.pbf"
    # Kaliningrad lives under /russia/ (not /europe/russia/ any more) — the
    # mapping is an absolute URL override; see create_model_osm.py.
    assert geofabrik_url("kaliningrad") == "https://download.geofabrik.de/russia/kaliningrad-latest.osm.pbf"


@pytest.mark.skipif(not PBF.exists(), reason="Lithuania PBF not downloaded")
def test_query_waterways_accepts_multi_region():
    """query_waterways should accept an iterable of regions and return features
    from all of them combined."""
    from app.modules.create_model_osm import query_waterways

    # Narrow bbox near the Lithuania/Kaliningrad border to keep the probe fast
    # while still guaranteeing features on both sides.
    bbox = (20.80, 54.90, 22.20, 55.95)

    lt_only = query_waterways("lithuania", bbox)
    both = query_waterways(("lithuania", "kaliningrad"), bbox)

    assert len(both) > len(lt_only), (
        f"Expected merged fetch to have more features than LT alone: "
        f"{len(both)} vs {len(lt_only)}"
    )


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
