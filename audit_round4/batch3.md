# Archetype review, round 2, batch 3 (23 archetypes)

Method: I rebuilt every gate from the source files with the same merge order as `compute()` (asymmetry_global, then the plain EDGAR merges, then the FMP overlays where the fresh file wins). The post-fill `_eff` columns come from archetype_tags.csv, and the end-of-run scrubs are applied: non-common, price-ghost, clinical-biotech, sub-$2M shell, EBITDA > 1.1x revenue, mcap < $20M with revenue > $200M, and the >500% revenue-spike scrub on the durability set. Then I matched each rebuild to the published `arch_*` column. **22 of 23 match exactly.** The exception is xr_quality_crisis: 3,393 of 3,402 (9 published-only, from the freshness-coalesced `pct_off_52w_high`).

Universe: N = 46,526 names; operating = 36,173 on my `is_operating` with the yartseva sector fill. "Removes X of Y" means that, of the Y names passing every other gate, this gate alone removes X. Scripts: scratchpad/r2b3/ (loader.py, build.py, common.py, a01..a13.py); the merged frame is F.pkl.

Shared facts used below (in addition to the review_batch1 facts):
- **Cumulative-growth columns.** `fmp_st_ebit_ps_5y_g` (fmp_statements.py:302, `a/b - 1`) and `fg_ni_ps_5y` (fmp_financial_growth.py docstring: "CUMULATIVE") are total growth over five years, not CAGRs. `equity_cagr_5y` and `fg_eq_ps_5y_cagr` are annualised.
- **Missing analyst counts.** `sent_n_analysts` is NaN for 74% of the universe. OTC and second lines of covered companies read NaN, and so they pass every "neglected" leg that treats missing as neglected.
- **Duplicate listings.** Duplicate lines of one company are common across all 23 archetypes. lindy_fcf has 744 duplicate lines, self_funded_returner 379, xr_quality_crisis 295, tax_efficient 175. Effective names are fewer than the fire counts.
- **Sparse columns.** `rev_3y_cagr` (master) is NaN for 95%. The populated series is `revenue_3y_cagr`, which is the FMP-filled `_eff` copy (fill rate 87%). `evh_evs_log_chg_3y` is populated for only 0.2% (51 names), because the EV history reaches about 2 years.
- **Pre-fill reads.** Columns written only as local variables (for example the FMP-filled effective tax rate) are invisible to the later spirit lenses, which read `df[...]`.
- **Non-common lines that escaped the scrub:**
  - TBB, the AT&T 5.35% notes line: mcap $153B, `total_debt` $10.5B against $162.9B on fq.
  - CCZ, the Comcast ZONES exchangeable debenture: mcap $15.5B, P/B 0.17.
  - NCRRP, an NCR Voyix preferred line: mcap $138.8B.
  - Korean preferred lines (code ending 5/7/9): 21 in blindspot, 18 in crisis, 14 in xr_quality_crisis.

---

## arch_gayner_missed_it (347 fires, median mcap $2.85B, 107 > $10B)

Intent (8139-8145): "a long compounding record (per-share EBIT, net income or book compounding >= 12%/yr over 5 years, lindy ROIC >= 12%, profitable 90%+ of years) whose tape has gone sideways — flat over 12 months, or in one of its 20%+ drawdowns ... while the earnings kept growing. No dilution."

Code legs:
- `_g_ps5` (8144) chains `fmp_st_ebit_ps_5y_g` → `fg_ni_ps_5y` → `equity_cagr_5y` → `fmp_st_equity_cagr`, and `_g_record` (8146) compares it with 0.12.
  - **BUG (units).** The first two sources are *cumulative* 5-year growth, so the gate tests 12% over five years (2.3%/yr), not 12%/yr. The book-value fallbacks are annualised, so one threshold is applied to two units.
  - 345 of 347 fires take the EBIT/share source. 162 of 347 (47%) fall below a true 12%/yr (cumulative < 76.2%), and 66 fall below 7%/yr (cumulative < 40%).
  - Examples: 2428.TW +12.1% cumulative (NI/share +9.8%); Geberit (GBERY) +15.7% cumulative with NI/share −3.4%; Logitech +15.5% with NI/share −13%; C.H. Robinson +13.2%.
  - With the correct threshold, the universe passing `record` falls from 2,108 to 1,224.
- `_g_prof_share >= 0.90` (8067): with `tc_years` capped at 8 this means no loss year. All 347 fires sit at exactly 1.0.
- `_g_stalled` (8147): `ts_r52 <= 0.05 | ts_dist_hi260 <= 0.80 | pct_off_52w_high <= -0.20`. **LOOSE.** "Sideways" is not enforced on the drawdown leg.
  - 31 fires are up more than 50% over 52 weeks and pass on `hi260 <= 0.8`: Keystone Microtech 6683.TWO +281%, Sinopower +149%, LRCX +147% (hi260 0.72), AMAT +139%, Tsugami +123%, Bajaj Consumer +114%.
  - The base rate of `stalled` among record & growing names is 63%, so it filters little: it removes 187 of 535.
- `_g_still_growing` (8149): TTM EBIT growth > 0 (342 fires), else the FY. 66 fires grow 0-5%. OK.
- No dilution `~(_g_sh3 > 0)` (8103): removes 243. Integrity removes 51. `_not_melting` removes 0 (a no-op here).

Coverage: `fmp_st_ebit_ps_5y_g` NaN 56% universe / 58% operating; `fg_ni_ps_5y` 12%; `roic_lindy` 12%; `ts_dist_hi260` 26%.

Fires: US 147, JP 49, IN 37, UK 15, ID/CN/TW 13 each. IT 99, Industrials 77. There are 50 duplicate lines; Tencent appears three times (0700.HK, TCEHY, TCTZF).
- Top spirit: Toyokumo 4058.T (r52 −26%, hi260 0.60, EBIT +37%, ROIC 26%), Upsales, Wingstop (−60%), StoneCo, IRCTC. These fit.
- Largest: MSFT (cumulative EBIT/share +137%, r52 +1.8%: a flat year qualifies) fits. LRCX/AMAT/KLAC (+78-147% on the year) do not.
- Random small: Kamakura Shinsho, Expleo (r52 +3%) fit.

Severity: **BUG** (cumulative read as annual), **LOOSE** (drawdown leg admits strong risers).

