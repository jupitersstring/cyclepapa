# Archetype review, round 2, batch 8 (22 archetypes)

Method: compute() was run read-only from a scratch copy (`scratchpad/b8/at_b8.py`, run by `b8/run_b8.py`). The copy returns before the output block, every DataFrame write and every open-for-write outside the scratchpad is blocked, and the spirit-spec path is pinned to the repo. It dumps the merged frame (with all load-time FMP fills) and the gate-leg locals to `b8/b8.parquet`. All 22 dumped `arch_*` columns match the published archetype_tags.csv exactly (22/22 identical row sets). Each gate was then rebuilt leg by leg in `b8/a1.py` … `a22.py` (outputs in `b8/a*.out`), with the post-hoc scrubs applied (sub-$2M shells, EBITDA>revenue, corrupt price, non-common, price-ghost, clinical biotech, segment cash-burner, rev-spike). 21 of 22 rebuilds match the published column exactly. Oak deep value matches at 582/582, with 318 extra rows from the interest-cover soft leg I did not rebuild. "Removes X of Y" means: of the Y names that pass every other leg (before scrubs), X fail this one. Universe N = 46,526; operating 36,173.

Shared facts used below (on top of the review_batch1 facts):
- `s()` zero-fills: `pb` (99), `nde` (99), `ev_ebitda_v` (99), `insider` (0), `fcf_yield` (0), `rev_yoy` (0), `ebitda_yoy_v` (0), the annual `*_first_positive` flags (0). So `x.isna()` on any of these is dead code.
- Analyst counts: `n_analysts` NaN for 74% of the universe, `n_analysts_pew` 92%, `sent_n_analysts` 74%. A NaN-permissive "few analysts" leg passes the OTC/F lines of mega-caps.
- `rev_3y_cagr` is a different, sparse column (95% NaN). The populated column is `revenue_3y_cagr` (72% coverage). Two gates in this batch read the sparse one.
- `cash_gt_ev_flag` = gross cash > EV and net cash > 0. It is not the same thing as "net cash covers the price".
- `insider_ownership_pct` (Yahoo "insiders") includes states and corporate parents: Aramco 81%, PetroChina 95%, Equinor 72%, Chugai (Roche) 60%.

---

## arch_capital_discipline (2,492 fires, median mcap $454m, 213 > $10B)

Intent (L1660-1695): "require a real capital-allocation ACTION (buyback / share shrink)… cash flowed OUT to capital providers… in >= 80% of >= 5 fiscal years"; "NOT YET RE-RATED… still priced for the old cycle"; a returns floor.

Code, leg by leg (L1671-1707; removes X of Y):
- `is_operating`: 342 of 2,850.
- `_own_aligned` (L1673-1691): 1,608 of 4,116. It has three action routes: 3y share count ≤ -1% (1,154 fires); buyback ≥2% with no current dilution (416); or financing outflow in ≥80% of years plus any dividend/buyback/shrink (1,981). 1,210 fires (49%) pass ONLY through the financing-outflow route. That route is satisfied by any mature dividend payer: Saudi Aramco (8/8 years, 5.2% dividend, 0 buyback), PetroChina, BHP, China Mobile, CNOOC. 688 fires have a 3-year share count that is RISING and 623 a rising current count. "Discipline" here is "pays a dividend". LOOSE.
- `_cd_returns_floor` (roce ≥10% | roic_after_sbc ≥10% | fcf_yield ≥5%): 508 of 3,016. OK.
- `_roce_now_ok`: removes 0. `_op_viable(0)`: removes 11 (near no-ops given the floor).
- Leverage (`_lev_ok(1.5)` | net cash ≥20%): 856 of 3,364. OK.
- "Not yet re-rated" (L1703): pb < 1.5 | 0 < EV/EBIT ≤ 12 | `pb.isna()`. The `pb.isna()` arm is dead because `pb = s('pb', 99)`. It would rescue 19 otherwise-passing names. Removes 1,936 of 4,444. 800 fires have P/B ≥ 1.5 and pass only on EV/EBIT ≤ 12; 196 have P/B > 3. Aramco (P/B 4.0), BHP (4.3), CVX (2.2) and Wacom (3.6) are "not re-rated" only because a commodity or quality EV/EBIT sits under an absolute 12. LOOSE.
- `ebitda_margin_sane ≥ 5%`: 278 of 2,786. NaN margin fails. OK.

Coverage: shares_growth_3y NaN 13.5% of operating names, fmp_st_financing_* 11.8%, pb 27.6%, ev_ebit 59.5%. Global: JP 672, US 495, CN 176, HK 161.

Fires: top by spirit are MegaStudyEdu (215200.KQ: P/B 0.85, EV/EBIT 3.1, shares -12%/3y, 8% dividend), Colefax (shares -26%/3y) and Yelp (shares -11%/3y, EV/EBIT 8.4). These fit. The largest five are Aramco, CVX, PetroChina (two lines), Shell and BHP. None of them is a re-rating-pending capital allocator. Secuve (131090.KQ) passes with shares_yoy +389%, a split/data artifact the 3y shrink leg does not see; 14 fires have shares_yoy > 50%.

Severity: LOOSE (the outflow route equals "pays a dividend"; the absolute EV/EBIT ≤ 12 arm reads majors as un-re-rated). COSMETIC (dead `pb.isna()`).
Fix: drop the bare financing-outflow route, or require `shares_growth_3y ≤ 0` on it; make "not re-rated" P/B < 1.5 AND (EV/EBIT ≤ 12 or below the industry median); delete `pb.isna()` or read `_ncol('pb')`.

## arch_cheap_per_roiic (3,020 fires, median mcap $1.28B, 622 > $10B)

Intent (L1953): "you're paying < 1.5x EV/EBITDA per percent of lindy ROIIC". It is meant to be a PEG on reinvestment.

