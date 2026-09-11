# Valuation cross-check — top 0 by ETA

Master: asymmetry_global.csv | Source: ticker_yf.csv

**0 ERROR, 60 WARN, 81 clean.**

## 088910.KQ (KR, yahoo) — WARN
- WARN: fcf_ttm 2.36e+10 > cfo_ttm 7.07e+09 (negative capex? check basis)

## 042420.KQ (KR, yahoo) — WARN
- WARN: EV 1.77e+11 vs mcap+debt-cash -2.1e+11 (gap 263% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.083 vs pb/p_e 0.058 (dev 44% — one of roe/pb/pe on a different period or equity basis)
- WARN: net_cash_pct_mcap 2.77 vs (cash-debt)/mcap 2.42 (basis gap > 30pts of mcap)

## 1900.HK (HK, yahoo) — WARN
- WARN: EV 3.8e+08 vs mcap+debt-cash -1.03e+08 (gap 160% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## DC-A.TO (CA, yahoo) — WARN
- WARN: roe 0.553 vs pb/p_e 0.383 (dev 45% — one of roe/pb/pe on a different period or equity basis)

## 2230.HK (HK, yahoo) — WARN
- WARN: EV 1.55e+08 vs mcap+debt-cash 4.47e+07 (gap 27% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## TTEC (US, yahoo) — WARN
- WARN: EV 9.26e+08 vs mcap+debt-cash -2.07e+07 (gap 1392% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## 003650.KS (KR, yahoo) — WARN
- WARN: roe 0.168 vs pb/p_e 0.117 (dev 43% — one of roe/pb/pe on a different period or equity basis)

## MDX.BK (TH, yahoo) — WARN
- WARN: EV 1.12e+09 vs mcap+debt-cash -1.9e+09 (gap 181% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## WEIBF (US, yahoo) — WARN
- WARN: EV 1.4e+09 vs mcap+debt-cash 3.33e+09 (gap 55% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## HEOL (US, yahoo) — WARN
- WARN: ebitda_margin 0.176 < op_margin 0.214 (gap 0.04 — kept & qc-flagged)
- WARN: gross_margin 0.124 < op_margin 0.214 (gap 0.09 — kept & qc-flagged)

## MKTW (US, yahoo) — WARN
- WARN: EV -2.09e+08 vs mcap+debt-cash 4.92e+06 (gap 411% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## BVNRY (US, yahoo) — WARN
- WARN: roe 0.122 vs pb/p_e 0.710 (dev 83% — one of roe/pb/pe on a different period or equity basis)

## CAAS (US, yahoo) — WARN
- WARN: EV 1.93e+08 vs mcap+debt-cash 1.02e+08 (gap 56% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## STG (US, yahoo) — WARN
- WARN: EV -6.9e+08 vs mcap+debt-cash -4.61e+07 (gap 1774% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## PRDO (US, yahoo) — WARN
- WARN: EV 1.46e+09 vs mcap+debt-cash 2.03e+09 (gap 27% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## 069730.KS (KR, yahoo) — WARN
- WARN: fcf_ttm 2.15e+10 > cfo_ttm 3.15e+09 (negative capex? check basis)

## INTRK.AT (GR, yahoo) — WARN
- WARN: EV 2.44e+08 vs mcap+debt-cash 1.23e+08 (gap 48% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## 075130.KQ (KR, yahoo) — WARN
- WARN: EV 1.46e+10 vs mcap+debt-cash 1.75e+09 (gap 40% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## ELTP (US, yahoo) — WARN
- WARN: roe 0.744 vs pb/p_e 0.515 (dev 44% — one of roe/pb/pe on a different period or equity basis)

## GDOT (US, yahoo) — WARN
- WARN: EV -3.18e+08 vs mcap+debt-cash -8.87e+08 (gap 75% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: gross_margin 0.000 < op_margin 0.049 (gap 0.05 — kept & qc-flagged)

## CHJTF (US, yahoo) — WARN
- WARN: ebitda_margin 0.379 < op_margin 0.526 (gap 0.15 — kept & qc-flagged)
- WARN: roe 0.209 vs pb/p_e 1.099 (dev 81% — one of roe/pb/pe on a different period or equity basis)

## 092300.KQ (KR, yahoo) — WARN
- WARN: fcf_ttm 1.98e+10 > cfo_ttm 1e+10 (negative capex? check basis)

## FEDU (US, yahoo) — WARN
- WARN: EV -5.96e+07 vs mcap+debt-cash 1.69e+07 (gap 324% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.057 vs pb/p_e 0.437 (dev 87% — one of roe/pb/pe on a different period or equity basis)
- WARN: ebitda_ttm 1.89e+06 vs Yahoo 1.36e+07 (EDGAR-preferred divergence)
- WARN: revenue_ttm 3.71e+07 vs Yahoo 2.54e+08 (EDGAR-preferred divergence)

## NOAH (US, yahoo) — WARN
- WARN: EV -4.25e+09 vs mcap+debt-cash -4.49e+07 (gap 726% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.053 vs pb/p_e 0.422 (dev 87% — one of roe/pb/pe on a different period or equity basis)

## 147830.KQ (KR, yahoo) — WARN
- WARN: roe 0.173 vs pb/p_e 0.305 (dev 43% — one of roe/pb/pe on a different period or equity basis)

## XNET (US, yahoo) — WARN
- WARN: EV 9.05e+07 vs mcap+debt-cash 1.96e+08 (gap 34% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## COFFEEDAY.NS (IN, yahoo) — WARN
- WARN: EV 1.85e+10 vs mcap+debt-cash 1.61e+10 (gap 36% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## JL (US, yahoo) — WARN
- WARN: fcf_ttm 6.2e+06 > cfo_ttm 3.9e+06 (negative capex? check basis)

## BHG.ST (SE, yahoo) — WARN
- WARN: roe 0.028 vs pb/p_e 0.015 (dev 90% — one of roe/pb/pe on a different period or equity basis)

## YALA (US, yahoo) — WARN
- WARN: EV -1.97e+06 vs mcap+debt-cash 3.05e+08 (gap 37% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## VISN (US, yahoo) — WARN
- WARN: EV 1.4e+09 vs mcap+debt-cash -1.03e+09 (gap 165% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## TYCN.BK (TH, yahoo) — WARN
- WARN: EV 2.91e+09 vs mcap+debt-cash 2.08e+09 (gap 83% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.023 vs pb/p_e 0.011 (dev 118% — one of roe/pb/pe on a different period or equity basis)

## IH (US, yahoo) — WARN
- WARN: EV -1.03e+09 vs mcap+debt-cash -1.02e+08 (gap 1482% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.098 vs pb/p_e 0.514 (dev 81% — one of roe/pb/pe on a different period or equity basis)
- WARN: net_cash_pct_mcap 2.30 vs (cash-debt)/mcap 2.64 (basis gap > 30pts of mcap)

## 033050.KQ (KR, yahoo) — WARN
- WARN: roe 0.076 vs pb/p_e 0.118 (dev 35% — one of roe/pb/pe on a different period or equity basis)

## SEKEF (US, yahoo) — WARN
- WARN: EV -3.97e+10 vs mcap+debt-cash -4.25e+10 (gap 64% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## BALM4.SA (BR, yahoo) — WARN
- WARN: dividend_yield 36.94% implausible (>30%)

## COLL (US, yahoo) — WARN
- WARN: roe 0.274 vs pb/p_e 0.132 (dev 107% — one of roe/pb/pe on a different period or equity basis)

## CSPKF (US, yahoo) — WARN
- WARN: EV 6.27e+09 vs mcap+debt-cash 5.13e+09 (gap 44% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: gross_margin 0.247 < op_margin 0.302 (gap 0.06 — kept & qc-flagged)

## RSKIA (US, yahoo) — WARN
- WARN: EV 5.28e+07 vs mcap+debt-cash 9.57e+07 (gap 43% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## MAR.LS (PT, yahoo) — WARN
- WARN: fcf_ttm 3.06e+07 > cfo_ttm 1.03e+07 (negative capex? check basis)

## PENG (US, yahoo) — WARN
- WARN: roe 0.096 vs pb/p_e 0.162 (dev 41% — one of roe/pb/pe on a different period or equity basis)

## 002878.SZ (CN, yahoo) — WARN
- WARN: EV 5.54e+09 vs mcap+debt-cash 3.39e+09 (gap 63% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: fcf_ttm 3.61e+08 > cfo_ttm 2.35e+08 (negative capex? check basis)

## KGGNF (US, yahoo) — WARN
- WARN: roe 0.253 vs pb/p_e 0.432 (dev 42% — one of roe/pb/pe on a different period or equity basis)

## 215480.KQ (KR, yahoo) — WARN
- WARN: EV 9.57e+09 vs mcap+debt-cash 1.58e+10 (gap 35% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: ebitda_margin 0.054 < op_margin 0.088 (gap 0.03 — kept & qc-flagged)
- WARN: roe 0.009 vs pb/p_e 0.001 (dev 899% — one of roe/pb/pe on a different period or equity basis)

## PHR (US, yahoo) — WARN
- WARN: ebitda_ttm 2.97e+07 vs Yahoo 4.38e+07 (EDGAR-preferred divergence)

## SHECY (US, yahoo) — WARN
- WARN: EV -1.14e+12 vs mcap+debt-cash -1.33e+12 (gap 278% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: net_cash_pct_mcap 19.34 vs (cash-debt)/mcap 20.66 (basis gap > 30pts of mcap)

## 205470.KQ (KR, yahoo) — WARN
- WARN: EV -5.43e+10 vs mcap+debt-cash -1.06e+11 (gap 71% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## APLS (US, snapshot-only) — WARN
- WARN: roe 0.460 vs pb/p_e 0.330 (dev 40% — one of roe/pb/pe on a different period or equity basis)

## JRNGF (US, yahoo) — WARN
- WARN: roe 0.076 vs pb/p_e 0.128 (dev 41% — one of roe/pb/pe on a different period or equity basis)

## GUJCRAFT.BO (IN, yahoo) — WARN
- WARN: roe 0.015 vs pb/p_e 0.009 (dev 73% — one of roe/pb/pe on a different period or equity basis)

## WLFC (US, yahoo) — WARN
- WARN: roe 0.176 vs pb/p_e 0.128 (dev 38% — one of roe/pb/pe on a different period or equity basis)

## BDULF (US, yahoo) — WARN
- WARN: EV 2.73e+10 vs mcap+debt-cash 2.4e+10 (gap 34% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.149 vs pb/p_e 4.424 (dev 97% — one of roe/pb/pe on a different period or equity basis)

## Z77.SI (SG, yahoo) — WARN
- WARN: roe 0.205 vs pb/p_e 0.128 (dev 61% — one of roe/pb/pe on a different period or equity basis)

## NGVT (US, yahoo) — WARN
- WARN: roe 0.301 vs pb/p_e 1.155 (dev 74% — one of roe/pb/pe on a different period or equity basis)

## 2158.HK (HK, yahoo) — WARN
- WARN: ebitda_margin -0.063 < op_margin 0.066 (gap 0.13 — kept & qc-flagged)
- WARN: roe 0.021 vs pb/p_e 0.015 (dev 40% — one of roe/pb/pe on a different period or equity basis)

## SUGBY (US, yahoo) — WARN
- WARN: ebitda_margin 0.449 < op_margin 0.598 (gap 0.15 — kept & qc-flagged)

## AIS.AX (AU, yahoo) — WARN
- WARN: roe 0.389 vs pb/p_e 0.183 (dev 113% — one of roe/pb/pe on a different period or equity basis)

## BNR (CN, yahoo) — WARN
- WARN: EV -2.69e+08 vs mcap+debt-cash 5.8e+07 (gap 259% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: ebitda_ttm -4.73e+06 vs Yahoo -4.43e+07 (EDGAR-preferred divergence)
- WARN: revenue_ttm 7.72e+07 vs Yahoo 5.14e+08 (EDGAR-preferred divergence)

## 3321.T (JP, yahoo) — WARN
- WARN: EV 1.91e+10 vs mcap+debt-cash 2.31e+10 (gap 29% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## SLVM (US, yahoo) — WARN
- WARN: roe 0.108 vs pb/p_e 0.078 (dev 39% — one of roe/pb/pe on a different period or equity basis)


## Clean names
AWC.SI, B9A.F, RDFEF, ACTG, KROS, LSIP.JK, IRC.BK, ALGEV.PA, 0100.KL, ISVLF, THMUI.BK, APP.BK, 100660.KQ, SRIKPRIND.BO, ONEXF, GASS, CEK.DE, USNA, NDT.MI, 215200.KQ, PREMIERPOL.NS, MADHAVIPL.BO, APH, GIS.MI, MILS3.SA, PACIFICI.BO, 2328.HK, 9942.TW, FRSH, T41.SI, BYGGP.ST, CCS, PAY, 035150.KS, SCCO, AMN, ADN.TO, LNN, MTY.TO, SONA.JK, PEN, TCNNF, SKR.BK, 2496.TW, 6498.TWO, 009190.KS, 6568.TWO, FORM, TEL.OL, PRKA, 3877.HK, 6039.T, 115570.KQ, TRLV, WDFC, MIKN.SW, 600019.SS, VGNT, WM, HPQ, VSNT, AMRX, BF-A, 9861.T, SM, AKG.NS, WW, 002128.SZ, SYK, MNPR, RTB, LII, SMCIP, PGUCY, HFRO, DBD, ATKR, SEM, 036810.KQ, 1120.SR, EGPLF
