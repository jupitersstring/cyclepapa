# Deep two-sided methodology audit — GROUP 2 (Growth, inflection & scalers)

Auditor pass over 20 archetypes. Method: read gate logic + shared helpers
(`_not_melting`, `_profit_present`, `_roce_now_ok`, `is_operating`,
`_roce_oneoff_suspect`, `oper_lev_any`, `rev_growth_score`, `_confirm`), then
pulled top-15 firers by `entry_today_asymmetry` with fundamentals and judged
BOTH directions (promotes-junk / excludes-good). Numbers below are from
`asymmetry_global.csv` + `edgar_roic_roiic.csv` (roic/roiic lindy) as of this run.

Reference calibration applied throughout: LEVEL of profitability/FCF (not the
growth rate) drives multibaggers; microcap sweet spot is ~$5-10M revenue; do
NOT re-raise the $5M floors; op_margin/fcf meaningless for financials/REITs.

---

## 1. kpi_threshold (L653) — CLEAN (minor)
Gate: `is_operating & _not_melting & first_pos_print & (margin_confirming | roce_today>=5%) & mcap>=10e6`.
Anchored by a first-positive profitability print + a returns/margin confirm; the
`_not_melting` + `mcap>=10M` legs are sound. Minor loophole: unlike its inflection
siblings (micro_activist_inflect, double_inflect got an R5 `rev_yoy>0` leg), kpi_threshold
has NO top-line-direction guard, so a cost-cut blip in a shrinking name can fire:
- **SIAM.BK** rev_yoy **-29%**, op_margin -2.4%, roce 2.3% — a first-positive print in a company whose sales fell 29%.
Low priority (the KPI-crossing thesis legitimately includes turnarounds). Optional fix: add `(rev_yoy > -0.10)`.

## 2. micro_activist_inflect (L698) — CLEAN
Gate is well-guarded: `rev_yoy>0`, mcap<250M, ebitda_margin>=5%, inflection_now,
clean balance sheet, cheap-on-EBITDA, `_not_melting`. Firers are genuine cheap profitable microcaps.
One data-quality outlier, not a gate defect: **BENGALT.BO** op_margin -160% while
ebitda_margin +38% (impairment/non-operating artifact) — passes on the EBITDA leg, which is the intended lens. No change.

## 3. fastest_segment (L1020) — PROMOTES-JUNK
Gate: `is_operating & revenue>=20M & _not_melting & segment_count>=2 & seg_inflect_any & seg_growth>=0.10`.
Defect: there is NO whole-company decline guard. `_not_melting` only fails a name
that is BOTH op-loss AND fcf-burning, so a company whose TOTAL revenue is collapsing
qualifies as a "hidden growth engine" on one 10%+ segment:
- **VISN** rev_yoy **-83.9%**, rev_3y_cagr **-30.6%**, fcf_yield -23.6% (op_margin +15% keeps `_not_melting` satisfied) — total revenue fell 84%, this is a divestiture/wind-down, not a hidden engine.
- **TRS** rev_yoy -9.3%, 3y CAGR -9.9%; **THRY** rev_yoy -6.4%, 3y CAGR -13.2% — both shrinking whole-cos firing on a single growing segment.
Fix: add a company-level growth floor to the gate, e.g.
`& (rev_yoy > -0.10) & ~(_ncol('revenue_3y_cagr') < -0.05)` (missing => pass), so
the mix-shift signal requires the parent not to be melting away underneath it.

## 4. lindy_growth (L1032) — PROMOTES-JUNK
Gate: `is_operating & _roce_now_ok & revenue>=20M & revenue_5y_cagr>=0.08 & revenue_accel_lindy>0 & asset_5y_cagr>0.03 & years>=5`.
Defect: this is a PURE-RATE gate (5y CAGR + acceleration + asset growth) with NO
profitability-LEVEL anchor. `_roce_now_ok` only requires `roce >= 0` and is
NaN-permissive — it does not require any cash generation. This is exactly the
Yartseva failure mode (rate without level):
- **PRCH** fcf_yield **-1.1%**, roic_lindy **-0.20**, roic_after_sbc 0.01 — qualifies purely on top-line CAGR while burning cash and destroying capital.
- **OPRX** roic_lindy **-0.057**, roce 2.7%, roic_after_sbc -0.041 — negative incremental returns, admitted on revenue growth alone.
Fix: add `& _profit_present` (the exact anchor its scaler siblings carry). Ideally
also `& ((fcf_yield > 0) | (n_yrs_fcf_pos >= 3) | (roic_lindy > 0.05))` so "durable
growth" requires durable *cash/returns*, not just a rising top line.

