# Promise sweep 2: archetype_tags.py, original lines 2700-5300 (lynch_pegy … xr_nol_shield)

## Method and caveats

- **The file changed while I worked.** Another session was editing `archetype_tags.py`: a cannabis block went in at about line 3586 and Gayner fixes at about line 8070, so the file grew from 10,533 to 10,726 lines. Line numbers below come from the live file as copied at 16:11 (`ps2/live.py`). Every old/new pair in `ps2/patches.py` was checked against that copy: each old string occurs exactly once, and applying all 30 in sequence still parses (`ps2/patched_preview.py`). The patches use string replacement, not line numbers.
- **How impact was measured.** I made a scratch copy, `ps2/inst.py`. It is the 16:08 snapshot plus a probe inserted straight after the `arch_xr_nol_shield` block. The probe computes each current gate next to its patched gate, writes `ps2/probe.parquet` (580 KB) and returns before the output block, so no repo file was written.
- **What the impact columns mean.**
  - "gate" counts are taken at that point in `compute()`, before the later scrubs run.
  - "pub-removed" is the number of fires in the published `archetype_tags.csv` (15:31 build) that the patch would remove.
  - For every archetype checked, the published flags were a strict subset of the gate flags.
- **Column semantics I checked in the producers.** Several findings below depend on these.
  - `fqx_eps_pos_share_8` is the share of the last 8 periods with EPS **up year-on-year** (fmp_quarterly_ext.py:13).
  - `fmp_st_ni_up_share_5` is the share of the last 5 fiscal years with net income **up on the year** (fmp_statements.py:276-278).
  - `eps_yoy_positive_share` is the share of the last 8 quarters with **YoY EPS growth** (yartseva_db.py:683).
  - None of the three measures profitability. The only "years profitable" count is `tc_opinc_pos / tc_years` (operating income > 0, up to 8 fiscal years).
  - `fg_ni_ps_3y` is the **cumulative** 3-year per-share change. `fg_ni_ps_3y_cagr` is already per share.
  - `fq_fcf` / `fq_ni` are TTM, and `*_p` is the year-ago TTM.

---

## F1 — BUG: lynch_pegy nets a per-share growth rate for dilution a second time (line 2799-2801)

- **Promise.** "a share-issuing acquirer's NI growth is netted for the count where it is measured". The financial-growth note adds that "Lynch's growth is the LONG-TERM per-share rate: the 3-year net-income-per-share CAGR first".
- **What the code does.**
  - It builds the growth chain with `fg_ni_ps_3y_cagr` first, then divides the whole chain by `(1 + fq_shares_yoy)`.
  - The 3-year per-share CAGR is already per share, so dilution is counted twice.
  - It also mixes a 1-year share change into a 3-year CAGR. 801 of 1,125 gate fires take the per-share leg.
- **Impact.** 50 published fires removed and 59 added (1,125 becomes 1,134 at the gate).
- **Patch (F1).** Net only the total-NI legs:

```python
    # the share netting applies to the TOTAL net-income legs only: the 3-year
    # CAGR is already PER SHARE (netting it again counts the dilution twice)
    _g_ly_tot = (_ncol('fqx_ni_ttm_g').fillna(_ncol('fmp_st_ni_g1'))
                 .fillna(_ncol('yf_earnings_growth').where(_ncol('yf_earnings_growth') < 0.50)))
    _g_ly_tot = ((1.0 + _g_ly_tot) / (1.0 + _ncol('fq_shares_yoy').fillna(0).clip(lower=-0.5)) - 1.0)
    _g_ly = _ncol('fg_ni_ps_3y_cagr').fillna(_g_ly_tot)
```

## F2 — lynch_pegy durability: the comment says "positive", the columns count growth (line 2807-2808)

- **Promise.** "EPS positive in >= 75% of the last 8 quarters, else NI positive in >= 4 of 5 FYs".
- **What the code does.** Both columns count growth years, not profitable years.
  - `fqx_eps_pos_share_8` is the share of quarters with EPS up year-on-year.
  - `fmp_st_ni_up_share_5` is the share of fiscal years with NI up on the year. With 4 comparisons, `>= 0.75` passes 3 of 4.
