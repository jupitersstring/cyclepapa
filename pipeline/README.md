# cyclepapa pipeline

Scripts that built `fund_activity_last_6mo.xlsx` (455 fund tabs) and
`investment_archetypes.xlsx` (22 analysis sheets), moved out of /tmp so the
work is reproducible.

## Data store

`../data/master_candidates.csv` is the single source of truth for candidates.
Columns separate what previous sheets fused:

- `mcap_recorded` vs `price_recorded` + `price_asof` — frozen claims, dated
- `pct_of_company` vs `pct_of_book` — kept SEPARATE (prior sheets conflated them)
- `verification_status` — VERIFIED_IN_WORKBOOK / PENDING_VERIFY /
  CONFLICT_* / DATA_ERROR_SUSPECTED / RERATED_SUSPECT
- `known_issues` — explicit unresolved problems per row

Rule: a name cannot sit in Tier 1 while `verification_status` is a CONFLICT
or DATA_ERROR state.

## Known systematic flaws in the scan scripts (documented 2026-06-10 audit)

1. `comprehensive_ticker_scan.py` / `scan_insider_v2.py` attribute line-level
   signals to EVERY ticker on the line → mis-attributed percentages
   (the +597% smear across SE/BLDR/ABG/SDRL). Fix: per-cell parsing with
   column schemas, not row-concatenation regex.
2. Section detection requires exact "(1) Highest conviction" headers; tabs
   that deviate scan as empty (OPRX false-negative).
3. NOT_TICKERS blocklists are duplicated across scripts with drift.
4. Agent outputs were freeform text, hand-retyped into dicts. Future: demand
   JSON schema, merge programmatically, auto-detect contradictions.
5. xlsx is a render target, not a database. Edit the CSV, regenerate sheets.

## Refresh order (manual until EDGAR ingestion is built)

1. Update prices/mcaps in master_candidates.csv with as_of dates
2. Re-age catalyst dates; expire passed ones
3. Re-run tier filters off the CSV
4. Regenerate xlsx views
