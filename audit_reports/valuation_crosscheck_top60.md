# Valuation cross-check — top 60 by ETA

Master: asymmetry_global.csv | Source: ticker_yf.csv

**0 ERROR, 24 WARN, 36 clean.**

## 088910.KQ (KR, yahoo) — WARN
- WARN: fcf_ttm 2.36e+10 > cfo_ttm 1.9e+10 (negative capex? check basis)

## 2230.HK (HK, yahoo) — WARN
- WARN: EV 1.55e+08 vs mcap+debt-cash 3.87e+07 (gap 29% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## 003650.KS (KR, yahoo) — WARN
- WARN: roe 0.168 vs pb/p_e 0.117 (dev 43% — one of roe/pb/pe on a different period or equity basis)

## 4629.T (JP, yahoo) — WARN
- WARN: roe 0.052 vs pb/p_e 0.081 (dev 35% — one of roe/pb/pe on a different period or equity basis)

## JAMESWARREN.BO (IN, yahoo) — WARN
- WARN: roe 0.064 vs pb/p_e 0.039 (dev 67% — one of roe/pb/pe on a different period or equity basis)

## 042420.KQ (KR, yahoo) — WARN
- WARN: EV 1.77e+11 vs mcap+debt-cash -2.09e+11 (gap 261% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.083 vs pb/p_e 0.058 (dev 44% — one of roe/pb/pe on a different period or equity basis)
- WARN: net_cash_pct_mcap 2.77 vs (cash-debt)/mcap 2.41 (basis gap > 30pts of mcap)

## 035610.KQ (KR, yahoo) — WARN
- WARN: EV 1.51e+10 vs mcap+debt-cash -4.74e+10 (gap 45% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.172 vs pb/p_e 0.099 (dev 73% — one of roe/pb/pe on a different period or equity basis)

## 4301.T (JP, yahoo) — WARN
- WARN: roe 0.082 vs pb/p_e 0.013 (dev 517% — one of roe/pb/pe on a different period or equity basis)

## NPK.BK (TH, yahoo) — WARN
- WARN: roe 0.062 vs pb/p_e 0.022 (dev 185% — one of roe/pb/pe on a different period or equity basis)

## SHRIDINE.BO (IN, yahoo) — WARN
- WARN: ebitda_margin 0.095 < op_margin 0.121 (gap 0.03 — kept & qc-flagged)

## 054800.KQ (KR, yahoo) — WARN
- WARN: EV 4.64e+11 vs mcap+debt-cash -6.22e+10 (gap 399% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: fcf_ttm 7.15e+10 > cfo_ttm 6.65e+10 (negative capex? check basis)

## 014570.KQ (KR, yahoo) — WARN
- WARN: roe 0.087 vs pb/p_e 0.018 (dev 376% — one of roe/pb/pe on a different period or equity basis)

## 2101.HK (HK, yahoo) — WARN
- WARN: ebitda_margin 0.187 < op_margin 0.271 (gap 0.08 — kept & qc-flagged)
- WARN: fcf_ttm 3.69e+08 > cfo_ttm 2.38e+08 (negative capex? check basis)

## 031510.KQ (KR, yahoo) — WARN
- WARN: EV 3.29e+09 vs mcap+debt-cash 1.04e+10 (gap 25% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## 1118.HK (HK, yahoo) — WARN
- WARN: EV 5.89e+08 vs mcap+debt-cash 2.15e+08 (gap 54% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## IGAR.JK (ID, yahoo) — WARN
- WARN: EV 2.24e+11 vs mcap+debt-cash -2.69e+10 (gap 58% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## 0911.HK (HK, yahoo) — WARN
- WARN: EV 5.74e+07 vs mcap+debt-cash 1.13e+07 (gap 63% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.015 vs pb/p_e 0.009 (dev 78% — one of roe/pb/pe on a different period or equity basis)

## 0725.HK (HK, yahoo) — WARN
- WARN: ebitda_margin 0.126 < op_margin 0.160 (gap 0.03 — kept & qc-flagged)

## 11C.SG (PL, yahoo) — WARN
- WARN: roe 0.046 vs pb/p_e 0.001 (dev 8293% — one of roe/pb/pe on a different period or equity basis)

## 036190.KQ (KR, yahoo) — WARN
- WARN: ebitda_margin 0.102 < op_margin 0.123 (gap 0.02 — kept & qc-flagged)

## 043610.KQ (KR, yahoo) — WARN
- WARN: EV 5.34e+10 vs mcap+debt-cash -5.34e+09 (gap 85% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## 200570.SZ (CN, yahoo) — WARN
- WARN: fcf_ttm 3.38e+08 > cfo_ttm 3.07e+08 (negative capex? check basis)

## TUGU.JK (ID, yahoo) — WARN
- WARN: roe 0.063 vs pb/p_e 0.100 (dev 37% — one of roe/pb/pe on a different period or equity basis)

## 1758.T (JP, yahoo) — WARN
- WARN: ebitda_margin 0.065 < op_margin 0.086 (gap 0.02 — kept & qc-flagged)


## Clean names
CTTMF, AWC.SI, IRC.BK, 6155.T, TPP.BK, ALGEV.PA, 1900.HK, 120240.KQ, 1V5.F, 0057.HK, ENEFI.BD, 3798.HK, 2348.HK, 264450.KQ, 219420.KQ, 6907.T, 0114.HK, 1281.HK, TCID.JK, 052330.KQ, LSIP.JK, SPG.BK, 0243.HK, HMVL.NS, FPIP.ST, 348350.KQ, 7877.T, 1905.T, 0887.HK, 088130.KQ, 053980.KQ, GTEC, 047820.KQ, 3954.T, 095660.KQ, 0018.HK
