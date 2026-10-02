# Archetype review, round 2, batch 7 (23 archetypes)

Method. I did not run the pipeline. An instrumented in-memory run of `compute()` by a sibling audit (scratchpad/r2/df.parquet + locals.parquet, 15:38 today, from the same archetype_tags.py) gave me the final frame and every intermediate Series (`is_operating`, `_not_melting`, `_mb_base`, `heavy_debt`, `_informed_g`, `_hidden_pct` ...). Its 23 `arch_*` columns match the published archetype_tags.csv **exactly** (23/23, 100.00% row agreement). I then rebuilt each gate leg by leg from those inputs (scripts scratchpad/b7/a1.py ... a23.py, working set b7/w.parquet). For **22 of 23** archetypes the reconstruction matches the published column exactly (pub-only 0, rec-only 0). For the 23rd, levered_inflection, the `beaten_down_any(0.25)` leg was proxied from `_watch`, so that match is circular for that one leg. "Removes X of Y" means: of the Y names that pass every other leg (after the noncommon/corrupt/shell/ghost/clinical-biotech scrubs), this leg alone removes X. Universe N = 46,526, operating 36,173, `_mb_base` 15,304.

Shared facts this batch leans on (in addition to batch 1's):
- **Stale `cash_gt_ev_flag`.** The flag comes from an earlier yartseva_db / edgar_to_yartseva snapshot. Against today's master, 471 of the 1,733 flagged names have cash < EV, and 182 have EV < 0. Any gate that ORs it in, such as discounted_vehicle and nol_shell, admits names with net debt.
- **Rows with mcap <= 0 or NaN are not scrubbed.** The <$2M shell scrub requires mcap > 0, so 5,083 rows with no market cap stay live. Delisted or acquired names fire: FLIR, CCMP, SWMA.ST/SWMAF (Swedish Match, taken private in 2022), EVTN, CLCN. buyback_compounder has 59 such fires, capital_light_pivot 66 and geographic_global 7.
- **Multiple lines of one issuer.** Same-name duplicate fires: customer_float 314, capital_light_pivot 227, buyback_compounder 203, bottleneck 198, hidden_assets 119. They inflate counts and books.
- **USD-quoted OTC/ADR lines.** Master flows such as `financing_cf_ttm` stay in reporting currency while `market_cap` is USD. `_fx_coherent` checks only mcap against revenue, and revenue *is* converted, so this mismatch passes (see xr_paydown_yield).
- **EDGAR-only inputs.** Several inputs exist only for US filers (non-null share of operating names): `geographic_region_count` 11%, `investments_associates` 5%, `deferred_tax_valuation_allowance` 11%, `rpo` 3%, `ppe_gross` 10%, `nol_usd` 5%. The FMP-global counterparts exist but are mostly unused (`fmp_geo_count` 5.6%).
- **ZA FX bug (seen again).** NTCP.JO Netcare shows mcap $758B, with currency ZAC treated as ZAR. It appears in customer_float and bottleneck as a "largest" member.

---

## arch_discounted_vehicle (1,251 fires, median mcap $56m)

Intent: "Cluster E7: Discounted Vehicle"; endpoint matrix spirit "net-cash operating company below 0.85x book". The mechanism to close the discount (buyback, 13D, deal) is surfaced as a flag, not gated (L1647).

Code (L1639-1646), legs and binding counts:
- `is_operating`: removes 201 of 1,452.
- `pb` in (0, 0.85) (L1641): `s('pb', 99)`, so NaN fails. Removes 2,208 of 3,459, the most binding leg.
- `cash_gt_ev > 0 | net_cash_pct_sane > 0.20` (L1642): removes 1,858 of 3,109. The comment reads "(G2) drop >100%-of-mcap shells", but the `cash_gt_ev` OR-leg readmits them. **83 fires have net cash > 100% of mcap**, and they dominate the spirit ranking: 28 of the top-50 spirit names, including 2222.HK at 3.9x, 1900.HK at 2.1x and RWI.BK at 1.8x. TMC.BK passes with `net_cash_pct` NaN and cash of THB 7.0B against a THB 0.32B mcap, a 22x data error that only the flag lets through. 124 fires pass only on the flag. 60 fires carry the flag although cash < EV today, and 18 of them have net debt (net_cash_pct <= 0): 088790.KS (EV 28.4B > mcap 28.3B), DH, 9923.HK, GEA.WA, 5070.KL (-29%), RFT.AX (-17%), 2393.HK, 3758.T. **BUG.**
- `~(nde >= 1 & nde < 90)` (L1643): removes 7 of 1,258, a near no-op. 382 fires have nde unknown (99).
- `_not_melting` (L1644): removes 83. Still, 304 fires have op margin < 0, 415 have FCF yield < 0, and 140 have both. YSS (op -38%, FCF -20%, CFO -19%), SSYS, 000910.SZ (FCF -24%) and GEGYF (op -114%) pass through the "improving" lenses.
- `mcap < $2B` (L1645): removes 62.

Nothing measures "vehicle" (holdco, NAV, look-through). In effect this is a P/B < 0.85 + net-cash screen. It overlaps hidden_assets on 861 of 1,251 fires (69%).

Coverage: pb NaN 28.8% of the universe / 27.6% of operating names; net_cash_pct 23.3% / 21.4%; cash_gt_ev_flag 24.8%. Venues: JP 290, KR 193, HK 165, US 131, TH 61, IN 60. This is the structural low-P/B Asia small-cap set; 598 fires are below $50m.

Fire check:
- 016090.KS Daehyun: P/B 0.26, net cash 87%, op +1.6%, FCF 37%. Fits.
- 0393.HK Glorious Sun: P/B 0.64, net cash 61%, op 7.6%. Fits.
- Kangwon Land: P/B 0.80, net cash 98%, op 18%. Fits.
- 2222.HK NVC: net cash 3.9x mcap, P/B 0.08. A data or holdco artifact.
- 1900.HK: FCF NaN, 2.1x.
- TMC.BK: corrupt cash.
- GEGYF/GEGYY: two lines of a loss-making E&P.

Severity: BUG (the stale cash_gt_ev leg defeats G2 and admits net-debt names), LOOSE (no "vehicle" leg, 140 double-negative operators).
Fix: cap the flag leg the same way, `net_cash_pct <= 1.0`, and recompute cash > EV from today's cash/EV instead of the stale flag. Require `op_margin > 0 | fcf_yield > 0`. Dedupe lines.

## arch_roic_inflect (1,079 fires, median mcap $566m)

Intent (L1935): "latest ROIC crossed zero from below AND cash ROIC also positive (confirms the inflection is real, not accounting)".

Code (L1942-1951):
- turn = `roic_inflection_flag | cash_roic_inflection_flag | _roic_turn_q`: removes 6,618 of 7,697. The comment says annual cross **AND** cash; the code ORs in the *cash* ROIC cross as a standalone path. `cash_roic_inflection_flag` (fmp_statements.py L186-191) is "prior-year FCF/IC <= 0 < latest", i.e. a one-year FCF dip and recovery. **522 of 1,079 fires (48%) pass only on that flag while accounting ROIC was positive in all 5 of the last 5 years.** 149 of them are established compounders with roic_lindy >= 10%: VRTX (lindy 17%, cash lindy 26%; its FY24 FCF went negative on the Alpine IPR&D charge), Nintendo (3 lines), Lenovo (3 lines), Titan, Bajaj Auto, Steel Dynamics, Devon, Eoptolink. None of these "crossed zero". **BUG.**
- Path split: annual flag 326, cash flag 677, TTM 267; only 57 fires carry both flags. The EDGAR `roic_inflection_flag` column has 0 non-null values of its own, so every annual flag comes from the FMP fill.
- `~(fqx_roic_ttm < 0.03)` (L1947): removes 228; 54 fires pass with the input NaN.
- `cash_roic_lindy > 0` (L1948): a lindy median, not the current cash ROIC. Removes 627.
- `rev_yoy > 0`: removes 543. `_op_viable(0)`: removes 60.

Coverage: fqx_roic_ttm NaN 36% / 35%; bs_ebit_turned 48% / 46%; cash_roic_inflection_flag 24% / 19%. Venues: US 266, JP 186, IN 150, CN 121. 93 fires are duplicate lines.

Fire check: 4449.T giftee (both flags, TTM ROIC 26%) and AGXKF (both flags) fit. MRVL and DASH (annual flag, lindy negative, now positive) fit. Transcend 2451.TW (5/5 positive years, cash flag only) does not. SSRM shows fqx_roic_ttm 382 (a units artifact passes the >= 3% sizing). VRTX does not fit.

Severity: BUG (the cash-flag OR path admits perpetually positive ROIC names).
Fix: make the cash flag a confirmation, `(roic_inflection_flag==1 | _roic_turn_q) & (cash_roic_inflect | current cash ROIC > 0)`, or require `n_yrs_positive_roic <= 4`. Cap fqx_roic_ttm at 1.

## arch_buyback_compounder (1,163 fires, median mcap $2.6B)

Intent (L2414): "shrinking share count + durable ROIC + clean balance sheet. Greenblatt / capital-allocation classic."

Code (L2421-2444):
- `_shares_shrink`, the OR of four legs (5y <= -5%, 3y <= -3%, buyback >= 3% with shares_yoy <= 2%, FG diluted g1 <= -3%): removes 3,666 of 4,829. Only-path counts: 5y 100, 3y 172, buyback 80, fg1 64. The buyback-yield leg admits issuers whose count *grew*. **Celltrion: 3y shares +67%, 5y +59%** (merger stock), in through a 3.2% buyback yield. 126 fires have shares_growth_3y > 0 and 204 have 5y > 0.
- `~(shares_yoy > 0.02)`: removes 35. `roic_lindy >= 8%`: removes 1,855. `n_yrs_roic_pos >= 4`: removes 52. `fqx_fcf_ps_g` not < -10%: removes 261, but the input is NaN for 73%. `_roce_now_ok`: removes 4, a near no-op.
- "Clean balance sheet" was demoted to a weight (L10270, nde -1). As a result 92 fires have nde > 3, 28 have nde > 5, and **49 have negative equity**: HLT, YUM, FICO, DPZ, DVA, all levered recaps. The headline comment still promises "clean balance sheet". LOOSE / COSMETIC.
- There is no `mcap > 0` leg, so **59 fires have no market cap**, delisted or dead lines among them: FLIR, CCMP, SWMA.ST, SWMAF, SWMAY ($16B, delisted in 2022), KAZ.L. SWMA.ST and SWMAY rank #3 and #6 by spirit. **BUG.**

Coverage: buyback_yield NaN 54% (FMP FY repurchase fills to 22%); shares_yoy 45%; fqx_fcf_ps_g 73%. Venues: US 599, JP 151, UK 57. 203 fires are duplicate lines.

Fire check: AAPL (5y -14%), 6194.T Atrae, 3964.T, PAY.L, TAYD fit. Celltrion, SWMA*, 7W6.F (shares_growth_5y 130x data) and HLT/YUM (negative equity) do not.

Severity: BUG (no live-listing / mcap leg), LOOSE (buyback-yield leg ignores multi-year issuance; leverage cap demoted).
Fix: add `mcap > 0`. Require `~(shares_growth_3y > 0)` on the buyback-yield and FG legs. Restore a soft `equity > 0 | nde <= 3` guard, or rename the thesis.

## arch_capital_light_pivot (2,105 fires; watch 2,416; median mcap $708m)

Intent (L2576): "revenue growing AND assets growing slower AND ROIC turning up. The asset-light transition." The core (L2592) drops the lindy > 10% escape.

Code (L2579-2594): `rev_3y >= 8%` removes 1,738; `asset_3y < rev_3y` removes 1,127; `n_yrs_roic_pos >= 3` removes 577; `(roic_acc > 0 | lindy > 10%)` removes 1,092; the core leg removes 176; `asset_3y >= -10%` removes 52; `_roce_now_ok` removes 7.
- "Capital-light" is never measured. 340 fires have capex intensity > 10% (502 have it NaN): TSFA.F/TSMC 34%, MU 28%, Tencent 22% (3 lines), LLY 20%, AEM, Barrick, SII.DE (199%). LLY has asset growth 31.5% against revenue 31.7%, a 0.2pp "pivot". 306 fires have a revenue-minus-asset gap < 2pp, and 394 have ROIC acceleration in (0, 1pp]. LOOSE.
- `roic_acceleration` is unbounded: 18 fires have |acc| > 1 (EVTN 21.3, AHIX 6.6 on lindy -8%). These artifacts drive the top spirit scores.
- **66 fires have mcap <= 0 or NaN**, including 3 of the top-6 spirit (EVTN, CLCN, IKW.AX). BUG (shared).

Coverage: revenue_3y_cagr NaN 28% / 26%; fqx_roic_ttm 36%. Measured-otherwise fallback: names without either ROIC lens keep the watch rule. Venues: US 497, IN 292, CN 290, JP 265.

Fire check: JCHAC.BO, NEOWIZ (capex 0.5%, ROIC acceleration 30pp) and ASML (capex 4.5%) fit. TSMC, MU, Tencent, LLY are capital-heavy and do not. EVTN, CLCN, IKW.AX are dead lines.

Severity: BUG (mcap-0 rows lead the ranking), LOOSE (no capital-intensity measure; trivially small gaps pass).
Fix: add `mcap > 0` and `capex_intensity` falling or <= sector median. Require gap >= 3pp. Clip roic_acceleration to [-1, 1].

## arch_kullamagie_breakout (284 fires; watch 1,165; median mcap $957m)

Intent (L3289): "[C] leader across momentum scans; [C] large prior advance (>=30%); [P] orderly tightening near rising highs." The core (L3306) says leadership is "ranked WITHIN the listing market (a global rank over-weighted a few high-volatility markets 2-7x)".

Code (L3293-3315):
- The watch leader leg `_pr6 >= 95 | _pr12 >= 95` is still a **global** rank, and it is the binding leg: it removes **348 of 632** names that pass the in-market core (ts_rs_pct_mkt >= 90, at >= 90% of the 52w high, above MA30, >= $1M/day). The global-leader share runs TW 11.8%, US 8.7%, JP 5.4%. So the core's stated fix does not apply, because the global gate it replaced still runs first. TIGHT (inconsistent).
- Tight: all 284 fires pass via `sr_m_squeeze_run >= 3`; the base-depth path never fires (fire median base depth 0.80). Measured `ts_tight5` > 15% on 91 fires and > 25% on 26 (max 68%). "Orderly tightening" is weak. LOOSE.
- Near-high: `_off_high` in [-0.25, -0.005] uses the quote-time column. It disagrees with ts_dist_hi52 by > 10pp on 20 fires and excludes 16 names that sit at the high; meanwhile 27 fires are >= 99.5% of the high by the weekly panel. COSMETIC.
- 32 fires have no weekly panel (the measured=False fallback). INC.MI is an example; their spirit is NaN.
- Financials are not excluded (39 fires; 8377.T Hokuhoku ranks #6 by spirit). Acceptable for a tape setup. PANW is labelled "Financials" (a sector data error).

Coverage: roc_6m NaN 40%; ts_* 23.5% / 22%; squeeze 40%.

Fire check: 6213.TW ITEQ (RS 99.7, 0.99 of high, +346%), Advantech, Welspun, DELL, MediaTek fit. INC.MI (no panel) and fires with tight5 > 0.25 are not tight.

Severity: TIGHT (global leader gate overrides the in-market core), LOOSE (tightness).
Fix: drop `_kk_leader` when ts_rs_pct_mkt is measured. Use `ts_tight5 <= 0.15` as the tight leg and ts_dist_hi52 for near-high.

## arch_geographic_global (696 fires, median mcap $5.7B)

Intent (L2273): "4+ geographies reporting. Currency diversification + market diversification."

Code (L2275-2280): `geographic_region_count >= 4` removes 18,075 of 18,771. `fcf > 0 | ebitda_margin > 5%` removes 167. `_roce_now_ok` removes 0 (a no-op here). It also passes the segment-survivability scrub.
- **The input is NaN for 89%**, and US coverage is only 17% of operating names. **654 of 696 fires (94%) are US-listed**; JP has 0.0% coverage, UK 2.2%, DE 1.6%. The FMP geographic count (`fmp_geo_count`, 5.6% coverage, 947 names >= 4) is not used; 82 operating names would add. TIGHT.
- A count of reported regions is not "global": NVDA qualifies on 4 regions, and a US / Canada / Mexico / Other split counts as 4. There is no foreign-revenue share leg; `fmp_geo_em_share` exists but is 94% NaN. LOOSE.
- 113 fires have op margin < 0: CE (op -7%, ROCE -4%), AVD, CBAT (op -10%, ROCE -14%), XRX. 7 fires have mcap <= 0.

Fire check: ADNT and VC fit (14-18 regions, real global auto supply). NVDA, GOOG and META fit only nominally (a 4-region filing). AMSYF ArcelorMittal on its US OTC line fits, but its home line does not fire (no EDGAR).

Severity: TIGHT (US-EDGAR only), LOOSE (region count is not diversification).
Fix: fill from `fmp_geo_count`. Require largest-region share <= 60% (`fmp_geo_largest_share` exists). Add `_not_melting`.

## arch_wolf_turnaround (676 fires, median mcap $49m)

Intent (L3518): "loss-maker crossing into the black (incl. the OCF-turns-positive shape) while still GROWING... Cheap-entry ceiling added."

Code (L3521-3550): mcap 10-200m removes 757; the crossing leg removes 512; cheap-entry removes 365; growing/cost-cut removes 264; `emd_c >= 0` removes 217; op < 15% removes 164.
- The crossing leg includes `(ebitda_inflection > 0) & oper_lev_any` (L3529), where `ebitda_inflection` is an EBITDA *growth* turn, not a loss-to-profit turn. **245 of 676 fires (36%) carry no first-positive or turned flag at all** (EBITDA / NI / CFO / FCF first positive, EPS turned, TTM EBIT turned). 293 fires already earn an op margin >= 5%. Examples: Gyldendal (op 12.5%), Bjorn Borg 13.5%, Talbros 10.2%, Saison Info 12.0%, Woowon (op 2.6%, no turn flag) at spirit #1. LOOSE.
- `emd_c = ebitda_margin_delta` is zero-filled, so NaN passes `>= 0`. That is 2 fires today; the input is NaN 34% of operating names.
- `wolf_cheap_entry` is EV/EBITDA < 12 OR P/E < 20. 107 fires pass on P/E alone, including MOONG.BK (EV/EBITDA 54.5, P/E 12) and CRST.L (EV/EBITDA 74, op -8.6%, P/E 7.2 from a one-off).
- 131 fires have NI first positive while op margin is still < 0; 50 have op < 0 and FCF < 0.

Coverage: the first-positive flags are NaN 25%; bs_ebit_turned 48%; ev_ebitda 49%; p_e 50%. Venues: JP 178, KR 110, IN 79, US 57.

Fire check: TYGO (EBITDA first positive, rev +92%), PEHA.JK, Prosafe and 1596.HK fit. Gyldendal, Bjorn Borg, Woowon and Sansei (op 3.7%, already profitable, no prior loss) do not.

Severity: LOOSE (the EBITDA-growth path admits names that were never loss-makers).
Fix: drop the `ebitda_inflection & oper_lev_any` path, or require a negative op margin or EBIT in the prior FY. Use `_ncol` for emd. Require EV/EBITDA < 12 whenever it is measured.

## arch_oak_deleveraging (422 fires, median mcap $517m)

Intent (L3766): "heavy FCF, moderate debt being paid down (rising EBITDA mechanically cuts the ratio = his actual thesis)".

Code (L3769-3794): nde 1-3 removes 1,528 of 1,950; yield >= 10% removes 516; net debt not rising removes 229; cash out to providers removes 134; IC >= 2 (soft) removes 88; capex/DA removes 81.
- The EBITDA leg `ebitda_yoy > 0 | ebitda_inflection | season_robust` lets **177 of 422 fires (42%) through with EBITDA flat or falling**, 121 of them down >= 10%. Transcontinental (2 lines, EBITDA -33%), Midsona -41%, HON -13%, Jiumaojiu -10%. `season_robust` is any margin/TTM lens, which is not "rising EBITDA cuts the ratio". LOOSE.
- "Heavy FCF" passes via `owner_earnings_yield >= 10%` alone on 46 fires whose FCF yield is 3-9%: BATS (FCF 6.4%), PSX 6.1%, HON 6.2%, R. SOLV passes with FCF -1.0% (OE 11.3%). LOOSE.
- `fq_netdebt_change_pct_assets` is NaN-permissive (92 fires unmeasured); 330 show net debt falling. IC is NaN on 89.
- 77 fires have NaN spirit. DTEA.F is a Frankfurt line with no quarterly panel.

Fire check: SBM Offshore (FCF 47%, net debt -20% of assets, EBITDA +71%), FirstGroup, Tai Hing, PYT.VI and TMILL.BK fit. Transcontinental, HON and SOLV do not.

Severity: LOOSE.
Fix: require `ebitda_yoy >= 0` (TTM) where measured. Require `fcf_yield >= 0.08` alongside any OE/robust lens.

## arch_hidden_assets (1,955 fires, median mcap $83m)

Intent (L4035-4048): off-EV "securities/investment portfolio sitting under the operating business"; L4086: "HIDDEN means a portfolio... a pure net-cash pile with no stakes is negative_ev_value / net_cash_returner ground".

Code (L4065-4093): `_hidden_pct = (assoc.fillna(0) + cash - debt) / mcap >= 25%` removes 2,924. pb < 1.5 removes 648. The profit-any leg removes 404. `~(assoc/mcap < 0.10)` removes 40.
- **`investments_associates` is NaN for 94.3% of the universe and 94.9% of operating names** (US 15%, JP/IN 0%). The stakes gate is NaN-permissive and `fillna(0)` reduces the measure to net cash / mcap. **1,929 of 1,955 fires (98.7%) have no associates line**, so the archetype is the very "pure net-cash pile" its comment excludes. Only 26 fires carry a >= 10% stake (TCOM/TRPCF, WB/WEIBF, IAC, TK, TDS, YMM: genuine). It also duplicates discounted_vehicle on 861 names. **BUG.**
- No upper bound: 321 fires have net cash > 100% of mcap and 63 > 200%, and they top the spirit list: HOLO 10.1x, 900250.KQ 9.0x, 900310.KQ 7.0x, CDGXY 4.1x, FANCY.BK 2.2x. That is data or holdco-scale corruption. CICOY shows cash 508% of mcap against 67% on 601919.SS (ADR scale), and `_fx_coherent` missed it.
- CCZ (a Comcast exchangeable debt line, $15.5B "mcap") fires as hidden assets. This is a non-common leak.

Coverage: assoc 94% NaN; cash and debt about 22%. Venues: JP 524, HK 246, KR 235, US 221, CN 161.

Fire check: TCOM (assoc $8.8B = 35% of mcap, P/B 1.06), IAC, TK and Weibo fit. HOLO, CDGXY, 900250.KQ, Kia, Gree and COSCO (plain net cash) do not.

Severity: BUG (the NaN-permissive stakes leg collapses the thesis into a net-cash screen; no upper sanity cap).
Fix: require `assoc/mcap >= 0.10` (use FMP `longTermInvestments` to reach non-US). Cap `_hidden_pct <= 1.5`.

## arch_customer_float (1,514 fires, median mcap $2.6B)

Intent (L4310-4313): "negative working capital, INVERTED forensic read: customers funding the business ... CFO above NI".

Code (L4321-4339): the negative-WC/CCC leg (4 lenses OR'd) removes 4,013. op > 3% removes 582. rev_yoy >= 0 removes 564. CFO/NI >= 1.1 removes 410. CFO/NI a year ago removes 120. The supplier-squeeze guard removes 52.
- The `net_working_capital < 0` lens is total NWC, which goes negative from short-term debt or current maturities, not from customer float. **380 fires pass only on total NWC < 0 while operating NWC/revenue > 0 and CCC > 0.** PM (CCC 254 days), NOVN (117 days), Sanofi (2 lines, 83 days), EMR 104, HCA, UNP, WM, CTM.F, and SOMN "Southern Co" (a utility mislabelled Materials). LOOSE, close to a BUG.
- `rev_yoy_c` is zero-filled, so 57 fires pass `>= 0` with rev_yoy NaN.

Coverage: NWC NaN 42% / 40%; fq_ccc 44%; fmp CCC 18%. Venues: US 622, JP 109, CN 109. 314 fires are duplicate lines.

Fire check: TEMN.SW/TMSNY (CCC -228 days, op NWC -53%), Netcall, Broadleaf, Tencent (CCC -159 days), AMZN (-63 days) fit. PM, NOVN, Sanofi, UNP and SOMN do not. NTCP.JO is the ZA FX artifact.

Severity: LOOSE.
Fix: drop the total-NWC lens, or require it with `fq_op_nwc_to_rev < 0 | ccc < 0`. Use `_ncol('rev_yoy')`.

## arch_dta_reversal (177 fires, median mcap $111m)

Intent (L4504): "large DTA with a VALUATION ALLOWANCE in a business that has TURNED profitable — the allowance reverses".

Code (L4510-4517): VA >= 15% of mcap removes 13,184. `op > 0 | roce > 0` removes 351. `~(eps_pos_share_8 < 0.5)` removes 50.
- "Turned profitable" is read as op > 0 **or** ROCE > 0 on a single point. **108 of 177 fires have TTM net income <= 0, and 56 pass on ROCE alone with op margin <= 0**: DOMO (op -3%, NI -$56m), BATL, CISO (op -23%), MOS (NI -$638m), XRX (NI -$989m). An allowance reverses on sustained *pre-tax income*, not on positive ROCE. The EPS share leg is NaN-permissive (8 fires). LOOSE.
- VA/mcap reaches up to 7.8x (NBR 2.9x, XRX 4.3x, CYH 2.5x). These are heavily levered names where VA relative to equity says little about value to shareholders.
- PRSI is named "Square, Inc." with a $5m mcap and EHVVF has a $2m mcap; the CIK/name mapping is suspect.

Coverage: VA NaN 89% (US 31% of operating names). Fires: US 174, UK 2, CA 1. TIGHT by construction.

Fire check: APA (NI $1.6B, 5 of 8 positive quarters), AA, WFRD, GTES, SD fit. XRX, DOMO, MOS and CISO do not.

Severity: LOOSE.
Fix: require `pretax_income_ttm > 0 & fqx_eps_pos_share_8 >= 0.625` (measured), and drop the ROCE OR-leg.

## arch_xr_paydown_yield (444 fires, median mcap $293m)

Intent (L4674): "the FINANCING LINE proves a massive annual transfer to capital providers (>=10% of mcap) against a still-heavy debt load with stable EBITDA."

Code (L4679-4690): `_paydown_y = -financing_cf_ttm / market_cap` (L4679). Paydown >= 10% removes 1,450; net debt down >= 3% of assets removes 533; EBITDA stable removes 293; nde > 0 removes 215.
- **Currency mix.** `financing_cf_ttm` is in reporting currency, but `market_cap` on USD OTC/ADR lines is in USD. `_fx_coherent` passes these because revenue *is* converted. Examples: TLK paydown **1,370x** (IDR 20.2T over a $14.7B mcap; true value 7.9%), PTGCF 5.69 (true 0.17), SCVPY/SCVPF 3.07/2.90 (true 0.086), GRPFF 4.98 (true 0.31), SASOF 1.06 (true 0.049), AIPUY/APTPF 0.67/1.04 (true 0.022), SBYSF 0.585 (true 0.035). **30 fires on USD lines reuse the home line's financing figure, and 15 of them fail the 10% bar at the true ratio.** The comment (L4682) claims the fx gate covers financing_cf. **BUG.**
- "Still-heavy debt load" is coded as `nde > 0` ("no fixed band"). 102 fires have nde < 1 and 50 have < 0.5. LOOSE relative to the thesis.
- 78 fires show a financing outflow above 2x their FCF yield (refinancing or asset-sale funded).

Coverage: financing_cf NaN 38% / 37%; netdebt change 38% (25 fires unmeasured). Venues: US 125, JP 56, TH 34, HK 30.

Fire check: THE.BK (paydown 87%, net debt -34% of assets, FCF 80%), 3399.HK, NPK.JO, VOD (27%, nde 4.5) and CMCSA fit. TLK, PTGCF, SCVPY and GRPFF are artifacts. SSTY.L has nde 36 and HDVTY 14 (heavy, but EBITDA is barely covering).

Severity: BUG (currency mix on ADR/OTC lines).
Fix: compute paydown as `-financing_cf_ttm * fx_report_to_usd / market_cap_usd` (the fq_fx bridge already exists), and require `nde >= 1`.

## arch_xr_cannibal_below_cash (34 fires, median mcap $118m)

Intent (L4893): "market cap BELOW net cash while management BUYS BACK stock."

Code (L4898-4907): net cash >= 100% of mcap removes 2,406. Buyback >= 1% removes 97. Operating removes 69. Corroboration removes 8. shares_yoy removes 5.
- Financial and deposit leaks:
  - RBKB Rhinebeck **Bancorp** is labelled Consumer Discretionary / Specialty Retail. The name regex only runs when sector is blank, so this bank passes.
  - CTT.LS/CTTOF: Portuguese post plus Banco CTT. "Net cash" is bank deposits (P/B 2.1-2.7, which is not below cash).
  - DRTGF Jet2: net cash 2.21x but cash only 0.87x mcap; airline customer deposits.
  - 9959.HK Linklogis and 6608.HK Bairong (supply-chain finance and fintech).
- 14 of 34 fires show `net_cash_pct > cash_pct_mcap + 5pp` (net cash above gross cash), which signals two inconsistent cash definitions. LOOSE.
- 038540.KQ shows fmp_st_buyback_yield_y0 = 559.7 (data).

Coverage: net_buyback_ttm NaN 70%; shares_yoy 45%. Venues: US 15 (mostly China ADRs), KR 7, HK 5.

Fire check: MOMO (net cash 1.7x, buyback 15%, shares -9%), SOHU, ATHM, Gungho, 120030.KS and PXGYF fit. RBKB, CTT, Jet2 and Linklogis do not.

Severity: LOOSE (financial leakage through a mislabelled sector; data inconsistency).
Fix: run the name-based finance regex regardless of sector (`bancorp|bank|banco`). Require `net_cash_pct <= cash_pct_mcap` as a consistency check. Exclude deposit-taking industries (airlines/travel with customer prepayments) via `cash_pct_mcap >= net_cash_pct`.

## arch_xr_pre_scale_margin (153 fires, median mcap $234m)

Intent (L5111-5121): a fat gross margin not yet in the operating line, the scaling proven by a high incremental margin or by margins inflecting, revenue >= 15%, and "not yet re-rated".

Code (L5122-5143): implemented as described. Revenue 15-150% removes 638; op in [-15%, 12%] removes 177; scaling removes 144; GM >= 40% removes 42. The `gap >= 30pp` leg removes **0**: it is implied by GM >= 40 and op <= 12, so it is dead. COSMETIC.
- Scaling paths: incremental margin 46, op delta 125, EBITDA delta 111 (17 on the EBITDA delta alone). 8 fires carry a negative op delta.
- Price legs are generous: EV/GP <= 8 or EV/S <= 4. AMZN ($2.8T, op 11.5%, EV/GP 7.7) passes as "pre-scale"; DKNG, HUBS, PINS, SNAP and PCOR pass on SBC-depressed GAAP op margins. There is no SBC leg. LOOSE (mild).
- 3 fires show GM = 100% (no COGS reported: 042420.KQ, LCY.AX explorer).

Coverage: incremental_ebitda_margin NaN 65% / 61%; ev_gross_profit 42%. Venues: US 56, JP 16, IN 15, KR 12.

Fire check: PHO.OL Photocure (GM 94%, op -7% to +6pp, EV/GP 2.0), ZEEMEDIA, ALM.MC, PERF and Woongjin fit. AMZN does not. LCY.AX is a data artifact.

Severity: LOOSE (minor), COSMETIC (dead gap leg).
Fix: add `mcap < $20B` or EV/GP <= 5 with SBC-adjusted op margin. Drop or raise the gap leg. Require GM < 0.999.

## arch_xr_contracted_backlog (90 fires, median mcap $10.0B)

Intent (L5420-5426): RPO >= one year of revenue "while the market prices the TRAILING numbers ... contract wins the tape hasn't caught".

Code (L5428-5440): RPO >= 1x revenue removes 7,920. Cheap (EV/S <= 4 | EV/EBITDA <= 15 | FCF >= 3%) removes 59. rev >= 5% removes 36.
- "Unpriced" is an OR of three loose lenses. 30 fires pass on FCF >= 3% alone: GEV (EV/EBITDA 96, EV/S 5.8), SNDK (EV/S 11.6), CRM (EV/S 5.3). Nothing compares RPO growth with price, and 45 of 90 fires are > $10B, among the most covered stocks there are: BA, RTX, GD, DELL, LNG, CQP. LNG/CQP's 20-year SPAs make RPO/revenue structurally about 5x; that is not a new contract win. LOOSE.
- Fires with negative FCF and op losses (ELWT FCF -20%, op -44%; KAZR FCF -8%, op -54%) pass via EV/S.
- `rpo` is "USD (EDGAR)". It is 97.4% NaN, so the archetype is blind outside the US (88 of 90 fires are US). TIGHT by design.

Fire check: SIF (RPO 1.8x, EV/S 1.6), HP, CXDO and GD fit. GEV, SNDK and CRM are priced on backlog. LNG/CQP are structural.

Severity: LOOSE.
Fix: require `ev_sales <= 3 & ev_ebitda <= 15` (AND), plus RPO growth > revenue growth (needs prior-period rpo) or a size cap.

## arch_xr_owned_realestate_value (34 fires, median mcap $582m)

Intent (L5653-5661): "OWNS... its footprint" so it "carries real estate worth a multiple of net book... Tell: a high accumulated-depreciation ratio".

Code (L5662-5680): pb < 1.2 removes 77; accumulated ratio >= 50% removes 41; PP&E net >= 25% of assets removes 35; op/FCF > 0 removes 10.
- No leg separates land and buildings from machinery, wells or networks. Fires are E&P (MUR, MXC, 4 energy services), cable/telecom (LBTYA/B/K 3 classes, TDS, NUVR), a tyre maker (GT), paper (CLW), textiles (UFI) and chemicals (6). Heavily depreciated *plant* is the opposite thesis: old equipment usually carries less value than book, not more. LOOSE (thesis mismatch).
- MXC shows an accumulated-depreciation ratio of 1.156 (> 1, impossible; full-cost depletion). GURE has op margin -171% and passes on FCF > 0 with `_not_melting`. 4 fires are below $50m.

Coverage: ppe_gross NaN 90% (US 29%); all 34 fires are US.

Fire check: none clearly embodies owned real estate. CYAN (farm-land algae facility) is closest.

Severity: LOOSE.
Fix: use the EDGAR `LandAndBuildings` / `Land` concepts (land >= 10% of mcap), or restrict to retail/hospitality/industrial-owner industries. Drop ratios > 1.

## arch_mb_fallen_deep_value (974 fires, median mcap $111m)

Intent (L7514-7520, L7550): the multibagger study's own state, "fallen + deep value" (lift 2.5x / 3.4x), explicitly "better-loaded lottery tickets".

Code (L7526-7550): `_mb_base` removes 2,194 of 3,168. Fallen (`ts_dist_hi260 <= 0.40`) removes 1,660. `_mb_deep` (EV/EBIT <= 6 | P/B <= 0.7 | P/S <= 0.3) removes 2,410. It matches the study definition.
- The deep leg is mostly P/B and P/S: P/B 683, P/S 538, EV/EBIT only 124. ev_ebit is NaN for 37% of the base. P/S <= 0.3 is not cheap for 0-2% margin businesses: JD (op 0.2%, EV/EBIT 47, two lines), VW 3 lines (nde 11), Nippon Steel. 230 fires pass on P/S alone.
- No survival or operator floor: 187 fires have op < 0 and FCF < 0; 44 fail `_not_melting` (UBI.PA op -149%, ASTL -51%, 601238.SS); 52 have negative equity; 250 have nde > 5. That is consistent with "lottery ticket", but `mb_fallen_stressed` already holds the stressed population, so the two overlap.
- Venue skew: KR 255 against JP 42. Korean P/B < 0.7 is structural.

Coverage: within the base, ev_ebit NaN 37%, pb 3%, p_s 6%.

Fire check: 128540.KQ Ecocab (op 16%, FCF 19%, P/B 0.36, 9% of 5y high), 1765.HK Hope Education (EV/EBIT 1.2) and 9922.HK fit. UBI.PA, Aprogen KIC (op -76%) and VW (3 lines) are lottery tickets at best.

Severity: OK as a raw study state; LOOSE as a screen (P/S path on thin-margin names; no melt guard).
Fix: add `_not_melting` (weights are already demoted). Require P/S <= 0.3 only with gross margin >= 20% or op >= 0.

## arch_mb_fallen_ignored_believers (377 fires, median mcap $280m)

Intent (L7615-7617): "few analysts, but those few are buyers, and no dividend yield propping the name up."

Code (L7618-7621): implemented as stated. Analysts 2-5 removes 429; fallen removes 869; buy share >= 0.6 removes 187; dividend <= 2% removes 102 (NaN-permissive; 208 fires have dividend NaN).
- `sent_n_analysts` is NaN for 44% of the base: JP 40% covered, CN 36%, KR 26%, against UK 89% and CA 85%. TIGHT. Fires are US 154, CN 80. The OTC-line issue appears in 2 fires: ADYEY with 3 analysts (Adyen has 35), NSANY with 3 (17).
- Buy share is coarse at n = 2-3: 271 of 377 fires sit at exactly 1.0. 104 names were removed by the clinical-biotech scrub.
- No operator floor: 100 fires have op < 0 and FCF < 0 (NXXT op -51%, DFLI -44%, CXL.AX FCF -143%). SPWR, the renamed post-bankruptcy SunPower, fires as "fallen" on a pre-rename price high.

Fire check: 0148.HK Kingboard (3 analysts, 100% buy, op 21%), SBC Medical and BUB.AX fit. ADYEY and NSANY do not (heavily covered).

Severity: TIGHT (analyst-feed coverage), otherwise OK.
Fix: borrow the max analyst count across same-issuer lines. Require n >= 3 for the buy-share leg.

## arch_mb_preprofit_freefall_informed (672 fires, median mcap $285m)

Intent (L8721-8726): pre-profit population, "fallen 88%, 8 weeks off the 5-year low, P/S 0.30, insiders 30%, activist 45%, headcount SHRINKING".

Code (L8697-8727): `_mb_base & _seg_preprofit & _mb_fallen & _informed_g`. Informed removes 904; fallen removes 973; pre-profit removes 630.
- `_informed_g` includes `_inst_arrival = fmp_inst_new_q0 >= 1`, meaning one new 13F holder. That is **true for 76.9% of the US base** (1.6% outside the US). **465 of 672 fires pass via it, and 99 only via it**; the median fire has 24.5 new holders: RBLX, U, EL, SMCI, RIVN. `_corp_conviction` (FY buyback > 1% or a shrinking count) is the only path for 186. The study's informed buyers (insiders 2+ quarters, 13D) account for 117 and 185. For US names "informed" is a no-op. **BUG.**
- `_seg_preprofit = op < 0 | fcf < 0`, so capex-heavy profitable firms count as "pre-profit": **150 fires have op >= 0 with negative TTM FCF**, and 30 have op >= 10%: LULU (op 17%), CZR, TREX (op 25%), CAR, YETI, ACHC, VWAGY (op 4%). LOOSE.
- "8 weeks off the 5y low" is not gated (fire median is 39.5 weeks since the low; 150 are within 8 weeks). Headcount is not used. 144 fires have NaN spirit.

Coverage: fmp_inst_new_q0 NaN 79% of the base (US 13F only); insider feeds 80-84% NaN. Fires: US 466, CN 80.

Fire check: ARAY (op -7%, 4% of 5y high, insiders net +$154k), FLUX and TOMZ fit. LULU, TREX, CZR, RBLX and VWAGY do not.

Severity: BUG (inst-arrival leg is near-universal for US), LOOSE (pre-profit includes profitable negative-FCF names).
Fix: require `fmp_inst_new_q0` above the base's 80th percentile (or a 13F ownership increase >= 5pp). Define pre-profit as `op_margin < 0` (or EBIT TTM < 0).

## arch_weschler_levered_equity (201 fires, median mcap $177m)

Intent (L6069-6082): a levered equity stub "cheap on ROBUST cash (Lindy)", EBITDA "stable/rising", "AMORTISING".

Code (L6097-6123): heavy_debt removes 663; `tc_min_ic >= 1` removes 268; robust cash yield removes 92; net debt not rising removes 72.
- The stable/rising leg admits **87 of 201 fires with EBITDA down YoY** through `season_robust`: MS Autotech -73%, Photon Energy -64%, Pavonine -62%, B&M -20%, BBWI -13%. LOOSE.
- Holdco consolidation: ALMENDRAL.SN (#1 by spirit; FCF yield 76%, EV/mcap 7.7) consolidates Entel, and CGO.TO Cogeco (FCF 81%, EV/mcap 12.7) consolidates Cogeco Communications. Consolidated FCF over the parent's own mcap ignores minorities. KCAR.BK, a car-rental lessor at FCF 78%, is lease-funded. 27 fires have FCF yield > 50%. LOOSE / BUG-adjacent.
- The amortisation proof is NaN-permissive: net debt change NaN on 93, IC NaN on 91, tc_min_ic NaN on 74.
- Overlap: oak_deleveraging 37, xr_paydown_yield 37, levered_inflection 21.

Fire check: BLC.PA (FCF 36%, nde 2.4, net debt -17% of assets), D01.SI Dairy Farm, BBWI and 4175.TWO fit. Almendral, Cogeco, KCAR and MS Autotech do not.

Severity: LOOSE.
Fix: require `ebitda_yoy >= -0.05` where measured. Cap FCF yield at 0.40, or require `minority_interest/equity < 0.3`.

## arch_levered_inflection (164 fires; watch 379; median mcap $128m)

Intent (L6164-6170): "a heavily-levered equity stub whose operating economics are inflecting and DELEVERAGING, priced cheaply and beaten down".

Code (L6180-6196): cheap removes 269; the core nde 1.5-3 band removes 196; beaten down removes about 119 (proxy); EBITDA rising removes 107.
- The core (`_tier`, L6196) keeps only ND/EBITDA 1.5-3x ("the source's own band") and moves **215 heavier stubs (nde 3.6-76, median 4.4) to watch**. The tradeable archetype is therefore "moderately levered" and contradicts its headline "heavily-levered equity stub". Core EV/mcap has a median of 1.65, and 16 fires sit below 1.3x (little torque). COSMETIC / LOOSE.
- `oper_lev_any` removes 0, since `strong_op_improvement` subsumes it (a dead leg). 58 of 164 fires (35%) also fire oak_deleveraging.
- EBITDA growth artifacts reach the top: 2442.TW Jean Co EBITDA +513%, MODINATUR.BO +601%.

Fire check: 010770.KS Pyung Hwa, 012280.KS, KBR and DOO.TO fit a moderately levered inflector. Jean Co and EQ4.F do not (no panel; growth artifact).

Severity: COSMETIC (headline vs core), LOOSE (overlap; dead leg).
Fix: rename the core to "moderately levered inflection", or keep nde 1.5-6 in the core with EV/mcap >= 1.5. Drop `oper_lev_any`.

## arch_bottleneck (1,149 fires, median mcap $2.2B)

Intent (L8838-8844): "durable HIGH + non-eroding gross margin (pricing power), high returns on capital (a toll road), and CAPITAL-LIGHT economics".

Code (L8846-8860): ROCE/lindy >= 15% removes 861; `tc_min_gm >= 40%` removes 756; capex <= 10% removes 236. The "GM not eroding" leg removes **12** (a near no-op once tc_min_gm is gated).
- GM >= 40% with ROIC >= 15% is generic quality, not a chokepoint. 148 fires are restaurants or apparel (OOTOYA, a restaurant at GM 58%, op 6%), plus household products. Overlap with buyback_compounder is 230 and with capital_light_pivot 225. LOOSE (thesis is broad).
- **GM = 100% from missing COGS (26 fires) wins the ranking.** The top spirit names are royalty trusts VOC, MVO and MSB, and PLANVITAL.SN, a Chilean pension-fund administrator (a financial) with blank sector and industry. The trusts have `tc_min_gm` NaN while tc_years is 8, so the through-cycle check passes. 87 fires have tc_years < 5; capex intensity is NaN for 154. BUG-adjacent (data).

Coverage: gross_margin NaN 27%; tc_min_gm 29%; roce 40% (roic_lindy fills).

Fire check: Bioventix (GM 91%, tc_min 91%), WINA, NVDA, ASML and 2148.T fit. VOC, MVO, MSB, PLANVITAL, OOTOYA and NTCP.JO (FX) do not.

Severity: LOOSE.
Fix: require `gross_margin < 0.999` and `tc_min_gm` measured when tc_years >= 5. Exclude trusts/royalty (name regex) and blank-sector financials. Add a pricing-power trend (GM vs tc_med) or an industry-rank leg (top quintile GM within industry).

## arch_nol_shell (19 fires, median mcap $34m)

Intent (L9164-9169): "large NOL carryforward relative to market cap (a monetizable tax asset — WMIH/Mr. Cooper), on a survivable balance sheet... a SHELL is cash-backed."

Code (L9170-9179): NOL/mcap 0.5-20 removes 5,094 of 5,113. Net cash >= 10% | cash_gt_ev removes 102. op > -30% removes 21.
- The stale `cash_gt_ev_flag` admits **CETX with net cash -142% of mcap**. BUG (shared).
- There is no Section 382 guard, unlike the sibling xr_monetization_trifecta (`~(shares_yoy > 0.05)`, L5414). **8 of 19 fires grew shares > 5%**: FIEE +124%, MODD +85%, RYES +29%, NXPL +29%. An ownership change caps the NOL. LOOSE.
- `op > -30%` reads zero-revenue explorers and devices (RYES, SVBL, LTUM, MODD; op margin 0.000 on revenue 0) as "survivable". The NOL is gross, not tax-effected; 0.5x is about 10% of mcap in tax value. That is acceptable but undocumented in the gate.

Coverage: nol_usd NaN 94% (US 15%); all fires are US.

Fire check: KODK (NOL $2.2B against $0.9B mcap, net cash 21%, FCF 51%), GHG, RGP, BOSC and IDN fit. CETX, FIEE, MODD and RYES do not.

Severity: BUG (stale flag), LOOSE (no 382 guard).
Fix: drop the `cash_gt_ev` OR-leg (or recompute it). Add `~(shares_yoy > 0.05)` and `revenue_ttm_usd >= 1e6`.

---

## Summary

| archetype | fires | severity | one-line fix |
|---|---:|---|---|
| arch_roic_inflect | 1,079 | BUG | Cash-ROIC cross as confirmation only; 522 fires (48%) are perpetual-positive-ROIC names (VRTX, Nintendo, Lenovo) on a one-year FCF dip |
| arch_hidden_assets | 1,955 | BUG | Require assoc/LT-investments >= 10% of mcap (1,929 of 1,955 fires have no stake line, so this is a net-cash screen); cap at 1.5x |
| arch_xr_paydown_yield | 444 | BUG | Convert financing_cf with the reporting-to-USD bridge (TLK 1,370x, PTGCF 5.7x, SCVPY 3.1x; 15 of 30 USD-line fires fail at the true ratio); require nde >= 1 |
| arch_mb_preprofit_freefall_informed | 672 | BUG / LOOSE | inst_arrival (>= 1 new 13F holder) is true for 77% of US base: raise it to top-quintile new holders; pre-profit = op < 0 (150 profitable negative-FCF fires: LULU, TREX) |
| arch_discounted_vehicle | 1,251 | BUG / LOOSE | Recompute cash > EV today and cap net cash <= 1.0x (83 fires > 100% mcap, 18 with net debt via the stale flag); require op or FCF > 0 |
| arch_buyback_compounder | 1,163 | BUG / LOOSE | Add mcap > 0 (59 dead lines incl. SWMA, FLIR); block 3y issuance on the buyback-yield leg (Celltrion +67%); restore an equity > 0 guard |
| arch_capital_light_pivot | 2,105 | BUG / LOOSE | Add mcap > 0 (66; top spirit EVTN, CLCN); measure capex intensity (TSMC, MU, Tencent fire); clip roic_acceleration |
| arch_nol_shell | 19 | BUG / LOOSE | Drop the stale cash_gt_ev leg (CETX at -142% net cash); add a shares_yoy <= 5% Section 382 guard (8 of 19 fail) |
| arch_customer_float | 1,514 | LOOSE | Drop total-NWC-only path (380 fires with positive CCC: PM 254d, NOVN 117d) |
| arch_wolf_turnaround | 676 | LOOSE | Remove EBITDA-growth path; require prior-FY loss (245 fires carry no turn flag) |
| arch_oak_deleveraging | 422 | LOOSE | Require EBITDA not falling (177 fall) and FCF >= 8% beside the OE lens |
| arch_dta_reversal | 177 | LOOSE | Require pretax income > 0 and sustained EPS; drop ROCE OR-leg (108 fires NI <= 0) |
| arch_xr_cannibal_below_cash | 34 | LOOSE | Finance regex regardless of sector (RBKB bank, CTT bank deposits, Jet2 deposits) |
| arch_xr_contracted_backlog | 90 | LOOSE | AND the price legs and add RPO growth (GEV EV/EBITDA 96, SNDK pass) |
| arch_xr_owned_realestate_value | 34 | LOOSE | Use land/buildings concepts; current fires are depreciated plant (E&P, cable, tyres) |
| arch_weschler_levered_equity | 201 | LOOSE | EBITDA not falling (87 fall); cap holdco-consolidated FCF (Almendral, Cogeco) |
| arch_bottleneck | 1,149 | LOOSE | Exclude GM = 100% / no-COGS (royalty trusts and a pension administrator top the spirit) and require industry-relative GM |
| arch_mb_fallen_deep_value | 974 | LOOSE (by design) | Add `_not_melting`; P/S path only with GM >= 20% |
| arch_xr_pre_scale_margin | 153 | LOOSE (minor) / COSMETIC | Size or EV/GP cap (AMZN passes); remove the dead gap leg |
| arch_kullamagie_breakout | 284 | TIGHT / LOOSE | Drop global leader gate where in-market RS exists (removes 348 of 632); tight = ts_tight5 <= 0.15 |
| arch_geographic_global | 696 | TIGHT / LOOSE | Fill from fmp_geo_count (94% of fires US); add largest-region share <= 60% |
| arch_mb_fallen_ignored_believers | 377 | TIGHT | Analyst coverage 44% NaN in base (KR 26%, CN 36% covered); borrow sibling-line counts |
| arch_levered_inflection | 164 | COSMETIC / LOOSE | Core nde 1.5-3 contradicts "heavily levered stub" (215 heavier stubs in watch); dead oper_lev_any leg |