## 5. qarp (L1115) — CLEAN
`roiic_lindy>=0.15 & cheap & n_yrs_roic_pos>=4 & roce not<0.03 & shares_3y<=0.02`.
`n_yrs_roic_pos>=4` is a real profitability-level anchor; the `roce<0.03` guard already
closes the base-effect hole (MHH excluded). Firers (PRDO, HRMY, ESEA roce 30%) embody the thesis. No change.

## 6. reinvest_inflect (L1128) — CLEAN (soft)
`roiic_lindy>=0.05 & roiic_acceleration>=0.05 & asset_3y_cagr>=0.05 & _roce_now_ok`.
Anchored on a returns LEVEL (roiic_lindy) rather than pure rate. One soft outlier:
**GTLB** op_margin -5.9%, ebitda_margin -6.2%, roic_lindy -0.18 — passes because
`roiic_lindy` 0.053 clears the 0.05 floor and `_roce_now_ok` reads roce 0.26 (an
SBC-addback/definition mismatch vs the negative GAAP margin). Low priority; could
tighten with `& _profit_present`, but the gate is narrow (71 firers) and returns-anchored.

## 7. double_inflect (L1139) — CLEAN (soft)
`roic_inflect & cash_roic_inflect & rev_yoy>0 & _not_melting & ~(shares_yoy>0.15)`.
A genuinely strict double-crossing gate (24 firers) with dilution guard. Soft
outlier: **MVST** fcf_yield -14.9% (op_margin +10% satisfies `_not_melting`), p_e 192 —
a current cash burner whose lindy cash-ROIC "inflected." Also a data artifact worth
noting (not a gate defect): **HTLM** roic_lindy = **-405** print. Low priority; the
gate's inflection-flag design is sound. Optional: add `& _profit_present`.

## 8. cash_quality (L1151) — CLEAN (minor)
`cash_roic_lindy>0.08 & roic_lindy>0 & (gap)>=0.05 & shares_3y<=0.05 & n_yrs_fcf_pos>=4 & _roce_now_ok`.
Strongly anchored by `n_yrs_fcf_pos>=4`. Minor: `_roce_now_ok` (roce>=0) lets a ~0%
current-returns name through — **MHH** roce **0.0018%**, roic_lindy 0.081 — the same
base-effect shape qarp explicitly closed. Optional parity fix: replace `_roce_now_ok`
with qarp's `~(roce.notna() & roce<0.03)`.

## 9. capital_light_pivot (L1188) — CLEAN
`revenue_3y_cagr>=0.08 & asset_3y_cagr<revenue_3y_cagr & n_yrs_roic_pos>=3 & (roic_accel>0 | roic_lindy>0.10) & _roce_now_ok`.
`n_yrs_roic_pos>=3` supplies the profitability-level anchor; the asset-vs-revenue
inequality is the genuine asset-light signal. Firers embody the thesis. No change.

## 10. lynch_pegy (L1319) — PROMOTES-JUNK (lite)
Gate is a bare `(pegy>0)&(pegy<=1.0)` — the loosest in the group (4832 firers), with
NO `_not_melting` and NO quality/level anchor. Omitting `is_operating` is defensible
(P/E is meaningful for financials, per the design note). The real gap: PEGY's numerator
is P/E, so a name with a NEGATIVE operating margin but positive *non-operating* net
income prints a low P/E and passes:
- **AWC.SI** op_margin **-0.5%** (operating loss) yet p_e 8.1 — the "earnings" behind the cheap PEGY are non-operating.
Growth is capped at 100% upstream (mitigates the denominator side) but there is no
one-off-earnings guard on the numerator. Low-priority given the tag is intentionally
broad; optional fix: `& _not_melting & (op_margin > 0)` (missing => pass on op_margin).

## 11. lynch_evgy (L1329) — CLEAN
`is_operating & ((evgy<=0.6 & ebitda_ttm>0) | (evsg/psg fallback with ebitda_ttm>0 & ev_sales>=0.05))`.
The mandatory `ebitda_ttm>0` is a profitability-level anchor and the ev_sales>=0.05
floor kills the near-zero-EV artifact. Minor: no revenue floor, so a sub-sweet-spot
nano like **ZENIFIB.BO** (rev $4.5M, mcap $2.2M, fcf_yield -14%) fires — but it clears
EBITDA>0. Acceptable given breadth mandate. No change.

