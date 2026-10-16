"""Rule checks (findings detection).

Each rule inspects the loaded pack and, if triggered, produces a finding
dict shaped like:

    {"what": CODE, "where": "Country1;Country2", "proof": "<=200 chars"}

CODE values and the conditions that trigger them are intentionally left
undefined. None of the "what are we checking for" questions have been
answered by domain leads yet, so no rule logic is implemented here.
Hardcoding guessed thresholds or category values would bake in
unconfirmed assumptions. See NOTES/lead_refs.md to track open questions.

RULES is the registry future rule functions should register into. Each
entry is a callable with signature (loaded_pack) -> list[dict], matching
the finding shape above.
"""
from __future__ import annotations

from collections.abc import Callable

from .loading import LoadedPack

RuleFunc = Callable[[LoadedPack], list[dict]]

RULES: list[RuleFunc] = []


def run_all_rules(pack: LoadedPack) -> list[dict]:
    """Run every registered rule and flatten their findings.

    Returns an empty list until rules are implemented and registered.
    """
    findings: list[dict] = []
    for rule in RULES:
        findings.extend(rule(pack))
    return findings
