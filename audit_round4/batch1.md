# Archetype review, round 2, batch 1 (23 value / forensic / XR / multibagger archetypes)

Method: an instrumented COPY of `archetype_tags.py` (scratchpad/r2/archetype_tags_inst.py: identical code, it stops right before the output block and writes `df` plus every length-N local Series to scratchpad/r2/df.parquet and locals.parquet; the repo was only read). The copy reproduces the published `archetype_tags.csv` exactly for all 23 columns (23/23 identical, 0 mismatches). Every gate leg was then recomputed from those inputs in scratchpad/r2/p1.py ... p6.py (outputs p*.out). The parquet dumps were deleted afterwards to free disk; re-run scratchpad/r2/run_inst.py to regenerate them. Reconstructions match the published flag exactly for 22/23, and dead_option matches 2,703 of 2,705: two names differ in the 8-lens drawdown helper because of float32 rounding. Each reconstruction includes the post-gate scrubs (non-common lines, EBITDA>revenue, corrupt price, sub-$2M shell, price ghost, clinical biotech). "Removes X of Y" = names that pass every other leg (after the scrubs) and fail this leg alone. Universe N = 46,526; operating (`is_operating`) 36,173.

Shared facts (in addition to batch 1's):
- tc_years is capped at 8, so a ">= 90% of years" test means "no loss year in eight" (Gayner lens 1: 2,434 pass at exactly 1.0; 163 at 7/8 fail).
- Several value gates read `s()`-zero-filled inputs: `rev_yoy_c`, `net_cash_pct_c`, `ncav_pct`, `fcf_yield`, `ebitda_margin`, `fcf_margin`. A zero-fill fails `>= x` gates for x > 0, so it only matters where the threshold is <= 0. That happens for `nde`, which is 99-filled and so fails every `nde <= x` leg.
- Duplicate listing lines (OTC ADR / F-share / Frankfurt `.F` / preferred) are not deduplicated in any gate. 78 of 583 Gayner fires and 195 of 2,705 dead_option fires are second lines of a name that already fires.
- Non-common securities that escape `_is_noncommon` and fire value gates: CHS Inc preferreds CHSCM/CHSCN/CHSCO/CHSCP (p_tb 0.027), LBRDP (Liberty Broadband pref, p_tb 0.043), Stifel SFB and Prudential PRS (exchange-traded notes), Enbridge preferred lines EBBGF/EBGEF/EBBNF/ENBFF. All are `_is_noncommon == False`.
- Mis-sectored financials pass `is_operating`: BN (Brookfield Corp, "Consumer Staples / Household Products") and ADAM (Adamas Trust, a mortgage REIT, "Information Technology / Software").

## arch_gayner_four_lens (583 fires, median mcap $2.36B, 160 > $10B)

Intent: "Tom Gayner ... four lenses": a profitable business with good returns, management with talent and integrity, reinvestment dynamics, and a fair price ("the least important of the four"). The comment adds: "Every number below is Gayner's own ... a sign, or a peer frame — never an invented absolute."

Code (8061-8117; gate 8112-8114)
- Lens 1 (8061-8070): lindy ROIC >= 12%, profit share >= 0.90 over >= 5 FY, op_margin > 0. This is the binding leg (removes 1,840 of 2,423). Because of the 8-year cap, ">= 90%" means "no loss year". 30 names fail only because they have 7 of 8 profitable years. TIGHT, as the window is mislabelled.
- Lens 2 (8077-8087): talent is `opm >= 0.9 x tc_med_opm`. Integrity is CFO/NI >= 0.6, no Beneish flag, no data-quality flag, SBC <= 5% and no one-off flag. Removes 390 of 973. The CFO/NI test is NaN-permissive (95 fires have no `fq_cfo_to_ni`). Dilution is not part of integrity: 27 fires have 3-year share growth > 25% (300573.SZ +98.5%, HTLM, SATLF, ROUTE.NS, REFEX.NS, CLEO.JK). Those pass lens 3 through the "organic" route, which has no share-count test. LOOSE.
- Lens 3 (8097-8105): organic (ROIIC >= 12% and growth >= 5%: 471 fires), acquirer (111), or discipline (173; 62 fires qualify only through discipline). Tencent passes with ROIIC -2.3% through discipline. OK.
- Lens 4 (8106-8110): 0 < EV/EBIT <= 1.5x the listing-country median. Removes 226 of 809. 74 of those names have NaN ev_ebit. The other 150 are above 1.5x the median, which is US 26.2, CN 43.5, IN 31.7, TW 29.0, JP 17.7, HK 16.0, UK 20.3. A CN/IN name at 40x EV/EBIT is "fair", while MSFT at 21.3 passes in the US. The frame is a peer frame, as promised. The ev_ebit hole (59.5% NaN among operating names) is TIGHT.
- The comment's "never an invented absolute" is false: the gate uses ROIC 12%, ROIIC 12%, growth 5%, acquisitions 2% of assets, capital return 2%, SBC 5%, CFO/NI 0.6 and 1.5x. COSMETIC.

Coverage: roic_lindy / tc_years NaN 12.5% of the universe; tc_med_opm 30%; fq_cfo_to_ni 60%; ev_ebit 59.7%. Venues: US 192, IN 67, CN 54, JP 51, TW 40, UK 27.

Fire sanity
- Fit: CMOCTEZ.MX (ROIC 38%, 8/8 years, EV/EBIT 7.1 vs MX median 9.8), ASY.L, CASS.JK, SMSM.JK, CBAV.MC, 4021.T, MSFT, 2222.SR.
- Questionable: CDNIF (Logista, op margin 2.5%, a distributor). 0700.HK plus TCEHY and TCTZF (three lines of one name).
- Bad: 300573.SZ (share count nearly doubled in 3 years) is not a Gayner integrity / discipline name.

Severity: LOOSE (no dilution test outside the discipline route; duplicate lines), TIGHT (8-year "90%"; ev_ebit hole), COSMETIC (comment).

Fix: add `~(_g_sh3 > 0.05)` to `_g_integrity`; use `prof_share >= 0.875` when tc_years == 8; derive EV/EBIT from EV / (op_margin x revenue) where it is NaN.

## arch_dead_option (2,705 fires, median mcap $373m, 179 > $10B)

Intent: "Option Mispriced as Dead": a real operating cash cow, priced as if dead (beaten down >= 40%), with cash yield > 5%.

Code (1749-1766)
- `beaten_down_any(0.40)` (1196-1215) has eight lenses. 1,292 of 2,705 fires pass only through the 5-year-high lens (52-week drawdown shallower than 40% and r52 > -40%). 1,141 fires have r52 > -20%, 766 trade at >= 50% of their 5-year high, and 124 are > $10B with r52 > -30%. Examples: LVMH (three lines; 0.48 of its 5-year high, r52 -0.23, EV/EBIT 12.6), Novo Nordisk (two lines), Accenture (EV/EBIT 9.2, ts_r13 +0.38). Removes 6,042 of 8,748.
- `_cash_yield_any`: any one of FCF yield, owner-earnings yield, robust cash yield or cash-return-EV above 5%. 1,008 fires pass without FCF yield > 5%, and 350 have FCF yield <= 0. Removes 1,292.
- There is no price/valuation leg beyond the yield: 416 fires have EV/EBIT > 25 (2010.SR SABIC 130).
- `_op_viable(0)` lets DH (Definitive Healthcare, op margin -105%) through on EBITDA 14.6%, gross margin 76% and FCF. Removes 188.
- `nde <= 3` (99-fill): 173 names fail only on unmeasured nde, 103 of them net cash. TIGHT (minor).
- `ebitda_margin > 0` and `_roce_now_ok` remove 0 (no-ops).

Coverage: ts panel NaN 23.5%; robust_cash_yield 21%; nde NaN 54% (then 99). Venues: US 562, CN 492, KR 390, IN 191, HK 184.

Fire sanity: GTEC (EV/EBIT 3.2, 0.09 of 5-year high, FCF yield 51%) and 2YU.F fit. KODI / Sewon (no tape data, nde -63) are unverified. LVMH, Novo, ACN, SABIC are not "priced as dead". DH is a loss-maker.

Severity: LOOSE. 2,705 fires (7.5% of operating names) is a generic "down from the 5-year high with some cash yield" screen. It overlaps mb_fallen_deep_value (273 fires), regime_cyclical (228) and tangible_value (294).

Fix: require the 52-week lens (`_dd52 <= -0.40` or `ts_r52 <= -0.40`), not 5-year-high only; add a price leg (EV/EBIT <= 10 or FCF yield >= 8%); require FCF yield > 0 in addition to any other yield.

## arch_tangible_value (1,646 fires, median mcap $87m)

Intent: "P/TB < 0.7 with tangible equity > 50% of book equity (real assets, not goodwill)"; Altman Z and debt/assets demoted to weights.

Code (1966-1981)
- `p_tb in (0, 0.7)` removes 15,939 of 17,585.
- The tangible-equity / equity > 0.5 leg is NaN-permissive and removes 8 (near no-op). It passes only 2 fires on NaN.
- `fcf_yield >= -0.15` removes 312; `net_cash_pct <= 1.0` removes 185; `_not_melting` removes 28.
- `is_operating` appears twice (1970 and 1981). COSMETIC.
- Data inconsistency: in 343 fires `p_tb < 0.95 x pb`, which is impossible when tangible equity <= equity. Jindo 088790.KS: teq ~= eq, p_tb 0.22 vs pb 0.31. RE.L: p_tb 0.32 vs pb 0.60. The two multiples come from different price/share snapshots. 95 fires have pb >= 0.7.

Coverage: p_tb NaN 48.9% (universe and operating alike). Venues: JP 388, KR 276, HK 230, US 223.

Fire sanity
- Fit: 2055.T (P/TB 0.32, Altman 3.1), 003650.KS (P/TB 0.31, ROCE 48%), 155660.KS, 9854.T.
- Bad (not common equity): CHSCM/CHSCN/CHSCO/CHSCP and LBRDP (P/TB 0.03-0.04: a preferred's price over the common's book). WVVIP (pref) also leaks.
- Bad (other): BN (Brookfield, a financial labelled Consumer Staples; Altman 0.49). CPEFF (Evolve Royalties, every fundamental NaN, top spirit 0.918).
- 94 fires have op margin < 0 and FCF < 0 by design (asset play). 679 have Altman < 1.8 (a weight only).

Severity: LOOSE (preferred/notes leak, financial leak), data BUG (p_tb vs pb mismatch on 21% of fires), COSMETIC.

Fix: extend `_is_noncommon` to US tickers whose base symbol plus P/M/N/O shares a name with a common line; require `p_tb >= pb x 0.98` (or recompute p_tb = mcap / tangible_equity in one currency).

## arch_qarp (720 fires, median mcap $714m)

Intent: "high lindy ROIIC AND not already discounted as a compounder ... paying fair for great".

Code (2482-2506)
- ROIIC in [0.15, 1.0] removes 797; ROIC lindy >= 10% removes 1,219.
- Cheap = two of {EV/EBITDA <= 12, P/E <= 18, EV/FCF <= 20}, or EV/EBIT <= 12. Removes 768. 14 fires pass on EV/EBIT alone. 49 fires have EV/EBIT > 20 (WMMVF 25.1, passing through EV/EBITDA 8.8 and P/E 16.2).
- `shares_growth_3y <= 0.02` (NaN fails) removes 188.
- `n_yrs_positive_roic >= 4` removes 2 (near no-op). `_roce_now_ok` removes 0.
- `_qarp_cheap` (2485-2490) is computed and never used: dead code. COSMETIC.

Coverage: roiic_lindy NaN 40.7% (36.6% operating); ev_ebitda 49%; p_e 50%. roiic present: US 8.9k, CN 2.9k, IN 2.7k, JP 2.4k.

Fire sanity: BRBR, MegaStudyEdu 215200.KQ, CAMB3.SA, 2767.T, NOVO-B.CO, KPEL.BO fit. LVE.AX ($3m, ROCE 101%) is marginal. Rio Tinto (three lines; ROIIC 0.16-0.43 on a cyclical base) is mechanical.

Severity: OK / COSMETIC.

Fix: delete `_qarp_cheap`; deduplicate lines.

## arch_balance_sheet_return (1,745 fires, median mcap $275m, 111 > $10B)

Intent: "Companies returning cash NOT generated by operations (dividends/buybacks while FCF is negative — funded from the balance sheet), PLUS negative-EV businesses (net cash exceeds market cap)".

Code (2152-2181)
- Uncovered route: `_returns_any & (tc_uncov_payout_3y >= 2 | (NaN & fcf_y < 0))` and `_bsr_funded`. 1,173 fires: 1,136 via the 3-FY count, 37 via the TTM fallback. 800 of these have positive FCF now (347 at > 5%), so the payout is uncovered in history, not today. 360 pass "funded" only via `nde_known <= 0`.
- Negative-EV route: `(EV < 0 | cash_gt_ev_flag > 0) & is_operating`. `cash_gt_ev_flag` means cash > EV, which is not EV < 0; flagged names have a median net cash of 56% of mcap. 572 fires come only through this route: 177 have EV < 0, 165 have net cash >= 100% of mcap, 140 have net cash < 50%, and in 380 FCF covers the payout. Those 380 are ordinary net-cash dividend payers (000921.SZ Hisense: net cash 54%, FCF yield 8.7%, payout 4.7%), which is net_cash_returner's thesis. Overlap: net_cash_returner 673 fires, negative_ev_value 816. LOOSE.
- 28 fires carry net debt.

Coverage: dividend_yield / buyback_yield NaN 50-54%; tc_uncov_payout_3y 23%; cash_gt_ev_flag 25%. Venues: JP 440, US 308, CN 257, TW 156, HK 147.

Fire sanity
- Fit: YeaRimDang 036000.KQ (net cash 3.7x mcap, FCF -59%, yield 23%), 001940.KS, MAJESAUT.BO.
- Bad (data): MGP1.SG (Marfrig, top spirit 0.989) has net cash 2.77x mcap and nde -6.1. Marfrig/MBRF is a heavily indebted meat packer, so this is an FX/units error on a `.SG` line.
- Not the thesis: BABA/BABAF (net cash 5% of mcap, payout 1.5%, capex-driven negative FCF), 601138.SS, Recruit (two lines).

Severity: LOOSE (the "negative EV" leg is cash > EV; uncovered is historical), data BUG (Marfrig).

Fix: negative-EV leg = `EV < 0 | net_cash_pct >= 1.0`; uncovered also requires `fcf_yield < tot_yield` now.

## arch_biotech_deep_value (119 fires, median mcap $113m)

Intent: "A drug developer trading at/below its NET CASH: the market pays you to own the cash" with "enough runway not to face imminent dilution".

Code (8778-8828)
- Clinical classifier, plus a cash leg: net cash in [0.5, 3]x mcap, or `cash_gt_ev_flag`, or NCAV in [0.8, 3].
- The cash leg admits names at 50% of mcap in net cash: 90 of 119 fires have net cash < 1.0x mcap (positive EV), so they are not below cash. 32 fires come only through `cash_gt_ev_flag` and that flag contradicts the net cash figure. ZNTL: cash_pct 0.11, EV $115m on a $332m cap. FDMT: EV $423m on $728m. FLGT: EV $301m on $563m; Fulgent is a revenue-generating diagnostics lab, classed "clinical".
- Runway >= 2y (or >= 1y with shares up <= 15%) removes 56. 10 clinical names with net cash 1-3x fail on runway < 1y, which is the intended behaviour.
- `mcap >= 2e6` (8818) is redundant with `mcap >= 10e6` (8823). COSMETIC.

Coverage: net_cash_pct NaN for 33% of clinical names; clinical universe 2,266 (US 1,305, CA 221, CN 85). 82 of 119 fires are US.

Fire sanity: Hwail 061250.KQ (net cash 1.44x, cash > EV), Ilsung 003120.KS (1.73x), AMRN (1.06x), Galapagos (2.36x), SYBX (0.98x) fit. 1X8.F (Creso Pharma) reads $19.3B mcap and $6.3B FCF; Creso is a nano-cap, so this is an FX/units error. ZNTL, FDMT, FATE, AVIR are biotechs with cash cover, not below cash.

Severity: LOOSE (0.5x threshold; contradictory flag route), data BUG (Creso).

Fix: require `net_cash_pct >= 0.9` (or EV <= 0.1 x mcap); use `cash_gt_ev_flag` only when `net_cash_pct >= 0.8`.

## arch_bab_low_beta (764 fires, median mcap $1.36B; old rule surfaced as watch, 125)

Intent: Frazzini-Pedersen long leg: "high-quality, optically-boring businesses whose cash flows can be safely levered", beta "ranked WITHIN that market".

Code (2622-2628 quality; 2697-2720 reframe)
- `_bab_low`: panel 3y and 1y beta ranks both <= 0.35 within the listing market, raw > 0. Removes 4,012 of 4,776.
- `bab_quality`: FCF margin > 0 (zero-filled: 71 low-beta liquid payers fail on NaN), EBITDA margin >= 10%, op > 0, and ROCE >= 10% or cash conversion >= 0.6. Removes 1,389.
- `_bab_liquid` removes 486. `_bab_payout` removes 21 (6 fires pass with both yields missing).
- The rank population is the whole panel, illiquid lines included. 55.8% of US-ranked lines trade under $500k a week, and 15% of US panel betas are <= 0, so the US 0.35 rank cut sits at a raw beta of 0.19. Of 326 liquid US quality payers with Yahoo beta 0.2-0.7, 24 fire. In CN, 103 of 296 fire, and the CN low third has a median raw beta of 0.77. Result: CN 249 fires, US 43. This is a reach artifact, not a thesis result. TIGHT (US) / LOOSE (CN).
- ROCE input errors: 5515.TW (ROCE -0.91) and 4441.T (-0.73) pass through cash conversion.

Coverage: ts beta NaN 26%; fcf_margin 33%; roce 40%.

Fire sanity: Gree 000651.SZ (beta 0.10, ROCE 49%, yield 8%), 2222.SR, XOM, JNJ, ABBV, KPN.AS, PetroChina fit. 300641.SZ (3y beta 0.59) and 600801.SS (0.94) are "low" only relative to CN.

Severity: TIGHT/LOOSE (rank population). Otherwise sound.

Fix: rank betas within market among `_bab_liquid` names only (or require raw beta <= 0.8 alongside the rank).

## arch_wolf_emerging (0 fires)

Intent: Wolf's "cautious cannabis bets": emerging-sector profitability, positive CFO, clean SBC, growing, reasonable multiple.

Code (3576-3599). The gate is `_emerging & CFO > 0 & growth >= 10% & no reverse split & SBC < 15% & (P/E < 20 | EV/EBITDA < 12)`.
- `_emerging` (3586) matches 37 names: industries never contain "cannabis" (they are "Pharmaceuticals"), so only the name clause works, and it needs "cannabis/marijuana" in the name. Tilray, Canopy Growth, Cronos, Curaleaf, Green Thumb, Village Farms, Organigram, Verano, High Tide, Planet 13 and TerrAscend are all missed.
- 29 of the 37 are classed `_is_clinical_biotech` (drug-manufacturer industry, not "commercial"). The clinical scrub (9397-9409) zeroes every fundamental archetype for them, so the 3 names that pass the gate (CBWTF, XLY.TO Auxly, and one more) are all scrubbed.
- The sanity report already prints "ZERO arch_wolf_emerging fires on NOBODY". BUG (dead).

Coverage: n/a (37-name population).

Severity: BUG.

Fix: define cannabis by a curated name list or keyword set (cannabis|marijuana|hemp|tilray|canopy|cronos|curaleaf|...) and exempt `_emerging` from `_is_clinical_biotech` (or add it to `_biotech_ok`).

## arch_oak_nav_discount (191 fires, median mcap $470m)

Intent: "narrow to REAL NAV vehicles — closed-end funds, investment trusts, holdcos, asset managers — where book ~ NAV. An operating bank or insurer at 0.7x book is just a cheap financial".

Code (3814-3854)
- `_nav_vehicle` regex `investment trust` also matches "Equity Real Estate Investment Trusts (REITs)". 94 of 191 fires are equity REITs (median pb 0.60). Book is not NAV for a REIT (depreciated cost), and REITs are not in the intended vehicle list. BUG.
- "Capital Markets" accounts for 75 fires, and the regex lets debt and data lines through:
  - SFB (Stifel 5.2% senior notes) and PRS (Prudential junior subordinated notes) carry the common's book (SF pb 2.27, PRU 1.30).
  - The Brookfield Asset Management OTC lines BXDIF / BKFPF / BAMGF read pb 0.10-0.15 vs BAM 10.0. These are the largest fires.
- `_nav_addressed`: dividend >= 5% (137 fires), share count shrinking (52) or buyback >= 3% (32). BAMGF and BKFPF pass the dividend route with fq_shares_yoy +104%.
- The comment says net debt is "listed twice" in the recipe, but debt is only a weight (38 fires have D/E > 1).

Coverage: pb NaN 29%; p_tb 49%; vehicle universe 3,929 (Capital Markets 1,620, Diversified Financials 1,227, REITs 774).

Fire sanity: ZC.V (Zimtu, pb 0.18) and NOAH (pb 0.34, yield 7%) fit. YEIS.MC and SRVGY.IS are REITs. FCT.NZ (F&C Investment Trust) has p_tb 0.98, so it passes only on a pb 0.62 that is wrong for a trust at a ~10% discount. CS0.F (CSC Financial, a broker) leaks via the `.F` line name. SFB, PRS and the three BAM OTC lines are bad.

Severity: BUG (REIT capture; notes and wrong-pb lines).

Fix: change the regex to `closed-end|investment trust(?!s \(reits\))|\bfund\b|asset manag|holding compan|investment compan` and exclude `reit`; scrub exchange-traded debt and OTC lines whose pb deviates more than 3x from the primary line.

## arch_understated_earnings (1,957 fires, median mcap $374m)

Intent: "CFO persistently far ABOVE net income (deferred-revenue float, conservative provisioning, heavy non-cash charges) — the P&L UNDERSTATES cash economics", with persistence "proven from quarterly statements".

Code (4158-4192)
- CFO/NI in [1.5, 4] removes 1,993; P/E <= 15 removes 2,788.
- Corroboration is any one of: cash conversion >= 1.1, FCF yield >= 10%, year-ago CFO/NI >= 1.2, FCF/NI >= 1.2, Sloan accruals <= -5%. Removes 179.
- Persistence is not required: 1,305 fires have year-ago >= 1.2, but 174 are below 1.0 a year ago, and 410 have no year-ago measure.
- CFO above NI is mostly D&A. The file says so itself at line 770 ("CFO above NI is the norm for any D&A-heavy business"). In 787 of 1,595 fires with D&A measured, capex >= 0.8x D&A, so the surplus is reinvested as maintenance. 152 fires have negative FCF and 267 have FCF/NI < 0.5. Top spirit AntarChile (CFO 2.39T, capex 2.53T, FCF -0.43T CLP) is a capex-heavy holdco. PetroChina, Shell, China Mobile, Verizon and HMM fire for the same D&A reason.
- `sbc` removes 1 and `not_melting` 0 (no-ops).
- Overlap: tax_verified_earnings 795, xr_cash_leads_book 113.

Coverage: cfo_ttm NaN 20%; fq_cfo_p 40%; p_e 50%. Venues: US 469, JP 330, HK 139, KR 138.

Fire sanity: GBBYF/1086.HK (FCF/NI 2.1, P/E 3.7), 3399.HK (FCF yield 63%), Nordic Group MR7.SI, ABEO.PA fit. AntarChile, PetroChina, Shell, Verizon do not (D&A).

Severity: LOOSE.

Fix: make FCF/NI >= 1.2 (capex-aware) a required leg, not one of five, and require `_cfo_ni_ya >= 1.2` where measured.

## arch_tax_verified_earnings (2,365 fires, median mcap $229m)

Intent: "You do not pay real cash taxes on fake earnings: a FULL effective tax rate (18-40%) on positive pretax income is the tax authority auditing the P&L".

Code (4385-4404)
- ETR in [0.18, 0.40] removes 2,020. ETR comes from EDGAR for 156 fires and from FMP's book rate for 2,209.
- The cash-tax cross-check `~(fq_cash_tax_rate < 0.10)` is measured for 50 of 2,365 fires (column 96.5% NaN) and removes 10: a near no-op. The thesis says "cash taxes", but the gate verifies a book ETR.
- P/E <= 12 removes 6,455, so the archetype is effectively "P/E <= 12 with a normal book tax rate".
- 115 fires have an operating loss (2442.TW Jean Co, op margin -9.4%, top spirit 0.975: NI and tax from non-operating items). 147 fires have P/E < 4.
- Overlap with understated_earnings: 795.

Coverage: effective_tax_rate (EDGAR) NaN 92.8%; fmp_effective_tax_rate 17.9%; fq_cash_tax_rate 96.5%.

Fire sanity: Nexen Tire, Sungwoo Hitech, Godo Steel, Samsung (two lines), Toyota (two lines with different ETRs, 0.39 vs 0.21) fit "cheap with tax". Jean Co (operating loss) does not.

Severity: LOOSE (cash-tax verification absent for 98% of fires; no operating-profit floor).

Fix: add `op_margin > 0`; where `fq_cash_tax_rate` is NaN, require the ETR from the cash-flow statement (taxes paid / pretax) or demote to watch.

## arch_xr_triple_floor (90 fires, median mcap $105m)

Intent: "three INDEPENDENT downside supports — a net-cash balance sheet, real earnings ..., and a PAID dividend — while revenue still grows".

Code (4542-4558): net cash >= 40% (removes 313), NI > 0, dividend >= 3% and not cut (removes 186), revenue >= 8% (removes 256), pb < 1.5, no dilution, `_fx_coherent`, data-quality flag. Each leg measures its stated floor. `evt_div_cut_2y` is NaN-permissive (19 fires unmeasured). `dq` and `not_melting` remove 0.

Coverage: dividend_yield NaN 50%; rev_yoy 33%. Venues: JP 32, KR 23, HK 8, US 8.

Fire sanity: Yooshin 054930.KQ (net cash 87% of mcap, yield 5.7%, rev +19%, P/E 1.9), Osangjaiel, 361 Degrees, Capinfo, Cuckoo fit. Minor issues: TOUR (net cash 2.6x mcap: should be clamped like `net_cash_pct_sane`), 12 fires paying a dividend above NI, Macromill Embrain (P/E 66), JD and JDCMF (two lines).

Severity: OK (minor LOOSE).

Fix: use `net_cash_pct_sane` (<= 1.0) and require dividend <= NI.

## arch_xr_clean_net_net (203 fires, median mcap $53m)

Intent: "NCAV (now NET of preferred and minority interests) covering the WHOLE price, positive earnings power ... and management PAYING owners".

Code (4692-4706): NCAV >= 1.0x mcap removes 6,995 of 7,198. Earnings (ni_avg or TTM) removes 21. Pay (dividend >= 2% not cut, or a corroborated buyback) removes 310. The legs match the intent.
- `ncav_pct_mcap` (zero-filled) is NaN for 47.5% of the universe, and US operating names are the largest NaN block (7,850 names). US gets 9 fires vs KR 68 and JP 63. TIGHT.
- Data: HCLTECH.NS reads NCAV 9.5x a $34B mcap (units error). 8 fires have NCAV > 3 (054800.KQ, TNHDF, BAL1R.RG, PEXIP.OL, 001940.KS, 3991.HK, 1292.HK, HCLTECH.NS).
- The "net of preferred/minority" claim could not be verified (minority_interest present for 4 fires).
- Homebuilders (TW.L, BWY.L, KBH) qualify on land inventory at cost, which is not a Graham liquidation floor (`nnwc_pct_mcap` 87% NaN, so it cannot be checked).

Fire sanity: Saeron 075180.KS (NCAV 2.6x, net cash 2.1x, 4.7% yield), Silla, Iljin Diamond, Kanefusa fit. HCLTECH, KBH and Kato Works (net debt 2x mcap) do not.

Severity: TIGHT (US coverage), data BUG (NCAV units).

Fix: cap NCAV at 3x unless net cash corroborates; fill US NCAV from EDGAR current assets minus total liabilities; for homebuilders use NNWC (inventory at 50%).

## arch_xr_leverage_detonation (86 fires, median mcap $190m)

Intent: "the breakeven CROSSING with high drop-through — losses just flipped (or are one step from flipping) while incremental margins run >= 35% on 20%+ growth".

Code (4978-4996)
- Crossing = EBITDA first positive (31 fires), FCF first positive (58) or FCF ETA <= 2 quarters (9). Removes 222.
- Drop-through >= 35% removes 287; growth 20-150% removes 328.
- FCF turning positive is not the operating breakeven: 46 of 86 fires have op margin > 10% and 50 have EBITDA margin > 15% (43 cross via FCF with EBITDA margin > 10%). Gold and coal miners on a price windfall fire as "operating leverage": Austral Gold (two lines, op 40%), Galiano, Torex, Orvana (two lines), Shandong Gold (incremental EBITDA margin -0.02, passes via fqx 0.92), Whitehaven (two lines).
- 12 fires have op margin < 0 (the intended population).

Coverage: incremental_ebitda_margin NaN 65%; fcf_eta 78%; first-positive flags 25%.

Fire sanity: SRICHA.BK, 2712.TW (op -11.5% to EBITDA +13%), MQ (op 1.8%), Sejoong fit. Transcend 2451.TW (op 75%) and the miners do not.

Severity: LOOSE.

Fix: require `op_margin <= 0.08` (or EBITDA-first-positive / FCF ETA, not FCF-first-positive alone); exclude Metals & Mining / Oil & Gas where revenue growth tracks the commodity price.

## arch_xr_nol_shield (36 fires, median mcap $2.16B)

Intent: "an accumulated DEFICIT (negative retained earnings — a bank of tax losses) in a business that has TURNED profitable ... little or no CASH tax", "a LOSS deficit, not a buyback-driven negative retained earnings".

Code (5253-5285)
- Low tax = EDGAR ETR in [0, 0.15] OR `fq_cash_tax_rate` in [0, 0.15]. Removes 193; this is the binding leg.
- The OR lets a full-rate taxpayer in on a single-period cash-tax dip: Enbridge (ETR 20.5%, cash rate 12.3%) fires on four OTC lines EBBGF / EBGEF / EBBNF / ENBFF, which are preferreds; ENB.TO itself does not fire. Enbridge's deficit comes from dividends in excess of earnings, not losses, and `_re_is_loss30` passes it on pb < 2.
- Low ETR also captures structural zero-tax entities with no NOL: SHIP (Marshall Islands shipping, ETR 0), ADAM (a mortgage REIT mislabelled Software, ETR 0.4%). HPE (deficit from separation and buybacks, ETR 11.7%) is not a turnaround NOL.
- `_re_is_loss30` = `~(roe > 0.20) | pb in (0, 2)` removes 9. NaN roe passes, so 6 negative-equity fires pass (Bombardier: a genuine deficit, acceptable).

Coverage: US-only by construction. effective_tax_rate is 92.8% NaN and present for US 3,176 vs CA 71; retained_earnings NaN 44%. Fires: US 34, CA 2.

Fire sanity: SD (SandRidge, a real NOL), BOSC, IDN, IVFH and Bombardier (three lines) fit. Enbridge ×4, SHIP, ADAM and HPE do not.

Severity: LOOSE (tax OR-leg; no tax-domicile / REIT / preferred guard), TIGHT (US-only).

Fix: require the EDGAR ETR <= 15% when it is measured, using cash tax only when the ETR is NaN; require a deferred-tax-asset or NOL line (`nol_usd > 0` / `deferred_tax_valuation_allowance > 0`); exclude REIT and shipping tax regimes and preferred lines.

## arch_xr_segment_justifies_whole (73 fires, median mcap $1.29B)

Intent: "The single BEST segment, valued alone at a conservative ~12x its own operating EBIT, already covers the ENTIRE enterprise value — so every OTHER segment (plus any net cash) comes free."

Code (5470-5495)
- `seg_best x 12 >= EV` removes 264 of 337; `seg_total > seg_best` removes 28. The other legs are no-ops.
- Segment EBIT is before unallocated corporate costs, so the sum overstates group EBIT: across fires, segment total / consolidated EBIT has a median of 1.86, 39 of 73 fires exceed 1.5x, and 12 have consolidated EBIT <= 0.
  - FTEK: best segment $8.6m, but the group EBIT is -$4.0m.
  - SKIL: best segment $279m, group EBIT -$73m.
  - NATR: segment total $80m vs group $29m.
- In those cases "the other segments come free" is false: corporate overhead is a real negative segment. 19 fires are already at EV/EBIT <= 12 on the consolidated numbers. BUG (overstated numerator).

Coverage: seg_best_ebit_usd 1.2% of the universe (sanity report SPARSE); fires US 72, IN 1.

Fire sanity: LULU (best segment $2.56B x 12 = $30.7B vs EV $11.7B), GIS, DAL, HPQ, AOS: plausible, though the result is mostly "cheap on group EBIT". FTEK, SKIL and NUS (group op margin 3.2%) are bad.

Severity: BUG (unallocated costs ignored), TIGHT (EDGAR only).

Fix: scale the best segment by consolidated EBIT / segment total (allocate corporate costs pro rata) and require consolidated EBIT > 0.

## arch_xr_verified_deleveraging (32 fires, median mcap $550m)

Intent: "net debt down across >= 9 months of consecutive balance sheets, by >= 5% of assets, operations-funded, not equity- or disposal-funded", at 1.5-4x net debt/EBITDA and a cheap EV/EBITDA.

Code (5721-5742; flag at 796-801)
- The flag implements the comment exactly: decline months >= 9, change <= -5% of assets, shares <= +2%, CFO > 0, discontinued share <= 20%. It removes 676 of 708.
- The nde band [1.5, 4] removes 251; 697 of the 1,129 flagged names have already deleveraged below 1.5x (by design). EV/EBITDA <= 8 removes 37.
- `fcf > 0` and `ebitda > 0` remove 0 (implied by the other legs).
- "Net debt down" also counts cash build-up, not only repayment (minor).

Coverage: the quarterly path is NaN for 37%; net_debt_ebitda 54% (then 99); interest cover 46% (NaN passes).

Fire sanity: MGM China (two lines; net debt -16% of assets over 24 months, nde 1.66, EV/EBITDA 5.6), SBM Offshore, Nexi (two lines), Macy's, TeamViewer, H&H, Tai Hing fit.

Severity: OK.

Fix: none needed; deduplicate lines.

## arch_mb_fallen_value_accel (114 fires, median mcap $106m)

Intent: the multibagger study's fallen (>= 60% below the 5-year high) + deep value + accelerating state. The comment at 7537 reads "acceleration date-matched where the quarterly shape exists (audit 3: rev_accel's annual fallback is a different horizon)".

