"""Migratory fish data client — WGBAST / WGEEL / WGNAS / ecosystem overviews.

Project-specific companion to the generic DATRAS/SAG/SID clients. Focuses on
**diadromous migratory fish** (Atlantic salmon, sea trout, European eel,
sturgeons, twaite shad, smelt, lamprey, etc.):

  - ICES Library (Figshare-hosted): working group reports, ecosystem
    overviews, advice documents.
  - Curated Aphia-ID catalogue for key migratory species.
  - Helpers to filter SAG/SID results to migratory-fish stocks.

Data sources
------------

- ICES Library: `api.figshare.com/v2/articles/search` (public, no auth).
- ICES SAG/SID: existing `sag.py` / `sid.py` wrappers.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional


FIGSHARE_SEARCH = "https://api.figshare.com/v2/articles/search"
FIGSHARE_ARTICLE = "https://api.figshare.com/v2/articles/{id}"


# Curated catalogue of diadromous migratory fish relevant to ICES advisory work.
# All Aphia IDs verified 2026-04-20 against
# https://www.marinespecies.org/rest/AphiaRecordsByName/<name> (status="accepted").
# Do not mutate without re-querying WoRMS.
# Habitat tags:
#   anad = anadromous (sea → river to spawn)
#   cata = catadromous (river → sea to spawn)
#   amph = amphidromous / facultative
MIGRATORY_FISH: List[Dict[str, Any]] = [
    {"common": "Atlantic salmon",     "scientific": "Salmo salar",            "aphia": 127186, "habitat": "anad"},
    {"common": "Sea trout",           "scientific": "Salmo trutta",           "aphia": 127187, "habitat": "anad"},
    {"common": "European eel",        "scientific": "Anguilla anguilla",      "aphia": 126281, "habitat": "cata"},
    {"common": "European smelt",      "scientific": "Osmerus eperlanus",      "aphia": 126736, "habitat": "anad"},
    {"common": "Twaite shad",         "scientific": "Alosa fallax",           "aphia": 126415, "habitat": "anad"},
    {"common": "Allis shad",          "scientific": "Alosa alosa",            "aphia": 126413, "habitat": "anad"},
    {"common": "Houting",             "scientific": "Coregonus oxyrinchus",   "aphia": 154238, "habitat": "anad"},
    {"common": "River lamprey",       "scientific": "Lampetra fluviatilis",   "aphia": 101172, "habitat": "anad"},
    {"common": "Sea lamprey",         "scientific": "Petromyzon marinus",     "aphia": 101174, "habitat": "anad"},
    {"common": "Atlantic sturgeon",   "scientific": "Acipenser oxyrinchus",   "aphia": 151802, "habitat": "anad"},
    {"common": "European sturgeon",   "scientific": "Acipenser sturio",       "aphia": 126279, "habitat": "anad"},
    {"common": "Arctic char",         "scientific": "Salvelinus alpinus",     "aphia": 127188, "habitat": "anad"},
    {"common": "Vendace",             "scientific": "Coregonus albula",       "aphia": 127178, "habitat": "amph"},
]


# ===========================================================================
# European smelt (Osmerus eperlanus) — first-class dedicated reference
# ===========================================================================
SMELT_REFERENCE: Dict[str, Any] = {
    "common_name": "European smelt",
    "scientific_name": "Osmerus eperlanus",
    "aphia_id": 126736,
    "family": "Osmeridae",
    "habitat": "anadromous (with landlocked lake populations)",
    "ices_wgs": ["WGDIAD", "WGBAST"],
    "ices_ecoregions": ["Baltic Sea", "Greater North Sea", "Celtic Seas"],
    "distribution": (
        "Estuaries and lower rivers of the NE Atlantic and Baltic Sea: "
        "Baltic (Curonian Lagoon, Gulf of Bothnia, Gulf of Finland), "
        "Elbe, Thames, Humber, Rhine. Landlocked lake populations across "
        "Scandinavia, Russia, and Baltic states."
    ),
    "life_history": {
        "spawning_period":  "March-April",
        "spawning_habitat": "Freshwater / lower tidal reach, adhesive eggs on substrate",
        "egg_duration":     "2-4 weeks (temperature-dependent)",
        "juvenile_phase":   "Fry descend to estuary within 1-2 months post-hatch",
        "maturation_age":   "2-4 years",
        "max_age":          "10 years",
        "max_length_cm":    30,
        "spawning_length_cm": "15-25",
    },
    "conservation_status": (
        "Locally threatened (UK Red List 'Vulnerable' in the Thames/Humber), "
        "recovering in the Elbe after dredging reduction. Baltic populations "
        "considered stable but data-poor. IUCN Least Concern globally."
    ),
    "ices_search_terms": ["smelt", "Osmerus eperlanus", "estuarine smelt population"],
    "sample_references": [
        {"doi": "10.17895/ices.pub.27150609.v1",
         "title": "ICES ASC Theme Session: Estuarine gradients by immature anadromous fishes"},
    ],
}


# ===========================================================================
# Twaite shad (Alosa fallax) — first-class dedicated reference
# ===========================================================================
SHAD_REFERENCE: Dict[str, Any] = {
    "common_name": "Twaite shad",
    "scientific_name": "Alosa fallax",
    "aphia_id": 126415,
    "family": "Clupeidae",
    "habitat": "anadromous",
    "ices_wgs": ["WGDIAD"],
    "ices_ecoregions": ["Greater North Sea", "Celtic Seas", "Bay of Biscay and the Iberian Coast"],
    "distribution": (
        "NE Atlantic coastal waters from Morocco to southern Norway + Mediterranean. "
        "ICES-region strongholds: Severn (UK), Wye (UK), Loire + Garonne-Dordogne "
        "(France), Elbe (Germany; re-established). Rhine population extinct 1950s."
    ),
    "life_history": {
        "spawning_period":  "May-June",
        "spawning_habitat": "Lower freshwater / tidal limit, demersal eggs on gravel",
        "egg_duration":     "3-8 days",
        "juvenile_phase":   "0+ fry descend to sea 4-6 weeks post-hatch; feed in estuaries then marine",
        "maturation_age":   "3-6 years (females slightly later)",
        "max_age":          "15 years",
        "max_length_cm":    55,
        "spawning_length_cm": "35-50",
    },
    "conservation_status": (
        "EU Habitats Directive Annex II + V. Protected across UK, Ireland, Germany, "
        "France. Data-poor status in most basins; recent German status report "
        "(Hermes 2024, ICES DOI 10.17895/ices.pub.25349818) documents recovery "
        "in the Elbe and persistent decline in smaller basins."
    ),
    "ices_search_terms": ["twaite shad", "Alosa fallax", "shad diadromous"],
    "sample_references": [
        {"doi": "10.17895/ices.pub.25349818.v1",
         "title": "Status of the anadromous twaite shad Alosa fallax in Germany (ICES 2024)"},
        {"doi": "10.17895/ices.pub.27879867.v1",
         "title": "ICES ASC Theme Session E: Applied evidence for biodiversity conservation"},
        {"doi": "10.17895/ices.pub.27169758.v1",
         "title": "WGDIAD 2024 report"},
    ],
}


# ===========================================================================
# Allis shad (Alosa alosa) — sister species, included for completeness
# ===========================================================================
ALLIS_SHAD_REFERENCE: Dict[str, Any] = {
    "common_name": "Allis shad",
    "scientific_name": "Alosa alosa",
    "aphia_id": 126413,
    "family": "Clupeidae",
    "habitat": "anadromous",
    "ices_wgs": ["WGDIAD"],
    "distribution": (
        "NE Atlantic: Morocco to southern Norway. Largest stronghold "
        "historically the Garonne-Dordogne (France); now critically depleted. "
        "Habitats Directive Annex II + V species."
    ),
    "life_history": {
        "spawning_period":  "May-July",
        "spawning_habitat": "Freshwater, demersal eggs",
        "maturation_age":   "4-7 years",
        "max_age":          "8 years",
        "max_length_cm":    70,
        "spawning_length_cm": "40-60",
    },
    "conservation_status": "Critically depleted in most river basins; urgent management interest.",
}


# Known ICES working-group acronyms covering migratory fish.
MIGRATORY_WGS: Dict[str, Dict[str, str]] = {
    "WGBAST":    {"title": "Baltic Salmon and Trout Assessment Working Group",    "species": "Atlantic salmon, sea trout"},
    "WGEEL":     {"title": "Joint EIFAAC/ICES/GFCM Working Group on Eels",         "species": "European eel"},
    "WGNAS":     {"title": "Working Group on North Atlantic Salmon",               "species": "Atlantic salmon (North Atlantic)"},
    "WGDIAD":    {"title": "Working Group on Diadromous Species",                  "species": "All diadromous (shad, smelt, lamprey, sturgeon)"},
    "WGRECORDS": {"title": "Working Group on Recreational Fisheries Surveys",      "species": "Recreational catches (includes salmon)"},
    "WKBALT":    {"title": "Workshop on Baltic Salmon",                            "species": "Baltic salmon"},
    "WKTRUTTA":  {"title": "Workshop on Sea Trout",                                "species": "Sea trout"},
    "WKEELMIGR": {"title": "Workshop on European Eel Migration",                   "species": "European eel"},
    "WKESDLS":   {"title": "Workshop on Estuarine and Diadromous Species",         "species": "Diadromous fish estuarine phase"},
    "WGCRAB":    {"title": "(Non-migratory) — listed for completeness",            "species": "Not migratory"},
}


# ICES ecosystem overviews (curated list; URLs resolve via Figshare-backed library).
ECOREGIONS: List[str] = [
    "Baltic Sea",
    "Greater North Sea",
    "Celtic Seas",
    "Bay of Biscay and the Iberian Coast",
    "Oceanic Northeast Atlantic",
    "Azores",
    "Barents Sea",
    "Norwegian Sea",
    "Icelandic Waters",
    "Greenland Sea",
    "Faroes",
]


def _http_post_json(url: str, payload: Dict[str, Any], timeout: int = 20) -> Any:
    """POST JSON and return parsed response."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_get_json(url: str, timeout: int = 20) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# ICES Library search (Figshare-backed)
