"""
ICES Stock Information Database (SID) client.

REST endpoints at sid.ices.dk/services/:
  - /stockkeylabel/{label}[/{year}]  — search by stock key label
  - /species/{name}[/{year}]         — search by species name
  - /eg/{expertgroup}[/{year}]       — search by expert group
  - /year/{year}                     — all stocks for a year
  - /datacategory/{cat}[/{year}]     — by data category
  - /adg/{adg}[/{year}]             — by advice drafting group
  - /stockkey/{key}                  — most recent stock by key
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://sid.ices.dk/services"

_SESSION: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({"Accept": "application/json"})
    return _SESSION


def _get_json(path: str) -> Any:
    """Fetch JSON from a SID endpoint."""
    url = f"{BASE_URL}/{path}"
    resp = _get_session().get(url, timeout=60)
    resp.raise_for_status()
    return resp.json()


def search_by_species(species: str, year: Optional[int] = None) -> pd.DataFrame:
    """Search stocks by species name (partial match)."""
    path = f"species/{species}"
    if year:
        path += f"/{year}"
    data = _get_json(path)
    return pd.DataFrame(data) if data else pd.DataFrame()


def search_by_label(label: str, year: Optional[int] = None) -> pd.DataFrame:
    """Search stocks by stock key label (e.g. 'her', 'cod')."""
    path = f"stockkeylabel/{label}"
    if year:
        path += f"/{year}"
    data = _get_json(path)
    return pd.DataFrame(data) if data else pd.DataFrame()


def get_by_expert_group(eg: str, year: Optional[int] = None) -> pd.DataFrame:
    """Get stocks managed by a specific expert group."""
    path = f"eg/{eg}"
    if year:
        path += f"/{year}"
    data = _get_json(path)
    return pd.DataFrame(data) if data else pd.DataFrame()


def get_stocks_by_year(year: int) -> pd.DataFrame:
    """Get all published stocks for a specific year."""
    data = _get_json(f"year/{year}")
    return pd.DataFrame(data) if data else pd.DataFrame()


def get_stock_by_key(stock_key: int) -> Optional[dict]:
    """Get the most recent record for a specific stock key."""
    data = _get_json(f"stockkey/{stock_key}")
    if isinstance(data, list) and len(data) > 0:
        return data[0]
    return data if isinstance(data, dict) else None


def get_by_ecoregion(ecoregion: str, year: Optional[int] = None) -> pd.DataFrame:
    """
    Search stocks using OData filter on EcoRegion.
    Uses the OData v3 endpoint for flexible querying.
    """
    url = f"{BASE_URL}/odata3/StockListDWs3"
    filt = f"substringof('{ecoregion}',EcoRegion)"
    if year:
        filt += f" and ActiveYear eq {year}"
    params = {"$filter": filt}
    resp = _get_session().get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if "value" in data:
        return pd.DataFrame(data["value"])
    return pd.DataFrame(data) if isinstance(data, list) else pd.DataFrame()