- **Why I propose a comment fix.** A consistent growth record fits Lynch, and line 2785 says "consistent EPS record". Changing the code to "EPS positive" would need a quarterly EPS-positive count, which does not exist; the closest is `tc_opinc_pos / tc_years` (annual operating income).
- **Impact.** 0 fires.
- **Patch.** F2 (comment only).

## F3 — lynch_pegy exceptional: number and leg differ (line 2787 vs 2810)

- **Promise.** "Exceptional: PEGY <= 0.6 and operating income positive every year".
- **What the code does.** `(_pegy_ttm <= 0.5) & (fqx_eps_pos_share_8 >= 0.875)`: a different number, and an EPS-growth share instead of a profitability record.
- **Impact.** 224 exceptional names become 468 (27 removed, 271 added).
- **Patch (F3).** `(_pegy_ttm <= 0.6) & (tc_years >= 5) & (tc_opinc_pos >= tc_years)`. Alternative: keep the code and change the comment to "<= 0.5 and EPS up in >= 7 of 8 quarters".

## F4 — lynch_evgy exceptional omits "with operating leverage showing" (line 2832 vs 2843)

- **Promise.** "Exceptional: <= 0.4 with operating leverage showing".
- **What the code does.** `(_evgy_d <= 0.4)` only.
- **Impact.** 994 exceptional names become 836 (158 removed).
- **Patch (F4).** Add `& (_ebit_g_chain > _ncol('fq_rev_growth').fillna(rev_yoy))`, i.e. EBIT outgrowing sales on the chain the core already uses.

## F5 — oneil_canslim "A": 25%/yr stated, about 15%/yr coded (line 3391)

- **Promise.** "3-year NI per share >= +52% (25%/yr)".
- **What the code does.** `fg_ni_ps_3y` is cumulative, so 0.52 is 15%/yr. 25%/yr over three years is 1.25³ − 1 = 0.953.
- **Impact.** 12 of 97 published fires removed (MSFT, HALO, DWS.DE, RFX.L and others).
- **Patch (F5).** Change 0.52 to 0.953 and fix the comment. Alternative: keep 0.52 and change the comment to "(15%/yr)".

## F6 — cundill_deep_value: the "no deficits over 5y" test counts growth years (line 3432-3434, 3456)

- **Promise.** "the 5-year no-deficit test read GLOBALLY: the EDGAR EPS share, else the statement-history share of NI-positive years, else the through-cycle op-income count".
- **What the code does.** The first two lenses (`eps_yoy_positive_share`, `fmp_st_ni_up_share_5`) are growth shares. A name profitable every year but with flat earnings fails. A loss-maker whose losses shrink passes. The score's "# no deficits" term also uses `_ceps_pos`.
- **Impact.** 15 published fires removed and 173 gate fires added (303 becomes 458).
- **Patch (F6 and F6b).** Use `tc_opinc_pos / tc_years` (tc_years >= 3) as the only no-deficit lens, missing still passes, and score on it. No NI-positive-years column exists; this is the closest, and it is at operating level.

## F7 — dta_reversal "SUSTAINED: positive in at least half the last 8 quarters" reads EPS growth (line 4547)

- **Promise.** "positive in at least half the last 8 quarters".
- **What the code does.** `~(fqx_eps_pos_share_8 < 0.5)` is "EPS up YoY in half the quarters". A biotech whose losses narrow passes as a "sustained positive" record.
- **Impact.** 105 of 177 published fires removed (TTEC, VXRT, AGEN, SPRO, MVST, UPLD and others) and 24 gate fires added.
- **Patch (F7).** Cumulative NI over the last 8 quarters, `fq_ni + fq_ni_p > 0` (TTM plus year-ago TTM), where measured. No quarterly EPS-positive count exists, so this is the closest column, and it matches how valuation-allowance releases are judged (on cumulative income).

## F8 — wolf_compounder omits "margins expanding" (header line 3660 vs gate 3664-3679)

