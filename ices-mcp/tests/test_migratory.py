"""Unit + integration tests for ices_clients.migratory.

Three test classes:

  TestStaticData       — catalogue / reference data well-formed, no network
  TestMockedApi        — Figshare client paths with urllib mocked
  TestLiveApi          — hits the real Figshare + WoRMS endpoints
                         (marked `online`, skippable offline)

Run:
    pytest ices-mcp/tests/test_migratory.py -v
    pytest ices-mcp/tests/test_migratory.py -v -m "not online"   # offline only
"""
from __future__ import annotations

import json
import socket
from unittest.mock import MagicMock, patch

import pytest

from ices_clients import migratory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_internet() -> bool:
    try:
        socket.create_connection(("api.figshare.com", 443), timeout=3).close()
        return True
    except OSError:
        return False


online = pytest.mark.skipif(not _has_internet(), reason="no network")


# ---------------------------------------------------------------------------
# Static data integrity
# ---------------------------------------------------------------------------


class TestStaticData:
    def test_migratory_fish_has_13_species(self):
        assert len(migratory.MIGRATORY_FISH) == 13

    def test_each_entry_has_required_keys(self):
        required = {"common", "scientific", "aphia", "habitat"}
        for sp in migratory.MIGRATORY_FISH:
            assert required.issubset(sp.keys()), f"missing keys in {sp}"
            assert isinstance(sp["aphia"], int) and sp["aphia"] > 0
            assert sp["habitat"] in {"anad", "cata", "amph"}

    def test_no_duplicate_aphia_ids(self):
        ids = [s["aphia"] for s in migratory.MIGRATORY_FISH]
        assert len(ids) == len(set(ids)), f"duplicate Aphia IDs: {ids}"

    def test_no_duplicate_scientific_names(self):
        names = [s["scientific"] for s in migratory.MIGRATORY_FISH]
        assert len(names) == len(set(names))

    def test_known_species_present(self):
        # Sanity: the key SalmoPy-relevant species must be in the catalogue
        scientific = {s["scientific"] for s in migratory.MIGRATORY_FISH}
        for target in [
            "Salmo salar", "Salmo trutta", "Anguilla anguilla",
            "Osmerus eperlanus",  # smelt (explicit)
            "Alosa fallax",       # twaite shad (explicit)
            "Alosa alosa",        # allis shad (sister species)
        ]:
            assert target in scientific, f"{target!r} missing"

    def test_known_wgs(self):
        for wg in ["WGBAST", "WGEEL", "WGNAS", "WGDIAD"]:
            assert wg in migratory.MIGRATORY_WGS
            entry = migratory.MIGRATORY_WGS[wg]
            assert {"title", "species"} <= entry.keys()

    def test_eleven_ecoregions(self):
        assert len(migratory.ECOREGIONS) == 11
        assert "Baltic Sea" in migratory.ECOREGIONS
        assert "Greater North Sea" in migratory.ECOREGIONS

    def test_smelt_reference_wellformed(self):
        s = migratory.SMELT_REFERENCE
        assert s["aphia_id"] == 126736
        assert s["scientific_name"] == "Osmerus eperlanus"
        assert "WGDIAD" in s["ices_wgs"]
        assert "life_history" in s
        assert "spawning_period" in s["life_history"]

    def test_shad_reference_wellformed(self):
        s = migratory.SHAD_REFERENCE
        assert s["aphia_id"] == 126415
        assert s["scientific_name"] == "Alosa fallax"
        assert "WGDIAD" in s["ices_wgs"]

    def test_allis_shad_reference_wellformed(self):
        s = migratory.ALLIS_SHAD_REFERENCE
        assert s["aphia_id"] == 126413
        assert s["scientific_name"] == "Alosa alosa"

    def test_smelt_and_shad_in_main_catalog(self):
        """Regression: smelt + shad must be first-class AND in the catalogue."""
        cat = {s["scientific"]: s["aphia"] for s in migratory.MIGRATORY_FISH}
        assert cat["Osmerus eperlanus"] == migratory.SMELT_REFERENCE["aphia_id"]
        assert cat["Alosa fallax"] == migratory.SHAD_REFERENCE["aphia_id"]
        assert cat["Alosa alosa"] == migratory.ALLIS_SHAD_REFERENCE["aphia_id"]


