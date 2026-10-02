# Rank 5-20 Qualitative Review — Consolidated Fix Spec (all 4 batches)

~1,280 names reviewed (ranks 5-20 × 80 archetypes). The misfits collapse to
~10 reusable rule bugs. Fix the root cause → many archetypes improve at once.
Each fix names the archetypes and the exact leg. [C]onfirmed data/logic bug vs
[T]uning. Small-cap breadth ($2-5M) is INTENTIONAL — not flagged.

## R1 [C] `is_operating` porous + missing — financials/REITs pollute
`is_operating` is `~(sector.contains financ|real estate|utilit)`, so a NULL
sector bypasses it; and many archetypes omit the gate. Leaks: roic_inflect
(FXNC/NTRSO/SRBK/COHN banks), the whole lindy family (WBS/KINS/ACGLO...),
oak_deleveraging (REITs), oak_nav_discount (operating banks), segment family,
tangible_value (LAND farmland REIT via sector=None).
FIX: (a) make is_operating robust to NULL sector (industry-keyword backstop for
bank/insurance/reit/thrift/mortgage; a NULL sector on a financial-name doesn't
auto-pass); (b) add `& is_operating` to: lindy_fcf/lindy_growth/lindy_margin,
cash_quality, cash_reinvest, durable_reinvestment, owner_operator,
low_sbc_quality, no_dilution, roic_inflect, levered_inflection,
micro_activist_inflect, liger_lagging_inflect, oak_deleveraging, tangible_value
(already has it — fix the NULL-sector hole).

## R2 [C] EDGAR-only gate-legs collapse to trivial proxy for non-US
strong_coverage: `interest_coverage` is NA for all non-US → collapses to a
net-cash screen mislabeled "coverage." capital_discipline: `roic_after_sbc` NA
→ collapses to "insider>=0.20 & fcf>0" (insider-alone failure).
FIX: use globally-available `roce` as the returns/coverage leg (roce>=0.12 for
capital_discipline's quality; a real coverage proxy for strong_coverage), and
require the coverage CLAIM to use real interest_coverage where present.

## R3 [C] FX-corrupted `enterprise_value` breaks EV legs
EV is not net-cash-consistent and FX-corrupt on cross-listings, so: (a) the
"heavily indebted" leg flags NET-CASH firms as levered (weschler_levered_equity,
asymmetric_assembly — KIROY +214% net cash reads as levered); (b) EV/EBITDA and
EV/sales cheapness go absurd (midcap_garp: Nitori EV/EBITDA 0.04; Polimex
EV/sales −0.04).
FIX: leverage legs → use `net_debt_ebitda`/`debt_to_equity`, NOT ev_over_mcap.
EV-multiple cheapness legs → guard `abs(ev/mcap)` to a sane band (e.g. 0.2-5)
so an FX-corrupt EV can't read as ultra-cheap. (Root cause is upstream ADR/FX;
this guards the symptom.)

## R4 [C] Backward-looking lindy/n_yrs ROIC gates lack a current-state floor
Melting ice cubes / post-peak reversers keep qualifying (CATO, THRY, RMNI,
BANL, TUYA, QTWO, BODI, HURC) in durable_reinvestment, cash_reinvest,
lindy_*, roic_inflect.
FIX: add a current-state floor — current roce>0 (or margin not collapsing YoY)
alongside the multi-year streak, so a name whose returns have since turned
negative no longer qualifies as "durable."

## R5 [C] Margin/cost inflection fires while REVENUE DECLINES
oper_lev_any/margin_shock_any/fcf_margin>0 read cost-cut blips as inflections
in declining businesses (ILINK −38%, Neungyule −33%, Baosight −17%, RFT −38%).
The `rev_yoy>0` guard exists in fixed_cost_demand_shock/regime_cyclical but is
MISSING from roic_inflect, levered_inflection, liger_lagging_inflect,
micro_activist_inflect, double_inflect.
FIX: add `rev_yoy > 0` (revenue not declining) to those inflection rules.

## R6 [T] No revenue floor on growth/microcap rules
Sub-$20M (even $0.3M) revenue nanos where % growth is noise (Bengal Tea,
ZENIFIB, NPK, DeTai) in tenbagger_*, exceptional_evsg, cheap_sales_scaler,
growth_algo, bab_*. Only sustainable_scaler has `revenue_ttm>=20e6`.
FIX: add `revenue_ttm >= 20e6` to the growth-scaling archetypes.

## R7 [C] Foreign preferred/non-common leakage
financials_value ranks Great-West/Sun Life/Popular PREFERRED lines on the
common's P/B & ROE — foreign preferreds escape `^[A-Z]{1,5}-P[A-Z]?$`.
FIX: broaden the non-common scrub regex for suffixed foreign preferreds
(`-P[A-Z]?\.` , `-PR`, ` PFD`), and add a `.PR`/`ADR-pfd` name catch.

## R8 [C] fastest_segment fires with NO segment data
Its `_adv_breadth>=3` whole-company corroboration leg fires with no segment
input at all; no is_operating; financials + one-off land sales rank (KANP
+1006%). Segment family also lacks scale/operating gates.
FIX: require actual segment data present (segment_count>=2 or a real
seg_inflect signal), add is_operating; drop the whole-company-only path.

## R9 [C] analyst_awakening on falling knives
"Re-rating begun" fires on crashers near 52w lows (FUBO −75%, TIGR −55%)
because target-upside inflates after a crash.
FIX: require the stock is NOT in freefall — pct_off_52w_high above a floor
(e.g. >= −0.35) or positive recent momentum, so a genuine early re-rating
(not a collapse) qualifies.

## R10 [C] Momentum leader-leg + BAB liquidity default
oneil_canslim/kullamagie_breakout leader = `max(PR6,PR12)>=X`, so a name up on
neither horizon qualifies (Foxconn −5.7%, AVPT −4.5%). BAB liquidity floor
defaults missing ADV to 1e12 → illiquid foreign nanos auto-pass (beta artifact).
FIX: require actual positive recent momentum (momentum_12m>0 OR roc_6m>0) for
the "leader" claim; BAB — treat missing ADV as fail-the-liquidity-gate, not pass.

## Also flagged (specific)
- oak_nav_discount → narrow to real NAV vehicles (closed-end fund / trust /
  holding industry), exclude operating banks/insurers.
- oak_resource_leverage → use NET cash not gross cash_pct_mcap.
- cash_quality → add a non-dilution gate (the cash-vs-earnings gap is the SBC
  add-back; it selects the MOST dilutive names, PEGA +125% shares).
- insider_conviction → tighten the `pb<2.5` value leg (admits melting nanos).
- no_dilution → use freshest share count (stale trailing counts pass collapsing MED).
- lindy_margin → cap op_margin at ~0.6 (royalty holdco INVA 95%) + require ≥5yr
  history (QDMI 1-yr shell, roic 1560%).
- blindspot → convert to a modifier / add a discriminator (near-noise as a
  standalone archetype).

## Cleanest (leave): sustainable_scaler, reinvest_inflect, capital_light_pivot,
quiet_compounder, owner_operator (post-R1), wolf_seal, qarp, weinstein_stage2,
oak_asset_floor, oak_deep_value, cundill.
