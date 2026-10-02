# Archetype review, round 2, batch 6 (23 archetypes)

Method: I ran an instrumented copy of today's `archetype_tags.py` (scratchpad/b6/at_inst.py). It is identical to the repo file except that, just before the file writes, it dumps `df` and every local Series of length N to scratchpad/b6/{df,loc}.parquet and returns. It writes nothing in the repo. All 23 published `arch_*` columns are reproduced exactly (0 mismatches against archetype_tags.csv). Every per-leg count below is taken from those dumped locals: each gate is rebuilt from its legs and matches the published column 1:1 (`recon == pub`). Spirit/exceptional values come from archetype_tiers.csv. "Removes X of Y" means: Y names pass every other leg (after the global scrubs), and X of them fail this leg alone. Universe N = 46,526, operating 36,173. Scripts: scratchpad/b6/*.py (lib.py has the helpers).

Shared facts this batch leans on (in addition to batch 1's):
- **D&A currency bug on USD-quoted OTC/ADR lines.** On lines where every level is USD-converted (`market_cap == market_cap_usd`, revenue/NI/capex in USD), `da_ttm` still carries the home-currency value. Aisin ASEKY: revenue $32.5B, capex $1.6B, D&A **2.65e11** (= the ¥265B of 7259.T). Kawasaki Kisen KAIKY: D&A 5.24e10 (¥) on $6.6B of revenue. Also STAEF, OJIPY, DNPCF, ASGLY, CTPCF, SNEJF (Sony OE/NI = 167x), BMBOY (35x). 1,327 operating names show D&A > 60% of revenue, 1,000 of them on such lines. `_fx_coherent` compares mcap with revenue only, so it cannot see the problem. Every owner-earnings / harvest gate (`_dna_loc`, `_oe_loc`, `_oe_ratio`) is inflated by roughly the FX rate on these lines. Affected fires: xr_harvest_distribution 21/145, xr_amortization_mask 13/95, and outside this batch xr_forensic_multiple_gap 63/360 and owner_earnings_power 24/340.
- `insider_ownership_pct` counts parent, state and strategic stakes as "insiders": Aramco 0.815 (the Saudi state), Chugai 0.599 (Roche), Kia 0.394 (Hyundai Motor), Mercedes 0.205 (Geely/BAIC/Kuwait). It is NaN for 21% of operating names.
- Neglect read through NaN coverage: `sent_n_analysts` NaN = 73% of operating names. OTC lines of covered names (EVVTY, DKILF, OMRNY, KGGNF, HSWLF) read as uncovered.
- `fqx_inc_ebit_margin` raw values > 1 are out of domain (cost cuts / loss unwind). The code defines `fqx_inc_ebit_margin_dt` (<= 1) to exclude them (line 1265), but some gates still read the raw column.
- `season_robust` (line 3022) = ANY one of 10 YoY/TTM-sequential lenses > 0 (`rev_qoq_ttm > 0` alone qualifies). It passes 63% of operating names, so every "operating leverage" leg built on it is close to a no-op.

---

## arch_narrative_lag (5,317 fires, median mcap $633m; US 1,734, JP 636, CN 446, IN 382; 720 fires > $10B)

Intent: "Business ADVANCING while the market ignores it ... The LAG is the thesis, so it is measured directly ... each 'the fundamental advance outran the price' ... A LAG IS UNPRICED ADVANCE, NOT MULTIPLE COMPRESSION ... credited with min(outrun, log(sector-norm multiple / current multiple))" (1349-1486).

Code (core = the reframe at 1529-1537; the old rule is `narrative_lag_watch`, 1388-1396)
- `narrative_lag_lenses >= 1` (1505): removes 6,063 of 11,380. The lens count = one per horizon whose valuation-anchored per-share gap clears its threshold, **plus `_lag_rel` (1503) and `_lag_ign` (1504), which have no valuation anchor and no price test**. `_lag_ign` = `evt_ignored_beats_2y >= 2`, i.e. two or more earnings beats in two years with a non-positive price reaction. 6,245 names have that (33% of the 19,196 with the field), so it is close to a coin-flip statistic. **1,625 fires (31%) have no anchored lag at all (`narrative_lag_extent == 0`): 1,341 pass on ignored-beats only and 365 on relative-strength only.** These include Apple (r52 +34%, P/B 45, 4 ignored beats), J&J (+54%), AbbVie, Chevron, Tencent (3 lines) and Samsung GDR (r52 +249%). 1,245 of the ignored-beats fires are US, because the feed is US-centric. This contradicts the comment's own rule that a lag is unpriced advance. BUG.
- `_adv_breadth >= 2`: removes 2,017 of 7,334. OK.
- **The `_adv_shock` leg was dropped in the reframe.** The audit-3 comment at 1383-1386 says breadth counts only beside a shock-sized lens. The watch rule has that leg; the core does not. 1,264 fires lack any shock lens. The "tightened" core is **larger** than the watch (5,317 vs 5,084), and only 2,468 fires are in both. COSMETIC/LOOSE: the `_tier` doctrine says core is a subset of watch.
- `is_operating`, mcap >= $10m (removes 242), `_roce_now_ok` (removes 4: no-op), cash/EBITDA positive (removes 201), value `(0 < pb < 3) | fcf_yield >= 3%` (removes 801; `pb` is filled with 99, so NaN P/B fails unless FCF yield >= 3%: 71 fires pass that way). Value admits AAPL (P/B 45, FCF yield 3.2%) and ALHC (P/B 9.9).
- Coverage: fq_rev_growth NaN 44%, fqx_ebit_ttm_g 58%, ts_r52 22%, ev_sales 32% of operating names. The anchored lenses are blind wherever the multiple is missing. The ignored-beats lens is in practice US-only.

Fires: 980 have >= 10 analysts; 846 are up > 30% on the year, 115 up > 100%. Top spirit fits the thesis: YELP (r52 -43%, 5 lenses, extent 3.05, 5-year lag), PENTA.IS, GWLLY (Great Wall, P/B 0.69, -54%), MRVSY. ADBE (spirit 0.96, P/B 8.7, 39 analysts) is an anchored multi-year lag, so it is defensible. The largest fires are the bad ones: AAPL, JNJ, ABBV, CVX, Tencent (0700.HK, TCEHY, TCTZF), Samsung BC94.L, all with extent 0. Random members: RYHTY (Ryman, extent 1.09, P/B 0.52) fits; GAERF (P/B 10.1, extent 0) does not.

Severity: BUG (unanchored ignored-beats / relative lenses count as a lag; 1,625 fires have no measured lag), COSMETIC (shock leg silently dropped; core not a subset of watch).
Fix: count `_lag_rel` / `_lag_ign` only beside at least one anchored horizon (or move them to the spirit), and restore `_adv_shock` in the core.

## arch_cash_reinvest (1,937 fires, median mcap $1.43B; US 555, JP 254, CN 160, IN 152, TW 140)

Intent: "J — Cash-confirmed reinvestment: cash ROIIC lindy > 12% (lower bar than NOPAT because FCF includes capex outflows)", in the section "EDGAR XBRL-derived archetypes (US filers only) ... Names without EDGAR coverage get 0" (1889-1924).

Code (1926-1933)
- `cash_roic_lindy >= 0.10`: removes 2,361 of 4,298, the binding leg. `cash_roiic_lindy` in [0.12, 1.0]: removes 1,169 of 3,106. `n_yrs_positive_roic >= 4` (zero-filled, so NaN fails): removes 126. `asset_3y_cagr > 5% | cash_roiic >= 0.20`: removes 218. `_roce_now_ok`: removes 2 (no-op). `is_operating`: removes 355.
- **Source is 100% FMP, not EDGAR.** edgar_roic_roiic.csv has no cash_roic/cash_roiic column, and all 1,937 fires carry the `fmp_st_cash_roiic_lindy` value. The section comment is stale. COSMETIC.
- Cash ROIIC = median of 3-year ΔFCF / ΔIC windows (fmp_statements.py:121-152), with >= 2 windows required (254 fires sit at exactly 2). ΔFCF on a commodity producer is the commodity price. 411 fires have a falling 3-year revenue CAGR and 476 a falling TTM revenue. Examples: Aramco 2222.SR (3y revenue -9.7%, assets +0.8%/yr), ConocoPhillips (3y revenue -9.1%), CNOOC, Mitsubishi Corp (MSBHF/MBI.F, cash ROIIC 0.42 on assets -0.6%/yr, via the `>= 0.20` asset-light branch). 259 fires have shrinking 3-year assets and 99 have negative TTM FCF. "Reinvestment" with a shrinking asset base is not the thesis.
- Overlap: 854 fires are also durable_reinvestment (1,854).
- Coverage: cash_roiic_lindy NaN 38% of operating names (present: JP 78%, CN 72%, IN 72%, UK 67%, US 59%, DE 59%, KR 40%).

Fires: NVDA (cash ROIC 0.28, cash ROIIC 0.90, assets +36%/yr), Tobila 4441.T, ASPEED, Pop Mart, GOOG, MSFT, TSMC: genuine. Aramco, COP, CNOOC, Mitsubishi, LOW (3y revenue -3.9%) are cycle-driven or have no reinvestment. 0QTE.L carries NaN mcap.
Severity: LOOSE (commodity ΔFCF and asset-shrinking names pass), COSMETIC (EDGAR comment).
Fix: require `asset_3y_cagr > 0` AND `revenue_3y_cagr > 0` on both branches, and >= 3 ROIIC windows; update the comment to say FMP.

## arch_quiet_compounder (314 fires, watch 809, median mcap $584m; IN 66, TW 38, JP 31, US 21)

Intent: "Quiet Compounder: proven ROIC, not noticed yet ... boring, predictable compounder before it gets discovered" (2381-2386). Tier: "QUIET measured ... price has not run (52w <= +20%), no deep drawdown ... and earnings are still compounding (TTM EBIT +10%)" (2402-2406).

Code
- `_qc_common` (2388): `insider >= 0.10` (zero-filled, so NaN fails: removes 104 of 418), `_qc_band` r52 in [-10%, +50%] (removes 203), `_roce_now_ok` (removes 0). Paths: `_qc_us` (EDGAR lindy ROIC >= 15%) or `_qc_global` (ROCE >= 15%, durability guards): removes 2,439 of 2,753. Core tier (2408): r52 <= 0.20 and 5-year max drawdown > -45% (removes 463 of 777).
- **There is no "not noticed" leg.** 64 fires have >= 10 analysts and 87 have >= 5. **The "earnings still compounding (TTM EBIT +10%)" in the tier comment is only in the exceptional tier:** 107 of 314 fires have falling TTM EBIT. LOOSE.
- The "insider" leg reads parent/state stakes: 199 fires at insider >= 50% and 8 above 90%. Examples: Aramco (0.815, the state), Chugai 4519.T/CHGCF (0.599, Roche), L'Oréal (0.571, Bettencourt + Nestlé), AFPCAPITAL.SN (0.997; a pension-fund manager that is_operating admits), Embonor.
- Coverage: insider_ownership_pct NaN 21% of operating names (US 27%, DE 30%, KR 24%). ts_maxdd_5y NaN 25% (unmeasured names keep the watch rule).

Fires: Sunmax 4728.TWO (ROCE 1.31, r52 -2%, no coverage), Tofu Restaurant 2752.TWO, Hawkins Cookers, JAC Recruitment (2 analysts) and Castrol India fit. Aramco ($1.7T, 18 analysts), L'Oréal (24), HCA (26), Cintas (20, P/E 41) and Chugai (15) are not "quiet". 58 fires have P/E > 30.
Severity: LOOSE.
Fix: core needs `sent_n_analysts <= 5` (or NaN with no covered sibling) and `fqx_ebit_ttm_g >= 0` where measured; cap insider at < 0.75 unless the holder is a person.

## arch_midcap_garp (1,080 fires, median mcap $7.3B; US 505, CN 105, JP 99)

Intent: "strong OR accelerating return on INCREMENTAL invested capital ... paired with a good earnings yield that is actually growing (attractive E/P where earnings are RISING)" (2896-2902).

Code (2955-2960)
- mcap >= $2B: removes 2,443 of 3,523. `_ey_good_growing` (2949): removes 2,290 of 3,370. `_roiic_quality`: removes 404. `is_operating`: removes 283.
- `_roiic_true` (2919) accepts `roiic_acceleration > 0` alone. **113 fires qualify on ROIIC acceleration only; 66 of them have roiic_lindy < 10%.** The `~(roiic_lindy < 0.05)` guard admits 5-10%. Examples: Merck KGaA (MKGAF/MKKGY: ROIIC 9.5%, cash ROIIC -2%, EBIT -10%, revenue -1%), Couche-Tard (6.5%), SMC QMC.F (7.8%, EBIT flat), AngloGold, Pan American Silver.
- Growth: "earnings RISING" is satisfied by revenue >= 8% alone. 91 fires pass only through revenue; 49 have EBIT growth <= 0 on both lenses. LOOSE.
- Value: the raw `earnings_yield` field is used. That field is corrupt on several lines (JGSHF 3.82, AYYLF 11.3, PHTCF 5.93, TAVHL.IS 2.81, i.e. 280-1,130% E/P). The comment in special_situation (8920) already calls it "FX-corruptible". 7 fires have E/P >= 5% while P/E is NaN or > 25. They would mostly pass through EV/EBITDA anyway, so the effect is latent.
- Coverage: roiic_lindy NaN 37%, fqx_ebit_ttm_g 58%, ev_ebitda 44% of operating names.

Fires: the top spirit is commodity-peak names: OceanaGold (spirit 0.913, all ROIIC NaN, via proxy), Impala (EBIT -33%), Amplats, Harmony. GOOG, Aramco, CVX, PetroChina and Shell (2 lines) are the largest. GOOG fits. Aramco (revenue -4.5%, EBIT +1.4%) passes on TTM EBIT +13%. 395 fires have >= 10 analysts, which is expected for mid-cap GARP.
Severity: LOOSE (ROIIC acceleration from a sub-10% base; revenue-only "earnings growth"; cyclicals at peak dominate the spirit).
Fix: `_roiic_true` = ROIIC >= 15% | cash ROIIC >= 15% | (acceleration > 0 & ROIIC >= 10%); growth = EBIT (annual or TTM) >= 8%; value = 1/P/E, not `earnings_yield`.

## arch_weinstein_stage2 (1,794 fires, watch 4,510, median mcap $1.6B; US 768, JP 260)

Intent: "price advancing above its long trend into little overhead resistance ... Stage 2 MEASURED — price above a RISING 30-week MA with positive Mansfield RS ... Weinstein's buy point is EARLY Stage 2" (3317-3341).

Code: watch (3327) = live tape (removes 68), 12m momentum > 0 & 5y range >= 0.55 (96), RS (113), within 10% of 52w high (221), not-stage-4 (0: dead, implied by trend). Core tier (3342): stage == 2, above MA30, MRS > 0, dist_hi52 >= 0.90, r52 <= 1.0, `~(dist_hi260 < 0.90)`, not clinical. It removes 2,457 of 4,251. Matches the comment.
- `measured` = ts_weinstein_stage present. 110 fires are unmeasured and run on the proxy rule, including 24 Frankfurt `.F` lines and corrupt ZA lines: INPPR.JO (Investec preference shares, $493B "mcap", momentum_12m 110 = +11,000%), NTCP.JO Netcare ($759B mcap).
- The hi260 >= 0.90 leg removes 226 Stage-2 names, 220 of them 10-50% below the 5-year high. Weinstein's Stage 1 -> 2 breakout is often well below old highs. Mildly TIGHT, and matches the comment's stated choice.
- **No sector or liquidity gate.** 773 fires (43%) are financials (464 banks, 130 capital markets, 88 insurers), plus 69 REITs and 48 utilities. 340 fires have `ts_dvol26_usd` < $100k. Fire volatility median is 0.25 vs 0.45 for operating names: the screen has become "low-volatility banks at highs". That is consistent with a pure price setup, but it dominates the list.
- Coverage: ts_weinstein_stage NaN 22% of operating names.

Fires: Ansell (MRS 0.27, at 5y high, MA30 slope 1.8%), Viewshine 002849.SZ, Kitagawa 6317.T and Schouw fit (2A-like). NVDA and AAPL are mature Stage 2, not early. KAEPF (Kansai Electric) is a utility.
Severity: LOOSE (no liquidity floor; financials dominate; proxy-rule fallback admits corrupt lines), COSMETIC (`_not_st4` dead).
Fix: add `ts_dvol26_usd >= $250k` and the `_mb_base`-style liquidity floor, drop the unmeasured fallback (or require a `.F`/ZA sanity check), and drop `_not_st4`.

## arch_concentrated_segments (568 fires, median mcap $3.0B; US 525)

Intent: "Concentrated Segment Risk: HHI >= 0.70 OR largest segment >= 70%. One bad year in the dominant segment sinks the whole business. FIRES as a NEGATIVE signal" (2262-2266).

Code (2267-2271): `is_operating` (removes 163), concentration (removes 914 of 1,482), segment_count >= 2 (removes 582).
- **The global cash-burner scrub (9411-9425) zeroes this NEGATIVE flag for double cash-burners.** 118 operating names that meet the rule are removed, i.e. the riskiest concentrated names are hidden from a risk flag. BUG (fires on the opposite of the thesis for the scrub population).
- The FMP fill has a reconciliation guard (segments must sum to 0.8-1.2x revenue, 438-444), but the EDGAR-sourced HHI does not. 346 fires use EDGAR values, and 90 fires have FMP coverage outside the guard (ABG 1.82, RDNW 0.26).
- 27 fires have NaN/0 mcap (SDH, C5N1.F, 6SQB.F). There is no `mcap > 0` leg.
- Concentration of *reported segments* is not business concentration. 379 fires have exactly 2 segments. Examples: Meta (Family of Apps 99% vs Reality Labs), NVDA (Compute & Networking 90%), GOOG, Tesla, Chevron (Upstream/Downstream), Costco. The spirit/exceptional tiers then rank the most concentrated as "exceptional" (30), which is odd for a risk tag. COSMETIC.
- Coverage: HHI NaN 92% of operating names. US 23% present; JP, IN, KR 0%; CN, DE, CA 1%; UK 3%. It is a US-only flag in practice. TIGHT.

Severity: BUG (survivability scrub on a negative flag), LOOSE (2-segment reporting artefacts), TIGHT (US only).
Fix: take `arch_concentrated_segments` out of `_segment_arch` in the scrub, apply the 0.8-1.2 reconciliation to EDGAR HHI too, add `mcap > 0`, and require segment_count >= 3 or a largest-segment share < 0.98.

## arch_wolf_trifecta (284 fires, median mcap $76m; JP 65, KR 42, IN 32, US 24)

Intent: "DOUBLE-DIGIT revenue growth + improving margins + operating leverage (opex growing slower than sales, i.e. EBITDA outgrowing revenue), bought at an undemanding multiple" (3483-3497).

Code (3498-3519): binding legs are growth `rev_yoy_c >= 0.15` (removes 807 of 1,091), mcap $10-300m (260), clean balance sheet `_clean_bs(1.0)` (142), margins (111), cheap entry (59).
- **Operating-leverage leg `season_robust | _wolf_oplev_ttm` removes 2 of 286 (no-op).** 198 fires pass only through `season_robust` (any one of 10 lenses > 0). 34 of those have TTM EBIT growing *slower* than revenue and 46 have EBITDA growing slower than revenue, which is the opposite of the leg's own words. LOOSE.
- Margins: 52 fires pass only through `fqx_inc > op_margin` without a 2pp delta. The SBC leg removes 0 (soft guard; `sbc_pct_revenue` is EDGAR-only). The melt leg removes 0.
- Growth uses annual `rev_yoy`. 54 fires have quarterly growth < 10% and 28 have negative quarterly growth.
- Coverage: rev_yoy NaN 33%, fqx_inc_ebit_margin_dt 68%, ev_ebitda 44% of operating names.

Fires: the top spirit is gold miners riding the gold price: Monument Mining MMY.V/MMTMF (revenue +189%), Austral Gold, Serabi. Also Sriracha Construction (quarterly revenue +382%) and Hebei Yichen 1596.HK (EV/EBITDA 0.6, P/E 0.6: suspicious data). R Systems, istyle and Daeduck fit the Wolf shape. Jiangsu Fengshan 603810.SS (EBITDA margin -0.2pp, inc margin 1%) and TOTL.JK (inc margin 3.7%) fit the "trifecta" only through the no-op legs. Duplicate lines appear (LIK.DE/LIK.F).
Severity: LOOSE.
Fix: require `_wolf_oplev_ttm | (ebitda_yoy > rev_yoy & ebitda_yoy > 0)`; also require `fq_rev_growth >= 0.10` where present.

## arch_liger_neglected_survivor (1,031 fires, watch 3,424, median mcap $64m; JP 272, IN 133, KR 122, TW 102)

Intent: "neglected + financially survivable (no dilution) + cheap, with an early inflection ... (tighten) 'early inflection' must be REAL: a first-positive print, EPS turning positive, or incremental EBIT margin >= 20% (not oper_lev_any's sequential drift)" (3709-3733).

Code: watch legs at 3716-3732 (balance sheet removes 700 of 1,731; mcap 539; dilution 184; cheap 139; neglect 26). Core tier (3734): removes 2,359 of 3,390.
- **The core reads raw `fqx_inc_ebit_margin`, not the domain-checked `_dt`.** 432 fires qualify only through the inc-margin leg. 47 of those have values > 1, which line 1260 defines as "out of the lens's domain ... a different fact from operating leverage". They are the top of the spirit: TVAGF 1.78, HT Media 2.64, Aigan 1.01. 3 more have inc >= 0.2 on *falling* revenue (a ratio of two negatives: Kogan rev -18%, Shriro, Bestone). BUG.
- Neglect: `_liger_cov` falls back sent -> Yahoo -> pew -> 0. **870 of 1,031 fires (84%) are "neglected" because no field exists.** 5 have a same-name sibling with >= 5 analysts (KGGNF/Kogan, HSWLF and HSW.IR/Hostelworld, HAIVF, RLLMF).
- 112 fires have falling TTM EBIT and 186 falling quarterly revenue, so "early inflection" is not established.
- Coverage: sent_n_analysts 73%, fqx_inc_ebit_margin 65%, fq_fcf 37% NaN of operating names.

Fires: Toray Textiles TTT.BK (TTM EBIT +963% off a near-zero base), Imasen 7266.T and Nippon Rietec 1938.T (inc 0.33, EBIT +37%, net cash 12%) fit. TVAGF and HTMEDIA.NS (inc margin > 1) do not. Lanpec 601798.SS ($400m, EV/S 2.7) is borderline.
Severity: BUG (out-of-domain inc margin in the core), LOOSE (NaN = neglected).
Fix: use `fqx_inc_ebit_margin_dt` and require `fq_rev_growth > 0` with it; treat NaN coverage as neglected only if no sibling line is covered.

## arch_institutional_accumulation (498 fires, median mcap $2.2B; US 481)

Intent: "Institutions are ADDING — 13F ownership share and net share count both rising — while the price consolidates or declines ... Subtracting each quarter's cross-sectional median isolates accumulation ABOVE what is typical" (7276-7303).

Code (7304-7327): adding (removes 487 of 985), flat-or-down (722 of 1,220), validity (105), persistent >= 2 of 3 quarters (84), sanity (41). The medians removed are +0.97pp ownership and +3.1% net shares; the logic matches the comment.
- **Issuance reads as accumulation.** 13F shares rise when a company sells new shares to institutions. 96 fires have share count +5% or more and 60 have +10% or more; there is no `shares_yoy` adjustment to `_ish0`. Recent IPOs whose float and index inclusion mechanically raise institutional ownership: NTSK (Netskope, r52 NaN), TTAN (ServiceTitan), KRMN (Karman). 17 fires have no 52-week history and 36 none for 2 years. LOOSE.
- 95 fires beat the median net-share change by < 1pp, and 41 beat the ownership median by < 0.5pp, which is noise-level. No `is_operating` gate (by design: "validity only"), so 140 financials and 36 utilities fire.
- Coverage: the 13F fields are NaN for 89% of operating names (US 5,564 present; CA 88). It is a US-only archetype. TIGHT by data.

Fires: NeoVolta (+11.9pp, +45% net shares, r52 -51%), ALHC, RxSight, OLED: plausible divergence. TSLA, WMT, ORCL, COST, PG are index-fund flow at mega-caps (+1.7-3.5pp).
Severity: LOOSE.
Fix: use `_ish0 - fq_shares_yoy/4` (13F shares net of issuance), require 2 years of listing, and require `_ish_x0 >= 0.02`.

## arch_retained_earnings_discount (1,353 fires, median mcap $118m; JP 444, KR 257, US 200, HK 122)

Intent: "Retained-earnings discount (Buffett's dollar-retained test, priced). Decades of ACCUMULATED retained profit exceed the whole market cap while the business still earns ... Audited EDGAR retained_earnings" (4290-4296).

Code (4301-4309): RE/mcap >= 1 (removes 3,579 of 4,932), profit (106), `is_operating` (422), P/B < 1.5 (62), FX (42), melt (15). Local `market_cap` vs local RE behind `_fx_coherent`: consistent.
- **The source is mostly FMP quarterly RE (fill at 519-537), not EDGAR.** The comment is stale.
- **RE >= mcap almost implies P/B <= 1** (RE/equity median 0.77 among fires; fire P/B median 0.51, 90th percentile 0.82). The `pb < 1.5` leg is redundant (removes 62), and the archetype is a low-P/B screen. It overlaps tangible_value (738 fires) and book_compounder_discount (299).
- **Buffett's test is the opposite of what fires.** His test is that each retained dollar created at least a dollar of market value, so the cheap-and-good case needs high returns on the retained capital. 635 of 1,353 fires (47%) have ROE < 5%. The ROE gate was demoted to a spirit weight (`_DEMOTED`, 4300), so the screen selects retainers that earned little on their retentions: the value trap the test detects. 214 fires have TTM NI <= 0 and pass only through `ni_avg`. LOOSE.
- Bad lines: MELI.BA (Argentine CEDEAR of MercadoLibre at P/B 0.07, RE/mcap 15.1), NIVF ($2.3m, r52 -99.9%), RUBI ($2.7m, ROE -5%).
- Coverage: RE NaN 44% of operating names (IN 1% present: blind). TIGHT for India.

Fires: ItoKuro 6049.T (P/B 0.63, ROE 84%: odd, but cheap), Yeebo 0259.HK, Comtec and ChinHung (ROE 41-45%, P/B 0.34-0.46) fit. The largest fires are cyclicals at mid-cycle with low ROE: Mercedes-Benz (P/B 0.47, ROE 5.3%), Maersk (3 lines, ROE 3-4%), ArcelorMittal (ROE 3.3%).
Severity: LOOSE.
Fix: restore ROE (or ni_avg / equity) >= 8% as a gate, drop the redundant P/B leg, exclude CEDEAR (.BA) lines, and fix the comment.

## arch_pension_overfunded (5 fires: WY, DXC, SCHL, CAL, MAGN; all US)

Intent: "a POSITIVE funded status (plan assets > benefit obligation) is a hidden asset ... take HALF of it" (4485-4494).

Code (4497-4502): materiality `0.5 x funded / mcap >= 0.10` removes 108 of 113. The other legs remove 0, except `is_operating` (3).
- **The input is wrong for 4 of the 5 fires.** edgar_universe_extract.py:772-776 derives funded status as `plan_assets - obligation` whenever the direct concept is absent, without checking that the two facts have the same date or the same plan. Checked against the EDGAR cache:
  - WY: 4.62e9 ≈ plan assets as of 2010 (4,773m); there is no matching obligation. A 15-year-old asset figure is being treated as a surplus.
  - CAL: 316m = 2026 plan assets (318m) minus a 2018 obligation of $2m.
  - SCHL: 157m = 2016 assets (164m) minus a 2021 obligation ($8m).
  - MAGN: 292m = 2018 assets (333m) minus a 2014 obligation ($42m).
  - Only DXC is genuine: direct FundedStatus +$742m (assets 7,062 - obligation 6,320, both 2026-03-31). That is 41% of mcap, or 20% after the 0.5 haircut. It is a real fit.
- Coverage: funded status present for 636 names (633 US). TIGHT by data.

Severity: BUG (stale and mismatched derived funded status).
Fix: derive funded status only when assets and PBO share the same `end` date within the last 2 FYs (else NaN); require the latest 10-K date <= 18 months.

## arch_xr_harvest_distribution (145 fires, median mcap $303m; US 62, HK 18, UK 12)

Intent: "forensic evidence of a CONTROLLED asset-base harvest — capex <= half of D&A — handed BACK to owners at >= 6% combined payout, priced below book" (4656-4660).

Code (4662-4673): payout >= 6% (removes 464 of 609), harvest (443 of 588), P/B < 1 (296), not-decay (74), `is_operating` (83), FX (23).
- **Currency bug: 21 of 145 fires have D&A > 60% of revenue** because USD-quoted lines carry home-currency D&A (see shared facts). Examples: ASEKY (capex $1.6B vs "D&A" 2.65e11), KAIKY, ASGLY, OJIPY, DNPCF, STAEF, SEOTF, ZHEXF, COGNY, ADERY. Their "harvest" (capex <= 0.5 D&A) and OE > 0 are artefacts. On the home lines (7259.T: capex ¥260B vs D&A ¥265B) none of them is harvesting. 34 fires show capex < 10% of D&A. BUG.
- `rev_yoy_c` is zero-filled, so 3 fires with NaN revenue growth pass "harvest, not decay".
- Payout: `buyback_yield` is EDGAR-only (NaN 55% of operating names) and filled with 0. The global `fmp_st_buyback_yield_y0` is not used here (it is used in `_payout_any`, 6001). 14 names would pass with it. 36 fires pay a dividend larger than TTM NI.
- Coverage: `_dna_loc` NaN 34%, capex 40%, dividend_yield 51% of operating names.

Fires: TNHDF (Times Neighborhood, dividend 13.6%, P/B 0.30, capex $2.2m vs D&A $70m) and Tycoon 3390.HK fit a harvest. LMMHF (Langham, a hotel trust: capex $638 vs D&A $792k, odd units) and ELRNF (Elron, a holding company) do not. CITIC (CTPCF: capex 6.3e9 vs D&A 2.69e10, mixed units) and the Japanese ADR lines above are artefacts.
Severity: BUG (unit mismatch), TIGHT minor (buyback yield).
Fix: in `_dna_loc` require `da_ttm <= ebitda_ttm` and `da_ttm <= 0.6 x revenue_ttm` (else NaN); use `buyback_yield.fillna(fmp_st_buyback_yield_y0)`; NaN `rev_yoy` should not pass.

## arch_xr_amortization_mask (95 fires, median mcap $759m; US 28, SE 13, UK 12)

Intent: "GAAP EPS is crushed by acquired-intangible amortization that has NO cash cost, so owner earnings run far above NI exactly where the intangible base is heavy" (4872-4877).

Code (4878-4888): goodwill+intangibles >= 30% (removes 325 of 420), P/E >= 15 or NaN (93), OE multiple <= 12 (78), FCF yield >= 7% (33), dilution (13), OE/NI >= 1.5 (8).
- **Mechanism not measured.** `_oe_ratio` uses total D&A minus maintenance capex, not amortisation. The intangible leg mostly counts goodwill, which is not amortised under IFRS or US GAAP; `intangibles` is NaN for 88 of 95 fires, so the split cannot be checked. 50 fires have D&A > 3x NI. Telecoms and other depreciation-heavy businesses qualify: Deutsche Telekom (D&A €24.6B, mostly network depreciation), Swisscom. LOOSE.
- **Currency bug: 13 of 95 fires.** SNEJF (Sony OTC: OE/NI = 167 from ¥ D&A against USD NI), BMBOY (Bimbo, 35x). BUG.
- Coverage: goodwill_intangibles_pct_assets NaN 36% and `_dna_loc` 34% of operating names.

Fires: CARS (Cars.com: goodwill/intangibles 66%, OE/NI 3.7, FCF yield 23%), Shift4 (FOUR), Dometic, BHG and Ekspress Grupp fit the serial-acquirer / amortisation shape. DTE.DE and SCMN.SW are depreciation, not a mask. SNEJF and BMBOY are artefacts.
Severity: BUG (units), LOOSE (D&A, not amortisation).
Fix: the same `_dna_loc` sanity as above; where an amortisation line exists (fq or EDGAR `AmortizationOfIntangibleAssets`) use `amortisation / NI >= 0.5` instead of total D&A, else require intangibles-ex-goodwill >= 10% of assets.

## arch_xr_asset_owner_catalyst (1,161 fires, median mcap $71m; KR 301, JP 149, US 133, HK 125)

Intent: "A completed object priced BELOW its reproduction/realisable value, a credible OWNER-operator ... and a CATALYST already in motion ... harvest alone is too common to count as a catalyst here" (5078-5089).

Code (5090-5110): the asset floor (removes 2,763 of 3,924) is the binding leg, then beaten-down 25% (728), not-controlled (622), insider >= 15% (391), catalyst (443), `is_operating` (279).
- **The catalyst leg passes 51% of operating names.** 284 fires pass it only through `rev_accel > 0 & oper_lev_any`, where `oper_lev_any` is almost always true when revenue accelerates. 162 fires pass only through a buyback (`buyback_yield >= 2%` or `net_buyback_ttm > 0`); 23 of those buybacks did not shrink the count. Only 565 fires have a dated first-positive / EPS turn. "Already in motion" is not what most fires show. LOOSE.
- "Owner-operator" = `insider_ownership_pct`, which counts parent stakes: Kia 0.394 (Hyundai Motor), Mercedes 0.205 (strategic holders), HCL 0.627 (promoter: fine). 112 fires at >= 60% pass the "controlled sub" exception through buyback/insider flags.
- The asset leg passes through P/B < 0.8 alone in 683 fires (59%). Bad inputs: HCLTECH.NS passes with `ncav_pct_mcap` 9.5 (an IT-services company with NCAV at 950% of mcap: local NCAV over USD mcap) at P/B 3.6. BN (Brookfield Corporation, an asset manager tagged "Consumer Staples / Household Products", so `is_operating`) passes with net debt 2.5x mcap.
- Coverage: insider_ownership_pct 21%, net_buyback_ttm 70%, ncav 42% NaN of operating names.

Fires: Cheil Grinding 001560.KS (insider 67%, P/B 0.62, net cash 68%), Roundtop 1540.TW, KVH (net cash 107% of mcap, insider 20%) and Trigyn fit. BN, Mercedes, BMW, Kia and HCL do not.
Severity: LOOSE.
Fix: catalyst = dated legs only (first-positive / EPS turned / 13D / buyback with `fq_shares_yoy <= -1%`); owner = insider >= 15% with no corporate parent; add `brookfield` (and BN/BAM) to `_known_holdco`; cap `ncav_pct_mcap` at 3.

## arch_xr_monetization_trifecta (2 fires: KODK, IH)

Intent: "(a) NET CASH ... (b) a monetizable NOL tax shield >= 30% of market cap ... (c) returns / FCF JUST INFLECTING positive" (5396-5403).

Code (5410-5420): NOL/mcap in [0.5, 20] removes 401 of 403; net cash >= 20% removes 15 of 17; EBITDA margin > 3% removes 7 of 9. Everything else is a no-op on this tiny set.
- **"NOL >= 30% of mcap" in the comment vs `nol/mcap >= 0.50` in the code.** The code comment explains this as roughly 10% in tax value at 21%. COSMETIC mismatch with the header.
- IH (iHuman): ROCE -27% but `roce_inflection = 1`. "Inflecting positive" is satisfied by a still-negative ROCE that is rising. KODK passes on FCF/CFO first-positive with net cash 21% of mcap.
- Coverage: nol_usd NaN 95% of operating names (US 2,508 present). Only 5 names meet net cash + NOL + profitable + no dilution even before the inflection leg. TIGHT by design ("vanishingly rare").

Severity: OK / COSMETIC.
Fix: align the header comment (50% gross NOL); require `roce > 0` when the inflection leg is `roce_inflection`.

## arch_xr_cash_tax_advantage (278 fires, median mcap $3.1B; US 270)

Intent: "a real book tax charge on positive pre-tax income, cash tax <= 60% of it (a >= 40% cash-vs-book wedge) ... NB: single-period cash-tax can be timing-noisy" (5611-5619). FMP path: "PERSISTENCE: the median wedge over >= 2 fiscal years must also be >= 40%" (5632-5637).

Code (5646-5651): the tax leg removes 13,491 of 13,769; value 66; `is_operating` 192. 266 fires come through EDGAR and 12 through FMP.
- **Persistence is asymmetric.** The FMP path demands a 2-year median wedge; the EDGAR path (95% of fires) is single-period TTM. The 2025 US tax law (100% bonus depreciation, domestic R&D expensing) cut US cash taxes for most filers in one year, so the US cohort is largely a one-off deferral. Examples: GOOG (book $55.1B, cash $21.5B), CRM, TMUS (book $3.26B, cash $0.86B), DIS, AT&T. Book tax on non-cash gains also produces a "wedge": IAC/PPLI (pretax $659m includes the MGM mark, cash tax $9.5m; FCF yield -6.5%). SNDK reflects spin timing. LOOSE.
- The FMP path is only allowed where both EDGAR columns are NaN. 619 US names with FMP tax rates are blocked from the persistence test even when it is available. 70 names meet the FMP test, only 10 of them non-US.
- Coverage: EDGAR tax columns NaN 89% of operating names; FMP tax rates 98%. TIGHT outside the US.

Fires: Ironwood (book $77.5m vs cash $3.5m: an NOL-utilisation pattern, P/E 5.2) and Nabors fit. GOOG, TMUS, DIS and T are the one-year law change.
Severity: LOOSE.
Fix: apply the FMP 2-year median wedge test to EDGAR names too (prefer `fq_cash_tax_wedge_med >= 0.40` wherever present), and exclude years where pretax includes > 25% non-operating gains.

## arch_ignition_fallen_angel (19 fires, median mcap $361m)

Intent: "the FALLEN-ANGEL variants — a base formed >= 40% below the prior 5-year high — carried the largest out-of-sample lift" (7468-7473). Ignition: "price/volume evidence ... volume expansion / accumulation" (7464-7467).

Code: `arch_base_ignition` (87) & `_fallen_ctx` (7474-7479). Legs: time block (removes 145 of 164), prior_dd <= 0.60 (43), validity (39), coil (15), perception (10), volume (10), 2 lenses (7), dilution / loss-year / revenue guards (1-3 each). `bs_prior_dd` = base close / prior 5y high (event_study_base.py:196), so the gate matches the comment.
- **The "volume" ignition fires with volume contracting.** 8 of 19 fires have `bs_cp_dvol_z13 < 0`, and 7 of those also have `bs_dvol_trend < 1`. They pass through `bs_updown_vol >= 1.8` (up-weeks carry relatively more volume), which can be high in a dead tape. Examples: EVVTY (dvol trend 0.40, z13 -2.09), DAL.MI/DLGCF (0.60, -2.34), OMRNY (0.39, -1.32), CAAS. In base_ignition overall, 14 of 87 show both contracting. LOOSE.
- Perception block: OTC lines of covered names count as unwatched. EVVTY ($16.6B Evolution, 2 analysts on the OTC line), DKILF (Daikin, NaN), OMRNY (Omron, 1). 10 of 19 pass with NaN coverage.
- Coverage: bs_* NaN 26-27%, bs_coil_rev 51% of operating names.

Fires: III.BK (Triple i: prior_dd 0.34, sales coil +53%, dvol trend 2.9, z13 1.3), CSS.BK, Songwon, Andhra Sugars and NANTEX fit. EVVTY, DKILF and OMRNY do not (covered, volume shrinking).
Severity: LOOSE.
Fix: count `bs_updown_vol` only with `bs_dvol_trend >= 1` or `z13 >= 0`; apply the batch-1 sibling-coverage rule to the perception block.

## arch_mb_left_for_dead_value (649 fires, median mcap $126m; US 166, KR 155, HK 58)

Intent: "fallen + deep value + FCF margin NOT yet in an improving streak — the condition present in all 40 top 10x patterns; the market prices terminal decline before the cash flow turns ... blow-up 15%" (7608-7613).

Code (7617): liquidity base (removes 1,336 of 1,985), deep (1,572 of 2,221), fallen `hi260 <= 0.40` (1,094 of 1,743), FCF not turned (325 of 974). It matches the study definition.
- **No per-share / survival guard, and the spirit rewards the wrong thing.** The fallen-angel sibling excludes `shares_growth_3y > 20%` because "the fall is per share, not a dilution-driven price collapse" (7475); this archetype does not. 89 fires have > 50% share growth over 3 years and 56 have > 100%. The spirit weights `ts_dist_hi260` at -1 (10012), so the most-diluted collapse ranks first. Top spirit is GPUS (Hyperscale Data: shares x210 in 3 years, dist_hi260 7e-8, op margin -60%), then TANH (dist 2e-5, op margin -87%). Others: AFLYY (shares +1,340% in 3 years, data), SASA.IS (+749%), Eutelsat (+374%). 129 fires are loss-making with negative FCF, 40 have negative equity and 36 fail `_not_melting`. LOOSE (the spirit ordering is close to inverted).
- "Deep" passes through P/S <= 0.3 alone in 153 fires. 9 fires pass EV/EBIT <= 6 with an insane EV.
- Coverage: ev_ebit NaN 59%, fqx_fcfm_streak 48%, ts_dist_hi260 24% of operating names.

Fires: Zhongsheng 0881.HK (P/B 0.14, dist 0.05, profitable), Volvo Car (P/B 0.37, dist 0.17) and Mosaic fit. GPUS, TANH and Mercer AEZ.F ($24m Frankfurt line) do not. Truwin 105550.KQ (FCF margin -65%) is marginal.
Severity: LOOSE.
Fix: add the `_fallen_ctx` per-share guard (`shares_growth_3y <= 0.20`) and `_not_melting`, and floor the dist_hi260 weight at 0.02 (or rank on the per-share fall).

## arch_mb_left_for_dead_insider (26 fires, all US)

Intent: "left-for-dead value with insider conviction (5.5x)" (7676-7680).

Code (7684): left_for_dead (removes 218 of 244) & `mb_fallen_insider` (insiders buying in >= 2 of 4 quarters removes 360 of 386; margins not consistent 10; not an asset play 2). It inherits the parent's lack of dilution and survival guards. Top spirit is again GPUS (shares x210; insiders in the Ault group buying). Also ALIT (op margin -96%), SPWR (shares +386% in 3 years). OSG (Overseas Shipholding) was taken private by Saltchuk in 2024; it is still in the universe with fresh-looking data, so it is a stale line.
Coverage: all 26 fires come from the SEC usf_ insider panel. Insider data exists for 5,313 US operating names and < 100 in any other country. TIGHT by data.
Fires: THRY, GAIA, SMPL (EV/EBIT 6.9, P/B 0.61, 3 insider quarters) and CLVT fit.
Severity: LOOSE (inherited).
Fix: as for the parent, plus drop names delisted/acquired (an `evt` delisting date, or a last bar > 45 days).

## arch_oak_order_conversion (122 fires, watch 4,116, median mcap $268m; CN 29, US 19, JP 16)

Intent: "Oak order-book conversion (backlog -> revenue, the MPAC pattern) ... the FORWARD BOOK is the thesis (signed orders / deposits > 20% of revenue): the core requires the deferred-revenue build" (6021-6038).

Code: watch at 6024-6033, core at 6040-6042. The deferred-revenue flag removes 3,442 of 3,564 and mcap < $1B removes 164. The growth leg removes 80. `oper_lev_any | inc >= 0.2` removes 3 (near no-op).
- **The `ebitda_inflection | ebitda_yoy > 0 | defrev` leg removes 0.** Now that the core requires `fq_defrev_build_flag == 1`, its third branch makes it tautological. COSMETIC.
- The deferred-revenue build is not an order book in mining, oil and events. Top spirit is Anglo Asian Mining (AGXKF: deferred revenue = a gold prepayment/streaming financing) and Tethys Petroleum (oil prepayment). Emerald (EEX, trade shows: seasonal event deposits, EBITDA -30%) is the largest fire. Software subscription billing (Serviceware, Raycloud) is ordinary deferred revenue. 41 fires have falling quarterly revenue. LOOSE.
- Coverage: the defrev flag is computed for 927 operating names (US 301, CN 228). `fq_defrev` is NaN for 37% of operating names.

Fires: Chien Kuo Construction 5515.TW, Southern Cross Electrical SXE.AX and CH. Karnchang CK.BK (construction backlog) fit MPAC/Oak.
Severity: LOOSE, COSMETIC.
Fix: exclude Metals & Mining / Oil & Gas / event organisers from the defrev leg (or use RPO where present, as xr_contracted_backlog does); require `fq_rev_growth > 0`; drop the dead third branch.

## arch_asymmetric_assembly (115 fires, median mcap $96m; US 28, IN 16, KR 16)

Intent: "PSIX-type levered inflection stub ... (1) a bad HEADLINE conceals improving unit economics ... (2) HEAVY debt load ... (3) DELEVERAGING ... (6) SURVIVABLE ... deliberately STRICT conjunction" (6122-6145).

Code (6151-6171): heavy debt (removes 215 of 330), beaten-down 35% (109), headline rev <= +5% (96), cheap (72), ebitda up (57), IC soft (52), net debt not rising (20). `season_robust` (3) and `strong_op_improvement` (5) are near no-ops. EBITDA > 0 removes 0.
- **There is no upper bound on distress, and the spirit ranks zombies first.** `heavy_debt` allows nde up to 30 and EV/mcap up to 30. Examples: Sadbhav Engineering (spirit 0.932, EV/mcap 25, revenue -49%, $14m), Sadbhav Infrastructure (EV/mcap 30, $9m), Changsha Broad Homes 2163.HK (nde 75: outside the cap, so it passes through EV/mcap 14.7; EV/EBITDA 80 passes "cheap" through `robust_cash_yield >= 0.15` on a $37m cap). These are near-worthless equity stubs, not PSIX (EV/mcap ~1.5-2 in May 2024). 38 fires have NaN interest coverage and NaN net-debt change, so the soft guards pass vacuously. LOOSE.
- Only 33 of 115 fires show the PSIX signature (gross profit up, revenue down). 25 overlap `arch_levered_inflection` (164) and 1 overlaps psix.
- Coverage: ev_ebitda 44%, interest_coverage 43%, fq_netdebt_change 37%, net_debt_ebitda 49% NaN of operating names.

Fires: LG Display (revenue -5%, GP +32%, EBITDA +28%, EV/EBITDA 4.5), DIC, Blackbaud (EBITDA +334% off a charge year) and TUI (2 lines) are PSIX-like. The Sadbhav pair and Changsha Broad Homes are distressed.
Severity: LOOSE.
Fix: cap EV/mcap <= 6 and nde <= 8, make IC a hard leg (>= 1.5, NaN fails) and require `robust_cy` only with `ev_ebitda <= 10`.

## arch_analyst_rerating_confirmed (76 fires, watch 223, median mcap $11.0B)

Intent: "the market has already CONFIRMED it with price: the same analyst-conviction legs (real rating, breadth, target upside) AND the stock is ACTUALLY printing a fresh 52-week high" (7233-7243).

Code (7251-7254 plus the tier at 7266): the sentiment-change leg (removes 98 of 174) and 52w-high (82) bind; the weekly-panel core removes 146 of 222. `_rating_present` and `_nan_ >= 3` remove 9 each.
- **Conviction does not require upside.** `_confirm` passes on half the present lenses, so rating <= 2.2 alone suffices. 63 of 76 fires pass through the rating only. 11 fires trade **above** the consensus target (Tokai Carbon: upside -21.6%, rating 1.0 from 4 analysts, spirit 0.933 at the top; VITROX -9.7%; AAPL -0.06%) and 23 have < 5% upside. A stock through its targets is the end of a re-rating, not its confirmation. LOOSE.
- `_rating_present` needs `yf_recommendation_mean`, which is NaN for 86% of operating names (US 12% present, IN 7%, KR 5%, TW 7%). 3,230 names with >= 3 analysts carry an FMP buy share (`sent_buy_share`) but no Yahoo rating and are excluded. TIGHT.
- No `is_operating` (20 financials); this is a perception screen, so that is acceptable.

Fires: JCDecaux (upside 24%, 13 analysts, at high), Redington (38%), AbbVie (17%, 3 sentiment turns) and Arista fit. Tokai Carbon, VITROX and AAPL do not.
Severity: LOOSE, TIGHT.
Fix: require `_ups >= 0.10` (the target still above the price) and fall back to `sent_buy_share >= 0.6` when the Yahoo rating is missing.

## arch_special_situation (305 fires, median mcap $735m; US 296)

Intent: "a dated merger / tender / going-private event with a bounded downside ... On a DEFINITIVE deal (announced merger / going-private) the return is the SPREAD to the deal price ... Fire definitive deals on the EVENT alone" (9146-9155).

Code (9156-9162): merger 238 fires, going-private 22, tender-only 58. EDGAR flags (edgar_event_signals.py) = any DEFM14A/PREM14A, SC TO-I/TO-T/14D9 or SC 13E3 **filed under the company's own CIK in the last ~24 months, undated**. `evt_*` dated anchors use 270 days. `_deal_alive` = r13 >= -20% (removes 38 merger names).
- **Acquirers and issuer tenders fire as if they were targets.** SC TO-T is filed by the bidder, SC TO-I by the issuer (its own buyback or exchange), and DEFM14A by an acquirer that issues stock. 22 fires are > $20B, mostly bidders or merger partners: BMY, OXY, BIIB, GSK (GLAXF), JAZZ, RPRX, RGLD, CDE, CTRA/DVN (merger of equals), MDT, CUK/CUKPF, FWONA/FWONK (Liberty tracking-stock reclassification), INPAP, LEN/LEN-B. ZTO/ZTOEF pass through an issuer tender. A bidder's share price has no spread to a deal price. Genuine targets such as NSC (Union Pacific), WBD and EA (take-private) are mixed in. BUG (role sign: an acquirer is not a special-situation long).
- **The undated 24-month EDGAR flag is not "dated".** A deal closed in 2025 still fires, and only the r13 guard removes broken deals.
- SPACs and BDCs: 21 fires have SPAC-like names (VIH, TVAC; FSK and Franklin BSP are BDC mergers). 119 fires are financials and 23 REITs on the merger path, which has no sector gate (Banks 25, Capital Markets 34, Shell Companies 8). A de-SPAC vote is not a spread trade.
- **The global clinical-biotech scrub (9407) zeroes 22 biotech names with a live merger / going-private signal.** That defeats the comment's stated reason for the event-only path ("biotech/tech takeout targets where op<0"). BUG.
- Coverage: US only (EDGAR forms); 296 of 305 fires are US.

Fires: NSC, WBD, EA, Talkspace (TALK, merger flag) fit. BMY, OXY, GSK, BIIB, JAZZ, MDT, DVN/CTRA and the SPACs/BDCs do not.
Severity: BUG.
Fix: count only target-side forms (SC 14D9, SC 13E3, DEFM14A where the filer is the target / no S-4 issuer), date them (<= 270 days), exempt `arch_special_situation` from the biotech scrub, and exclude `Shell Companies` and SPAC/BDC names.

---

## Summary

| archetype | fires | severity | one-line fix |
|---|---|---|---|
| arch_narrative_lag | 5,317 | BUG | Count ignored-beats / relative-strength lenses only beside an anchored lag (1,625 fires have extent 0: AAPL, JNJ, ABBV, CVX, Tencent); restore `_adv_shock` |
| arch_pension_overfunded | 5 | BUG | Derive funded status only from same-date assets and PBO; 4 of 5 fires (WY, CAL, SCHL, MAGN) are stale assets minus a mismatched obligation |
| arch_xr_harvest_distribution | 145 | BUG | Sanity-check `_dna_loc` (D&A <= EBITDA, <= 60% revenue): 21 fires are USD-line ¥/HK$ D&A artefacts (ASEKY, KAIKY, OJIPY...); fall back to the FMP buyback yield |
| arch_xr_amortization_mask | 95 | BUG | Same D&A fix (13 fires; SNEJF OE/NI 167); measure amortisation, not total D&A (DTE, Swisscom) |
| arch_liger_neglected_survivor | 1,031 | BUG | Core uses raw inc margin (47 fires > 1, 3 on falling revenue): switch to `_dt` and require growth; 84% "neglected" via NaN |
| arch_concentrated_segments | 568 | BUG | Exempt this NEGATIVE flag from the cash-burner scrub (118 hidden); reconcile EDGAR HHI (90 fires outside 0.8-1.2); add mcap > 0; US-only coverage |
| arch_special_situation | 305 | BUG | Target-side forms only (bidders BMY, OXY, GSK, BIIB, JAZZ fire); date the EDGAR flags; drop SPAC/BDC; exempt from the biotech scrub (22 targets lost) |
| arch_wolf_trifecta | 284 | LOOSE | Operating-leverage leg is a no-op (removes 2 of 286): require TTM EBIT/EBITDA growth > revenue growth |
| arch_quiet_compounder | 314 | LOOSE | Add a neglect leg (64 fires >= 10 analysts) and TTM EBIT >= 0 (107 falling); insider stake excludes corporate/state parents |
| arch_midcap_garp | 1,080 | LOOSE | ROIIC acceleration only with ROIIC >= 10% (66 fires below); EBIT growth, not revenue (91); P/E, not the corrupt `earnings_yield` |
| arch_cash_reinvest | 1,937 | LOOSE | Require positive 3y revenue and asset growth (411 / 259 fires fail); >= 3 windows; comment says EDGAR but it is 100% FMP |
| arch_retained_earnings_discount | 1,353 | LOOSE | Restore ROE >= 8% (635 fires < 5%): Buffett's test needs returns on retentions; drop CEDEAR lines (MELI.BA) |
| arch_xr_asset_owner_catalyst | 1,161 | LOOSE | Dated catalysts only (catalyst passes 51% of operating names); no corporate parents as "owners"; BN misclassified |
| arch_xr_cash_tax_advantage | 278 | LOOSE | Apply the 2-year wedge persistence to EDGAR names (US 2025 tax-law deferral: GOOG, TMUS, DIS) |
| arch_institutional_accumulation | 498 | LOOSE | Net 13F share gains of issuance (60 fires with +10% shares); require 2y listing and a material excess |
| arch_mb_left_for_dead_value | 649 | LOOSE | Add the per-share guard (56 fires with > 100% dilution; top spirit GPUS x210) and `_not_melting` |
| arch_mb_left_for_dead_insider | 26 | LOOSE | Inherits the parent (GPUS top); drop stale/acquired lines (OSG) |
| arch_asymmetric_assembly | 115 | LOOSE | Cap distress (EV/mcap <= 6, nde <= 8) and harden IC: top spirit is the Sadbhav zombie stubs (EV/mcap 25-30) |
| arch_ignition_fallen_angel | 19 | LOOSE | Up/down volume counts only with expanding dollar volume (8 of 19 fire on contracting volume); OTC sibling coverage |
| arch_oak_order_conversion | 122 | LOOSE | Exclude mining/oil prepayments and event deposits (top: Anglo Asian, Tethys, Emerald); drop the tautological leg |
| arch_analyst_rerating_confirmed | 76 | LOOSE / TIGHT | Require target upside >= 10% (11 fires trade above target); fall back to the FMP buy share when the Yahoo rating is missing (86% NaN) |
| arch_weinstein_stage2 | 1,794 | LOOSE | Add a liquidity floor (340 fires < $100k dvol); drop the unmeasured proxy fallback (INPPR.JO, .F lines); 43% financials |
| arch_xr_monetization_trifecta | 2 | OK / COSMETIC | Align the "30%" header with the 0.5x NOL gate; require ROCE > 0 on the `roce_inflection` leg (IH at -27%) |
