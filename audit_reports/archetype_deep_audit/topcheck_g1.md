# Top-10 vs Measure — Verification Sweep (group 1, 29 archetypes)

Method: `scratch_diligence_dump.py <arch>` ranks 1-10 cross-read against the
measure legs in `archetype_tags.py`; suspect rows re-checked against
`asymmetry_global.csv` and `edgar_roic_roiic.csv`. Data as of 2026-09-10 rebuild
(event sleeve + ghost-dedup passes).

## Verdict table

| archetype | verdict | one-line |
|---|---|---|
| arch_narrative_lag | PASS | top-10 all tape-down + multi-leg advance + cheapness anchor; only blemish is the 042420.KQ mislabeled row (see cross-cutting) |
| arch_fixed_cost_demand_shock | PASS | heavy-asset, rev rising, margin shock all honoured (WITHTECH ebitda +24% / op -26% is a D&A gap, within letter) |
| arch_discounted_vehicle | PASS | all top-10 pb<0.85, genuine net cash, no contradicting net debt |
| arch_capital_discipline | PASS | every name clears the returns floor + op-profit + nde legs (Gevelot passes on the intended fcf-yield fallback) |
| arch_regime_cyclical | PASS | beaten-down heavy-asset with confirmed margin turn; notes: Dong A Eltek corrupt-ish roce 138%/rev +234%, Austem passes depth only via 5y-range lens at +16% momentum |
| arch_dead_option | **FLAG** | YHEKF corrupt cross-list line (fcf_yield 72%, net cash 478% mcap) double-counting 9923.HK; WEBJF passes "beaten down 40%" with a zero/absent tape |
| arch_kpi_threshold | PASS | first-positive + margin/roce confirm all consistent |
| arch_blindspot | PASS | country/mcap/ADV only, by design (ENEFI.BD op margin -288% is ugly but blindspot makes no quality claim) |
| arch_micro_activist_inflect | PASS | microcap, cheap, net-cash, growing; China ITS op -4.6% tolerated by design (FCF-positive) |
| arch_durable_reinvestment | PASS | high-ROIIC franchises; note: Greek shippers (ESEA/DAC) qualify on 2020-24 boom-cycle lindy — cyclical, but the measure is history-based by design |
| arch_cash_reinvest | PASS | note: YALA rank-1 "reinvestment" is largely a growing cash pile (rev -0.8%, net cash 141% mcap) — asset_3y_cagr counts cash accumulation |
| arch_roic_inflect | PASS | genuine zero-crossings with rev growth + positive op margin; SSTK's inflection is merger-accounting noise (rev +87.6% acquisition) — letter holds |
| arch_cheap_per_roiic | **FLAG** | KPLT / CATO / TLF / THRY: ROIIC on a NEGATIVE or ~0 base ROIC = loss-narrowing, plus stale-EBITDA cheapness (details below) |
| arch_tangible_value | **FLAG** | HPK — a comment-named exclusion — still fires (fcf guard threshold too loose); only 3 firers total |
| arch_lindy_margin | PASS | note: USNA current op margin 5% is below the 10% lindy bar (history-based measure, roce-now floor passes) |
| arch_lindy_fcf | PASS | note: TRS net_debt_ebitda prints -10.1 with real debt (d/e 0.34) — corrupt-looking sign |
| arch_no_dilution | PASS | shares flat + FCF/ROIC streaks all real |
| arch_lindy_growth | **FLAG** | QDMI ($13.9M revenue — the sub-$20M growth guard is absent from this leg) and PRCH (comment-named roe -1.03 exclusion still fires) |
| arch_quiet_compounder | PASS | 22 firers, all proven-ROIC / low-momentum / insider-aligned |
| arch_buyback_compounder | PASS | real shrinkage + ROIC history + clean balance sheets |
| arch_owner_operator | PASS | insider>=20% + multi-year streaks honoured (MHH at ~0% current roce is history-carried, letter allows) |
| arch_qarp | PASS | quality-at-price gates honoured (TDC roe 118% is a small-book artifact, roce/valuation real) |
| arch_reinvest_inflect | PASS | note: ACTG rank-1 is an acquisition holdco (see capital_light_pivot flag) but clears all legs |
| arch_double_inflect | **FLAG** | MSGM (+66% dilution, one-off 68.5% EBITDA margin on $11M rev) and MVST (TTM fcf -15%, nde 75x) — no current-cash/dilution corroboration leg |
| arch_cash_quality | PASS | cash>NOPAT gap names all FCF-real (MHH thin-margin but genuinely cash-generative) |
| arch_large_cap_quality | **FLAG** | worst of the sweep: 8/10 of the top-10 are corrupt OTC cross-list lines; CSPC fires 3×, Galaxy 3×; comment-named exclusions Ericsson and Subaru re-admitted on corrupt roce |
| arch_midcap_garp | **FLAG** | RV1.F = Raven Industries, delisted (acquired by CNH 2021) stale ghost at rank 2; IZZ.F Frankfurt dup of TAL; 900936.SS fcf_yield 99% B-share currency artifact |
| arch_capital_light_pivot | **FLAG** (soft) | ACTG rank-1: "pivot" is an M&A roll-up spending a cash pile (rev +133% acquired, roe -2.9%) — organic asset-light spirit violated |
| arch_capital_returner | PASS | all top-10 are real 5-10% dividend payers with positive FCF coverage |

