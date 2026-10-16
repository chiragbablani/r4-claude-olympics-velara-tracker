"""Month-over-month change detection.

Row key confirmed: each tracker row is one SKU in one country, so the
composite key is (Country, SKU). Country matching is case-insensitive
because the column is named "Country" in the tracker and Ref_Countries
sheets but "country" in dashboard_status.csv, and values could vary in
case too; SKU matching is exact (stripped of whitespace only).

Structural comparison on that key — duplicate keys within a month, and
keys that appear or disappear between two months — is mechanical, not a
domain judgment call, so it is implemented here. Deciding which
column-level changes between months are *meaningful* (e.g. what counts
as a slipped date) is still unconfirmed with domain leads and remains
unimplemented. See NOTES/lead_refs.md.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import pandas as pd

DEFAULT_KEY_COLUMNS = ["Country", "SKU"]


def find_column(df: pd.DataFrame, name: str) -> str | None:
    """Find a column by name, case-insensitive and whitespace-tolerant."""
    target = name.strip().lower()
    for col in df.columns:
        if str(col).strip().lower() == target:
            return col
    return None


def composite_key(row: pd.Series, country_col: str, sku_col: str) -> tuple[str, str]:
    """Build the (country, sku) key for one row.

    Country is lowercased and stripped (case-insensitive match across
    sheets that spell the column differently). SKU is stripped only.
    """
    country_value = row[country_col]
    sku_value = row[sku_col]
    country_text = "" if pd.isna(country_value) else str(country_value).strip().lower()
    sku_text = "" if pd.isna(sku_value) else str(sku_value).strip()
    return (country_text, sku_text)


def composite_keys(df: pd.DataFrame, country_col: str, sku_col: str) -> list[tuple[str, str]]:
    return [composite_key(row, country_col, sku_col) for _, row in df.iterrows()]


def find_duplicate_keys(
    df: pd.DataFrame, country_col: str, sku_col: str
) -> dict[tuple[str, str], int]:
    """Return {(country, sku): count} for keys appearing more than once in this sheet."""
    counts = Counter(composite_keys(df, country_col, sku_col))
    return {key: count for key, count in counts.items() if count > 1}


@dataclass
class KeyStructureDiff:
    country_col_earlier: str
    sku_col_earlier: str
    country_col_later: str
    sku_col_later: str
    duplicate_keys_earlier: dict[tuple[str, str], int] = field(default_factory=dict)
    duplicate_keys_later: dict[tuple[str, str], int] = field(default_factory=dict)
    only_in_earlier: list[tuple[str, str]] = field(default_factory=list)
    only_in_later: list[tuple[str, str]] = field(default_factory=list)


def key_structure_diff(earlier: pd.DataFrame, later: pd.DataFrame) -> KeyStructureDiff:
    """Structural (Country, SKU) comparison of two monthly snapshots.

    Reports duplicate keys within each month and which keys appear in
    only one of the two months. Does not compare other column values
    between matched rows — see module docstring.

    Raises ValueError if a Country or SKU column can't be found in
    either frame.
    """
    country_a = find_column(earlier, "Country")
    sku_a = find_column(earlier, "SKU")
    country_b = find_column(later, "Country")
    sku_b = find_column(later, "SKU")

    if not all([country_a, sku_a, country_b, sku_b]):
        raise ValueError("could not find both Country and SKU columns in both frames")

    keys_a = set(composite_keys(earlier, country_a, sku_a))
    keys_b = set(composite_keys(later, country_b, sku_b))

    return KeyStructureDiff(
        country_col_earlier=country_a,
        sku_col_earlier=sku_a,
        country_col_later=country_b,
        sku_col_later=sku_b,
        duplicate_keys_earlier=find_duplicate_keys(earlier, country_a, sku_a),
        duplicate_keys_later=find_duplicate_keys(later, country_b, sku_b),
        only_in_earlier=sorted(keys_a - keys_b),
        only_in_later=sorted(keys_b - keys_a),
    )


def diff_month_over_month(
    earlier: pd.DataFrame,
    later: pd.DataFrame,
    key_columns: list[str] = DEFAULT_KEY_COLUMNS,
) -> pd.DataFrame:
    """Full value-level comparison of two monthly snapshots on the row key.

    Stub: not implemented. Which column-level changes count as
    meaningful (vs. noise) is still unconfirmed with domain leads. Use
    key_structure_diff() for the structural-only (duplicate/missing key)
    comparison, which is implemented above.
    """
    raise NotImplementedError("month-over-month value diff logic is not yet defined")
