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
