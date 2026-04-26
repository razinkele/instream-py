"""Tests for the Marine Regions cache+fetch helpers
(generate_baltic_example.py + _generate_wgbast_physical_domains.py)."""
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import pytest

from _generate_wgbast_physical_domains import (
    RIVERS,
    _marineregions_cache_path,
)

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


# v0.48.0: tests for the IHO-keyed cache path helper.

@pytest.mark.parametrize("short_name,expected_filename", [
    ("example_tornionjoki", "gulf_of_bothnia_marineregions.json"),
    ("example_simojoki",    "gulf_of_bothnia_marineregions.json"),
    ("example_byskealven",  "gulf_of_bothnia_marineregions.json"),
    ("example_morrumsan",   "baltic_sea_marineregions.json"),
])
def test_marineregions_cache_path_returns_iho_keyed_path(
    short_name: str, expected_filename: str
):
    """Each WGBAST river maps to its IHO-keyed cache filename."""
    river = next(r for r in RIVERS if r.short_name == short_name)
    assert _marineregions_cache_path(river).name == expected_filename


def test_iho_cache_paths_collapse_to_unique_slugs():
    """All 4 WGBAST rivers collapse to exactly 2 unique IHO cache paths.

    Catches 'added a 5th river but RIVER_TO_IHO_NAME slug is wrong'
    by enforcing the set-equality property the de-dup relies on.
    """
    paths = {_marineregions_cache_path(r).name for r in RIVERS}
    assert paths == {
        "gulf_of_bothnia_marineregions.json",
        "baltic_sea_marineregions.json",
    }, f"Unique IHO cache filenames drifted: {paths}"
