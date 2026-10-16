"""Slippage calculation (stub).

Intended to compute, per country, how many days a milestone or launch
has slipped relative to plan, and the resulting impact_score
(slippage_days * forecast_volume per the output contract).

Not implemented: the definition of "slipped", which date columns are
plan vs actual, and where forecast_volume comes from are all unconfirmed
domain questions. See NOTES/lead_refs.md.
"""
from __future__ import annotations

from .loading import LoadedPack


def compute_slippage(pack: LoadedPack) -> dict[str, dict]:
    """Compute per-country slippage_days, impact_score, driver, evidence.

    Stub: not implemented. Raises NotImplementedError until slippage
    rules are confirmed with domain leads.
    """
    raise NotImplementedError("slippage calculation is not yet defined")
