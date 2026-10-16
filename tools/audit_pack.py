#!/usr/bin/env python3
"""Read-only data audit for a pack folder.

Usage:
    python3 tools/audit_pack.py <pack_dir>

Prints a plain-text report to stdout covering:
    - sheet names and row counts per monthly tab
    - column names per sheet
    - blank counts per column
    - duplicate rows
    - date-like columns stored as text, and mixed date formats within a column
    - unexpected / inconsistent category values per column
    - a month-to-month diff summary on the (Country, SKU) row key:
      duplicate keys within a month, and keys missing/added between months

Row key: each tracker row is one SKU in one country, so the row key is
the composite (Country, SKU) pair — confirmed, not guessed. The country
column is named "Country" in the tracker and Ref_Countries sheets, and
"country" in dashboard_status.csv; matching is case-insensitive
everywhere via velara.changes.find_column.

Month-to-month diffing only runs between sheets whose name matches the
tracker's monthly-tab pattern (e.g. "Tracker_2026_01"), so reference
tabs (Ref_Countries, Ref_SKUs, Ref_Sites, Column Guide) are audited for
blanks/duplicates/categories but are never paired against each other or
against monthly tabs.

This tool never writes to the pack folder or mutates any data; it only
reads and prints. It is a human-facing exploration aid, separate from
solve.py's own logic.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from velara.changes import find_column, find_duplicate_keys, key_structure_diff  # noqa: E402

DATE_LIKE_PATTERNS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),          # 2026-01-31
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$"),    # 1/31/2026 or 31/1/26
    re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"),  # 31-Jan-2026
    re.compile(r"^[A-Za-z]{3,9} \d{1,2},? \d{4}$"),  # January 31, 2026
]

MONTHLY_TAB_PATTERN = re.compile(r"^Tracker_\d{4}_\d{2}$", re.IGNORECASE)


def section(title: str) -> None:
    print()
    print("=" * len(title))
    print(title)
    print("=" * len(title))


def describe_date_like_text_column(series: pd.Series) -> str | None:
    """Return a note if a text column looks like it holds dates stored as text."""
    non_null = series.dropna().astype(str).str.strip()
    non_null = non_null[non_null != ""]
    if non_null.empty:
        return None

    matched_patterns: set[int] = set()
    matches = 0
    for value in non_null:
        for idx, pattern in enumerate(DATE_LIKE_PATTERNS):
            if pattern.match(value):
                matched_patterns.add(idx)
                matches += 1
                break

    ratio = matches / len(non_null)
    if ratio < 0.5:
        return None

    note = f"looks date-like as TEXT ({matches}/{len(non_null)} values match a date pattern)"
    if len(matched_patterns) > 1:
        note += f"; MIXED FORMATS across {len(matched_patterns)} distinct pattern(s)"
    return note


def audit_dataframe(name: str, df: pd.DataFrame) -> None:
    section(f"Sheet/table: {name}")
    print(f"rows: {len(df)}  columns: {len(df.columns)}")
    print(f"columns: {list(df.columns)}")

    print("\nblank counts per column:")
    for col in df.columns:
        blank_count = int(df[col].isna().sum())
        if df[col].dtype == object:
            blank_count += int((df[col].astype(str).str.strip() == "").sum())
        print(f"  {col}: {blank_count}")

    dup_count = int(df.duplicated().sum())
    print(f"\nfully duplicate rows: {dup_count}")

    print("\ntext columns that look date-like:")
    found_any = False
    for col in df.columns:
        if df[col].dtype != object:
            continue
        note = describe_date_like_text_column(df[col])
        if note:
            found_any = True
            print(f"  {col}: {note}")
    if not found_any:
        print("  (none detected)")

    print("\ncategory-like columns (object dtype, low cardinality) and their values:")
    for col in df.columns:
        if df[col].dtype != object:
            continue
        values = df[col].dropna().astype(str).str.strip()
        values = values[values != ""]
        unique_vals = sorted(values.unique().tolist())
        if 0 < len(unique_vals) <= 15:
            print(f"  {col}: {unique_vals}")


def _format_keys(keys: list[tuple[str, str]]) -> str:
    if not keys:
        return "(none)"
    return ", ".join(f"({country!r}, {sku!r})" for country, sku in keys)


def _format_dupes(dupes: dict[tuple[str, str], int]) -> str:
    if not dupes:
        return "(none)"
    return ", ".join(f"({country!r}, {sku!r}) x{count}" for (country, sku), count in dupes.items())


def diff_sheets(name_a: str, df_a: pd.DataFrame, name_b: str, df_b: pd.DataFrame) -> None:
    section(f"Month-to-month diff: {name_a} -> {name_b}")
    print("  row key: (Country, SKU) — country matched case-insensitively")

    try:
        diff = key_structure_diff(df_a, df_b)
    except ValueError as exc:
        print(f"  skipped: {exc}")
        return

    print(f"  duplicate keys within {name_a}: {_format_dupes(diff.duplicate_keys_earlier)}")
    print(f"  duplicate keys within {name_b}: {_format_dupes(diff.duplicate_keys_later)}")
    print(f"  keys only in {name_a} (missing in {name_b}): {_format_keys(diff.only_in_earlier)}")
    print(f"  keys only in {name_b} (missing in {name_a}): {_format_keys(diff.only_in_later)}")


def report_duplicate_keys_within_sheet(name: str, df: pd.DataFrame) -> None:
    country_col = find_column(df, "Country")
    sku_col = find_column(df, "SKU")
    if country_col is None or sku_col is None:
        return
    dupes = find_duplicate_keys(df, country_col, sku_col)
    print(f"\nduplicate (Country, SKU) keys within {name}: {_format_dupes(dupes)}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 tools/audit_pack.py <pack_dir>", file=sys.stderr)
        return 2

    pack_dir = Path(sys.argv[1])
    tracker_path = pack_dir / "VELARA_tracker.xlsx"
    dashboard_path = pack_dir / "dashboard_status.csv"

    if not tracker_path.is_file():
        print(f"missing: {tracker_path}", file=sys.stderr)
        return 1
    if not dashboard_path.is_file():
        print(f"missing: {dashboard_path}", file=sys.stderr)
        return 1

    print(f"AUDIT REPORT for pack: {pack_dir}")
    print(f"tracker: {tracker_path.name}")
    print(f"dashboard: {dashboard_path.name}")

    sheets = pd.read_excel(tracker_path, sheet_name=None, engine="openpyxl")
    for name, df in sheets.items():
        df.columns = [str(c).strip() for c in df.columns]
        audit_dataframe(f"tracker::{name}", df)
        if MONTHLY_TAB_PATTERN.match(name):
            report_duplicate_keys_within_sheet(f"tracker::{name}", df)

    monthly_names = [name for name in sheets if MONTHLY_TAB_PATTERN.match(name)]
    for earlier_name, later_name in zip(monthly_names, monthly_names[1:]):
        diff_sheets(earlier_name, sheets[earlier_name], later_name, sheets[later_name])

    dashboard = pd.read_csv(dashboard_path)
    dashboard.columns = [str(c).strip() for c in dashboard.columns]
    audit_dataframe("dashboard_status.csv", dashboard)

    print()
    print("Audit complete. No data was modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
