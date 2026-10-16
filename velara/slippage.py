"""Slippage calculation, per confirmed lead answers (R4-Q04-dc5b and related).

Everything here is derived from the data by rule — no country names are
hardcoded — so it generalizes to other packs with the same shape.

Confirmed rules (see NOTES/lead_refs.md for the lead-ref tags):
- The 2MG box is the "real" signal for a country: every patient starts
  on 2MG, so its shipment date governs. Plant/warehouse setup dates do
  NOT move the demand-load date used here.
- 2MG feasible ship date = 2MG box's recorded Demand Loaded Date, plus
  the packaging site's lead time (Ref_Sites, in weeks, times 7). If the
  demand-load date is blank AND the market is Direct, the load date
  used is TODAY (2026-04-25). Via Hub markets are legitimately blank on
  demand/setup fields and impose no feasibility constraint at all (no
  feasible date is computed for them).
- If the 2MG box's expected shipment date is before TODAY and it has no
  recorded actual shipment date, its real date has a floor of TODAY. A
  box with an actual shipment date recorded gets no such floor.
- Real ship date = max(2MG expected date, 2MG feasible date [if any],
  the passed-date floor [if triggered]).
- Claimed date = earliest Expected Launch Shipment Date across all of
  the country's boxes (not just the 2MG one).
- slippage_days = max(0, real_ship_date - claimed_date). No
  extrapolation of a date-creep trend beyond this.
- impact = slippage_days * forecast_volume (Ref_Countries), counted
  once per country.
- Approval is explicitly not a gate for MTO (make-to-order) markets, so
  approval dates are not part of this calculation.

TODAY is fixed, never read from the system clock, so results are
reproducible and match whatever pack is handed to solve.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .changes import find_column

TODAY = pd.Timestamp("2026-04-25")
STARTING_DOSE = "2MG"


@dataclass
class CountrySlippage:
    country: str
    claimed_date: pd.Timestamp
    expected_2mg_date: pd.Timestamp
    real_ship_date: pd.Timestamp
    slippage_days: int
    forecast_volume: float
    impact_score: float
    driver: str
    evidence: str
    demand_load_date_used: pd.Timestamp | None
    feasible_date: pd.Timestamp | None
    floor_applied: bool
    supply_route: str


def _one_country_slippage(
    country_rows: pd.DataFrame,
    forecast_volume: float,
    lead_time_days: float,
) -> CountrySlippage:
    country = country_rows["Country"].iloc[0]
    exp_col = "Expected Launch Shipment Date"
    claimed_date = country_rows[exp_col].min()

    two_mg_rows = country_rows[country_rows["Dose"] == STARTING_DOSE]
    if len(two_mg_rows) != 1:
        raise ValueError(
            f"expected exactly one {STARTING_DOSE} box for {country!r}, found {len(two_mg_rows)}"
        )
    row = two_mg_rows.iloc[0]

    expected_2mg = row[exp_col]
    demand_load = row["Demand Loaded Date"]
    actual_ship = row["Actual Launch Shipment Date"]
    supply_route = row["Supply Route"]

    demand_load_used: pd.Timestamp | None
    feasible_date: pd.Timestamp | None
    if supply_route == "Via Hub":
        # Via Hub markets are legitimately blank on demand/setup fields;
        # no feasibility constraint applies at all for them.
        demand_load_used = None
        feasible_date = None
    else:
        demand_load_used = demand_load if pd.notna(demand_load) else TODAY
        feasible_date = demand_load_used + pd.Timedelta(days=lead_time_days)

    floor_applied = bool(expected_2mg < TODAY and pd.isna(actual_ship))
    floor_date = TODAY if floor_applied else None

    candidates = [expected_2mg]
    if feasible_date is not None:
        candidates.append(feasible_date)
    if floor_date is not None:
        candidates.append(floor_date)
    real_ship_date = max(candidates)

    slippage_days = max(0, (real_ship_date - claimed_date).days)
    impact_score = slippage_days * forecast_volume

    if slippage_days == 0:
        driver = "NONE"
        evidence = ""
    else:
        # Driver must be one of the allowed finding codes (DATE_PASSED_NO_REPLAN
        # is explicitly excluded, even as a driver tag). DEMAND_LOADED_TOO_LATE
        # applies when the feasible date (demand load + site lead time) is the
        # unique cause pulling the real date past the 2MG box's own expected
        # date; otherwise the 2MG box's own expected date (optionally pushed
        # further by the passed-date floor) is the cause, tagged
        # STARTING_DOSE_UNAVAILABLE since the 2MG box is what's constraining.
        if feasible_date is not None and feasible_date == real_ship_date and feasible_date > expected_2mg:
            driver = "DEMAND_LOADED_TOO_LATE"
            evidence = (
                f"2MG feasible ship {feasible_date.date()} "
                f"(load {demand_load_used.date()} + site lead time) exceeds "
                f"claimed {claimed_date.date()}"
            )[:200]
        elif floor_applied and real_ship_date == floor_date and floor_date > expected_2mg:
            driver = "STARTING_DOSE_UNAVAILABLE"
            evidence = (
                f"2MG expected {expected_2mg.date()} already passed TODAY "
                f"with no actual shipment recorded; floored to {TODAY.date()}"
            )[:200]
        else:
            driver = "STARTING_DOSE_UNAVAILABLE"
            evidence = (
                f"2MG expected {expected_2mg.date()} later than country's "
                f"earliest claimed date {claimed_date.date()}"
            )[:200]

    return CountrySlippage(
        country=country,
        claimed_date=claimed_date,
        expected_2mg_date=expected_2mg,
        real_ship_date=real_ship_date,
        slippage_days=slippage_days,
        forecast_volume=forecast_volume,
        impact_score=impact_score,
        driver=driver,
        evidence=evidence,
        demand_load_date_used=demand_load_used,
        feasible_date=feasible_date,
        floor_applied=floor_applied,
        supply_route=supply_route,
    )


def compute_slippage(
    latest_month_df: pd.DataFrame,
    ref_countries: pd.DataFrame,
    ref_sites: pd.DataFrame,
) -> dict[str, CountrySlippage]:
    """Compute per-country slippage from the latest (April) monthly sheet.

    Returns {country_name: CountrySlippage}, one entry per country found
    in latest_month_df. Raises ValueError if a country doesn't have
    exactly one 2MG row, since the rule depends on that box existing.
    """
    country_col = find_column(latest_month_df, "Country")
    site_col = find_column(latest_month_df, "Packaging Site")

    lead_time_weeks = ref_sites.set_index(find_column(ref_sites, "Packaging Site"))[
        find_column(ref_sites, "Lead Time From Demand Load To Shipment (weeks)")
    ]
    forecast_volume_col = find_column(ref_countries, "Forecast Volume Year 1 (units)")
    ref_country_col = find_column(ref_countries, "Country")
    forecast_by_country = ref_countries.set_index(
        ref_countries[ref_country_col].str.strip().str.lower()
    )[forecast_volume_col]

    results: dict[str, CountrySlippage] = {}
    grouped = latest_month_df.groupby(latest_month_df[country_col].str.strip().str.lower())
    for country_norm, rows in grouped:
        site = rows[site_col].iloc[0]
        lead_time_days = lead_time_weeks.get(site, 0) * 7
        forecast_volume = forecast_by_country.get(country_norm, 0)
        results[country_norm] = _one_country_slippage(rows, forecast_volume, lead_time_days)

    return results