Fix: compare `_g_ps5` with `1.12**5 - 1` for the cumulative sources (or annualise them first). Make the drawdown leg `(hi260 <= 0.8) & (ts_r52 <= 0.20)`.

## arch_blindspot (1,666 fires, median mcap $46M)

Intent (1812-1830): "Regional Blind-Spot ... tradeable-but-thin in USD ($50k-$2.5M / week), observed neglect (<= 1 analyst), a real operating business."

Code legs:
- Base rule (1819-1825): country in BLINDSPOT_COUNTRIES, `is_operating`, mcap < $400M, `~(sent_n_analysts > 1)`, `(~adv_has) | (adv < 5e5)`.
- Tier (1832): core = operating & weekly dvol in $50k-$2.5M & ≤ 1 analyst, `measured = _dv_wk.notna()`.

Leg checks:
- **ADV leg is dead.** It removes 0 of 1,666 (`avg_dollar_volume` NaN 92%).
- **The `pew_avg_dollar_volume * 5` fallback reaches 0 fires.**
- **The analyst leg is a near no-op.** It removes 1 of 1,667; 1,606 of 1,666 fires (96%) have NaN analysts and 60 have exactly 1. "Observed neglect" is in practice "no record".
- **615 fires (37%) have no weekly panel at all.** `measured` is False for them, so they keep the old rule with no liquidity test. These are the unpriced KR/ID lines; 136 fires are below $10M mcap.
- **"A real operating business" is only the sector test.** 400 fires have op_margin < 0, 113 have op_margin < −20%, and 87 fail `_not_melting`. **LOOSE.**
- Spirit is NaN for 308 fires. The top spirit names are unpriced and unmeasured: Dong A Eltek 088130.KQ, ESTec and Kwangjin Wintec all have NaN dvol and NaN op_margin.

Coverage: `sent_n_analysts` NaN 74%; `ts_dvol26_usd` NaN 23% universe (37% of fires). The list is a fixed 24-country set: it includes IL, misses e.g. MY/EG/PK/NG/KE, and is not a coverage-based frame.

Fires: KR 932 (56%), ID 181, TH 169, TR 119, GR 60, BR 59. 21 fires are KR preferred lines (e.g. 005305.KS Lotte Chilsung pref). Examples: PCSGH.BK (op 17%, dvol $53k) fits; GMFI.JK (1 analyst, op 11%) fits; 010400.KS (op −4.6%) is marginal; unmeasured KR lines do not show the thesis at all.

Severity: **LOOSE** (no viability floor; 37% unmeasured escape), **COSMETIC** (dead ADV leg and pew fallback).

Fix: drop the `~measured` escape (require `_dv_wk` in band), add `_not_melting & op_viable(0)`, and remove the ADV leg.

## arch_lindy_fcf (3,557 fires, median mcap $2.36B, 1,003 > $10B)

Intent (2010-2047): "durability = FCF positive in EVERY one of >= 7 fiscal years at a real margin"; "(audit 3) a LEVEL: through-cycle FCF margin >= 10% or lindy ROIC >= 8%... FCF of +0.1% of sales every year is not lindy".

Code legs:
- Old rule (2035-2046): operating, `_roce_now_ok`, `_not_melting`, roic_after_sbc ≥ 0, `years_of_history >= 5`, ≥ 4/5 FCF and op-income years, and the level leg.
- Tier core `_fcf_all_pos` (2053): all `tc_fcf_years` positive with `tc_fcf_years >= 3`.

Leg checks:
- **The comment says ≥ 7 years; the code says ≥ 3.** Fire windows: 3y 11, 4y 12, 5y 21, 6y 45, 7y 88, 8y 3,361. 89 fires sit below the stated 7. **LOOSE (minor).**
- **Level leg:** 1,021 fires have FCF margin < 10% and pass on ROIC ≥ 8%. 59 average < 3% FCF margin (Ework 0.85%, AmerisourceBergen 0HF3.L 1.0%, Sundrug 1.2%, Ampol 1.3%), which is the case the comment says is not lindy.
- `roce_ok`, `notmelt`, `yh>=5` and `fcfpos>=4` together remove ≤ 13. The core removes 2,378 and the level leg 1,214.
- 73 fires have negative TTM FCF; 144 fires have NaN mcap (London 0xxx.L lines, e.g. 0QTE.L) because there is no mcap gate.

Coverage: `tc_fcf_years` NaN 23% / 21%. Where it is missing, `fmp_st_n_yrs_positive_fcf >= min(5, years)` stands in.

Fires: US 1,360, JP 296, CN 281, IN 191. GTT, Adyen, NVDA, AAPL and Winmark fit. 744 duplicate lines (GTT.PA/GZPZY, TSFA.F). Distributors with 1% FCF margins do not fit.

Severity: **LOOSE** (window and level), **COSMETIC** (no mcap > 0).

Fix: core `tc_fcf_years >= 7` (FMP fallback only when ≥ 7 years); level `tc_fcf_margin_avg >= 0.05` as an AND, with ROIC as the alternative only when FCF margin ≥ 5%; add `mcap > 0`.

## arch_double_inflect (172 fires, median mcap $269M)

Intent (2519-2521): "BOTH NOPAT-ROIC AND cash-ROIC crossed zero from below in the latest year."

Code (2524-2533):
- `roic_inflection_flag == 1 & cash_roic_inflection_flag == 1`. These are filled from `fmp_st_*`, defined at fmp_statements.py:186 as `prior <= 0 < latest` on consecutive FYs. This matches the intent.
- `~(fqx_roic_ttm <= 0)` is NaN-permissive (14 fires unmeasured).
- `rev_yoy > 0` is zero-filled, so NaN fails (fine).
- `_not_melting` removes 1. Shares ≤ 15% removes 12.

Coverage: the flags are NaN for 14% / 24% (they need two consecutive FYs).

Fires:
- 23 have current op_margin < 0 and 16 have roce < 0. The FY cross is not current. Example: BCRX op −33%, roce NaN, spirit 0.81.
- Artifacts: BNC (CEA Industries, now a crypto treasury) `fqx_roic_ttm` 223; AGGI rev +446% with op NaN.
- Fits: giftee 4449.T, Sandisk (ROIC crossed with the memory cycle), STS Group.

Severity: **LOOSE** (minor: no current-state check beyond NaN-permissive TTM ROIC).

Fix: require `op_margin > 0` and `0 < fqx_roic_ttm <= 1` where measured.