class TestCatalogueFilters:
    def test_catalog_no_filter_returns_all(self):
        out = migratory.migratory_species_catalog(habitat=None)
        assert len(out) == 13

    def test_catalog_anadromous_filter(self):
        anad = migratory.migratory_species_catalog(habitat="anad")
        assert all(s["habitat"] == "anad" for s in anad)
        assert len(anad) == 11  # 13 total - 1 cata (eel) - 1 amph (vendace)

    def test_catalog_catadromous_filter(self):
        cata = migratory.migratory_species_catalog(habitat="cata")
        assert len(cata) == 1
        assert cata[0]["scientific"] == "Anguilla anguilla"

    def test_catalog_amphidromous_filter(self):
        amph = migratory.migratory_species_catalog(habitat="amph")
        assert len(amph) == 1
        assert amph[0]["scientific"] == "Coregonus albula"

    def test_aphia_map_round_trip(self):
        m = migratory.migratory_aphia_ids()
        assert m["Salmo salar"] == 127186
        assert m["Osmerus eperlanus"] == 126736
        assert m["Alosa fallax"] == 126415

    def test_list_migratory_wgs_is_dict(self):
        out = migratory.list_migratory_wgs()
        assert isinstance(out, dict)
        assert all("title" in v for v in out.values())

    def test_list_ecoregions_is_list(self):
        out = migratory.list_ecoregions()
        assert isinstance(out, list)
        assert len(out) == 11


# ---------------------------------------------------------------------------
# Mocked-API tests (no network)
# ---------------------------------------------------------------------------


def _mock_urlopen(payload, status=200):
    """Build a context-manager mock that urllib.urlopen returns."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=resp)


class TestMockedApi:
    def test_search_returns_filtered_fields(self):
        payload = [
            {
                "id": 123, "doi": "10.x/y", "title": "WGBAST report",
                "published_date": "2024-01-01",
                "url_public_html": "https://…",
                "group_id": 99,
                "timeline": {"firstOnline": "2024-01-01"},
                "extra_field": "should be dropped",
            }
        ]
        with patch("urllib.request.urlopen", _mock_urlopen(payload)):
            out = migratory.search_ices_library("WGBAST", page_size=1)
        assert len(out) == 1
        r = out[0]
        assert r["id"] == 123
        assert r["doi"] == "10.x/y"
        assert r["title"] == "WGBAST report"
        assert "extra_field" not in r

    def test_search_network_error_returns_error_dict(self):
        import urllib.error
        def boom(*a, **kw):
            raise urllib.error.URLError("simulated")
        with patch("urllib.request.urlopen", boom):
            out = migratory.search_ices_library("anything")
        assert len(out) == 1 and "error" in out[0]

    def test_search_unexpected_shape_returns_error_dict(self):
        with patch("urllib.request.urlopen", _mock_urlopen({"not": "a list"})):
            out = migratory.search_ices_library("x")
        assert len(out) == 1 and "error" in out[0]

    def test_get_article_compacts_authors_and_files(self):
        payload = {
            "id": 9, "doi": "10.x", "title": "T", "description": "D",
            "published_date": "2024",
            "authors": [{"full_name": "Smith J"}, {"full_name": "Doe A"}],
            "categories": [{"title": "Fisheries"}],
            "files": [
                {"name": "report.pdf", "download_url": "u", "size": 2_097_152}
            ],
        }
        with patch("urllib.request.urlopen", _mock_urlopen(payload)):
            out = migratory.get_ices_article(9)
        assert out["authors"] == ["Smith J", "Doe A"]
        assert out["categories"] == ["Fisheries"]
        assert out["files"][0]["size_mb"] == 2.0

    def test_latest_wg_report_unknown_acronym_returns_error(self):
        out = migratory.latest_wg_report("WGXYZ")
        assert "error" in out
        assert "available" in out
        assert "WGBAST" in out["available"]

    def test_latest_wg_report_filters_title(self):
        # Payload mixes a non-WG paper and two WGBAST results
        payload = [
            {"id": 1, "title": "FRSG 2025 Resolutions", "doi": "a"},
            {"id": 2, "title": "WGBAST 2024 report", "doi": "b"},
            {"id": 3, "title": "WGBAST 2023 data call", "doi": "c"},
        ]
        with patch("urllib.request.urlopen", _mock_urlopen(payload)):
            out = migratory.latest_wg_report("WGBAST")
        assert out["latest"]["id"] == 2  # first one matching the filter
        assert len(out["other"]) == 1    # id=3
        # FRSG entry dropped

    def test_ecosystem_overview_matches_multi_word_region(self):
        """'Greater North Sea' should match both 'Greater North Sea
        Ecosystem Overview' and 'North Sea Ecosystem Overview'."""
        payload = [
            {"id": 1, "title": "Greater North Sea Ecosystem Overview 2023", "doi": "a"},
            {"id": 2, "title": "North Sea Ecosystem Overview 2022",         "doi": "b"},
            {"id": 3, "title": "Celtic Seas Ecosystem Overview 2023",       "doi": "c"},
        ]
        with patch("urllib.request.urlopen", _mock_urlopen(payload)):
            out = migratory.ecosystem_overview("Greater North Sea")
        assert "matches" in out
        titles = [m["title"] for m in out["matches"]]
        assert any("Greater North Sea" in t for t in titles)
        # Celtic Seas shouldn't match
        assert not any("Celtic" in t for t in titles)


