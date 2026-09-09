# Rank 1–10 / 30–50 deep audit — INFLECTION / TURNAROUND / CYCLICAL / SEGMENT (16 archetypes)

Scope: names ranked 1–10 AND 30–50 by `entry_today_asymmetry` in each of the 16 family archetypes. Verdicts read against the rule legs in `archetype_tags.py`. Already-landed fixes (rev_yoy>0 on roic/double/micro-activist/liger inflect; fastest_segment segment_count≥2+is_operating; net-debt `heavy_debt` veto on asymmetric_assembly/levered_inflection) are NOT re-flagged — this reports what REMAINS. Small-cap breadth treated as intentional. `[C]` = confirmed structural bug; `[T]` = tuning. `$` figures are as-shown (KR/JK/etc. are local-ccy in the dump; USD gate applied upstream). Worst-first.

## Cross-cutting root cause
**Missing `is_operating` gate on tags that were never touched.** Five archetypes (`reinvest_inflect`, `levered_inflection`, `asymmetric_assembly`, `geographic_global`, `diversified_segments`) omit the financial/REIT/utility exclusion their siblings carry, so banks, insurers, capital-markets, SPACs, REITs, property developers and utilities leak — populations for which EV/EBITDA, ROIC/ROIIC and "revenue-segment diversification" are meaningless or structurally different. `is_operating` already exists and cleanly excludes `sector∈{financials, real estate, utilities}` (with a NULL-sector industry backstop). Adding `& is_operating` is the minimal, intent-preserving fix in every case.

---

## 1. arch_wolf_emerging — [C] 100% off-thesis (6/6 firers)
Thesis (code comment): "his cautious **cannabis** bets… emerging-sector profitability." Every single firer is a mature **Big Tobacco** major, zero cannabis names:
- **GGRM.JK** Gudang Garam, **HMSP.JK** Sampoerna, **WIIM.JK** Wismilak, **JAPAF/JAPAY** Japan Tobacco (dup ADRs), **STG.CO** Scandinavian Tobacco. Several are *declining* (GGRM rev −9.4%, HMSP −6.0%, STG −3.1%) — the opposite of an emerging-sector bet.

**Root-cause leg:** the sector regex `_emerging = _ind/_nm.str.contains('cannabis|hemp|marijuana|tobacco')` — `tobacco` drags in the entire mature tobacco complex, which then trivially clears the cash-flow/cheapness gates. The archetype fires exclusively on the population it was meant to avoid.
**Fix:** remove `tobacco` from the `_emerging` regex (keep `cannabis|hemp|marijuana`). Optionally add a growth floor (`rev_yoy>0`) so a shrinking emerging-sector name can't qualify either.

## 2. arch_reinvest_inflect — [C] financials/REITs + melting names (no is_operating, no live-returns floor)
Thesis (V): "ROIIC accelerating from a **positive base** AND assets actually growing… a compounder finding more runway." Leg: `(roiic_lindy≥0.05) & (roiic_acceleration≥0.05) & (asset_3y_cagr≥0.05)` — **no `is_operating`, no current-returns floor** (its siblings `durable_reinvestment` / `cash_reinvest` carry BOTH `is_operating` and `_roce_now_ok`; this one carries neither).
- Financials/insurers/REITs where ROIIC is meaningless: **WDH** Waterdrop (insurance, EV/EBITDA −1.7), **THG** Hanover Insurance, **ECPG** Encore Capital (debt collector), **GCMG** GCM Grosvenor, **MC** Moelis, **NOAH** (capital markets), **STRW** Strawberry Fields REIT (nde 6.1, shares +78% — "asset growth" is debt-funded property + dilution), **LTC** Properties REIT.
- Melting / negative live returns passing on a trailing ROIIC window: **JFIN** Jiayin (rev −10.3%, mom −82%), **ACTG** Acacia (roce −2.9%, a patent holdco).
**Root-cause leg:** absent `is_operating` and `_roce_now_ok`.
**Fix:** `df['arch_reinvest_inflect'] = is_operating & _roce_now_ok & (roiic_lindy≥0.05) & (roiic_acceleration_v≥0.05) & (asset_3y_cagr_v≥0.05)` — i.e. port the two guards its two siblings already use.

