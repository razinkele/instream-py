"""
ICES Fish Data MCP Server
=========================

Model Context Protocol server providing AI assistants with access to:

  1. **DATRAS** — Trawl survey data (hauls, length frequencies, age data, CPUE, indices)
  2. **SAG** — Stock Assessment Graphs (SSB, F, recruitment time-series)
  3. **SID** — Stock Information Database (stock metadata, reference points)
  4. **ICES Vocab** — Species codes (WoRMS Aphia IDs)
  5. **ICES GIS** — Spatial reference layers (statistical areas, rectangles, ecoregions)

Usage:
    micromamba run -n shiny python ices_mcp_server.py

Transport: stdio (default for Copilot CLI / Claude Desktop)
"""

from __future__ import annotations

import json
import logging
import sys
import os

# Add ices_datras to path — it lives in the marine-gis-tools repo
# or can be installed separately.  We check both locations.
_DATRAS_PATHS = [
    os.path.join(os.path.dirname(__file__), "..", "..", ".."),  # inSTREAM root
    os.path.join(os.path.dirname(__file__), "vendor"),
]
for p in _DATRAS_PATHS:
    _abs = os.path.abspath(p)
    if os.path.isdir(os.path.join(_abs, "ices_datras")):
        if _abs not in sys.path:
            sys.path.insert(0, _abs)
        break

from mcp.server.fastmcp import FastMCP

# Local clients
from ices_clients import sag, sid, gis, vocab

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "ICES Fish Data",
    instructions=(
        "Access ICES fisheries data: trawl surveys (DATRAS), stock assessments "
        "(SAG), stock information (SID), species vocabulary, and spatial "
        "reference layers."
    ),
)


# ===========================================================================
# DATRAS Tools
# ===========================================================================