Code (L1957-1963):
- `cheap_per_roiic_lindy = ev_ebitda / (roiic × 100)` (L420-423; verified, 0 of 3,020 fires deviate by more than 5%). A ≤ 1.5 cap means EV/EBITDA ≤ 1.5 × ROIIC%, so EV/EBITDA up to 30× at 20% ROIIC and 45× at 30%. Of 6,796 operating names with ROIIC > 10% and EV/EBITDA > 0, 6,029 (89%) pass. The "cheap" leg removes only 875 of 3,964. It does not measure cheapness. Fires: NVDA 26×, LLY 25×, COST 29×, ASML 43×, LRCX 43×, AMAT 35×, KLA 39×. 1,215 fires sit above the operating median EV/EBITDA (10.8×). BUG (threshold scale).
- No `_ev_sane`: 39 fires have EV/mcap outside 0.2-5. The top spirit name is MELI.BA (Argentine CEDEAR line), EV/EBITDA 1.84 vs ~30× on MELI itself, a currency/line artifact. 65 fires have EV/EBITDA < 2.
- `roiic_lindy > 0.10`, with no upper band (the sibling durable_reinvestment caps it at 1.0): 37 fires have ROIIC > 100% (max 1.84).
- `roic_lindy ≥ 5%`: 1,313 of 4,402. `fqx_ebit_ttm_g ≥ -10%`: 1,200 of 4,289. `_roce_now_ok` and `_not_melting` remove 1 and 3. 56 fires have roce < 0 (2745.TWO at -0.60 is the batch-1 bogus ROCE).

Coverage: all 3,020 fires are FMP-filled (`fmp_filled_cheap_per_roiic_lindy == 1`); `cheap_per_roiic_lindy` is NaN for 70% of operating names, `ev_ebitda` for 44.5%.

Severity: BUG (the cheap leg is a near no-op), LOOSE (no EV sanity band, no ROIIC cap).
Fix: cap EV/EBITDA at ≤ 0.5 × ROIIC% (or rank cpr within industry and keep the bottom quintile); add `_ev_sane`; require `roiic_lindy ≤ 1.0`.

## arch_owner_operator (3,852 fires, median mcap $599m, 387 > $10B)

Intent (L2447-2454, 2467-2470): "management with skin in the game AND multi-year discipline… Yahoo 'insiders' includes corporate parents: >= 60% is usually a listed SUBSIDIARY". Core: "insider 20-60%, or revealed alignment".

Code (L2455-2480):
- `_oo_common` (operating, `_roce_now_ok`, `_not_melting`, rev_yoy > -15%, insider ≥ 20%): removes 3,677 of 7,582. `rev_yoy` is zero-filled, so NaN passes. `insider` is zero-filled, so NaN fails (21% of operating names; CA 40%, DE 30%, US 27%).
- `_oo_us | _oo_global`: 7,150 of 11,055. The "US" path has no country test and now runs on FMP-filled lindy fields: 1,127 of the 1,547 US-path-only fires are non-US. Naming only. The US path has no current-ROCE floor: 80 fires have roce < 0 (Boutiques 9272.T -0.86, Zee Learn -0.53, Playtika -0.09).
- Tier core `insider ∈ [0.20, 0.58] | _aligned`: removes 1,339 of 5,244. `_aligned` includes `shares_growth_3y < 0` with zero tolerance. Of the 918 fires with insider > 58%, 774 survive ONLY through a sub-1% count decline: PetroChina (95%, -0.06%/3y), Aramco (81%, -0.09%), Moutai (62% state, -0.2%). The subsidiary guard the comment promises does not bite. 1,718 fires have insider ≥ 50% (`controlled_sub_flag`). LOOSE.
- `measured=insider.notna()` is always True (zero-filled). COSMETIC.

Fires: SWC.BK, Shane Global, Firstlogic, Yorkey Optical and Omega Flex-type family firms fit. Aramco, PetroChina, Moutai, Equinor-type state holdings and Walmart, L'Oréal and LVMH (523 fires carry ≥ 10 analysts) are "owner-operated" only in the loosest sense.

Severity: LOOSE.
Fix: `_aligned` share-shrink leg `shares_growth_3y ≤ -0.02`; exclude insider > 0.58 unless an insider buy or buyback ≥ 1% is observed; add `~(roce < 0)` to the US path.

## arch_capital_returner (1,464 fires, median mcap $631m, 209 > $10B)

Intent (L2108-2141): "paying back >= 5% of market cap per year via dividends + buybacks… FCF-COVERED… covered by FCF in EACH of the last 3 fiscal years".

Code (L2129-2151):
- Yield 5-30% via `capital_return_yield` or div + buyback: removes 13,336 of 14,855, the defining leg. 865 fires via cry, 1,255 via total yield, 209 via cry only. 27 fires have cry ≥ 5% while dividend + buyback < 2%: DDS, Voestalpine (5.2% vs 1.7% dividend, 0 buyback), Sichuan Changhong (10% vs 1.6%), Shougang, ZPMC, Telecom Argentina. On Chinese cash-flow statements "dividends, profits or interest paid" is one line, so interest paid leaks in. LOOSE (minor).
- `_covered` (FCF > 0, or FCF unknown and no dilution): 137 of 1,656. 4 fires pass with fcf_yield ~1e-32 (Inpex IPXHY/IPXHF: effectively zero FCF passes `> 0`).
- Tier core `tc_uncov_payout_3y == 0`: removes 2,459 of 3,978. `measured` uses the zero-filled `fcf_yield.notna()`, so it reduces to `tc.notna() | cry.notna()`. I reconstructed 1,464/1,464 only after accounting for this. 116 fires have tc NaN.
- Buyback yield is the EDGAR/partial `buyback_yield` (55% NaN on operating names, 14% coverage in CA). Using the global FY `fmp_st_buyback_yield_y0` as `capital_discipline` already does would add 63 covered names (US 26, UK 8, CA 8). TIGHT (minor).

Fires: Spectra Systems, Molson Coors (12% yield, 5% shrink, FCF 13.7%), Nutrien, VZ, QCOM and CRM (16% buyback) fit. GMD.MX (cry 18%, dividend 0, buyback 0) is a data inconsistency.

Severity: LOOSE (minor) / TIGHT (minor). The core is sound.
Fix: require cry to agree with div + bb within 2× (or prefer div + bb), `fcf_yield > 0.005`, and fill `buyback_yield` with `fmp_st_buyback_yield_y0`.

## arch_cundill_deep_value (296 fires, median mcap $84m, 2 > $10B)

Intent (L3398-3440): Cundill's six MUSTs; (4) "profitable; preferably no deficits over 5y".

