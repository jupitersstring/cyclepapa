# Rank 1-10 / 30-50 Deep Audit — QUALITY / COMPOUNDER family

Method: `scratch_diligence_dump.py <arch>` (ETA-ranked firers, ranks 1-10 + 30-50), judged against
the POST-FIX legs in `archetype_tags.py`. The recent fixes (is_operating across most of the family,
`_roce_now_ok` on durable/cash_reinvest/lindy_fcf, roce-based capital_discipline return leg,
cash_quality non-dilution gate, lindy_margin op-margin cap) are treated as landed and NOT re-flagged.
Small-cap breadth is intentional. What remains, worst-first.

Key recurring giveaway: a NEGATIVE current `roce`/`op_margin`/`roe` sitting at the TOP of a "quality"
or "durable" screen. Several rules got a partial fix (is_operating OR a non-dilution gate) but never
got the current-state returns floor, so loss-makers still rank 1.

---

## 1. arch_buyback_compounder + arch_quiet_compounder — NO is_operating gate (WORST, [C])
The family-wide `is_operating` fix SKIPPED these two. Both defs (lines 951-956, 928-936) have no
financial/REIT/utility exclusion, so book/float-artifact ROIC ranks at the very top:
- **buyback_compounder**: HNNA (Hennessy Advisors, Financials/Capital Markets, #0), **XYF (X Financial —
  Chinese consumer LENDER, roce 0.225 is a loan-book artifact, #3)**, HGBL (Heritage Global asset mgr, #6),
  GNE (Genie Energy — Utilities, #1), **WBS (Webster Financial — a BANK, ebitda_margin 0.94 artifact, #34)**.
- **quiet_compounder**: GNE (Utilities, #0), HGBL (Financials, #1), **AFG (American Financial Group —
  INSURER, roic_lindy 0.18 is float, #9)**.
Root-cause leg: missing `& is_operating`. FIX: add `is_operating &` to both defs (the exact gate the
rest of the family already carries). Highest impact — financials/utilities occupy rank #0-#9 in both.

## 2. arch_low_sbc_quality — no returns floor; roce<0 loss-makers & financials rank 1-5 ([C])
Sole quality test is still `ebitda_margin > 0.05`; is_operating is present but there is NO `roce > 0`
floor. Rank 1-10 is dominated by capital-destroyers and financials:
**SOGP (Sound Group, roce −0.956 NEGATIVE, #3)**, JFU (9F Inc — Chinese fintech, roce 0.003 ≈ zero, #1),
STG (roce 1.018 tiny-equity artifact, momentum −56%, #2), VIOT (momentum −61%, #4), SLDE (Slide
**Insurance** — sector & industry both NaN so is_operating can't catch it, roe 0.48 float, #8). Rank 30-50
adds **CCLD (shares_yoy +135% serial diluter, #38)** and QDMI (roce 1.50 shell, #41).
Root-cause leg: `(ebitda_margin > 0.05)` is the only profitability test. FIX: add `& (_roce_now_ok) &
((_roce_n > 0) | (_roic_asbc > 0))` so a negative-ROCE name (SOGP) and a near-zero-return lender (JFU)
can't pass. (SLDE also needs the null-industry financial backstop — see #10.)

## 3. arch_tax_efficient — no operating-profit floor; operating loss-makers rank 1-9 ([C])
`(effective_tax_rate<0.15) & (pretax_income_ttm>0)` — pretax income includes non-operating interest/
investment income on cash hoards, so operating losers back in:
**WIMI (ebitda_margin −0.08 / op_margin −0.09 — operating LOSS, #6)**, **SOGP (roce −0.956, #1)**,
**MKTW (roce −0.755, shares_yoy +0.23 diluting, #2)**, STG (roce 1.02 artifact, #0), FVRR (op_margin
−0.003, #9). Rank 30-50 also leaks financials with NaN sector+industry: **COF (Capital One — a BANK, #47)**,
PLGO (Pelagos **Insurance**, #39).
Root-cause leg: `(pretax_pos > 0)` is not an operating-profit test. FIX: replace/pair with an operating
floor — `(ebitda_margin_sane > 0) & (s('op_margin') > 0)` — so tax efficiency is judged on a business
that operates at a profit.

## 4. arch_lindy_growth — no profitability/returns floor; capital-destroyers rank 1-9 ([C])
Pure top-line + asset growth: `revenue_5y_cagr>=0.08 & revenue_accel_lindy>0 & asset_5y_cagr>0.03 &
years>=5`. is_operating present, but NO margin/ROIC floor:
**PRCH (Porch, roe −1.03, op_margin_lindy −0.44, roic_lindy −0.20 — deeply capital-destructive, #9)**,
QDMI ($14M shell, roce 1.50 = 150% artifact, momentum −56%, #2), **OPRX (roce 0.027 ≈ zero, op_margin_lindy
−0.099, momentum −62%, #4)**. Rank 30-50: **FEED (roce −4.49 = −449%, ebitda_margin −4.49, $3.7M shell,
NaN sector, #38)**, **SPRU (roe −0.105, fcf_yield −0.86, nde 13.3 solar-lease burner, #37)**.
Root-cause leg: growth-only, no returns gate. FIX: add `& _roce_now_ok & ((op_margin_lindy > 0) |
(roic_lindy > 0))` and a `revenue_ttm >= 20e6` floor to drop the QDMI/FEED nano shells.

## 5. arch_cash_quality — got the non-dilution gate but NOT the current-state floor ([C])
Fix added `shares_growth_3y<=0.05` + `n_yrs_fcf_pos>=4`, but there is still no `_roce_now_ok`, so
currently-negative names ride their history:
**BRLT (Brilliant Earth — roce −0.192, op_margin −0.089, shares_yoy −0.85 reverse split, net_cash_pct 3.09
shell, #37)**, **TTEC (roe −1.00 losing money, momentum −60%, #0)**, MHH (roce 0.00002 ≈ zero, #5).
Root-cause leg: no current-returns floor (unlike its siblings durable/cash_reinvest/lindy_fcf which got it).
FIX: add `& _roce_now_ok` (and it would also help to require `roic_lindy` computed on assets, not the
buyback-shrunk equity denominator).

## 6. arch_lindy_margin — op-margin cap landed, but no current-roce / return-durability floor ([C])
Cap (`op_margin_lindy<=0.6`) removed the INVA royalty-holdco, but the def has NO `_roce_now_ok` and NO
`roic_lindy>0 / n_yrs_positive_roic>=4`, so margins-held-while-returns-collapse still ranks 1:
**MKTW (roce −0.755 NEGATIVE, shares diluting, #1)**, STG (roce 1.02 artifact, momentum −56%, #0),
**JFIN (Jiayin — Chinese lender mislabeled Comm Services, momentum −82%, pct_off −83%, #5)**, MOMO
(revenue_5y shrinking, #7).
Root-cause leg: margin level over the window with no return backing. FIX: add `& _roce_now_ok & (roic_lindy
> 0) & (n_yrs_roic_pos >= 4)` so a durable-MARGIN claim is backed by durable RETURNS.

## 7. arch_wolf_compounder — no rev_yoy cap, no op-margin floor, no dilution cap ([C])
`rev_yoy_c>=0.25 & rev_accel>0 & oper_lev_any & cheap & low_sbc_wolf` — none of the prior recommended
guards landed. Base-effect spikes, operating losers, and diluters still fire:
**088130.KQ Dong A Eltek (rev_yoy +234% base-effect, roce 1.38 = 138% artifact, #6)**, **BENGALT.BO Bengal
Tea (op_margin −1.60 NEGATIVE, #2)**, 348350.KQ WITHTECH (op_margin −0.26, #4). Rank 30-50: **ADESE.IS
(shares_yoy +4.0 = +400% dilution, roe −0.009, #42)**, **DataVan (op_margin −2.42, #45)**.
Root-cause leg: `oper_lev_any` doesn't require positive CURRENT op margin; rev_yoy uncapped; low_sbc_wolf
doesn't cap issuance. FIX: cap `rev_yoy_c < 1.0`, require `(s('op_margin') > 0) | (roce > 0)`, add a
share-issuance cap (`shares_yoy <= 0.05`).

## 8. arch_capital_discipline — the roce fix is undercut by the fcf-only fallback + bare buyback leg ([C]/[T])
The roce>=0.12 return leg landed, but it's OR'd with `fcf_yield>=0.04`, and `_action_leg` (a ≥1% share
shrink / any buyback) satisfies `_own_aligned` with NO return quality at all. So low-ROCE, declining, and
negative-op-margin names pass:
**047820.KQ Chorokbaem Media (revY −30.4%, op_margin −0.002, roce 0.064 — passes on fcf_yield 0.042, #31)**,
**HGS.NS Hinduja (op_margin −0.099, roe −0.018, revY −5.8%, #49)**, 1900.HK (op_margin −0.046, momentum
−50%, #4), ALGEV.PA (pe 49.7 on roce 0.067, #7). No `_roce_now_ok` either.
Root-cause legs: the `(fcf_yield >= 0.04)` disjunct and the return-free `_action_leg`. FIX: add
`& _roce_now_ok & (price... )`—concretely, require `(s('op_margin') > 0)` and drop the bare `fcf_yield`
fallback (or pair it with `roce > 0.08`); gate `_action_leg` on a positive-return floor too.

## 9. arch_no_dilution + arch_owner_operator — stale trailing counts, no current-state floor ([C])
Both use backward-looking `n_yrs_positive_fcf/roic >= 4` with is_operating but NO `_roce_now_ok`
(recommended in the prior audit's fix #4, applied to lindy_fcf but not to these two). Collapsing/near-zero
names inherit the tag:
- no_dilution: **TRS (TriMas, revY −9.3%, #3)**, MOMO (revY −3.1%, #5), **MHH (roce 0.00002, #9)**,
  MOH (Molina — insurer via Health Care sector, ebitda_margin 0.014 float, #41).
- owner_operator: **MHH (roce 0.00002, #6)**, **SSTK (Shutterstock roe −0.038, momentum −76%, #8)**,
  TRS (revY −9.3%, #4), **IPGP (roce 0.001 ≈ zero, op_margin 0.002, #48)**.
Root-cause leg: no current-state gate on the trailing counts. FIX: add `& _roce_now_ok & (rev_yoy > −0.15)`
to both defs.

## 10. Financial misclassification via feed sector — JFIN-type lenders leak family-wide ([C])
`is_operating` trusts the data feed's `sector`. **JFIN (Jiayin Group — a Chinese consumer LENDER)** is
tagged sector = "Communication Services" / industry = "Diversified Telecommunication Services", so it
passes is_operating and ranks **durable_reinvestment #0, cash_reinvest #1, lindy_fcf #7, no_dilution #4,
owner_operator #5, lindy_margin #5**. Its ROIC/reinvestment/FCF are lending-book artifacts. Same shape:
**SLDE / COF / PLGO** (insurers/bank with NaN sector AND NaN industry — the industry backstop can't fire).
Root-cause: sector-string trust + a null-industry hole in the backstop. FIX: extend the financial-name
detection to the `name` string (`bank|financ|lending|capital|insurance`) as a last-resort backstop, and
add a returns-plausibility guard; at minimum add JFIN-class tickers to a known-financial override.

## 11. arch_strong_coverage — coverage CLAIM still never binds; pure net-cash proxy ([C], partial)
is_operating + `mcap>=50e6` + `net_cash_pct_sane` landed, but the titular `interest_coverage >= 8.0`
disjunct is still NA for every ranked non-US name, so 100% of firings ride `nde<=0 | net_cash_pct_sane>=0.20`
— a net-cash screen wearing a coverage label, redundant with the net-cash/cash-quality archetypes. Some
firers are shrinking (0882.HK revY −4.9% op_margin −7.3%) or losing at the net line (**TTEC roe −1.00,
nde −93.7 data artifact, #35**). Root-cause leg: the real-coverage disjunct is unreachable ex-EDGAR.
FIX: compute an `ebitda_ttm / interest_expense` proxy from the global feed for the coverage leg, or merge
this into the net-cash family and reserve the name for names with an actual computed coverage ratio.

## 12. arch_large_cap_quality — dividend-alone return leg lets cyclicals/holdcos pass ([T])
The 4-way return OR still lets `dividend_yield >= 0.015` alone satisfy it, and there is no globally-available
ROCE leg, so deep cyclicals and conglomerate holdcos count as "durable franchises":
**ERIXF Ericsson (op_margin 0.000 — breakeven operationally, #0)**, YSHLF Yangzijiang (shipbuilder, #3),
AGPPF Anglo Am Platinum (mining, #5), Subaru (auto OEM, roe 0.033, #6); rank 30-50 adds CDE Coeur Mining
(roce 0.074), Vedanta, CMOC, Kawasaki Kisen (shipping), **JARLF Jardine Matheson (conglomerate holdco,
roce 0.093, #38)**. (Dual-listings also double-count: GOOGN/GOOGM, CSPCY/CHJTF, SDVKF/SDVKY.)
Root-cause leg: `dividend_yield>=0.015` alone passes; ROIC legs are EDGAR-only. FIX: add a globally-available
`(roce >= 0.12)` requirement to the return gate rather than letting bare dividend yield qualify; exclude
near-zero-ROCE holdcos.

## 13. arch_wolf_seal — inflection admits negative-roce / shrinking names ([T], soft)
Momentum-inflection archetype, so weaker current returns are tolerable at entry, but `inflection_print`
still admits: **6155.T Takamatsu Machinery (roce −0.008 NEGATIVE, revY −2%, #3)**, Michang Oil (revY −6.1%,
#1); rank 30-50 **900920.SS Shanghai Diesel (op_margin −0.010, net_cash_pct 7.67 shell, #44)**, DDEJF Dundee
(op_margin −1.25 holdco, #38). Minor. FIX: tighten `inflection_print` to exclude `roce < 0` and materially
negative revenue growth.

---

## HIGHEST-IMPACT FIXES (do first)
1. **Add `is_operating` to buyback_compounder AND quiet_compounder** (#1) — the family fix missed both;
   financials/utilities/lenders rank #0-#9. One-line each, largest top-of-book impact.
2. **Add a current-returns / profitability floor to the four rules that got only a partial fix**:
   low_sbc_quality (`roce>0`), tax_efficient (operating-profit gate), lindy_growth (`op_margin_lindy>0 |
   roic_lindy>0`), lindy_margin + cash_quality + no_dilution + owner_operator (`_roce_now_ok`). This kills
   SOGP (−96%), WIMI (op loss), PRCH (roe −1.03), MKTW (−76%), BRLT (−19%), MHH (≈0) across the board.
3. **wolf_compounder guards** (#7): cap `rev_yoy<1.0`, require positive current op_margin, cap dilution —
   drops Dong A Eltek +234%, Bengal Tea op_margin −160%, ADESE shares +400%.
4. **capital_discipline** (#8): drop the return-free `fcf_yield>=0.04` fallback and the bare `_action_leg`
   pass; add an op-margin/roce floor — drops Chorokbaem (−30%) and Hinduja (op_margin −9.9%).
5. **Financial-name backstop** (#10): extend is_operating to a name-string check + null-industry hole, so
   JFIN-class lenders (and SLDE/COF/PLGO) stop polluting 5+ quality screens.

## CLEAN (no action needed)
- **durable_reinvestment** — well-gated post-fix; only soft leaks are container-shipping cyclicals
  (ESEA/DAC/GSL, Industrials so is_operating can't help) and JFIN (#10). Fine otherwise.
- **cash_reinvest** — clean except JFIN #1 (#10); ranks 30-50 are genuine compounders (URBN, LECO, INTU,
  MPWR, RMD, SCCO).
- **lindy_fcf** — `_roce_now_ok` holds; only soft residue is shrinkers with positive roce (TRS −9%, MOMO
  −3%). Optional `revenue_5y_cagr > −0.05` guard, not urgent.