@mcp.tool()
def datras_list_surveys() -> str:
    """List all trawl survey acronyms available in the ICES DATRAS database.

    Returns survey names like NS-IBTS, BITS, ROCKALL, BTS, etc.
    Use these names as the 'survey' parameter in other DATRAS tools.
    """
    try:
        from ices_datras import get_survey_list
        surveys = get_survey_list()
        return json.dumps({"surveys": list(surveys), "count": len(surveys)})
    except ImportError:
        return _datras_not_available()
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def datras_survey_years(survey: str) -> str:
    """Get all available years for a DATRAS trawl survey.

    Args:
        survey: Survey acronym, e.g. 'NS-IBTS', 'BITS', 'ROCKALL'
    """
    try:
        from ices_datras import get_survey_year_list
        years = get_survey_year_list(survey)
        return json.dumps({"survey": survey, "years": list(years), "count": len(years)})
    except ImportError:
        return _datras_not_available()
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def datras_get_haul_data(survey: str, year: int, quarter: int) -> str:
    """Get haul-level (HH) exchange data from a DATRAS trawl survey.

    Returns one row per haul with station position (lat/lon), depth, gear,
    haul duration, and environmental variables.

    Args:
        survey: Survey acronym, e.g. 'NS-IBTS'
        year: Survey year
        quarter: Quarter (1-4)
    """
    try:
        from ices_datras import get_hh_data
        df = get_hh_data(survey, year, quarter)
        return _df_to_json(df, f"HH data for {survey} {year} Q{quarter}")
    except ImportError:
        return _datras_not_available()
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def datras_get_length_data(survey: str, year: int, quarter: int) -> str:
    """Get length-frequency (HL) data from a DATRAS trawl survey.

    Returns species-level length distributions per haul.

    Args:
        survey: Survey acronym
        year: Survey year
        quarter: Quarter (1-4)
    """
    try:
        from ices_datras import get_hl_data
        df = get_hl_data(survey, year, quarter)
        return _df_to_json(df, f"HL data for {survey} {year} Q{quarter}")
    except ImportError:
        return _datras_not_available()
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def datras_get_age_data(survey: str, year: int, quarter: int) -> str:
    """Get catch/age (CA) data from a DATRAS trawl survey.

    Returns individual fish age, length, weight, sex, and maturity data.

    Args:
        survey: Survey acronym
        year: Survey year
        quarter: Quarter (1-4)
    """
    try:
        from ices_datras import get_ca_data
        df = get_ca_data(survey, year, quarter)
        return _df_to_json(df, f"CA data for {survey} {year} Q{quarter}")
    except ImportError:
        return _datras_not_available()
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def datras_get_cpue_length(survey: str, year: int, quarter: int) -> str:
    """Get CPUE (catch per unit effort) per length class per haul per hour.

    Pre-computed product from DATRAS. Standardised abundance by size class.

    Args:
        survey: Survey acronym
        year: Survey year
        quarter: Quarter (1-4)
    """
    try:
        from ices_datras import get_cpue_length
        df = get_cpue_length(survey, year, quarter)
        return _df_to_json(df, f"CPUE-length for {survey} {year} Q{quarter}")
    except ImportError:
        return _datras_not_available()
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def datras_get_cpue_age(survey: str, year: int, quarter: int) -> str:
    """Get CPUE (catch per unit effort) per age group per haul per hour.

    Pre-computed product from DATRAS. Standardised abundance by age class.

    Args:
        survey: Survey acronym
        year: Survey year
        quarter: Quarter (1-4)
    """
    try:
        from ices_datras import get_cpue_age
        df = get_cpue_age(survey, year, quarter)
        return _df_to_json(df, f"CPUE-age for {survey} {year} Q{quarter}")
    except ImportError:
        return _datras_not_available()
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def datras_get_indices(survey: str, year: int, quarter: int, species: int = 0) -> str:
    """Get age-based survey indices of abundance from DATRAS.

    Args:
        survey: Survey acronym
        year: Survey year
        quarter: Quarter (1-4)
        species: WoRMS Aphia ID (0 for all species)
    """
    try:
        from ices_datras import get_indices as _get_indices
        df = _get_indices(survey, year, quarter, species=species if species else "")
        return _df_to_json(df, f"Indices for {survey} {year} Q{quarter}")
    except ImportError:
        return _datras_not_available()
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def datras_get_catch_weight(
    survey: str, years: list[int], quarters: list[int], aphia: list[int]
) -> str:
    """Calculate total catch weight by species and haul from DATRAS survey data.

    Combines HH (haul) and HL (length) data to compute aggregated catch
    weights for specified species across multiple years and quarters.

    Args:
        survey: Survey acronym
        years: List of years (e.g. [2020, 2021, 2022])
        quarters: List of quarters (e.g. [1, 3])
        aphia: List of WoRMS Aphia IDs for species of interest
    """
    try:
        from ices_datras import get_catch_wgt
        df = get_catch_wgt(survey, years, quarters, aphia)
        return _df_to_json(df, f"Catch weight for {survey}")
    except ImportError:
        return _datras_not_available()
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def datras_get_species_list() -> str:
    """Get the list of species recorded in DATRAS with their codes.

    Returns species names and Valid_Aphia (WoRMS) codes used in DATRAS data.
    Uses the DATRAS getSpecies web service endpoint.
    """
    try:
        from ices_datras._client import fetch
        df = fetch("getSpecies")
        return _df_to_json(df, "DATRAS species list")
    except ImportError:
        return _datras_not_available()
    except Exception as e:
        return json.dumps({"error": str(e)})


# ===========================================================================
# SAG Tools (Stock Assessment Graphs)
# ===========================================================================

