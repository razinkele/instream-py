"""Tests for the Marine Regions cache+fetch helper inside generate_baltic_example.py."""
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_baltic_example import fetch_curonian_lagoon  # noqa: E402


def test_fetch_curonian_lagoon_uses_cache(monkeypatch, tmp_path):
    """If the cache file exists, fetch_curonian_lagoon must NOT hit the network."""
    monkeypatch.setattr(
        "generate_baltic_example.CURONIAN_CACHE_PATH", tmp_path / "lagoon.geojson"
    )
    import geopandas as gpd
    from shapely.geometry import Polygon

    poly = Polygon([(21.0, 55.2), (21.3, 55.2), (21.3, 55.5), (21.0, 55.5), (21.0, 55.2)])
    gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326").to_file(
        tmp_path / "lagoon.geojson", driver="GeoJSON"
    )
    import requests

    def fail(*_args, **_kwargs):
        raise AssertionError("network hit when cache exists")

    monkeypatch.setattr(requests, "get", fail)

    result = fetch_curonian_lagoon()
    assert result.geom_type in ("Polygon", "MultiPolygon")
    assert result.area > 0


def test_fetch_curonian_lagoon_falls_back_on_http_error(monkeypatch, tmp_path):
    """If the cache is missing AND the API fails, return the hand-traced fallback
    with a WARN log — must not raise."""
    monkeypatch.setattr(
        "generate_baltic_example.CURONIAN_CACHE_PATH", tmp_path / "missing.geojson"
    )
    import requests

    class FakeResponse:
        status_code = 503

        def raise_for_status(self):
            raise requests.HTTPError("Service Unavailable")

    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())
    result = fetch_curonian_lagoon()
    assert result.geom_type == "Polygon"
    assert result.area > 0
