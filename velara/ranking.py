"""Ranking and output formatting.

Rank by impact descending, ties broken by slippage descending then
country name ascending. All countries appear once with unique ranks
1..N. Zero-slippage countries get driver NONE.
"""
from __future__ import annotations

from .slippage import CountrySlippage


def build_risk_ranking(slippage_by_country: dict[str, CountrySlippage]) -> list[dict]:
    ordered = sorted(
        slippage_by_country.values(),
        key=lambda s: (-s.impact_score, -s.slippage_days, s.country),
    )
    return [
        {
            "country": s.country,
            "rank": idx + 1,
            "slippage_days": s.slippage_days,
            "impact_score": int(s.impact_score),
            "driver": s.driver,
            "evidence": s.evidence,
        }
        for idx, s in enumerate(ordered)
    ]


def build_clean_ranking(countries: list[str]) -> list[dict]:
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