Code (7525-7552)
- `_accel_now` (7538) is built and then not used. `_mb_accel` (7539) = annual `rev_accel >= 0.10` and `fq_rev_growth >= 0`.
- 51 of 114 fires have `fqx_rev_accel_now == 0`: the date-matched quarterly series says growth is decelerating. 11 fires have rev_accel > 1 (base effects: GXAI 464, AVX 86, 8059.TWO 17.9). The accel leg removes 860 of 974. BUG (the audit-3 fix was written and never wired in).
- Deep: pb <= 0.7 (86 fires), P/S <= 0.3 (61), EV/EBIT <= 6 (13). Fine as the study's definition.
- 40 of 114 fires have op margin < 0 (GXAI -116%, GPUS -60%).

Coverage: rev_accel NaN 34% (zero-filled, fails); fq_rev_growth 44%; ts panel 26%.

Fire sanity: China Harmony 3836.HK (0.12 of 5-year high, pb 0.16, rev +27% accelerating), Woongjin, Stellantis 8TI.F, Mosaic, AZEV4.SA fit. GXAI, AVX and CastleNet (base-effect acceleration, quarterly decelerating) do not.

Severity: BUG.

Fix: `_mb_accel = _accel_now & (rev_accel >= 0.10) & (fq_rev_growth >= 0) & ~(rev_accel > 1)`.

