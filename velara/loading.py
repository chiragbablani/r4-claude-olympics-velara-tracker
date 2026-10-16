"""Loading and cleaning of the input pack.

Reads VELARA_tracker.xlsx (expected to contain one or more monthly tabs)
and dashboard_status.csv, and returns normalized, minimally-cleaned
pandas structures for downstream modules.

No business rules live here. "Cleaning" is limited to generic,
rule-agnostic concerns: trimming whitespace in headers/strings,
normalizing column names, and parsing dates where a column is
unambiguously a date column. Anything data-specific (what counts as a
slipped milestone, which columns matter, what "clean" means) is out of
scope until the domain rules are confirmed.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import pandas as pd


class LoadedPack(NamedTuple):
    tracker_sheets: dict[str, pd.DataFrame]
    dashboard: pd.DataFrame


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_tracker(tracker_path: Path) -> dict[str, pd.DataFrame]:
    """Load every sheet of the tracker workbook.

    Returns a dict of sheet_name -> DataFrame, columns normalized
    (stripped of surrounding whitespace). No row filtering or dtype
    coercion beyond pandas' own defaults.
    """
    sheets = pd.read_excel(tracker_path, sheet_name=None, engine="openpyxl")
    return {name: _normalize_columns(df) for name, df in sheets.items()}


def load_dashboard(dashboard_path: Path) -> pd.DataFrame:
    """Load the dashboard status CSV with normalized column names."""
    df = pd.read_csv(dashboard_path)
    return _normalize_columns(df)


def load_pack(tracker_path: Path, dashboard_path: Path) -> LoadedPack:
    return LoadedPack(
        tracker_sheets=load_tracker(tracker_path),
        dashboard=load_dashboard(dashboard_path),
    )
