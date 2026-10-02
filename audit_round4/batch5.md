# Archetype review, round 2, batch 5 (23 archetypes)

Method: I took every gate input and every intermediate leg from an instrumented, write-free copy of `compute()`, run on today's inputs (scratchpad/r2 df.parquet + locals.parquet, 15:38 UTC). Its final `arch_*` columns match `archetype_tags.csv` exactly on all 23 columns (0 differing rows out of 46,526). I then rebuilt each gate leg by leg from those inputs. Reconstruction vs the published column: 21 of 23 are exact. Three show small gaps:

- durable_reinvestment: 1,929 rebuilt vs 1,854 published. The 75 extra rows are the EBITDA > 1.1x revenue data-corruption scrub at L9272.
- gayner_wiggle_not_obsolete: 446 vs 444 (2 rows lost to the scrubs).
- wolf_compounder: 164 vs 165.

"Removes X of Y" means: of the Y names that pass every other leg, this leg alone fails X. Universe N = 46,526; operating 36,173; `_mb_base` 15,304. Scripts are in scratchpad/b5/ (lib.py, a1.py ... a23.py).

Facts several sections rely on (beyond the batch-1 list):
- **`da_ttm` is in the reporting currency, not converted on ADR/OTC lines.** Tokyo Electron's TOELF line carries da_ttm = 8.13e10, the same figure as 8035.T (¥81.3B). On TOELF that sits next to net income of $5.0B and EBITDA of $6.3B. `_fx_coherent` (L4068-4078) only compares the market-cap and revenue USD twins, so it lets this through. Across the universe, 1,597 operating names with positive EBITDA and positive op margin show D&A > 1.05x EBITDA. Every owner-earnings construction (`_oe_loc` L4270) inherits this.
- **`rev_3y_cagr` is populated for only 2,311 names (5%).** The filled `revenue_3y_cagr` has 33,708. Eleven gates read the sparse column (L3114, 3233, 4150, 4278, 5016, 5071, 5796, 6259, 6290, 6635, 6856), so those legs are dead or no-ops for 95% of the universe.
- **Missing analyst count is read as "neglected"** (`sent_neglected_flag = ~(_sn > 3)`, L7379; `_blk_perc` L7428). OTC/ADR lines of heavily covered companies inherit "nobody is watching".
- **Non-common lines still leak past `_is_noncommon` (L9195-9248):**
  - CHS Inc. preferreds CHSCL/M/N/O/P: 5-letter tickers whose base "CHSC" is not in the universe.
  - Comcast ZONES exchangeable debenture CCZ.
  - Celgene CVR CELG-RI: the `-RI` suffix is not in the rights pattern.
- **`sent_initiations_12m` is 0 on every one of its 7,088 non-NaN rows**, so every `>= 1` initiation lens is dead.
- Many fires are duplicate listing lines of one company (Tencent ×3, Volkswagen ×6, Bombardier ×5). This is a known pool-level issue and I note it only where it distorts a top list.

---

## arch_gayner_wiggle_not_obsolete (444 fires, median mcap $2.85B, 123 > $10B)

**Intent** (L8183-8191): "a franchise with a long record ... whose price is 20%+ off its 5-year high while perception has turned against it ... yet the business passes the 'would we start it today' test ... The alcohol / bread case, not the newspaper case." The inline comment at L8200 reads "integrity: a wiggle in a clean set of books, not a fraud at 0.4x EBIT".

**Code** (L8192-8204; helpers L8061-8087):
- `_g_long` (L8192): years ≥ 8, `tc_loss_years_other ≤ 1` (NaN-permissive), lindy ROIC ≥ 10%.
  - Most binding leg: removes 1,131 of 1,577.
  - "Full statement window" is in practice "8 of 8 years". 29,639 names sit at the cap; 7-year names fail.
- `_g_intact` (L8194): TTM revenue ≥ -5% and op margin ≥ 0.75x the through-cycle median. Removes 366 of 812. It measures the intent.
- `_g_out_of_favour` (L8195):
  - Price part: `ts_dist_hi260 ≤ 0.80`. All 444 fires pass on the 5-year lens.
  - Perception part: OR of buy-share falling, targets cut, or `ts_r52 < 0`. 302 of 444 fires qualify on `ts_r52 < 0` alone, so "perception turned" is mostly a second price test.
  - 40 fires are up on the year and pass via a buy-share dip. Examples:
    - CAT: r52 +78%, buy share -4pp, targets **raised** 28%.
    - Bajaj Consumer: r52 +114%.
    - Neste: r52 +108%.
  - These are momentum pullbacks, not out-of-favour franchises.
- `~(_g_sh3 > 0)`: zero tolerance on share growth. Removes 345 of 791.
- `_g_integrity` (L8084): `~(fq_cfo_to_ni < 0.6)`, Beneish, DQ flag, SBC ≤ 5%, no one-off flag. Removes only 62 of 508.
  - **Every quarterly input is NaN-permissive.** `fq_cfo_to_ni` is NaN for 39% of `_mb_base` and 93 of 444 fires.
  - No fallback to the master CFO/NI or to the through-cycle cash record.
- `_not_melting`: no-op (removes 0).

**Brightcom Group (BCG.NS)** ranks about 6th by spirit (0.707, tied). It has no fmp_quarterly panel at all: `fq_cfo_to_ni`, `fq_beneish_m`, `fq_sloan_accruals`, `fq_rec_vs_rev`, `fq_dso` and the cash-tax fields are all NaN. That is why every integrity leg passes. The receivables-divergence, accruals and cash-tax-wedge flags could not have caught it. No auditor field exists, and `data_quality_flag` = 0.

These available columns would have flagged it:

| Column | BCG value |
|---|---|
| cfo_ttm / net_income_ttm | 0.19 |
| cash_conversion (CFO/EBITDA) | 0.107 |
| fmp_income_quality | 0.028 |
| tc_fcf_pos | 4 of 8 years |
| tc_fcf_margin_avg | -0.4%, vs tc_med_opm 22.5% |
| fmp_st_cash_roic_lindy | -0.4%, vs roic_lindy 14.5% |
| fg_ocf_ps_5y | -88%, while fg_rev_ps_5y is +27% |
| fmp_st_shares_growth_5y | +91% |
| fmp_low_earnings_quality_flag | 1 |
| ev_ebit | **0.40**, with net cash 71% of mcap (the comment's own "fraud at 0.4x EBIT") |

Two fallbacks, each of which catches BCG:
- Master CFO/NI < 0.6 where `fq_cfo_to_ni` is NaN removes 17 of 444. They include TRITURBINE 0.32, ASTRAZEN.NS -0.08, WPIL -0.59 and DLINKINDIA 0.14.
- Through-cycle FCF margin < 25% of the median op margin removes 37 of 444.

**Coverage** (NaN %: universe / operating / mb_base):

| Input | Universe | Operating | mb_base |
|---|---|---|---|
| tc_years | 12.5 | 11.7 | 2.9 |
| tc_loss_years_other | 22.5 | 21.3 | 6.5 |
| tc_med_opm | 30.0 | 29.7 | 10.5 |
| sent_buy_share_d12 | 75.6 | 75.1 | 47.1 |
| sent_pt_rev_q | 93.8 | 93.9 | 86.9 |
| fq_cfo_to_ni | 59.9 | 61.9 | 39.3 |

Venues: US 166, IN 61, CN 48, JP 32. The quarterly-panel gaps (IN/ID/TH micro-caps) are exactly where integrity is unmeasured.

**Fires / sanity:**
- Fit the thesis: 6200.T Insource, NOVO-B.CO, AUTO.L, ROL, 0700.HK. All have 8 of 8 profitable years, are 40-75% off the 5-year high, and keep margins at or above their median.
- Do not fit:
  - BCG.NS (above).
  - CAT and IESC: momentum pullbacks.
  - NONOF, TCEHY/TCTZF: duplicate lines; 100 fires share a company name.

**Severity:** LOOSE.

**Fix:** where `fq_cfo_to_ni` is NaN, fall back to master `cfo_ttm/net_income_ttm ≥ 0.6`, and require `tc_fcf_margin_avg ≥ 0.25×tc_med_opm`. Add `ts_r52 ≤ 0.20` to `_g_out_of_favour`.

## arch_durable_reinvestment (1,854 fires, median mcap $1.48B, 418 > $10B)

**Intent** (L1907-1908): "lindy ROIIC > 15% over a multi-cycle history. The Mauboussin / Mayer compounder signature."

**Code** (L1915-1922): op, `_roce_now_ok`, `roic_lindy ≥ 0.10`, `n_yrs_positive_roic ≥ 4`, ROIIC in [0.15, 1.0], and (`asset_3y_cagr > 5%` OR `roiic ≥ 0.20`). Spike scrub at L9429-9440.
- ROIC ≥ 10% removes 2,659 of 4,588; the ROIIC band removes 1,446 of 3,375. Both measure the intent.
- All 1,854 fires use the FMP-filled `roiic_lindy` (`fmp_filled_roiic_lindy` = 1 for every fire). The section header's "EDGAR-only" is stale.
- `n_yrs_positive_roic` maxes at 5, so "≥ 4" means 4 of 5 years. 198 fires rest on only 2 ROIIC windows (`fmp_st_roiic_windows`), which is a two-point "lindy".
- **The asset-light escape (`roiic ≥ 0.20` with assets ≤ 5%/yr) admits 411 fires. 163 of them have a shrinking asset base** (asset_3y_cagr < 0), so they are harvesters, not reinvestors:
  - MO: assets -1.8%/yr, revenue 5y -0.7%, ROIIC 0.64.
  - LOW, NKE (assets -3.2%), Kuehne+Nagel (-6.8%), Wesfarmers ×3 lines.
  - ROIIC on a falling invested-capital base is a ratio of two negatives.
- No `mcap > 0` or live-listing gate: 59 fires have a NaN market cap. These are delisted or acquired lines: Swedish Match (×2), Atlas Copco ATLKF, Loral, IBI Group, LTI.BO, NetEnt NTNTY, MyHammer MYRK.DE. Three of them are in the top 5 by spirit (0QTE.L, MYRK.DE, NTNTY).

**Coverage** (NaN %: universe / operating / mb_base):

| Input | Universe | Operating | mb_base |
|---|---|---|---|
| roic_lindy | 12.5 | 11.7 | 2.9 |
| roiic_lindy | 40.7 | 36.6 | 20.5 |
| asset_3y_cagr | 18.2 | 16.0 | 3.3 |

**Fires / sanity:**
- Fit: GOOG (ROIIC 0.85, assets +17.7%), LLY, KLA, TSMC, PREMIERPOL.NS.
- Do not fit: MO, NKE and the shrinking-base group; the NaN-mcap delisted lines; Wuliangye (rev -48%).

**Severity:** LOOSE.

**Fix:** require `asset_3y_cagr > 0` on the ROIIC-escape branch, `fmp_st_roiic_windows ≥ 3` and `mcap > 0`.

## arch_lindy_growth (916 fires, median mcap $1.34B)

**Intent** (L2340-2342): "revenue 5y CAGR >= 8% AND topline accelerating (3y CAGR > 5y CAGR) AND asset base growing. Multi-cycle expansion without the single-year base-effect noise."

**Code** (L2343-2362):
- Legs: op, `_roce_now_ok`, revenue ≥ $20M, `_profit_present`, cash or ROIC, 5y CAGR ≥ 8%, `revenue_accel_lindy > 0`, assets 5y > 3%, history ≥ 5, sales per share 5y ≥ +47%, TTM ≥ half the 5y rate, high-inflation exclusion.
- `revenue_accel_lindy` equals `revenue_3y_cagr - revenue_5y_cagr` exactly (32,249 rows checked).
- Acceleration is the binding leg (removes 2,090 of 3,006). A steady 15%/yr compounder that eases to 14% fails, which is TIGHT for a "durable growth" label.
- **The base-effect guard only checks a single-year `rev_yoy > 5` (L9429).** Multi-year explosions pass:
  - 78 fires have a 3y CAGR > 50%; 20 have > 100%.
  - 33 of the top-50 by spirit have a 3y CAGR > 50%.
  - The top spirit names are MEDIQON (3y CAGR 657%), AVI.BO (335%), Kernex (374%) and Krishana (126%).
- MU (rev_yoy +259%, a memory-cycle peak) passes as "durable".
- `~(rev_yoy < 0.5×cagr)` is NaN-permissive: 19 fires have rev_yoy NaN, e.g. AVI.BO.
- 39 fires have op margin < 0 (TTGT -47%, ACTG), admitted via `fcf_yield > 0` or EBITDA in `_profit_present`.

**Coverage** (NaN % universe / mb_base): revenue_5y_cagr 29.6 / 9.1; revenue_accel_lindy 30.7 / 9.3; fg_rev_ps_5y 12.5 / 2.9. TR fires go to the hi-inflation watch as intended (2 names); no other venue is blind.

**Fires / sanity:**
- Fit: MSFT, AVGO, META, LLY, 5TP.SI.
- Do not fit: MEDIQON, AVI.BO, Kernex (base effect); MU (cycle peak).

**Severity:** LOOSE (base effect), with a TIGHT element (strict acceleration).

**Fix:** cap `revenue_3y_cagr ≤ 0.60` and `rev_yoy ≤ 1.0` unless the 5y CAGR corroborates; require `rev_yoy` present.

## arch_large_cap_quality (839 fires, median mcap $26.5B)

**Intent** (L2546-2551): "big, highly profitable, cash-generative, conservatively financed, and either returning cash or compounding at a high rate."

**Code** (L2559-2572):
- mcap ≥ $10B; EBITDA margin ≥ 15% (sane band); FCF; nde < 3.
- Returns leg: (roce ≥ 0.10 and not one-off) OR roic_after_sbc ≥ 0.15 OR roic_lindy ≥ 0.12.
- Payout leg: capital return ≥ 2% OR dividend ≥ 1.5% OR FCF yield > 2%.
- 823 of 839 fires pass the returns leg on spot ROCE. **256 fires have lindy ROIC < 8%** and 6 have it negative:
  - GE: ROCE 0.82, lindy 2.5%.
  - BeiGene 49BA.F: ROCE 0.61, lindy -30%.
  - Bombardier (×5 lines): ROCE 0.62 on thin equity, lindy 3%.
  - Salesforce: lindy 1.8%.
  - Deutsche Telekom ×5 lines: lindy 4.5%.
- `_roce_oneoff_suspect` only triggers above 1.0, so 0.6-0.8 artifacts pass.
- 148 fires pass the payout leg only through `fcf_yield > 2%`, which duplicates the cash-generation leg.
- nde 99-fill: only 2 net-cash giants (UTHR, NXT) are lost, so this is negligible.

**Coverage:** roic_after_sbc is NaN for 90.6%, so that leg is effectively US-only. Venues: US 517, CN 42, JP 33.

**Fires / sanity:**
- Fit: AAPL, META, SABIC Agri, Luzhou Laojiao, CHKP.
- Do not fit: GE, BeiGene, Bombardier, Chesapeake CS1.F (rev +241% merger), Accor.

**Severity:** LOOSE.

**Fix:** require `roic_lindy ≥ 0.10` alongside spot ROCE (or `_roce_corroborated`), and lower the one-off suspect threshold to roce > 0.5 with lindy < 0.10.

## arch_oneil_canslim (97 fires, median mcap $885M)

**Intent** (L3355-3359, 3381-3384): C = current-quarter EPS +25%, A = annual growth with ROE ≥ ~17%, N = near the high, L = RS leader.

**Code:**
- Watch rule (L3372-3375; helpers L3272-3281): `_on_C` = EPS streak ≥ 2 OR **rev_yoy ≥ 20%**; `_on_A`; `_on_N` uses the stale quote-time `pct_off_52w_high`; `_on_L`.
- Core via `_tier` (L3386-3395): `fqx_eps_q_yoy ≥ 0.25`, `ts_rs_pct_mkt ≥ 80`, `ts_dist_hi52 ≥ 0.85`, not decelerating, continuing ops, ROCE ≥ 15%, `fg_ni_ps_3y ≥ +52%`.
- `measured = fqx_eps_q_yoy.notna() & ts_rs_pct_mkt.notna()`.

Two logic problems:
1. **The measured core is ANDed onto the proxy watch rule.** 105 names pass every measured core leg (and op > 0) but are dropped because the proxy fails. 90 of them fail the proxy "C" (no 2-quarter EPS streak and revenue < 20%). Examples:
   - ASML: EPS q +28%, RS 92.5.
   - DELL: EPS q +282%, RS 97.
   - Recruit ×3 lines.
   - Ross, Garmin, WuXi AppTec.
   - That is more names than the archetype holds (97).
2. **40 fires take the unmeasured route**, mostly OTC lines without `fqx_eps_q_yoy`. On that route every other core leg is skipped, including `fg_ni_ps_3y`, which is present:
   - Neste NTOIF/NTOIY pass with NI per share -92% over 3 years and revenue -8%.
   - SNDK passes with no EPS print.
   - BeiGene 49BA.F passes with `fqx_eps_accel` -169.

Other points:
- 83 of 97 fires satisfy proxy C through revenue only.
- `fqx_eps_q_yoy` reaches 302x on Niutech, the top spirit name, from a near-zero base.
- 7 fires are financials. CANSLIM can apply to them, so this is acceptable.

**Coverage** (NaN % universe / mb_base): fqx_eps_q_yoy 54.1 / 31.6; ts_rs_pct_mkt 23.5 / 0; fqx_eps_accel 60.8 / 39.2.

**Fires / sanity:**
- Fit: Jentech 3653.TW, Auras 3324.TWO, Zaptec, ARROWGREEN.NS, MSFT (marginal: r52 +1.8%).
- Do not fit: Neste ×2, Niutech (base effect), BeiGene.

**Severity:** BUG (measured-mask logic), with TIGHT and LOOSE effects.

**Fix:** for measured names, use the core in place of the watch rule rather than AND-ing them. Define `measured` per leg, so `fg_ni_ps_3y` and ROCE always apply when present.

## arch_diversified_segments (242 fires, median mcap $5.9B)

**Intent** (L2248-2249): "4+ segments AND HHI <= 0.40. Real diversification of revenue streams." It is a descriptor and is not counted in density (`_NOT_COUNTED` L9733).

**Code** (L2250-2261):
- `segment_count ≥ 4` (s() zero-fills NaN, so NaN fails), HHI ≤ 0.40, FCF or EBITDA margin, `_roce_now_ok`, `_not_melting`.
- The reconciliation guard (segments sum to 0.8-1.2x revenue, L437-446) applies **only to the FMP fill** (`fmp_seg_hhi_rec`). The EDGAR `segment_revenue_hhi` is used unreconciled.
  - 44 fires have FMP coverage outside [0.8, 1.2]. Ford's segments cover 7% of revenue (coverage 0.07); EPD's are 3.5x.
  - 40 fires use the FMP HHI fill.
- **CELG-RI**, a Celgene contingent value right, is the #1 spirit fire with 20 "segments" (BMS's). It is a non-common leak.
- 32 fires have op margin < 0: INTC, APD, IFF, CAG.

**Coverage:** segment_count NaN 87.7% universe / 81.0% mb_base; FMP segment fields NaN 90.9%. **238 of 242 fires are US.** The archetype is effectively blind outside EDGAR filers.

**Fires / sanity:**
- Fit: ITW (8 segments, HHI 0.13), EMR, PEP, YUM, KO.
- Do not fit: CELG-RI; Ford (7% coverage); INTC.

**Severity:** LOOSE (unreconciled EDGAR HHI, CVR leak) and TIGHT (non-US coverage).

**Fix:** apply the 0.8-1.2 coverage guard to the EDGAR HHI too, and add `-RI` / CVR to `_is_noncommon`.

## arch_lynch_evgy (1,346 fires, median mcap $210M)

**Intent** (L2758-2764, 2809-2811): EV/EBITDA ÷ (growth% + yield%) ≤ 0.6, where growth is "min(TTM EBIT growth, 3y revenue CAGR), capped at 50% — one hot EBITDA year no longer manufactures a cheap ratio."

**Code:**
- Watch rule (L2800-2804): `ev_ebitda_gy` in (0, 0.6], EBITDA > 0, `_ev_sane`.
- Core (L2812-2826): `_evgy_d ≤ 0.6`, measured where `_g_ev` is present. The core removes 4,774 of the 6,116 measured watch names (3,934 for growth < 8%).

Findings:
- **The min() collapses to one side when the other is NaN** (`pd.concat(...).min(axis=1)` skips NaN). 354 of 1,272 measured fires have no 3y revenue CAGR, so their growth is the single-year EBIT print (KQ names: EBIT +85% to +104%, capped at 50%). This is the exact "one hot year" the comment rules out.
- 364 fires sit at the 50% cap.
- **Cyclical peaks pass:**
  - 433 fires have TTM op margin > 1.5x their through-cycle median.
  - NVDA, MU (EBIT +906%), SNDK, Newmont, Agnico Eagle.
  - Lynch's own rule is to avoid low P/E cyclicals at peak.
- 74 unmeasured fires keep the watch rule. 70 fires overall have op margin < 0: Telefonica Chile -19%, SUNIC -50%.
- The top spirit names are EV/EBITDA artifacts:
  - TEKCF: EV/EBITDA 0.086, op margin 99.5% (revaluation gains), fq_rev_growth -103%.
  - Teka TEKA3.SA: mcap $4M.

**Coverage** (NaN % universe / mb_base): ev_ebitda 48.9 / 18.5; `_g_ev` 18.7 / 0.8; ev_ebitda_gy 71.6 / 52.2.

**Fires / sanity:**
- Fit: Hankukpackage, Modi Naturals (EV/EBITDA ~8, growth 20-30%).
- Do not fit: NVDA and MU (peak), TEKCF, Silver Elephant (mcap $6M, EBIT +554%).

**Severity:** LOOSE.

**Fix:** require both growth legs to be present (else unmeasured), `op_margin > 0`, and `fqx_opm_ttm ≤ 1.5×tc_med_opm` (no peak margin).

## arch_wolf_compounder (165 fires, median mcap $45M)

**Intent** (L3622-3626): "a sustained, ACCELERATING grower bought at a single-digit/low-teens multiple, margins expanding, cash-positive, low dilution. Isolates the multi-quarter streak."

**Code** (L3632-3648): mcap $10-150M, revenue ≥ $10M, rev 25-150%, `rev_accel > 0`, streak ≥ 3 (NaN-permissive), `_op_viable`, `_roce_now_ok`, dilution ≤ 5%, CFO or FCF > 0, `oper_lev_any | _wolf_oplev_ttm`, cheap multiple, `low_sbc_wolf`.

Several legs do not do their job:
- **No-op legs** (each removes 0 of 164):
  - `oper_lev_any` (L3024) is any positive YoY margin delta or any positive TTM/raw-sequential print. 147 of 165 fires pass through it rather than the TTM operating-leverage measure (18).
  - `low_sbc_wolf`.
  - `_roce_now_ok`.
- 36 fires show neither EBITDA nor op margin expanding, against "margins expanding" in the thesis.
- **The streak is vacuous for 95 of 165 fires** (NaN streak passes), and 96 have no quarterly revenue. So "multi-quarter" is unmeasured for 58% of fires; growth is the annual `rev_yoy`.
- 6 fires show stale annual growth: Nippon Pigment (annual +42%, latest quarterly TTM +5%), WILLPLUS (+86% vs +9%).
- `shares_yoy` is NaN for 52 fires, so low dilution passes unobserved.

**Coverage:** venues are IN 55, KR 31, JP 20, US 7. The streak and quarterly gaps cluster in IN/KR.

**Fires / sanity:**
- Fit: SEAFCO.BK (rev +47%, streak 5), Keen Ocean, ZJK, SamYoung 003720.KS.
- Do not fit: BIFIDO (op margin -11%), Nippon Pigment and WILLPLUS (decelerated), DeviceENG (top spirit, no quarterly panel).

**Severity:** LOOSE.

**Fix:** make the operating-leverage leg `_wolf_oplev_ttm | (ebitda_margin_delta_yoy ≥ 0.02)`, require the streak to be observed (fall back to `fq_rev_growth ≥ 0.20`), and drop the no-op legs.

## arch_cluseau_buyback_accel (74 fires, median mcap $395M)

**Intent** (L3966-3971): "buybacks accelerating into a discount ... this year's shrink faster than the 3-year trend — a >= 3% pace, and a cash-LIGHT balance sheet."

**Code** (L3972-3989):
- P/TB < 1 is the binding leg (removes 659 of 733).
- Pace leg: buyback yield ≥ 3% or FY yield ≥ 3%.
- `_cl_accel` = (count shrink faster than the 3y trend) OR (`by0 ≥ 3%` and `by0 > by1 ≥ by2`).
- Cash deployed removes 130 of 204.

Findings:
- **The FY-yield acceleration path never checks the share count.** 28 fires qualify only through it; 7 have shares_yoy > 0 and 16 have quarterly `fq_shares_yoy > 0`:
  - Barratt BTDPF: shares +41.6% (the Redrow merger).
  - Samjin: quarterly shares +3.3%.
  - Manho Rope: `fq_shares_yoy` +1,120%.
- 11 fires are a first buyback (`by1 = by2 = 0`), which is not acceleration: JECC.JK, Woongjin Thinkbig, Juki, Lotte Shopping.
- SGLMF (Starhill Global REIT) leaks past `is_operating`. Four fires show a pace > 20% (artifacts, e.g. ASLE's 62% "buyback").

**Coverage** (NaN % universe / mb_base): p_tb 48.9 / 24.1; buyback_yield 54.4 / 27.6; fmp_st_buyback_yield_y0 22.3 / 6.2.

**Fires / sanity:**
- Fit: MegaChips (count -27.6% vs -5.8%/yr), KB Home, Century Communities, Fukuyama Transporting.
- Do not fit: Barratt, Manho Rope, SGLMF, first-buyback names.

**Severity:** LOOSE.

**Fix:** require `~(fq_shares_yoy.fillna(shares_yoy) > 0)` on both acceleration paths and `by1 > 0` on the FY path.

## arch_forensic_payout_confirmed (3,579 fires, median mcap $397M)

**Intent** (L5992-6000): "Any forensic / hidden-value member that is ALSO returning capital ... **earns an EXTRA archetype count, which is this system's native ranking boost**."

**Code** (L6001-6019):
- `_payout_any`: dividend + buyback ≥ 3%, or count ≤ -1%, and not ≥ 2 uncovered payout years.
- AND any of 11 forensic member archetypes.
- My reconstruction gives 3,637; the published 3,579 is after the scrubs.

Findings:
- **The flag is in `_NOT_COUNTED` (L9733-9734), so it adds no density.** The comment describing it as a ranking boost is false.
- It fires on 43% of all forensic members (3,579 of 8,360), so it is barely selective.
- Covered payout is not enforced on the current year:
  - 338 fires have negative TTM FCF: VW ×6 lines, RCL, Nippon Steel, Tenaga.
  - 1,509 have one uncovered payout year in three.
- 40 fires have a total yield > 25%: TOUR (Tuniu, 25.7% dividend + 13% buyback on negative FCF), NOVATECH 24.7%.
- CCZ (Comcast exchangeable ZONES) sits at #5 with a "buyback yield" of 36%.
- 111 fires are financials through `book_compounder_discount`.

**Coverage:** inherits from its members. Venues: US 953, JP 617, KR 269.

**Severity:** COSMETIC (misleading comment, no effect) and LOOSE.

**Fix:** either count it (and require `fcf_ttm > 0` and yield ≤ 25%) or delete it and fix the comment.

## arch_lifo_hidden_reserve (10 fires, median mcap $304M)

**Intent** (L4472-4477): "LIFO reserve is a hidden asset ... Buy at/below the LIFO-ADJUSTED book (reported book + reserve)."

**Code** (L4476-4489):
- After-tax reserve ≥ 10% of mcap removes 21 of 31; adjusted book ≥ 1 removes 11 of 21.
- `_adj_book_f15 = (1/pb).where(pb > 0) + lifo_pct`, but **`pb` is `s('pb', 99.0)` (L882).** A NaN P/B becomes 99, giving 1/99 = 0.01. The "priced below adjusted book" test then reduces to "reserve ≥ ~99% of mcap".

**6 of 10 fires are artifacts:**
- **Five are CHS Inc. preferred lines** (CHSCM, CHSCN, CHSCP, CHSCL, CHSCO). Each carries the whole cooperative's $618M LIFO reserve against a ~$300M preferred-class cap (161% of mcap), with pb NaN → 99. `_is_noncommon` misses them: the names say "Chs Inc." and the base "CHSC" is not in the universe.
- **ACH** (Chalco ADR, delisted from NYSE): mcap $83M against a 658M reserve, giving 626% of mcap. This is stale and currency-mixed.

Genuine fits: NACCO (P/B 0.69 + reserve 14%), Hooker Furniture, Oxford Industries, Ryerson (P/B 1.02 + reserve 10.7%), though OXM and HOFT have op margin ≤ 0.

**Coverage:** lifo_reserve is present for 259 names (226 US). This is US-EDGAR only by construction.

**Severity:** BUG.

**Fix:** use `_ncol('pb')` (NaN → unmeasured, fail), add "-preferred-by-cap" detection (class mcap < 0.5x the company's book with NaN pb), and require `_fx_coherent`.

## arch_xr_forensic_multiple_gap (360 fires, median mcap $689M)

**Intent** (L4627-4631): "the market prices the ACCOUNTING multiple ... while the FORENSIC earnings power — owner earnings (latest or 5-yr average) — implies <= 6x."

**Code** (L4632-4644):
- `_oe_best` = `_oe_loc` (= NI + D&A − max(capex_ttm, capex_avg), L4270) else `oe_avg`.
- Legs: 1.5 ≤ mcap/OE ≤ 6, P/E ÷ OE multiple ≥ 2.5, NI > 0, CFO/NI ≥ 1 where measured, dilution ≤ 5%, `_fx_coherent`, `_not_melting`.

**Currency mixing in D&A.** `da_ttm` stays in the reporting currency while NI, capex_avg (converted at L572-576) and mcap are in the listing currency. On cross-currency lines OE is inflated by the FX rate:
- TOELF/TOELY (Tokyo Electron): D&A ¥81.3B is added to NI of $5.0B, giving OE of $85B, a "1.8x" multiple and P/E 31. The home line 8035.T does not fire.
- NTDOY/NTDOF (Nintendo): ¥18.6B D&A on $3.0B NI.
- CUAEF/CSUAY (China Shenhua): CNY 25.8B on $8.1B NI.
- WMMVF/WMMVY, Reitmans RTMNF/RTMAF.

**214 of 360 fires have D&A > EBITDA** (impossible with positive EBIT): 129 are cross-currency lines (`fq_fx_to_master` outside [0.8, 1.25]) and 78 have inconsistent same-currency data, e.g. VW ×6 lines with D&A 39.5B vs EBITDA 19-22B. The median OE/NI among fires is 4.7x (max 616x). 237 fires have a statement-history owner-earnings yield below 8% (56 below 0), i.e. the independent source disagrees.

**Coverage** (NaN % universe / mb_base): `_oe_loc` 43.0 / 8.8; oe_avg 26.8 / 5.0; p_e 50.2 / 26.6.

**Fires / sanity:**
- Fit: DXC (OE from real D&A; 1.8x vs P/E 15), Hiap Tong, Khind.
- Do not fit: TOELF, NTDOY, CUAEF, the Volkswagen lines, Reitmans OTC lines.

**Severity:** BUG.

**Fix:** convert `da_ttm` with `fq_fx_to_master` (or with revenue_ttm_usd/revenue_ttm ÷ market_cap_usd/market_cap) before `_oe_loc`. Reject rows with `da_ttm > 1.05×ebitda_ttm`. The same fix applies to owner_earnings_power, depreciation_cliff and insider_capitulation.

## arch_xr_wc_normalization (152 fires, median mcap $146M)

**Intent** (L4845-4849): "a one-cycle inventory/receivables GLUT crushed reported FCF ... while margins and demand stay intact."

**Code** (L4850-4871):
- Earnings yield ≥ 8% removes 550 of 702; FCF yield < 2% removes 347 of 499.
- The WC-mechanism OR: cash short of earnings with any glut, or DIO +15, or DSO +10, or inventory vs COGS +15pp.
- Then revenue ≥ -5%, gross-margin delta ≥ -3pp, nde < 3, no Beneish, no receivables-divergence flag, DQ, dilution.

Findings:
- 31 fires have `cfo_yield ≥ earnings_yield`, meaning no working-capital drag on CFO at all. Their FCF is broken by capex: 61 fires have capex > 1.5x D&A. BMTR.JK (CFO yield 76%, capex 2.5x D&A) passes on DSO +21 alone.
- The comment says "a DSO-led glut is the red flag, not the setup", yet `ddso ≥ 10` is a stand-alone setup leg. 32 fires are DSO-led with no inventory build.
- 55 fires had negative FCF in half or more of their 8 years, i.e. chronic rather than one-cycle.

**Coverage** (NaN % universe / mb_base): fq_dio 41.3 / 15.1; fq_dso 43.2 / 17.2; fq_inv_vs_cogs 66.8 / 37.9. Venues: JP 53, KR 23, US 17.

**Fires / sanity:**
- Fit: Charoong Thai Wire (DIO +34, inventory +27pp, CFO yield -14%), Poongsan, HDC Hyundai EP, Yokohama Rubber.
- Do not fit: BMTR.JK; TCOM (CFO yield 0.0003 looks like a data error).

**Severity:** LOOSE (minor).

**Fix:** make `cfo_yield < earnings_yield − 0.03` mandatory and the glut legs corroborating; require `tc_fcf_pos ≥ tc_fcf_years/2`.

## arch_xr_reusable_assembler (514 fires, median mcap $2.19B)

**Intent** (L5046-5056): "incremental margins running ABOVE the average margin ... an ASSET-LIGHT base ... SELF-FUNDED ... durable, and bought at a growth-adjusted price. CoStar/Gartner/FactSet/MSCI/IDEXX class."

**Code** (L5057-5077):
- Reuse leg removes 424 of 938; asset-light removes 405 of 919.
- Reuse: annual incremental EBITDA margin ≥ 30% and above the average, OR TTM incremental EBIT ≥ 30%.
- Also: self-funded, EBITDA margin ≥ 15%, growth, price, dilution.

Findings:
- **`incremental_ebitda_margin` is not domain-clipped.** The TTM lens is clipped to ≤ 1 at L1265; this one is not. 53 fires have > 100%: SAP 1.57, Kyungbang 1.64, max 9.1. Above 100% the code's own L1260-1264 says this is "a different fact from operating leverage".
- **The growth leg's `rev_3y_cagr ≥ 0.12` is dead** (shared fact), so growth is a 6-quarter streak (377) or TTM ≥ 12% (131 fires on that alone).
- "Durable", per the thesis, is not tested on returns: 239 of 514 fires have lindy ROIC < 8% (Clear Secure -20%, D-BOX -3.6%).
- The `_financing_fragile` leg removes 0; `_not_melting` removes 0.
- 215 fires qualify on a single annual incremental print (no TTM confirmation).

**Coverage** (NaN % universe / mb_base): incremental_ebitda_margin 64.9 / 40.6; fqx_inc_ebit_margin_dt 68.7 / 49.4; evsg 62.7 / 44.0.

**Fires / sanity:**
- Fit: NFLX, Kinaxis, Spectra Systems, Electromed, NVDA.
- Do not fit: SNDK (memory-cycle incremental margin 1.16), SAP via 157% incremental, Clear Secure (lindy ROIC negative), Philip Morris (ROIC fine but not a reuse engine).

**Severity:** LOOSE.

**Fix:** clip `incremental_ebitda_margin ≤ 1.0`, read `revenue_3y_cagr`, and require `roic_lindy ≥ 0.10`.

## arch_xr_oneoff_loss_mask (74 fires, median mcap $458M)

**Intent** (L5372-5381): "A business GUSHING cash ... that nonetheless reports a GAAP NET LOSS — a goodwill impairment, restructuring charge ... the loss is a NON-STRUCTURAL charge."

**Code** (L5382-5394): NI < 0, EBITDA margin > 15%, gross margin > 15%, FCF yield > 3%, EV/EBITDA ≤ 9, leverage, CFO − NI ≥ 0.5×|NI|, dilution, DQ. There is no `_not_melting` (by design).

Findings:
- **"One-off" is never tested.** 29 of 74 fires have a negative 5-year average NI and 16 had losses in ≥ 3 of 8 years. HLS Therapeutics lost money in 7 of 8 years; Bumble (op -63%, 3 loss years) is in the top 6 by spirit. A recurring loss is the opposite of the thesis.
- 27 fires have an operating loss, not just a below-the-line charge. Some fit (impairments in opex, e.g. KHC, TAP); some are structural (BMBL, TRLV -24%).

**Coverage:** venues US 33, CA 11. 23 of 74 fires are Energy (E&P impairments, which fit).

**Fires / sanity:**
- Fit: KHC, TAP, Continental, Frontera, Pharos, Talos (impairment years).
- Do not fit: BMBL, HLTRF, GLIBA (op -38%).

**Severity:** LOOSE.

**Fix:** add `~(ni_avg < 0) & ~(tc_loss_years ≥ 3)`.

## arch_xr_deferred_revenue_lead (375 fires, median mcap $1.30B)

**Intent** (L5581-5590): "the SaaS / subscription / prepaid book ... yet the market prices the CHEAP trailing tape."

**Code** (L5591-5608): deferred revenue ≥ 15% of revenue (removes 5,714 of 6,089), building, not shrinking (NaN-permissive), cheap, dilution, earning, `_not_melting`.

Findings:
- **The cheap leg is an OR that includes `fcf_yield ≥ 3%`.** 99 fires are "cheap" only by FCF yield:
  - GE Vernova: EV/EBITDA 96, EV/Sales 5.8.
  - Tencent ×3 lines: EV/Sales 4.4.
- "Building" is unobserved for 150 fires: `fq_defrev_growth_minus_rev` is NaN for 90.8% of the universe, so for them building = revenue growth ≥ 5%.
- The forward book is often a contract or customer-deposit liability rather than a subscription float. Top industries among fires: Machinery 36, Aerospace & Defense 32, Construction & Engineering 27, Airlines 10 (ticket liability). Software accounts for 70.

**Coverage** (NaN % universe / mb_base): deferred_revenue 41.4 / 14.2; defrev ratio 48.3 / 17.5.

**Fires / sanity:**
- Fit: GetBusy, VITA 34, Segue, Technip Energies (backlog advances).
- Do not fit: GEV, Tencent (not cheap), airline lines.

**Severity:** LOOSE.

**Fix:** cheap = `(ev_sales ≤ 3) | (ev_ebitda ≤ 12)` with FCF yield as a weight; require `fq_defrev_growth_minus_rev` observed where `fq_defrev` exists.

## arch_coiled_fallen_angel (76 fires, median mcap $283M)

**Intent** (L7469-7473): the fallen-angel variant of the coiled base — "a base formed >= 40% below the prior 5-year high." The coiled base itself (L7382-7390) is "value accretes under a flat price (the COIL), the market is not watching or does not believe (PERCEPTION LAG)."

**Code** (L7395-7480):
- Time block removes 795 of 872; fallen leg (`bs_prior_dd ≤ 0.6`) removes 190 of 267.
- Then coil, perception, validity, the per-share/never-deep-loss/sales guards.

Findings:
- **Perception relies on NaN.** 44 of 76 fires are "neglected" because both `sent_n_analysts` and `n_analysts` are NaN. All 11 fires above $5B are OTC/ADR lines of heavily covered companies:
  - SEMHF (Siemens Healthineers).
  - DKILY/DKILF (Daikin).
  - DNZOY (DENSO).
  - GXYYY (Galaxy Entertainment).
  - CIADY (Mengniu).
  - STEAV.HE (Stora Enso).
  - SPXSY (Spirax-Sarco).
  - EVVTY (Evolution).
  - OMRNY, TMSNY.
- **The coil is weak for 34 of 76:** their only coil lens is `fmp_dyn_unrerated_gap ≥ 0.15` (multi-year revenue CAGR minus the EV/Sales change). For any stock that fell 40%+ this is close to automatic.
- Eolus Vind is the #1 spirit fire with TTM op margin **-457%**. `tc_min_opm` (-8.6%, annual) does not see the TTM, and `_coil_real` passes through FCF > 0.

**Coverage** (NaN % universe / mb_base): bs_prior_dd 29.0 / 5.0; bs_coil_ebit 67.1 / 43.8; sent_n_analysts 73.7 / 43.6.

**Fires / sanity:**
- Fit: Songwon, Andhra Sugars, NANTEX, User Local (small, measured ≤ 3 analysts, EBIT coil).
- Do not fit: the 11 large ADR lines, Eolus.

**Severity:** LOOSE.

**Fix:** neglect = measured count ≤ 3, or NaN only when no same-name sibling line is covered and mcap is below the country 60th percentile. Count `unrerated_gap` only alongside a revenue or EBIT coil. Add `op_margin > -0.20`.

## arch_mb_quiet_turn (662 fires, median mcap $884M, 79 > $10B)

**Intent** (L7592-7598): "against same-state lookalikes, the winners had WEAKER recent price action while revenue accelerated and EBIT grew, and were cheaper than their own history."

**Code** (L7596-7606):
- Weak tape (`ts_r13 < 0` and 52-week distance < 0.85) removes 1,071 of 1,733.
- Fundamental turning (rev_accel > 0 or quarterly growth ≥ 10%, plus EBIT TTM growth > 0 or a turn).
- Margin trend (8-quarter slope with consistency ≥ 0.6, or a dated inflection).
- ROIC trend.
- Cheaper than own history: 3y EV/Sales change < 0 OR 1y < 0.

Findings:
- **No sanity cap, no viability floor.** The top spirit fires are base-effect shells: GXAI (rev_accel 464, `fq_rev_growth` +2,922%, op -116%, `opm_slope8` 161), BZAI (op -194%), RYTHM (rev_accel 960), FIEE (`fqx_opm_slope8` 383). 113 fires have op margin < 0.
- The weak-tape leg passes 42% of `_mb_base`; the ROIC trend passes 73% (removes 29).
- 418 fires have `fqx_rev_accel_now = 0`, i.e. revenue is not accelerating on the quarterly shape the code prefers elsewhere. 244 are "turning" only on the annual `rev_accel` with quarterly growth below 10%.
- 244 fires are "cheaper than own history" only on the 1-year EV/Sales change. 272 fires sit above their own 3-year EV/Sales median.
- Large, well-covered names pass: COST (op-margin slope 0.0003, flat), NFLX, IBM, MCD. 155 fires have ≥ 10 analysts.

**Coverage** (NaN % universe / mb_base): fq_rev_growth 43.8 / 17.6; fqx_ebit_ttm_g 56.9 / 33.6; fqx_opm_slope8 35.0 / 7.4.

**Fires / sanity:**
- Fit: C.T.I. Traffic, Qualicorp, CPSH (small, EBIT up, margin trend).
- Do not fit: GXAI, BZAI, RYTHM, COST, MCD.

**Severity:** LOOSE.

**Fix:** clip rev_accel / growth / slope to sane bands (e.g. rev_accel ≤ 1, `fqx_opm_slope8 ≤ 0.1`). Add `op_margin > -0.10`, require `fqx_rev_accel_now = 1` where measured, and require `evh_evs_vs_med_3y < 0` where measured.

## arch_mb_conviction_confluence (33 fires, median mcap $283M; all US)

**Intent** (L7676-7680): "insider conviction inside the smart-money wreckage ... literal confluence: insiders PLUS a second, independent arrival."

**Code** (L7560-7566, 7630-7634, 7681-7683): `mb_fallen_insider` (109) & `mb_smart_money_wreckage` (234) & `_smart_legs ≥ 2`. The legs are insider ≥ 2 quarters, SC 13D ≤ 1 year, headcount +10%, and `fmp_inst_new_q0 ≥ 1`.

Findings:
- **The second-arrival leg is close to a no-op.** `fmp_inst_new_q0 ≥ 1` (at least one new 13F holder this quarter) is true for 76.9% of the US liquid base (median 39 new holders). 30 of 33 fires carry it; 13D carries 20; headcount 3. The intersection is 34 rows before scrubs, so the extra leg removes about 1 of 34.
- Fallen and deep value can be a dilution artifact. GPUS (Hyperscale Data) has `shares_yoy` +9,945% and `ts_dist_hi260` 7e-8, i.e. its "fall" is per-share dilution. No share-count guard exists, unlike the fallen-angel and coiled siblings.
- Operating condition: 20 of 33 fires have op margin < 0 and 12 have negative FCF. WW (shares -87%, post-reorg) is in the set.

**Coverage:** US only by construction (Form 4, 13F, 13D).

**Fires / sanity:**
- Fit: THRY (EV/EBIT 43 though), CNXC (EV/EBIT 8.8, FCF 26%), PTLO, SMPL, O-I.
- Do not fit: GPUS, SST (op -51%), ALIT (op -96%).

**Severity:** BUG (the defining "second independent arrival" leg is a no-op).

**Fix:** make the institutional-arrival leg relative (new holders ≥ 25% of `fmp_inst_holders_q0`, or top quintile of `inst_own_excess_q0`), and add `~(shares_growth_3y > 0.20)`.

## arch_xr_value_unlock (199 fires, median mcap $278M)

**Intent** (L5858-5865): "A CHEAP security whose management/board is actively SIGNALLING intent to realise / crystallise / unlock latent value ... OR a structured unlock event already in motion ... The cheapness is the margin of safety."

**Code** (L5866-5893):
- The catalyst leg removes 7,152 of 7,351; cheap removes 415 of 614.
- Catalyst: fresh language ≤ 400 days, or events (spin, tender, merger, going-private, SC 13D ≤ 180 days below $2B).
- Cheap: P/B < 1 | NCAV ≥ 1 | net cash ≥ 30% | EV/EBITDA ≤ 6 | `forensic_hidden_pct ≥ 0.20`.

Findings:
- **The `forensic_hidden_pct` cheap leg is dead.** It reads `s('forensic_hidden_pct', 0)` at L5884, but the column is first created at L9528 and is not in the master, so it is 0 everywhere. The same applies to the `_vu_forensic` confirmation leg at L5912.
- **No leverage guard on "cheap".** P/B < 1 on an over-levered stub passes. The top 4 spirit fires carry net debt of 12-19x their market cap: SPRU -18.0, HAIN -12.0, GETY -18.9. Every one of them has P/B < 0.5. That is equity optionality, not a margin of safety.
- **CCZ** (Comcast ZONES debenture) is #7 by spirit: a non-common leak.
- 116 of 199 fires qualify by event only. The event flags (`merger_flag`, `tender_flag`) are undated. LEN/LEN-B pass on a tender flag; CHTR passes on a merger flag.
- `unlock_days_ago` was computed on 2026-09-14 and is 18 days stale. Only 1 fire crosses 400 days as a result.
- 90 fires have op margin < 0.
- GVH ($2.4M mcap) fires just above the $2M shell scrub.

**Coverage:** EDGAR text, so effectively US (186 of 199).

**Fires / sanity:**
- Fit: KHC (strategic review), MGA, Identiv (sale process plus net cash), BATL.
- Do not fit: SPRU, HAIN, GETY (levered stubs), CCZ.

**Severity:** LOOSE, plus COSMETIC (dead leg).

**Fix:** move the `forensic_hidden_pct` computation above L5858 (or drop the leg). Require `net_cash_pct_mcap ≥ -1.0` (or `nde ≤ 4`) on the P/B branch. Date the event flags.

## arch_asleep_unrerated (815 fires, median mcap $3.0B, 234 > $10B)

**Intent** (L6453-6465): "the market has been REPEATEDLY told ... and STILL has not re-rated the name ... through ANY lens". "Not re-rated" needs ≥ 2 lenses. The not-already-rich guard is "missing = permissive".

**Code:**
- Parent `arch_asleep_at_wheel` tier core (7 of 8 beats, or 4/4 with ≥ 2% surprise; L6420-6432).
- `_no_rerate_au` = ≥ 2 of 8 lenses (L6484-6495). My lens rebuild matches the local on 46,526 of 46,526 rows.
- `_not_rich_au`, `_not_melting`, then the tier core (1-year coil ≥ 0 or the 2-year coils; L6516-6520). The tier removes 312 of 1,127.

Findings:
- **Lenses a/b/c are one fact.** EV/Sales change, price lagging fundamentals and implied P/E expansion are all 12-month price vs 12-month fundamentals. b implies c on 1,197 of 1,217 asleep names. 143 fires reach "≥ 2 lenses" using only that trio.
- **`_not_rich_au`'s "both missing" leg is dead.** `ev_ebitda_v` is `s('ev_ebitda', 99.0)` and never NaN. 156 asleep, unrerated names with no P/E and no EV/EBITDA fail, contrary to the comment.
- **There is no `is_operating`.** 229 fires are financials (153) or real estate, where EV/Sales lenses are meaningless.
- Already re-rated names pass. 29 fires have r52 > 50%:
  - The Samsung GDR BC94.L is up 249%. It passes the measured core because `fq_rev_growth` on the GDR line reads +248% (a unit error).
  - AMZN: r52 +52%, `_c1_au` 0.019.

**Coverage:** evt_beats_8q / earnings_beat_rate reach covered names only. Venues: US 457, IN 56, TW 41.

**Fires / sanity:**
- Fit: ZTS (8 beats, -50%), ADBE, PLNT, Zoetis-type names; Tencent (8 beats, r52 -31%).
- Do not fit: BC94.L, AMZN, CHGG (revenue -39%), banks.

**Severity:** LOOSE, plus COSMETIC.

**Fix:** count a/b/c as one lens (so ≥ 2 needs an independent EV-history or coil lens); test `_not_rich` on `_ncol('ev_ebitda')`; add `is_operating` or a bank-specific lens.

## arch_analyst_awakening (1,656 fires, median mcap $5.54B, 599 > $10B)

**Intent** (L7141-7151): "Analysts are pounding the table but the market has only STARTED to pay: CONVICTION triangulated ... without an extended trailing run." The core "AWAKENING is a CHANGE: perception moving ... or the price turning" (L7222-7226).

**Code** (L7152-7232):
- Watch rule (2,383): ≥ 3 analysts, rating ≤ 3, conviction, not extended, not in freefall, live tape.
- Core: ≥ 1 sentiment-change lens, or Mansfield RS rising with r13 > 0. It removes 727.

Findings:
- **Conviction is satisfied by a rating ≤ 2.2 alone.** `conv_score ≥ 0.5` with only two lenses means one is enough. 764 of 1,656 fires have upside < 25%, and 280 have upside < 10%:
  - AAPL: rating 2.18, upside -0.06%.
  - NSA: rating 2.83, upside 1.6%, the #1 spirit fire, which passes on ≥ 2 sentiment changes with no tape data.
- The fire set is the most-covered stocks in the world: 293 fires have ≥ 20 analysts; NVDA, AAPL, GOOG, MSFT, AMZN, AVGO are all in. "Pounding the table but the market only started" does not describe them.
- **The change leg admits worsening perception.** 676 fires pass on the RS-only route. 202 fires have the buy share **falling** ≥ 10pp and 99 had targets cut ≥ 5%: SAP (PT -17%), IBM, CRM, TMUS, MCD.
- The `sent_initiations_12m ≥ 1` lens is dead (0 rows).

**Coverage** (NaN % universe / mb_base): yf_recommendation_mean 86.5 / 69.3; analyst_target_upside 74.3 / 44.9; sent_buy_share_d12 75.6 / 47.1. So the archetype only sees covered names (expected).

**Fires / sanity:**
- Fit: Unity (rating 1.46, upside 35%, buy share +40pp, 12 upgrades, r52 -3%), RBRK, AVAH, AZTA.
- Do not fit: AAPL, MSFT, NSA, SAP.F, IBM.

**Severity:** LOOSE, plus COSMETIC.

**Fix:** conviction = (rating ≤ 2.2 AND upside ≥ 20%) OR ≥ 2 sentiment changes; veto `sent_buy_share_d12 ≤ -0.10` or `sent_pt_rev_q ≤ -0.05`; drop the initiations lens.

## arch_post_reorg (2 fires: DBD, WW)

**Intent** (L9058-9072): fresh-start equity cheap on OPERATING yield ("EV/EBIT or FCF ... the one discharge gains cannot inflate. WW's real EV/EBIT yield is 5.8% and FCF is negative, so it is now robustly excluded on value").

**Code** (L9085-9145):
- `_reorg` (EDGAR flag) & op & `_not_melting` & `_reorg_value` (EBITDA yield ≥ 10%, or EBIT yield ≥ 10% with sane D&A, or FCF ≥ 8%; mid-cycle for E&M) & leverage & 5-year freshness.
- Freshness removes 8 of 10 (33 of 49 reorg names emerged more than 5 years ago); value removes 2 of 4.

Findings:
- **WW now fires, against its own comment.**
  - EV/EBIT reads 8.8, an 11.3% yield, while the op margin is -30% and FCF yield is -9%.
  - Those two numbers contradict each other on sign.
  - The EBIT behind `ev_ebit` still carries reorganisation items, which is exactly the contamination the comment describes.
- The comment cites Verdad's 20% EBIT yield; the code uses 10%. The comment documents this ("~1 of ~44 clears 20%"), so it is fine.
- `_emg_cut` uses `pd.Timestamp.now()` rather than `_asof` (COSMETIC, not reproducible on reruns).

**Coverage:** `reorg_flag` covers 49 names, 48 of them US (EDGAR ReorganizationValue). The archetype is blind outside US filers.

**Fires / sanity:**
- Fit: DBD (2023 emergence, EV/EBIT 9.9, FCF 9.5%, nde 1.26).
- Do not fit: WW.

**Severity:** TIGHT (coverage), plus LOOSE (sign-contradicted EBIT).

**Fix:** use the EBIT-yield lens only when `op_margin > 0` (sign agreement), and use `_asof` for freshness.

---

## Summary

| archetype | fires | severity | one-line fix |
|---|---|---|---|
| arch_xr_forensic_multiple_gap | 360 | BUG | Convert `da_ttm` to the listing currency (`fq_fx_to_master`) before `_oe_loc`; reject `da_ttm > 1.05×ebitda_ttm` (214 of 360 fires have D&A > EBITDA). |
| arch_lifo_hidden_reserve | 10 | BUG | Use NaN-preserving `pb` (the 99-fill makes P/B "known"); drop CHS preferred lines and stale ACH (6 of 10 fires are artifacts). |
| arch_oneil_canslim | 97 | BUG | Measured core should replace, not AND, the proxy watch (105 core-qualifiers such as ASML/DELL dropped); apply `fg_ni_ps_3y`/ROCE whenever present (Neste NI/sh -92% fires). |
| arch_mb_conviction_confluence | 33 | BUG | "Second arrival" `fmp_inst_new_q0 ≥ 1` is true for 77% of the US base; make it relative; add a per-share fall guard (GPUS +9,945% shares). |
| arch_gayner_wiggle_not_obsolete | 444 | LOOSE | Integrity falls back to master CFO/NI ≥ 0.6 and through-cycle FCF/op-margin ≥ 0.25 (both catch BCG.NS); cap `ts_r52` (40 fires up on the year). |
| arch_durable_reinvestment | 1,854 | LOOSE | ROIIC escape requires `asset_3y_cagr > 0` (163 harvesters); `mcap > 0` (59 delisted lines); ≥ 3 ROIIC windows. |
| arch_lindy_growth | 916 | LOOSE | Cap 3y CAGR / `rev_yoy` base effects (33 of the top-50 spirit names have 3y CAGR > 50%); require `rev_yoy` present. |
| arch_large_cap_quality | 839 | LOOSE | Require `roic_lindy ≥ 0.10` with spot ROCE (256 fires have lindy < 8%: GE, CRM, BeiGene, Bombardier). |
| arch_diversified_segments | 242 | LOOSE | Reconcile the EDGAR HHI too (Ford segments = 7% of revenue); add CVR `-RI` to the non-common filter; 238 of 242 are US. |
| arch_lynch_evgy | 1,346 | LOOSE | Require both growth legs (354 fires use a one-year EBIT print); op margin > 0; no peak margin (433 fires). |
| arch_wolf_compounder | 165 | LOOSE | Replace the no-op `oper_lev_any`; require an observed streak (95 of 165 NaN) and quarterly growth. |
| arch_cluseau_buyback_accel | 74 | LOOSE | Check the share count on the FY-yield path (Barratt +42% shares) and `by1 > 0` (11 first-time buybacks). |
| arch_xr_wc_normalization | 152 | LOOSE | Make CFO < earnings − 3pp mandatory (31 fires are capex-crushed, not WC). |
| arch_xr_reusable_assembler | 514 | LOOSE | Clip incremental EBITDA margin ≤ 1 (53 fires); use `revenue_3y_cagr` (`rev_3y_cagr` 95% NaN); `roic_lindy ≥ 0.10`. |
| arch_xr_oneoff_loss_mask | 74 | LOOSE | Test "one-off": `ni_avg ≥ 0` and `tc_loss_years < 3` (29 fires have a negative 5y-average NI). |
| arch_xr_deferred_revenue_lead | 375 | LOOSE | Drop FCF-only "cheap" (GEV at 96x EBITDA); require observed defrev growth. |
| arch_coiled_fallen_angel | 76 | LOOSE | Neglect from a measured count (44 of 76 are NaN; 11 ADRs > $5B); no coil from `unrerated_gap` alone (34 fires); TTM op floor (Eolus -457%). |
| arch_mb_quiet_turn | 662 | LOOSE | Sanity-clip growth/slope (top spirit = GXAI/BZAI shells); op floor (113 op < 0); quarterly acceleration where measured. |
| arch_xr_value_unlock | 199 | LOOSE | Leverage guard on the P/B branch (top 4 carry net debt 12-19x mcap); move `forensic_hidden_pct` above use (dead leg); drop CCZ. |
| arch_asleep_unrerated | 815 | LOOSE | Count price-lag lenses a/b/c once; NaN-aware `_not_rich`; add `is_operating` (229 financials/REITs). |
| arch_analyst_awakening | 1,656 | LOOSE | Conviction = rating AND upside ≥ 20% (764 fires < 25%); veto falling buy-share/PT (202/99 fires); drop the dead initiations lens. |
| arch_forensic_payout_confirmed | 3,579 | COSMETIC | Comment says "extra count" but it is `_NOT_COUNTED`; either count it with `fcf_ttm > 0` & yield ≤ 25% or delete it. |
| arch_post_reorg | 2 | TIGHT | 49 US-only reorg names; EBIT-yield lens only when `op_margin > 0` (WW fires on EV/EBIT 8.8 with op -30%). |

Cross-cutting fixes that touch more than this batch:
- Convert `da_ttm` per line.
- Repoint the 11 `rev_3y_cagr` reads to `revenue_3y_cagr`.
- Extend `_is_noncommon` to CHS-type preferred lines, ZONES (CCZ) and CVRs (CELG-RI).
- Treat a NaN analyst count as unmeasured, not neglected.
