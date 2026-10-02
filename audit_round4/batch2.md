# Archetype review, round 2, batch 2 (23 archetypes)

Method: `archetype_tags.compute()` was run read-only from a scratch copy (`scratchpad/at_dump.py`, output writes removed; dump kept in /dev/shm only) so every gate leg could be evaluated on the exact frame and locals the pipeline uses. All 23 dumped `arch_*` columns match the published archetype_tags.csv exactly (23/23, 0 differences). Each gate below was then rebuilt leg by leg from that frame. The rebuilds match the published column exactly once the post-gate scrubs are applied: non-common, clinical biotech, EBITDA>revenue, corrupt price, sub-$2M shell and price-ghost; reinvest_inflect also gets the cash-burner scrub, and lindy_margin/low_sbc_quality get the rev_yoy>5 spike scrub. Universe N = 46,526; operating 36,173; "oper>=10m" = operating with USD mcap >= $10m (25,468). "Removes X of Y" = of the Y names that pass every other leg, this leg alone removes X. Scripts: scratchpad/r2_load.py, r2_a..r2_h.py, r2_x.py, r2_y.py; outputs r2_*.out.

Shared facts used below:
- The batch-1 facts still hold. `ev_ebit` is NaN for 59.7% of the universe and 45.4% of oper>=10m; it is present for only 21% of US oper>=10m names. `tc_years` is capped at 8 (29,638 names sit at 8), so `prof_share >= 0.90` means "no loss year on file" (every g_strong passer has prof_share = 1.0).
- Duplicate listing lines fire side by side. Fires whose normalised name already fired on another line: kpi_threshold 330, low_sbc_quality 397, negative_ev_value 293, lindy_margin 257, bab_becoming 164, cannibal_at_discount 84, wolf_seal 75, reinvest_inflect 68, cash_leads_book 65, confluence 60. Frankfurt `.F` lines and OTC F/Y lines also carry unit errors of their own: TSFA.F has EV/EBIT 179, and NAPRF carries mcap $206B and r52 -87% while NPN.JO has $32.8B and -41%.
- EDGAR-only inputs cover essentially nothing outside the US among oper>=10m names: `seg_mix_uplift` US 3% and 0% elsewhere; `inv_remark_*` US 10% and 0% elsewhere; `sbc_pct_revenue` US 26%, JP 1%, CN 2%, IN 2%.

## arch_gayner_pay_up_quality (66 fires, median mcap $8.1B, 32 > $10B)

Intent (l.8122-8128): "lenses 1-3 at their strongest (lindy ROIC and ROIIC >= 15%, a record of >= 7 years, revenue compounding >= 8%/yr) and the FOURTH lens deliberately failed — EV/EBIT ABOVE its market's median ... but no more than 3x it".

Code (l.8129-8135; helpers l.8061-8110):
- `_g_strong` (l.8124): roic_lindy >= .15, roiic >= .15, years >= 7, prof_share >= .90, rev5 >= .08. Among the 527 names passing every other leg it removes 461; roic removes 114, rev5 23, roiic 8, prof_share 3. `years >= 7` removes 0, so it is a no-op (29.6k names are at the cap of 8). prof_share >= .90 means no loss year in 8.
- `_g_lens2` (talent and integrity) removes 71 of 137. Its NaN-permissive legs (`~(x < 0.6)`, `~(sbc > .05)`) pass the 49-73% of names where those inputs are missing. Talent is never passed through the both-NaN path: 0 fires.
- `_g_lens3` removes 0 of 66. It is implied by `_g_strong` (roiic >= .15 and rev5 >= .08 already satisfy its organic leg `roiic >= .12 & growth >= 5%`), and all 66 fires pass through that organic leg. Dead gate.
- `_g_not_cheap`: EV/EBIT in (median, 3x median] of the listing country. It removes 88 of 154. Fires sit at 1.03-2.71x the median (median 1.46x). The frame is the listing venue, so ASMLF (the US OTC line of ASML) is judged against the US median of 17.5 at 2.46x.
- `~(_g_sh3 > 0)` has zero tolerance and removes 58 of 124. A 0.04% creep in the share count fails, while names with no share data pass.
- Coverage: the ev_ebit hole removes 27 of the 299 names that pass every other leg. Most of them would fail the 3x cap anyway (Advantest has op margin 52%, ASPEED 53%). YETI ($2.9B) and Systena are genuine losses.

Fire check: LLY (ROIC 20%, ROIIC 60%, rev5 22%, EV/EBIT 24.8 vs 17.5), MSFT, ASML, OMAB.MX (op margin 55%), Force Motors, ESAB India, Lycopodium and ChemoMetec all fit "pay up for the compounding runway". 11 fires are duplicate lines.

Severity: OK, with COSMETIC findings: lens3 and the years leg are dead; zero-tolerance dilution; frame keyed on the listing line.
Fix: drop `_g_lens3` and `years >= 7` from the gate (or say they are implied), use a 0.5% share-growth tolerance, and frame cross-listed lines on the home-venue median.

## arch_kpi_threshold (3,329 fires, median mcap $259m, 193 > $10B)

Intent (l.1766-1798): a first-positive print on an "OPERATING-LINE crossing (EBITDA / NI / ROCE / EPS / TTM EBIT)", confirmed by a >= 2pp margin move or a real TTM drop-through.

