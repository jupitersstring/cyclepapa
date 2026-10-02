# Methodology audit, round 4 — the remaining 183 archetypes on the rebuilt data

Date: 2 Oct 2026. Data: the full-universe rebuild from the filled FMP cache (46,526 names; audit gate 240 checks, 0 FAIL). Round 3 (`METHODOLOGY_AUDIT_3.md`) covered the cycle family and the 26 newest archetypes; this round covers the other 183. Each archetype was re-run leg by leg from a write-free copy of `archetype_tags.py`; the reconstructions match the published `arch_*` columns exactly for all but four, and those four within a handful of names. Full per-archetype write-ups (intent, every gate leg with line numbers, input coverage, fire sanity with named members, fix) are in `audit_round4/batch1.md` to `batch8.md`.

| Severity | Archetypes |
|---|---|
| BUG | 56 |
| LOOSE | 108 |
| TIGHT | 11 |
| COSMETIC | 5 |
| OK | 3 |

BUG = wrong result or logic error; LOOSE = admits names that do not fit the thesis; TIGHT = excludes names that should fit (usually coverage); COSMETIC = dead code or a misleading comment.

## Root causes shared across archetypes (fix once, fixes many)

Most BUG and LOOSE verdicts trace to a dozen shared causes. Fixing these in the data layer or the shared helpers repairs the bulk of the findings before any per-archetype change.

1. **D&A and financing cash flow left in the home currency on USD-quoted ADR/OTC lines.** Revenue, net income and capex are converted; `da_ttm` and `financing_cf_ttm` are not, and the currency check compares only market cap with revenue. 1,597 operating names show D&A above EBITDA. Tokyo Electron's OTC lines add ¥81B of D&A to $5B of net income; TLK's paydown yield reads 1,370x instead of 7.9%. Hits xr_forensic_multiple_gap, owner_earnings_power, overdepreciated_assets, xr_forensic_floor_growth, xr_harvest_distribution, xr_amortization_mask, xr_growth_capex_masked, xr_paydown_yield.
2. **Non-common lines leak through the scrub.** Preferreds (CHS, Liberty Broadband, Enbridge, NCR), exchangeable debt (Comcast ZONES), notes (AT&T), CVRs (CELG-RI), rights and exchange-traded notes fire in value screens at P/B 0.03-0.17 and in quality screens. Hits tangible_value, lifo_hidden_reserve, xr_nol_shield, xr_look_through_value, xr_value_unlock, coiled_base, cash_adjusted_pe, diversified_segments, xr_lookthrough_earner and others.
3. **A missing analyst count is read as neglect.** OTC and second lines carry no count while the primary line has 12-46 analysts, so Tencent, LVMH, Airbus, Keyence and AB InBev count as "undiscovered". Hits flyover (970 of 1,400 fires), coiled_base, coiled_fallen_angel, base_ignition, mb_fallen_ignored_believers. The new company map (`company_key`) lets coverage be shared across a company's lines.
4. **Dead or delisted listings fire.** Rows with no market cap or live price are never scrubbed: Swedish Match (taken over in 2022) tops no_dilution, FLIR fires in buyback_compounder. Hits no_dilution, cash_quality, buyback_compounder, capital_light_pivot, durable_reinvestment.
5. **Secondary listings are not deduplicated in the archetype output.** 195 of dead_option's fires and 78 of gayner_four_lens's are second lines of a company that already fires. The company map now supplies `is_secondary_listing`.
6. **Stale `cash_gt_ev_flag`.** 471 of 1,733 flags contradict today's cash and EV, letting net-debt names into discounted_vehicle, nol_shell, oak_asset_floor and negative_ev_value.
7. **Gross cash or clipped net cash used as "net cash".** oak_deep_value counts gross cash (282 of 582 fires carry net debt, e.g. Volkswagen, Nissan). liger_asset_backed uses a clipped value (323 fires above 100% of market cap). hidden_assets lets a 95%-missing associates input pass, so 1,929 of 1,955 fires are plain cash piles.
8. **The wrong revenue-growth column.** `rev_3y_cagr` (5% populated) is read by 11 gates that mean `revenue_3y_cagr` (72%). evsales_derating's "hard floor" removes 7 names; sustainable_scaler passes 162 of 167 on one year's growth.
9. **"Informed buyer" means one new 13F holder**, which is true for 77-98% of the liquid US base. Hits mb_smart_money_wreckage, mb_preprofit_freefall_informed, mb_conviction_confluence.
10. **The clinical-biotech scrub empties archetypes built for those names.** wolf_emerging (29 of 37 cannabis names; fires on nobody), mb_biotech_financed_hiring (118 of 166), special_situation (22 genuine takeout targets).
11. **Cumulative growth compared with annual thresholds.** gayner_missed_it tests 2.3%/yr instead of 12%/yr (162 of 347 fires fail a true 12%). book_compounder_discount mixes total equity with per-share book.
12. **Fixes promised in comments but never wired in.** mb_fallen_value_accel computes the quarterly acceleration test but never applies it (51 of 114 fires decelerating). tenbagger_path uses a flat 6% terminal margin instead of each name's own (138 loss-makers; Don't Nod at -228% shows a 100x path). narrative_lag dropped its shock leg in the tightened core.

One further TIGHT theme has no single fix: `ev_ebit` is missing for about 60% of names, so every EV/EBIT gate is blind to about 2,400 liquid, profitable names that do have an EV.

**Data-integrity note on Brightcom Group (BCG.NS).** It has no quarterly panel, so every quarterly integrity test passes on missing data. The master's own columns would have caught it: CFO/NI 0.19, through-cycle FCF margin -0.4% against a 22.5% operating margin, and EV/EBIT 0.40. Falling back to those when the quarterly panel is missing removes it and 16-36 similar names.