**Totals: 21 PASS / 8 FLAG** (one soft).

---

## FLAG details

### arch_large_cap_quality — corrupt OTC cross-list lines dominate the top (worst flag)
Measure: mcap>=10B, sane margin, cash-generative, nde<3, **returns floor**
(`roce>=0.10 | roic_after_sbc>=0.15 | roic_lindy>=0.12`), payout.

- **ERIXF (Ericsson)** rank 1: ev_ebitda **0.38**, fcf_yield **91%**, pb 0.32, op_margin 0.0 —
  local-currency (SEK) fundamentals divided into USD OTC market data. The archetype's own
  comment names Ericsson as the reason the returns floor exists; the corrupt roce 29.6%
  (real ~5-8%) re-admits it. **Root-cause leg: the returns floor and cash gates evaluated on
  currency-mismatched OTC-line ratios — the "wrong-price ghost" class leaking on F/Y lines.**
- **CHJTF + CSPCY + 1093.HK (CSPC Pharmaceutical)**: same company fires **three times**;
  the two OTC lines carry corrupt ev_ebitda 0.61/0.68 and fcf_yield 29% vs the primary
  1093.HK's sane 9.57× / 3.9%. Cross-listing triple-count, two of them in the top-10.
- **GXYEF + GXYYY + 0027.HK (Galaxy Entertainment)**: same pattern — ev_ebitda 0.106 / 0.042
  on the OTC lines vs 9.8× on 0027.HK; both OTC lines in the top-10.
- **7270.T (Subaru)** rank 7: roce prints **43.2%** with op_margin **-2.1%** and roe 3.3% —
  internally contradictory (real Subaru roce ~10%, op margin ~+7%). The comment names
  Subaru as an intended returns-floor exclusion, and indeed the ADR line FUJHY (roce 3.1%)
  correctly does NOT fire — the Tokyo line's corrupt roce leaks it back in.
  **Leg: `roce>=0.10` on a corrupt roce value.**
- YSHLF / SBMFF / KUASF / AGPPF: same OTC-line family with 17-70% "fcf yields" and sub-2×
  ev_ebitda for mega caps — all suspect denominators.

### arch_cheap_per_roiic — ROIIC on a negative/zero base = loss-narrowing, not reinvestment yield
Measure: `cheap_per_roiic <= 1.5 & roiic_lindy > 0.10` (+roce-now, not-melting). There is
**no `roic_lindy > 0` or `n_yrs_positive_roic` leg**, unlike every sibling ROIC archetype.

- **KPLT (rank 1)**: fcf_yield **-40.7%**, roic_lindy **-0.151**, n_yrs_positive_roic **0**,
  roce 105% (near-zero-capital denominator artifact), negative equity (pb NaN). Its
  roiic_lindy 0.63 is a delta off a negative base — losses narrowing, the exact class the
  in-code comment "(fresh) ... not a cash-burner (KPLT fcf-41%)" claims to have fixed.
  `_not_melting` only fails on `op_margin<0 AND fcf<0`; KPLT's positive op margin lets the
  -41% cash burner through. **Leg: missing positive-base-ROIC gate + `_not_melting` blind
  to op-positive/FCF-negative burners.**
