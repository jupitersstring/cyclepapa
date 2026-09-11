# Valuation cross-check — top 0 by ETA

Master: asymmetry_global.csv | Source: ticker_yf.csv

**0 ERROR, 57 WARN, 76 clean.**

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

## XAUMF (US, yahoo) — WARN
- WARN: EV 1.77e+08 vs mcap+debt-cash 1.43e+08 (gap 26% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: ebitda_margin 0.242 < op_margin 0.270 (gap 0.03 — kept & qc-flagged)

## TTEC (US, yahoo) — WARN
- WARN: EV 9.26e+08 vs mcap+debt-cash -2.07e+07 (gap 1392% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## 003650.KS (KR, yahoo) — WARN
- WARN: roe 0.168 vs pb/p_e 0.117 (dev 43% — one of roe/pb/pe on a different period or equity basis)

## MDX.BK (TH, yahoo) — WARN
- WARN: EV 1.12e+09 vs mcap+debt-cash -1.9e+09 (gap 181% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

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

## FEDU (US, yahoo) — WARN
- WARN: EV -5.96e+07 vs mcap+debt-cash 1.69e+07 (gap 324% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.057 vs pb/p_e 0.437 (dev 87% — one of roe/pb/pe on a different period or equity basis)
- WARN: ebitda_ttm 1.89e+06 vs Yahoo 1.36e+07 (EDGAR-preferred divergence)
- WARN: revenue_ttm 3.71e+07 vs Yahoo 2.54e+08 (EDGAR-preferred divergence)

## NOAH (US, yahoo) — WARN
- WARN: EV -4.25e+09 vs mcap+debt-cash -4.49e+07 (gap 726% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.053 vs pb/p_e 0.422 (dev 87% — one of roe/pb/pe on a different period or equity basis)

## CN6.F (CN, yahoo) — WARN
- WARN: EV -3.36e+08 vs mcap+debt-cash -5.2e+08 (gap 461% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.020 vs pb/p_e 0.176 (dev 89% — one of roe/pb/pe on a different period or equity basis)

## XNET (US, yahoo) — WARN
- WARN: EV 9.05e+07 vs mcap+debt-cash 1.96e+08 (gap 34% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## COFFEEDAY.NS (IN, yahoo) — WARN
- WARN: EV 1.85e+10 vs mcap+debt-cash 1.61e+10 (gap 36% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## 7916.T (JP, yahoo) — WARN
- WARN: roe 0.020 vs pb/p_e 0.009 (dev 121% — one of roe/pb/pe on a different period or equity basis)

## 4530.TWO (TW, yahoo) — WARN
- WARN: roe 0.105 vs pb/p_e 0.006 (dev 1654% — one of roe/pb/pe on a different period or equity basis)

## SWPFF (US, yahoo) — WARN
- WARN: roe 0.012 vs pb/p_e 0.085 (dev 86% — one of roe/pb/pe on a different period or equity basis)

## YALA (US, yahoo) — WARN
- WARN: EV -1.97e+06 vs mcap+debt-cash 3.05e+08 (gap 37% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## MAMA (US, yahoo) — WARN
- WARN: roe 0.149 vs pb/p_e 0.048 (dev 212% — one of roe/pb/pe on a different period or equity basis)
- WARN: ebitda_ttm 1e+07 vs Yahoo 1.7e+07 (EDGAR-preferred divergence)

## AKKVF (US, yahoo) — WARN
- WARN: ebitda_margin 0.493 < op_margin 0.545 (gap 0.05 — kept & qc-flagged)
- WARN: gross_margin 0.428 < op_margin 0.545 (gap 0.12 — kept & qc-flagged)
- WARN: roe 0.027 vs pb/p_e 0.248 (dev 89% — one of roe/pb/pe on a different period or equity basis)

## GYLD-B.CO (DK, yahoo) — WARN
- WARN: EV 3.78e+08 vs mcap+debt-cash 1.82e+09 (gap 85% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.104 vs pb/p_e 0.033 (dev 220% — one of roe/pb/pe on a different period or equity basis)

## KGPETRO.BO (IN, yahoo) — WARN
- WARN: roe 0.024 vs pb/p_e 0.015 (dev 63% — one of roe/pb/pe on a different period or equity basis)

## CRDE (US, yahoo) — WARN
- WARN: EV 3.84e+08 vs mcap+debt-cash 1.96e+08 (gap 115% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: fcf_ttm 5.55e+07 > cfo_ttm 2.86e+07 (negative capex? check basis)

## RSMDF (US, yahoo) — WARN
- WARN: EV 1.35e+10 vs mcap+debt-cash 3.44e+10 (gap 59% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.252 vs pb/p_e 0.091 (dev 177% — one of roe/pb/pe on a different period or equity basis)

## DYNR (US, yahoo) — WARN
- WARN: roe 0.591 vs pb/p_e 3.276 (dev 82% — one of roe/pb/pe on a different period or equity basis)

## VALIANTORG.NS (IN, yahoo) — WARN
- WARN: roe 0.045 vs pb/p_e 0.072 (dev 37% — one of roe/pb/pe on a different period or equity basis)

## 600729.SS (CN, yahoo) — WARN
- WARN: fcf_ttm 2.11e+09 > cfo_ttm 1.81e+09 (negative capex? check basis)

## ZIJMF (US, yahoo) — WARN
- WARN: EV 2.48e+11 vs mcap+debt-cash 1.81e+11 (gap 53% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: ebitda_margin 0.262 < op_margin 0.321 (gap 0.06 — kept & qc-flagged)
- WARN: roe 0.366 vs pb/p_e 2.418 (dev 85% — one of roe/pb/pe on a different period or equity basis)

## WIMI (US, yahoo) — WARN
- WARN: EV -2.66e+09 vs mcap+debt-cash -1.6e+08 (gap 11240% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: ebitda_ttm -4.79e+06 vs Yahoo -1.88e+07 (EDGAR-preferred divergence)
- WARN: revenue_ttm 6.01e+07 vs Yahoo 4.22e+08 (EDGAR-preferred divergence)

## DKFT.JK (ID, yahoo) — WARN
- WARN: fcf_ttm 4.85e+11 > cfo_ttm 4.56e+11 (negative capex? check basis)

## PCRX (US, yahoo) — WARN
- WARN: roe 0.007 vs pb/p_e 0.021 (dev 66% — one of roe/pb/pe on a different period or equity basis)

## LLY (US, yahoo) — WARN
- WARN: roe 1.075 vs pb/p_e 0.783 (dev 37% — one of roe/pb/pe on a different period or equity basis)

## MMO.F (JP, yahoo) — WARN
- WARN: EV 1.55e+11 vs mcap+debt-cash 1.09e+11 (gap 1643% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## SUNS (US, yahoo) — WARN
- WARN: EV 2.37e+08 vs mcap+debt-cash 9.54e+07 (gap 140% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: ebitda_margin 0.460 < op_margin 0.578 (gap 0.12 — kept & qc-flagged)

## GIII (US, yahoo) — WARN
- WARN: ebitda_ttm 2.51e+08 vs Yahoo 1.55e+08 (EDGAR-preferred divergence)

## BKFKF (US, yahoo) — WARN
- WARN: roe 0.076 vs pb/p_e 0.478 (dev 84% — one of roe/pb/pe on a different period or equity basis)

## BJCHF (US, yahoo) — WARN
- WARN: net_cash_pct_mcap -11.67 vs (cash-debt)/mcap -10.66 (basis gap > 30pts of mcap)

## BYD (US, yahoo) — WARN
- WARN: roe 0.943 vs pb/p_e 0.659 (dev 43% — one of roe/pb/pe on a different period or equity basis)

## 600926.SS (CN, yahoo) — WARN
- WARN: EV 3.76e+11 vs mcap+debt-cash 2.86e+11 (gap 73% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## JG (US, yahoo) — WARN
- WARN: EV -7.62e+07 vs mcap+debt-cash 3.31e+07 (gap 283% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.055 vs pb/p_e 0.684 (dev 92% — one of roe/pb/pe on a different period or equity basis)

## 023810.KS (KR, yahoo) — WARN
- WARN: EV 4.54e+11 vs mcap+debt-cash 3.43e+11 (gap 217% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.086 vs pb/p_e 0.050 (dev 71% — one of roe/pb/pe on a different period or equity basis)
- WARN: net_cash_pct_mcap -4.89 vs (cash-debt)/mcap -5.75 (basis gap > 30pts of mcap)

## 4433.TWO (TW, yahoo) — WARN
- WARN: EV 4.36e+09 vs mcap+debt-cash 4e+09 (gap 32% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: roe 0.055 vs pb/p_e 0.038 (dev 46% — one of roe/pb/pe on a different period or equity basis)

## DFRYF (US, yahoo) — WARN
- WARN: roe 0.186 vs pb/p_e 0.123 (dev 51% — one of roe/pb/pe on a different period or equity basis)

## 110790.KQ (KR, yahoo) — WARN
- WARN: EV 2.93e+11 vs mcap+debt-cash 3.18e+11 (gap 35% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)
- WARN: ebitda_margin 0.072 < op_margin 0.121 (gap 0.05 — kept & qc-flagged)
- WARN: net_cash_pct_mcap -3.01 vs (cash-debt)/mcap -3.49 (basis gap > 30pts of mcap)

## ETCC (US, yahoo) — WARN
- WARN: EV 4.15e+07 vs mcap+debt-cash 3.4e+07 (gap 49% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)

## VISTAA.MX (MX, yahoo) — WARN
- WARN: roe 0.351 vs pb/p_e 0.014 (dev 2320% — one of roe/pb/pe on a different period or equity basis)

## IZM (US, yahoo) — WARN
- WARN: EV 1.63e+07 vs mcap+debt-cash 9.68e+06 (gap 237% of mcap — likely broad-cash/investments basis vs Yahoo totalCash)


## Clean names
AWC.SI, B9A.F, ACTG, KROS, LSIP.JK, IRC.BK, ALGEV.PA, 0100.KL, ISVLF, THMUI.BK, 134580.KQ, 100660.KQ, 7692.KL, SRIKPRIND.BO, ONEXF, CEK.DE, USNA, CSRA.JK, VICR, DV, 045300.KQ, GIS.MI, GNGBF, NTG.CO, 080530.KQ, WHITF, CVONF, BYKE.NS, TBTC, GNTX, PHAR.L, GMPL.BO, FIE.DE, CALM, 2298.HK, CWXZF, ONGC.NS, MPWR, ADBE, FNTL.L, TCNNF, 3587.TWO, 7733.T, WPAY.ST, 6961.T, FTI, 1997.HK, 5PD.SI, CXM, PRKA, AMARIN.BK, 600285.SS, TRLV, VGNT, MUSA, FHTX, GET.PA, VSNT, MX, KHAICHEM.NS, ORLY, QCOM, MDIA.JK, EVV, 300913.SZ, DLHC, 9656.T, IREN, DBD, HURN, VNG.BK, TEVJF, 2233.TW, VVV, SHC, NILI.V