## arch_mb_grew_into_valuation_turning (1,477 fires, median mcap $857m, 200 > $10B)

Intent: "GREW INTO THE VALUATION, NOW TURNING: the de-rating-through-growth family where the margin / profit turn has arrived (Archetype B's medians: revenue +13%, margin at the 64th pct of its own history)".

Code (7635-7640; parent 1546-1599)
- `derate_through_growth` removes 4,937 of 6,414. The turn leg (`_margin_trend_up | _mb_turn`) removes 759; 311 fires pass only via `_mb_turn` (first-positive / turned prints). `fq_rev_growth >= 8%` removes 2,368.
- Unlike every sibling `mb_*` archetype it has no `_mb_base`: 308 fires have weekly dollar volume < $250k or NaN, which is outside the study's population. LOOSE.
- `~(_dg_share < 0.5)` is NaN-permissive: 345 fires have no growth share.
- The "64th percentile margin" condition is not implemented.

Coverage: fq_rev_growth 44% NaN; fqx_* 27-35%; bs_ebit_turned 48%.

Fire sanity: NVDA, AMZN, LLY, Tencent (two lines) and NFLX fire. They match "the multiple compressed while the business grew" (price rose, growth share 1.0), but are not the study's small-cap fallen population. ULUSE.IS (rev +117%), 7089.T and B58.SI fit. VST.CN / VSQTF (two lines, op margin 0-10%) are marginal.