Code (l.1805-1811):
- `_kpi_turn` (l.1792) removes 8,366 of 11,911 and is the binding leg. Fires and sole-leg fires by turn leg: ni_first_pos 1,441 (383 sole), roce_first_pos 1,247 (253), fqx_eps_turned 1,194 (704), ebitda_first_pos 971 (210), bs_ebit_turned 945 (289). Net income is not an operating line: of the 383 fires that rest on NI alone, 66 have op margin < 0 and 16 carry `earnings_oneoff_flag`. Across all fires, 261 carry `earnings_oneoff_flag`.
- `_kpi_confirm` (l.1799) removes 1,258 of 4,803. A ROCE delta >= 2pp or a gross-margin delta >= 2pp is enough, so 214 fires have both op-margin and EBITDA-margin deltas below zero.
- `_not_melting` removes 23 and `is_operating` 552. There is no current-profit floor: 787 fires have op margin < 0, 724 have ROCE < 0, and 324 have both.

Coverage: the annual first-positive flags are NaN for 6.8% of oper>=10m, fqx_eps_turned for 12.4% and bs_ebit_turned for 32.7%, so the gate reaches globally.

Fires: 3,329 is 13.1% of operating names >= $10m, which is broad for a "threshold crossing". Venues: US 920, CN 438, KR 277, JP 267, TW 216. 330 fires are duplicate lines.
- Bad fires: INTC (op margin -0.1%, ROCE -4.2%, EPS positive in 1 of the last 8 quarters; it qualifies through bs_ebit_turned and an op-margin delta of +16pp off a deeply negative base). 8269.HK (op margin -28%, rides a ROCE first-positive of 0.69). HRME.JK (op margin NaN, revenue -3.7%, op and gross margin deltas -13pp and -4pp).
- Fit: MU (TTM EBIT turned, op margin 66%), SNDK, INOV.JK.

Severity: LOOSE.
Fix: require the operating line positive now (`op_margin > 0 | fqx_ebit_ttm > 0`), count `ni_first_pos` only alongside an op-line turn, and veto `earnings_oneoff_flag == 1`.

## arch_lindy_margin (1,202 fires, median mcap $4.4B, 422 > $10B)

Intent (l.2034-2047, tightened at l.2049-2062): "durable HIGH margin measured on the WORST year": tc_min_opm >= 15% over >= 3 years, or a statement-history median >= 20%, and the current margin >= 0.7x the through-cycle median.

Code: the watch rule (l.2002-2008) runs `_tier` with the core `_lm_core & _lm_still` (l.2063-2067).
- `measured = _min_opm_chain.notna()` is true for all 7,417 watch names, because the chain is back-filled from `fmp_st_op_margin_lindy`. The "unmeasured keeps the previous rule" path never fires. COSMETIC.
- Core: `_lm_core` removes 5,918 of the 7,417 watch names and `_lm_still` a further 268. 1,189 fires are judged on tc_min_opm and 13 on the 20% median fallback.
- The watch-rule caps `op_margin_lindy <= 0.6` and `ebitda_margin_lindy <= 0.8` were written for the old median rule and now contradict the worst-year thesis. Of the 1,206 operating names with worst-year margin >= 15% that are still durable, 86 do not fire: 56 through the 60% cap and 48 through the EBITDA band. They include Kweichow Moutai (worst year 68.7%), VeriSign (63%), Texas Pacific Land (72%), Evolution (36%), OBIC (51%) and Pro Medicus (53%).
- `ebitda_margin_lindy < op_margin_lindy` (impossible) holds for 3,801 universe rows, e.g. PBLOF at 0.0, so the EBITDA band reads bad data.
- 130 fires have op margin NaN and pass `_lm_still` because the leg is NaN-permissive.

Coverage: tc_min_opm is NaN for 17.8% of oper>=10m. Venues: US 454, CN 126, IN 86, JP 77.

Fires: NESCO.NS (worst year 47%), GTT, eMemory, Nihon Falcom, NVDA (worst 15.7%), AAPL, GOOG and Anhui Expressway all fit.

Severity: TIGHT (the caps drop the best durable-margin names), COSMETIC (the `measured` path is dead).
Fix: apply the 0.6/0.8 caps only when tc_years < 5 (or drop them for tc_min_opm >= .15), and use ebitda_margin_lindy only where it is >= op_margin_lindy.

## arch_reinvest_inflect (633 fires, median mcap $1.4B)

Intent (l.2506-2508): "ROIIC accelerating from a positive base AND assets actually growing".

Code (l.2512-2520):
- `roiic_acceleration in [.05, 1]` removes 2,084 of 2,720 and is the binding leg. The input comes only from the FMP statement fill (all 633 fires are `fmp_st` fills) and is NaN for 69.3% of oper>=10m names. Present share by venue: US 13%, UK 11%, DE 10%, JP 34%. TIGHT.
- roiic in [.05, 1] removes 291, roic_lindy >= .05 removes 212, asset growth >= 5% removes 154, and `~(fqx_ebit_ttm_g < 0)` removes 121 (NaN-permissive: 51 fires have no TTM read).
- There is no mcap floor and no `_not_melting`. 26 fires have mcap NaN or 0 and 13 are below $10m (BETXIND.BO, $8m). The downstream cash-burner scrub removes 3 more (YIBO, LMG.V, 4499.T).
- 61 fires have revenue down YoY.

Fires: TSFA.F (the Frankfurt TSMC line), CATL, Rio Tinto (RTNTF) and Thomas Scott fit. Vinati Organics sits on the floors (ROIIC 5.4%, acceleration 5.5%).

Severity: TIGHT (coverage of the acceleration input), LOOSE minor (no size or melt guard).
Fix: add `mcap >= 10e6 & _not_melting`, and fall back to `fqx_roic_slope8 > 0` where the annual acceleration is missing.

