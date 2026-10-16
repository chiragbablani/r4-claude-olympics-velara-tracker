"""Output contract validation.

Checks the final JSON payload against the hard rules from the task
contract, before it is printed. This is a structural safety net, not a
domain check — it does not know what a "correct" finding or ranking is,
only whether the shape is valid.

Returns a list of human-readable violation strings; an empty list means
the payload passed every check.
"""
from __future__ import annotations


def validate_contract(
    findings: list[dict],
    risk_ranking: list[dict],
    expected_countries: list[str],
    forecast_volume_by_country: dict[str, float] | None = None,
) -> list[str]:
    violations: list[str] = []

    expected_set = set(expected_countries)
    ranking_countries = [row.get("country") for row in risk_ranking]

    if len(ranking_countries) != len(expected_countries):
        violations.append(
            f"risk_ranking has {len(ranking_countries)} entries, "
            f"expected {len(expected_countries)}"
        )

    if len(set(ranking_countries)) != len(ranking_countries):
        violations.append("risk_ranking contains duplicate countries")

    if set(ranking_countries) != expected_set:
        missing = expected_set - set(ranking_countries)
        extra = set(ranking_countries) - expected_set
        if missing:
            violations.append(f"risk_ranking missing countries: {sorted(missing)}")
        if extra:
            violations.append(f"risk_ranking has unexpected countries: {sorted(extra)}")

    ranks = [row.get("rank") for row in risk_ranking]
    expected_ranks = set(range(1, len(risk_ranking) + 1))
    if len(set(ranks)) != len(ranks):
        violations.append("risk_ranking contains duplicate ranks")
    if set(ranks) != expected_ranks:
        violations.append(f"risk_ranking ranks are not exactly 1..{len(risk_ranking)}")

    for row in risk_ranking:
        country = row.get("country", "<unknown>")
        slippage_days = row.get("slippage_days")
        impact_score = row.get("impact_score")
        driver = row.get("driver")

        if driver == "NONE" and (slippage_days != 0 or impact_score != 0):
            violations.append(
                f"{country}: driver is NONE but slippage_days/impact_score are not both 0"
            )

        if forecast_volume_by_country is not None and country in forecast_volume_by_country:
            expected_impact = slippage_days * forecast_volume_by_country[country]
            if impact_score != expected_impact:
                violations.append(
                    f"{country}: impact_score {impact_score!r} != "
                    f"slippage_days * forecast_volume ({expected_impact!r})"
                )

    for finding in findings:
        where = finding.get("where", "")
        proof = finding.get("proof", "")
        what = finding.get("what", "<unknown>")

        if not where:
            violations.append(f"finding {what!r} has empty 'where'")
        if "," in where:
            violations.append(f"finding {what!r} 'where' contains a comma: {where!r}")
        if len(proof) > 200:
            violations.append(
                f"finding {what!r} 'proof' exceeds 200 chars ({len(proof)})"
            )

    return violations