## 3. arch_levered_inflection + arch_asymmetric_assembly — [C] Real-estate/utility/SPAC leak (shared root cause)
Thesis: a **levered operating equity STUB** whose economics are inflecting and DELEVERAGING (value transfers lenders→equity as EBITDA rises / debt falls). Both rules gate on `heavy_debt` but **neither carries `is_operating`**, so the sheets are dominated by names whose leverage is *structural*, not a convex distressed stub:
- **levered_inflection (486):** ranks are wall-to-wall Real Estate developers — **SAMCO.BK, SENA.BK, MTRE3.SA, PKG1T.TL, 5UX.SI** Oxley, **IMMO.BR, ARTE.PA** — plus an outright **REIT (YEIS.MC** Elaia Socimi, ebitda_margin 1.06 artifact, net_cash 1.0 artifact) and a blank-check **SPAC (310870.KQ** Korea No.8 Special Purpose Acquisition, Financials) and **AMTD** Idea (op_margin −336%).
- **asymmetric_assembly (186):** **MK.BK** M.K. Real Estate (nde 18.3, ev/ebitda 71, op_margin −19%), **CORE-B.ST** Corem Property (REIT, roe −18%, nde 17.9 — "op improvement" is property revaluation), **CMC.BK** Real Estate, **PRIME.BK** (Utility / IPP), **JFIN**/**TPHIF** (financials).

For a property developer/REIT, `heavy_debt` is satisfied by every name (leverage is the business model) and revaluation- or project-timing EBITDA satisfies the "deleveraging inflection" leg — the convex value-transfer thesis simply doesn't apply.
**Root-cause leg:** missing `is_operating` on both rules (distinct from the net-cash `heavy_debt` veto that already landed).
**Fix:** append `& is_operating` to `arch_levered_inflection` and `arch_asymmetric_assembly`. (`is_operating` drops sector∈{Real Estate, Financials, Utilities} — exactly the leaking population.)

## 4. arch_geographic_global — [C] pure descriptor, zero quality gate
Thesis (AF): "Global footprint… currency + market **diversification**" — used as a positive signal. Leg is literally `(geographic_region_count≥4)` and nothing else (no `is_operating`, no survivability floor, no `.fillna(False)`).
- Financials/utilities where the framing is wrong: **AGO** Assured Guaranty (insurer), **TIGR** Up Fintech (capital markets), **CWCO** Consolidated Water (utility).
- Deeply distressed / value-destroying names presented as a positive: **TTEC** (roce −9.7%, roe −101%, rev −3.2%, mom −60%), **WIMI** Wimi (roce −4.2%, ebitda_margin −8%, rev −22%), **BANL** Cbl Intl (roce −19.5%, ebitda_margin −0.4%), **ACTG** (roce −2.9%).
**Root-cause leg:** no operating/quality gate at all.
**Fix:** `is_operating & (geographic_region_count≥4) & ((ebitda_margin>0)|(s('cfo_ttm')>0))` and add `.fillna(False)`. Preserves the diversification signal but only on solvent operating businesses.

## 5. arch_diversified_segments — [C] financials leak (no is_operating)
Thesis (AD): "4+ segments AND HHI ≤0.40 → real **diversification of revenue streams**, lowers single-segment risk." Leg omits `is_operating`, so the segment-HHI construct is applied to financials where "segments" are premium/product lines, not diversified operating revenue:
- **NOAH** (EV/EBITDA −33 artifact), **CINF** Cincinnati Financial, **SIGI** Selective Insurance, **RILY** B. Riley, **TREE** LendingTree, **BRK-A** Berkshire (insurer conglomerate). Plus distressed shells: **AMTD** (op_margin −336%, net_cash −5.5), **HOLO** MicroCloud (RED, EV/EBITDA −568, nde −627).
**Root-cause leg:** missing `is_operating`.
**Fix:** `is_operating & (segment_count≥4) & (segment_hhi≤0.40)`; optionally add a survivability floor to drop AMTD/HOLO-type shells. (Sibling note: `concentrated_segments` shares the missing `is_operating` but is an explicit NEGATIVE/transparency flag, so lower stakes — apply the same gate for consistency only.)

## 6. arch_wolf_value_catalyst — [T] "growing" bypassed by rev_growth_score; no live-returns floor
Thesis (C): "a **growing**, cash-generative microcap with a fortress balance sheet at a cheap FCF yield." Growth leg is `((rev_yoy_c≥0.10) | (rev_growth_score≥0.5))` — the composite `rev_growth_score` alt-leg lets **declining** top lines qualify as "growing," and there is no current-ROCE/op-margin floor:
- **TTEC** (rev −3.2%, roce −9.7%, roe −101%, mom −60%, net_cash 74% — a melting shell reading as "value + catalyst"), **043610.KQ** Genie Music (**roce −22.4%**, rev +2.3%), **016090.KS** Daehyun (rev −6.2%), **003650.KS** Michang Oil (rev −6.1%), **POONADAL.BO** (op_margin −0.5%, ebitda_margin 1.6%), **0911.HK** Qianhai (ebitda_margin 1.1%).
**Root-cause leg:** the soft `rev_growth_score≥0.5` bypass + no returns floor.
**Fix:** require `rev_yoy_c≥0` even when leaning on `rev_growth_score` (so a negative top line can't pass), and add `((roce>0)|(op_margin_v>0))`.

## 7. arch_roic_inflect — [T] residual: no CURRENT-returns floor
Post-fix it carries `is_operating` + `rev_yoy>0` + `cash_roic_lindy>0`, but the inflection is still a binary flag confirmed by a *trailing* lindy — with no live-returns floor, currently loss-making names clear it:
- **GTLB** GitLab (op_margin −6.0%, ebitda_margin −6.2%, roe −3.0%), **AZTA** Azenta (op_margin −32.7%, roe −6.8%), **PATH** UiPath (op_margin +0.3%, roce +0.35% ≈ 0), **CERT** Certara (roe −1.4%), **SSTK** Shutterstock (roe −3.8%, mom −75%). Also net-cash artifacts: **RLX** (EV/EBITDA −134), **TUYA** (nde −46).
**Root-cause leg:** binary `roic_inflection_flag` + trailing `cash_roic_lindy>0`, no live floor (the rank5–20 audit recommended this; only `rev_yoy>0` landed).
**Fix:** add `& ((s('roce')>0)|(s('op_margin')>0))` — require the returns to be positive *today*, not just to have crossed once.

## 8. arch_liger_lagging_inflect — [T] residual: negative-ROCE + M&A base-effect still pass
Post-fix it carries `is_operating` + `rev_yoy_c>0`, but two named misfits from the prior audit survive because only the rev_yoy guard landed:
- **043610.KQ** Genie Music — **roce −22.4%** yet fires "quiet inflection" (rev +2.3% clears rev_yoy>0; oper_lev_any carries it). No current-ROCE floor.
- **NWL.MI** Newlat Food — rev **+130%** is the Princes acquisition (inorganic), not a quiet organic inflection. No M&A/organic cap.
**Root-cause leg:** growth/oper-lev leg lacks a current-ROCE floor and an organic-growth cap.
**Fix:** add `& (roce>0)` (or `roce_v>−0.02`), and cap the top-line leg (e.g. exclude `rev_yoy_c` above a threshold, or require `rev_accel>0` alongside) so acquisition pops don't read as a lagging inflection.

## 9. arch_wolf_turnaround — [T] "loss-maker crossing to black" leg conflates YoY deltas with zero-crossings
Thesis (B): "a loss-maker crossing into the **black** while still growing." But the inflection leg `… | (cfo_inflection>0) | (fcf_inflection>0) | ((ebitda_inflection>0)&oper_lev_any)` accepts mere YoY *improvements* — not zero-crossings — with no requirement that the base was negative or that current profitability is still marginal. Result: 1020 firers dominated by already-profitable, stable cheap Asian small-caps (positive ROCE + P/E present) that are not turnarounds at all, plus net-cash EV/EBITDA artifacts clearing `wolf_cheap_entry`: **8147.T** Tomita (EV/EBITDA 0.10), **0538.HK** Ajisen (0.16), **9918.HK** Wise Ally (0.11), and negative-ROCE **043610.KQ** Genie Music (−22%).
**Root-cause leg:** the `cfo_inflection`/`fcf_inflection`/`ebitda_inflection` deltas stand in for the zero-crossing turnaround shape.
**Fix:** gate the delta legs on a genuine turnaround signature — require a real first-positive print (`ebitda/cfo/fcf/ni_first_pos`) OR that current profitability is still marginal (e.g. `emd_c>0 & roce<0.10`), so a long-profitable compounder can't read as a turnaround; and clamp `ev_ebitda≥1` (or a sane band) inside `wolf_cheap_entry`.

---

## Minor / watch (not worth a rule change yet)
- **arch_micro_activist_inflect** — `profitable = ebitda_margin≥0.05` lets D&A-heavy operating-loss names through: **1900.HK** China ITS (op_margin −4.6%), **ZENIFIB.BO** (op_margin −5%, FCF −14%); drug developer **2348.HK** Dawnrays fires on a net-cash EV/EBITDA (0.25) artifact. Consider `op_margin>0` and an `is_drug_developer` exclusion, but low volume.
- **arch_double_inflect** — clean post-fix; residual net-cash artifacts only (**FEDU** EV/EBITDA −31, ev_sales −1.6).
- **arch_fastest_segment** — recently fixed; residual: the `_adv_breadth≥3` whole-co corroboration leg can rescue loss-makers (**TUSK** op_margin −40%, **ACTG** lumpy patent rev) with one ≥10% segment. Minor.

## CLEAN (on-thesis, no change needed)
- **arch_regime_cyclical** — HEAVY_ASSET_SECTORS + beaten-down + `rev_yoy>0` + capped margin/inflection leg + not_priced_in. Firers are heavy-asset cyclicals with rising revenue off depressed bases (incl. utilities/IPPs, which are in-scope by design). On-thesis.
- **arch_fixed_cost_demand_shock** — HEAVY_ASSET_SECTORS + `rev_accel>0` + `rev_yoy>0` + margin leg capped at +20pp. Broad (3396) but breadth is intentional; every firer has rising revenue with a margin response. On-thesis.
- **arch_concentrated_segments** — explicit NEGATIVE/transparency flag; firing on distressed concentrated names is expected. (Add `is_operating` only for consistency with #5.)

## Priority order for fixes
1. `wolf_emerging` (drop `tobacco`) — 100% off-thesis, trivial fix.
2. `reinvest_inflect` (add `is_operating` + `_roce_now_ok`).
3. `levered_inflection` + `asymmetric_assembly` (add `is_operating`) — one shared fix.
4. `geographic_global` + `diversified_segments` (add `is_operating` [+ survivability floor]).
5. Tuning: `wolf_value_catalyst`, `roic_inflect`, `liger_lagging_inflect`, `wolf_turnaround` (current-returns / turnaround-shape floors).