## arch_financials_value (271 fires, median mcap $742m)

Intent (l.3187-3198): banks and insurers cheap on book (P/B < 1) with ROE >= 10%. "a P/B<1 ... on a closed-end fund / BDC ... is a discount-to-NAV whose 'ROE' is just the distribution rate. Those are NAV vehicles ... not book-value-cheap operating financials."

Code (l.3200-3206):
- `_fin_fund_vehicle` matches only the industry string. Closed-end funds are labelled "Capital Markets", so they pass. 47 of 271 fires (17%) are unlevered vehicles with equity/assets >= 0.85, 43 of them in Capital Markets. The top four by spirit are all funds: MXF (The Mexico Fund, "ROE" 28.9% = market return), SOR, CET and FFA. Others include BOE, LGI, GAM, CII, GAB, BDJ, GDV and EMF (EMF "ROE" 50%). 64 fires have fund, trust, income or investors in the name. These fires contradict the archetype's own comment. BUG.
- pb in [.15, 1) removes 835 of 1,106 and roe >= .10 removes 557. The `p_e <= 15 or NaN` leg removes 4: it is a near no-op, because P/B < 1 with ROE >= 10% already implies P/E <= 10 (the book-implied P/E of the fires is at most 9.8).
- Dundee (DDEJF and DC-A.TO, both lines) fires with ROE 55% from a one-off.

Coverage: ROE is NaN for 27.7% of the financial pool (US 920 of 2,526 = 36%).

Fires: CMB (CIHHF and CIHKY, two lines), BNP, Banco Sergipe, Community Bancorp and Aeon Credit fit.

Severity: BUG (funds admitted against the stated thesis).
Fix: exclude `fq_equity / fq_total_assets >= 0.8` (no balance-sheet leverage means NAV vehicle) plus a name regex `fund|trust|income`, and drop the redundant P/E leg.

## arch_low_sbc_quality (1,900 fires, median mcap $4.1B, 613 > $10B)

Intent (l.2180-2184): "clean accounting (SBC < 2% of revenue) AND genuinely profitable"; the (fresh) comment makes SBC presence mandatory.