## 12. midcap_garp (L1440) — CLEAN (soft)
`mcap>=2B & _roiic_quality & _ey_good_growing`. The proxy branch's `roce>=0.10`
addition (the Jet2 note) works — JET2.L now qualifies via the ROE>=15% branch (a real
returns floor), not the fat-margin-thin-returns hole. Soft outlier: **RV1.F** roce
**-17%** passes the high-EBITDA-margin branch via the `_roe>=0.10` OR-leg despite
negative ROCE. Low priority; consider requiring roce not deeply negative on the ROE branch.

## 13. sustainable_scaler (L1693) — CLEAN
`mcap<2B & revenue>=5M & shares_3y<=0.05 & _durable_growth & _self_funding & _not_pricey & _profit_present`.
Correctly carries `_profit_present` AND `_self_funding` (fcf_ps>0 | fcf_margin>0.03 |
roic>=0.10) AND a non-dilution leg. This is the model the pure-rate gates (esp.
lindy_growth) should imitate. $5M floor is correct — do not raise. No change.

## 14. cheap_sales_scaler (L2315) — CLEAN
`mcap<5B & revenue>=5M & p_s in[0.1,2.0] & rev_yoy>=0.10 & PSG/EVSG cheap & oper_lev_any & near_profit & _profit_present & is_operating`.
Fully anchored (operating-leverage confirmation + `_profit_present` + p_s lower bound).
Firers are cheap growing operating microcaps. $5M floor correct. No change.

## 15. exceptional_evsg (L2339) — PROMOTES-JUNK
Gate: `mcap<20B & revenue>=5M & evsg in[0.002,0.05] & rev_yoy>=0.20 & ev_sales in[0.15,4] & _profit_present & is_operating`.
Defect: BASE-EFFECT single-year growth. `rev_yoy_c` is clipped only at +1000%, and a
huge one-year revenue print mechanically makes EVSG (valuation ÷ growth) look
"exceptional" — the growth denominator is a one-off:
- **B9A.F** rev_yoy **+346%**, op_margin **0.0%**, p_e **307** — a barely-operating name whose 3.5x one-year revenue jump (M&A/base) drives evsg to 0.005. `_profit_present` passes only on the EBITDA margin; the thesis (cheap per unit of *durable* growth) is violated.
- Similar single-year pops: **088130.KQ** rev_yoy +234%, **1815.HK** +209%.
Fix: corroborate growth across bases before trusting EVSG — e.g. require
`(rev_yoy_c<=1.0) | (revenue_3y_cagr>=0.15)` (a >100% YoY must be backed by a durable
3y CAGR), or add a real margin floor `(op_margin>0)`. This mirrors tenbagger's
`_g_confirmed` discipline, which this single-year gate lacks.

## 16. growth_algo (L2388) — CLEAN
`revenue>=20M & rev_yoy>=0.15 & oper_lev_any & fcf_ttm>0 & fcf compounding>=0.20 & ev_fcf in[2,15] & not_diluting & is_operating`.
The mandatory `fcf_ttm>0` + cheap-EV/FCF anchor means even the base-effect growers here
(e.g. 1815.HK +209%) are genuinely cash-generative and cheap on cash. Well-designed. No change.

## 17. tenbagger_path (L2541) — CLEAN (soft)
Uses `g10 = median` of four growth bases + `_g_confirmed` (>=2 bases at 15%) OR
`rev_growth_score>=0.5`, plus op-leverage confirm, viable econ, `_profit_present`,
`implied_10x>=10`. The median-of-bases + cap at 0.50 is the right defense against
single-year base effects. Soft leak: the `rev_growth_score>=0.5` OR-branch re-admits
single-YoY-only names (**B9A.F** rev_growth_score 0.75 on one +346% print), but the
`implied_10x` arithmetic caps growth at 0.50 so the damage is bounded. Data outlier:
**BENGALT.BO** op_margin -160% (EBITDA leg carries `_profit_present`). Low priority.

