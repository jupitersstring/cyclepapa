# Deep two-sided audit — GROUP 1: Quality compounders & capital allocation

Method: read each gate + shared helpers (`_not_melting`, `is_operating`, `_roce_now_ok`,
`_roce_oneoff_suspect`, `net_cash_pct_sane`, `ebitda_margin_sane`), pulled top-15 firers by
`entry_today_asymmetry` with fundamentals + EDGAR lindy fields, and quantified melters across the
whole firer set (not just the head). Data: `asymmetry_global.csv` (46,526 rows, deduped) merged with
`edgar_roic_roiic.csv`. "Confirmed melter" = non-financial with (op_margin<0 & fcf_yield<0) OR roce<-5%.

Structural note that applies to the whole family: `durable_reinvestment, cash_reinvest, roic_inflect,
cheap_per_roiic, lindy_margin, lindy_fcf, no_dilution, low_sbc_quality(partial), quiet_compounder,
buyback_compounder, owner_operator` are all keyed on EDGAR multi-year fields (`roic_lindy`, `n_yrs_*`,
`years_of_history`) and therefore fire on **US filers only**. This is by design (additive tags; non-US
names keep their point-in-time matches) and global breadth is preserved by the point-in-time gates
(`narrative_lag, capital_returner, balance_sheet_return, strong_coverage, large_cap_quality`). I do NOT
score US-only as a defect except where a cheap non-US path is available and the thesis is inherently a
neglected-microcap thesis (quiet_compounder / owner_operator — see below).

---

## narrative_lag (L524) — CLEAN
Point-in-time, global, mcap floor $10M (correctly low — keeps the microcap cohort). Top firers are
cheap net-cash HK/KR/JP/TH names with positive margins and a down tape (2230.HK, 1900.HK, FPIP.ST).
`_roce_now_ok` + cheapness anchor + advance-breadth>=2 keep it honest. Thin-negative-op names
(1900.HK op -4.6%, 6820.HK op -3.9%) pass only because roce is positive (net-cash) — thesis-consistent.

## durable_reinvestment (L728) — CLEAN
Genuine ROIC compounders (PRDO, HRMY, ESEA, APH, MOH). `roic_lindy>=0.10`, `n_yrs_positive_roic>=4`,
sane ROIIC band [0.15,1.0], asset growth, `_roce_now_ok`. No melters. Exactly the Mauboussin signature.

## cash_reinvest (L739) — CLEAN
Same shape on cash ROIIC (YALA, HRMY, ACN, CPRX). Sane bands, positive base, no melters. Clean.

## roic_inflect (L750) — CLEAN (minor note)
Thesis is "just crossed zero from below," so a **negative `roic_lindy`** among firers (XNET -0.01,
TUYA -0.15, QTWO -0.22, TPC -0.01) is expected, not a defect — the gate requires current op_margin>0,
cash_roic_lindy>0 and rev_yoy>0 to confirm the inflection is real. Only borderline names: XNET
(roce 0.5%, op 1.4%) and DJCO (roce 2.3% — a Munger securities holdco, thin operating base). Optional
downrank: a modest `op_margin > 0.02` floor would trim the thinnest inflections without hurting the thesis.

## cheap_per_roiic (L761) — CLEAN (minor note)
Has `_not_melting`. Real reinvestment-yield names (HRMY, SBC, CLMB, TDC). The `roic_lindy>=0.05` floor
is low and admits marginal reinvestors whose FCF is capex/wc-negative (NUS roic_lindy 0.071, fcf -25%;
LFVN fcf -3%). op>0 so `_not_melting` passes. Minor; a downrank of roic_lindy<0.10 would sharpen.

## lindy_margin (L798) — CLEAN
`_roce_now_ok`, op/EBITDA-margin-lindy bands with caps (0.6 / 0.8) that correctly reject royalty/one-off
prints. High `roic_lindy` artifacts among firers (QDMI 15.6, STG 1.22) are harmless here — the gate is
on the capped *margin-lindy*, not roce. 4/637 capex-heavy edge melters (UHAL, EPM). Sound.