@mcp.tool()
def sag_list_stocks(year: int = 2024) -> str:
    """List all fish stocks assessed by ICES for a given year.

    Returns stock labels, species names, descriptions, assessment models,
    and links to official ICES advice.

    Args:
        year: Assessment year (default: 2024)
    """
    try:
        df = sag.list_stocks(year)
        return _df_to_json(df, f"SAG stock list for {year}")
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def sag_search_stocks(species: str, year: int = 2024) -> str:
    """Search ICES assessed stocks by species name or stock label.

    Searches in species name, stock description, and stock key label.

    Args:
        species: Search term (e.g. 'herring', 'cod', 'her.27')
        year: Assessment year (default: 2024)
    """
    try:
        df = sag.search_stocks_by_species(species, year)
        return _df_to_json(df, f"Stocks matching '{species}' in {year}")
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def sag_get_stock_summary(assessment_key: int) -> str:
    """Get full stock assessment summary: SSB, fishing mortality (F),
    recruitment, catches, and landings time-series.

    Use sag_list_stocks or sag_search_stocks to find the AssessmentKey first.

    Args:
        assessment_key: ICES assessment key (integer)
    """
    try:
        data = sag.get_summary_table(assessment_key)
        if data is None:
            return json.dumps({"error": "No data found for this assessment key"})

        meta = {k: v for k, v in data.items() if k != "Lines"}
        lines = data.get("Lines", [])

        # Trim lines to essential columns
        trimmed = []
        for line in lines:
            trimmed.append({
                k: v for k, v in line.items()
                if v is not None and k in (
                    "Year", "Recruitment", "SSB", "Low_SSB", "High_SSB",
                    "F", "Low_F", "High_F", "Catches", "Landings",
                    "Discards", "TBiomass",
                )
            })

        return json.dumps({
            "metadata": meta,
            "time_series": trimmed,
            "years_covered": len(trimmed),
        }, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def sag_get_reference_points(assessment_key: int) -> str:
    """Get biological reference points for a stock (Blim, Bpa, FMSY, MSYBtrigger).

    These define the boundaries for sustainable fishing.

    Args:
        assessment_key: ICES assessment key
    """
    try:
        data = sag.get_reference_points(assessment_key)
        if data is None:
            return json.dumps({"error": "No reference points found"})
        return json.dumps(data, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ===========================================================================
# SID Tools (Stock Information Database)
# ===========================================================================

@mcp.tool()
def sid_search_stocks(
    query: str,
    search_type: str = "species",
    year: int | None = None,
) -> str:
    """Search the ICES Stock Information Database.

    Args:
        query: Search term (species name, stock label, or expert group code)
        search_type: One of 'species', 'label', 'expert_group', 'ecoregion'
        year: Optional year filter
    """
    try:
        if search_type == "species":
            df = sid.search_by_species(query, year)
        elif search_type == "label":
            df = sid.search_by_label(query, year)
        elif search_type == "expert_group":
            df = sid.get_by_expert_group(query, year)
        elif search_type == "ecoregion":
            df = sid.get_by_ecoregion(query, year)
        else:
            return json.dumps({"error": f"Unknown search_type: {search_type}"})

        return _df_to_json(df, f"SID results for '{query}'")
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def sid_stocks_by_year(year: int) -> str:
    """Get all published ICES stocks for a specific year.

    Args:
        year: Year to query
    """
    try:
        df = sid.get_stocks_by_year(year)
        return _df_to_json(df, f"All SID stocks for {year}")
    except Exception as e:
        return json.dumps({"error": str(e)})


# ===========================================================================
# Vocabulary / Species Tools
# ===========================================================================

@mcp.tool()
def ices_search_species(query: str, limit: int = 20) -> str:
    """Search ICES species vocabulary by name.

    Returns WoRMS Aphia ID keys and species names. Use the Key (Aphia ID)
    in DATRAS tools to filter by species.

    Args:
        query: Species name or partial name (e.g. 'Gadus', 'herring', 'Clupea')
        limit: Maximum results (default 20)
    """
    try:
        df = vocab.search_species(query, limit)
        return _df_to_json(df, f"Species matching '{query}'")
    except Exception as e:
        return json.dumps({"error": str(e)})


# ===========================================================================
# GIS / Spatial Tools
# ===========================================================================

@mcp.tool()
def ices_list_gis_layers() -> str:
    """List available ICES GIS reference layers (statistical areas, rectangles, ecoregions)."""
    layers = gis.list_available_layers()
    return json.dumps({"layers": layers})


@mcp.tool()
def ices_get_areas(area_filter: str = "", max_features: int = 100) -> str:
    """Get ICES statistical areas as GeoJSON.

    Args:
        area_filter: Filter by ICES area code substring (e.g. '27.3.d' for Baltic)
        max_features: Maximum features to return (default 100)
    """
    try:
        data = gis.get_ices_areas(
            area_filter=area_filter if area_filter else None,
            max_features=max_features,
        )
        n = len(data.get("features", []))
        return json.dumps({
            "type": "FeatureCollection",
            "features_count": n,
            "features": data.get("features", [])[:50],  # Cap for token limits
            "note": f"Showing {min(n, 50)} of {n} features" if n > 50 else None,
        }, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def ices_get_rectangles(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float,
    max_features: int = 500,
) -> str:
    """Get ICES statistical areas within a bounding box as GeoJSON.

    Args:
        min_lon: Western boundary longitude
        min_lat: Southern boundary latitude
        max_lon: Eastern boundary longitude
        max_lat: Northern boundary latitude
        max_features: Maximum features (default 500)
    """
    try:
        data = gis.get_ices_areas_by_bbox(
            bbox=(min_lon, min_lat, max_lon, max_lat),
            max_features=max_features,
        )
        n = len(data.get("features", []))
        return json.dumps({
            "type": "FeatureCollection",
            "features_count": n,
            "features": data.get("features", [])[:100],
            "note": f"Showing {min(n, 100)} of {n} features" if n > 100 else None,
        }, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def ices_get_gis_layer(
    layer: str,
    max_features: int = 200,
    cql_filter: str = "",
) -> str:
    """Get any ICES GIS layer as GeoJSON.

    Use ices_list_gis_layers to see available layers.

    Args:
        layer: Layer alias or full WFS name
        max_features: Maximum features (default 200)
        cql_filter: Optional CQL filter expression
    """
    try:
        data = gis.get_features(
            layer,
            max_features=max_features,
            cql_filter=cql_filter if cql_filter else None,
        )
        n = len(data.get("features", []))
        return json.dumps({
            "type": "FeatureCollection",
            "features_count": n,
            "features": data.get("features", [])[:100],
        }, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ===========================================================================
# Analysis Tools
# ===========================================================================

@mcp.tool()
def ices_analyse_distribution(
    survey: str,
    years: list[int],
    quarters: list[int],
    aphia: list[int],
) -> str:
    """Analyse fish distribution from DATRAS survey data.

    Fetches haul data and catch weights, then computes:
    - Spatial extent (lat/lon range) of catches
    - Mean CPUE by year
    - Proportion of hauls with the species present (occurrence frequency)
    - Depth range where species was caught

    Args:
        survey: Survey acronym (e.g. 'NS-IBTS', 'BITS')
        years: List of years
        quarters: List of quarters
        aphia: List of WoRMS Aphia IDs
    """
    try:
        from ices_datras import get_catch_wgt
        import numpy as np

        df = get_catch_wgt(survey, years, quarters, aphia)
        if df is None or df.empty:
            return json.dumps({"error": "No data returned"})

        results = {}
        for sp in df["Valid_Aphia"].dropna().unique():
            sp_df = df[df["Valid_Aphia"] == sp]
            present = sp_df[sp_df["CatchWgt"] > 0]

            # Coordinates
            lat_col = next((c for c in ("ShootLat", "HaulLat", "Latitude") if c in sp_df.columns), None)
            lon_col = next((c for c in ("ShootLong", "HaulLong", "Longitude") if c in sp_df.columns), None)
            depth_col = next((c for c in ("Depth", "BottomDepth", "HaulDepth") if c in sp_df.columns), None)

            spatial = {}
            if lat_col and lon_col and not present.empty:
                lats = present[lat_col].dropna().astype(float)
                lons = present[lon_col].dropna().astype(float)
                if not lats.empty:
                    spatial = {
                        "lat_range": [float(lats.min()), float(lats.max())],
                        "lon_range": [float(lons.min()), float(lons.max())],
                        "centre": [float(lats.mean()), float(lons.mean())],
                    }

            depth_info = {}
            if depth_col and not present.empty:
                depths = present[depth_col].dropna().astype(float)
                if not depths.empty:
                    depth_info = {
                        "min_depth": float(depths.min()),
                        "max_depth": float(depths.max()),
                        "mean_depth": round(float(depths.mean()), 1),
                    }

            # Yearly stats
            yearly = {}
            if "Year" in sp_df.columns:
                for yr, grp in sp_df.groupby("Year"):
                    n_hauls = len(grp)
                    n_present = (grp["CatchWgt"] > 0).sum()
                    yearly[int(yr)] = {
                        "total_hauls": int(n_hauls),
                        "hauls_with_catch": int(n_present),
                        "occurrence_pct": round(100 * n_present / n_hauls, 1) if n_hauls > 0 else 0,
                        "mean_catch_wgt_kg": round(float(grp["CatchWgt"].mean()), 3),
                        "total_catch_wgt_kg": round(float(grp["CatchWgt"].sum()), 1),
                    }

            results[int(sp)] = {
                "aphia_id": int(sp),
                "total_hauls": len(sp_df),
                "hauls_with_catch": len(present),
                "occurrence_pct": round(100 * len(present) / len(sp_df), 1) if len(sp_df) > 0 else 0,
                "spatial": spatial,
                "depth": depth_info,
                "yearly": yearly,
            }

        return json.dumps({"survey": survey, "species_results": results}, default=str)

    except ImportError:
        return _datras_not_available()
    except Exception as e:
        return json.dumps({"error": str(e)})


# ===========================================================================
# Helpers
# ===========================================================================

def _df_to_json(df, label: str = "data") -> str:
    """Convert a DataFrame to a JSON response, handling None and large frames."""
    if df is None or (hasattr(df, "empty") and df.empty):
        return json.dumps({"label": label, "rows": 0, "data": []})

    n = len(df)
    MAX_ROWS = 500

    # Convert to records
    records = df.head(MAX_ROWS).to_dict(orient="records")

    result = {
        "label": label,
        "rows": n,
        "columns": list(df.columns),
        "data": records,
    }
    if n > MAX_ROWS:
        result["truncated"] = True
        result["note"] = f"Showing first {MAX_ROWS} of {n} rows"

    return json.dumps(result, default=str)


def _datras_not_available() -> str:
    return json.dumps({
        "error": (
            "ices_datras package not found. Clone it from "
            "https://github.com/razinkele/marine-gis-tools and add to "
            "PYTHONPATH, or place it in the vendor/ directory."
        )
    })


# ===========================================================================
# Resources (contextual reference data)
# ===========================================================================

@mcp.resource("ices://surveys/overview")
def surveys_overview() -> str:
    """Overview of major ICES trawl surveys and their coverage."""
    return json.dumps({
        "description": "Major ICES trawl surveys",
        "surveys": {
            "NS-IBTS": "North Sea International Bottom Trawl Survey (all North Sea, quarterly)",
            "BITS": "Baltic International Trawl Survey (Baltic Sea, Q1 & Q4)",
            "BTS": "Beam Trawl Survey (North Sea, southern areas)",
            "EVHOE": "French Atlantic survey (Bay of Biscay)",
            "FR-CGFS": "French Channel Ground Fish Survey",
            "IE-IGFS": "Irish Ground Fish Survey",
            "ROCKALL": "Rockall survey (deep water, NE Atlantic)",
            "SP-PORC": "Spanish Porcupine survey",
            "SWC-IBTS": "Scottish West Coast IBTS",
            "NIGFS": "Northern Ireland Ground Fish Survey",
        },
        "data_types": {
            "HH": "Haul data (station positions, depth, gear, environment)",
            "HL": "Length-frequency data (species, length, count per haul)",
            "CA": "Catch/age data (individual fish: age, length, weight, sex, maturity)",
        },
        "common_species_aphia": {
            "Atlantic cod": 126436,
            "Atlantic herring": 126735,
            "European sprat": 126425,
            "European plaice": 127143,
            "Common sole": 127160,
            "Whiting": 126438,
            "Haddock": 126437,
            "European flounder": 127141,
            "Baltic flounder": 1306780,
            "Turbot": 127149,
        },
    })


@mcp.resource("ices://api/endpoints")
def api_endpoints() -> str:
    """Reference of all ICES API endpoints used by this server."""
    return json.dumps({
        "datras_xml": "https://datras.ices.dk/WebServices/DATRASWebService.asmx",
        "datras_download": "https://datras.ices.dk/Data_products/Download/DATRASDownloadAPI.aspx",
        "sag": "https://sag.ices.dk/SAG_API/api/",
        "sid": "https://sid.ices.dk/services/",
        "vocab": "https://vocab.ices.dk/services/pox/GetCodeList/",
        "gis_wfs": "https://gis.ices.dk/geoserver/wfs",
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