# ---------------------------------------------------------------------------


def search_ices_library(
    query: str,
    page_size: int = 20,
    order: str = "published_date",
    order_direction: str = "desc",
) -> List[Dict[str, Any]]:
    """Search ICES Library via Figshare API.

    Parameters
    ----------
    query : str
        Search string. Supports quotes for phrases (e.g. "sea trout").
    page_size : int
        Max results. Figshare caps at 1000; default 20 for snappy responses.
    order : str
        "published_date" | "relevance" | "cited" | "views".
    order_direction : str
        "desc" | "asc".

    Returns
    -------
    list of dicts with keys:
        id, doi, title, published_date, group_id, url_public_html
    """
    payload = {
        "search_for": query,
        "page_size": page_size,
        "order": order,
        "order_direction": order_direction,
    }
    try:
        results = _http_post_json(FIGSHARE_SEARCH, payload)
    except urllib.error.URLError as e:
        return [{"error": str(e)}]
    if not isinstance(results, list):
        return [{"error": "unexpected response shape", "raw": results}]
    filtered: List[Dict[str, Any]] = []
    for r in results:
        filtered.append({
            "id": r.get("id"),
            "doi": r.get("doi"),
            "title": r.get("title"),
            "published_date": r.get("published_date") or r.get("timeline", {}).get("firstOnline"),
            "url_public_html": r.get("url_public_html"),
            "group_id": r.get("group_id"),
        })
    return filtered


