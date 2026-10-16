#!/usr/bin/env python3
"""Entry point: python3 solve.py <pack_dir>

Prints exactly one JSON object to stdout. All diagnostics go to stderr.
On any internal error, prints a best-effort fallback JSON so stdout is
never empty or malformed.
"""
from __future__ import annotations

import json
import re
import sys
import traceback

import pandas as pd

from velara.countries import extract_country_values
from velara.loading import load_pack
from velara.paths import resolve_pack_paths
from velara.ranking import build_clean_ranking, build_payload, build_risk_ranking
from velara.rules import run_all_rules
from velara.slippage import compute_slippage
from velara.validation import validate_contract

MONTH_PATTERN = re.compile(r"^Tracker_\d{4}_\d{2}$", re.IGNORECASE)


def _fallback_payload(countries: list[str], error_note: str) -> dict:
    ranking = build_clean_ranking(countries)
    for row in ranking:
        row["evidence"] = f"solve.py error: {error_note}"
    return build_payload(findings=[], risk_ranking=ranking)


def _discover_countries(pack_dir: str) -> list[str]:
    paths = resolve_pack_paths(pack_dir)
    pack = load_pack(paths["tracker"], paths["dashboard"])
    frames = list(pack.tracker_sheets.values()) + [pack.dashboard]
    return extract_country_values(frames)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 solve.py <pack_dir>", file=sys.stderr)
        return 2

    pack_dir = sys.argv[1]
    countries: list[str] = []

    try:
        countries = _discover_countries(pack_dir)

        paths = resolve_pack_paths(pack_dir)
        pack = load_pack(paths["tracker"], paths["dashboard"])

        ref_countries = pack.tracker_sheets.get("Ref_Countries")
        ref_sites = pack.tracker_sheets.get("Ref_Sites")

        monthly_names = sorted(
            n for n in pack.tracker_sheets if MONTH_PATTERN.match(n)
        )
        latest = pack.tracker_sheets[monthly_names[-1]]

        slippage = compute_slippage(latest, ref_countries, ref_sites)
        risk_ranking = build_risk_ranking(slippage)

        findings = run_all_rules(pack)

        forecast_by_country = {}
        if ref_countries is not None:
            for _, row in ref_countries.iterrows():
                c = str(row["Country"]).strip()
                forecast_by_country[c] = row["Forecast Volume Year 1 (units)"]

        payload = build_payload(findings=findings, risk_ranking=risk_ranking)

        violations = validate_contract(
            findings, risk_ranking, countries,
            forecast_volume_by_country=forecast_by_country,
        )
        if violations:
            print("output contract violations:", file=sys.stderr)
            for v in violations:
                print(f"  - {v}", file=sys.stderr)

        print(json.dumps(payload))
        return 0

    except Exception as exc:
        traceback.print_exc(file=sys.stderr)

        if not countries:
            try:
                countries = _discover_countries(pack_dir)
            except Exception:
                countries = []
                print(
                    "could not discover any countries from the pack; "
                    "fallback risk_ranking will be empty",
                    file=sys.stderr,
                )

        payload = _fallback_payload(countries, str(exc))
        print(json.dumps(payload))
        return 1


if __name__ == "__main__":
    sys.exit(main())