Code (L3406-3443):
- c1 0 < P/B < 1: removes 143 of 446. c2 ≤ half the 5y high: 956 of 1,259. c3 P/E ≤ min(10, 1/5.5%) = 10: 366 of 669. c5 dividend > 0: 243 of 546. c6 debt (financials exempt): 54 of 357. These measure the intent.
- c4 (L3432-3434): `_c_nodef = eps_yoy_positive_share → fmp_st_ni_up_share_5 → tc_opinc_pos/tc_years`, gated at ≥ 0.6. The first two inputs are GROWTH shares, not profit-positive shares:
  - `eps_yoy_positive_share` is the share of the last 8 quarters with EPS above the year-ago quarter (yartseva_db.py L676-687).
  - `fmp_st_ni_up_share_5` is the share of the last 5 years with NI above the prior year (fmp_statements.py L277-278).
  - c4 therefore tests "earnings rose in ≥ 60% of periods", not "no deficits". It removes 184 profitable cheap names, 95 of which have an operating profit in every year on file. Comcast (8/8, P/B 1.0, P/E 8.1, 5.4% dividend) fails because its EPS-growth share is 0. Deutsche Wohnen (8/8) fails at 0.4. It admits 92 fires with an operating-loss year on file, 15 of them with fewer than 60% profitable years: KEP (op-profit in 3 of 8 years), Telecom Argentina (2/6), Thai Group (1/8), Taiwan Calsonic (1/7). BUG.
- Not `is_operating`, by design: 32 financials and 18 REITs fire (Keppel REIT, nde 9.1).

Coverage: P/E NaN 51% (loss-makers plus a gap); `eps_yoy_positive_share` 68% NaN, so the growth-share mis-read reaches 248 fires via the FMP fallback. KR 100, HK 37, US 28.

Fires: Austem, Dong-A-type KOSDAQ names, Tianneng Power and BWG.BK fit (P/B 0.2-0.4, P/E 2-5). Powerlong Commercial (roce -0.94; c4 passes via EBITDA > 0) is doubtful. Mitsubishi Materials MUJ.F at 1.5% of its 5y high is a Frankfurt-line price artifact.

Severity: BUG (c4 measures earnings growth, not absence of deficits).
Fix: `_c_nodef = (tc_opinc_pos / tc_years)` first (or an NI-positive share), with the growth shares used only for the "preferably increasing" score.

## arch_fastest_segment (569 fires, median mcap $5.4B, 227 > $10B)

Intent (L2282-2297): "a 'hidden growth engine' the consolidated number masks… GENUINELY multi-lens… the segment archetypes… reach every filer FMP covers" (L425-431).

