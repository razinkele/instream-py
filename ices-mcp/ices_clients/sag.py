"""
ICES Stock Assessment Graphs (SAG) API client.

Endpoints:
  - GET /SAG_API/api/StockList?year=YYYY          → list assessed stocks
  - GET /SAG_API/api/SummaryTable?AssessmentKey=N  → SSB/F/R time-series
  - GET /SAG_API/api/RefPoints?AssessmentKey=N     → reference points (Blim, Bpa, FMSY…)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://sag.ices.dk/SAG_API/api"

_SESSION: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({"Accept": "application/json"})
    return _SESSION


def _get_json(endpoint: str, **params: Any) -> Any:
    """Fetch JSON from a SAG API endpoint."""
    url = f"{BASE_URL}/{endpoint}"
    resp = _get_session().get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def list_stocks(year: int) -> pd.DataFrame:
    """List all assessed stocks for a given assessment year."""
    data = _get_json("StockList", year=year)
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    cols_keep = [
        "AssessmentKey", "StockKeyLabel", "StockDescription",
        "SpeciesName", "Purpose", "AssessmentYear", "ModelType",
        "ModelName", "LinkToAdvice",
    ]
    cols_keep = [c for c in cols_keep if c in df.columns]
    return df[cols_keep]


def get_summary_table(assessment_key: int) -> Optional[dict]:
    """
    Get the summary table for a stock assessment.
    Returns metadata + time-series lines with SSB, F, Recruitment, Catches.
    """
    data = _get_json("SummaryTable", AssessmentKey=assessment_key)
    if not data:
        return None
    return data


def get_summary_dataframe(assessment_key: int) -> Optional[pd.DataFrame]:
    """Get the summary table lines as a DataFrame."""
    data = get_summary_table(assessment_key)
    if data is None or "Lines" not in data:
        return None
    lines = data["Lines"]
    if not lines:
        return None
    df = pd.DataFrame(lines)
    cols_core = [
        "Year", "Recruitment", "SSB", "Low_SSB", "High_SSB",
        "F", "Low_F", "High_F", "Catches", "Landings", "Discards",
        "TBiomass",
    ]
    cols_core = [c for c in cols_core if c in df.columns]
    return df[cols_core]


def get_reference_points(assessment_key: int) -> Optional[dict]:
    """Get reference points (Blim, Bpa, FMSY, etc.) for a stock."""
    try:
        data = _get_json("RefPoints", AssessmentKey=assessment_key)
        return data
    except requests.HTTPError:
        return None


def search_stocks_by_species(species_keyword: str, year: int = 2024) -> pd.DataFrame:
    """Search stocks by species name substring."""
    df = list_stocks(year)
    if df.empty:
        return df
    mask = (
        df["SpeciesName"].str.contains(species_keyword, case=False, na=False)
        | df["StockDescription"].str.contains(species_keyword, case=False, na=False)
        | df["StockKeyLabel"].str.contains(species_keyword, case=False, na=False)
    )
    return df[mask].reset_index(drop=True)
