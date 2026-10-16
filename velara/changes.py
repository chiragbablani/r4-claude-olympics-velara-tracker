"""Month-over-month change detection.

Intended to compare the same row key (e.g. country + milestone) across
consecutive monthly tabs in the tracker workbook and surface what
changed between them (value changed, row added, row disappeared, etc).

Not implemented yet: the row key, the comparison columns, and what
counts as a meaningful change all depend on confirmed domain rules that
have not been gathered yet. See NOTES/lead_refs.md.
"""
from __future__ import annotations

import pandas as pd


def diff_month_over_month(
    earlier: pd.DataFrame,
    later: pd.DataFrame,
    key_columns: list[str],
) -> pd.DataFrame:
    """Compare two monthly snapshots on the given row key.

    Stub: not implemented. Raises NotImplementedError until the row key
    and comparison columns are confirmed with domain leads.
    """
    raise NotImplementedError("month-over-month diff logic is not yet defined")