Severity: LOOSE.

Fix: add `_mb_base` and `~(_dg_share < 0.5)` with NaN failing; optionally `mcap < 2e9` as in the study's inflecting-operator set.

## arch_xr_peer_margin_gap (993 fires, median mcap $163m)

Intent: "an operating margin far BELOW its sector's median ... We admit it only WITH a turn signal (margin delta up ...) and a cheap multiple".

Code (5761-5800)
- The peer norm is the industry median (>= 20 peers) or else the sector median, computed across all countries. Gap >= 5pp removes 6,244.
- Turn (5786) = op-margin delta >= 1pp, OR gross-margin delta >= 1pp, OR TTM EBIT growth > 0, OR an inflection flag. Removes 836. 320 of 993 fires have a falling op margin: they pass on gross margin (197 fires overall) or on EBIT growth alone (363), which revenue growth can produce. The comment's "margin delta up" is not required. LOOSE.
- The `not_secular` leg reads rev_3y_cagr, which is 95% NaN, so it removes 29 (near no-op).
- The global industry median penalises low-margin countries. Universe operating margin medians: KR 4.2%, HK 3.8% vs US 7.7%, IN 8.3%. Fire rates: JP 8.0%, HK 6.9%, KR 6.8% vs CN 2.9%, US 4.2%.
- Structural low-margin businesses fire as "latent": refiners VLO / MPC / PSX vs the Oil & Gas median 13.4%; Glencore (two lines; a trader at 2.8%); 88 Metals & Mining and 67 telecom fires.