- **Promise.** "a sustained, ACCELERATING grower bought at a single-digit/low-teens multiple, margins expanding, cash-positive, low dilution".
- **What the code does.** There is no margin leg. `oper_lev_any` can pass on `rev_qoq_ttm > 0` or `cfo_seq > 0` alone.
- **Impact.** 27 of 165 published fires removed.
- **Patch (F8).** Add `((ebitda_margin_delta > 0) | (op_margin_delta_yoy > 0) | (_fqx_inc > op_margin))`.

## F9 — oak_nav_discount: "net debt low (the recipe lists it twice)" is missing (line 3874-3886)

- **Promise.** "the vehicle test is the industry … at a sub-0.7 book; net debt low (the recipe lists it twice); and the discount being ADDRESSED".
- **What the code does.** It has the vehicle, not-eroding, discount and addressed legs. There is no leverage leg.
- **Impact.** With `_lev_ok(3.0)` (nde, else debt/assets <= 0.35 / D/E <= 1 / net cash; unmeasured passes), 93 of 191 published fires are removed: levered property holdcos such as BLND.L, DXS.AX, CMW.AX and ARF.AX.
- **Patch (F9).** The threshold is my choice. `_lev_ok(2.0)` would be stricter.

## F10 — crisis_asset_backed_recovery: the discount is not measured against tangible assets (line 3940)

- **Promise.** "the discount must be measured against TANGIBLE assets (real, saleable plant/reserves, not goodwill)".
- **What the code does.** `(pb < 0.8) | (p_tb < 0.8)`. Total book, including goodwill, qualifies even when P/TB is measured and above 0.8.
- **Impact.** 103 of 788 published fires removed.
- **Patch (F10).** Use P/TB where measured, and P/B only where P/TB is NaN.

## F11 — hidden_assets: "priced at/below book", coded as P/B < 1.5 (header line 4078 vs 4123)

- **Promise.** "the stock priced at/below book (so the portfolio really is free)".
- **What the code does.** `(pb > 0) & (pb < 1.5)`.
- **Impact.** 573 of 1,955 published fires sit at 1.0 < P/B < 1.5.
- **Patch (F11).** `pb <= 1.0`. Alternative: change the header to "below 1.5x book".

## F12 — xr_float_compounding: the NWC proxy is used even where deferred revenue is measured, and "persistently" is not tested (line 4823, 4829)

- **Promise (a).** "Where the audited balance is absent, the negative-NWC proxy still qualifies". The comment presents NWC as a fallback because it "also flags stretched payables".
- **What the code does (a).** `(defrev/rev >= 0.10) | (nwc < 0)`. Negative NWC qualifies even when deferred revenue is measured and below 10%.
- **Impact (a).** 99 of 128 published fires removed: ZAP.WA (fertiliser), MTN, VET.TO, BIREF (oil and gas). These are exactly the payables-float cases the comment excludes.
- **Promise (b).** "CFO far above NI persistently".
- **What the code does (b).** It tests only one window.
- **Impact (b).** Adding `~(_cfo_ni_ya < 1.0)` (as customer_float already does) removes 2.
- **Patch.** F12a and F12b.

## F13 — XR5 forensic_floor_growth and XR14 depreciation_cliff test harvest on TTM capex, not maintenance capex (line 4653, 4871)