Code (L2327-2336; removes X of Y):
- `segment_count ≥ 2`: 374 of 985. `_seg_any_growth ≥ 10%`: 218 of 829. Materiality: 104 of 715. `seg_inflect_any`: 69 of 680. Revenue floor / not-melting / decline guards: 13 / 10 / 31 + 87.
- Fires 556 of 569 are US. `segment_count` is NaN for 88.5% of operating names. The FMP segment fill reached 80 fires, all US-listed. TIGHT: the archetype is blind outside EDGAR.
- "Hidden": nothing caps the engine's share or requires the consolidated growth to lag. 120 fires have the fastest segment at ≥ 70% of revenue (46 at ≥ 90%: META 98.9%, ELV 95.9%, MNST 92.7%, CAH 94.9%). 76 fires grow consolidated revenue as fast as the "hidden" segment. The sibling XR37 has both guards (share ≤ 60%, rev ≤ seg - 10pp). LOOSE.
- 40 fires pass `seg_inflect_any` on dispersion / whole-company breadth alone (the comment's "corroboration" legs).

Fires: Bunge (+183% segment at 26% share: the Viterra merger, M&A not organic), Lumentum, BWXT, Penguin, Crane NXT, Acuity. The largest are NVDA (segment 89.6% of revenue), MSFT, AMZN, AVGO and META: none is hidden.

Severity: TIGHT (US-only coverage), LOOSE (no "hidden" test, no M&A guard).
Fix: add `fastest_segment_share ≤ 0.6` and `rev_yoy ≤ seg_growth - 0.10` (as XR37 does); exclude segments whose revenue jump coincides with acquisitions (`fq_acq_pct_assets`); extend the FMP segment fill to non-US filers.

## arch_wolf_value_catalyst (455 fires, median mcap $53m)

Intent (L3552-3556): "a growing, cash-generative microcap with a fortress balance sheet at a cheap FCF yield".

Code (L3557-3569):
- mcap < $200m: 380 of 850. rev_yoy ≥ 10% (present): 1,276 of 1,746. Cheap (FCF ≥ 8% | EV/EBITDA < 6): 140 of 610. CFO > 0: 46. EV sane: 59. `_not_melting`: 0.
- "Fortress" (net cash ≥ 20% | cash > EV | NCAV ≥ 50% | FCF ≥ 10% & nde ≤ 1.5): 362 of 832. 106 fires carry net debt, 19 above 50% of mcap. They pass through NCAV (current assets less all liabilities) or the FCF route. UNISON METALS (net debt 2.3× mcap, NCAV 1.38) and Jean Co 2442.TW (net debt 1.09× mcap, NCAV 1.05, op -9%) are not fortresses. LOOSE.
- No base-effect cap on growth (siblings use ≤ 1.0): 20 fires have rev_yoy > 100% (Jean +881%, Umiya +749%, SemiLEDs +566%). LOOSE.
- The cheap leg accepts EV/EBITDA < 6 with negative FCF: 26 fires have FCF < 0 (VEDAVAAG -12%). 48 fires have op margin < 0.
- There is no catalyst leg. It is only surfaced: 151 of 455 have `wolf_value_catalyst_dated_flag`.

Fires: Dong-A Eltek, Hutter & Schrantz (net cash 59%, FCF 49%), IDIS (net cash 151%), Densan and Chuan Holdings fit.

Severity: LOOSE.
Fix: require `net_cash_pct ≥ 0` on every fortress route; `rev_yoy ≤ 1.0` unless `revenue_3y_cagr ≥ 0.15`; require `fcf_yield > 0` on the EV/EBITDA arm.

## arch_oak_deep_value (582 fires, median mcap $51m, 8 > $10B)

Intent (L3741-3743, 3796-3798): "Every Oak winner pairs cheapness with a CASH-RICH, cash-generative balance sheet; every trap… was a cash-burner needing external capital… real cash".

Code (L3799-3812):
- Crash (5y high ≤ 0.5 and not back within 25% of the 52w high): 1,837 of 2,786. Discount (P/B < 0.5 | P/S < 0.3 | NCAV ≥ 0.5): 875 of 1,824. EBITDA > 0 and cash+: 857 of 1,806. Dilution / reverse split: 101. `_not_melting`: 0.
- Interest-cover soft leg (≥ 1.5 where present, not rebuilt): about 318 of 900.
- "Real cash" is `cash_pct_mcap_v ≥ 0.20`, GROSS cash (L3807). It removes 292 of 1,241. 282 of 582 fires (48%) carry net debt and 173 carry net debt above their market cap. Volkswagen (gross cash 1.66× mcap, net debt 4.5× mcap), Nissan (net debt 6.1×), Casino Guichard (net debt 36× mcap, op margin -0.4%, FCF negative; top-5 spirit 0.90), Luxking (net debt 3.2×), Edvantage (FCF negative). The sibling oak_resource_leverage says explicitly "NET-cash survivability (not gross cash)". BUG.
- 161 fires pass the discount leg via P/S < 0.3 only. For low-margin distributors and autos that is not "price / assets very low". This is the author's own leg, so acceptable.

Fires: China ITS (net cash 2.1×), Chinese People Holdings, Hebei Yichen (net cash ~0) and Wilhelmina (net cash 3.9×) fit.

Severity: BUG (gross cash stands in for real cash).
Fix: replace `cash_pct_mcap_v ≥ 0.20` with `net_cash_pct ≥ 0.20` (or gross cash ≥ 20% AND net cash ≥ 0). 247 of today's fires already meet net cash ≥ 20%.

## arch_overdepreciated_assets (455 fires, median mcap $353m, 39 > $10B)

Intent (L4096-4107): "implied D&A … runs far above replacement capex while revenue HOLDS… All components are LOCAL currency from the same source rows (currency-neutral by construction)".

Code (L4108-4156):
- D&A/revenue ≥ 5%: 357 of 823. 0 ≤ maintenance capex ≤ 0.6 × D&A: 508 of 974. P/B < 1.2: 1,174 of 1,640. op > 0: 180. rev_yoy ≥ -5%: 181. fq capex/DA ≤ 0.8: 96.
- Currency (L4114, 4126): `da_ttm` is in the REPORTING currency, while `revenue_ttm` and `capex_ttm` are in listing currency, which is USD for OTC ADRs. 110 of 455 fires (24%) show D&A above revenue (median D&A/revenue 0.13; 75th pct 0.71; max 337):
  - HNDAF Honda: D&A 1.30e12 (JPY) vs revenue 1.40e11 (USD), capex 8.3e9.
  - TYIDY Toyota Industries: D&A 3.53e11 vs revenue 2.72e10. DENSO and Bridgestone ADRs.
  - JR East: 4.29e11 vs 2.53e10.
  - China Mobile CTM.F: 1.90e11 vs 1.35e11.

  On those rows capex/D&A reads ~0.01-0.1, so "replacement far below depreciation" is an FX artifact. 127 of the 138 fires with D&A > 35% of revenue are OTC/.F/ADR lines. The quarterly cross-check `fq_capex_to_da` is NaN on 88 of them. Where it is present (BRDCY 0.72, CTM.F 0.80) it shows normal reinvestment. BUG.
- `rev_3y_cagr ≥ -2%` (L4150) reads the sparse column (95.7% NaN on operating names; removes 4). The populated `revenue_3y_cagr` exists. COSMETIC.

Fires: Krungthai Car Rent (fq capex/DA 0.005), China Maple Leaf and Parkit fit on currency-coherent data. EQ4.F, LOO.F, WACLF, HNDAF and MZDAF (top-10 spirit) are FX artifacts.

Severity: BUG (unit mixing).
Fix: convert `da_ttm` with `fq_fx_to_master` (or use `fq_da × 4` against `fq_capex`, which is one currency); drop rows where D&A > revenue; use `revenue_3y_cagr`.

## arch_dividend_verified_value (65 fires, median mcap $93m)

Intent (L4364-4367): "a fat payout covered by BOTH earnings and FCF at a sub-book price… div <= 70% of NI and <= 70% of FCF".

Code (L4373-4383):
- Dividend ≥ 6%: 930 of 998. Div ≤ 70% NI: 71 of 139. Div ≤ 70% FCF: 40 of 108. P/B < 1: 50 of 118. No cut in 2y: 66 of 134. tc_uncov < 2: 9. fx_coherent: 7. Each leg measures the intent. Units are coherent: dividend yield × local mcap vs master-currency NI/FCF behind `_fx_coherent`.
- "Covered over the cycle" allows one uncovered year in three: 22 of 65 fires have tc_uncov = 1. 12 fires have no tc history and 14 have no cut history (`evt_div_cut_2y` NaN on 49% of operating names).

Fires: SEOHAN, Hansol Logistics (raise streak 8), Niraku, China Unicom (7.3%, P/B 0.36), PTTEP and Global Ship Lease fit. Payout/NI on fires is 6-70% (median 45%).

Severity: OK (the tc ≥ 2 tolerance is a mild LOOSE).
Fix: optional `tc_uncov_payout_3y == 0` where measured.

## arch_xr_neg_ev_growth (200 fires, median mcap $87m, 11 > $10B)

Intent (L4524-4526): "Paid to grow: cash covers the whole price (or nearly) while the business GROWS… The market pays you to own the growth".

Code (L4527-4540):
- `cash_gt_ev | net_cash_pct ≥ 0.80`: removes 4,781 of 4,989, the defining leg. 121 of 200 fires pass ONLY through `cash_gt_ev_flag` (gross cash > EV); 64 of those have net cash < 50% of mcap and 32 < 30%. Gross cash above EV with equal debt does not cover the price. Xiaomi (net cash 13.8% of mcap), WuXi AppTec (6.6%), Anta (7.6%), ZTO (8.7%), Kuaishou (30.7%), Geely (29%) and Centene (16.8%; a managed-care insurer under Health Care) are not "paid to grow". The flag comes from the yartseva snapshot; 22 of these fires contradict it on the current master (cash < EV). LOOSE.
- Growth (point 15-100% or ≥ 8-quarter streak): 872 of 1,080. 55 fires pass on the streak only, 11 with rev_yoy < 5% (Synergie +1.8%, Azeus -1.7%).
- `_profit_present` and `_not_melting` remove 0; op > 0 | FCF ≥ 3% removes 10.
- 52 fires have net cash > mcap. D&L Industries (net cash 7.5× mcap with EV 2.2e10 vs mcap 3.6e8) is an FX artifact that passes `_fx_coherent`. HOLO (net cash 10×) is a cash shell.

Fires: IDIS (net cash 151%, +22%), Billing System (4.2×), Monument Mining, SINOPEC Engineering (1.68×) and Hutter & Schrantz fit.

Severity: LOOSE.
Fix: drop the bare `cash_gt_ev` arm or require `net_cash_pct ≥ 0.5` beside it; add `ev_mcap` sanity; the streak arm needs `rev_yoy ≥ 0.05`.

## arch_xr_audited_streak_unrerated (2,091 fires, median mcap $1.0B, 353 > $10B)

Intent (L6522-6529): "8+ CONSECUTIVE quarters of FILED growth… while the market has NOT re-rated… and the multiple is not already rich. The longest-duration told-and-ignored signal". The comment says it is "XR = rare conjunction… counts stay small by design" (L4519-4522).

Code (L6539-6555):
- Streak ≥ 8: removes 7,073 of 9,222. Window ≥ 8: 0. Not melting: 4.
- No-rerate (≥ 2 of 8 lenses) | `_coil1_xr`: 593 of 2,742. The lens count is easy for any growing company: 2+ lenses true for 1,867 fires; 224 pass on coil1 alone and 116 fires have zero lenses. Samsung GDR (r52 +248%), Innodisk (+282%), Albatron (+513%) and Tembo (+933%): 25 fires more than doubled in a year and are still "unrerated". AMZN, META, Tencent, ORCL, UNH, NFLX and BABA fire, as do 436 fires with ≥ 10 analysts. 2,091 fires is not an XR count. LOOSE.
- `_not_rich_au` (L6502-6504): P/E ≤ 25 | EV/EBITDA ≤ 14 | (P/E NaN & EV/EBITDA NaN). `ev_ebitda_v` is `s('ev_ebitda', 99)`, so the last arm is dead. The comment says "missing = permissive", yet 222 otherwise-passing names with neither multiple fail. COSMETIC/TIGHT. P/E ≤ 25 is an absolute "not rich" that admits UNH and NFLX at 24×.
- "Filed / audited": 1,510 fires rely on the FMP dyn streak. That is positional, quarterly filers only, and not audited.

Fires: MYEG (streak 9, r52 -77%, P/E 8.7), Pop Mart (streak 10, r52 -42%, P/E 9.8), Stamen and CHIeru fit the told-and-ignored shape.

Severity: LOOSE (no-rerate is a 2-of-8 vote; no tape cap), COSMETIC (dead NaN arm).
Fix: require ≥ 3 lenses and `ts_r52 ≤ fq_rev_growth`; replace the dead arm with `_ncol('ev_ebitda').isna()`; cap at a liquidity-adjusted analyst count or an industry-relative P/E.

## arch_xr_forced_seller (174 fires, median mcap $145m, 16 > $10B)

Intent (L4956-4960): "price COLLAPSED >=40% in a year in which the BUSINESS GREW on both lines with no dilution — a seller-driven, not business-driven, mark".

Code (L4961-4973):
- r52 ≤ -40%: 4,236 of 4,429. r13 ≥ -5%: 270 of 463. Revenue ≥ 5%: 210. Shares ≤ 2%: 72. Profit grew: 62. Revenue floor: 45.
- "Profit grew" (`ebitda_yoy_v ≥ 0 | fqx_ebit_ttm_g ≥ 0`): `ebitda_yoy_v` is zero-filled, so NaN passes. 8 fires get in that way: UTime (op -42%), GCL (-4.7%), Beijing Infosec (-12%), Chandra Asri (2 lines). 9,301 operating names would pass this leg on NaN alone. 31 fires have TTM EBIT falling (`fqx_ebit_ttm_g < 0`) but pass on annual EBITDA. BUG (minor).
- Nothing separates seller-driven from business-driven: the 13F exodus is spirit-only, observed for 28 fires and negative for 7. The large fires are a 2026 sector de-rating, not forced selling: NFLX, PDD, INTU (-60%), BSX (-55%), Rheinmetall (2 lines), Trip.com. NISTF Nippon Steel (r52 -76% with r13 +34%) looks like the 2025 5:1 split unadjusted in the OTC line. 17 fires have rev_yoy > 100%. LOOSE.

Fires: YG Entertainment (+62% revenue, EBIT +363%, r52 -57%), 3SBio, Alibaba Pictures and Kingdee fit the shape.

Severity: LOOSE; zero-fill BUG (minor).
Fix: `_ncol('ebitda_yoy') ≥ 0`; require `fqx_ebit_ttm_g ≥ 0` where measured; require the drop to exceed the industry's (`vs_ind_r52 ≤ -0.30`); add a split check (`|ts_r52 - price_yoy| < 0.3`).

## arch_xr_latent_inflection_floor (260 fires, median mcap $40m)

Intent (L5145-5159): "improving but has NOT yet crossed… Each requires a hard downside FLOOR (net cash, NCAV, deep book discount, or hidden assets)".

Code (L5152-5178):
- Improving: 1,283 of 1,595. Not yet crossed: 914 of 1,226. Floor: 393 of 705. Financing-fragile: 135. rev ≥ -5%: 192 (zero-filled rev_yoy, so 15 fires pass with NaN revenue growth).
- Floor (L5152-5154) includes P/B < 0.8 and GROSS cash ≥ 50% of mcap. 114 of 260 fires carry net debt:
  - Atlantic Sapphire: net debt 48× mcap, P/B 0.39, op -89%.
  - China Aircraft Leasing (a lessor): 15×.
  - Orpea: 13.5×.
  - China Nuclear Energy Tech: 9.9×.
  - Air China: P/B 3.0 with net debt 2.7× mcap, passing via gross cash.
  - Bezeq: P/B 7.9, net debt 1.05×.

  A book discount on a balance sheet that is mostly debt is not a floor. LOOSE (near BUG).
- "Not yet crossed" uses `op ≤ 0 | fcf < 0`, so profitable capex-heavy names count as pre-turn: 36 fires have op margin > 5% (Vale Indonesia 26.8%, Furukawa Electric 7%). Wise Ally (roce 1.03, op -16%) is the top spirit name.

Fires: SeaChange (net cash 1.6×, op -9.5%), Tokyo Kisen and Woowon fit.

Severity: LOOSE.
Fix: floor = net cash ≥ 20% | NCAV ≥ 0.5 | (P/B < 0.8 & net cash ≥ 0); "not crossed" = `op_margin ≤ 0.02`.

## arch_xr_hidden_segment_compounder (38 fires, median mcap $2.3B, 10 > $10B)

Intent (L5440-5447): "A fast-growing segment whose OPERATING MARGIN is inflecting… GAINING SHARE… still < 60%… masks the emerging one".

Code (L5448-5468): segment inflecting removes 139 of 178, share Δ ≥ 2pp 40, segment yoy ≥ 20% 22, share ≤ 60% 22, cheap 15. The legs match the intent; this is the well-guarded sibling of fastest_segment.
- Coverage: the segment-margin inputs exist for 9.3% of operating names. 37 of 38 fires are US (EDGAR). TIGHT.
- No M&A guard: Xerox (top spirit, segment +113% = the Lexmark acquisition), L3Harris (segment +467%, a re-segmentation), EQT (+162%, the Equitrans merger), Bunge-type deals. LOOSE.
- The cheap leg passes 62% of the universe; 6 fires are cheap only via FCF ≥ 3% or P/B < 2 with EV/S > 3. Phoenix New Media passes with EV/S -1.0.

Severity: TIGHT (EDGAR-only), LOOSE (acquired growth).
Fix: exclude names with `fq_acq_pct_assets > 0.10` or segment yoy > 100% unless organic; extend FMP segment margins.

## arch_xr_discops_mask (79 fires, median mcap $336m, 7 > $10B)

Intent (L5681-5688): "consolidated net income is depressed (or negative) BECAUSE of a losing unit in discontinued operations or held for sale, while CONTINUING operations are solidly profitable".

Code (L5689-5719):
- Mask: removes 5,361 of 5,444. The arms are (a) NI ≤ 0 & continuing > 0 (non-FMP rows), (b) a material discops loss, (c) assets held for sale ≥ 15% of mcap. 37 fires pass only on arm (a), and 31 of those have a discontinued-ops line of 0 or NaN. The NI/continuing gap is an impairment or a period mismatch, not a discontinued drag:
  - Ford: continuing 5.67B, disc 0, NI -7.40B.
  - Molson Coors (two lines): 1.41B vs -1.84B/-2.14B.
  - Conagra, Lumen, Newell, Alpha Metallurgical.
  - Scienjoy, Angi, Oriental Culture (the top three spirit names after PSHG).

  47% of the archetype measures "NI below continuing income for any reason". BUG.
- Arm (c) divides local AHFS by the USD mcap (L5710). This is latent: AHFS is EDGAR-only (98% NaN), so 0 fires are affected today. COSMETIC.
- Non-common leaks: CHS preferreds CHSCM/CHSCN/CHSCL (preferred mcap $0.3B vs CHS continuing income $0.54B, so a "179% yield") and JSM (Navient notes; a lender tagged Materials).

Fires: Hexagon (Octave discontinued -16.3B SEK), Carrefour (disc -0.71B), Hellenic Telecom and Viomi fit.

Severity: BUG.
Fix: arm (a) must require `income_discontinued_ops_ttm < 0` and |disc| ≥ 50% of (continuing - NI); divide AHFS by the local `market_cap`; scrub preferred lines (`non_common_flag` misses CHSC*/JSM).

## arch_mb_fallen_value_turn (401 fires, median mcap $131m, 9 > $10B)

Intent (L7519-7551): the study's "fallen + deep value + profit turn" state (lift 2.7/3.6×).

Code (L7525-7551): base (liquid operating) removes 895 of 1,316; fallen ≤ 0.40 of the 5y high: 641; deep (EV/EBIT ≤ 6 | P/B ≤ 0.7 | P/S ≤ 0.3): 917; turn: 626.
- `_mb_turn` arms among fires: dyn NI 200, dyn op-inc 183, fcf_first_pos 119, fqx_eps_turned 91, ebitda_first_pos 70, ni_first_pos 63, bs_ebit_turned 38. As sole arm: fmp_dyn opinc 46 and dyn NI 33. Both compare one quarter with the prior four, which the code itself rejects as "a seasonality-confounded turn" (L1940-1942). fcf_first_pos sole: 55 (a working-capital swing; 20 of these have op < 0).
- The recency cap applies only where `fqx_m_since_turn_positive` exists (NaN for 210 of 401 fires), so the annual first-positive flags can be stale.
- 121 fires have op margin < 0, 198 NI < 0 and 169 FCF < 0. The top spirit names are Definitive Healthcare (op -105%, NI -$173m) and Vroom (op -64%): not turned. LOOSE.
- Deep is mostly P/B ≤ 0.7 (267) and P/S ≤ 0.3 (251); EV/EBIT ≤ 6 only 48 (`ev_ebit` NaN for 41% of fires).

Fires: Beachbody (op +5.7%, EV/EBIT 4.8, 1.6% of the 5y high), Fiverr (EV/EBIT 3.1) and Castor Maritime fit. The VW, JD, Nissan and Stellantis lines are fallen and cheap with a weak "turn".

Severity: LOOSE.
Fix: drop the fmp_dyn single-quarter arms (or require them beside a TTM turn); require `op_margin ≥ 0` or `fqx_eps_turned`; require a known recency ≤ 12 months.

## arch_mb_smart_money_wreckage (234 fires, median mcap $164m)

Intent (L7625-7629): "fallen + deep value + informed buyers arriving — insider buying, a new >= 5% holder (SC 13D <= 12 months), or a headcount jump".

Code (L7630-7634): smart legs ≥ 1 removes 773 of 1,047; deep 885; base 274; fallen 140.
- `_inst_arrival = fmp_inst_new_q0 ≥ 1` (L7566) counts new 13F holders in the quarter. The operating median is 31 and the 75th percentile 68. 239 of 244 covered US liquid fallen-deep names (98%) have ≥ 1. This leg is in 216 of 234 fires and is the sole leg in 92. It turns the archetype into "US fallen deep value". Mosaic (100 new 13F holders, insiders net -$0.5m), Kyndryl, Sunrun (insiders net -$21m), Kohl's and Olin: 86 of 234 fires have insiders net SELLING over 12 months. BUG.
- The 13D leg (104 fires) and ins_2q (54) are genuine.
- Coverage: 13F and the usf_* feeds are US-only (`fmp_inst_new_q0` covers 80% of US mb_base and 0-3% elsewhere). US 220 of 234 fires, while the US is 27% of the liquid fallen-deep pool.

Fires: Hyperscale Data (4 legs, 3 insider-buy quarters), Spruce Power (6 buyers, +$8.3m), Pledge Petroleum and System1 fit.

Severity: BUG (the arrival leg is a no-op), TIGHT (US-only by data).
Fix: `_inst_arrival` = new holders ≥ the 80th percentile of the mcap bucket, or net 13F share change > +2pp; require `fmp_insider_net_usd_12m ≥ 0` when it is the only leg.

## arch_mb_biotech_financed_hiring (48 fires, median mcap $417m)

Intent (L8728-8732): "DRUG DEVELOPER, FINANCED AND HIRING INTO THE FALL: the drug developers' highest-lift cluster (AXSM 2017, EXEL 2014, CORT 2013, ITCI 2019)". These are clinical / early-commercial names.

Code (L8733-8743): drug-dev removes 1,219 of 1,385; runway 351; hi260 ≤ 0.5: 187; financed 163; committed 68.
- The gate admits 166 names, but the clinical-biotech scrub (L9401-9409) zeroes every `arch_*` except `arch_biotech_deep_value` on `is_clinical_biotech`. That deletes 118 of 166 members (71%), exactly the population the thesis names: Spyre (+1,800% share count, runway 1.4y), Relay, Legend, Zealand, Junshi, Telix. All 48 survivors are COMMERCIAL: Pharmaron ($10.9B CRO), Fosun Pharma, Alibaba Health (3 lines), 3SBio, Cresco Labs (cannabis), Viva Biotech (CRO). Median revenue $315m, median op margin +7.7%. BUG.
- "Committed" is headcount ≥ +10% in only 2 of 48 fires (`usf_emp_g1` 85% NaN, US-only). 29 fires pass on the R&D-growth fallback.
- "Financed" `fq_financing_cf > 0` is one quarter, debt included: 16 fires pass on it alone.

Severity: BUG.
Fix: add `arch_mb_biotech_financed_hiring` to `_biotech_ok` (L9401), as `arch_biotech_deep_value` is.

## arch_cheap_sales_scaler (2,448 fires, median mcap $142m)

Intent (L6238-6243): "cheap on SALES… cheaply relative to that growth… whose operating margins are IMPROVING… at or near profitability".

Code (L6244-6269): rev ≥ 10% removes 1,043 of 3,556; P/S 0.1-2: 441; PSG: 386; is_operating 370; mcap < $5B: 283; margin improving 131; near profit 115; base-effect guard 107.
- PSG ≤ 0.10 = P/S ≤ 0.1 × growth% (verified: psg = p_s/(rev_yoy×100), median ratio 1.000). It passes 84.8% of names already inside P/S 0.1-2 with growth ≥ 10%, so it is nearly redundant. The EVSG fallback is dead: evsg is NaN wherever psg is NaN (2 exceptions).
- "Margins improving" = `season_robust` (any one of 10 YoY/TTM lenses > 0) or incremental EBIT ≥ 15%. 64.6% of operating names pass. 835 of 2,448 fires have op margin FALLING year on year, and 591 have op and EBITDA margins both falling: Whitehaven (op Δ -11.9pp), Core Natural Resources (-17.4pp), ASTORY (-21.8pp). LOOSE.
- Near-profit: 384 fires have op < 0 and 71 have op < -15% (they pass via EBITDA > 0, FCF > 0 or a zero-filled first-positive flag). Khoon Group: op -124%, EBITDA and FCF negative.
- Base-effect guard (L6259) reads the sparse `rev_3y_cagr` (5% coverage among rev > 100% names). It removes 107, 65 of which have `revenue_3y_cagr ≥ 15%`. COSMETIC/TIGHT.

Fires: Poona Dal, Daemyung Sonoseason, Cirtek and IDIS (P/S 0.13-0.30, growth 21-48%, PSG 0.006) fit the shape. The top of the spirit list is dominated by sub-$20m names.

Severity: LOOSE.
Fix: margin improving = `op_margin_delta_yoy > 0` (or TTM EBIT margin up) where measured, with `season_robust` only as the fallback; use `revenue_3y_cagr`.

## arch_insider_conviction (314 fires, median mcap $177m)

Intent (L6203-6209): open-market buys by officers/directors/10% owners, net buyer, "a value-oriented price so it reads as conviction, not a pump"; US-only by design.

Code (L6210-6233): size ≥ 0.05% of mcap removes 274 of 672; value 196; not melting 41; buy flag 38; net buyer 33. The clinical-biotech scrub removes 84.
- The value leg (EV/EBITDA ≤ 15 | P/B < 2.5 | FCF ≥ 3% | `cheap_any`) passes 78% of operating names with a buy flag. On (P/B 4.6), Pool (P/B 5.0), MGM (4.0) and Lamb Weston (3.6) are "value-oriented". LOOSE (mild).
- Size floor: no fire is a net seller on the FMP 12-month record. One net/mcap value of 3.8e6 is a units artifact.
- US 300 of 314 (SEC Form 4); 80 financials/REITs at P/B < 1, by design.

Fires: Thryv (P/B 0.38, FCF 47%, cluster buy $7.6m), AdaptHealth, Guaranty Bancshares, Transocean and Versant fit. Pledge Petroleum (FCF -94%) and Mobia Medical (op -133%) are weaker.

Severity: LOOSE (mild).
Fix: value = `cheap_any` with `cheapness_score ≥ 0.3`, or P/B ≤ 1.5 for operating names.

## arch_flyover (1,400 fires, median mcap $282m, 73 > $10B)

Intent (L8863-8868): "high-quality, low-coverage, owner-controlled… LOW analyst coverage (<5, ideally 0)… the 'undiscovered quality' lens".

Code (L8869-8887): ROCE/ROIC ≥ 15% removes 2,972 of 4,396; tier core 1,092; sent ≤ 2: 306; insider ≥ 20%: 253; op > 0: 216; FCF: 116; `n_analysts ≤ 5`: 4.
- Neglect: `n_analysts_v` fills NaN with 0 and `~(sent_n_analysts > 2)` is NaN-permissive. 970 of 1,400 fires (69%) have no analyst count on ANY feed. The archetype calls them undiscovered:
  - Tencent TCTZF ($484B).
  - LVMHF, L'Oréal LRLCF, Airbus (AIR.DE / EADSF).
  - Fast Retailing (2 lines), Equinor STOHF (state 72% as "insider").
  - Xiaomi, Japan Tobacco, Chugai (Roche 60%), RATIONAL.

  113 fires exceed $5B, 88 of them OTC/.F/ADR lines. BUG (the same NaN-as-neglect defect as review_batch1 `mb_wave_neglected`).
- Tier `measured=insider.notna()` is always True (zero-filled). COSMETIC.

Fires: Homeland Interactive, Firstlogic, Omega Flex (insider 65%, roce 46%, genuinely ~1 analyst) and Generic Sweden fit. 498 fires have insider ≥ 50% (controlled).

Severity: BUG (missing coverage read as neglect).
Fix: neglect = measured count ≤ 2, or NaN only where mcap is below the country's 60th percentile and no same-name sibling line carries ≥ 3 analysts.

---

## Summary

| archetype | fires | severity | one-line fix |
|---|---|---|---|
| arch_cheap_per_roiic | 3,020 | BUG | cpr ≤ 1.5 lets EV/EBITDA reach 1.5×ROIIC% (NVDA 26×, ASML 43×; 89% pass): cap at ~0.5 or rank in industry; add `_ev_sane`, ROIIC ≤ 1.0 |
| arch_cundill_deep_value | 296 | BUG | "no deficits" reads EPS/NI *growth* shares (Comcast 8/8 fails, KEP 3/8 passes): use tc_opinc_pos/tc_years first |
| arch_oak_deep_value | 582 | BUG | "real cash" is gross cash: 282 fires net debt, 173 > mcap (VW, Nissan, Casino -36×): use net_cash_pct ≥ 0.20 |
| arch_overdepreciated_assets | 455 | BUG | da_ttm in reporting ccy vs USD revenue/capex: 110 fires D&A > revenue (Honda, Denso, JR East): FX-convert da or use fq_da/fq_capex; read revenue_3y_cagr |
| arch_xr_discops_mask | 79 | BUG | 37 fires on NI ≤ 0 with no discontinued item (Ford, TAP, CAG, LUMN impairments): require disc < 0 and ≥ 50% of the gap; scrub CHSC*/JSM |
| arch_mb_smart_money_wreckage | 234 | BUG | 13F "≥ 1 new holder" true for 98% of US names (sole leg in 92; 86 fires insiders net selling): use a top-quintile or net-ownership change |
| arch_mb_biotech_financed_hiring | 48 | BUG | clinical-biotech scrub deletes 118 of 166 members (the thesis population): add to `_biotech_ok` |
| arch_flyover | 1,400 | BUG | 970 fires have no analyst count anywhere (Tencent, LVMH, Airbus, Equinor OTC lines): NaN ≠ neglect; size/sibling test |
| arch_fastest_segment | 569 | TIGHT / LOOSE | 556/569 US; 120 fires engine ≥ 70% of revenue (META 99%): add share ≤ 0.6 and rev ≤ seg - 10pp; M&A guard; global segment fill |
| arch_xr_hidden_segment_compounder | 38 | TIGHT / LOOSE | 37/38 US; Xerox/L3Harris/EQT segment jumps are M&A: add acquisition guard |
| arch_capital_discipline | 2,492 | LOOSE | 1,210 fires pass only as "dividend payer with financing outflow" (Aramco, PetroChina); 800 "un-re-rated" at P/B ≥ 1.5 via EV/EBIT ≤ 12: require shrink, relative cheapness; drop dead pb.isna() |
| arch_owner_operator | 3,852 | LOOSE | 774 of 918 insider > 58% fires pass via a sub-1% 3y share decline (state/parent-controlled): shrink ≤ -2%, roce floor on US path |
| arch_wolf_value_catalyst | 455 | LOOSE | 106 fires net debt via NCAV/FCF "fortress" (UNISON -2.3×); 20 fires rev > 100%: net cash ≥ 0 on every route; base-effect cap |
| arch_xr_neg_ev_growth | 200 | LOOSE | 121 fires only via gross-cash > EV flag (Xiaomi net cash 14%, WuXi 7%): require net cash ≥ 50% |
| arch_xr_audited_streak_unrerated | 2,091 | LOOSE | 2-of-8 lens vote makes AMZN/META/Samsung (+248%) "unrerated": ≥ 3 lenses + r52 ≤ rev growth; fix dead NaN-permissive arm (222 names) |
| arch_xr_forced_seller | 174 | LOOSE | nothing seller-specific (NFLX, INTU, BSX derating); zero-filled ebitda_yoy admits 8: NaN-aware, industry-relative drop, split check |
| arch_xr_latent_inflection_floor | 260 | LOOSE | "floor" via P/B or gross cash with net debt (114 fires; Atlantic Sapphire -48×, Orpea -13.5×): require net cash ≥ 0 |
| arch_mb_fallen_value_turn | 401 | LOOSE | turn via single-quarter fmp_dyn (79 sole) / FCF swing (55); 121 fires op < 0 (DH -105%): require TTM turn + recency |
| arch_cheap_sales_scaler | 2,448 | LOOSE | "margins improving" = any 1 of 10 lenses: 835 fires op margin falling; use op_margin_delta_yoy > 0; read revenue_3y_cagr |
| arch_capital_returner | 1,464 | LOOSE (minor) | 27 fires cry ≥ 5% vs div + bb < 2%; fcf 1e-32 passes; fill buyback_yield from fmp_st (+63 names) |
| arch_insider_conviction | 314 | LOOSE (mild) | value leg passes 78% (On P/B 4.6, POOL 5.0): tighten to cheapness_score or P/B ≤ 1.5 |
| arch_dividend_verified_value | 65 | OK | optional: tc_uncov == 0 where measured (22 fires allow one uncovered year) |
