"""Unit tests for the create_model_geocode helper module.

Mocks `requests.get` to test the Nominatim wrapper without network.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure app/modules is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from modules.create_model_geocode import lookup_place_bbox

NOMINATIM_KLAIPEDA = [{
    "place_id": 12345,
    "lat": "55.7128",
    "lon": "21.1351",
    "boundingbox": ["55.65", "55.78", "21.05", "21.25"],  # [lat_s, lat_n, lon_w, lon_e]
    "display_name": "Klaipėda, Lithuania",
    "address": {"country_code": "lt", "country": "Lithuania"},
}]


def _mock_response(json_data, content_length=2000):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.headers = {"Content-Length": str(content_length)}
    resp.raise_for_status = MagicMock()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_lookup_place_bbox_klaipeda_success():
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.return_value = _mock_response(NOMINATIM_KLAIPEDA)
        result = lookup_place_bbox("Klaipėda")
    assert result is not None
    country, bbox = result
    assert country == "lithuania"
    assert bbox[0] == pytest.approx(21.05)  # lon_w (NOT lat)
    assert bbox[1] == pytest.approx(55.65)  # lat_s
    assert bbox[2] == pytest.approx(21.25)  # lon_e
    assert bbox[3] == pytest.approx(55.78)  # lat_n


def test_lookup_place_bbox_empty_results():
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.return_value = _mock_response([])
        result = lookup_place_bbox("Klaipėda")
    assert result is None


def test_lookup_place_bbox_unknown_country_code():
    payload = [dict(NOMINATIM_KLAIPEDA[0])]
    payload[0]["address"] = {"country_code": "zz"}
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.return_value = _mock_response(payload)
        result = lookup_place_bbox("Klaipėda")
    assert result is not None
    country, bbox = result
    assert country is None  # zz not in _ISO_TO_GEOFABRIK
    assert bbox[0] == pytest.approx(21.05)


def test_lookup_place_bbox_network_error(caplog):
    import requests as req
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.side_effect = req.ConnectionError("network down")
        with caplog.at_level(logging.WARNING):
            result = lookup_place_bbox("Klaipėda")
    assert result is None
    assert any("Nominatim lookup failed" in rec.message for rec in caplog.records)


def test_lookup_place_bbox_empty_input():
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        assert lookup_place_bbox("") is None
        assert lookup_place_bbox("   ") is None
        mock_get.assert_not_called()


def test_lookup_place_bbox_special_chars():
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.return_value = _mock_response(NOMINATIM_KLAIPEDA)
        lookup_place_bbox("Mörrumsån")
    assert mock_get.call_args.kwargs["params"]["q"] == "Mörrumsån"


def test_lookup_place_bbox_addressdetails_param():
    with patch("modules.create_model_geocode.requests.get") as mock_get:
        mock_get.return_value = _mock_response(NOMINATIM_KLAIPEDA)
        lookup_place_bbox("Klaipėda")
    assert mock_get.call_args.kwargs["params"]["addressdetails"] == 1