Code (l.2189-2199):
- The SBC leg removes 6,469 of 8,371 and is the binding leg. `sbc_pct_revenue` is EDGAR-derived and NaN for 72.7% of oper>=10m (JP 1%, CN 2%, IN 2% present). The `roic_after_sbc ~ roce` fallback is NaN for 87.7% and carries 8 fires.
- `fmp_sbc_to_revenue` (82% present) and `fq_sbc_pct_revenue` are not used. With them, 5,427 more operating names would pass every leg. Venues today: US 1,151 of 1,900 (61%).
- roce >= 8% removes 845 and the dilution cap removes 324. 40 fires have ROCE >= 100% and 56 have EBITDA margin >= 60% (royalty and one-off profiles; no `_roce_oneoff_suspect` guard).
- 397 fires are duplicate lines (e.g. TSFA.F next to TSMC's home line).

Fires: LLY (SBC 0.8%), WMT, Simcere, DXPE and Adient fit.

Severity: TIGHT (coverage: a US screen in practice).
Fix: `sbc = sbc_pct_revenue.fillna(fq_sbc_pct_revenue).fillna(fmp_sbc_to_revenue)` and add `~_roce_oneoff_suspect`.

## arch_bab_becoming (2,759 fires, median mcap $833m, 427 > $10B)

Intent (l.2725-2731): "the within-market 1-year beta rank has fallen >= 10 points below the 3-year rank, or 1-year volatility < 0.85x the 3-year ... from a not-yet-low 3-year beta" (becoming low-beta, the BAB long leg).

Code (`_reframe` at l.2752; `_compress` at l.2738-2741):
- `_compress` removes 8,368 of 11,127. Fires by leg: beta-rank drop only 1,591, vol ratio only 602, both 566.
- Nothing requires the 1-year beta to be low now. 1,261 fires (46%) still have a 1-year rank above 0.5 and 627 above 0.65, e.g. NVDA moving from 0.95 to 0.83 and AAPL from 0.77 to 0.65. 285 fires qualify on the vol-ratio leg while their beta rank rose.
- 342 fires have `ts_beta_1y <= 0`. The file's own bab_low_beta comment calls a non-positive panel beta "a non-trading artifact" (l.2690), but `_compress` checks only `ts_beta_3y > 0`.
- There is no liquidity guard. bab_low_beta uses `_bab_liquid`; here 586 fires have dvol < $250k.
- The spirit then ranks these artifacts first: 22 of the top 50 have a negative 1-year beta. AZTEF (TV Azteca, in default proceedings: beta 2.98 to -0.55), BGUUF (vol_3y 363%) and LECBF (vol_3y 680%) lead.
- The vol-ratio market median is taken over all lines, financials included (US 0.959 vs 0.982 for operating names only). Minor.
- The NaN-to-0 fills on fcf_margin and rev_yoy pass 76 and 85 fires respectively.

Coverage: ts_beta_3y_rk is NaN for 13.2% of oper>=10m.

Fires: KSK and Tokyo Radiator are plausible. NVDA, AAPL, TSFA.F and AZTEF are not "becoming safe".

Severity: BUG (artifact betas lead the spirit), LOOSE (no "now low" condition, no liquidity guard).
Fix: add `ts_beta_1y > 0 & _bab_liquid & (b1 <= 0.50)`.

## arch_wolf_seal (1,682 fires, median mcap $97m)

Intent (l.3601-3612): "an earnings inflection bought on a post-earnings dip ... the SEAL is an EARNINGS inflection: a first-positive print, a shock-sized margin move or a dated EPS turn".

Code (l.3616-3625):
- `mom >= .10` removes 2,712 of 4,394, the cheap leg 882, `_seal_inflect` 539 and `not_too_deep(.5)` 102.
- Seal legs among fires: margin_shock_any 1,504 (873 sole), first-positive 564 (74), eps_turned 312, bs_ebit_turned 145. Of the 873 margin-shock-only fires, 296 have no P&L margin lens >= 2pp (they pass only on TTM EBITDA/CFO-minus-revenue or flow-through), and 88 pass on gross margin alone. Examples: the top-spirit fire CNT.BK (op margin 1.7%, +1.1pp, P/E 14.5 but EV/EBITDA 16.1), Denyo (+0.3pp) and Espec (-1.1pp).
- The dip is a spirit weight, not a gate. Only 189 fires show a negative last reaction (1,172 have none on file), 328 sit at >= 95% of the 52-week high, and 220 are up more than 100% on the year.
- Data: DWWEF has `ts_r52` = 124.0 (+12,400%) against momentum_12m of -17%. The panel value is preferred, so an artifact passes the momentum leg.

Coverage: ev_ebitda and p_e are NaN for 27% and 35% of oper>=10m. Venues: JP 351, IN 198, US 197, KR 136, TH 114.

Severity: LOOSE.
Fix: require a P&L margin move >= 2pp or a dated turn (drop the TTM-only shock lenses), require `ts_dist_hi52 <= 0.90` where the panel exists, and veto `ts_r52` when its sign disagrees with momentum_12m.

## arch_oak_asset_floor (1,282 fires, median mcap $33m)

Intent (l.3855-3863): "the author's test is mcap <= cash + tangible assets: net cash >= 70% of mcap at/below tangible book, or NCAV covering the cap; the old 40% / 80% / pb < 1.5 rule is surfaced as oak_asset_floor_watch".

Code (l.3859-3874):
- The floor leg removes 5,979 of 7,261. Fires by floor leg: NCAV >= 1 688, net cash >= 70% with P/TB <= 1 478, and `(net cash >= 40%) & cash_gt_ev` 586, of which 331 sole.
- The third leg is the old 40% rule the comment says was retired, with no tangible-book test. "cash > EV" works out to roughly net cash >= 50% of mcap.
- Bad fires through that leg: 84 of the sole fires have NCAV < 0.5; across all fires, 28 have negative NCAV. KNO.AX ($4.8m) has net cash 84% but NCAV -7% and op margin -18%. 600218.SS has net cash 59% and P/TB 1.02.
- 402 fires hold cash > mcap. The G2 comment calls this "a shell/holdco artifact" for operating value theses, but there is no `net_cash_pct_sane` here.
- 21 fires are FX-incoherent; this archetype has no `_fx_coherent` guard.

Coverage: p_tb is NaN for 33% and ncav_pct_mcap for 27% of oper>=10m. Venues: JP 249, KR 214, HK 204, US 150.

Fires: Taekwang (net cash 167%, P/TB 0.16) and Moatech (NCAV 1.9x) fit.

Severity: LOOSE.
Fix: drop the third leg or add `p_tb <= 1.0` to it, and add `_fx_coherent`.

## arch_expensed_growth_value (216 fires, median mcap $74m)

Intent (l.4192-4198): "Companies expensing R&D/brand/customer-acquisition show BOTH a thin op margin and an understated book ... FAT gross margins ... with a thin op margin, while revenue grows".

Code (l.4205-4216):
- rev_yoy in [.1, 1] removes 994 of 1,210, GM in [.40, .98] removes 459 and GP/mcap >= .5 removes 362. Nothing measures expensed growth spend.
- Of the 203 fires with an R&D read, 175 have R&D below 2% of revenue (median 0). Top industries are restaurants (18), telecoms (16), software (15), household products (11) and steel/textiles.
- In the IN and JP filings, "gross margin" is revenue less materials. SAIL.NS (Steel Authority of India) shows a 50% gross margin, so the "fat GM" leg measures a reporting convention.
- The top spirit fires are cash cows, not reinvestors: POLYSPIN.BO ($3m, FCF yield 97%), ZUC.MI (87%), NPI.MI (85%), MUL.BO (66%). 45 fires have FCF yield >= 15%. GP/mcap reaches 34.8 at the maximum.

Coverage: inputs are 9-21% NaN, so this is not a coverage problem.

Severity: BUG (the gate measures a different fact from the thesis).
Fix: require the spend, i.e. `(fmp_rd_to_revenue + fq_sga/fq_revenue) >= 0.25`, rank GM within industry (not absolute), and cap `fcf_yield < 0.10`.

## arch_cannibal_at_discount (673 fires, median mcap $389m, 41 > $10B)

Intent (l.4401-4412): "Management retiring stock BELOW BOOK ... net shrinkage is the FACT that matters".

Code (l.4418-4427):
- `_shrink_f12` removes 5,005 of 5,678 and P/B < 1 removes 1,913.
- The shrink leg reads only master `shares_yoy` (598 fires; 75 more through the buyback leg). The quarterly count disagrees: 135 fires show `fq_shares_yoy > 0`, and for 44 the FY diluted count (`fg_shares_dil_g1`) also rose.
- The top spirit fire, ODTech 080520.KQ, shows shares_yoy -12.9% but the quarterly count +6.2%, FY diluted +6.0%, ROCE -5% and NI NaN.
- 45 fires show <= -10% with no buyback yield. The -30% reverse-split guard does not catch them.
- 108 fires are .F or OTC lines, e.g. LYK1.F Parkmead (-10%, quarterly 0%, buyback 0). 48 fires are "profitable" only through FCF yield.

Coverage: shares_yoy is NaN for 21% of oper>=10m (fq_shares_yoy 23%).

Fires: CMCSA (-5.1% across all three lenses, P/B 0.996), Mercedes-Benz, Maersk and Kaneshita fit.

Severity: BUG (input contradiction admits issuers).
Fix: shrink = `fq_shares_yoy.fillna(shares_yoy) <= -0.02`, and veto when any present lens shows growth > 0.

## arch_xr_floor_inflection (719 fires, median mcap $35m)

Intent (l.4563-4567): "Priced at/below a HARD asset floor (net-net, deep net cash, or the hidden-asset gap) exactly as operating INFLECTION evidence appears (a first-positive print, or acceleration with operating leverage)".

Code (l.4565-4578):
- The floor leg removes 5,348 of 6,067. Its hidden-asset leg uses `_hidden_pct = (associates.fillna(0) + cash - debt) / mcap` (l.4065). `investments_associates` is NaN for 93.5% of oper>=10m, so the leg collapses to net cash, cut at 0.40 while the explicit net-cash leg demands 0.50. 103 fires are admitted only through this back door. BUG.
- The inflection leg removes 696 of 1,415. 395 of 719 fires pass solely through `rev_accel > 0 & oper_lev_any`, and oper_lev_any passes 67.8% of the universe, so in practice the leg is just `rev_accel > 0`. 160 fires have revenue down YoY (the decline merely slowed), 245 have op margin < 0 and 288 negative FCF.
- `beaten_down(.30)` removes 436.

Fires: JD and JDCMF are the largest fires. Each passes on net cash of 44-47% (via the hidden leg), an op margin of 0.2% that is falling, and an "inflection" that amounts to rev_accel of +0.06. SAIC Motor's net cash of 164% includes its auto-finance arm. Senshukai and Seiwa Chuo (NCAV 1.0-1.5, NI first-positive) fit.

Severity: BUG (hidden-pct fallback), LOOSE (the inflection is not one).
Fix: `hidden >= .40` only where investments_associates is present, and the inflection leg = first-positive, or `(rev_accel > 0) & (rev_yoy > 0) & margin_shock_any`.

## arch_xr_compounding_deployer (285 fires, median mcap $2.3B, 84 > $10B)

Intent (l.4708-4714): "high AUDITED incremental returns on capital actually DEPLOYED ... financed internally ... and the market pricing it at an ordinary multiple".

Code (l.4715-4727):
- roic_lindy >= .12 removes 560, roiic >= .20 removes 333, financing_cf <= 0 removes 155 and the growth leg 139.
- The cheap leg (removes 76) includes `evsg <= 0.40`. That leg alone admits 99 fires at EV/EBIT 14-179 (median 20.4): NVDA 26.1x, MSFT 21.3x, TSFA.F 179x (a unit error on the line). That is not "an ordinary multiple".
- The deploying leg accepts any acquisition above zero. 69 fires have capex below D&A and acquisitions under 1% of assets (50 under 0.2%). Gayner's version uses >= 2%.
- There is no ROIIC sanity band (reinvest_inflect and qarp cap it at 1.0): 7 fires exceed 1.0, NVDA at 1.04.
- 35 fires are duplicate lines.

Fires: NEDAP, Track & Field (EV/EBIT 9.1), LIMES and Mercedes-like industrials fit.

Severity: LOOSE.
Fix: evsg leg only with `ev_ebit <= 20`, `fq_acq_pct_assets >= 0.02`, `roiic_lindy <= 1.0`.

## arch_xr_confluence (924 fires, median mcap $112m, 38 > $10B)

Intent (l.6566-6576): "the once-in-a-lifetime meta-gate ... >= 3 DISTINCT families ... By construction the rarest flag in the book".

Code (l.6577-6620): the reconstruction from final family flags matches 924/924. 26 pre-scrub confluences were later scrubbed, consistently.

Findings:
- 924 fires is 2.6% of operating names, not rare.
- The dislocation family is effectively xr_quality_crisis: it accounts for 723 of the 825 fires with a dislocation and fires on 3,402 names universe-wide.
- In 114 fires the engine family rests on xr_peer_margin_gap alone (993 universe fires). In 41 the floor family rests on xr_floor_inflection alone, which is LOOSE above. In 34 the forensic family rests on cash_leads_book alone, also LOOSE below.
- Family combinations: floor+dislocation+forensic 293, dislocation+forensic+engine 228, all four 169.
- The largest fire is NAPRF (Naspers OTC line). Its mcap reads $206B against $32.8B for NPN.JO, and dist_hi260 0.12 against 0.54, so the line's dislocation is a price artifact. PROSF and PROSY, two lines of Prosus, fire separately.

Severity: LOOSE (the members' looseness compounds; the claim of rarity is false).
Fix: count xr_quality_crisis toward the dislocation family only with a second dislocation member or `ts_r52 <= -0.3`, require >= 4 families or exclude the broadest member of each family, and dedupe lines.

## arch_xr_growth_capex_masked (24 fires, median mcap $793m)

Intent (l.5288-5292): "capex >= 1.5x D&A, strong returns, CFO healthy, growing — and cheap on the MAINTENANCE cash take".

Code (l.5325-5336):
- `maint_y >= .07` removes 599 of 623 and `fcf_yield < .04` removes 207.
- `fcf_yield` is the zero-filled `s()`, so NaN passes "reported FCF suppressed": 4 fires, including 1742.HK, 9998.HK and 5OC.SI.
- Currency and units mixing between the audited D&A (`_dna_loc`) and listing-currency capex and CFO:

| Fire | capex / D&A (code) | Maintenance yield | Notes |
|---|---|---|---|
| MELI.BA | 2,197 | 28.1 (2,812%) | ARS capex over USD D&A; the quarterly panel says 0.71 |
| ERO | 193 | | D&A 1.5m vs capex 298m; quarterly 2.37 |
| VISTAA.MX | 28.3 | | its own VSOGF line reads 3.48 |
| 1742.HK | | 1.76 | SGD/HKD mix; quarterly capex/D&A 0.57 |
| 9998.HK | | 1.46 | SGD/HKD mix; quarterly capex/D&A 0.54 |
| 5OC.SI | | 2.23 | |

- The `_fx_coherent` twin test misses these lines.
- Three companies fire on two lines each (Vista, Okeanis, Korean Air) and one more on ERO and ERO.TO.
- At least 8 of the 24 fires are artifacts. Korean Air (ROCE 4.3%, revenue +42% from the Asiana merger) is acquisition growth, not growth capex.

Severity: BUG.
Fix: use `fq_capex_to_da` first (same-statement ratio) and the level D&A only when it agrees within 2x; require `fcf_yield.notna()`; cap `maint_y <= 0.5`.

## arch_xr_margin_mixshift (45 fires, median mcap $2.2B, 15 > $10B)

Intent (l.5495-5502): the fastest-growing segment earns a materially higher margin and is gaining mix, "gated to a cheap consolidated whole so the re-rate is unpriced".

Code (l.5508-5519):
- `seg_mix_uplift >= .05` removes 374 of 419. The input is EDGAR-only: 672 names in total (US 561). All 45 fires are US. TIGHT by construction, since FMP has no segment EBIT.
- The cheap leg is one lens in four (EV/S <= 3, EV/EBITDA <= 12, P/B < 2 or FCF yield >= 3%), and it removes 2. PM (EV/S 8.1), TMO (5.7) and DHR (6.5) pass on FCF yield. They are not "cheap consolidated wholes".
- seg_mix_uplift reaches 19.5 (1,950pp) on a tiny-revenue segment.
- 15 of 45 fires show consolidated op margin not expanding. That is acceptable, since the thesis says the expansion is not yet visible.

Severity: TIGHT (US-only), LOOSE (cheap leg).
Fix: require two cheap lenses or `ev_ebitda <= 12`, and clip the mix uplift to [0.05, 1.0].

## arch_xr_cash_leads_book (500 fires, median mcap $706m, 60 > $10B)

Intent (l.5741-5750): "operating cash flow runs ahead of net income AND is growing faster than it ... the TRAJECTORY — cash pulling away from book".

Code (l.5752-5759); the flag is built at l.779-784.
- The flag leg removes 8,591 of 9,091. `fq_cfo_growth_minus_ni_growth >= 0.10` compares growth rates, so it holds when NI falls faster than CFO. 368 of 500 fires have TTM NI down YoY (239 down by more than 20%), and 149 have CFO down as well.
- UNH: NI fell from $21.3B to $14.1B and CFO from $29.0B to $27.0B. That is collapsing earnings, not cash pulling ahead of a conservative book.
- The cheap leg removes 213. 333 fires have P/E > 15 and pass on FCF yield >= 6%, e.g. TRJA.JK at P/E 637 with CFO/NI of 409x on a near-zero NI.
- The flag is 0 (not NaN) where the quarterly panel is missing. Panel reach for oper>=10m: US 43% vs KR and TW 87%.

Fires: Deutsche Telekom (two lines) and COLL (CFO up 62% vs NI up 32%) fit.

Severity: LOOSE.
Fix: also require CFO growth > 0 and NI growth >= -10% (or CFO - NI widening in currency), and require `p_e <= 15` or `fcf_yield >= .06 & p_e <= 25`.

## arch_mb_fallen_stressed (971 fires, median mcap $299m, 23 > $10B)

Intent (l.7553 and the study comment at l.7517-7519): the study's state "fallen (>= 60% below the 5y high) & stressed balance sheet", with lift 3.1x fit and 2.7x test.

Code (l.7546-7553): `_mb_stressed` is `nde in [5, 90)`, equity < 0, net cash <= -100% of mcap, or debt-to-equity >= 2.
- Stressed removes 2,413 of 3,384, fallen 1,597 and the liquid base 1,872.
- Legs among fires: net debt >= mcap 574 (164 sole), nde 519 (178 sole), debt-to-equity >= 2 327 (94 sole), equity < 0 158.
- 28 fires have meaningful nde < 3, interest cover >= 3 and positive equity, and qualify only because debt is large against a depressed market cap. Example: the top-spirit fire TokyoTsushin (nde 0.5, cover 6.0, d/e 2.1).
- Captive finance reads as stress. Volkswagen fires on three lines (nde 11 from VW Financial Services debt), and 29 auto names fire in total.
- 130 fires have 3y share growth > 50%, so the fall is per share (dilution).

The archetype reproduces the study's state as written; the looseness lies in how the state is read.

Severity: LOOSE (minor).
Fix: exclude the size-relative legs when meaningful nde < 3 and interest cover >= 3, exclude captive-finance autos (or use industrial net debt), and add `~(shares_growth_3y > 0.20)` as the sibling fallen-angel rule does.

## arch_mb_tree_recipe (362 fires, median mcap $37m)

Intent (l.7639-7642): "within-country ranks — volatility top 40%, size bottom 13%, fallen top 17%, profitability bottom 46%: 16.7% ... led to a 3x within 24 months".

Code (l.7647-7661): the ranks are taken within the liquid operating base, matching the comment.
- size <= .13 removes 438, fallen >= .83 removes 255, prof <= .46 removes 168 (NaN op margin fails: 175) and vol removes 125.
- There is no per-share guard. The fallen-angel siblings use `~(shares_growth_3y > 0.20)`, but here 115 fires have 3y share growth > 50% and 82 > 100%.
- The spirit (-dist_hi260, vol, -mcap) ranks the dilution wreckage first: GPUS (shares +20,946%, dist_hi260 7e-8), NXXT (+9,146%), GFAI (+1,668%), AZEV4.SA (+671%).
- 240 fires have op margin < 0 and 73 below -50%. That is by design (bottom 46% profitability), but 43 fail `_not_melting`.

Fires: Tsudakoma, 2314.TW and the CN small caps fit.

Severity: LOOSE (the spirit ordering is dominated by dilution artifacts).
Fix: add `~(shares_growth_3y > 0.20) & _not_melting`, or rank the fallen leg on a per-share-adjusted drawdown.

## arch_xr_investment_remark (3 fires)

Intent (l.5801-5807): a JV or equity stake remeasured to fair value (the LanzaTech pattern), material against mcap.

Code (l.5813-5822): `gain_sized` removes 8 of 11. Every other leg removes 0 or 1. The input is EDGAR-only (2,987 names, all US).

Fires:
- LNZA, the reference case: carrying value $26m to $223m against mcap $80m. Fits.
- XNET: carrying value $1.07B against mcap $319m, but the value is dated 2025-12-31 (nine months stale), and carrying value plus quarterly cash ($0.28B) exceeds the latest total assets ($1.18B). Suspect, needs verification.
- CETX: $4m mcap, a $4.0m jump sized only by a non-operating gain of $3.5m, op margin -6%. Marginal.

Severity: TIGHT (US-only, 3 names), OK on logic.
Fix: require `inv_carry_now_end` within 6 months of the as-of date and `inv_carry_now <= fq_total_assets - fq_cash_sti`.

## arch_negative_ev_value (4,618 fires, median mcap $52m)

Intent (l.6297-6303): "The market cap is at or below net cash (negative or tiny EV — you are effectively PAID to own the operating business) OR the price is well below book".

Code (l.6312-6328):
- The branch leg removes 17,301 of 21,919. 3,360 of 4,618 fires (73%) come through the plain `pb < 0.7` branch with only `_not_melting` attached.
- Of those 3,360, 2,294 carry net debt, 1,600 carry net debt above 50% of mcap, 865 have op margin < 0 and 1,435 negative FCF. The largest fires are levered sub-book industrials: Kobe Steel (net debt 74% of mcap) and Hankook Tire (46%).
- The archetype therefore mostly duplicates tangible_value (1,464 shared fires) and oak_asset_floor (1,195).
- `cash_gt_ev_flag` disagrees with the master's own cash vs EV: 471 of the 1,733 flagged rows have cash <= EV (155 of them fire), and 2,802 unflagged rows have cash > EV.
- The top spirit names are shells: Awilco Drilling (no rigs, FCF -$13m, net cash 128%), RCR.AX ($5m, flag 1 with net cash 16%) and ABR.V.
- 293 fires are duplicate lines; 147 are FX-incoherent.

Severity: LOOSE (the sub-book branch dominates and contradicts the name), BUG (inconsistent flag input).
Fix: give the P/B < 0.7 branch its own archetype or require net cash >= 0 on it, and recompute cash > EV from `cash` and `enterprise_value` instead of the stale flag.

## arch_tenbagger_credible (605 fires, median mcap $108m)

Intent (l.6690-6699, l.6758-6766): a 10-year compounding at durable growth, a conservative terminal margin and an 18x multiple closes a 10x on the current P/S, plus real owner cash and a stable share count.

Code (path at l.6740-6756, credible at l.6782-6785):
- `implied >= 10` removes 849 of 2,139 path candidates, g10 removes 385 and the <= $1B cap removes 486. In the credible layer, stable shares removes 342 and owner cash 107.
- The arithmetic uses P/S, not EV/S (l.6702), even though the comment calls EV/S "the conservative proxy". 83 fires have net debt above their mcap. Hansol Holdings: P/S 0.12 vs EV/S 0.71 gives an implied 84.5x; on EV/S it would be about 14x. 521 of 605 would still pass on EV/S.
- `term_margin` floors at 6% net. 173 fires have op margin <= 4%, and 123 are modelled at >= 2x their current after-tax margin. The comment promises "its own (after-tax) margin plus a modest expansion".
- 86 fires are clamped at the 100x cap, and 118 sit at the g10 cap of 50%.

Fires: BLS International and Khaitan fit. TGNO4.BA (Argentine gas utility; ARS inflation inflates growth by 23-68%) and 300985.SZ (EV/S 4.6, op margin 4.9%) are stretches.

Severity: LOOSE.
Fix: use `ev_sales` where net debt > 0, set `term_margin = clip(max(own_net_margin * 1.5, ...), 0.04, 0.22)`, and deflate growth for high-inflation currencies (AR, TR).

## arch_spinoff_quality (1 fire: SOLS)

Intent (l.8977-8987): a high-return franchise spun at a fair multiple (SanDisk: ROCE .35, op margin .61, EV/EBIT 20).

Code (l.8998-9006):
- The spin population is 44 names, EDGAR Form 10 plus 9 from dated fmp_events, all US, 37 of them operating. ROCE >= .20 removes 4 of 5, op margin >= .15 removes 2 and undelivered removes 1.
- SNDK, the archetype's own exemplar, is excluded by `_spin_undelivered` (+189% in 6 months). That is consistent with the comment.
- HONA (Honeywell Aerospace) misses at op margin 14.7%. The when-issued lines HONAV and MFPVV sit in the universe unscrubbed.
- Zero-fill: `net_cash_pct_c >= 0` reads `s('net_cash_pct_mcap')` with NaN set to 0, so a missing balance sheet passes "sound balance sheet". 7 spin names are NaN; none fires today.

Fire: SOLS (ROCE 21%, op margin 18%, EV/EBIT 14.9) fits.

Severity: TIGHT (US-only spin feed), COSMETIC (zero-fill).
Fix: use `_ncol('net_cash_pct_mcap') >= 0` on the balance-sheet leg, add `when issued` to the non-common scrub, and widen the spin feed beyond EDGAR.

## Summary

| archetype | fires | severity | one-line fix |
|---|---:|---|---|
| xr_growth_capex_masked | 24 | BUG | use fq_capex_to_da first (level D&A only if it agrees within 2x), require fcf_yield notna, cap maint_y <= 0.5 (MELI.BA 2,197x, ERO 193x, VISTAA.MX 28x) |
| expensed_growth_value | 216 | BUG | require R&D+SG&A >= 25% of revenue, rank GM within industry, fcf_yield < 10% (175/203 fires have R&D < 2%) |
| financials_value | 271 | BUG | exclude equity/assets >= 0.8 and fund/trust names (47 CEFs incl. top-4 spirit) |
| cannibal_at_discount | 673 | BUG | shrink = fq_shares_yoy.fillna(shares_yoy) <= -2%, veto if any lens shows growth (135 fires contradicted, top spirit ODTech) |
| bab_becoming | 2,759 | BUG + LOOSE | require ts_beta_1y > 0, _bab_liquid, 1y rank <= 0.5 (342 negative-beta fires; 22 of top-50 spirit) |
| xr_floor_inflection | 719 | BUG + LOOSE | hidden leg only where associates present (103 fires via net cash 40-50%); inflection needs rev_yoy > 0 & margin_shock |
| negative_ev_value | 4,618 | LOOSE + BUG | separate or require net cash on the pb < 0.7 branch (73% of fires); recompute cash > EV from cash and EV |
| kpi_threshold | 3,329 | LOOSE | require op line positive now, NI turn only with an op turn, veto earnings_oneoff (787 op < 0 fires; INTC) |
| wolf_seal | 1,682 | LOOSE | P&L margin >= 2pp or dated turn; dist_hi52 <= 0.9; veto ts_r52 sign conflicts (DWWEF +12,400%) |
| oak_asset_floor | 1,282 | LOOSE | drop the retired 40% & cash > EV leg or add p_tb <= 1 (331 sole fires); add _fx_coherent |
| xr_compounding_deployer | 285 | LOOSE | evsg leg only with EV/EBIT <= 20; acq >= 2% of assets; ROIIC <= 1 |
| xr_confluence | 924 | LOOSE | quality_crisis needs a second dislocation lens; >= 4 families or drop the broadest member; dedupe lines |
| xr_cash_leads_book | 500 | LOOSE | require CFO growth > 0 and NI growth >= -10% (368/500 fires have NI falling) |
| tenbagger_credible | 605 | LOOSE | use EV/S where net debt > 0; terminal margin from own margin x 1.5, not a 6% floor; deflate ARS/TRY growth |
| mb_tree_recipe | 362 | LOOSE | add ~(shares_growth_3y > 0.20) & _not_melting (115 fires > 50% dilution lead the spirit) |
| mb_fallen_stressed | 971 | LOOSE | drop size-relative stress legs when nde < 3 & cover >= 3; strip captive finance; add dilution guard |
| xr_margin_mixshift | 45 | TIGHT + LOOSE | US-only by input; require two cheap lenses; clip mix uplift <= 1 |
| low_sbc_quality | 1,900 | TIGHT | fill SBC from fq_sbc_pct_revenue / fmp_sbc_to_revenue (+5,427 eligible names); add ~_roce_oneoff_suspect |
| reinvest_inflect | 633 | TIGHT | fall back to fqx_roic_slope8 where roiic_acceleration is NaN (69%); add mcap >= 10m & _not_melting |
| lindy_margin | 1,202 | TIGHT + COSMETIC | lift the 0.6 op / 0.8 EBITDA caps when tc_min_opm >= 15% (Moutai, VeriSign, TPL, OBIC out); `measured` path is dead |
| xr_investment_remark | 3 | TIGHT | require carrying value dated <= 6 months and carry <= assets - cash (XNET suspect) |
| spinoff_quality | 1 | TIGHT + COSMETIC | _ncol for the net-cash leg (zero-fill passes NaN); scrub when-issued lines; widen spin feed beyond EDGAR |
| gayner_pay_up_quality | 66 | OK (COSMETIC) | drop dead lens3 and years >= 7 legs; 0.5% share tolerance; frame cross-listed lines on home venue |