def get_ices_article(article_id: int) -> Dict[str, Any]:
    """Retrieve full metadata for one ICES Library article by Figshare ID."""
    try:
        raw = _http_get_json(FIGSHARE_ARTICLE.format(id=article_id))
    except urllib.error.URLError as e:
        return {"error": str(e)}
    keep = [
        "id", "doi", "title", "description", "published_date",
        "authors", "categories", "tags", "references", "files",
        "url_public_html", "url_public_api", "citation",
    ]
    out = {k: raw.get(k) for k in keep}
    # Compact authors/categories
    if isinstance(out.get("authors"), list):
        out["authors"] = [a.get("full_name") for a in out["authors"]]
    if isinstance(out.get("categories"), list):
        out["categories"] = [c.get("title") for c in out["categories"]]
    if isinstance(out.get("files"), list):
        out["files"] = [
            {
                "name": f.get("name"),
                "download_url": f.get("download_url"),
                "size_mb": round((f.get("size") or 0) / 1_048_576, 2),
            }
            for f in out["files"]
        ]
    return out


# ---------------------------------------------------------------------------
# Working group report shortcuts
# ---------------------------------------------------------------------------


def latest_wg_report(wg_acronym: str) -> Dict[str, Any]:
    """Fetch the latest ICES Library entry matching a working-group acronym.

    Example:
        latest_wg_report("WGBAST")
        → most recent WGBAST report with DOI and download URL.
    """
    wg = wg_acronym.upper().strip()
    if wg not in MIGRATORY_WGS:
        return {
            "error": f"unknown WG acronym {wg!r}",
            "available": sorted(MIGRATORY_WGS.keys()),
        }
    results = search_ices_library(
        query=wg, page_size=10, order="published_date", order_direction="desc"
    )
    # Filter to articles whose title contains the acronym
    matches = [r for r in results if isinstance(r, dict) and wg in (r.get("title") or "")]
    if not matches:
        return {"wg": wg, "info": MIGRATORY_WGS[wg], "results": results[:5]}
    return {"wg": wg, "info": MIGRATORY_WGS[wg], "latest": matches[0], "other": matches[1:5]}