## lindy_fcf (L809) — CLEAN (one edge leak)
`_roce_now_ok` + 5y history + 4/5 FCF + 4/5 op-income. Strong (STG, USNA, GASS, PRDO). One leak: **DSNY**
(op -21.6%, fcf -0.8%, roce **NaN**) slips through because `_roce_now_ok` is permissive on NaN roce and
this gate lacks `_not_melting`. Single name; fix folded into the group recommendation below.

## no_dilution (L827) — **PROMOTES-JUNK (highest priority in group)**
Defect: this is the **only** EDGAR-durability gate in the group with **no current-state floor** — it has
neither `_roce_now_ok` nor `_not_melting`. It fires on any name with flat share count + 4/5y positive
FCF + 4/5y positive ROIC *history*, so melting-ice-cube names that WERE clean compounders but are
loss-making/over-levered NOW qualify as "clean compounders."
- **51 non-financial firers fail a basic current-state floor** (roce<-5% OR op&fcf<0 OR net_debt/EBITDA>8x);
  22 are confirmed op&fcf melters.
- Examples: **MED** (net_debt/EBITDA **84.9x**, roce -7.7%, op -2.5%; ETA 0.448), **BRLT** (roce -19%,
  op -8.9%), **PUBM** (op -24%, roce -11%), **SLP** (op -76%, roce -58%), **CNC/Centene** (roce -24%).
- Fix: add the two legs its siblings (lindy_fcf/owner_operator/buyback_compounder) already carry:
  `df['arch_no_dilution'] = ( is_operating & _roce_now_ok & _not_melting & (...existing share/FCF/ROIC legs...) )`.
  This drops all 51 while keeping every genuine clean compounder (USNA, PRDO, SKY, HRMY unaffected).

## capital_returner (L866) — CLEAN
The `_covered` FCF leg works: **0** true operating (op&fcf) melters among 2,351 firers. Top firers are
net-cash HK/KR/TH microcaps yielding 5-30% — the breadth edge working as intended. The 139 roce<0 rows
are negative-book / foreign-book artifacts (e.g. MKTW roce -75% while op +15%, fcf +73%), not junk.

## balance_sheet_return (L888) — CLEAN
Distinct thesis (returns funded off the balance sheet / negative-EV runoff), correctly separated from the
FCF-covered returner and correctly excluding financials/REITs from the neg-EV leg. roce artifacts among
firers (JAMESWARREN.BO roce 1.00 — the base-effect the code itself flags) are irrelevant: the gate
doesn't key on roce. Cash-rich Asian nano/microcaps at 0.2-0.8x book — genuine, currency-neutral cheap.

## low_sbc_quality (L899) — CLEAN (two thin edges)
`_roce_now_ok` + real returns floor + not-a-diluter + present-and-low SBC (the missing-SBC loophole was
already closed). 0 confirmed melters. Two thin edges where a stale-positive roce co-exists with a
collapsed current op margin: **EDUC** (op -57%, roce +15.8%) and **KPLT** (fcf -41%, roce 105% on a
near-zero/negative equity base — subprime BNPL, questionable "quality"). Optional: a `_not_melting` add
or an `op_margin > 0` leg would drop EDUC. Low priority (2 names).

## tax_efficient (L916) — CLEAN
Narrow, well-guarded thesis: etr in [3%,15%), pretax>0, op_margin>0. All firers meet it. Negative
`roic_lindy` among firers (TUYA, RERE, QTWO, YEXT) and MKTW's -75% roce are other-archetype-driven ETA
and irrelevant to the tax-structure claim — these names top the sort because of *other* tags.

