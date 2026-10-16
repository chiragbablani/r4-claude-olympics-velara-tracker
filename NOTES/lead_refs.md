# Lead Reference Log

Tracking log for questions sent to domain leads and their answers.

| # | Lead | Question | Answer Summary | Lead-Ref Tag |
|---|------|----------|-----------------|--------------|
| 1 | Domain | Do plant/warehouse setup dates gate the demand-load date? | No. Plant and warehouse setup dates do NOT move the effective demand-load date. Use only the 2MG box's recorded demand-load date, or 25 April 2026 if blank on a Direct market. | R4-Q04-dc5b |
| 2 | Domain | What happens when an expected date is before today with no actual shipment? | If an expected date is before 25 April 2026 and no actual shipment is recorded, the real date is at least 25 April 2026. A country with an actual shipment date does not get slippage from a passed expected date. | R4-Q05-floor |
| 3 | Domain | Should we extrapolate date creep trends? | No. Do not extrapolate date creep. Use the single latest expected date and the feasibility calculation only. | R4-Q06-noextrap |
| 4 | Domain | When does ROLLUP_ANY_NOT_ALL apply? | Only where at least one of a country's boxes fails the demand lead-time test and another passes. | R4-Q07-rollup |
| 5 | Domain | Which box determines a country's real ship date? | The 2MG box (every patient starts on 2MG). The real ship date is the latest of the 2MG expected date, its feasible date (demand load + site lead time), and the passed-date floor if triggered. | R4-Q08-2mg |
| 6 | Domain | How is slippage calculated? | Claimed date = earliest Expected Launch Shipment Date across all boxes. Real ship date from the 2MG box. Slippage = max(0, real - claimed). Impact = slippage * forecast volume. Rank by impact desc, ties by slippage desc then name asc. | R4-Q09-slippage |
| 7 | Domain | Via Hub markets with blank setup/demand fields? | Via Hub markets are legitimately blank on setup and demand fields and impose no constraint. No feasibility date is computed for them. | R4-Q10-viahub |
| 8 | Domain | Should DEMAND_NEVER_LOADED be claimed? | Yes, for Direct markets where the demand-loaded flag and the demand-loaded date are both blank in all four monthly copies. Not for Via Hub markets. | R4-Q11-neverloaded |