def list_migratory_wgs() -> Dict[str, Dict[str, str]]:
    """Return the curated dictionary of ICES WGs covering migratory fish."""
    return MIGRATORY_WGS


# ---------------------------------------------------------------------------
# Ecosystem overviews
# ---------------------------------------------------------------------------


def ecosystem_overview(ecoregion: str, year: Optional[int] = None) -> Dict[str, Any]:
    """Find the ICES ecosystem overview document for an ecoregion.

    Parameters
    ----------
    ecoregion : str
        Full name or keyword (e.g. "Baltic Sea", "Greater North Sea").
    year : int, optional
        Filter to a specific publication year.
    """
    query = f"Ecosystem Overview {ecoregion}"
    if year is not None:
        query = f"{query} {year}"
    results = search_ices_library(query=query, page_size=10)
    eco_lower = ecoregion.lower().strip()
    # Accept either the full ecoregion name or all of its words individually
    # (handles "Greater North Sea" whose Figshare title may read "North Sea
    # Ecosystem Overview" without the "Greater" modifier).
    eco_words = [w for w in eco_lower.split() if len(w) > 3]
    matches = [
        r for r in results
        if isinstance(r, dict)
        and "ecosystem overview" in (r.get("title") or "").lower()
        and (
            eco_lower in (r.get("title") or "").lower()
            or all(w in (r.get("title") or "").lower() for w in eco_words)
        )
    ]
    if not matches:
        return {"ecoregion": ecoregion, "query": query, "results": results[:5]}
    return {"ecoregion": ecoregion, "matches": matches[:5]}


def list_ecoregions() -> List[str]:
    """Return the curated list of ICES ecoregion names."""
    return list(ECOREGIONS)


# ---------------------------------------------------------------------------
# Migratory-fish catalogue helpers
# ---------------------------------------------------------------------------


def migratory_species_catalog(habitat: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return the curated migratory-fish catalogue.

    Parameters
    ----------
    habitat : str, optional
        Filter by habitat tag: 'anad' (anadromous), 'cata' (catadromous),
        or 'amph' (amphidromous). None returns all.
    """
    if habitat is None:
        return list(MIGRATORY_FISH)
    return [s for s in MIGRATORY_FISH if s["habitat"] == habitat]


def migratory_aphia_ids() -> Dict[str, int]:
    """Return {scientific_name: aphia_id} for all catalogued migratory species."""
    return {s["scientific"]: s["aphia"] for s in MIGRATORY_FISH}


# ---------------------------------------------------------------------------
# First-class smelt + shad helpers (user-requested 2026-04-20)
# ---------------------------------------------------------------------------


def smelt_profile(include_library_search: bool = True) -> Dict[str, Any]:
    """Full dossier for European smelt (*Osmerus eperlanus*).

    Combines the static SMELT_REFERENCE dataset with a live ICES Library
    search (Figshare) for the 5 most recent smelt publications.

    Parameters
    ----------
    include_library_search : bool
        If True, issues a live Figshare request. Disable for offline /
        fast calls.
    """
    profile = dict(SMELT_REFERENCE)
    if include_library_search:
        try:
            profile["recent_publications"] = search_ices_library(
                "smelt Osmerus eperlanus", page_size=5, order="published_date",
            )
        except Exception as e:  # pragma: no cover — network path
            profile["recent_publications_error"] = str(e)
    return profile


def shad_profile(include_library_search: bool = True) -> Dict[str, Any]:
    """Full dossier for Twaite shad (*Alosa fallax*).

    Combines SHAD_REFERENCE with a live ICES Library search for the 5
    most recent twaite-shad publications. Also returns the Allis-shad
    reference alongside (sister species under the same WGDIAD scope).

    Parameters
    ----------
    include_library_search : bool
        If True, issues a live Figshare request.
    """
    profile = {"twaite_shad": dict(SHAD_REFERENCE), "allis_shad": dict(ALLIS_SHAD_REFERENCE)}
    if include_library_search:
        try:
            profile["recent_twaite_shad_publications"] = search_ices_library(
                "twaite shad Alosa fallax", page_size=5, order="published_date",
            )
            profile["recent_allis_shad_publications"] = search_ices_library(
                "allis shad Alosa alosa", page_size=3, order="published_date",
            )
        except Exception as e:  # pragma: no cover
            profile["recent_publications_error"] = str(e)
    return profile
