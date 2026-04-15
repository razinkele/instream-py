"""
ICES Vocabulary service client.

Accesses species codes and other reference vocabularies from
vocab.ices.dk.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

VOCAB_URL = "https://vocab.ices.dk/services/pox/GetCodeList"

_SESSION: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def get_code_list(code_type: str) -> pd.DataFrame:
    """
    Get a vocabulary code list.

    Parameters
    ----------
    code_type : str
        e.g. 'SpecWoRMS', 'Country', 'Ship', 'Gear', 'ICES_Area'

    Returns
    -------
    DataFrame with columns: Key, Description, LongDescription
    """
    url = f"{VOCAB_URL}/{code_type}"
    resp = _get_session().get(url, timeout=120)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    ns = {}
    # Handle namespace
    for el in root.iter():
        if "Code" in el.tag:
            break

    rows = []
    for code_el in root.iter():
        tag = code_el.tag.split("}")[-1] if "}" in code_el.tag else code_el.tag
        if tag != "Code":
            continue

        row = {}
        for child in code_el:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child_tag in ("Key", "Description", "LongDescription", "GUID"):
                row[child_tag] = child.text.strip() if child.text else ""
        if row and "Key" in row:
            rows.append(row)

    return pd.DataFrame(rows)


def search_species(query: str, limit: int = 20) -> pd.DataFrame:
    """
    Search species by name in the SpecWoRMS vocabulary.
    Downloads the full list and filters locally (cached after first call).
    """
    if not hasattr(search_species, "_cache"):
        search_species._cache = get_code_list("SpecWoRMS")

    df = search_species._cache
    if df.empty:
        return df

    mask = df["Description"].str.contains(query, case=False, na=False)
    if "LongDescription" in df.columns:
        mask = mask | df["LongDescription"].str.contains(query, case=False, na=False)

    return df[mask].head(limit).reset_index(drop=True)