Coverage: op_margin_delta_yoy NaN 48%; fqx_ebit_ttm_g 57%; rev_3y_cagr 95%.

Fire sanity: 1596.HK (op margin up 13.8pp, EV/S 0.09), TSTH.BK, 601003.SS fit. XOM (op margin 6.4%, delta -1pp), 2187.HK (delta -1.1pp, EV/EBITDA 54), INTLCOMBQ.BO (delta -7.6pp) and the refiners do not.

Severity: LOOSE.

Fix: require `op_margin_delta_yoy >= 0.01` (or `fqx_margin_inflect_now`); compute the peer median within industry x region; replace rev_3y_cagr with revenue_3y_cagr (28% NaN).

## arch_exceptional_evsg (898 fires, median mcap $128m)

Intent: "A fast grower priced at an EXCEPTIONALLY low EV/sales relative to that growth (EVSG)".

Code (6271-6297)
- EVSG in [0.002, 0.05] removes 1,180; growth >= 20% removes 1,022.
- EVSG = (EV/S) / (rev_yoy x 100, capped at 100%; derive_missing_columns.py:516). It ignores margin, so a 2%-margin distributor at 0.2x sales is "exceptional". 263 fires have gross margin < 15%, 226 have op margin < 3%, and 245 have EV/S <= 0.5 (T41.SI TeleChoice op 2.6%, top spirit 0.929; PENTA.IS op 3.3%; MRAT.JK 2.5%).
- 383 fires have NaN `fq_rev_growth` and use the snapshot growth.
- 898 fires (2.5% of operating names) is not "exceptional". Overlap: cheap_sales_scaler 618 (69%), tenbagger_path 474. `profit` removes 0 (implied by `oplens`).

