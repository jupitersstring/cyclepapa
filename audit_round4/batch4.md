# Archetype review, round 2, batch 4 (23 archetypes)

Method: a scratch copy of archetype_tags.py (scratchpad/r2b4/at_probe.py) was run read-only against today's refreshed inputs. It stops just before the output writes and pickles the frame plus about 180 intermediate gate series (r2b4/probe_locals.pkl, probe_df.pkl). The probe's arch_* columns match the published archetype_tags.csv exactly for all 23 archetypes (23/23 identical, 0 differences). Every leg below was then re-computed from those series. "Rebuilt N vs published M" is my AND of the legs listed; the gap is the universe-wide scrubs that run later (clinical biotech, sub-$2m shells, price ghosts, EBITDA>revenue, durability spike), which only ever remove names. "Removes X of Y" means that this leg alone fails X of the Y names that pass every other leg. Universe N = 46,526; operating 36,173; `_mb_base` (operating, mcap >= $10m, weekly $vol >= $250k) 15,304. Scripts: r2b4/lib.py plus inline snippets. fqx_m_since_* was re-read from fmp_quarterly_ext.csv, and the recompute matches `_signs` 100%.

Shared facts used in several sections (in addition to batch 1's):
- Ghost rows: 5,083 universe rows have no market cap, and 4,934 of those also have no op_margin or price. They are dead or renamed listings (Swedish Match SWMA.ST/SWMAF/SWMAY, delisted 2022; TOTAL FP.PA; GP Strategies NPD.F; Kellogg K.MX; Adtalem DVY.SG tagged "Household Products"). They still carry multi-year history fields. Any gate without `mcap > 0` can fire on them: no_dilution 93, cash_quality 164, asleep_at_wheel 66.
- Sparse twin columns. `rev_3y_cagr` is NaN for 95.0% of the universe, while `revenue_3y_cagr` is NaN for 27.6%; where both exist, corr 0.88 and median abs diff 0. `shares_3y_cagr` is 46% NaN against `shares_growth_3y` at 16%. Gates written on the sparse twin are near no-ops.
- Cross-listed lines (OTC F/Y, Frankfurt .F/.MU/.DU, BDR 34.SA, GDR .L) carry USD (or local-line) revenue and NI but statement items in the reporting currency. `da_ttm`, for example, is ARS for TCMFF/CVHSY, HKD for CTVIF/GRDZF, JPY for ADTTF, DKK for NONOF and KRW for BC94.L. `_fx_coherent` only compares mcap with revenue, so it cannot catch a third item. D&A > 50% of revenue occurs on 157 operating names with D&A/PP&E >= 0.35 alone.
- `is_otc` is absent from the frame (100% NaN). `s('is_otc', 0)` therefore reads 0 everywhere, and every "not OTC" leg is dead. `bs_cp_slope_brk` is also absent, which makes one base_ignition leg dead.
- The OTC/second-line "uncovered" leak from batch 1 recurs wherever missing analyst data reads as neglect: base_ignition, liger_lagging_inflect, and the `_liger_cov` fill.
- Venue blind spots of key inputs (share of operating names with a value): `ppe_net` US 33%, every other venue 0-2%. `da_ttm` IN 7%, AU 2%, CA 37%. `retained_earnings` IN 1%. `p_tb` IN 8%. `fq_sga` IN 8%, CN 28%. `evt_beats_8q` JP 25%, IN 25%, KR 23%, HK 20%. `pegy` (Yahoo) US 19%, CA 7%. `ev_ebit` US 32%, CA 12%, AU 20%. Insider cluster buys and `em_income` are SEC data (1,219 of 1,257 cluster flags are US).

## arch_gayner_frugal_operator (214 fires, median mcap $975m, 36 > $10B; IN 52, US 36, JP 27, CN 19, TW 15, ID 15)

Intent (l. 8164): "frugality ... read on the company: a lean cost structure (SG&A/revenue not above its industry median), SBC <= 2%, operating margin not below its industry median ... owners' money treated as owners' money ... insiders aligned (>= 10% owned, or buying), good returns on capital, a profit through the cycle."

Code (l. 8172-8184). Rebuilt 215 vs published 214 (214 in both).
- `_g_lean` (l. 8178): NaN-permissive on SG&A. `_g_sga_rev` is NaN for 53% of operating names, and 95 of 214 fires (44%) have no SG&A measured, so they pass on the op-margin-vs-industry half alone. The industry median is global across all countries, and in Pharmaceuticals (n=484) it includes loss-making drug developers (median SG&A/rev 28.6%). That lets JNJ (SG&A 25.7%, $640B) read as "frugal". Removes 128 of 343. LOOSE.
- `_g_aligned` (l. 8179): insider >= 10% OR insider_buy_flag OR the fmp flag. Insider >= 10% holds for 83% of JP, 82% IN, 89% CN, 81% HK and 82% TW operating names with a value, against 31% in the US. In Asia this measures a controlling holder, not alignment. 197 of 214 fires pass on the >= 10% leg alone (median insider 58%). The leg removes only 82 of 297, and almost all of those are US. Hence the venue mix: IN 52 and JP 27 vs US 36. LOOSE.
- SBC <= 2% is NaN-permissive (1 fire NaN). The uncovered payout is a single-year test (removes 286 of 501, second most binding). Share count `~(_g_sh3 > 0)` has zero tolerance (removes 235).
- `_g_roic >= 0.12` is the binding gate (removes 505 of 720).
- `_g_prof_share >= 0.90`: all 214 fires are at exactly 1.0, and 210 have tc_years = 8. As in batch 1, ">= 90%" means "no loss year in eight". TIGHT/COSMETIC.
- `_g_integrity` and `_not_melting` are near no-ops (remove 18 and 1).

Coverage: fq_sga NaN 47.5% of operating names (IN 92% missing). tc_uncov_payout_3y 22%, roic_lindy 12%.

Fire sanity: Caplin Point (CAPLIPOINT.NS, op 31%, ROIC 25%, promoter 74%), EMS-Chemie (EMSN.SW / EMSHF, Blocher family 71%) and Keyence (6861.T / KYCCF, op 54%) fit. Multi Bintang (MLBI.JK) is a Heineken subsidiary, with 89% "insider" = parent: frugal maybe, aligned no. JNJ, TJX (SG&A NaN), ADP and Grupo Mexico (GMBXF / GMEXICOB.MX) are not frugal-operator exemplars. 12 duplicate lines.

Severity: LOOSE (alignment and SG&A legs). TIGHT/COSMETIC (90% = 8/8).
Fix: require SG&A measured (NaN fails); define alignment as insider >= 10% AND below the country's median ownership, or insider buying, or the fmp alignment ratio; use prof_share >= 0.875.

## arch_micro_activist_inflect (843 fires, median mcap $56m; JP 270, KR 161, IN 76, HK 58, US 52)

Intent (l. 1840): microcap < $250m, short-term profit inflection, cheap (<8x EV/EBITDA; ~5x target), clean or net-cash balance sheet. The activist and backlog half is left to a scraper. The exceptional tier is a recent SC 13D, which is US only (59 names).

Code (l. 1852-1878). Rebuilt 868 vs published 843 (25 removed later by scrubs).
- Legs: rev_yoy > 0 (zero-fill means NaN fails; removes 533), mcap < $250m (579), clean balance sheet (927, the most binding), cheap (504), inflection (320), ebitda_margin > 0 (122).
- Inflection: 304 fires have a first-positive print, 370 have EBITDA margin +2pp. 106 fires pass only on a 2-5pp EBITDA-margin drift. The comment calls this "a shock-sized margin move", but the code uses 2pp. LOOSE.
- No upper cap on rev_yoy: 28 fires grow > 100%. UMIYA.BO grew +749% from a near-zero base.
- Cheap: 715 via EV/EBITDA <= 8 (460 at <= 5), 51 via P/E <= 8 only, 77 via P/B <= 0.8 only.
- Clean balance sheet: 782 via net cash > 5%.
- 112 fires have a negative operating margin (positive EBITDA only).
- No liquidity floor: 203 fires trade < $50k a week and 40 have no weekly panel. An activist cannot build a position in WHLM or 0074.KL at $1-11k a week.

Coverage: rev_yoy 33% NaN, ev_ebitda 49%, net_debt_ebitda 54%. US-heavy 13D data only in the exceptional tier.

Fire sanity: Shinwa 7607.T (EV/EBITDA 2.8, net cash 58% of mcap, rev +11%) and Tsutsumi Jewelry 7937.T fit. Monument Mining MMY.V (gold, op margin 60%, rev +189%) is a commodity price print, not an inflection. The top spirit names (0074.KL $6m, DHPIND.BO, BENGALT.BO $2k/wk) are untradeable.

Severity: LOOSE.
Fix: inflection = first-positive or a >= 5pp margin move; cap rev_yoy <= 1.0; require weekly $vol >= $50k.

## arch_no_dilution (2,598 fires, median mcap $1.8B, 615 > $10B; watch 7,752)

Intent (l. 2064): "shares roughly flat over 3y AND FCF positive 4 of 5 AND ROIC positive 4 of 5", and (core) "reinvesting at HIGH returns": lindy ROIC >= 10%.

Code (l. 2073-2093). Rebuilt 2,647 vs 2,598.
- The core ROIC >= 10% removes 5,105 of 7,752. Then FCF 4/5 removes 604, the 3-year share leg 226, and the 3-year diluted-share max (> 5%) 35. `_roce_now_ok`, `_not_melting` and `n_yrs_roic_pos` remove 0-28 each.
- BUG: there is no `mcap > 0` or price gate. 93 fires have NaN market cap, 85 of them with NaN op_margin too. These are ghost or delisted rows firing on stale 5-year EDGAR/FMP history: Swedish Match SWMA.ST (top spirit 0.968; acquired by PMI 2022), SWMAF/SWMAY, PharmChem PCHM (op NaN), FP.PA, Kellogg K.MX. The current-state guards are NaN-permissive, so they cannot catch a row with no current data.
- 394 fires are duplicate company lines.
- `n_yrs_positive_*` are capped at 5 (max 5), so "4 of 5" is as documented. 1,980 fires are 5/5.

Coverage: roic_lindy 88% (KR 52%). shares_yoy 45% NaN, but the 3-year leg carries it.

Fire sanity: AutoZone (shares -11.7%/3y, ROIC 33%), NRC Health and Apple fit. NVDA, MSFT and TSMC (the TSFA.F line) fit the letter (flat count, high ROIC) but are generic quality. Small Indian textile mills at $2m (HISARSP.BO, BLUECHIPT.BO) are untradeable, but the logic is fine. Swedish Match is a bad fire.

Severity: BUG (ghost rows; the #1 spirit name is delisted). Otherwise OK.
Fix: add `(mcap > 0) & _ncol('op_margin').notna()` (or a live-price check).

## arch_cash_quality (3,329 fires, median mcap $1.26B, 700 > $10B)

Intent (l. 2541): "cash-ROIC running materially ahead of NOPAT-ROIC over the lindy window ... earnings hide the cash". The audit-4 comment explicitly reduced "materially" to "> 0".

Code (l. 2544-2556). Rebuilt 3,415 vs 3,329 (86 removed by the spike scrub and others).
- `gap > 0` passes 80% (5,592 of 6,999) of operating names with cash ROIC > 8% and ROIC > 0. It removes 970 of 4,385, so it is close to a no-op for "materially ahead". 303 fires have a gap < 1pp and 692 < 2pp (NVDA gap 0.001, Aramco 0.011). LOOSE.
- `roic_lindy > 0`: the median fire ROIC is 8.8%, and 25% are below 6.2%.
- Lease accounting: under IFRS 16, lease principal leaves via financing, so CFO-based cash ROIC structurally exceeds NOPAT ROIC for retailers, restaurants, rental fleets and airlines. 606 fires (18.2%) sit in those industries against 12.1% of operating names, and 33 of the top 100 by spirit. The top spirit names are exactly this artifact: Migros (op margin 0.1%, cash ROIC 27.5% vs ROIC 8.1%), Taiwan FamilyMart (op 1%), create restaurants and ASAP car rental. LOOSE.
- Artifacts: Jet Airways (bankrupt; cash ROIC 12.8), Nemak 8.5, NRT ROIC 29.6. There is no cap on either ROIC.
- BUG: 164 fires have NaN mcap (ghost rows, as in no_dilution). No mcap gate.
- The harvest guard removes 741. The SBC guard removes 38 (roic_after_sbc is 91% NaN). Overlap with no_dilution: 1,202 names.

Coverage: cash_roic_lindy 86% (KR 52%). fq_capex_to_da 40% NaN, so the harvest guard is NaN-permissive.

Fire sanity: Apple (cash ROIC 1.74 vs 0.41: buyback-shrunk equity), Royalty Pharma (cash ROIC 1.19, royalty receipts vs amortized basis: a real gap) and Philip Morris CR fit. Migros, FamilyMart, ASAP, Jet Airways and Altus 8149.HK do not.

Severity: BUG (ghost rows), LOOSE (gap > 0; lease artifact).
Fix: require gap >= 3pp and mcap > 0; for IFRS-16 filers compute cash ROIC net of lease principal (or demote industries with ROU assets > 20% of assets); cap the ROICs at 1.0.

## arch_sustainable_scaler (167 fires, median mcap $71m; watch 777)

Intent (l. 3226): small-cap durable growth "confirmed either by a durable 3y CAGR or by PER-SHARE FCF growth". The audit-4 core is the source's numbers: mcap < $300m, EV/S < 3, growth >= 25%.

Code (l. 3229-3256). Rebuilt 168 vs 167.
- BUG: `_sr3 = _num('rev_3y_cagr')` is the 95%-NaN twin (95.7% NaN on operating names). Only 4 of 167 fires pass growth via the 3-year CAGR, and 162 pass on a single-year `rev_yoy >= 25%`. On the dense `revenue_3y_cagr`, 54 of 167 fires grew < 10%/yr over 3 years and 22 shrank. Telos (TLS): 3-year -8.7%, op margin -9.9%, passes on rev +52% in one year. The "durable" in the name is unmeasured.
- `_ssh3 = shares_3y_cagr` (46% NaN) has the same issue, but the fallback chain covers it.
- mcap is from `s()`, so a NaN mcap passes `mcap < 300e6` (2 fires).
- 66 fires lack `fqx_ebit_ttm_g` (the NaN-permissive earnings guard). 28 have op margin < 0 and 47 FCF margin < 0. Self-funding rests on per-share FCF growth only for 68.
- Core legs: mcap < $300m removes 127 of 295, growth >= 25% removes 176, EV/S < 3 removes 26. Only 2 fires are unmeasured.

Coverage: ev_sales 32% NaN, revenue_ttm_usd 23%.

Fire sanity: Serabi Gold (3-year +38%, EV/S 1.5), Sanyo Engineering 1960.T and Medialink 2230.HK fit. TLS, KARSN.IS (op -0.6%, 3y NaN), nTels 069410.KQ ($17m, EV/S 0.1, op 0.9%) and OMAXAUTO.NS (EBIT TTM +139% off a trough) are one-year rebounds.

Severity: BUG (sparse column makes "durable" a 1-year print).
Fix: `_sr3 = _num('revenue_3y_cagr').fillna(_num('fmp_st_revenue_3y_cagr'))`, and require it >= 15% where measured.

## arch_strong_coverage (12,238 fires = 26% of universe, 34% of operating; median mcap $993m)

Intent (l. 2213): "debt burden trivially serviceable, seen through ANY lens — interest coverage, EBITDA vs interest expense, near-zero net leverage, or outright net cash". The audit-4 rule replaced coverage with "Tillinghast: debt/EBITDA above 4x is scary".

Code (l. 2223-2231). Rebuilt 12,411 vs 12,238.
- The leverage leg passes 81% (12,718 of 15,729) of operating names >= $50m with EBITDA > 0. "Not scary" (nde <= 4) is not "trivially serviceable". 2,459 fires pass only via nde in (2, 4], and 997 sit at 3-4x.
- Interest coverage is a weight only. 1,903 fires have IC < 3 and 1,130 IC < 1.5: Intel (IC -2.8, tc_min_ic -14), Naspers/Prosus (IC 0.4), NCR Voyix NCRRP (a preferred line with a $139B "mcap"). 2,606 fires have no IC.
- The identity is diluted to "profitable with ordinary leverage". It sits below the 40% BLOATED alarm, so the sanity report is silent.

Coverage: net_debt_ebitda 49% NaN on operating names (the net-cash and _bs_lev paths compensate); interest_coverage 43%.

Fire sanity: George Risk (IC 6,108, net cash 47%), Xuchang KETOP and Alphabet fit. Intel, Prosus, NCRRP and Naspers do not.

Severity: LOOSE.
Fix: core = (IC >= 5 or tc_min_ic >= 3 where measured) & nde <= 2, or net cash; keep the current rule as watch.

## arch_lynch_pegy (1,100 fires, median mcap $627m; watch 8,280; Financials 273)

Intent (l. 2781-2806): Lynch PEGY = P/E / (growth% + yield%) <= 1 on DURABLE long-term per-share growth. The comment says Yahoo's growth "at/above its clip (>= 0.50 before clipping) is UNMEASURED, not g = 50%".

Code (l. 2781-2831). Rebuilt 1,125 vs 1,100.
- BUG: `measured=_g_ly.notna()`. The 306 fires (28%) whose own growth chain is NaN keep the watch rule, which is Yahoo's `pegy <= 1`. All 306 have `yf_earnings_growth >= 0.50`, which is exactly the case the comment declares unmeasured. They have no EPS-durability check either. Most are secondary lines without their own panels: AppLovin 6RV.MU, China Life CHL.F (Yahoo growth 849%), NXP BDR N1XP34.SA, RWE RWEA.F (a utility), CITIC Securities CI9.F, Bending Spoons (P/E 90).
- TIGHT: the published flag is Yahoo PEGY AND own PEGY. 1,428 names pass the archetype's own core (own PEGY <= 1, durable EPS, no one-off), but 625 of them are dropped only because Yahoo's PEGY is NaN (338) or > 1 (287). Yahoo pegy covers 19% of US and 7% of CA operating names. The two PEGYs correlate at only 0.44.
- Double per-share adjustment: `fg_ni_ps_3y_cagr` is already per share and is then divided again by (1 + fq_shares_yoy). 81 fires have |shares yoy| > 5%. WFC: 23.1% per-share becomes 30.6%.
- No is_operating: 343 fires are financials, utilities or funds. 67 are Capital Markets / asset managers, including EMF (Templeton Emerging Markets, a closed-end fund, P/E 2.4 on mark-to-market gains).

Fire sanity: Okayamaken Freight 9063.T (P/E 3.1, NI/share +42%/yr, EPS positive 7/8) and IwaiCosmo 8707.T fit. JPM, MS and GS (PEGY 0.6-0.86 on 17-25% 3-year NI/share recovery from a 2023 dip) fit the letter. EMF, RWEA.F and CHL.F do not.

Severity: BUG (unmeasured path rests on the capped Yahoo growth; double share adjustment). TIGHT (Yahoo gate).
Fix: drop `measured=` (unmeasured fails) and make the core the watch (do not AND with Yahoo pegy); remove the fq_shares_yoy division when `fg_ni_ps_3y_cagr` is used; exclude funds.

## arch_liger_lagging_inflect (1,059 fires, median mcap $200m, 232 > $1B, 51 > $10B)

Intent (l. 3672): "NEGLECTED microcaps ... quiet inflection the market hasn't processed": acceleration-aware growth, an incremental margin above history, cash, a clean balance sheet, <= 4 analysts, not mining/biotech, and a lag (flat or down, a 2-year base, or sales outgrowing price).

Code (l. 3685-3709). The lag leg's `beaten_down_any` was not rebuilt, so my partial rebuild gives 902 with 882 in common. 177 fires pass via the drawdown lenses.
- No size cap. 232 fires exceed $1B: Tencent TCTZF ($484B, coverage NaN on the OTC line) and TCEHY (3 analysts recorded), KLA.DE (the Frankfurt line of KLA, r52 +82%), Airbus EADSF, Reliance RLI.F. The thesis is a microcap one (Liger's RCMT, VTSI).
- `_liger_cov = ...fillna(0.0)` reads absent coverage as zero analysts. 748 of 1,059 fires (71%) have no coverage field at all. This is the batch-1 OTC leak.
- BUG (lag leg, shared helpers):
  - `flat_or_down` (l. 1174) ORs two stale quote fields and never consults the weekly panel. SKUYF r52 +113% passes with price_yoy -88%; Infomart 2492.T r52 +107% at 98% of its 52-week high; Karat, WITZ and Danlaw likewise. 23 fires up > 50% on the year pass this way.
  - Another 98 fires up > 50% pass via `beaten_down_any(0.30)` because they spiked and pulled back 30% from the 52-week high: YZOFF r52 +2,110%, Sungho 043260.KQ +2,422%, Guangdong Fenghua +254%.
  - Over the 2-year base, 333 of the 766 fires with `bs_coil_rev` measured have the price outrunning sales (coil < 0; 106 below -0.5). That is the opposite of "not processed".
- The growth gate is the most binding (removes 1,200 of 2,102). The margin leg passes 495 fires via `margin_shock_any` alone and 61 via the seasonality fallback.

Coverage: fqx_inc_ebit_margin 68% NaN (the shock and seasonality lenses stand in); coverage counts 73% NaN.

Fire sanity: Jai Corp, Alankit and 300940.SZ (rev +56%, accelerating, net cash, r52 -52%) fit. TCTZF/TCEHY, KLA.DE, EADSF, YZOFF and Infomart do not.

Severity: BUG (stale flat_or_down; spike-and-pullback read as lag). LOOSE (no size cap; NaN = neglected).
Fix: lag = panel-first (`ts_r52 <= 0` else the quote fields) AND `~(bs_coil_rev < 0)`; add mcap < $1B (country-relative); count NaN coverage as neglected only below the country's 60th mcap percentile.

## arch_cluseau_realizable_book (37 fires, median mcap $61m; HK 10, KR 9, US 7)

Intent (l. 3944): deep sub-tangible-book (< 0.6x) where >= half the tangible book is net cash, and it is being returned (>= 3% yield or a >= 2% shrink). "Distinct from ... a net-net (cash > market cap)."

Code (l. 3957-3966). Rebuilt 38 vs 37. P/TB < 0.6 removes 673 of 711 and realizable >= 0.5 removes 442; the other legs remove 0-28.
- COSMETIC: the distinctness claim is false by construction. Net cash >= 0.5 x TB with mcap < 0.6 x TB forces net cash >= 0.83 x mcap. All 37 fires have net cash >= 95% of mcap (median 172%). It is a net-net screen.
- The return is a dividend for 28 of 37; only 9 buy back. Fine.
- Artifacts:
  - RVP passes on buyback_yield 35.8% at 0% share change. The cannibal comment (l. 4416) names this as a creation/redemption artifact, but here the corroboration guard is missing. RVP's op margin is -71%.
  - Secuve 131090.KQ has shares +389% and still passes on its dividend.
  - TEK.AX is an investment company tagged Energy, with op margin NaN and NI negative.
- p_tb < pb, impossible on one basis, holds for 9 of 37: 3601.HK P/TB 0.21 vs P/B 4.0; 200521.SZ, a B-share, 0.56 vs 1.83. Two price or currency bases are mixed. Universe-wide this is 1,646 of 22,596.
- India blind: p_tb 8%.

Fire sanity: Tuniu, iHuman and Z Holdings 042420.KQ fit the arithmetic, but cash at Chinese VIEs is not obviously realizable. Chinney Kin Wing 1556.HK and Motonic 009680.KS (dividend 8.4%, net cash 176%) fit well. RVP and TEK.AX do not.

Severity: LOOSE (minor), COSMETIC (the net-net distinction).
Fix: add the cannibal corroboration `(net_buyback_ttm > 0) | (shares_yoy < 0)` to the buyback leg, plus `~(shares_yoy > 0.05)`; reword the comment (or lower the realizable bar so it is not a net-net).

## arch_owner_earnings_power (340 fires, median mcap $136m; US 74, KR 41, HK 35, SG 26)

Intent (l. 4262): "when depreciation persistently overstates true asset consumption (D&A >> replacement capex) ... owner earnings run >= 1.4x reported NI and the price is <= 10x OWNER earnings".

Code (l. 4268-4289). Rebuilt 347 vs 340. Binding legs: fmp_st_owner_earnings_yield (removes 788 of 1,135), ratio >= 1.4 (454), cheap (142).
- BUG (currency mixing): `_oe_loc = NI + D&A - maint capex` mixes `net_income_ttm` (USD on OTC/BDR lines) with `da_ttm` (reporting currency). 26 fires have D&A > 50% of revenue and 16 have D&A > revenue: Telecom Argentina TCMFF and Cablevision CVHSY (D&A ARS 2.08 trillion vs revenue $6.2B, ratio 3,781-10,639), Niraku 1245.HK (JPY D&A vs HKD), CTVIF, GRDZF, MFRVF, R1DY34.SA (Dr Reddy's BDR), AACAF and GXYYY. `_fx_coherent` passes them because it only tests mcap against revenue.
- Lease artifact: ROU depreciation has no capex counterpart. 87 fires are retail/restaurant/apparel/hotel (Reitmans RET-A.V / RTMAF ratio 11.8-20.2, Tokmanni 616, Magazine Luiza 68, Galaxy). The rental fleet's capex sits in operating cash for Vamos VAMO3.SA.
- Thin-NI artifact: median fire net margin 3.2% (10% under 0.8%), and the median ratio is 2.5. 3,277 of 15,565 operating names with NI > 0 and D&A > 0 meet ratio >= 1.4.
- `~(rev_3y_cagr < -0.02)` reads the 95%-NaN column (5 fires measured; removes 5). On `revenue_3y_cagr`, 43 fires are decliners (Maersk -12.8%, CK Hutchison).
- India blind (da_ttm 7%), AU 2%.

Fire sanity: KNOT Offshore (D&A $146m vs capex $1-4m on a shuttle-tanker fleet: real harvest economics, though drydock spend is understated) and CITIC / CK Hutchison (conglomerate D&A vs capex) are defensible. Zicom ZGL.AX is fine. TCMFF, CVHSY, Niraku, Reitmans, Tokmanni and MGLUY are artifacts.

Severity: BUG (D&A currency), LOOSE (leases; thin NI).
Fix: take D&A, capex and NI from one statement row (or require da_ttm/revenue_ttm <= 0.35 as `_dna_implied` already does); subtract lease principal (or exclude ROU-heavy industries); require NI/revenue >= 3%; switch to `revenue_3y_cagr`.

## arch_book_compounder_discount (1,204 fires, median mcap $172m; 255 financials)

Intent (l. 4452): "Audited book value compounding >= 8%/yr over the last ~5 FYs while the market prices it BELOW book". The comment on l. 4458 says "(financial-growth) book value PER SHARE, 5-year CAGR".

Code (l. 4458-4466). Rebuilt 1,290 vs 1,204. P/B < 1 removes 4,333 of 5,623 and book growth >= 8% removes 3,795.
- BUG (priority): `_eqc_f14 = equity_cagr_5y.fillna(fg_eq_ps_5y_cagr)`. Total equity is used first and per share only as fallback (1,156 fires via total, 48 via per share). The `shares_growth_5y <= 5%` guard does not equalize them: 239 of 1,204 fires (20%) have book per share growing < 8%, and 20 have it shrinking. Examples: Crédit Agricole CRLO.PA (total 184%/yr vs 6.5% per share), IDI 185% vs 7.4%, Evercel 189% vs 6%, Promisia PHL.NZ 416% (a reverse split, shares -99.99%).
- Currency: MercadoLibre MELI.BA (a CEDEAR) has P/B 0.074 (ARS price vs USD book). It is the #1 spirit name (0.982); MELI trades at about 20x book. 52 fires have P/B < 0.2.
- Inflation: book growth is nominal. The country median of eq CAGR is 46% in TR (27% of TR names clear 8%); there are 24 TR and 5 AR fires. ROE < 5% for 335 of 909 fires with NI and equity, so in a third of the fires the book "compounds" without earnings (revaluations, FX translation).

Coverage: equity_cagr_5y 28.5% NaN, the per-share series 18.8%.

Fire sanity: China Construction Bank (CICHY, per-share +14.7%, P/B 0.47, ROE 12%), ICBC and China Merchants Bank fit. Toyota (P/B 0.96, per-share 12.8%) fits. MELI.BA, CRLO.PA, PHL.NZ, JFIN (a lender; total 247% vs per share 65%) and EVRC (a shell, op NaN) do not.

Severity: BUG.
Fix: `_eqc_f14 = fg_eq_ps_5y_cagr.fillna(equity_cagr_5y)` (per share first); require `roe >= 0.08` (or NI/equity_avg); deflate by the country CPI or rank within country; drop P/B < 0.2 unless P/TB agrees.

## arch_xr_forensic_floor_growth (826 fires, median mcap $329m, 104 > $10B)

Intent (l. 4612): an "INVISIBLE floor — off-EV securities (hidden-asset gap), retained earnings above 1.5x the price, or an over-depreciated asset base — while the business on top GROWS".

Code (l. 4617-4632). Rebuilt 862 vs 826. Floor removes 4,535 of 5,397 and rev +10-100% removes 3,372.
- BUG/LOOSE: 509 of 826 fires (62%) pass the floor only via the third leg: TTM `capex <= 0.5 x D&A` with D&A >= 5% of revenue.
  - That leg uses the TTM capex. The owner-earnings sibling replaced it with `_maint_capex` precisely because a collapsed TTM window fakes it (FLNG). 108 of the 509 have capex_avg > 0.5 x D&A.
  - D&A includes acquired-intangible amortization, which is the separate `xr_amortization_mask` thesis: Amgen (Horizon), Novo Nordisk (NONOF), GE.
  - It inherits the D&A currency mix: 106 fires have D&A/revenue > 0.5, including Samsung's GDR BC94.L (155x revenue, KRW vs USD) and Advantest ADTTF (3.3x, JPY vs USD).
  - "Over-depreciated" is not a floor: nothing on the balance sheet supports the price.
- The hidden-asset leg (`_hidden_pct >= 0.5`) is net cash alone for 229 of 246 (investments_associates is 94.9% NaN), so it is a net-cash screen.
- The retained-earnings leg carries 89 (65 alone). India blind (RE 1%).

Fire sanity: Z Holdings (net cash 241% of mcap, RE 2.7x, rev +22%), HPC Holdings and Xunlei fit. Samsung BC94.L, ADTTF, NONOF, AMGN, GE and Naspers do not; they are large-cap amortizers or unit errors.

Severity: BUG.
Fix: use `_maint_capex` in leg 3, exclude intangible-heavy names (`goodwill_intangibles_pct_assets > 0.15`, as xr_depreciation_cliff does), require D&A/revenue <= 0.35, and require the associate leg (not net cash alone) for "hidden".

## arch_xr_depreciation_cliff (5 fires, all US)

Intent (l. 4826): a nearly fully depreciated asset base (D&A/PP&E >= 0.35) with low replacement capex; earnings understated and set to release.

Code (l. 4828-4840). Rebuilt 5 = 5.
- TIGHT: `ppe_net` is 88.7% NaN (US 33%, every other venue 0-2%). The D&A/PP&E leg removes 730 of 735.
- BUG: all 5 fires are artifacts of `ppe_net` excluding the real operating asset:
  - Willis Lease WLFC, D&A/PP&E 3.8: engines sit in "equipment held for operating lease".
  - Genco GNK, 11.75: "vessels, net".
  - Alta Equipment ALTG, 1.99: the rental fleet, whose purchases run through operating cash flow, so capex/D&A reads 0.09.
  - Cheer Holding CHR: PP&E $17k, a China micro shell.
  - Immersion IMMR: the consolidated Barnes & Noble Education.
  None has a depreciation cliff.

Severity: BUG (5/5 bad), TIGHT (US-only input).
Fix: denominator = fq_ppe_net (incl. ROU/fleet) or total fixed assets; exclude lessors and rental industries; require PP&E >= 5% of assets.

## arch_xr_insider_capitulation (182 fires, US 177, median mcap $1.1B)

Intent (l. 5029): "insiders CLUSTER-BUY their own crash — >= 40% off the high while demand and margins hold".

Code (l. 5034-5044). The `beaten_down_any(0.40)` leg was not rebuilt; the other legs give 427, which contains all 182.
- TIGHT: the cluster flag is SEC Form 4 (1,219 of 1,257 flags are US). The archetype is US-only, as documented.
- Timing: the flag covers 2025q3-2026q2 (sec_insider_buys.py l. 32) with no link to when the drawdown happened. 65 of 177 fires are not 40% off the 52-week high but pass via the 5-year-high lens: TPL at 0.63 of its 52-week high and VRSK at 0.67. That is an old crash, not "their own crash".
- `rev_yoy_c` is zero-filled (NaN passes `>= -0.10`), but only 3 fires are affected.
- 56 fires have op margin < 0. Most are impairments (ALIT op -96% on EBITDA 22%; PRGO; FUN). Acceptable under the impairment-robust doctrine.

Fire sanity: NKE (5 buyers, 0.48 of the 52-week high, 0.22 of the 5-year), BRBR (0.21), Zoetis and Sportradar fit. CPSH (EBITDA -0.05%, FCF negative) is marginal. TPL and VRSK are not a crash.

Severity: OK (TIGHT by data, minor LOOSE on the 5-year lens).
Fix: require `ts_dist_hi52 <= 0.60` (a 52-week crash) or a buy date after the high.

## arch_xr_cannibal_below_tbook (374 fires, median mcap $219m; JP 148, US 75, KR 66)

Intent (l. 5355): buyback while trading below TANGIBLE book and earning.

Code (l. 5362-5370). Rebuilt 379 vs 374. P/TB < 1 removes 1,967 of 2,346 and buyback >= 1% removes 966. The corroboration, share and earnings legs remove 21-76.
- 54 fires are corroborated only by `shares_yoy < 0` without net_buyback dollars; 10 of them by a shrink of less than 0.5%.
- 59 fires have TTM NI <= 0 and pass via the 5-year average (Kureha, PIOLAX). Tender-offer prints read as buyback yield: PIOLAX 59%, Sejong 103% (NI NaN).
- Overlaps cannibal_at_discount (208 of 374); the `_DEDUP_CLUSTERS` entry handles the counting.
- p_tb < pb holds for 58 fires (the two sources disagree; the p_tb side is internally consistent).
- India blind (p_tb 8%).

Fire sanity: MegaChips (shares -27.6%, P/TB 0.43, ROE 18%), Sohu, Hello Group and Seohee fit. BMW and Mercedes (P/TB 0.5-0.64, buying 2-4%) fit the letter with ROE 5-7%.

Severity: OK (minor LOOSE).
Fix: require TTM NI > 0 or an operating margin > 0, and net_buyback_ttm > 0 when buyback_yield > 20%.

## arch_xr_gaap_profit_crossover (2,774 fires, median mcap $513m, 257 > $10B)

Intent (l. 5550): "the multiple was capped ... by WHO COULD NOT OWN IT — passive index funds (S&P inclusion requires GAAP profitability) ... The turn to a first GAAP net profit mechanically unlocks that latent demand"; "on a listed (non-ghost, non-OTC) ... base".

Code (l. 5564-5579). Rebuilt 2,835 vs 2,774.
- BUG: the turn leg ORs `fmp_dyn_ni_turned_positive`, which is defined in fmp_dynamics.py l. 109-116 as "latest quarter NI > 0 and any one of the prior four quarters <= 0". It fires 2,392 of 2,774 and is the only turn for 1,331. 983 of those 1,331 have zero non-COVID loss years in the last eight.
  - Overall, 1,543 fires have no loss year and 2,051 had positive operating income in >= 6 of 8 years.
  - Examples: QUALCOMM, Honeywell, Astellas, Transurban and Renesas, each with one impairment or charge quarter. They were index-eligible all along. A name that was never profitable (opinc positive <= 2 of 8 years) accounts for 111 fires.
- BUG: `~(s('is_otc', 0) == 1)` is dead. The column is absent (`is_otc` 100% NaN), so 372 US 5-letter F/Y OTC lines fire against the stated "non-OTC" rule.
- The fire rate is 13% of operating names with revenue >= $20m, too broad for a "mandate unlock" event.

Fire sanity: SanDisk (loss years 3, op positive 2 of 8; a spin turned profitable), Marvell (loss years 3) and Shopify (4) fit. QCOM, HON, 4503.T, TCL.AX, MTN.JO and MFRISCOA-1.MX (one loss year; spirit #1) do not.

Severity: BUG.
Fix: turn = trailing-4Q NI sum crossing <= 0 to > 0 (the S&P test), or annual first-positive with >= 2 loss years in the last 4; produce `is_otc` (or use the exchange field) and fail lines without it.

## arch_base_ignition (87 fires, median mcap $409m, 10 > $10B)

Intent (l. 7382): a 2-year flat base (TIME), value accreting under it (COIL), nobody watching (PERCEPTION), and ignition by >= 2 price/volume lenses including volume.

Code (l. 7395-7468). Rebuilt 88 vs 87. Time removes 859 of 947, validity 195, coil 157, perception 108.
- COSMETIC/TIGHT: `bs_cp_slope_brk` is absent (100% NaN), so the "slope break (~1.4x)" ignition lens (l. 7454) is dead.
- Perception is NaN-permissive: 41 fires have no analyst count. All 10 fires above $10B are OTC/ADR or second lines of covered companies: AB InBev BUDFF, Daikin DKILF, HEICO HEI-A (1 analyst on the A line), Publicis PUBGY (2 on the ADR), FUJIFILM FUJIY. Same leak as batch 1.
- Coil: 52 fires pass via `fmp_dyn_unrerated_gap >= 0.15`, and 36 rely on it alone. For 15 of those 36 the 2-year sales coil is negative and for 18 the EBIT coil is negative (ADO Optronics 3516.TWO: EBIT coil -2.4), so the price did not lag the base.

Fire sanity: Triple i Logistics III.BK (2 analysts, sales coil +0.53, dvol trend 2.9x), Century Enka and Andhra Sugars (EBIT coil +2.1, uncovered) fit. BUDFF, DKILF, HEI-A, PUBGY and 3516.TWO do not.

Severity: LOOSE, COSMETIC (dead leg).
Fix: neglect needs a measured count on the primary line (map OTC/ADR lines to their primary's `sent_n_analysts`); the unrerated-gap coil counts only if `bs_coil_rev >= 0`; drop or produce the slope-break leg.

## arch_mb_inflecting_operator (1,275 fires, median mcap $359m; JP 297, US 171, KR 157)

Intent (l. 7582): "INFLECTING OPERATOR (38%, 1.1x): margins and EBIT rising, returns improving, smaller cap, a fair (not bubble) price".

Code (l. 7584-7591). Rebuilt 1,288 vs 1,275. EV/EBIT in (0, 25] removes 1,548 of 2,836, `_mb_base` 962, mcap 837, margin 541.
- The study's own lift is 1.1x, and it fires on 12% of `_mb_base` under $2B. It is a broad filter rather than an archetype.
- No growth floor: 130 fires have negative TTM revenue growth, cost-cut "inflections" on a shrinking top line. Beachbody BODI (rev -32%, ROIC lindy -73%) is #3 by spirit, alongside Obsidian, HANSHIN and Haein (-24 to -27%).
- Margin up passes 248 fires via `fqx_inc_ebit_margin_dt >= 0.20` alone, and 124 of those have a YoY op-margin delta below 0. The two lenses contradict.
- 169 fires pass "returns improving" via `roce_delta_yoy > 0` alone, and 71 have TTM ROIC below their own lindy.
- TIGHT: EV/EBIT is NaN for 4,681 base names under $2B, 1,273 of them profitable (the shared ev_ebit hole).

Fire sanity: Gulshan Polyols (EBIT TTM +238%, EV/EBIT 5.3), Sinfonia 6507.T and Sriracha Construction fit. BODI, PROP (Pledge Petroleum: op margin delta +364pp from a near-zero base) and IPT.V (silver price) are not operators inflecting.

Severity: LOOSE, TIGHT (ev_ebit).
Fix: add `fq_rev_growth >= 0` and `op_margin > 0`; require both margin lenses non-negative; derive EV/EBIT from EV / (op_margin x revenue) where ev_ebit is NaN.

## arch_mb_sequence_preignition (2,417 fires, median mcap $590m, 212 > $10B; CN 672, US 577)

Intent (l. 7664): "Two or more of the fundamental signs FIRST APPEARED 3-18 months ago and the tape has NOT yet ignited".

Code (l. 7670-7675; data fmp_quarterly_ext.py l. 134-164). Rebuilt 2,575 vs 2,417 (signs recompute 100%). Signs >= 2 removes 6,958 of 9,533 and not-ignited removes 1,492. It fires on 15.8% of `_mb_base`.
- BUG (definition): `fqx_m_since_k` is "months since the sign first appeared INSIDE THE LAST 18 MONTHS", measured from the last filed quarter. A sign that has been on for years therefore reads as having "first appeared" about 15-18 months ago. 583 fires have share_shrink at >= 17 months (Alphabet, Netflix and Novartis: perpetual buybacks), 254 have margin_inflect at the edge and 136 have rev_accel at the edge.
- The sign need not persist: 967 of 2,417 fires (40%) have none of their in-window signs live now (`fqx_<k>_now`).
- 779 fires have negative revenue growth and 615 a negative op margin (SoftBank, Meituan, Flutter).
- "Not ignited" = below 90% of the 52-week high: GOOG at 0.84 and GE at 0.84 pass.

Fire sanity: CPS Technologies (rev accel 3.8 months ago and live, margin inflect 9 months, turn positive 6 months), Amagasa 3070.T and Chindata fit the sequence. GOOG, NFLX, NVSEF, GEV, SFTBF/9984.T and Meituan (3690.HK/MPNGY) do not.

Severity: BUG.
Fix: compute "first appeared" as the start of the current run (require the sign absent in the quarter before), require >= 1 sign live now, and add `fq_rev_growth >= 0`.

## arch_xr_lookthrough_earner (13 fires, all US)

Intent (l. 5841): "a hidden associate earnings ENGINE: the share of associates' profit is a material part of pre-tax income (or vs mcap), yet the market prices the parent cheaply".

Code (l. 5846-5856). `em_income` is 96.6% NaN; it is EDGAR, so the archetype is US-only.
- BUG: 6 of 13 fires are non-common securities whose "market cap" is a preferred or CVR line: CHS Inc. CHSCO, CHSCL, CHSCP, CHSCN and CHSCM (cooperative preferreds; associate income $202m vs a "$300m mcap" = 0.65), and CELG-RI (the BMS/Celgene CVR, $231m). The non-common scrub missed them.
- `_stake_cheap` is an OR of four loose lenses (P/B < 2, FCF yield >= 3%, EV/S <= 3, EV/EBITDA <= 12). Roper (EV/EBITDA 15, EV/S 6) passes on FCF yield 6%.
- JD and JDCMF are a duplicate pair.

Fire sanity: Worthington Enterprises (WAVE JV = 67% of pretax: the textbook case), Core Labs, AMCON and JD fit. The CHS preferreds and CELG-RI do not.

Severity: BUG (6/13).
Fix: exclude symbols whose name/line is preferred or a CVR (`-P*`, `-R*`, CHSC*), i.e. extend `_is_noncommon`; require at least two of the cheap lenses.

## arch_asleep_at_wheel (2,977 fires, median mcap $3.3B, 901 > $10B; US 1,733; Financials 515)

Intent (l. 6380-6432): consensus underestimates the business: chronic beats. Core: "7 of the last 8 reports beat, or a perfect 4/4 with a >= 2% average surprise".

Code (l. 6420-6432). Rebuilt 3,326 vs 2,977 (349 scrubbed, mostly clinical biotech). The core removes 2,056 of 5,382; 0 fires are unmeasured.
- 7/8 beats hold for 10.9% of names with an 8-quarter record and 17% in the US. The 4/4 & 2% path adds 1,311 fires.
- `avg_earnings_surprise` is a ratio on near-zero EPS: the median fire is 21.5%, and 329 fires average > 100% (Fastly 103x, Beachbody 46x, Intel 13.6x). The 2% bar is meaningless.
- The most-watched stocks fire as "asleep": NVDA, AAPL, GOOG, MSFT and AMZN (45-71 analysts); 390 fires have >= 20 analysts. 588 fires are up > 50% on the year, already re-rated. `asleep_unrerated` is the measured version, so this one is a superset.
- No is_operating and no melt guard: 737 non-operating fires and 305 with op margin < 0.

Coverage: evt_beats_8q JP 25%, IN 25%, KR 23%, HK 20% vs US 57%.

Fire sanity: Yue Yuen 0551.HK (8/8, r52 +2%) fits. TLS (op -10%, average surprise 440%), VALO.BA (Argentine nominal) and FPH (op -54%) do not. The mega-caps fit the letter, not the spirit.

Severity: LOOSE.
Fix: drop the 4/4 path or require 4/4 with a surprise measured as (actual - est) / max(|est|, 0.05 x price/P/E); add `ts_r52 <= 0.30` or `sent_n_analysts <= 15`, or make asleep_unrerated the core.

## arch_lynch_reward (904 fires, median mcap $572m; US 265, JP 128, TH 88)

Intent (l. 6883): years of fundamental progress (>= 2 multi-year lenses plus a profit-durability lens) while the price went nowhere ("unpaid": 3-year sales/EBIT growth outrunning the 3-year total return by >= 25%), a balanced coil near 50, and a release or ROC setup.

Code (l. 6930-7069). Rebuilt 978 vs 904. Near-50 removes 1,437 of 2,415, unpaid 888, release/ROC 838, progress 644, capacity trap 445. Every gate is used and documented.
- `fmp_st_ebit_ps_3y_g` is a cumulative 3-year growth and is uncapped (max 1.1e8; 90th percentile 2.0). 159 fires are "unpaid" only through the EBIT-per-share leg, 66 of them on EBIT/share more than doubling and 25 on > 300%, which is base-effect from a trough. Examples: Robinsons Retail (+633%, gap 1.95, spirit #1), Fuji Kyuko (+241%), ARYZTA ARZTF (+19,976%).
- 13 fires are up > 100% on the year and 70 > 35%. ARZTF r52 +2,334% is an OTC price artifact; Ironwood is +197% and Iridium +182%. The unpaid leg uses the 3-year gap only, so a 1-year rerun is invisible.
- PRSI "Square, Inc." at $5m is a stale name/ticker mapping (Portsmouth Square).

Fire sanity: Teradata (r156 -36%, coil, release), Freelance.com, Nestlé (r156 -18%, EBIT/share +28%), L'Oréal and Sanofi fit the "progress unpaid" pattern. RRETY, ARZTF and IRWD/IRDM (already paid this year) do not.

Severity: LOOSE (minor).
Fix: cap the EBIT-per-share leg at log(1 + min(g, 1.0)), and add `ts_r52 <= 0.5` beside the 3-year gap.

## arch_greenblatt_magic (698 fires, median mcap $652m; watch 841)

Intent (l. 9049): "Greenblatt's own method is a COMBINED RANK of earnings yield and return on capital ... ranked within the listing market; the core is the top decile of that combined rank".

Code (l. 9037-9056).
- LOOSE: `_crank` ranks only inside `_mb_base`, so `_gb_rank` is NaN outside it. `measured=_gb_rank.notna()` then lets every name outside the liquid base keep the absolute watch rule. 218 of 698 fires (31%) never face the combined rank. They are mostly illiquid OTC lines of large companies: BPAQF, CHDRF/CHDRY, NETTF, CMCLF, GFIOF. 33 of them have a ranked line of the same company that failed the core; NETTF fires while NTES fails.
- The core is still a subset of the watch (ey >= 10% and ROC >= 25%), so "the absolute-cut rule is the watch" is AND-ed, not replaced. A top-decile name with EV/EBIT 11 cannot be core. 26 core fires have ROC < 25% via the fqx ROIC path.
- TIGHT: the ev_ebit hole leaves 1,698 profitable base names unrankable.
- Core rates by country are sensible: US 4.2%, JP 6.8%, CN 2.3%, TW 7.2%.

Fire sanity: OMS Energy (EV/EBIT 1.4, ROCE 79%), Alphamin, Westlake Chemical Partners, CNOOC and Aramco fit the formula. BPAQF and NETTF are duplicate-line leaks.

Severity: LOOSE, TIGHT.
Fix: rank over all operating names with a value (liquidity as a separate gate), make the core = top decile without the absolute watch AND, and fail unmeasured lines.

## Summary

| archetype | fires | severity | one-line fix |
|---|---|---|---|
| xr_gaap_profit_crossover | 2,774 | BUG | Turn = trailing-4Q NI sum crossing 0 (S&P test) or >= 2 loss years in last 4; create `is_otc` (leg is dead, 372 OTC lines fire) |
| mb_sequence_preignition | 2,417 | BUG | "First appeared" = start of current run (sign absent the quarter before); >= 1 sign live now (967 have none); rev growth >= 0 |
| lynch_pegy | 1,100 | BUG + TIGHT | Drop `measured=` (306 fires rest on the capped Yahoo growth the comment calls unmeasured); don't AND with Yahoo pegy (625 own-core names lost); no double share adjustment; exclude funds |
| book_compounder_discount | 1,204 | BUG | Per-share book CAGR first (239 fires < 8% per share); ROE >= 8%; within-country/CPI-deflated; drop P/B < 0.2 (MELI.BA #1) |
| owner_earnings_power | 340 | BUG + LOOSE | D&A/capex/NI from one statement basis (16 fires D&A > revenue: ARS/HKD/JPY D&A vs USD NI); lease-adjust; NI margin >= 3%; use revenue_3y_cagr |
| xr_forensic_floor_growth | 826 | BUG | Leg 3 on maintenance capex, excluding intangible-heavy names and D&A/rev > 0.35 (509 fires ride it); "hidden" needs associates, not net cash alone |
| xr_depreciation_cliff | 5 | BUG + TIGHT | PP&E denominator incl. lease fleet/vessels (5/5 fires are lessor/shipping/rental artifacts); input US-only |
| liger_lagging_inflect | 1,059 | BUG + LOOSE | Panel-first lag and `bs_coil_rev >= 0` (121 fires up > 50%, 333 price outran sales); mcap cap; NaN coverage ≠ neglected for large caps |
| sustainable_scaler | 167 | BUG | Use `revenue_3y_cagr` (rev_3y_cagr is 95% NaN; 54/167 grew < 10%/yr over 3y) |
| xr_lookthrough_earner | 13 | BUG | Scrub preferreds/CVRs (6/13 fires: CHS preferreds, CELG-RI) |
| no_dilution | 2,598 | BUG | Require mcap > 0 and current data (93 ghost rows; #1 spirit = delisted Swedish Match) |
| cash_quality | 3,329 | BUG + LOOSE | mcap > 0 (164 ghosts); gap >= 3pp (gap > 0 passes 80%); lease-adjust cash ROIC (top spirit = IFRS-16 retailers) |
| gayner_frugal_operator | 214 | LOOSE | Measured SG&A (95 fires unmeasured); alignment relative to country ownership norms (insider >= 10% passes 82-89% in Asia) |
| micro_activist_inflect | 843 | LOOSE | Inflection >= 5pp or first-positive; rev_yoy <= 1.0; weekly $vol >= $50k (203 fires below) |
| strong_coverage | 12,238 | LOOSE | Gate on IC >= 5 / tc_min_ic >= 3 and nde <= 2 (1,130 fires IC < 1.5; passes 81% of base) |
| asleep_at_wheel | 2,977 | LOOSE | Drop the 4/4 & 2% path (surprise ratio on near-zero EPS); add an r52 or coverage lens (390 fires >= 20 analysts) |
| mb_inflecting_operator | 1,275 | LOOSE + TIGHT | Add rev growth >= 0 and op margin > 0 (130 shrinking); derived EV/EBIT where NaN |
| base_ignition | 87 | LOOSE + COSMETIC | Neglect from the primary line's analyst count (all 10 > $10B fires are OTC/ADR lines); unrerated coil needs bs_coil_rev >= 0; slope-break leg is dead |
| greenblatt_magic | 698 | LOOSE + TIGHT | Rank all operating names (218 illiquid-line fires bypass the rank); core = top decile alone |
| lynch_reward | 904 | LOOSE (minor) | Cap EBIT/share growth at +100% in the unpaid gap; add ts_r52 <= 0.5 |
| cluseau_realizable_book | 37 | LOOSE (minor) + COSMETIC | Corroborate the buyback (RVP artifact); the comment's "distinct from a net-net" is false by arithmetic (all 37 net cash >= 95% of mcap) |
| xr_cannibal_below_tbook | 374 | OK (minor LOOSE) | Require TTM NI > 0 (59 fires on the 5-year average) |
| xr_insider_capitulation | 182 | OK (TIGHT by data) | Use the 52-week drawdown, not the 5-year high (65 fires) |
