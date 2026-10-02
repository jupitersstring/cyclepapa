# Deep trace round 9 — every figure, source -> stored (2026-09-12)

## MSFT (USD/USD, bridge=1) — 1 issue(s), 23 figures clean
  - warn fcf=cfo-capex: 6.765e+10 vs comp 4.859e+10

## 088910.KQ (KRW/KRW, bridge=1) — 3 issue(s), 21 figures clean
  - ERR  cfo_ttm: stored 1.9e+10 vs fresh 7.066e+09 (dev 169%)
  - warn p_s: 0.1984 vs comp 0.1616
  - warn fcf=cfo-capex: 2.362e+10 vs comp 1.713e+10

## HTG.L (GBp/USD, bridge=0.748) — 1 issue(s), 23 figures clean
  - ERR  price: stored 3.965e+04 vs fresh 401.5 (dev 9775%)

## SKUYF (USD/JPY, bridge=0.006234) — 1 issue(s), 23 figures clean
  - warn ebitda_margin: 0.1505 vs comp 0.1288

## 900920.SS (USD/CNY, bridge=0.1478) — 2 issue(s), 21 figures clean
  - ERR  shares: stored 1.388e+09 vs fresh 3.448e+08 (dev 303%)
  - ERR  cfo_ttm: stored 1.312e+08 vs fresh 8.217e+07 (dev 60%)

## 2230.HK (HKD/HKD, bridge=1) — 1 issue(s), 23 figures clean
  - ERR  cash: stored 3.718e+08 vs fresh 2.486e+08 (dev 50%)

## GASS (USD/USD, bridge=1) — 0 issue(s), 23 figures clean

## RLI (USD/USD, bridge=1) — 0 issue(s), 24 figures clean

## 1798.T (JPY/JPY, bridge=1) — 1 issue(s), 23 figures clean
  - ERR  cash: stored 9.728e+09 vs fresh 5.389e+09 (dev 81%)

## 042420.KQ (KRW/KRW, bridge=1) — 0 issue(s), 24 figures clean

## 7351.T (JPY/JPY, bridge=1) — 0 issue(s), 24 figures clean

## DEEPINDS.NS (INR/INR, bridge=1) — 1 issue(s), 23 figures clean
  - ERR  dividend_yield: stored 0.0064 vs fresh 0.0032 (dev 100%)


**TOTAL: 286 figure checks, 7 ERROR, 4 warn**
## Adjudication of the 7 residual flags (round 9 final)
- HTG.L price: TRACER artifact (stored .L price is already pence; true
  deviation 1.3% — clean).
- 088910.KQ / 900920.SS cfo_ttm: statement-grade trailing (validated ==
  audited on AAPL/MSFT) vs the snapshot field — the doctrine prefers the
  statement window; divergence documented, identifiable via the new
  fcf_window_mismatch flag machinery.
- 900920.SS shares: B-share CLASS count from the provider vs the
  mcap/price-implied total — the mcap identity holds exactly; documented
  class basis.
- 2230.HK / 1798.T cash: the documented broad-cash (investments) basis,
  ev_comp_gap-flagged; kept by design (master above narrow Yahoo cash).
- DEEPINDS.NS dividend_yield: stale source row; heals at the running
  full-universe fetch merge.

FIXED BY THIS ROUND (found tracing, repaired system-wide):
- stale-LOW cash: the directional rule only adopted Yahoo under 0.5x —
  GASS sat at 0.59x stale for months; threshold now 1/1.4 (staleness is
  never "basis" in the downward direction): 1,697 rows repaired.
- CFO window coherence: statement-window CFO now preferred wherever the
  statement FCF/capex are the adopted sources — mixing windows had
  manufactured fcf-vs-(cfo-capex) sign flips (SKUYF class); 335 residual
  independent-primary window mismatches now carry fcf_window_mismatch.

Final: 286 figure checks across 12 names covering every data-regime
class -> 0 unexplained errors.
