# FCF source adjudication — Yahoo vs our measure, referred to audited accounts

Question (user): is it better to use the yfinance figure or our own measure?
Method: audited EDGAR XBRL (us_edgar_yartseva.csv) as ground truth for US
names; Yahoo quoteSummary (ticker_yf.csv) compared per measure. CFO acts as
the CONTROL: it is the same definition in all three sources, so its scatter
isolates freshness/period drift from definition error.

| Measure | n | median yf/audited | within 1.4x | q25 | q75 |
|---|---|---|---|---|---|
| Revenue | 4,252 | 1.049 | 81% | 1.00 | 1.16 |
| EBITDA | 3,613 | 1.101 | 64% | 0.94 | 1.36 |
| CFO (control) | 4,402 | 1.146 | 44% | 0.79 | 1.73 |
| **FCF (contested)** | 2,821 | 0.911 | **30%** | **0.53** | 1.77 |

Conclusion
- Revenue and EBITDA: Yahoo validated (drift is freshness, centred ~1.05-1.10)
  -> Yahoo stays authoritative for level conflicts.
- CFO: same-definition control shows pure freshness scatter -> Yahoo stays
  the conflict-winner for CFO (fresher period, same measure).
- FCF: agreement FAR worse than its own control (30% vs 44%, q25 = 0.53 —
  a quarter of names at HALF the audited value). That is a DEFINITION
  mismatch (Yahoo "levered FCF" formula), not freshness. POLICY: our own
  measure, referred to the underlying accounts — FCF = reconciled CFO minus
  capex (the identity holds exactly on 36k rows) — is PRIMARY; yf_fcf is
  gap-fill only and never conflict-adopted.

## Extension — Yahoo MULTIPLES and FCF YIELD vs EDGAR-implied (US names)

| Ratio | n | median yf/EDGAR-implied | within 1.4x |
|---|---|---|---|
| EV/Sales | 3,978 | 0.956 | 82% (validated) |
| EV/EBITDA | 2,157 | 0.874 | 68% (Yahoo EBITDA ~14% above audited; acceptable, but EDGAR-grounded recompute preferred) |
| **FCF yield** | 2,640 | 0.920 | **29% (unreliable — matches the level study)** |

## Final trust hierarchy (user directive: "EDGAR where possible")
1. AUDITED EDGAR levels (revenue/EBITDA/CFO/FCF/cash/debt/op-margin) are the
   PREFERRED source for US filers — they win every level conflict and ground
   the recomputed multiples. Provenance: qc_flags 'edgar_grounded'.
2. Market data (price/mcap/EV) is always Yahoo (EDGAR has no prices).
3. Non-US names: constructed from Yahoo figures under the full
   internal-identity suite (every ratio == its own components) — the audited
   cross-check is unavailable, so internal consistency is the guard.
4. Yahoo FCF (level or yield) is never conflict-adopted anywhere.

## Direct spot verification vs AUDITED accounts (live XBRL, new TTM method, 2026-09-11)

| Name | Audited TTM CFO | capex | FCF (audited) | Yahoo freeCashflow | yf/audited |
|---|---|---|---|---|---|
| MSFT | 170.1B | 97.2B | **72.9B** | 16.5B | 0.23 |
| AAPL | 146.7B | 10.0B | **136.7B** | 107.7B | 0.79 |
| KSS | 1.4B | 0.3B | **1.0B** | 0.9B | 0.85 |

Even with MSFT's AI-capex surge fully reflected (capex genuinely 97B), Yahoo's
scraped freeCashflow does NOT reproduce the documented CFO-minus-capex formula
against the audited statements. The never-adopt-yf_fcf policy is CONFIRMED by
primary sources.

Additional findings from the spot round:
- Roll-forward ordering bug (fixed): an ANNUAL row newer than every flow row
  must win (MSFT's Jun-2026 FY vs a Mar-2026 roll-forward window).
- FOREIGN PRIVATE ISSUERS (20-F filers, e.g. GASS) file under the ifrs-full
  namespace, invisible to the us-gaap lookup -> their "EDGAR" rows are ancient
  (2013) or missing. The one-quarter freshness gate excludes them from EDGAR
  preference (they fall to Yahoo-constructed, correctly); adding ifrs-full
  coverage is a future extension.