- **Promise.** At line 4162-4166 (audit #2/#4/#5): harvest / owner-earnings gates "were faked by a momentarily-collapsed TTM window", so maintenance capex (the higher of TTM and the 5-yr average) is used. XR5's floor is described as "an over-depreciated asset base" (F1's test).
- **What the code does.** Both gates still use `_capex_loc` (TTM).
- **Impact.** XR5: 108 of 826 published fires removed. XR14: 0 now (5 gate fires; latent).
- **Patch.** F13 and F14.

## F14 — liger_neglected_survivor exceptional: "observed coverage <= 1" passes when coverage is missing (line 3770)

- **Promise.** "Exceptional: observed coverage <= 1, TTM EBIT +30%".
- **What the code does.** `~(sent_n_analysts > 1)` is NaN-permissive.
- **Impact.** 340 of 376 exceptional names have no `sent_n_analysts`; 36 remain.
- **Patch (F15).** `(sent_n_analysts <= 1)`.

## F15 — The raw-sequential seasonality rule is contradicted: `oper_lev_any` fires on raw-seq alone (def. line 3024; gates 3675, 3761, 4601, 5126, plus more beyond 5300)

- **Promise.** Line 1292-1294: "Raw single-quarter sequential is deliberately EXCLUDED … never to firing". Line 2997-3001: a raw-seq turn "that the TTM/YoY view does NOT see is treated as seasonality".
- **What the code does.** `oper_lev_any = season_robust | rawseq_any`, with its own comment "Fire on ANY turn … even a raw-seq-only early signal". This is used in the gates. 2,878 names are raw-seq-only.
- **Impact if `season_robust` replaces it in-range (published fires removed):**
  - wolf_compounder: 4
  - liger_neglected_survivor: 14
  - xr_floor_inflection: 24
  - xr_asset_owner_catalyst: 23
  - wolf_turnaround: 0 (the leg is redundant there)
- **Patch.** F16a-d. Alternatively, delete the 1292/2997 claims if raw-seq firing is intended.

## F16 — financials_value "(tail) banks/insurers ONLY" (line 3193 vs 3201)

- **Promise.** "(tail) banks/insurers ONLY".
- **What the code does.** It excludes only REITs and funds / asset managers.
- **Impact.** 138 of 271 published fires are Capital Markets (105), Consumer Finance (25) or Credit Services.
- **Patch (F17).** Require a bank / insur / thrift / savings industry, letting blank industries (name-detected banks) through.

## F17 — sustainable_scaler: "NOT funded by dilution (share count flat/down)" is coded as <= 5%/yr (line 3229 vs 3247)

- **Promise.** "NOT funded by dilution (share count flat/down)".
- **What the code does.** A 3-year share CAGR of up to 5% (about 16% cumulative) passes.
- **Impact.** 80 of 167 published fires (core) and 404 of 777 watch fires have share growth > 0.
- **Patch (F18).** `<= 0.0`. A 0.5% noise tolerance, as Gayner uses, is a reasonable variant. Alternative: change the header to "<= 5%/yr".

## F18 — oak_asset_floor has a third leg the comment does not describe (line 3895-3899)

- **Promise.** "the author's test is mcap <= cash + tangible assets: net cash >= 70% at/below tangible book, or NCAV covering the cap; the old 40% … rule is surfaced as watch".
- **What the code does.** It also passes `(net_cash >= 0.40) & cash_gt_ev`, which re-admits the 40% rule.
- **Impact.** 331 of 1,282 published fires rely only on that leg.
- **Patch (F19).** Drop the leg. Alternatively, document it in the comment.

## F19 — Dead variable `n_analysts_present` (line 2885-2888)

- **Promise.** "(G5) … Neglect gates require the field actually present."
- **What the code does.** The mask is never referenced; I grepped the whole file. All three Liger gates read missing coverage as neglected, which the later "(twosided)" and "(endpoint matrix)" comments make explicit.
- **Impact if G5 were wired in (published fires lost).** Fires with no coverage field at all: liger_asset_backed 1,148 / 1,274; lagging_inflect 748 / 1,059; neglected_survivor 870 / 1,031.
  - liger_asset_backed's "no coverage field … neglected only at sub-$500M" leg does nothing, because the gate already caps mcap below $400M.
- **Patch (F20).** Delete the mask and correct the comment. Status: stale promise, 0 fires.

## F20 — Comment-only mismatches (0 fires)

- **cash_adjusted_pe (line 4265).** The comment says "0 < adj P/E <= 8 is the cheap band". The code, and the doctrine stated two lines earlier, accept negative values: 186 published fires have adj P/E <= 0. Patch F21.
- **Lynch preamble (line 2766-2770).** It says "PEGY falls back to a recompute …; EV-GY falls back to psg/evsg". The code has no PEGY fallback, and the sales fallback is only `lynch_evgy_sales_watch`. Patch F22.
- **xr_quality_crisis header (line 4614).** It says "or the bottom third of the 5-year range". The leg was removed by audit 3 (52-week / 5-year high only). Patch F23.

## F21 — Latent holes (0 current fires changed)

- **xr_nol_shield (line 5301).**
  - **Promise.** The comment says a buyback-driven deficit "shows negative RE with a HIGH roe".
  - **What the code does.** With negative equity, ROE is negative, so `~(roe > 0.20)` passes it.
  - **Impact.** All 8 negative-equity fires today are Bombardier share lines, whose deficit comes from losses (correct). Patch F24 targets only negative-equity repurchasers (buyback yield > 1%), so the expected change is about 0 (not measured).
- **cluseau_realizable_book (line 3980).**
  - **Promise.** "cash NET OF DEBT … a known net-cash position corroborates".
  - **What the code does.** `total_debt.fillna(0)` treats unknown debt as zero, and no net-cash corroboration exists.
  - **Impact.** 0 of 38 fires have NaN debt today. Patch F25.

---

## Summary table

Line numbers are from the live file at 16:11. "Est. fires changed" counts published fires removed / gate fires added unless noted.

| line | archetype | promise | status | est. fires changed |
|---|---|---|---|---|
| 2799-2801 | lynch_pegy | per-share growth, netted once for issuance | BUG: per-share CAGR netted twice | −50 / +59 |
| 2807-08 | lynch_pegy | "EPS / NI positive" durability | columns are growth shares | 0 (comment fix) |
| 2810 | lynch_pegy exc. | PEGY ≤ 0.6 + op. income positive every year | 0.5 + EPS-up share | 224 → 468 |
| 2843 | lynch_evgy exc. | ≤ 0.4 with operating leverage | leg missing | −158 of 994 |
| 3391 | oneil_canslim | 3y NI/sh ≥ 25%/yr | 0.52 = 15%/yr | −12 of 97 |
| 3432/3456 | cundill_deep_value | no deficits over 5y | growth shares used | −15 / +173 |
| 4547 | dta_reversal | positive in ≥ half of 8 quarters | EPS-up share | −105 of 177 / +24 |
| 3675 | wolf_compounder | margins expanding | leg missing | −27 of 165 |
| 3885 | oak_nav_discount | net debt low | leg missing | −93 of 191 |
| 3940 | crisis_asset_backed_recovery | discount vs TANGIBLE assets | P/B accepted | −103 of 788 |
| 4123 | hidden_assets | at/below book | P/B < 1.5 | −573 of 1,955 |
| 4823 | xr_float_compounding | NWC proxy only where deferred revenue absent | always OR | −99 of 128 |
| 4829 | xr_float_compounding | CFO > NI persistently | one window | −2 |
| 4653 | xr_forensic_floor_growth | maintenance-capex harvest | TTM capex | −108 of 826 |
| 4871 | xr_depreciation_cliff | maintenance-capex harvest | TTM capex | 0 (latent) |
| 3770 | liger_neglected_survivor exc. | OBSERVED coverage ≤ 1 | NaN passes | −340 of 376 |
| 3024 (+3675, 3761, 4601, 5126) | oper_lev_any users | raw-seq never fires | fires on raw-seq | −4 / −14 / −24 / −23 |
| 3201 | financials_value | banks/insurers ONLY | brokers / consumer finance pass | −138 of 271 |
| 3247 | sustainable_scaler | share count flat/down | ≤ 5%/yr | −80 of 167 |
| 3898 | oak_asset_floor | 70% NC at TB, or NCAV ≥ 1 | undocumented 40% + cash>EV leg | −331 of 1,282 |
| 2885 | Liger (G5) | neglect needs field present | mask never used | 0 (comment fix) |
| 4265 / 2766 / 4614 | cash_adj_pe / Lynch / xr_quality_crisis | stale numbers / fallbacks | comment-only | 0 |
| 5301 | xr_nol_shield | buyback deficit shows high ROE | negative equity passes | ~0 (latent) |
| 3980 | cluseau_realizable_book | cash net of debt | NaN debt = 0 | 0 (latent) |

Artifacts in `scratchpad/ps2/`:
- `patches.py`: exact old/new pairs, each verified unique.
- `inst.py` and `probe.txt`: the probe copy and its inserted code.
- `probe.parquet`: per-name current and patched gate flags.
