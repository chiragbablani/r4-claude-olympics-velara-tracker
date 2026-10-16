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
    - a month-to-month diff summary for matching row keys across sheets

This tool never writes to the pack folder or mutates any data; it only
reads and prints. It is a human-facing exploration aid, separate from
solve.py's own logic.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

DATE_LIKE_PATTERNS = [
    re.compile(r"^\d{4}-\d{2}-\d{2}$"),          # 2026-01-31
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$"),    # 1/31/2026 or 31/1/26
    re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$"),  # 31-Jan-2026
    re.compile(r"^[A-Za-z]{3,9} \d{1,2},? \d{4}$"),  # January 31, 2026
]

CANDIDATE_KEY_NAMES = {"country", "country_code", "code", "market", "region"}


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


def find_key_column(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if str(col).strip().lower() in CANDIDATE_KEY_NAMES:
            return col
    return None


def diff_sheets(name_a: str, df_a: pd.DataFrame, name_b: str, df_b: pd.DataFrame) -> None:
    key_a = find_key_column(df_a)
    key_b = find_key_column(df_b)
    section(f"Month-to-month diff: {name_a} -> {name_b}")

    if key_a is None or key_b is None or key_a != key_b:
        print(
            f"  skipped: could not find a matching row key column "
            f"(candidates checked: {sorted(CANDIDATE_KEY_NAMES)})"
        )
        return

    key = key_a
    keys_a = set(df_a[key].dropna().astype(str).str.strip())
    keys_b = set(df_b[key].dropna().astype(str).str.strip())

    only_in_a = sorted(keys_a - keys_b)
    only_in_b = sorted(keys_b - keys_a)
    common = sorted(keys_a & keys_b)

    print(f"  key column: {key}")
    print(f"  rows only in {name_a}: {only_in_a if only_in_a else '(none)'}")
    print(f"  rows only in {name_b}: {only_in_b if only_in_b else '(none)'}")

    shared_cols = [c for c in df_a.columns if c in df_b.columns and c != key]
    if not shared_cols or not common:
        print("  no shared non-key columns or no common rows to diff values on")
        return

    a_by_key = df_a.set_index(df_a[key].astype(str).str.strip())
    b_by_key = df_b.set_index(df_b[key].astype(str).str.strip())

    changed_count = 0
    for row_key in common:
        row_a = a_by_key.loc[row_key]
        row_b = b_by_key.loc[row_key]
        for col in shared_cols:
            val_a = row_a[col] if not isinstance(row_a, pd.DataFrame) else row_a[col].iloc[0]
            val_b = row_b[col] if not isinstance(row_b, pd.DataFrame) else row_b[col].iloc[0]
            if pd.isna(val_a) and pd.isna(val_b):
                continue
            if str(val_a) != str(val_b):
                changed_count += 1
    print(f"  changed (key, column) cell values across common rows: {changed_count}")


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

    sheet_names = list(sheets.keys())
    for earlier_name, later_name in zip(sheet_names, sheet_names[1:]):
        diff_sheets(earlier_name, sheets[earlier_name], later_name, sheets[later_name])

    dashboard = pd.read_csv(dashboard_path)
    dashboard.columns = [str(c).strip() for c in dashboard.columns]
    audit_dataframe("dashboard_status.csv", dashboard)

    print()
    print("Audit complete. No data was modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