## 18. tenbagger_credible (L2583) — CLEAN (soft)
`arch_tenbagger_path & real_owner_cash & stable_share_count`. Strictly narrows path.
Soft outlier: **4301.T** fcf_yield **-6.9%** appears — it clears `real_owner_cash` only
via an alternate cash lens (`owner_earnings_yield`/`robust_cash_yield`>0) since
`fcf_ttm>0` and `at_fcf_inflection` (needs fcf_yield>=-0.03) both fail at -6.9%. Worth a
spot-check that those alt lenses aren't stale, but the design is intentionally
multi-lens. Low priority.

## 19. evsales_derating (L2630) — PROMOTES-JUNK
Gate: `mcap>=50M & ((rev_yoy_c>=0.20) | (rev_growth_score>=0.6)) & derate_any & ev_sales in[0.1,6] & (viable) & ~(ebitda<0 & fcf<0) & is_operating`.
Two compounding defects create a value trap:
1. The growth floor is bypassable: `rev_growth_score>=0.6` admits names with NEGATIVE
   headline growth, because that score is a component-momentum composite (rev_accel,
   qoq, per-share) that stays high while actual sales fall.
2. `derate_any` fires on `mult_compression = rev_yoy_c - stock_return >= 0.15` — which
   is satisfied when the STOCK collapses far more than sales, i.e. it rewards price
   destruction, not "sales ripping past a flat stock."
Result — a shrinking company reads as "unpriced growth derating":
- **TTEC** rev_yoy **-3.2%**, rev_3y_cagr **-4.4%**, roce **-9.7%**, yet rev_growth_score = **0.633** (bypasses the 0.20 floor) and its collapsed stock produces a +47pt "derate gap." This is a melting value trap, the exact opposite of the thesis.
Fix: make the top-line floor HARD and positive — replace the OR with
`& (rev_yoy_c >= 0.15) & ~(_ncol('revenue_3y_cagr') < 0)` so a name with falling sales
cannot qualify no matter how the composite score reads; keep `rev_growth_score` only as
an upweight, not as a gate-opener.

## 20. lynch_reward (L2761) — CLEAN (minor)
`is_operating & _not_melting & lr_progress_gate (profit-durable) & lr_not_capacity_trap(roce>=0.06) & lr_unpaid & lr_live_tape & lr_near50 & (release|roc_setup)`.
Negative current rev_yoy among firers (IRC.BK -2%, JUBILE.BK -15%, 900920.SS -8%) is
CONSISTENT with the thesis (years of past progress, price not yet paid, recent stall) —
`lr_profit_durable` + `_not_melting` + `roce>=0.06` anchor it. Minor gap: no dilution
guard, so **131090.KQ** shares_yoy **+389%** fires while the pattern (Fannie-style
share shrink into a sleeping price) is the opposite. Low priority; optional
`& ~(_ncol('shares_yoy') > 0.15)` (the same guard double_inflect uses).

---

## THREE HIGHEST-PRIORITY FIXES

1. **lindy_growth (L1032) — add a profitability-LEVEL anchor.** It is a pure-rate gate
   (5y CAGR + accel + asset growth) with only NaN-permissive `_roce_now_ok`, so cash
   burners with negative incremental returns qualify (PRCH fcf -1.1% / roic_lindy -0.20;
   OPRX roic_lindy -0.057). Add `& _profit_present & ((fcf_yield>0) | (n_yrs_fcf_pos>=3) | (roic_lindy>0.05))`.
   This is the clearest violation of the Yartseva "level, not rate" doctrine in the group.

2. **evsales_derating (L2630) — close the shrinking-value-trap loophole.** The
   `rev_growth_score>=0.6` OR-branch admits names with falling sales (TTEC rev_yoy -3.2%,
   3y -4.4%, roce -9.7%) and the derate gap rewards stock collapse. Replace the growth OR
   with a HARD positive floor: `& (rev_yoy_c>=0.15) & ~(_ncol('revenue_3y_cagr')<0)`.

3. **fastest_segment (L1020) — add a whole-company decline guard.** A hidden growth
   engine inside a company whose TOTAL revenue is collapsing (VISN -84%, TRS/THRY
   shrinking) is noise. Add `& (rev_yoy > -0.10) & ~(_ncol('revenue_3y_cagr') < -0.05)`
   (missing => pass) so mix-shift requires the parent not to be melting.

(Runner-up: exceptional_evsg (L2339) — require single-year >100% growth to be corroborated
by `revenue_3y_cagr>=0.15`, or add `op_margin>0`, to stop base-effect EVSG like B9A.F +346%/PE307.)
