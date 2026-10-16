"""Ranking and output formatting.

Combines rule findings and per-country slippage data into the final
"risk_ranking" list (rank 1 = worst), and assembles the final payload
dict with "findings" and "risk_ranking" keys per the output contract.

Ranking order (what makes one country "worse" than another) is not
implemented yet — it depends on slippage.compute_slippage, which is
itself a stub pending confirmed domain rules.
"""
from __future__ import annotations


def build_clean_ranking(countries: list[str]) -> list[dict]:
    """Build an all-clean risk_ranking for the given countries.

    Every country gets slippage_days 0, impact_score 0, driver "NONE".
    Rank order among clean countries is arbitrary (alphabetical) since
    there is nothing to differentiate them by.
    """
    ordered = sorted(countries)
    return [
        {
            "country": country,
            "rank": idx + 1,
            "slippage_days": 0,
            "impact_score": 0,
            "driver": "NONE",
            "evidence": "",
        }
        for idx, country in enumerate(ordered)
    ]


def build_payload(findings: list[dict], risk_ranking: list[dict]) -> dict:
    return {"findings": findings, "risk_ranking": risk_ranking}