## Proposed fix pass

1. **Data layer and shared helpers**, the twelve root causes above: convert D&A and financing cash flow with the listing FX (reject D&A above EBITDA), widen the non-common scrub from the profile (preferred, notes, CVR, rights, ETN), share analyst coverage across a company's lines, require a live market cap, recompute cash > EV, use net rather than gross cash, swap `rev_3y_cagr` for `revenue_3y_cagr`, use a relative 13F test, exempt the biotech-built archetypes from the biotech scrub, and annualise the cumulative growth inputs.
2. **The per-archetype BUG fixes** in the table below.
3. **The LOOSE tightenings**, archetype by archetype, each checked against fire counts and named members before and after.
4. **Retag, run the audit gate, rebuild the books, re-run the top lists.**


## Per-archetype findings (BUG first)

| # | archetype | fires | verdict | fix | report |
|---|---|---|---|---|---|
| 1 | buyback_compounder | 1,163 | BUG / LOOSE | Add mcap > 0 (59 dead lines incl. SWMA, FLIR); block 3y issuance on the buyback-yield leg (Celltrion +67%); restore an equity > 0 guard | batch7 |
| 2 | capital_light_pivot | 2,105 | BUG / LOOSE | Add mcap > 0 (66; top spirit EVTN, CLCN); measure capex intensity (TSMC, MU, Tencent fire); clip roic_acceleration | batch7 |
| 3 | cheap_per_roiic | 3,020 | BUG | cpr ≤ 1.5 lets EV/EBITDA reach 1.5×ROIIC% (NVDA 26×, ASML 43×; 89% pass): cap at ~0.5 or rank in industry; add `_ev_sane`, ROIIC ≤ 1.0 | batch8 |
| 4 | concentrated_segments | 568 | BUG | Exempt this NEGATIVE flag from the cash-burner scrub (118 hidden); reconcile EDGAR HHI (90 fires outside 0.8-1.2); add mcap > 0; US-only coverage | batch6 |
| 5 | cundill_deep_value | 296 | BUG | "no deficits" reads EPS/NI *growth* shares (Comcast 8/8 fails, KEP 3/8 passes): use tc_opinc_pos/tc_years first | batch8 |
| 6 | discounted_vehicle | 1,251 | BUG / LOOSE | Recompute cash > EV today and cap net cash <= 1.0x (83 fires > 100% mcap, 18 with net debt via the stale flag); require op or FCF > 0 | batch7 |
| 7 | flyover | 1,400 | BUG | 970 fires have no analyst count anywhere (Tencent, LVMH, Airbus, Equinor OTC lines): NaN ≠ neglect; size/sibling test | batch8 |
| 8 | hidden_assets | 1,955 | BUG | Require assoc/LT-investments >= 10% of mcap (1,929 of 1,955 fires have no stake line, so this is a net-cash screen); cap at 1.5x | batch7 |
| 9 | lifo_hidden_reserve | 10 | BUG | Use NaN-preserving `pb` (the 99-fill makes P/B "known"); drop CHS preferred lines and stale ACH (6 of 10 fires are artifacts). | batch5 |
| 10 | liger_neglected_survivor | 1,031 | BUG | Core uses raw inc margin (47 fires > 1, 3 on falling revenue): switch to `_dt` and require growth; 84% "neglected" via NaN | batch6 |
| 11 | mb_biotech_financed_hiring | 48 | BUG | clinical-biotech scrub deletes 118 of 166 members (the thesis population): add to `_biotech_ok` | batch8 |
| 12 | mb_conviction_confluence | 33 | BUG | "Second arrival" `fmp_inst_new_q0 ≥ 1` is true for 77% of the US base; make it relative; add a per-share fall guard (GPUS +9,945% shares). | batch5 |
| 13 | mb_fallen_value_accel | 114 | BUG (`_accel_now` built but unused; 51/114 decelerating quarterly; base effects) | `_mb_accel &= _accel_now & ~(rev_accel > 1)` | batch1 |
| 14 | mb_preprofit_freefall_informed | 672 | BUG / LOOSE | inst_arrival (>= 1 new 13F holder) is true for 77% of US base: raise it to top-quintile new holders; pre-profit = op < 0 (150 profitable negative-FCF fires: LULU, TREX) | batch7 |
| 15 | mb_smart_money_wreckage | 234 | BUG | 13F "≥ 1 new holder" true for 98% of US names (sole leg in 92; 86 fires insiders net selling): use a top-quintile or net-ownership change | batch8 |
| 16 | narrative_lag | 5,317 | BUG | Count ignored-beats / relative-strength lenses only beside an anchored lag (1,625 fires have extent 0: AAPL, JNJ, ABBV, CVX, Tencent); restore `_adv_shock` | batch6 |
| 17 | nol_shell | 19 | BUG / LOOSE | Drop the stale cash_gt_ev leg (CETX at -142% net cash); add a shares_yoy <= 5% Section 382 guard (8 of 19 fail) | batch7 |
| 18 | oak_deep_value | 582 | BUG | "real cash" is gross cash: 282 fires net debt, 173 > mcap (VW, Nissan, Casino -36×): use net_cash_pct ≥ 0.20 | batch8 |
| 19 | oak_nav_discount | 191 | BUG (94 equity REITs via the "investment trust" substring; SFB / PRS notes; BAM OTC pb 0.1) | exclude `reit`; scrub exchange-traded debt; pb sanity vs the primary line | batch1 |
| 20 | oneil_canslim | 97 | BUG | Measured core should replace, not AND, the proxy watch (105 core-qualifiers such as ASML/DELL dropped); apply `fg_ni_ps_3y`/ROCE whenever present (Neste NI/sh -92% fires). | batch5 |
| 21 | overdepreciated_assets | 455 | BUG | da_ttm in reporting ccy vs USD revenue/capex: 110 fires D&A > revenue (Honda, Denso, JR East): FX-convert da or use fq_da/fq_capex; read revenue_3y_cagr | batch8 |
| 22 | pension_overfunded | 5 | BUG | Derive funded status only from same-date assets and PBO; 4 of 5 fires (WY, CAL, SCHL, MAGN) are stale assets minus a mismatched obligation | batch6 |
| 23 | roic_inflect | 1,079 | BUG | Cash-ROIC cross as confirmation only; 522 fires (48%) are perpetual-positive-ROIC names (VRTX, Nintendo, Lenovo) on a one-year FCF dip | batch7 |
| 24 | special_situation | 305 | BUG | Target-side forms only (bidders BMY, OXY, GSK, BIIB, JAZZ fire); date the EDGAR flags; drop SPAC/BDC; exempt from the biotech scrub (22 targets lost) | batch6 |
| 25 | tenbagger_path | 1,202 | BUG (flat 6% terminal margin for loss-makers, against the comment; 138 loss-makers; g capped at 50%) | own margin + 3pp; g cap 0.35 unless the 3y CAGR confirms | batch1 |
| 26 | wolf_emerging | 0 | BUG (dead: 29/37 cannabis names scrubbed as clinical biotech; name regex misses Tilray / Canopy / Curaleaf / ...) | curated cannabis list; exempt from `_is_clinical_biotech` | batch1 |
| 27 | xr_amortization_mask | 95 | BUG | Same D&A fix (13 fires; SNEJF OE/NI 167); measure amortisation, not total D&A (DTE, Swisscom) | batch6 |
| 28 | xr_discops_mask | 79 | BUG | 37 fires on NI ≤ 0 with no discontinued item (Ford, TAP, CAG, LUMN impairments): require disc < 0 and ≥ 50% of the gap; scrub CHSC*/JSM | batch8 |
| 29 | xr_forensic_multiple_gap | 360 | BUG | Convert `da_ttm` to the listing currency (`fq_fx_to_master`) before `_oe_loc`; reject `da_ttm > 1.05×ebitda_ttm` (214 of 360 fires have D&A > EBITDA). | batch5 |
| 30 | xr_harvest_distribution | 145 | BUG | Sanity-check `_dna_loc` (D&A <= EBITDA, <= 60% revenue): 21 fires are USD-line ¥/HK$ D&A artefacts (ASEKY, KAIKY, OJIPY...); fall back to the FMP buyback yield | batch6 |
| 31 | xr_paydown_yield | 444 | BUG | Convert financing_cf with the reporting-to-USD bridge (TLK 1,370x, PTGCF 5.7x, SCVPY 3.1x; 15 of 30 USD-line fires fail at the true ratio); require nde >= 1 | batch7 |
| 32 | xr_segment_justifies_whole | 73 | BUG (segment EBIT ignores corporate costs: median 1.86x group EBIT; 12 fires with group EBIT <= 0) | scale best segment by group EBIT / segment total; require group EBIT > 0 | batch1 |
| 33 | bab_becoming | 2,759 | BUG + LOOSE | require ts_beta_1y > 0, _bab_liquid, 1y rank <= 0.5 (342 negative-beta fires; 22 of top-50 spirit) | batch2 |
| 34 | book_compounder_discount | 1,204 | BUG | Per-share book CAGR first (239 fires < 8% per share); ROE >= 8%; within-country/CPI-deflated; drop P/B < 0.2 (MELI.BA #1) | batch4 |
| 35 | cannibal_at_discount | 673 | BUG | shrink = fq_shares_yoy.fillna(shares_yoy) <= -2%, veto if any lens shows growth (135 fires contradicted, top spirit ODTech) | batch2 |
| 36 | cash_quality | 3,329 | BUG + LOOSE | mcap > 0 (164 ghosts); gap >= 3pp (gap > 0 passes 80%); lease-adjust cash ROIC (top spirit = IFRS-16 retailers) | batch4 |
| 37 | evsales_derating | 1,015 | BUG + LOOSE | Floor on `revenue_3y_cagr` not the 95%-NaN `rev_3y_cagr` (64 shrinkers pass); require measured EV/S ≤ 0; clip EV-history artefacts | batch3 |
| 38 | expensed_growth_value | 216 | BUG | require R&D+SG&A >= 25% of revenue, rank GM within industry, fcf_yield < 10% (175/203 fires have R&D < 2%) | batch2 |
| 39 | financials_value | 271 | BUG | exclude equity/assets >= 0.8 and fund/trust names (47 CEFs incl. top-4 spirit) | batch2 |
| 40 | gayner_missed_it | 347 | BUG + LOOSE | Threshold the cumulative per-share growth at 1.12^5−1 (162/347 fail a true 12%/yr); drawdown leg also needs r52 ≤ 0.20 (31 fires up > 50%) | batch3 |
| 41 | liger_asset_backed | 1,274 | BUG/LOOSE | Use `net_cash_pct_sane` (323 fires have net cash > 100% of mcap, ATPC 1,025%); add an off-highs gate (295 at ≥ 90% of the 52w high) and `op_viable` | batch3 |
| 42 | liger_lagging_inflect | 1,059 | BUG + LOOSE | Panel-first lag and `bs_coil_rev >= 0` (121 fires up > 50%, 333 price outran sales); mcap cap; NaN coverage ≠ neglected for large caps | batch4 |
| 43 | lynch_pegy | 1,100 | BUG + TIGHT | Drop `measured=` (306 fires rest on the capped Yahoo growth the comment calls unmeasured); don't AND with Yahoo pegy (625 own-core names lost); no double share adjustment; exclude funds | batch4 |
| 44 | mb_sequence_preignition | 2,417 | BUG | "First appeared" = start of current run (sign absent the quarter before); >= 1 sign live now (967 have none); rev growth >= 0 | batch4 |
| 45 | negative_ev_value | 4,618 | LOOSE + BUG | separate or require net cash on the pb < 0.7 branch (73% of fires); recompute cash > EV from cash and EV | batch2 |
| 46 | no_dilution | 2,598 | BUG | Require mcap > 0 and current data (93 ghost rows; #1 spirit = delisted Swedish Match) | batch4 |
| 47 | owner_earnings_power | 340 | BUG + LOOSE | D&A/capex/NI from one statement basis (16 fires D&A > revenue: ARS/HKD/JPY D&A vs USD NI); lease-adjust; NI margin >= 3%; use revenue_3y_cagr | batch4 |
| 48 | sustainable_scaler | 167 | BUG | Use `revenue_3y_cagr` (rev_3y_cagr is 95% NaN; 54/167 grew < 10%/yr over 3y) | batch4 |
| 49 | tax_efficient | 1,947 | BUG + LOOSE | Write the FMP-filled ETR back to `df` so spirit works (NaN for 1,748/1,947); add a no-recent-loss-year / NOL guard (708 fires have a loss year) | batch3 |
| 50 | xr_depreciation_cliff | 5 | BUG + TIGHT | PP&E denominator incl. lease fleet/vessels (5/5 fires are lessor/shipping/rental artifacts); input US-only | batch4 |
| 51 | xr_floor_inflection | 719 | BUG + LOOSE | hidden leg only where associates present (103 fires via net cash 40-50%); inflection needs rev_yoy > 0 & margin_shock | batch2 |
| 52 | xr_forensic_floor_growth | 826 | BUG | Leg 3 on maintenance capex, excluding intangible-heavy names and D&A/rev > 0.35 (509 fires ride it); "hidden" needs associates, not net cash alone | batch4 |
| 53 | xr_gaap_profit_crossover | 2,774 | BUG | Turn = trailing-4Q NI sum crossing 0 (S&P test) or >= 2 loss years in last 4; create `is_otc` (leg is dead, 372 OTC lines fire) | batch4 |
| 54 | xr_growth_capex_masked | 24 | BUG | use fq_capex_to_da first (level D&A only if it agrees within 2x), require fcf_yield notna, cap maint_y <= 0.5 (MELI.BA 2,197x, ERO 193x, VISTAA.MX 28x) | batch2 |
| 55 | xr_look_through_value | 34 | BUG + TIGHT | Scrub ZONES/exchangeable debt lines (CCZ fires at $15.5B, P/B 0.17); FMP equity-method fill for non-US names (94% NaN) | batch3 |
| 56 | xr_lookthrough_earner | 13 | BUG | Scrub preferreds/CVRs (6/13 fires: CHS preferreds, CELG-RI) | batch4 |
| 57 | analyst_awakening | 1,656 | LOOSE | Conviction = rating AND upside ≥ 20% (764 fires < 25%); veto falling buy-share/PT (202/99 fires); drop the dead initiations lens. | batch5 |
| 58 | analyst_rerating_confirmed | 76 | LOOSE / TIGHT | Require target upside >= 10% (11 fires trade above target); fall back to the FMP buy share when the Yahoo rating is missing (86% NaN) | batch6 |
| 59 | asleep_unrerated | 815 | LOOSE | Count price-lag lenses a/b/c once; NaN-aware `_not_rich`; add `is_operating` (229 financials/REITs). | batch5 |
| 60 | asymmetric_assembly | 115 | LOOSE | Cap distress (EV/mcap <= 6, nde <= 8) and harden IC: top spirit is the Sadbhav zombie stubs (EV/mcap 25-30) | batch6 |
| 61 | bab_low_beta | 764 | TIGHT (US) / LOOSE (CN): beta ranked over a panel that is 56% illiquid in the US | rank within the liquid set or a raw-beta cap | batch1 |
| 62 | balance_sheet_return | 1,745 | LOOSE (negative-EV leg is cash > EV; 380 FCF-covered net-cash payers; Marfrig data) | neg-EV = EV < 0 or net cash >= 1x; require FCF < payout now | batch1 |
| 63 | biotech_deep_value | 119 | LOOSE (90/119 above net cash; 32 via a contradictory cash_gt_ev flag; Creso $19B) | net cash >= 0.9x mcap; flag only with net cash >= 0.8 | batch1 |
| 64 | bottleneck | 1,149 | LOOSE | Exclude GM = 100% / no-COGS (royalty trusts and a pension administrator top the spirit) and require industry-relative GM | batch7 |
| 65 | capital_discipline | 2,492 | LOOSE | 1,210 fires pass only as "dividend payer with financing outflow" (Aramco, PetroChina); 800 "un-re-rated" at P/B ≥ 1.5 via EV/EBIT ≤ 12: require shrink, relative cheapness; drop dead pb.isna() | batch8 |
| 66 | capital_returner | 1,464 | LOOSE (minor) | 27 fires cry ≥ 5% vs div + bb < 2%; fcf 1e-32 passes; fill buyback_yield from fmp_st (+63 names) | batch8 |
| 67 | cash_reinvest | 1,937 | LOOSE | Require positive 3y revenue and asset growth (411 / 259 fires fail); >= 3 windows; comment says EDGAR but it is 100% FMP | batch6 |
| 68 | cheap_sales_scaler | 2,448 | LOOSE | "margins improving" = any 1 of 10 lenses: 835 fires op margin falling; use op_margin_delta_yoy > 0; read revenue_3y_cagr | batch8 |
| 69 | cluseau_buyback_accel | 74 | LOOSE | Check the share count on the FY-yield path (Barratt +42% shares) and `by1 > 0` (11 first-time buybacks). | batch5 |
| 70 | coiled_fallen_angel | 76 | LOOSE | Neglect from a measured count (44 of 76 are NaN; 11 ADRs > $5B); no coil from `unrerated_gap` alone (34 fires); TTM op floor (Eolus -457%). | batch5 |
| 71 | customer_float | 1,514 | LOOSE | Drop total-NWC-only path (380 fires with positive CCC: PM 254d, NOVN 117d) | batch7 |
| 72 | dead_option | 2,705 | LOOSE (5-year-high-only drawdown for 1,292; no price leg; LVMH / Novo / ACN) | require the 52-week lens and EV/EBIT <= 10 or FCF >= 8% | batch1 |
| 73 | diversified_segments | 242 | LOOSE | Reconcile the EDGAR HHI too (Ford segments = 7% of revenue); add CVR `-RI` to the non-common filter; 238 of 242 are US. | batch5 |
| 74 | dta_reversal | 177 | LOOSE | Require pretax income > 0 and sustained EPS; drop ROCE OR-leg (108 fires NI <= 0) | batch7 |
| 75 | durable_reinvestment | 1,854 | LOOSE | ROIIC escape requires `asset_3y_cagr > 0` (163 harvesters); `mcap > 0` (59 delisted lines); ≥ 3 ROIIC windows. | batch5 |
| 76 | exceptional_evsg | 898 | LOOSE (no margin normalisation; 69% overlap with cheap_sales_scaler) | EV/gross profit-to-growth or a margin floor | batch1 |
| 77 | fastest_segment | 569 | TIGHT / LOOSE | 556/569 US; 120 fires engine ≥ 70% of revenue (META 99%): add share ≤ 0.6 and rev ≤ seg - 10pp; M&A guard; global segment fill | batch8 |
| 78 | gayner_four_lens | 583 | LOOSE / TIGHT (no dilution test: 27 fires > 25%; 7/8-year names excluded; ev_ebit hole) | dilution in integrity; 0.875 at 8 years; derived EV/EBIT | batch1 |
| 79 | gayner_wiggle_not_obsolete | 444 | LOOSE | Integrity falls back to master CFO/NI ≥ 0.6 and through-cycle FCF/op-margin ≥ 0.25 (both catch BCG.NS); cap `ts_r52` (40 fires up on the year). | batch5 |
| 80 | geographic_global | 696 | TIGHT / LOOSE | Fill from fmp_geo_count (94% of fires US); add largest-region share <= 60% | batch7 |
| 81 | ignition_fallen_angel | 19 | LOOSE | Up/down volume counts only with expanding dollar volume (8 of 19 fire on contracting volume); OTC sibling coverage | batch6 |
| 82 | insider_conviction | 314 | LOOSE (mild) | value leg passes 78% (On P/B 4.6, POOL 5.0): tighten to cheapness_score or P/B ≤ 1.5 | batch8 |
| 83 | institutional_accumulation | 498 | LOOSE | Net 13F share gains of issuance (60 fires with +10% shares); require 2y listing and a material excess | batch6 |
| 84 | kullamagie_breakout | 284 | TIGHT / LOOSE | Drop global leader gate where in-market RS exists (removes 348 of 632); tight = ts_tight5 <= 0.15 | batch7 |
| 85 | large_cap_quality | 839 | LOOSE | Require `roic_lindy ≥ 0.10` with spot ROCE (256 fires have lindy < 8%: GE, CRM, BeiGene, Bombardier). | batch5 |
| 86 | levered_inflection | 164 | COSMETIC / LOOSE | Core nde 1.5-3 contradicts "heavily levered stub" (215 heavier stubs in watch); dead oper_lev_any leg | batch7 |
| 87 | lindy_growth | 916 | LOOSE | Cap 3y CAGR / `rev_yoy` base effects (33 of the top-50 spirit names have 3y CAGR > 50%); require `rev_yoy` present. | batch5 |
| 88 | lynch_evgy | 1,346 | LOOSE | Require both growth legs (354 fires use a one-year EBIT print); op margin > 0; no peak margin (433 fires). | batch5 |
| 89 | mb_fallen_deep_value | 974 | LOOSE (by design) | Add `_not_melting`; P/S path only with GM >= 20% | batch7 |
| 90 | mb_fallen_value_turn | 401 | LOOSE | turn via single-quarter fmp_dyn (79 sole) / FCF swing (55); 121 fires op < 0 (DH -105%): require TTM turn + recency | batch8 |
| 91 | mb_grew_into_valuation_turning | 1,477 | LOOSE (no `_mb_base`: 308 illiquid; NaN growth share passes) | add `_mb_base`; NaN share fails | batch1 |
| 92 | mb_left_for_dead_insider | 26 | LOOSE | Inherits the parent (GPUS top); drop stale/acquired lines (OSG) | batch6 |
| 93 | mb_left_for_dead_value | 649 | LOOSE | Add the per-share guard (56 fires with > 100% dilution; top spirit GPUS x210) and `_not_melting` | batch6 |
| 94 | mb_quiet_turn | 662 | LOOSE | Sanity-clip growth/slope (top spirit = GXAI/BZAI shells); op floor (113 op < 0); quarterly acceleration where measured. | batch5 |
| 95 | midcap_garp | 1,080 | LOOSE | ROIIC acceleration only with ROIIC >= 10% (66 fires below); EBIT growth, not revenue (91); P/E, not the corrupt `earnings_yield` | batch6 |
| 96 | oak_deleveraging | 422 | LOOSE | Require EBITDA not falling (177 fall) and FCF >= 8% beside the OE lens | batch7 |
| 97 | oak_order_conversion | 122 | LOOSE | Exclude mining/oil prepayments and event deposits (top: Anglo Asian, Tethys, Emerald); drop the tautological leg | batch6 |
| 98 | owner_operator | 3,852 | LOOSE | 774 of 918 insider > 58% fires pass via a sub-1% 3y share decline (state/parent-controlled): shrink ≤ -2%, roce floor on US path | batch8 |
| 99 | quiet_compounder | 314 | LOOSE | Add a neglect leg (64 fires >= 10 analysts) and TTM EBIT >= 0 (107 falling); insider stake excludes corporate/state parents | batch6 |
| 100 | retained_earnings_discount | 1,353 | LOOSE | Restore ROE >= 8% (635 fires < 5%): Buffett's test needs returns on retentions; drop CEDEAR lines (MELI.BA) | batch6 |
| 101 | tangible_value | 1,646 | LOOSE + data (CHS / LBRDP preferreds, BN; p_tb < pb on 343) | extend `_is_noncommon`; recompute p_tb in one currency | batch1 |
| 102 | tax_verified_earnings | 2,365 | LOOSE (book ETR; cash-tax check measured on 50; 115 op losses) | require op margin > 0 and a cash-tax measure | batch1 |
| 103 | understated_earnings | 1,957 | LOOSE (D&A-driven CFO > NI; 787 with capex >= 0.8x D&A; 152 FCF < 0) | require FCF / NI >= 1.2 and year-ago persistence | batch1 |
| 104 | weinstein_stage2 | 1,794 | LOOSE | Add a liquidity floor (340 fires < $100k dvol); drop the unmeasured proxy fallback (INPPR.JO, .F lines); 43% financials | batch6 |
| 105 | weschler_levered_equity | 201 | LOOSE | EBITDA not falling (87 fall); cap holdco-consolidated FCF (Almendral, Cogeco) | batch7 |
| 106 | wolf_compounder | 165 | LOOSE | Replace the no-op `oper_lev_any`; require an observed streak (95 of 165 NaN) and quarterly growth. | batch5 |
| 107 | wolf_trifecta | 284 | LOOSE | Operating-leverage leg is a no-op (removes 2 of 286): require TTM EBIT/EBITDA growth > revenue growth | batch6 |
| 108 | wolf_turnaround | 676 | LOOSE | Remove EBITDA-growth path; require prior-FY loss (245 fires carry no turn flag) | batch7 |
| 109 | wolf_value_catalyst | 455 | LOOSE | 106 fires net debt via NCAV/FCF "fortress" (UNISON -2.3×); 20 fires rev > 100%: net cash ≥ 0 on every route; base-effect cap | batch8 |
| 110 | xr_asset_owner_catalyst | 1,161 | LOOSE | Dated catalysts only (catalyst passes 51% of operating names); no corporate parents as "owners"; BN misclassified | batch6 |
| 111 | xr_audited_streak_unrerated | 2,091 | LOOSE | 2-of-8 lens vote makes AMZN/META/Samsung (+248%) "unrerated": ≥ 3 lenses + r52 ≤ rev growth; fix dead NaN-permissive arm (222 names) | batch8 |
| 112 | xr_cannibal_below_cash | 34 | LOOSE | Finance regex regardless of sector (RBKB bank, CTT bank deposits, Jet2 deposits) | batch7 |
| 113 | xr_cash_tax_advantage | 278 | LOOSE | Apply the 2-year wedge persistence to EDGAR names (US 2025 tax-law deferral: GOOG, TMUS, DIS) | batch6 |
| 114 | xr_contracted_backlog | 90 | LOOSE | AND the price legs and add RPO growth (GEV EV/EBITDA 96, SNDK pass) | batch7 |
| 115 | xr_deferred_revenue_lead | 375 | LOOSE | Drop FCF-only "cheap" (GEV at 96x EBITDA); require observed defrev growth. | batch5 |
| 116 | xr_forced_seller | 174 | LOOSE | nothing seller-specific (NFLX, INTU, BSX derating); zero-filled ebitda_yoy admits 8: NaN-aware, industry-relative drop, split check | batch8 |
| 117 | xr_hidden_segment_compounder | 38 | TIGHT / LOOSE | 37/38 US; Xerox/L3Harris/EQT segment jumps are M&A: add acquisition guard | batch8 |
| 118 | xr_latent_inflection_floor | 260 | LOOSE | "floor" via P/B or gross cash with net debt (114 fires; Atlantic Sapphire -48×, Orpea -13.5×): require net cash ≥ 0 | batch8 |
| 119 | xr_leverage_detonation | 86 | LOOSE (46/86 op margin > 10%; gold / coal windfalls via FCF-first-positive) | op margin <= 8%; exclude commodity producers | batch1 |
| 120 | xr_neg_ev_growth | 200 | LOOSE | 121 fires only via gross-cash > EV flag (Xiaomi net cash 14%, WuXi 7%): require net cash ≥ 50% | batch8 |
| 121 | xr_nol_shield | 36 | LOOSE + TIGHT (cash-tax OR-leg admits Enbridge preferreds ×4; zero-tax regimes; US-only) | ETR <= 15% when measured; require NOL / DTA evidence | batch1 |
| 122 | xr_oneoff_loss_mask | 74 | LOOSE | Test "one-off": `ni_avg ≥ 0` and `tc_loss_years < 3` (29 fires have a negative 5y-average NI). | batch5 |
| 123 | xr_owned_realestate_value | 34 | LOOSE | Use land/buildings concepts; current fires are depreciated plant (E&P, cable, tyres) | batch7 |
| 124 | xr_peer_margin_gap | 993 | LOOSE (320 with falling margins; global industry median; refiners) | require margin delta >= 1pp; industry x region median | batch1 |
| 125 | xr_pre_scale_margin | 153 | LOOSE (minor) / COSMETIC | Size or EV/GP cap (AMZN passes); remove the dead gap leg | batch7 |
| 126 | xr_reusable_assembler | 514 | LOOSE | Clip incremental EBITDA margin ≤ 1 (53 fires); use `revenue_3y_cagr` (`rev_3y_cagr` 95% NaN); `roic_lindy ≥ 0.10`. | batch5 |
| 127 | xr_value_unlock | 199 | LOOSE | Leverage guard on the P/B branch (top 4 carry net debt 12-19x mcap); move `forensic_hidden_pct` above use (dead leg); drop CCZ. | batch5 |
| 128 | xr_wc_normalization | 152 | LOOSE | Make CFO < earnings − 3pp mandatory (31 fires are capex-crushed, not WC). | batch5 |
| 129 | asleep_at_wheel | 2,977 | LOOSE | Drop the 4/4 & 2% path (surprise ratio on near-zero EPS); add an r52 or coverage lens (390 fires >= 20 analysts) | batch4 |
| 130 | bab_multibagger | 871 | LOOSE | Require the low-beta third (266 at rank 0.35-0.50); drop the 43%-base-rate margin-shock leg; ROCE ≥ 10% as AND | batch3 |
| 131 | base_ignition | 87 | LOOSE + COSMETIC | Neglect from the primary line's analyst count (all 10 > $10B fires are OTC/ADR lines); unrerated coil needs bs_coil_rev >= 0; slope-break leg is dead | batch4 |
| 132 | blindspot | 1,666 | LOOSE + COSMETIC | Drop the unmeasured-liquidity escape (615 fires); add `_not_melting`/`op_viable` (400 op < 0); remove the dead ADV leg | batch3 |
| 133 | cash_adjusted_pe | 1,466 | LOOSE | Gate `earnings_oneoff_flag == 0 & op_margin > 0` (153 / 128 fires); require fq net-cash sign agreement (54; TBB AT&T notes line); net cash ≤ mcap | batch3 |
| 134 | cluseau_realizable_book | 37 | LOOSE (minor) + COSMETIC | Corroborate the buyback (RVP artifact); the comment's "distinct from a net-net" is false by arithmetic (all 37 net cash >= 95% of mcap) | batch4 |
| 135 | coiled_base | 378 | LOOSE | Neglect = max analysts across same-name lines (45 fires, e.g. Keyence, AB InBev); scrub NCRRP-type preferred lines | batch3 |
| 136 | crisis_asset_backed_recovery | 788 | LOOSE | Tangible P/TB < 0.8 (264 pass on total book only); peer-relative crash (45 > 95% collapses); `op_viable` | batch3 |
| 137 | double_inflect | 172 | LOOSE (minor) | Require `op_margin > 0` and 0 < `fqx_roic_ttm` ≤ 1 (23 op < 0; BNC ROIC 223) | batch3 |
| 138 | gayner_frugal_operator | 214 | LOOSE | Measured SG&A (95 fires unmeasured); alignment relative to country ownership norms (insider >= 10% passes 82-89% in Asia) | batch4 |
| 139 | greenblatt_magic | 698 | LOOSE + TIGHT | Rank all operating names (218 illiquid-line fires bypass the rank); core = top decile alone | batch4 |
| 140 | growth_algo | 519 | LOOSE | Require EBIT growth > revenue growth (134/359 fail; op-leverage leg is a 96% base rate) | batch3 |
| 141 | kpi_threshold | 3,329 | LOOSE | require op line positive now, NI turn only with an op turn, veto earnings_oneoff (787 op < 0 fires; INTC) | batch2 |
| 142 | lindy_fcf | 3,557 | LOOSE (minor) | Core needs ≥ 7 FCF years as commented (89 fires have 3-6); FCF-margin floor 5% as AND (59 below 3%); mcap > 0 (144 NaN) | batch3 |
| 143 | lynch_reward | 904 | LOOSE (minor) | Cap EBIT/share growth at +100% in the unpaid gap; add ts_r52 <= 0.5 | batch4 |
| 144 | mb_fallen_insider | 109 | LOOSE + TIGHT | Add `op_viable`/`_not_melting` (52/109 op < 0), a share-count guard and net insider buying > 0 (16 net sellers) | batch3 |
| 145 | mb_fallen_stressed | 971 | LOOSE | drop size-relative stress legs when nde < 3 & cover >= 3; strip captive finance; add dilution guard | batch2 |
| 146 | mb_inflecting_operator | 1,275 | LOOSE + TIGHT | Add rev growth >= 0 and op margin > 0 (130 shrinking); derived EV/EBIT where NaN | batch4 |
| 147 | mb_tree_recipe | 362 | LOOSE | add ~(shares_growth_3y > 0.20) & _not_melting (115 fires > 50% dilution lead the spirit) | batch2 |
| 148 | micro_activist_inflect | 843 | LOOSE | Inflection >= 5pp or first-positive; rev_yoy <= 1.0; weekly $vol >= $50k (203 fires below) | batch4 |
| 149 | net_cash_returner | 1,617 | LOOSE | Total yield ≥ 2% with shares not growing, FCF > 0 and payout covered (348 FCF < 0, 198 issuing) | batch3 |
| 150 | oak_asset_floor | 1,282 | LOOSE | drop the retired 40% & cash > EV leg or add p_tb <= 1 (331 sole fires); add _fx_coherent | batch2 |
| 151 | self_funded_returner | 2,569 | LOOSE | Require a shareholder return ≥ 1% (195 return nothing; outflow = debt repayment) | batch3 |
| 152 | spinoff_asset | 2 | TIGHT + LOOSE | P/TB not P/B for the floor; NaN tape should not count as an orphan (both fires) | batch3 |
| 153 | strong_coverage | 12,238 | LOOSE | Gate on IC >= 5 / tc_min_ic >= 3 and nde <= 2 (1,130 fires IC < 1.5; passes 81% of base) | batch4 |
| 154 | tenbagger_credible | 605 | LOOSE | use EV/S where net debt > 0; terminal margin from own margin x 1.5, not a 6% floor; deflate ARS/TRY growth | batch2 |
| 155 | wolf_seal | 1,682 | LOOSE | P&L margin >= 2pp or dated turn; dist_hi52 <= 0.9; veto ts_r52 sign conflicts (DWWEF +12,400%) | batch2 |
| 156 | xr_baron_compounder | 558 | LOOSE | Measure suppressed earnings (OM < own median or SG&A/R&D outgrowing revenue; 175 fires OM ≥ 20%); use `revenue_3y_cagr` | batch3 |
| 157 | xr_cannibal_below_tbook | 374 | OK (minor LOOSE) | Require TTM NI > 0 (59 fires on the 5-year average) | batch4 |
| 158 | xr_cash_leads_book | 500 | LOOSE | require CFO growth > 0 and NI growth >= -10% (368/500 fires have NI falling) | batch2 |
| 159 | xr_compounding_deployer | 285 | LOOSE | evsg leg only with EV/EBIT <= 20; acq >= 2% of assets; ROIIC <= 1 | batch2 |
| 160 | xr_confluence | 924 | LOOSE | quality_crisis needs a second dislocation lens; >= 4 families or drop the broadest member; dedupe lines | batch2 |
| 161 | xr_float_compounding | 128 | LOOSE | Customer float = deferred revenue ≥ 10% or (NWC < 0 & CCC < 0, not Materials/Energy) (100/128 are payables float); revenue growth ≥ 10% (25 shrinking) | batch3 |
| 162 | xr_gross_margin_lead | 245 | LOOSE | Cap revenue growth at 100% and GM delta at 10pp; require OM below its own norm; exclude commodity sectors | batch3 |
| 163 | xr_margin_mixshift | 45 | TIGHT + LOOSE | US-only by input; require two cheap lenses; clip mix uplift <= 1 | batch2 |
| 164 | xr_quality_crisis | 3,402 | LOOSE | Quality needs ≥ 2 legs incl. ROIC ≥ 10% (base rate 59%; 1,775 fires ROIC < 5%); crisis needs dd52 ≤ −20% (496 within 15% of the 52w high) | batch3 |
| 165 | mb_fallen_ignored_believers | 377 | TIGHT | Analyst coverage 44% NaN in base (KR 26%, CN 36% covered); borrow sibling-line counts | batch7 |
| 166 | post_reorg | 2 | TIGHT | 49 US-only reorg names; EBIT-yield lens only when `op_margin > 0` (WW fires on EV/EBIT 8.8 with op -30%). | batch5 |
| 167 | spinoff_value | 4 | TIGHT (US feed; orphan unobserved on 3/4) | price below the first close for new listings | batch1 |
| 168 | xr_clean_net_net | 203 | TIGHT (US NCAV 7,850 NaN) + data (HCLTECH NCAV 9.5x) | EDGAR NCAV fill; cap NCAV at 3x unless net cash corroborates | batch1 |
| 169 | lindy_margin | 1,202 | TIGHT + COSMETIC | lift the 0.6 op / 0.8 EBITDA caps when tc_min_opm >= 15% (Moutai, VeriSign, TPL, OBIC out); `measured` path is dead | batch2 |
| 170 | low_sbc_quality | 1,900 | TIGHT | fill SBC from fq_sbc_pct_revenue / fmp_sbc_to_revenue (+5,427 eligible names); add ~_roce_oneoff_suspect | batch2 |
| 171 | reinvest_inflect | 633 | TIGHT | fall back to fqx_roic_slope8 where roiic_acceleration is NaN (69%); add mcap >= 10m & _not_melting | batch2 |
| 172 | spinoff_quality | 1 | TIGHT + COSMETIC | _ncol for the net-cash leg (zero-fill passes NaN); scrub when-issued lines; widen spin feed beyond EDGAR | batch2 |
| 173 | xr_insider_capitulation | 182 | OK (TIGHT by data) | Use the 52-week drawdown, not the 5-year high (65 fires) | batch4 |
| 174 | xr_investment_remark | 3 | TIGHT | require carrying value dated <= 6 months and carry <= assets - cash (XNET suspect) | batch2 |
| 175 | xr_stake_fv_gap | 3 | TIGHT | Coverage limited to 179 EDGAR disclosers; add mcap ≥ $10M (TOPS $4M) | batch3 |
| 176 | forensic_payout_confirmed | 3,579 | COSMETIC | Comment says "extra count" but it is `_NOT_COUNTED`; either count it with `fcf_ttm > 0` & yield ≤ 25% or delete it. | batch5 |
| 177 | qarp | 720 | OK / COSMETIC (dead `_qarp_cheap`; yrs-ROIC leg near no-op) | delete dead code | batch1 |
| 178 | xr_monetization_trifecta | 2 | OK / COSMETIC | Align the "30%" header with the 0.5x NOL gate; require ROCE > 0 on the `roce_inflection` leg (IH at -27%) | batch6 |
| 179 | gayner_pay_up_quality | 66 | OK (COSMETIC) | drop dead lens3 and years >= 7 legs; 0.5% share tolerance; frame cross-listed lines on home venue | batch2 |
| 180 | mb_tree_recipe_10x | 333 | OK / COSMETIC | Require ≥ 3 cheapness lenses (22 ranked on ≤ 2); optional `_not_melting` | batch3 |
| 181 | dividend_verified_value | 65 | OK | optional: tc_uncov == 0 where measured (22 fires allow one uncovered year) | batch8 |
| 182 | xr_triple_floor | 90 | OK (minor: net cash > 1x on 15, dividend > NI on 12) | use `net_cash_pct_sane`; dividend <= NI | batch1 |
| 183 | xr_verified_deleveraging | 32 | OK | deduplicate lines | batch1 |
