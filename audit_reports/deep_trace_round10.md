# Deep trace round 9 — every figure, source -> stored (2026-09-12)

## JPM (USD/USD, bridge=1) — 4 issue(s), 20 figures clean
  - warn price: stored 329.1 vs fresh 353.6 (dev 7%)
  - warn market_cap: stored 8.817e+11 vs fresh 9.398e+11 (dev 6%)
  - ERR  cash: stored 3.121e+11 vs fresh 1.526e+12 (dev 80%)
  - ERR  total_debt: stored 7.243e+10 vs fresh 1.343e+12 (dev 95%)

## AAPL (USD/USD, bridge=1) — 0 issue(s), 24 figures clean

## 7203.T (JPY/JPY, bridge=1) — 2 issue(s), 22 figures clean
  - warn ebitda_ttm: stored 7.632e+12 vs fresh 5.601e+12 (dev 36%)
  - warn cfo_ttm: stored 5.473e+12 vs fresh 4.133e+12 (dev 32%)

## 0700.HK (HKD/CNY, bridge=1) — 0 issue(s), 24 figures clean

## HRMY (USD/USD, bridge=1) — 0 issue(s), 23 figures clean

## TASK (USD/USD, bridge=1) — 3 issue(s), 20 figures clean
  - ERR  shares: stored 9.169e+07 vs fresh 3.665e+07 (dev 150%)
  - warn ebitda_margin: 0.183 vs comp 0.1499
  - warn fcf=cfo-capex: 1.439e+08 vs comp 1.247e+08

## JUP.L (GBp/GBP, bridge=1) — 0 issue(s), 24 figures clean

## ALNPY (USD/JPY, bridge=0.006234) — 1 issue(s), 23 figures clean
  - warn ebitda_margin: 0.1643 vs comp 0.142

## 600841.SS (CNY/CNY, bridge=1) — 2 issue(s), 21 figures clean
  - warn shares: stored 1.388e+09 vs fresh 1.043e+09 (dev 33%)
  - ERR  cfo_ttm: stored 8.878e+08 vs fresh 5.56e+08 (dev 60%)

## TNHDF (USD/CNY, bridge=1) — 1 issue(s), 22 figures clean
  - warn ebitda_ttm: stored 9.553e+07 vs fresh 6.842e+07 (dev 40%)

## RALLIS.NS (INR/INR, bridge=1) — 3 issue(s), 21 figures clean
  - warn p_s: 1.355 vs comp 1.628
  - warn fcf_yield: 0.02621 vs comp 0.03164
  - warn net_margin: 0.06348 vs comp 0.08675

## GAW.L (GBp/GBP, bridge=1) — 0 issue(s), 24 figures clean


**TOTAL: 284 figure checks, 4 ERROR, 12 warn**
## Adjudication (round 10 final)
- JPM cash/debt vs fresh: FINANCIAL-INSTITUTION basis — Yahoo's
  totalCash/totalDebt for banks include deposits and wholesale funding
  (~$1.5T); the audited narrower concepts are the coherent measure for
  this pipeline and financials are excluded from the operating gates.
- TASK shares: DUAL-CLASS — Yahoo reports Class-A count (36.6M), ours is
  the mcap/price-implied all-class equivalent (91.7M); the mcap identity
  holds exactly. Same documented basis as the B-share class.
- 600841.SS cfo: statement-window TTM vs snapshot (statement preferred
  by validated doctrine).
- ERIXF (crosscheck) and HGIT (snapshot-only REIT remnant): the two
  known pendings — both heal at the running concepts re-map / full
  fetch merge.
ZERO new defect classes. Headline finding of this round was the
NON-COMMON SECURITIES class (user-caught: "JPM pe 1.5"): preferred
series, ETNs, warrants, units and rights inherit ISSUER financials
from the SEC ticker map and Yahoo, printing fake deep value (JPM
preferreds at 0.7-1.7x "earnings", 0.13x "book"; the AMJB ETN at
exactly 1.52x). 1,209 such securities now carry noncommon_security
and have issuer fundamentals + valuation ratios nulled — price-only
rows, unable to fire any gate. JPM common, both Google classes and
common ADS verified untouched. Fresh 3-per-archetype sweep (seed 42,
264 firers): 2 ERROR (both the known pendings above), rest documented
classes.
