"""Rule checks (findings detection).

Confirmed finding codes and their exclusions — see NOTES/lead_refs.md
for the lead-ref tags. Only these codes are claimed; no others.
"""
from __future__ import annotations

import re
import sys

import pandas as pd

from .changes import find_column
from .loading import LoadedPack
from .slippage import TODAY

MONTH_PATTERN = re.compile(r"^Tracker_\d{4}_\d{2}$", re.IGNORECASE)


def _get_monthly_sheets(pack: LoadedPack) -> list[tuple[str, pd.DataFrame]]:
    return sorted(
        [(n, df) for n, df in pack.tracker_sheets.items() if MONTH_PATTERN.match(n)],
        key=lambda x: x[0],
    )


def _clean_country(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def _countries_str(countries: set[str] | list[str]) -> str:
    return ";".join(sorted(countries))


def _trim(proof: str) -> str:
    return proof[:200]


def run_all_rules(pack: LoadedPack) -> list[dict]:
    findings: list[dict] = []
    monthly = _get_monthly_sheets(pack)
    latest_name, latest = monthly[-1]
    ref_countries = pack.tracker_sheets.get("Ref_Countries")
    ref_skus = pack.tracker_sheets.get("Ref_SKUs")
    ref_sites = pack.tracker_sheets.get("Ref_Sites")
    if ref_countries is None or ref_skus is None or ref_sites is None:
        print("WARNING: missing Ref sheets", file=sys.stderr)
        return findings

    ref_sku_set = set(ref_skus[find_column(ref_skus, "SKU")].str.strip())
    lead_time_weeks = ref_sites.set_index(
        find_column(ref_sites, "Packaging Site")
    )[find_column(ref_sites, "Lead Time From Demand Load To Shipment (weeks)")]

    # -- APPROVAL_BEFORE_SUBMISSION (National only) --
    countries: set[str] = set()
    for _, df in monthly:
        m = (
            df["Actual Approval Date"].notna()
            & df["Actual Submission Date"].notna()
            & (df["Actual Approval Date"] < df["Actual Submission Date"])
            & (df["Regulatory Pathway"] == "National")
        )
        countries |= set(_clean_country(df.loc[m, "Country"]))
    if countries:
        findings.append({
            "what": "APPROVAL_BEFORE_SUBMISSION",
            "where": _countries_str(countries),
            "proof": _trim("Actual Approval Date < Actual Submission Date on National pathway rows"),
        })

    # -- APPROVAL_TARGET_NOT_ACTUAL --
    m = (latest["Target Approval Date"] < TODAY) & latest["Actual Approval Date"].isna()
    countries = set(_clean_country(latest.loc[m, "Country"]))
    if countries:
        findings.append({
            "what": "APPROVAL_TARGET_NOT_ACTUAL",
            "where": _countries_str(countries),
            "proof": _trim(f"Target Approval Date before {TODAY.date()} with Actual Approval Date still blank"),
        })

    # -- COUNTRY_NAME_WHITESPACE --
    countries = set()
    for _, df in monthly:
        raw = df["Country"]
        hit = raw[raw != raw.str.strip()]
        if not hit.empty:
            countries |= set(hit.str.strip())
    if countries:
        findings.append({
            "what": "COUNTRY_NAME_WHITESPACE",
            "where": _countries_str(countries),
            "proof": _trim("Country values with leading/trailing whitespace found across monthly tabs"),
        })

    # -- DATE_MOVED_WITHOUT_RECORD --
    moved_countries: set[str] = set()
    for (name_a, df_a), (name_b, df_b) in zip(monthly, monthly[1:]):
        keys_a = {}
        for _, row in df_a.iterrows():
            k = (str(row["Country"]).strip().lower(), str(row["SKU"]).strip())
            keys_a[k] = (row["Expected Launch Shipment Date"], row.get("Shipment Date Change Log"))
        for _, row in df_b.iterrows():
            k = (str(row["Country"]).strip().lower(), str(row["SKU"]).strip())
            if k not in keys_a:
                continue
            exp_a, _ = keys_a[k]
            exp_b = row["Expected Launch Shipment Date"]
            log_b = row.get("Shipment Date Change Log")
            if pd.isna(exp_a) or pd.isna(exp_b):
                continue
            if exp_a != exp_b:
                has_log = isinstance(log_b, str) and log_b.strip() != ""
                if not has_log:
                    moved_countries.add(str(row["Country"]).strip())
    if moved_countries:
        findings.append({
            "what": "DATE_MOVED_WITHOUT_RECORD",
            "where": _countries_str(moved_countries),
            "proof": _trim("Expected Launch Shipment Date changed between months with no Shipment Date Change Log entry"),
        })

    # -- DATE_STORED_AS_NUMBER --
    serial_col_names = sorted({col for _, col in pack.serial_date_columns})
    if serial_col_names:
        findings.append({
            "what": "DATE_STORED_AS_NUMBER",
            "where": ";".join(serial_col_names),
            "proof": _trim(
                f"Column(s) loaded as integer serial dates in sheet(s): "
                f"{sorted({s for s, _ in pack.serial_date_columns})}"
            ),
        })

    # -- DEMAND_LOADED_TOO_LATE (Direct only) --
    countries = set()
    for _, df in monthly:
        lt = df["Packaging Site"].map(lead_time_weeks)
        gap_days = (df["Expected Launch Shipment Date"] - df["Demand Loaded Date"]).dt.days
        required_days = lt * 7
        m = (
            df["Demand Loaded Date"].notna()
            & df["Expected Launch Shipment Date"].notna()
            & (gap_days < required_days)
            & (df["Supply Route"] == "Direct")
        )
        countries |= set(_clean_country(df.loc[m, "Country"]))
    if countries:
        findings.append({
            "what": "DEMAND_LOADED_TOO_LATE",
            "where": _countries_str(countries),
            "proof": _trim("Demand Loaded Date to Expected Launch Shipment Date gap is less than site lead time; Direct markets only"),
        })

    # -- DEMAND_NEVER_LOADED (Direct only, blank flag and date in ALL four months) --
    demand_blank_by_key: dict[tuple[str, str], int] = {}
    for _, df in monthly:
        for _, row in df.iterrows():
            k = (str(row["Country"]).strip().lower(), str(row["SKU"]).strip())
            flag = row.get("Demand Loaded In Planning System?")
            date = row.get("Demand Loaded Date")
            supply = row.get("Supply Route")
            if supply != "Direct":
                continue
            if pd.isna(flag) and pd.isna(date):
                demand_blank_by_key[k] = demand_blank_by_key.get(k, 0) + 1
    never_loaded_countries: set[str] = set()
    for (country_norm, sku), count in demand_blank_by_key.items():
        if count == len(monthly):
            for _, df in monthly:
                hit = df[
                    (df["Country"].astype(str).str.strip().str.lower() == country_norm)
                    & (df["SKU"].astype(str).str.strip() == sku)
                ]
                if not hit.empty:
                    never_loaded_countries.add(hit["Country"].iloc[0].strip())
                    break
    if never_loaded_countries:
        findings.append({
            "what": "DEMAND_NEVER_LOADED",
            "where": _countries_str(never_loaded_countries),
            "proof": _trim("Demand Loaded flag and date both blank in all four months; Direct markets only"),
        })

    # -- DUPLICATE_ROW --
    dup_countries: set[str] = set()
    for name, df in monthly:
        keys = (
            df["Country"].astype(str).str.strip().str.lower()
            + "||"
            + df["SKU"].astype(str).str.strip()
        )
        duped = keys[keys.duplicated(keep=False)]
        if not duped.empty:
            for idx in duped.index:
                dup_countries.add(str(df.loc[idx, "Country"]).strip())
    if dup_countries:
        findings.append({
            "what": "DUPLICATE_ROW",
            "where": _countries_str(dup_countries),
            "proof": _trim("Same Country and SKU appears more than once in a single monthly tab"),
        })

    # -- FLAG_YES_BUT_NO_DATE (Direct only) --
    flag_date_pairs = [
        ("Product Code Set Up At Plant?", "Plant Setup Date"),
        ("Product Code Set Up At Warehouse?", "Warehouse Setup Date"),
        ("Demand Loaded In Planning System?", "Demand Loaded Date"),
    ]
    countries = set()
    for flagcol, datecol in flag_date_pairs:
        m = (
            (latest[flagcol] == "Yes")
            & latest[datecol].isna()
            & (latest["Supply Route"] == "Direct")
        )
        countries |= set(_clean_country(latest.loc[m, "Country"]))
    if countries:
        findings.append({
            "what": "FLAG_YES_BUT_NO_DATE",
            "where": _countries_str(countries),
            "proof": _trim("Readiness flag is Yes but corresponding date field is blank; Direct markets only"),
        })

    # -- SETUP_DATE_AFTER_SHIPMENT (Primary and not MTO only) --
    countries = set()
    for _, df in monthly:
        for setupcol in ["Plant Setup Date", "Warehouse Setup Date"]:
            m = (
                df[setupcol].notna()
                & df["Expected Launch Shipment Date"].notna()
                & (df[setupcol] > df["Expected Launch Shipment Date"])
                & (df["Site Role"] == "Primary")
                & (df["Demand Strategy"] != "MTO")
            )
            countries |= set(_clean_country(df.loc[m, "Country"]))
    if countries:
        findings.append({
            "what": "SETUP_DATE_AFTER_SHIPMENT",
            "where": _countries_str(countries),
            "proof": _trim("Plant or Warehouse Setup Date after Expected Launch Shipment Date; Primary site; not MTO"),
        })

    # -- SKU_NOT_IN_REFERENCE --
    countries = set()
    skus_missing: set[str] = set()
    for _, df in monthly:
        m = ~df["SKU"].str.strip().isin(ref_sku_set)
        if m.any():
            countries |= set(_clean_country(df.loc[m, "Country"]))
            skus_missing |= set(df.loc[m, "SKU"].str.strip())
    if countries:
        findings.append({
            "what": "SKU_NOT_IN_REFERENCE",
            "where": _countries_str(countries),
            "proof": _trim(f"SKU(s) {sorted(skus_missing)} not found in Ref_SKUs"),
        })

    # -- STATUS_INVALID_ENTRY --
    valid_status = {"active"}
    countries = set()
    for _, df in monthly:
        m = ~df["Launch Status"].str.strip().str.lower().isin(valid_status)
        countries |= set(_clean_country(df.loc[m, "Country"]))
    if countries:
        findings.append({
            "what": "STATUS_INVALID_ENTRY",
            "where": _countries_str(countries),
            "proof": _trim("Launch Status contains a value that is not a recognized status (e.g. 'Invalid Entry')"),
        })

    # -- STATUS_VALUE_DRIFT --
    # Only report countries whose own rows carry a non-canonical spelling of
    # a status that also appears under a different spelling elsewhere.
    canonical_by_norm: dict[str, str] = {}
    all_raw_by_norm: dict[str, set[str]] = {}
    for _, df in monthly:
        for raw in df["Launch Status"].unique():
            norm = raw.strip().lower()
            all_raw_by_norm.setdefault(norm, set()).add(raw)
            if norm not in canonical_by_norm:
                canonical_by_norm[norm] = raw
    drifted_norms = {norm for norm, variants in all_raw_by_norm.items() if len(variants) > 1}
    if drifted_norms:
        countries_with_drift: set[str] = set()
        for _, df in monthly:
            for _, row in df.iterrows():
                raw_status = row["Launch Status"]
                norm = raw_status.strip().lower()
                if norm not in drifted_norms:
                    continue
                canonical = canonical_by_norm[norm]
                if raw_status != canonical:
                    countries_with_drift.add(str(row["Country"]).strip())
        if countries_with_drift:
            findings.append({
                "what": "STATUS_VALUE_DRIFT",
                "where": _countries_str(countries_with_drift),
                "proof": _trim(f"Launch Status spelled inconsistently: {all_raw_by_norm}"),
            })

    # -- STARTING_DOSE_UNAVAILABLE --
    # The 2MG box's expected date is later than the country's earliest box
    countries = set()
    for _, df in monthly:
        grouped = df.groupby(df["Country"].astype(str).str.strip().str.lower())
        for country_norm, grp in grouped:
            earliest = grp["Expected Launch Shipment Date"].min()
            two_mg = grp[grp["Dose"] == "2MG"]
            if two_mg.empty:
                countries.add(grp["Country"].iloc[0].strip())
                continue
            two_mg_date = two_mg["Expected Launch Shipment Date"].iloc[0]
            if two_mg_date > earliest:
                countries.add(grp["Country"].iloc[0].strip())
    if countries:
        findings.append({
            "what": "STARTING_DOSE_UNAVAILABLE",
            "where": _countries_str(countries),
            "proof": _trim("2MG box expected shipment date is later than the country's earliest box date"),
        })

    # -- PLANT_CAPACITY_EXCEEDED --
    fv_col = find_column(ref_countries, "Forecast Volume Year 1 (units)")
    ps_col = find_column(ref_countries, "Packaging Site")
    rc_col = find_column(ref_countries, "Country")
    cap_col = find_column(ref_sites, "Annual Packaging Capacity (units)")
    site_demand = ref_countries.groupby(ps_col)[fv_col].sum()
    cap = ref_sites.set_index(find_column(ref_sites, "Packaging Site"))[cap_col]
    for site, demand in site_demand.items():
        capacity = cap.get(site)
        if capacity is not None and demand > capacity:
            countries_at_site = ref_countries[ref_countries[ps_col] == site][rc_col].str.strip().tolist()
            findings.append({
                "what": "PLANT_CAPACITY_EXCEEDED",
                "where": _countries_str(set(countries_at_site)),
                "proof": _trim(f"Site {site}: total forecast {demand} > annual capacity {capacity}"),
            })

    # -- BLANK_TREATED_AS_PASS (Direct only, blank in ALL four months) --
    flag_cols = [
        "Product Code Set Up At Plant?",
        "Demand Loaded In Planning System?",
    ]
    blank_all_months: dict[tuple[str, str, str], int] = {}
    for _, df in monthly:
        for _, row in df.iterrows():
            if row["Supply Route"] != "Direct":
                continue
            k_base = (str(row["Country"]).strip().lower(), str(row["SKU"]).strip())
            for fc in flag_cols:
                k = k_base + (fc,)
                if pd.isna(row[fc]):
                    blank_all_months[k] = blank_all_months.get(k, 0) + 1
    countries = set()
    for (country_norm, sku, fc), count in blank_all_months.items():
        if count == len(monthly):
            for _, df in monthly:
                hit = df[
                    (df["Country"].astype(str).str.strip().str.lower() == country_norm)
                    & (df["SKU"].astype(str).str.strip() == sku)
                ]
                if not hit.empty:
                    countries.add(hit["Country"].iloc[0].strip())
                    break
    if countries:
        findings.append({
            "what": "BLANK_TREATED_AS_PASS",
            "where": _countries_str(countries),
            "proof": _trim("Readiness flag blank (not No) in all four months; Direct markets only"),
        })

    # -- SHIPMENT_BEFORE_APPROVAL (NOT MTO, expected ship < target approval, no actual approval) --
    countries = set()
    for _, df in monthly:
        m = (
            df["Expected Launch Shipment Date"].notna()
            & df["Target Approval Date"].notna()
            & (df["Expected Launch Shipment Date"] < df["Target Approval Date"])
            & df["Actual Approval Date"].isna()
            & (df["Demand Strategy"] != "MTO")
        )
        countries |= set(_clean_country(df.loc[m, "Country"]))
    if countries:
        findings.append({
            "what": "SHIPMENT_BEFORE_APPROVAL",
            "where": _countries_str(countries),
            "proof": _trim("Expected shipment before target approval date and no actual approval; not MTO"),
        })

    # -- ROLLUP_ANY_NOT_ALL --
    # Only where at least one box fails the demand lead-time test and another passes
    countries = set()
    df = latest
    lt = df["Packaging Site"].map(lead_time_weeks)
    gap_days = (df["Expected Launch Shipment Date"] - df["Demand Loaded Date"]).dt.days
    required_days = lt * 7
    df_test = df.copy()
    df_test["lt_fail"] = (
        df_test["Demand Loaded Date"].notna()
        & df_test["Expected Launch Shipment Date"].notna()
        & (gap_days < required_days)
    )
    df_test["lt_pass"] = (
        df_test["Demand Loaded Date"].notna()
        & df_test["Expected Launch Shipment Date"].notna()
        & (gap_days >= required_days)
    )
    grouped = df_test.groupby(df_test["Country"].astype(str).str.strip().str.lower())
    for country_norm, grp in grouped:
        if grp["lt_fail"].any() and grp["lt_pass"].any():
            countries.add(grp["Country"].iloc[0].strip())
    if countries:
        findings.append({
            "what": "ROLLUP_ANY_NOT_ALL",
            "where": _countries_str(countries),
            "proof": _trim("At least one box fails the demand lead-time test while another passes in the same country"),
        })

    return findings