- **CATO (rank 2)**: current ev_ebitda **134×**, net_debt_ebitda **29.5×**, ebitda margin
  0.4%, roe 0.06% — earnings have collapsed; cheap_per_roiic_lindy 0.0996 is computed off a
  stale/EDGAR EBITDA. roic_lindy -0.066, n_yrs 2. Same missing-base leg + stale numerator.
- **TLF (rank 7)**: ev_ebitda 56.5×, op margin 0.02%, roe -4.4%, fcf -5.1%; roic_lindy 0.017.
- **THRY (rank 8)**: net debt 166% of mcap, rev -6.4%, shares +19.7% YoY, asset_3y_cagr
  -16.4% — a shrinking, diluting decliner reading as "cheap reinvestment".

### arch_lindy_growth — guarded classes leaking through this leg
- **QDMI (rank 2)**: revenue_ttm_usd **$13.9M** — below the $20M floor the sub-scale-growth
  guard applies elsewhere (lines 1010/2296/... of archetype_tags.py) but **arch_lindy_growth
  has no revenue floor**. roic_lindy prints 15.6 (1,559% — denominator corruption),
  n_yrs_positive_roic 1, roce 149.6%, momentum -55.9%. A reverse-merger nano leaking into a
  "durable growth" tag. **Leg: missing `revenue_ttm_usd >= 20e6`.**
- **PRCH (rank 10)**: roe **-1.03** — the archetype's own comment cites "PRCH roe -1.03" as
  the reason for the loss-maker gate, but `_roce_now_ok` tests only roce (+10.3% on negative
  equity), so the named exclusion still fires. fcf -1.1%, nde 2.77, pb NaN (negative equity).
  **Leg: `_roce_now_ok` roce-only; no roe/equity corroboration.** (PRCH also tops
  arch_double_inflect.)

### arch_double_inflect — no current-cash or dilution corroboration
Measure: NOPAT-ROIC and cash-ROIC both crossed zero + rev_yoy>0. No `_roce_now_ok`,
`_not_melting`, dilution, or margin-sanity leg.

- **MSGM (rank 5)**: shares_yoy **+65.7%** dilution, "ebitda margin" **68.5%** on $11.3M
  revenue (one-off gain, above the 60% `ebitda_margin_sane` cap other archetypes use), roe
  1.36 (equity-crossing artifact), momentum +96%. A serial-diluting near-shell whose
  "cash inflection" is a one-off. **Leg: no dilution / one-off-margin guard.**
- **MVST (rank 8)**: TTM fcf_yield **-14.9%**, net_debt_ebitda prints **75.1×**, p_e 193,
  momentum -87%. The cash-ROIC inflection is an annual-EDGAR print contradicted by the
  current TTM cash burn — "confirms the inflection is real cash" is violated now.
  (Secondary: BSET fcf -16.3% at rank 2, same missing current-cash leg.)

### arch_dead_option — stale/corrupt tape lines
- **YHEKF (rank 2)**: OTC line of Yeahka; fcf_yield **72%** and net cash **478% of mcap**
  vs the primary 9923.HK's 10.7% / 71% — HKD fundamentals over USD OTC denominators.
  Both lines fire arch_dead_option (also both fire narrative_lag and capital_discipline) —
  a residual cross-listing double count with the corrupt line ranking higher.
  **Leg: `_cash_yield_any` on a currency-mismatched line.**