Coverage: evsg / psg NaN 62.7%; fq_rev_growth 44%.

Fire sanity: KSOE 009540.KS (EV/S 0.6, rev +28%, op 16.7%), Samji, Jetwell, ASUS, MasTec (op 3.7%, borderline) fit. Monument Mining (two lines; gold price, +189%), TeleChoice, PENTA and NWL.MI (rev +131%, op -0.3%) do not.

Severity: LOOSE (no margin normalisation; a near duplicate of cheap_sales_scaler).

Fix: use EV/gross profit (or EV/EBIT) to growth, or require op margin >= the industry median; tighten to evsg <= 0.025.

## arch_tenbagger_path (1,202 fires <= $1B; 1,664 incl. watch; median mcap $93m)

Intent: "the arithmetic closing": (1+g)^10 x terminal net margin x 18 / (P/S) >= 10. Per the comment (6721-6723): "a name below the old 12% floor is modelled at its own (after-tax) margin plus a modest expansion, so the arithmetic can actually fail".

Code (6698-6764)
- `term_margin = max(op x 0.75, EBITDA x 0.65 x 0.75, 0.06).clip(0.06, 0.22)` (6724-6728). Every name below 8% op margin, loss-makers included, is modelled at a flat 6% net margin. There is no "own margin plus expansion". 550 of 1,202 fires sit at the 6% floor with op margin < 8%, including 138 loss-makers. ALDNE.PA (Don't Nod, op margin -228%, EBITDA -87%) gets implied 100x; 1452.HK (op -6.3%) and SOKM.IS (op -3.7%) likewise. BUG (code contradicts the comment).
- `g10` is the median of up to 5 growth lenses, capped at 50%: 328 fires sit at the cap, implying 57x revenue in 10 years. 447 fires have P/S < 0.5. The closes leg (implied >= 10) removes 808 of 2,010, and 420 fires have implied >= 50.
- `ps`, `mcap < 10e9` and `viable` remove 0-21 (no-ops).

Coverage: p_s / ev_sales NaN 34-36%; rev_qoq_ttm 57%; revenue_3y_cagr 28%. Venues: IN 250, KR 171, US 160, JP 102.

Fire sanity: BLS.NS (op 22%, g 31%, P/S 3.0, implied 15) and EISA.SN fit. FM.MI (Fiera Milano, op 23%) is mechanical: g capped at 50% from one +62% year with no 3y CAGR. ALDNE.PA and 1452.HK are bad. 99 fires have shares up > 20%.

Severity: BUG (6% floor admits loss-makers), LOOSE (g cap 50%).

Fix: `term_margin = clip(max(op x 0.75, 0) + 0.03, 0, 0.22)` (own margin plus 3pp); cap g10 at 0.35 unless revenue_3y_cagr >= 0.30.

## arch_spinoff_value (4 fires, median mcap $13.7B)

Intent: "the classic forced-selling / orphan discount — a viable operating business trading cheap on an OPERATING yield", "the forced-selling ORPHAN read on the panel".

Code (8895-8978)
- Spin universe = EDGAR `spin_flag` (35) plus fmp_events Form-10 filings within 730 days (`ev_spin_filing_date`, 42 rows), giving 44 names. All are US / OTC except one HK shell.
- Value (yield >= 8-10%, mid-cycle for Energy / Materials) removes 7 of 11.
- `_spin_orphan` is NaN-permissive: 3 of 4 fires (SUNB, VSNT, VGNT) have no ts panel because they are new listings, so the orphan condition is assumed, not observed.
- The `dirty_spin_flag` (nde_real > 4) is surfaced, never gated, as the comment says.

Coverage: spin_flag NaN 82%; non-US spins are invisible.

Fire sanity: AMRZ (r13 -31%, 0.59 of its 52-week high, EV/EBITDA 12.9, FCF yield 5.5%), VSNT (EV/EBITDA 3.2, P/E 6.8, FCF 31%) and VGNT (P/E 6.8) fit. SUNB (P/E 21.7, FCF 4.1%) passes only on an EBITDA yield of 10.9%; it was previously an EBITDA > revenue data case and is now clean.

Severity: TIGHT (US-only feed; 4 fires), minor LOOSE (orphan unobserved).

Fix: for listings with fewer than 13 weeks of data, require price below the first-week close (or the when-issued price); add non-US spin sources.

## Summary

| archetype | fires | severity | one-line fix |
|---|---|---|---|
| arch_wolf_emerging | 0 | BUG (dead: 29/37 cannabis names scrubbed as clinical biotech; name regex misses Tilray / Canopy / Curaleaf / ...) | curated cannabis list; exempt from `_is_clinical_biotech` |
| arch_oak_nav_discount | 191 | BUG (94 equity REITs via the "investment trust" substring; SFB / PRS notes; BAM OTC pb 0.1) | exclude `reit`; scrub exchange-traded debt; pb sanity vs the primary line |
| arch_xr_segment_justifies_whole | 73 | BUG (segment EBIT ignores corporate costs: median 1.86x group EBIT; 12 fires with group EBIT <= 0) | scale best segment by group EBIT / segment total; require group EBIT > 0 |
| arch_mb_fallen_value_accel | 114 | BUG (`_accel_now` built but unused; 51/114 decelerating quarterly; base effects) | `_mb_accel &= _accel_now & ~(rev_accel > 1)` |
| arch_tenbagger_path | 1,202 | BUG (flat 6% terminal margin for loss-makers, against the comment; 138 loss-makers; g capped at 50%) | own margin + 3pp; g cap 0.35 unless the 3y CAGR confirms |
| arch_balance_sheet_return | 1,745 | LOOSE (negative-EV leg is cash > EV; 380 FCF-covered net-cash payers; Marfrig data) | neg-EV = EV < 0 or net cash >= 1x; require FCF < payout now |
| arch_biotech_deep_value | 119 | LOOSE (90/119 above net cash; 32 via a contradictory cash_gt_ev flag; Creso $19B) | net cash >= 0.9x mcap; flag only with net cash >= 0.8 |
| arch_dead_option | 2,705 | LOOSE (5-year-high-only drawdown for 1,292; no price leg; LVMH / Novo / ACN) | require the 52-week lens and EV/EBIT <= 10 or FCF >= 8% |
| arch_tangible_value | 1,646 | LOOSE + data (CHS / LBRDP preferreds, BN; p_tb < pb on 343) | extend `_is_noncommon`; recompute p_tb in one currency |
| arch_understated_earnings | 1,957 | LOOSE (D&A-driven CFO > NI; 787 with capex >= 0.8x D&A; 152 FCF < 0) | require FCF / NI >= 1.2 and year-ago persistence |
| arch_tax_verified_earnings | 2,365 | LOOSE (book ETR; cash-tax check measured on 50; 115 op losses) | require op margin > 0 and a cash-tax measure |
| arch_xr_leverage_detonation | 86 | LOOSE (46/86 op margin > 10%; gold / coal windfalls via FCF-first-positive) | op margin <= 8%; exclude commodity producers |
| arch_xr_nol_shield | 36 | LOOSE + TIGHT (cash-tax OR-leg admits Enbridge preferreds ×4; zero-tax regimes; US-only) | ETR <= 15% when measured; require NOL / DTA evidence |
| arch_xr_peer_margin_gap | 993 | LOOSE (320 with falling margins; global industry median; refiners) | require margin delta >= 1pp; industry x region median |
| arch_exceptional_evsg | 898 | LOOSE (no margin normalisation; 69% overlap with cheap_sales_scaler) | EV/gross profit-to-growth or a margin floor |
| arch_mb_grew_into_valuation_turning | 1,477 | LOOSE (no `_mb_base`: 308 illiquid; NaN growth share passes) | add `_mb_base`; NaN share fails |
| arch_gayner_four_lens | 583 | LOOSE / TIGHT (no dilution test: 27 fires > 25%; 7/8-year names excluded; ev_ebit hole) | dilution in integrity; 0.875 at 8 years; derived EV/EBIT |
| arch_bab_low_beta | 764 | TIGHT (US) / LOOSE (CN): beta ranked over a panel that is 56% illiquid in the US | rank within the liquid set or a raw-beta cap |
| arch_xr_clean_net_net | 203 | TIGHT (US NCAV 7,850 NaN) + data (HCLTECH NCAV 9.5x) | EDGAR NCAV fill; cap NCAV at 3x unless net cash corroborates |
| arch_spinoff_value | 4 | TIGHT (US feed; orphan unobserved on 3/4) | price below the first close for new listings |
| arch_qarp | 720 | OK / COSMETIC (dead `_qarp_cheap`; yrs-ROIC leg near no-op) | delete dead code |
| arch_xr_triple_floor | 90 | OK (minor: net cash > 1x on 15, dividend > NI on 12) | use `net_cash_pct_sane`; dividend <= NI |
| arch_xr_verified_deleveraging | 32 | OK | deduplicate lines |