# ---------------------------------------------------------------------------
# Live API tests — skipped when no network
# ---------------------------------------------------------------------------


@online
class TestLiveApi:
    def test_figshare_search_returns_hits(self):
        out = migratory.search_ices_library("WGBAST", page_size=5)
        assert isinstance(out, list)
        assert len(out) > 0
        assert "error" not in out[0]
        assert out[0].get("id") is not None

    def test_latest_wgbast_has_recent_doi(self):
        out = migratory.latest_wg_report("WGBAST")
        assert "latest" in out
        latest = out["latest"]
        # WGBAST reports have DOIs like 10.17895/ices.pub.<figshare_id>
        assert latest.get("doi", "").startswith(
            "10.17895/ices.pub."
        ) or latest.get("doi", "") == ""
        assert "WGBAST" in latest["title"]

    def test_smelt_profile_live(self):
        p = migratory.smelt_profile(include_library_search=True)
        assert p["aphia_id"] == 126736
        assert isinstance(p.get("recent_publications"), list)

    def test_shad_profile_live(self):
        p = migratory.shad_profile(include_library_search=True)
        assert p["twaite_shad"]["aphia_id"] == 126415
        assert p["allis_shad"]["aphia_id"] == 126413
        assert isinstance(p.get("recent_twaite_shad_publications"), list)

    def test_smelt_profile_offline_flag(self):
        p = migratory.smelt_profile(include_library_search=False)
        assert "recent_publications" not in p
        assert p["aphia_id"] == 126736

    def test_aphia_ids_match_worms_for_smelt_and_shad(self):
        """Regression-ish: re-verify that the hard-coded Aphia IDs for
        smelt and shad still resolve on WoRMS. If WoRMS renumbers, this
        will fail loudly."""
        import urllib.request
        for scientific, expected in [
            ("Osmerus eperlanus", 126736),
            ("Alosa fallax",      126415),
            ("Alosa alosa",       126413),
        ]:
            url = (
                "https://www.marinespecies.org/rest/AphiaRecordsByName/"
                f"{scientific.replace(' ', '%20')}?like=false&marine_only=false"
            )
            with urllib.request.urlopen(url, timeout=20) as r:
                rows = json.loads(r.read())
            accepted = [row for row in rows if row.get("status") == "accepted"]
            assert accepted, f"WoRMS returned no accepted record for {scientific}"
            assert accepted[0]["AphiaID"] == expected, (
                f"WoRMS Aphia drift for {scientific}: "
                f"code expects {expected}, WoRMS says {accepted[0]['AphiaID']}"
            )
