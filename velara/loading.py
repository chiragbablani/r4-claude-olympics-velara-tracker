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

Serial-date cleaning: a date-named column that loads as plain integers
in a plausible Excel serial-date range (1900 date system, epoch
1899-12-30) is converted to real dates. This is a generic Excel-parsing
fix, not a domain rule — Excel/openpyxl can lose the date number format
on a cell and fall back to the raw serial integer, and this reconstructs
the date that was always there. Every conversion is logged to stderr.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

import pandas as pd

EXCEL_SERIAL_EPOCH = pd.Timestamp("1899-12-30")

# Plausible range for a serial integer to actually be a date rather than
# some other integer quantity: 1950-01-01 .. 2100-01-01. Wide on purpose
# (this is a sanity bound, not a business assumption about launch dates).
PLAUSIBLE_SERIAL_MIN = 18264
PLAUSIBLE_SERIAL_MAX = 73050

_DATE_NAME_PATTERN = re.compile(r"date", re.IGNORECASE)


class LoadedPack(NamedTuple):
    tracker_sheets: dict[str, pd.DataFrame]
    dashboard: pd.DataFrame
    serial_date_columns: list[tuple[str, str]]  # (sheet_name, column_name) converted from int serial


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _looks_like_date_column(column_name: object) -> bool:
    return bool(_DATE_NAME_PATTERN.search(str(column_name)))


def _is_plausible_excel_serial_series(series: pd.Series) -> bool:
    non_null = series.dropna()
    if non_null.empty or not pd.api.types.is_integer_dtype(series):
        return False
    return bool(
        ((non_null >= PLAUSIBLE_SERIAL_MIN) & (non_null <= PLAUSIBLE_SERIAL_MAX)).all()
    )


def convert_serial_date_columns(
    df: pd.DataFrame, sheet_name: str
) -> tuple[pd.DataFrame, list[str]]:
    """Convert integer-loaded Excel serial dates back to real dates.

    A column is converted only if its name looks date-like AND it is an
    integer dtype AND every non-null value falls in a plausible serial
    range. Returns the (possibly modified) DataFrame and a list of
    human-readable log lines describing each conversion made.
    """
    df = df.copy()
    log_lines: list[str] = []

    for col in df.columns:
        if not _looks_like_date_column(col):
            continue
        series = df[col]
        if not _is_plausible_excel_serial_series(series):
            continue

        converted = EXCEL_SERIAL_EPOCH + pd.to_timedelta(series, unit="D")
        n = int(series.notna().sum())
        log_lines.append(
            f"[cleaning] {sheet_name}: column {col!r} loaded as integer Excel "
            f"serial date(s) (range {int(series.min())}..{int(series.max())}); "
            f"converted {n} value(s) to real dates "
            f"(range {converted.min().date()}..{converted.max().date()})"
        )
        df[col] = converted

    return df, log_lines


def load_tracker(tracker_path: Path) -> tuple[dict[str, pd.DataFrame], list[tuple[str, str]]]:
    """Load every sheet of the tracker workbook.

    Returns (dict of sheet_name -> DataFrame, list of (sheet, col) pairs
    that were converted from integer serial dates).
    """
    sheets = pd.read_excel(tracker_path, sheet_name=None, engine="openpyxl")
    cleaned: dict[str, pd.DataFrame] = {}
    all_serial_cols: list[tuple[str, str]] = []
    for name, df in sheets.items():
        df = _normalize_columns(df)
        # Detect serial-date columns BEFORE converting (check raw dtypes)
        for col in df.columns:
            if _looks_like_date_column(col) and _is_plausible_excel_serial_series(df[col]):
                all_serial_cols.append((name, col))
        df, log_lines = convert_serial_date_columns(df, name)
        for line in log_lines:
            print(line, file=sys.stderr)
        cleaned[name] = df
    return cleaned, all_serial_cols


def load_dashboard(dashboard_path: Path) -> pd.DataFrame:
    """Load the dashboard status CSV with normalized column names."""
    df = pd.read_csv(dashboard_path)
    return _normalize_columns(df)


def load_pack(tracker_path: Path, dashboard_path: Path) -> LoadedPack:
    tracker_sheets, serial_cols = load_tracker(tracker_path)
    return LoadedPack(
        tracker_sheets=tracker_sheets,
        dashboard=load_dashboard(dashboard_path),
        serial_date_columns=serial_cols,
    )