## strong_coverage (L932) — CLEAN per its narrow thesis (mild note)
Balance-sheet-safety claim, not an operating-quality claim, so the 235 "operating melters" among 5,880
firers are almost all **deeply net-cash** (4301.T nde -8.2, 0882.HK -4.0, 9990.HK -225) — coverage is
literally true for them, so this is thesis-consistent, not junk. Mild concern: the `interest_coverage>=8`
leg can, in principle, tag an operating+FCF melter that is NOT net-cash as "strong coverage." Optional
tightening (see fix #3). mcap>=$50M floor is defensible (coverage is not a nano concept) and sits below
the $100M sweet-spot ceiling, so it does not cut the multibagger cohort.

## quiet_compounder (L1059) — **EXCLUDES-GOOD**
Only **22 firers** — the tightest gate in the group, and its thesis ("boring durable compounder before
it gets discovered," Mayer's 100-bagger sample) is *definitionally* the neglected name, yet it is
US-EDGAR-only (via `roic_lindy>=0.15` + `n_yrs_roic_pos>=4` + `years_of_history>=5`). The entire non-US
neglected-compounder universe scores 0 here. The momentum band [-0.10,0.30] is fine (wants an un-noticed
flat tape), but the ROIC requirement has no global fallback.
- Fix: add a non-US current-returns path so the same thesis fires globally, e.g. OR-in
  `( ~is_us & (s('roce')>=0.15) & (insider>=0.10) & (~(shares_yoy>0.03)) & _not_melting )`.
  Keeps the US EDGAR-corroborated path as the strong signal; opens the neglected global cohort.

## buyback_compounder (L1084) — CLEAN
`_roce_now_ok`, real share-shrink with a reverse-split guard (`buyback_yield` corroboration), roic_lindy>=0.08,
4y ROIC history, nde<=1.5. **0** melters. Textbook (USNA, PRDO, HRMY, MOMO, TDC). Clean.

## owner_operator (L1096) — **EXCLUDES-GOOD (+ one edge leak)**
Same US-EDGAR-only structural limit as quiet_compounder, and the thesis (Russo/Mayer owner-operator with
skin in the game) is again inherently a neglected-name thesis. insider>=0.20 + 4/5y ROIC&FCF + flat shares
+ current-state floor. Genuine (USNA, GASS insider 0.35, GIC insider 0.52, ELA insider 0.74). Two points:
(a) global blind spot — an owner-operated non-US microcap can't qualify; consider the same non-US current-roce
path as quiet_compounder. (b) one edge leak: **DSNY** (op -21.6%, fcf -0.8%, roce NaN) passes because
`_roce_now_ok` is NaN-permissive and the gate lacks `_not_melting`.

## large_cap_quality (L1168) — CLEAN (two notes)
Correctly requires a real returns floor (roce>=0.10 & not one-off-suspect, OR roic_after_sbc>=0.15, OR
roic_lindy>=0.12) so a low-ROCE cyclical giant on a 1.5% dividend can't back in. Firers are genuine large
franchises (Ericsson, CSPC, Galaxy, Yangzijiang, Sino Biopharm, Anglo Plat, CICC). Notes: (1) the firer
list is inflated by **duplicate OTC ADR lines of the same company** (GXYEF/GXYYY, CICOY/CICOF, CHJTF/CSPCY,
SBMFF/SBHMY) — redundancy, not junk, but worth a dedupe on the display side. (2) two names carry
negative current op_margin on a high (possibly stale) roce — ERIXF (op 0.0, roce 29.6%) and 7270.T/Subaru
(op -2.1%, roce 43%); both pass on `ebitda_margin_sane>=0.15` + roce. Mild; a `roce`-freshness cross-check
against op_margin would catch the stale-roce case.

---

## Top 3 highest-priority fixes (this group)

1. **no_dilution (L827) — add a current-state floor.** Insert `& _roce_now_ok & _not_melting` (the exact
   legs its siblings already use). Removes 51 melting/over-levered "clean compounders" (MED at 84.9x
   net-debt/EBITDA, BRLT, PUBM, SLP, CNC) with zero cost to genuine names. Clear PROMOTES-JUNK, one-line fix.

2. **quiet_compounder (L1059) & owner_operator (L1096) — add a global (non-US) path.** Both encode
   neglected-microcap theses but are US-EDGAR-only, so the entire non-US cohort scores 0 (quiet_compounder
   fires on just 22 names). OR-in a current-returns path: `(~is_us & (roce>=0.15) & (insider>=threshold)
   & ~(shares_yoy>0.03) & _not_melting)`, preserving the EDGAR path as the corroborated signal.

3. **Close the NaN-roce operating-melter leak across the durability family (L809 lindy_fcf, L1096
   owner_operator).** `_roce_now_ok` is permissive when roce is NaN, so NaN-roce op&fcf melters (DSNY)
   slip through gates that lack `_not_melting`. Add `& _not_melting` to both. (Same edit also hardens
   strong_coverage's non-net-cash interest-coverage leg if applied there: require
   `(op_margin>0) | (nde<=0) | (net_cash_pct_sane>=0.20)` alongside the coverage claim.)
