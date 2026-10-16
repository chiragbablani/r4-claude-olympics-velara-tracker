"""Derive the authoritative list of countries from the data pack.

The set of countries graded on is whatever appears in the data pack
itself, not a hardcoded list belonging to any one dataset. This module
reads candidate country values out of the loaded pack and canonicalizes
them against the generic ISO 3166-1 reference list in
velara/reference/countries.json (name/alpha-2/alpha-3), so that minor
spelling or casing differences don't produce duplicate "countries".

No assumption is made here about *which* column in the dashboard or
tracker holds the country value beyond a best-effort name match (a
column literally named "country", case-insensitively) — that should be
confirmed against the real data before this is relied on for grading.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from .paths import REFERENCE_COUNTRIES_PATH


def load_reference_countries() -> list[dict]:
    with open(REFERENCE_COUNTRIES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _find_country_column(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if re.fullmatch(r"country", str(col).strip(), flags=re.IGNORECASE):
            return col
    return None


def extract_country_values(frames: list[pd.DataFrame]) -> list[str]:
    """Collect the unique, order-preserved country values found across frames.

    Only looks at a column literally named "country" (case-insensitive).
    Does not canonicalize or validate against the reference list — that
    is a separate step so callers can decide how strict to be.
    """
    seen: dict[str, None] = {}
    for df in frames:
        col = _find_country_column(df)
        if col is None:
            continue
        for value in df[col].dropna():
            text = str(value).strip()
            if text and text not in seen:
                seen[text] = None
    return list(seen.keys())