- **WEBJF (rank 3)**: price_yoy 0.000, momentum 0.000, pct_off NaN — no present tape at all,
  yet passes `beaten_down_any(0.40)` via the 5y-range proxy lenses (the primary-52w veto
  can't act because pct_off is NaN). The G5 "genuine, PRESENT, non-zero tape" fix was applied
  to narrative_lag but not to beaten_down_any. **Leg: 5y-range lens with no present-tape
  requirement.** (Also an OTC line of ASX-listed WEB.AX.)

### arch_tangible_value — comment-named exclusion still firing
- **HPK (rank 3 of only 3 firers)**: the leg comment names HPK as excluded ("BATL fcf -153%,
  MOS, HPK"), but the guard is `~(fcf_yield < -0.15)` and HPK's fcf is now **-1.2%**, so it
  passes. roe -9.3%, rev_yoy -22.7%, nde 1.65, net debt 122% of mcap — a levered, shrinking
  E&P "melting the floor". No `_roce_now_ok` on this archetype (roce +6.4% would pass anyway,
  roe is the tell). **Leg: fcf guard threshold, no current-returns corroboration.**
  Also: the archetype now has only **3 firers** — the p_tb/tangible legs may be over-tight or
  under-covered post-rebuild; worth a coverage check.

### arch_midcap_garp — stale delisted ghost + cross-list artifacts
- **RV1.F (rank 2) = Raven Industries** — acquired by CNH Industrial and **delisted Nov 2021**;
  this Frankfurt line is a stale ghost ($2.48B "mcap", frozen tape, roce **-17.3%** vs roe
  +50.7% contradictory). Passes via the `_roe>=0.15` proxy branch. **Leg: `_roiic_proxy`
  roe branch on a dead line; the dead-listing sweep missed non-US secondary lines.**
- **IZZ.F (rank 5)**: Frankfurt line of TAL Education (US ADR also in universe) —
  cross-listing double-count class.
- **900936.SS (rank 7)**: fcf_yield prints **99.1%** — Shanghai B-share (USD-quoted price,
  CNY financials) currency artifact.
- **ATAT (rank 4)**: ev_ebitda **0.074** (corrupt EV; the name passes `_val_good` on real
  p_e 16.3, so only the printed ratio is bad).

### arch_capital_light_pivot (soft) — roll-up reads as a pivot
- **ACTG (rank 1)**: revenue_3y_cagr driven by acquisitions (rev_yoy +133%), roe -2.9%,
  roce 3.6% — a holdco converting a cash pile into bought businesses. Assets grow slower
  than acquired revenue, so the letter passes, but this is not the franchise/IP/platform
  transition the measure describes. **Leg: revenue_3y_cagr has no organic/quality
  corroboration beyond `roce>=0`.** (ACTG is also rank 1 in arch_reinvest_inflect on the
  same mechanics.)

---

## Cross-cutting residuals (not per-archetype design issues)

1. **042420.KQ labeled "Z Holdings Corporation"** — KOSDAQ ticker, KRW financials
   (mcap ~$97M), but the name (and tags-side src JP) belongs to the Japanese Z Holdings /
   LY Corp (which exists separately as YAHOF/YAHOY). The row's fundamentals look internally
   KRW-consistent (i.e. it's a real Korean company wearing the wrong name), so measures pass,
   but it ranks #1-3 in ~6 of these archetypes and carries archetype_count 26 — an identity
   mislabel that will poison any book built off names.
2. **OTC/secondary-line currency mismatches** are the dominant residual ghost class:
   ERIXF, CHJTF/CSPCY, GXYEF/GXYYY, YHEKF, WEBJF, KUASF, SBMFF, YSHLF, AGPPF, IZZ.F,
   900936.SS — local-currency fundamentals over USD (or EUR) market denominators produce
   sub-1× EV/EBITDA and 30-99% fcf yields that vault these lines to the top of any
   valuation-anchored archetype. The primary-listing lines usually also fire → double/triple
   counts (CSPC ×3, Galaxy ×3, Yeahka ×2, TAL ×2, Subaru saved only because FUJHY's data
   is sane).
3. **Corrupt-looking single ratios** in tops (data notes, letter unaffected):
   088130.KQ roce 138% / rev +234%; TRS net_debt_ebitda -10.1 with real debt;
   MVST net_debt_ebitda 75×; FPIP.ST roce 72% vs roe -6.6%; 7270.T roce 43% vs op -2%.
4. **Comment-vs-code drift**: three fixes whose comments name a ticker that still fires —
   KPLT (cheap_per_roiic), HPK (tangible_value), PRCH (lindy_growth) — plus two returns-floor
   comments naming Ericsson/Subaru (large_cap_quality) defeated by corrupt inputs. Worth a
   regression convention: every comment-named exclusion becomes a mutation-test case.