## arch_net_cash_returner (1,617 fires, median mcap $134M)

Intent (3206-3210): "net cash >= 30% of market cap AND the company is ACTIVELY returning it ... the legitimate, rewarded form."

Code (3215-3222): `net_cash_pct_sane >= 0.30` (≤ 100%), `_netcash_not_contradicted` (removes 2), the `_returning` OR of five legs, and `_not_melting` (removes 36).

`_returning` is weak:
- Dividend > 1% is the sole leg for 777 fires.
- A buyback yield of any size > 0 counts; 33 fires have < 0.25% and no dividend.
- 92 fires return < 0.5% in total; the median is 4.0%.
- 198 fires grew the share count > 2% on the latest count.
- 348 fires have negative FCF, 274 have op_margin < 0, and 393 had an uncovered payout in ≥ 2 of 3 years. "Returning" here is often cash being drawn down, not surplus distributed. **LOOSE.**

Coverage: net_cash_pct NaN 22%; the buyback lenses 54-69%. The panel shows net debt for 29 fires (sign contradicts).

Fires: JP 493, US 220, CN 178, KR 157. Aumann (net cash 83%, buyback 7.5%) fits; NetEase, Wuliangye and JD (op margin 0.2%) are mechanically in.

Severity: **LOOSE**.

Fix: total yield (dividend + buyback) ≥ 2% with `fq_shares_yoy <= 0`, plus `~(tc_uncov_payout_3y >= 2)` and `fcf_ttm > 0`.

## arch_tax_efficient (1,947 fires, median mcap $954M)

Intent (2201-2203): "effective tax rate < 15% AND positive pre-tax income. Distinguishes legitimate tax structure from 'no tax because no profit'."

Code (2204-2212):
- `effective_tax_rate` (2106) is EDGAR, filled with the quarterly FY rate and then the FMP TTM ratio.
- Band 3-15%; pretax > 0 (EDGAR or fq); cash-tax rate not > 20% where measured; `_op_viable(0)`.

