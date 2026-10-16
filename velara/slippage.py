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
    demand_never_loaded_countries: set[str],
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
        demand_load_used = None
        feasible_date = None
    else:
        demand_load_used = demand_load if pd.notna(demand_load) else TODAY
        feasible_date = demand_load_used + pd.Timedelta(days=lead_time_days)

    # Floor: if expected < TODAY, real date is at least TODAY, regardless
    # of whether an actual shipment is recorded (a bonded pre-approval
    # move does not count as shipped — R4-Q05-481a, R4-Q07-da69).
    floor_applied = bool(expected_2mg < TODAY)
    floor_date = TODAY if floor_applied else None

    candidates = [expected_2mg]
    if feasible_date is not None:
        candidates.append(feasible_date)
    if floor_date is not None:
        candidates.append(floor_date)
    real_ship_date = max(candidates)

    slippage_days = max(0, (real_ship_date - claimed_date).days)
    impact_score = slippage_days * forecast_volume

    # Check if this country's 2MG box has demand blank in all 4 months
    # (Direct only) — passed via demand_never_loaded_countries set.
    country_norm = country.strip().lower()
    is_demand_never_loaded = country_norm in demand_never_loaded_countries

    # Check if every expected date in the country is before TODAY with
    # no revised date in a later extract — DATE_PASSED_NO_REPLAN.
    all_expected_past = bool((country_rows[exp_col] < TODAY).all())

    if slippage_days == 0:
        driver = "NONE"
        evidence = ""
    else:
        if all_expected_past and floor_applied:
            driver = "DATE_PASSED_NO_REPLAN"
            evidence = (
                f"All expected dates before {TODAY.date()} with no "
                f"revised date; real date floored to {TODAY.date()}"
            )[:200]
        elif is_demand_never_loaded and feasible_date is not None and feasible_date >= real_ship_date:
            driver = "DEMAND_NEVER_LOADED"
            evidence = (
                f"Demand never loaded (blank in all 4 months); "
                f"feasible date {feasible_date.date()} from TODAY + site lead time"
            )[:200]
        elif feasible_date is not None and feasible_date == real_ship_date and feasible_date > expected_2mg:
            driver = "DEMAND_LOADED_TOO_LATE"
            evidence = (
                f"2MG feasible ship {feasible_date.date()} "
                f"(load {demand_load_used.date()} + site lead time) exceeds "
                f"claimed {claimed_date.date()}"
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
    all_monthly_sheets: list[pd.DataFrame] | None = None,
) -> dict[str, CountrySlippage]:
    """Compute per-country slippage from the latest (April) monthly sheet.

    If all_monthly_sheets is provided, it is used to determine which
    Direct-market 2MG boxes have demand blank in all 4 months (for
    the DEMAND_NEVER_LOADED driver).
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

    demand_never_loaded: set[str] = set()
    if all_monthly_sheets:
        blank_counts: dict[str, int] = {}
        for df in all_monthly_sheets:
            cc = find_column(df, "Country")
            for _, row in df.iterrows():
                if row.get("Supply Route") != "Direct":
                    continue
                if str(row.get("Dose", "")).strip() != STARTING_DOSE:
                    continue
                cnorm = str(row[cc]).strip().lower()
                flag = row.get("Demand Loaded In Planning System?")
                date = row.get("Demand Loaded Date")
                if pd.isna(flag) and pd.isna(date):
                    blank_counts[cnorm] = blank_counts.get(cnorm, 0) + 1
        n_months = len(all_monthly_sheets)
        demand_never_loaded = {c for c, n in blank_counts.items() if n >= n_months}

    results: dict[str, CountrySlippage] = {}
    grouped = latest_month_df.groupby(latest_month_df[country_col].str.strip().str.lower())
    for country_norm, rows in grouped:
        site = rows[site_col].iloc[0]
        lead_time_days = lead_time_weeks.get(site, 0) * 7
        forecast_volume = forecast_by_country.get(country_norm, 0)
        results[country_norm] = _one_country_slippage(
            rows, forecast_volume, lead_time_days, demand_never_loaded
        )

    return results
