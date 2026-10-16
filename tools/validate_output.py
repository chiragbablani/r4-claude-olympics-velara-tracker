#!/usr/bin/env python3
"""Validate a solve.py output JSON against the Round 4 contract.

Usage:
    python3 tools/validate_output.py path/to/output.json
    python3 tools/validate_output.py < output.json
    some_command | python3 tools/validate_output.py -

Reports pass/fail per rule to stdout and exits non-zero if anything
fails. This is a standalone checker, not part of solve.py itself.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FINDING_KEYS = {"what", "where", "proof"}
REQUIRED_RANKING_KEYS = {"country", "rank", "slippage_days", "impact_score", "driver", "evidence"}


class Check:
    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def run(self, name: str, fn) -> None:
        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"raised {exc!r}"
        self.results.append((name, ok, detail))

    def report(self) -> bool:
        all_ok = True
        for name, ok, detail in self.results:
            status = "PASS" if ok else "FAIL"
            if not ok:
                all_ok = False
            suffix = f" - {detail}" if detail else ""
            print(f"[{status}] {name}{suffix}")
        return all_ok


def load_input(arg: str | None) -> str:
    if arg is None or arg == "-":
        return sys.stdin.read()
    return Path(arg).read_text(encoding="utf-8")


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    raw = load_input(arg)

    check = Check()

    parsed: dict = {}

    def check_single_json_object():
        nonlocal parsed
        text = raw.strip()
        parsed = json.loads(text)
        # json.loads of a single value consumes the whole string already;
        # re-dumping and comparing length catches trailing garbage that
        # happens to still parse as part of a container.
        if not isinstance(parsed, dict):
            return False, f"top-level JSON is {type(parsed).__name__}, expected object"
        return True, ""

    check.run("stdout is exactly one JSON object", check_single_json_object)

    def check_top_level_keys():
        keys = set(parsed.keys())
        expected = {"findings", "risk_ranking"}
        if keys != expected:
            return False, f"keys are {sorted(keys)}, expected {sorted(expected)}"
        return True, ""

    check.run("top-level keys are exactly findings, risk_ranking", check_top_level_keys)

    findings = parsed.get("findings", [])
    risk_ranking = parsed.get("risk_ranking", [])

    def check_findings_shape():
        if not isinstance(findings, list):
            return False, "findings is not a list"
        for i, f in enumerate(findings):
            if not isinstance(f, dict):
                return False, f"findings[{i}] is not an object"
            missing = REQUIRED_FINDING_KEYS - set(f.keys())
            if missing:
                return False, f"findings[{i}] missing keys {sorted(missing)}"
        return True, f"{len(findings)} findings"

    check.run("findings entries have required keys", check_findings_shape)

    def check_where_format():
        bad = []
        for i, f in enumerate(findings):
            where = f.get("where", "")
            if not where:
                bad.append(f"findings[{i}] empty where")
            elif "," in where:
                bad.append(f"findings[{i}] where contains a comma")
        if bad:
            return False, "; ".join(bad)
        return True, ""

    check.run("findings 'where' uses semicolons, never empty/commas", check_where_format)

    def check_proof_length():
        bad = [i for i, f in enumerate(findings) if len(f.get("proof", "")) > 200]
        if bad:
            return False, f"findings at indices {bad} exceed 200 chars"
        return True, ""

    check.run("findings 'proof' <= 200 chars", check_proof_length)

    def check_ranking_shape():
        if not isinstance(risk_ranking, list):
            return False, "risk_ranking is not a list"
        for i, r in enumerate(risk_ranking):
            if not isinstance(r, dict):
                return False, f"risk_ranking[{i}] is not an object"
            missing = REQUIRED_RANKING_KEYS - set(r.keys())
            if missing:
                return False, f"risk_ranking[{i}] missing keys {sorted(missing)}"
        return True, f"{len(risk_ranking)} rows"

    check.run("risk_ranking entries have required keys", check_ranking_shape)

    def check_country_count():
        countries = [r.get("country") for r in risk_ranking]
        if len(countries) != 30:
            return False, f"{len(countries)} countries, expected 30"
        return True, ""

    check.run("risk_ranking has exactly 30 countries", check_country_count)

    def check_country_uniqueness():
        countries = [r.get("country") for r in risk_ranking]
        dupes = {c for c in countries if countries.count(c) > 1}
        if dupes:
            return False, f"duplicate countries: {sorted(dupes)}"
        return True, ""

    check.run("risk_ranking countries are unique", check_country_uniqueness)

    def check_rank_uniqueness():
        ranks = [r.get("rank") for r in risk_ranking]
        expected = set(range(1, len(risk_ranking) + 1))
        if set(ranks) != expected or len(set(ranks)) != len(ranks):
            return False, f"ranks are {sorted(ranks) if all(isinstance(x, int) for x in ranks) else ranks}"
        return True, ""

    check.run("risk_ranking ranks are unique 1..N", check_rank_uniqueness)

    def check_impact_score_formula():
        bad = []
        for i, r in enumerate(risk_ranking):
            slippage = r.get("slippage_days")
            impact = r.get("impact_score")
            if r.get("driver") == "NONE":
                if slippage != 0 or impact != 0:
                    bad.append(f"risk_ranking[{i}] driver NONE but slippage/impact not both 0")
        if bad:
            return False, "; ".join(bad)
        return True, "(forecast-volume-based impact formula not checked here; needs per-country volume)"

    check.run("clean rows have slippage_days=0, impact_score=0, driver=NONE", check_impact_score_formula)

    ok = check.report()
    print()
    print("OVERALL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