Leg checks:
- **The cash-tax corroboration is a near no-op.** `fq_cash_tax_rate` is NaN for 97% of the universe and for 1,887 of 1,947 fires; it removes 19.
- **There is no loss-history test, so a NOL-shielded name passes.** 708 fires have a loss year in the through-cycle record and 425 have ≥ 2. US fires with ETR < 10%: 152. Examples: ARLO (op margin 1.7%, ETR 3.3%, spirit #1); NCLH and GEV (valuation-allowance releases).
- **BUG (spirit).** The spirit lens (docs/spirit_spec.json) reads `effective_tax_rate` from `df`, which is the pre-fill column. 1,748 of 1,947 fires (90%) therefore have NaN spirit, so `_exceptional`/`_elite` cannot fire for them. This matches the 1,746 fires whose rate comes only from FMP.

Coverage: EDGAR/fq ETR NaN 93% / 94%; FMP ETR 18%. ETR source among fires: FMP 1,746, EDGAR/fq 201. 45 fires have both sources disagreeing by > 10pp, e.g. VICR (EDGAR 3.1% vs FMP −30%).

Fires: CN 805 (490 at 10-15%, the High-and-New-Technology concession, which is legitimate structure), US 356, TW 138, HK 110. MU and AVGO (Singapore incentives) fit; ARLO and VICR do not.

Severity: **BUG** (spirit blind to 90% of members), **LOOSE** (no NOL / loss-history guard; cash rate unusable).

Fix: write the filled ETR back to `df['effective_tax_rate']` (or put the spirit lens on it) and add `~(tc_years - tc_opinc_pos >= 1 in the last 3 FY)` or `fq_cash_tax_rate.notna()`.

## arch_bab_multibagger (871 fires, median mcap $1.13B)

Intent (2668-2670, 2721-2724): "low/declining-beta quality that is ALSO a yartseva multibagger OR very cheap"; "(audit 3) ... no looser than either parent".

Code: `_reframe` (2727) = `_bab_below_avg` (panel beta rank ≤ 0.50) & `_bab_beta_ok` (low third ≤ 0.35, or Yartseva ≥ 0.60) & `bab_quality` (2622) & `_bab_liquid` & (Yartseva ≥ 0.60 | `margin_shock_any` | cheap & `_ev_sane`).

Leg checks:
- **Beta.** 266 fires (31%) sit at beta rank 0.35-0.50 and carry the Yartseva escape. "Below the market median" is not low beta.
- **Multibagger leg.** `margin_shock_any` has a 43% base rate among operating names, and 254 fires pass on the shock alone, so it is not a multibagger signal. Examples: JNJ (EV/EBIT 24, Yartseva 0.39) and AbbVie.
- **Quality.** `(roce >= 0.10) | (cash_conversion >= 0.60)`: 227 fires pass only on cash conversion, including 12 with roce < 0. Chien Kuo 5515.TW (roce −0.91) is spirit #1.
- **LOOSE.** Liquidity removes 864; quality is the most binding gate (1,584).

Coverage: panel beta rank NaN 26%; Yartseva 25%; 28 fires on the Yahoo fallback.

Fires: CN 200, JP 106, US 96. Gree (beta rank 0.003, EV/EBIT 4.1, FCF yield 16%) fits; Eusu and Omnia fit; JNJ, AbbVie and CATL (EV/EBIT 16.8, roce 1.36) are not "boring and cheap".

Severity: **LOOSE**.

Fix: require `_bab_low` (drop the Yartseva beta escape); multibagger leg = Yartseva ≥ 0.6 or (shock & cheap); quality `roce >= 0.10` with cash conversion as AND.

## arch_liger_asset_backed (1,274 fires, median mcap $49M)

Intent (3647-3660, 3668-3670): "neglected microcaps ... survivable balance sheet, near-breakeven-or-better cash flow ... depressed/off-highs"; "GENUINE net cash"; "ASSET-BACKED: the book or the cash carries the cap".

Code (3662-3679): mcap < $400M; `net_cash_pct_c >= 0.20` (clipped −2..2, **not** `net_cash_pct_sane`); P/B < 3; asset leg; fq shares ≤ 3%; neglect; `(op >= -5%) | (EBITDA margin >= 0)`; SBC; sector exclusions.

Leg checks:
- **Shell admission.** 323 of 1,274 fires (25%) have net cash > 100% of mcap and 71 have > 200%. 61 pass the asset leg only through that. Example: ATPC, net cash 1,025% of a $2.4M cap, spirit #1. Sibling archetypes veto > 100% as "shell artifacts" (tangible_value 1979, net_cash_returner uses `_sane`). **BUG (inconsistent clamp).**
- **Neglect.** 1,148 fires have no count anywhere (passes); the leg removes 8.
- **"Depressed/off-highs" is not gated.** 295 fires are ≥ 90% of the 52-week high.
- **"Near-breakeven" is satisfied by EBITDA ≥ 0.** 84 fires have op < −5% and 344 have FCF < 0. CULTIBAB.MX has op −444%. 125 fires are below $10M mcap.
- `n_analysts_pew` (fallback) exists for 3,602 names.

Coverage: P/TB NaN 49%; NCAV 47%; `fq_shares_yoy` 38% (313 fires unmeasured, which pass).

Fires: JP 380, KR 230, HK 161, US 118. Overlap with net_cash_returner is 635 (50%). Incross (net cash 219%), PN Poong Nyun and Sansei are deep net-cash micro-caps; ATPC and 1259.HK (net cash 410%) are shells.

Severity: **BUG/LOOSE**.

Fix: use `net_cash_pct_sane` (≤ 1.0), add `ts_dist_hi52 <= 0.85` (where measured) and `op_viable(-0.05)`.

## arch_crisis_asset_backed_recovery (788 fires, median mcap $95M)

Intent (3879-3893): "A hard-asset-rich OPERATING company ... smashed by a MACRO / country / commodity crisis while the assets themselves stay intact ... the discount must be measured against TANGIBLE assets."

Code (3895-3912): asset-heavy (PP&E/assets ≥ 30%, else capex ≥ 5%, else Energy/Materials/Industrials label, or gross PP&E ≥ 40% of assets); crash (`beaten_down_any(0.55)` | 5y range ≤ 0.15 | `hi260 <= 0.45`); `(pb < 0.8) | (p_tb < 0.8)`; `_not_melting`.

Leg checks:
- **Tangible discount.** It is OR'd with total-book P/B. 264 of 788 fires (34%) are below 0.8x only on total book: 161 have P/TB NaN and 103 have P/TB ≥ 0.8.
- **"Macro/country/commodity crisis" has no peer frame.** An idiosyncratic collapse qualifies; 45 fires are > 95% off the 5y high.
  - Spirit #1 NATIONSTD.BO: hi260 0.006, op NaN.
  - FNUC (hi260 0.006, op 0): a pre-revenue nuclear/minerals shell.
  - MicroPort CardioFlow (op −65%).
- **Survival.** 232 fires have op < 0, 373 have FCF < 0, and 355 have nde > 5 or EBITDA ≤ 0. `_not_melting` removes 38. **LOOSE.**

Coverage: P/TB NaN 49%; `fq_ppe_net` 37%; `ppe_gross` 90%.

Fires: KR 194 (18 preferred lines), US 153, HK 81. Materials 201, Consumer Discretionary 192. POSCO (P/TB 0.57, hi260 0.44), Nippon Steel and Volkswagen (P/B 0.22) fit the "crushed heavy-asset" shape, but VW/NISTF have nde 5-11. Shells at the top of spirit do not fit.

Severity: **LOOSE**.

Fix: require `p_tb < 0.8` (P/B only if P/TB is unmeasurable and goodwill/assets < 10%); crash relative to peers (`hi260 <= 0.45` and industry or country median `hi260 <= 0.6`); `op_viable(0)`; revenue ≥ $10M.

## arch_cash_adjusted_pe (1,466 fires, median mcap $113M)

Intent (4227-4236): "(mcap − net cash) / NI ... When net cash exceeds market cap WITH real positive earnings, the multiple goes NEGATIVE ... 0 < adj P/E <= 8 is the cheap band."

Code (4237-4262): NI > 0, NI/mcap ≥ 2%, `cash − total_debt > 0`, adj P/E ≤ 8 (or on `ni_avg`), a one-off guard (NI > 2x avg), shares ≤ 5%, CFO ≥ 0.3 NI, `_not_melting` (removes 0).

Leg checks:
- **Any name with net cash > mcap passes the cheap leg whatever its earnings level.** 186 fires (13%) have a negative multiple; P/E up to 52 (Creema 4017.T). Billing System 3623.T (cash ¥39.6B vs mcap ¥7.6B) is a collection agency whose cash is client money, at spirit #1.
- **Non-operating earnings.** 153 fires carry `earnings_oneoff_flag` (NI > 1.1x EBITDA) and 128 have op_margin < 0 (e.g. 1303.HK). The file computes that flag but does not gate on it.
- **Debt understated.** 54 fires show net debt on the quarterly panel, including TBB (AT&T notes line, `total_debt` $10.5B vs fq $162.9B), 600335.SS and GMD.MX.
- **"Genuine net cash" is any positive amount.** 65 fires have net cash < 5% of mcap (1596.HK: ¥1.5M net on ¥466M).
- 219 fires are cheap only on the 5-year average (Maersk AMKBF/AMKBY: P/E 22, 5-year average NI inflated by 2021-22).

Coverage: `ni_avg` NaN 23% (164 fires unmeasured; the one-off guard is then permissive).

Overlap: net_cash_returner 761, liger 594.

Severity: **LOOSE** (plus the data leak of the TBB-type lines).

Fix: gate `earnings_oneoff_flag == 0 & op_margin > 0`; require the fq net-cash sign to agree; cap `nc <= mcap` or require `0 < adj_pe`; net cash ≥ 10% of mcap.

## arch_self_funded_returner (2,569 fires, median mcap $414M, 271 > $10B)

Intent (4428-4438): "the FINANCING cash-flow line has been a net OUTFLOW (returning capital / repaying debt, never raising) while free cash is positive ... persistence ... >= 80% of fiscal years."

Code (4443-4451): financing CF TTM < 0; outflow share ≥ 0.8 (NaN-permissive, 23 fires); fq shares ≤ 2%; FCF > 0; P/E ≤ 15 or P/B < 1.5; `_not_melting` (removes 0).

The name says "returner", but the outflow can be pure debt repayment:
- 195 fires return nothing to shareholders (dividend + buyback = 0 or NaN) and 296 return < 1%.
- 322 carry nde > 3; 364 have an outflow > 2x FCF.
- Example: GMD.MX (dividend 0, buyback 0) at spirit #5. **LOOSE.**
- Cheap leg: P/B < 1.5 alone lets P/E 95 in (SCI.BK).

Coverage: `financing_cf_ttm` NaN 38% / 36%.

Fires: US 590, JP 518, HK 206; 379 duplicate lines (Samsung ×3, PetroChina ×2). Nitta Gelatin (dividend 3.1%, P/E 6.6) fits.

Severity: **LOOSE**.

Fix: require dividend + buyback ≥ 1% (or `fq_dividends_paid + fq_buyback` ≥ 50% of the outflow) and `nde <= 3`.

## arch_xr_quality_crisis (3,402 fires; recon 3,393; median mcap $133M)

Intent (4579-4584): "MULTI-YEAR proven quality ... marked at a CRISIS price (>=40% off the high, or the bottom third of the 5-year range) and cheap on at least one lens."

Code (4585-4606):
- Quality = OR of: ≥ 4 FCF years; equity CAGR ≥ 10%; lindy ROIC ≥ 12%; oe_avg & ni_avg > 0; NI streak ≥ 8q; revenue streak ≥ 8q.
- Crisis = stale `pct_off_52w_high` ≤ −40% | dd52 ≤ −40% | hi260 ≤ 0.60.
- Cheap = P/B < 1.2 | P/E ≤ 10 | FCF yield ≥ 10%.

Leg checks:
- **Quality is a 59% base rate among operating names.** The legs are each ordinary: FCF4 33%, "oe & ni_avg > 0" 40%; 660 fires pass only on "average earnings > 0". 1,775 fires have lindy ROIC < 5%, 617 have op < 0, 912 have FCF < 0 and 601 have revenue < −10%. **LOOSE.**
- **Crisis.** 2,004 fires pass only on the 5-year high while their 52-week drawdown is shallower than −40%, and 496 are within 15% of the 52-week high. The "bottom third of the 5-year range" in the comment is not in the code. 52 pass only on the stale quote-time drawdown that the weekly panel contradicts.

Fires: US 731, IN 417, HK 288, CN 269. Embecta and BellRing (−86%/−90% off highs, ROIC 41%/29%, P/E 3.4/6.4) fit well. SoftBank (lindy ROIC 1.6%, op −11.5%) and McLeod Russel (P/B 12.6) do not. Comcast (P/B 1.0, hi260 0.44, ROIC 6%) is marginal.

Severity: **LOOSE**.

Fix: require ≥ 2 quality legs including lindy ROIC ≥ 10% or ≥ 4 FCF years with FCF > 0 now; crisis = `dd52 <= -0.40 | (hi260 <= 0.60 & dd52 <= -0.20)`.

## arch_xr_float_compounding (128 fires, median mcap $2.21B)

Intent (4773-4779): "customers PREPAY (deferred revenue / negative working capital float) so cash collections run ahead of GAAP revenue ... revenue now ACCELERATING while the market still prices the trailing P&L."

Code (4790-4803): float = deferred revenue ≥ 10% of revenue | NWC < 0; float not shrinking / CCC not > 0 where measured; SBC/CFO ≤ 30%; CFO/NI ≥ 1.3 | cash_conversion ≥ 1.2; `rev_accel > 0 | rev_yoy >= 15%`; P/E ≥ 20 or NaN; mcap/CFO ≤ 15; roic_after_sbc ≥ 0; shares ≤ 5%; `_not_melting` (removes 0).

Leg checks:
- 100 of 128 fires qualify on NWC < 0 alone. That is payables or supplier float, not customer prepayment: Suning.com (retail, revenue −14%), Liuzhou Iron & Steel, Pingdingshan coal (−32%), Enbridge.
- 25 fires have falling revenue and pass on `rev_accel > 0` (a decline that is slowing), and 59 grow < 5%. "Bookings engine turning" is not met. **LOOSE.**
- 17 fires pass "P/E dear" because P/E is NaN (loss or no earnings).

Coverage: deferred revenue NaN 41% (EDGAR/fq level); `fq_defrev_growth_minus_rev` NaN 91%.

Fires: US 58, CN 13. Oracle, Salesforce and Lincoln Educational (deferred tuition) fit; the CN steel/coal/retail names do not.

Severity: **LOOSE**.

Fix: float = deferred revenue ≥ 10% of revenue, or (NWC < 0 & `fq_ccc < 0` & sector not Materials/Energy); growth = `rev_yoy >= 0.10`.

## arch_xr_baron_compounder (558 fires, median mcap $846M)

Intent (4998-5005): "FOUNDER/OWNER-led businesses with DECADE-length growth durability, reinvesting so heavily that current earnings are suppressed ... bought at a growth-ADJUSTED fair price."

Code (5009-5027): insider ≥ 10%, with a control cap; duration (12q positive share ≥ 0.75 | streak ≥ 6q | `rev_3y_cagr` ≥ 15%); revenue ≥ 12%; reinvest = (GM − OM ≥ 15pp & GM ≥ 35%) | capex intensity ≥ 8%; EVSG ≤ 0.4 | P/S ≤ 6; revenue ≥ $25M; mcap ≤ $25B; roic_after_sbc ≥ 0; shares ≤ 8%; `_not_melting`.

Leg checks:
- **"Reinvesting so heavily that earnings are suppressed" is not measured.** GM − OM ≥ 15pp is just any SG&A line (35% base rate among operating names). 175 fires run op margins ≥ 20% and 74 run ≥ 30%; Toyokumo is at 42% (spirit #2). **LOOSE.**
- The `rev_3y_cagr` duration leg reads the 95%-NaN master column; `revenue_3y_cagr` is the populated one. **COSMETIC/TIGHT.**
- "Founder-led" means insider ≥ 10%. 144 fires have ≥ 50% insiders (Carlsberg 98%: a foundation, not a founder).
- Decade-length durability is read on 12 quarters.

Fires: CN 120, US 100, JP 97. SharkNinja, Fuyao, GenusPlus and KIYO Learning are growing owner-led companies. Western Midstream (an MLP, op 43%) and Serabi Gold (a gold-price effect) do not fit.

Severity: **LOOSE**.

Fix: reinvestment = `op_margin < tc_med_opm` or `(fg_sga_g1 + fg_rd_g1) > fg_rev_g1`, or capex/D&A ≥ 1.5; use `revenue_3y_cagr`; exclude insiders > 60% without founder evidence.

## arch_xr_look_through_value (34 fires, median mcap $612M)

Intent (5339-5344): "equity-method / associate investments ... MATERIAL relative to its own market cap, while the consolidated business is real and priced cheaply."

Code (5345-5353): `investments_associates / mcap_usd >= 0.30`; `_profit_present`; P/B < 1.5 or EV/EBITDA ≤ 10; `_not_melting`. All levels are USD for this population (the local and USD ratios agree for every fire).

Leg checks:
- **CCZ** (Comcast 2.0% ZONES exchangeable debentures, a debt security) fires with mcap $15.5B and P/B 0.17, spirit #3. The real CMCSA is about $90B and would not pass. **BUG (non-common leak).**
- Duplicate lines: Liberty Global ×3, Weibo ×2, Trip.com ×2, so about 30 companies.

Coverage: `investments_associates` NaN 94% (US 2,570 of 2,668 present). This is an EDGAR-only archetype. **TIGHT.**

Fires: US 33, CN 1. Teekay (stake in TNK, assoc $1.08B on a $1.24B cap), Liberty Global, Weibo, IAC (PPLI line, $3.2B stakes) and SunocoCorp (SUNC, mislabelled "Suncast Solar") genuinely fit. TOPS ($4M cap) is a micro shell.

Severity: **BUG** (debt-line leak), **TIGHT** (US-only).

Fix: extend the non-common scrub to names matching `zones|exchangeable|debenture`, or to lines whose `shares_outstanding` and price diverge from the same-name common. Fill associates from the FMP balance sheet (`longTermInvestments` / equity-method) for non-US names.

## arch_xr_gross_margin_lead (245 fires, median mcap $632M)

Intent (5528-5536): "GROSS margin inflects first (mix / pricing / scale) while SG&A hasn't yet scaled down, so operating margin LAGS ... on a GROWING revenue base."

Code (5539-5548): revenue ≥ $20M; GM delta ≥ +2pp; revenue ≥ 5%; GM ≥ 20%; 0 ≤ OM delta < ½ GM delta; shares ≤ 5%; `_not_melting` (removes 0). The OM band is the binding gate (removes 1,302).

Leg checks:
- **No test that the GM move is scale/pricing rather than an input-cost or commodity swing.** Hindustan Zinc (+20pp GM on zinc/silver prices, op margin 55%) is spirit #2. 42 fires show GM jumps ≥ 10pp, typical of reclassification or commodity moves.
- **No test that OM is "lagging" a norm.** Alphabet and Tencent (OM 33%) qualify.
- **No cap on revenue growth.** Fischer Chemic has revenue +784%.
- 112 of 245 fires (46%) are Indian annual filers, which suggests a reporting-basis artefact in the IN gross-margin deltas. **LOOSE.**

Coverage: GM/OM deltas NaN 48% / 42%.

Fires: IN 112, US 40, CN 15. Craftsman and Lumax (auto components) fit; Hindustan Zinc and GOOG do not.

Severity: **LOOSE**.

Fix: revenue growth ≤ 100%, GM delta ≤ 10pp unless `fq_gm_inflection_flag == 1`, `op_margin < tc_med_opm` (lagging its own norm), and exclude Materials/Energy.

## arch_coiled_base (378 fires, median mcap $389M)

Intent (7382-7390): "a future multi-bagger goes NOWHERE for ~2 years ... value accretes under a flat price (the COIL), the market is not watching or does not believe (PERCEPTION LAG)."

Code (7395-7464):
- Time: `bs_is_base & bs_pos_in_range >= 0.25`.
- Coil: any of 5 lenses, plus real & not melting.
- Perception: any of 5 lenses & `~(sent_n_analysts > 3)`.
- Validity: dvol ≥ $250k & revenue ≥ $10M.

Leg checks:
- **Perception.** `sent_neglected_flag` is `~(n > 3)`, so NaN counts as neglected; it is in all 378 fires and is the sole perception lens for 44.
  - 45 fires are OTC or second lines whose same-name line carries > 3 analysts: KYCCF Keyence, BUDFF AB InBev ($153B), TRUMY Terumo ($21.5B), DNZOF/DNZOY Denso, CCOEY, STEAV.HE.
  - NCRRP, an NCR Voyix *preferred* line with mcap $138.8B, fires: a non-common leak.
- **Coil.** `fmp_dyn_unrerated_gap >= 0.15` is the sole coil lens for 149 of 378 (39%), so the "value accreted while price did not" reads mostly through one model output. Revenue coil 117, EBIT coil 111.
- The base gate is the binding one (removes 2,962). **LOOSE** (perception).

Coverage: base-snapshot fields NaN 28%; `bs_coil_ebit` 67%.

Fires: JP 123, US 72, TW 44. Andhra Sugars, Kyungin Electronics and Matching Service Japan fit. AB InBev, Keyence and Terumo fail the perception thesis.

Severity: **LOOSE**.

Fix: neglect = max analysts over same-name lines ≤ 3; scrub `^[A-Z]{4}P$` preferred lines by name/shares match; require ≥ 2 coil lenses when the only one is `unrerated_gap`.

## arch_mb_fallen_insider (109 fires, median mcap $355M)

Intent (7554-7559): "fallen angel + insiders buying in 2+ of the last 4 quarters + an OPERATING business, not an asset play + margins not yet consistent."

Code (7560-7570): `_mb_base`; `hi260 <= 0.40`; `usf_ins_buy_quarters_4q >= 2` (fallback: distinct buyers ≥ 2 | FMP net 12m > 0); not NCAV ≥ 50%; not `fqx_opm_consist > 0.5`.

Leg checks:
- 108 of 109 fires use the SEC count (1 uses the fallback); purchases are counted per quarter (fmp_us_filings.py:73).
- 16 fires are net sellers over the same 4 quarters (`usf_ins_net_buy_4q < 0`) and 22 are net sellers on FMP 12m (CHTR −$9.0M, TEAM −$6.6M). A token buy in 2 quarters qualifies.
- **"An operating business" is only `~(ncav >= 0.5)`.** 52 of 109 fires have op < 0 (Empire Petroleum −224%, Alight −96%, Hyperscale Data −60%). Hyperscale Data (GPUS, hi260 7e-8) is a serial reverse-split diluter; the "fall" is per-share dilution and there is no share-count guard. **LOOSE.**

Coverage: `usf_*` NaN 85% (SEC filers only). Fires: US 108, UK 1. **TIGHT.**

Fires: Thryv, Portillo's, Nike (hi260 0.22, 2 buy quarters, +$6.0M net) and FIS fit.

Severity: **LOOSE**, **TIGHT** (US-only).

Fix: add `op_viable(0) | _not_melting`, `~(shares_growth_3y > 0.20)` and `usf_ins_net_buy_4q > 0`.

## arch_mb_tree_recipe_10x (333 fires, median mcap $39M)

Intent (7641-7644): "within-country ranks — volatility top 40%, size bottom 13% ... The 10x variant swaps the fallen leg for cheapness above the median."

Code (7656-7663): the ranks among the liquid operating base, with cuts at 0.62 / 0.12 / 0.46 / 0.45. These match the study's stated cuts.

Notes:
- `_r_cheap` averages whatever of 4 lenses exist; 22 fires are ranked on ≤ 2 lenses.
- The profitability-bottom leg admits melters by design: 202 op < 0, 35 fail `_not_melting`. Examples: Oceanpal (op −287%), Hyperscale Data (spirit #1).
- Exact match; no logic errors. Only 6 fires use the small-country fallback.

Fires: US 111, JP 49, IN 34; mcap $10M-$383M.

Severity: **OK / COSMETIC** (consider `_not_melting`; require ≥ 3 cheapness lenses).

Fix: require ≥ 3 cheapness lenses present; optionally add `_not_melting`.

## arch_xr_stake_fv_gap (3 fires)

Intent (5823-5827): "the company itself DISCLOSES ... that the fair value of its equity-method JV/associate stake exceeds its CARRYING VALUE ... on a cheaply-priced consolidated whole."

Code (5828-5839): carry > 0; FV > 1.3x carry; gap ≥ 10% of USD mcap; a cheap OR (62% base rate, removes 0); data-quality flag; `_not_melting`. Logic is correct; `em_fv_gap == em_fair_value − em_carry` for 100% of rows.

Coverage: `em_fair_value` is present for 179 names (US EDGAR). **TIGHT.**

Fires:
- CTRM (Castor Maritime: Toro stake FV $140M vs carry $50M on a $23M cap) fits.
- LSAK (Lesaka: FV $173M vs carry $0.3M on $366M) fits.
- TOPS ($4M cap, FV $19M vs carry $8M) is a micro shell.
- Spirit is NaN for all 3 (fewer than 5 members).

Severity: **TIGHT** (coverage). The cheap leg is decorative.

Fix: fill from FMP / IFRS disclosures if available; otherwise accept as a rare-event screen and add mcap ≥ $10M.

## arch_growth_algo (519 fires, median mcap $337M)

Intent (6329-6338): "gross-profit growth (~20%) + operating leverage (EBIT growing FASTER, ~25%) + a shrinking share count (~−5%) COMPOUND into outsized FCF/share growth (~30%), bought cheap."

Code (6350-6373): mcap < $50B; revenue ≥ $20M; revenue ≥ 15%; `season_robust` | incremental margin ≥ 20%; FCF > 0; fq shares ≤ 2%; FCF growth ≥ 20% on any lens; P/FCF 2-15; `not_diluting`; operating.

Leg checks:
- **Operating-leverage leg.** It has a 95.8% base rate among operating names with ≥ 15% growth and removes 7, because `season_robust` is any positive margin delta or any positive TTM-sequential revenue or EBITDA.
  - 134 of 359 measured fires have EBIT growing *slower* than revenue, and 137 have op margin down YoY.
  - Swisscom (×3 lines) has revenue +36.6% from the Vodafone Italia acquisition with op margin −4.9pp.
  - Gold miners (Monument Mining ×2, Gold Fields) reflect the gold price. **LOOSE.**
- The share count is "not growing" (≤ 2%), not shrinking; 202 fires shrink.
- 36 fires have FCF growth > 500% (base effects).

Coverage: `fqx_fcf_ps_g` NaN 73%; `fcf_yoy` 30%.

Fires: US 124, JP 62, KR 42. JMACS and Fonix fit. Swisscom, Repsol, Gold Fields and Chien Kuo do not.

Severity: **LOOSE**.

Fix: require `fqx_ebit_ttm_g > fq_rev_growth` (or `op_margin_delta_yoy > 0` where TTM is missing), cap FCF growth at 500%, and exclude Materials/Energy price-driven growth (or require `gross_profit_yoy >= 0.15`).

## arch_evsales_derating (1,015 fires, median mcap $570M)

Intent (6815-6824, 6856): "EV/Sales compresses even as revenue compounds ... (deep-audit) HARD positive top-line floor."

Code (6853-6875):
- Old rule: mcap $50M-$20B; revenue ≥ $5M; revenue ≥ 15%; `~(rev_3y_cagr < 0)`; `derate_any`; no > 20% EV/S expansion; EV/S 0.1-6; trap / cash guards; operating.
- Tier core: `fq_rev_growth >= 15% & (log gap >= 0.15 | bs_coil_rev >= 0.15)`, with `measured = fq_rev_growth.notna()`.

Leg checks:
- **BUG.** The "HARD positive top-line floor" reads `rev_3y_cagr`, which is NaN for 943 of 1,015 fires (95% of the universe), so it removes 7. The populated `revenue_3y_cagr` is negative for 64 fires that the floor exists to drop.
- **Derate legs.** 623 fires show a measured 1-year EV/S compression ≥ 0.15 and 144 an inferred one. 248 pass only via 3y, coil or EVSG. 77 fires show a *measured* EV/S that did not fall (log change between 0 and +0.20).
- **"Stock flat/down".** 115 fires are up ≥ 30% over 52 weeks.
- **`evh_evs_log_chg_3y` is populated for 0.2%**, so the "dated 3-year compression" is always the inferred fallback. **COSMETIC.**
- 373 fires (37%) have no `fq_rev_growth` and keep the old rule.
- 102 fires have revenue > +100%; 345 have FCF < 0; 121 have op < 0.

Fires: US 240, IN 225, CN 142. Toast (revenue +30%, EV/S log −0.69) and Navkar fit. SIMEC (EV/S log −5.07, an artefact) and QDMI (−7.47) carry implausible EV-history values. Wistron is up 58%.

Severity: **BUG** (wrong column), **LOOSE**.

Fix: `~(revenue_3y_cagr.fillna(rev_3y_cagr) < 0)`; require `evh_evs_log_chg_1y <= 0` where measured; clip the EV-history log change to [−2, 2]; cap revenue growth at 100%.

## arch_spinoff_asset (2 fires)

Intent (9008-9016): "forced-selling of a spun entity can leave it priced below its ASSET backing ... sum-of-parts / net-net / hidden-real-estate / deep-net-cash orphan."

Code (9017-9028): spin (EDGAR Form-10 flag, else an FMP spin filing ≤ 730 days); operating; `_not_melting`; `op_viable(-0.05)`; the asset floor (P/B < 1 | NCAV ≥ 0.5 | net cash ≥ 20% | cash > EV | hidden ≥ 25%); `_spin_orphan`.

Leg checks:
- Only 44 spins are in the universe, all flagged via EDGAR.
- Both fires (VSNT Versant Media, spun 2025-12-03; OCTV Octave Intelligence, 2026-04-27) have **no weekly panel**, so `_spin_orphan` passes on NaN.
- Both qualify on P/B < 1 alone. Versant's book is mostly cable-network goodwill and intangibles and it carries net debt (net cash −29%), which is not the "asset backing" the comment describes.
- The other four floor legs fire 0 times.

Coverage: the spin flags are present for about 0.1% of names.

Severity: **TIGHT** (coverage), **LOOSE** (P/B on an intangible-heavy carve-out; NaN tape passes).

Fix: use `p_tb < 1` (tangible) in place of P/B, and treat a missing tape as "unknown" (watch) rather than orphaned.

---

## Summary

| archetype | fires | severity | one-line fix |
|---|---|---|---|
| gayner_missed_it | 347 | BUG + LOOSE | Threshold the cumulative per-share growth at 1.12^5−1 (162/347 fail a true 12%/yr); drawdown leg also needs r52 ≤ 0.20 (31 fires up > 50%) |
| tax_efficient | 1,947 | BUG + LOOSE | Write the FMP-filled ETR back to `df` so spirit works (NaN for 1,748/1,947); add a no-recent-loss-year / NOL guard (708 fires have a loss year) |
| evsales_derating | 1,015 | BUG + LOOSE | Floor on `revenue_3y_cagr` not the 95%-NaN `rev_3y_cagr` (64 shrinkers pass); require measured EV/S ≤ 0; clip EV-history artefacts |
| xr_look_through_value | 34 | BUG + TIGHT | Scrub ZONES/exchangeable debt lines (CCZ fires at $15.5B, P/B 0.17); FMP equity-method fill for non-US names (94% NaN) |
| liger_asset_backed | 1,274 | BUG/LOOSE | Use `net_cash_pct_sane` (323 fires have net cash > 100% of mcap, ATPC 1,025%); add an off-highs gate (295 at ≥ 90% of the 52w high) and `op_viable` |
| cash_adjusted_pe | 1,466 | LOOSE | Gate `earnings_oneoff_flag == 0 & op_margin > 0` (153 / 128 fires); require fq net-cash sign agreement (54; TBB AT&T notes line); net cash ≤ mcap |
| xr_quality_crisis | 3,402 | LOOSE | Quality needs ≥ 2 legs incl. ROIC ≥ 10% (base rate 59%; 1,775 fires ROIC < 5%); crisis needs dd52 ≤ −20% (496 within 15% of the 52w high) |
| xr_float_compounding | 128 | LOOSE | Customer float = deferred revenue ≥ 10% or (NWC < 0 & CCC < 0, not Materials/Energy) (100/128 are payables float); revenue growth ≥ 10% (25 shrinking) |
| crisis_asset_backed_recovery | 788 | LOOSE | Tangible P/TB < 0.8 (264 pass on total book only); peer-relative crash (45 > 95% collapses); `op_viable` |
| bab_multibagger | 871 | LOOSE | Require the low-beta third (266 at rank 0.35-0.50); drop the 43%-base-rate margin-shock leg; ROCE ≥ 10% as AND |
| growth_algo | 519 | LOOSE | Require EBIT growth > revenue growth (134/359 fail; op-leverage leg is a 96% base rate) |
| xr_gross_margin_lead | 245 | LOOSE | Cap revenue growth at 100% and GM delta at 10pp; require OM below its own norm; exclude commodity sectors |
| xr_baron_compounder | 558 | LOOSE | Measure suppressed earnings (OM < own median or SG&A/R&D outgrowing revenue; 175 fires OM ≥ 20%); use `revenue_3y_cagr` |
| net_cash_returner | 1,617 | LOOSE | Total yield ≥ 2% with shares not growing, FCF > 0 and payout covered (348 FCF < 0, 198 issuing) |
| self_funded_returner | 2,569 | LOOSE | Require a shareholder return ≥ 1% (195 return nothing; outflow = debt repayment) |
| coiled_base | 378 | LOOSE | Neglect = max analysts across same-name lines (45 fires, e.g. Keyence, AB InBev); scrub NCRRP-type preferred lines |
| mb_fallen_insider | 109 | LOOSE + TIGHT | Add `op_viable`/`_not_melting` (52/109 op < 0), a share-count guard and net insider buying > 0 (16 net sellers) |
| double_inflect | 172 | LOOSE (minor) | Require `op_margin > 0` and 0 < `fqx_roic_ttm` ≤ 1 (23 op < 0; BNC ROIC 223) |
| lindy_fcf | 3,557 | LOOSE (minor) | Core needs ≥ 7 FCF years as commented (89 fires have 3-6); FCF-margin floor 5% as AND (59 below 3%); mcap > 0 (144 NaN) |
| blindspot | 1,666 | LOOSE + COSMETIC | Drop the unmeasured-liquidity escape (615 fires); add `_not_melting`/`op_viable` (400 op < 0); remove the dead ADV leg |
| spinoff_asset | 2 | TIGHT + LOOSE | P/TB not P/B for the floor; NaN tape should not count as an orphan (both fires) |
| xr_stake_fv_gap | 3 | TIGHT | Coverage limited to 179 EDGAR disclosers; add mcap ≥ $10M (TOPS $4M) |
| mb_tree_recipe_10x | 333 | OK / COSMETIC | Require ≥ 3 cheapness lenses (22 ranked on ≤ 2); optional `_not_melting` |
