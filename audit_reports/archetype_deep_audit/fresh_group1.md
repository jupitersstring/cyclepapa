# Fresh Archetype Quality Audit — Group 1 (27 archetypes)

Method: top-10 by `entry_today_asymmetry` (ETA, the book sort key) vs the stated
thesis in `archetype_tags.py`. Fresh-eyes representativeness + methodology read,
not a red-flag re-hunt. Guarded items (per brief) not re-flagged.

## Cross-cutting findings (read first)

1. **Ranking is archetype-agnostic.** Every book sorts on ETA, a generic
   cheap+beaten+high-FCF asymmetry score. So the *same ~10 names*
   (Z Holdings, Dongwoo, Medialink, Gevelot, Kokusai / and on the EDGAR side
   JFIN, USNA, YALA, HRMY, PRDO) float to the top of many different archetypes,
   and the *best thesis-fits* (Heico, Amphenol, Dolby) sit BELOW cheaper
   decliners. For pattern-specific archetypes (quality, inflection) the "top of
   book" is "highest-ETA names that also fire," not "most archetypal names."
   This is the single biggest lever: a thesis-aligned tiebreak/secondary sort
   would fix representativeness across the whole group without touching gates.

2. **The "quality" floor leaks low-ROCE names.** Wherever the returns floor is
   `_roce_now_ok` (NaN-permissive: only blocks *negative* current ROCE) or an
   OR-branch (dividend OR roic), low-single-digit-ROCE cyclicals and near-zero-
   return names reach the very top of QUALITY archetypes (qarp, large_cap_quality,
   midcap_garp, cash_quality, no_dilution). A real *magnitude* floor is missing.

3. **JFIN (Jiayin Group)** — a Chinese consumer/P2P LENDER classed
   "Communication Services" — escapes the financials guard and appears near the
   top of 8 operating-compounder archetypes (durable_reinvestment, cash_reinvest,
   lindy_margin, lindy_fcf, no_dilution, owner_operator, qarp, reinvest_inflect),
   despite -10% revenue and -82% 12m momentum. Worth a business-model/name spot-check;
   sector-only gating can't catch a misclassified lender.

---

## NEEDS-WORK

### arch_cheap_per_roiic — NEEDS-WORK
Top-10 badly off-thesis. #1 KPLT (Katapult) is a lease-to-own fintech with
**-41% FCF yield**; CATO (#2, ROE ~0.05%, EV/EBITDA 134) and TLF (#7, op margin
0.02%, ROE -4%) are near-dead retailers; THRY collapsing (-73% mom). The
`roiic_lindy>0.10` leg catches one-off EDGAR windows and the "cheap" ratio is
polluted by corrupt EV/EBITDA (134x, 56x). `_roce_now_ok` is NaN-permissive so
no quality floor bites. *Fix:* require positive current FCF/ROCE magnitude and a
sane EV/EBITDA band on the cheapness leg.

### arch_tangible_value — NEEDS-WORK
Only 5 firers; **3 (MOS, BATL, HPK) are cash-burning cyclicals** — Mosaic (FCF
yield -18%, ROE 0.6%, P/E 160), Battalion Oil (FCF yield -153%, ROE -29%, rev
-14%), HighPeak (ROE -9%, rev -23%). All pass the "real cash generation" leg via
the `cfo_ttm>0` fallback while FCF is deeply negative (capex burn). Only JRSH/GIII
are clean asset-value floors. *Fix:* the cfo>0 OR-branch defeats the intent —
require positive FCF (or a non-negative ROE) alongside the P/TB<0.7 floor.

### arch_large_cap_quality — NEEDS-WORK
Labeled "durable high-quality franchise… compounding at a high rate," but the
top is **low-ROCE cyclical giants** qualifying via the 1.5% dividend OR-branch,
not on returns: Ericsson (ROCE 3.3%), Yangzijiang Shipbuilding (4.4%), Anglo
American Platinum (5.7% — a PGM miner), Subaru (4.8%, *negative* op margin),
Kuaishou (1.9%), Sino Biopharma (2.1%). EBITDA-margin≥15% + a dividend is not
quality on a capital-heavy base. *Fix:* move a real returns floor
(roce/roic ≥ ~10-12%) into the AND core rather than leaving it as one OR-branch.

### arch_midcap_garp — NEEDS-WORK
Growth+value legs fine, but the "quality" proxy admits low-ROCE cyclicals at the
very top: #1 Jet2 (airline, **ROCE 1.2%**), #2 Raven (**ROE -17%**), #3 Ternium
Argentina (steel, hyperinflation-distorted, ROCE 4.1%), #8 Inner Mongolia Erdos
(coal/chem cyclical). The `_roiic_proxy` (EBITDA-margin OR ROE, + "improving")
lets margin-heavy but low-return names read as quality. *Fix:* tighten the proxy
with a returns floor; guard hyperinflation-accounting geographies (Argentina).

### arch_qarp — NEEDS-WORK
"Quality At Reasonable Price" whose **#1 is JFIN** (collapsing sub-prime Chinese
lender, -82% momentum) and #4 MHH (Mastech, **ROCE 0.002%**). `roiic_lindy≥0.15`
catches one-off incremental-return windows; the NaN-permissive `_roce_now_ok`
never floors current quality magnitude. The rest (PRDO, HRMY, Netease) are fine.
*Fix:* add a current returns-magnitude floor and a momentum/trajectory sanity gate.

### arch_dead_option — NEEDS-WORK
"Option mispriced as dead" wants a beaten-down *cash cow*, but **#2 is TTEC**
(ROE -101%, revenue declining, -60% momentum) — a genuine melting ice cube whose
5%+ cash yield is a one-off FCF spike. The gate (op_margin>0 & ebitda_margin>0 &
nde≤3) has **no returns floor** (`_roce_now_ok` absent here), so a near-zero-
operating-margin decliner qualifies. *Fix:* add `_roce_now_ok` (or a revenue/
momentum floor) as the sibling survivability archetypes have.

---

## MINOR

- **arch_narrative_lag** — MINOR. Legs sound (advance-breadth≥2 + cheapness);
  top is coherent cheap-turning value. Very broad (4,230) and ETA-ranked, so the
  "lagging *improving* fundamentals" distinction isn't visible at the top.
- **arch_fixed_cost_demand_shock** — MINOR. Sector gate includes Consumer
  Discretionary, so **#1/#? Z Holdings (an internet retailer)** surfaces in a
  fixed-cost operating-leverage thesis — no fixed-asset engine. Sector proxy is
  coarse; otherwise the rev-accel + margin-shock legs are right.
- **arch_discounted_vehicle** — SOUND-leaning. Clean net-cash sub-book: every
  top name P/B<0.85 with net *cash* (nde<0). Faithful. (Verdict: SOUND.)
- **arch_capital_discipline** — MINOR. Top has **no actual buyback/share-shrink**
  — all qualify via the `insider≥0.20 + returns` path, making it a generic
  high-insider value screen indistinguishable from siblings. Faithful to the
  proxy, but the "capital ALLOCATION action" spirit isn't what surfaces on top.
- **arch_regime_cyclical** — MINOR. Same Z-Holdings/CD + Utilities (LongiTech,
  op margin -1.4%) sector coarseness as fixed_cost. Inflection legs are sound.
- **arch_kpi_threshold** — MINOR. Genuine first-positive + margin-confirm legs;
  broad (2,652) and ETA-ranked so the top is the usual cheap names, inflection
  magnitude not rewarded.
- **arch_blindspot** — MINOR. Intentionally pure geography+size+ADV with **no
  quality floor**, so junk like ENEFI (op margin -288%) reaches #5. Acceptable if
  quality is judged downstream, but a light survivability floor would help.
- **arch_micro_activist_inflect** — MINOR. Quant half only (activist board +
  backlog left to scraper), so top = generic cheap profitable inflecting
  microcaps, not distinctively "activist." As designed, but not self-sufficient.
- **arch_durable_reinvestment** — MINOR. Mostly right (Netease, Perdoceo, Climb),
  but the lindy window catches **cyclical up-cycles** (Euroseas shipping) and
  decliners (JFIN #1, rev -10%) as "durable compounders." A cyclicality/trajectory
  screen would tighten it.
- **arch_cash_reinvest** — MINOR. Core is good (Amphenol, Dolby, DoubleVerify,
  Global Industrial). YALA/JFIN are the weak tops via ETA.
- **arch_roic_inflect** — MINOR. Legitimate zero-cross + cash-confirm + rev>0 +
  op>0 gate; some beaten names (SSTK -75% mom) at top, which is defensible for an
  inflection thesis.
- **arch_lindy_margin** — MINOR. "Durable margin" but ETA pulls **beaten-down
  decliners that USED to have high margins** to the top (STG -56% mom, JFIN, MOMO
  rev -9%). Backward-looking by design; a current-trajectory floor would restore
  the "durable" spirit.
- **arch_lindy_fcf** — MINOR. 4/5-year FCF durability test is structurally sound;
  ETA re-orders toward cyclical shippers (IMPP, GASS) and STG at the top.
- **arch_no_dilution** — MINOR. Non-dilution + FCF/ROIC-positive test is faithful,
  but "clean compounder" oversells: no returns-magnitude floor, so MHH (ROCE
  0.002%) and decliners (JFIN, MOMO) reach the top.
- **arch_lindy_growth** — MINOR. Majority are real growers (Elite, Smith-Midland,
  AppFolio, Alarm.com), but several top names have **currently declining revenue**
  (OPRX -3% & -62% mom, PRCH rev down & ROE -103%, QDMI collapsing) despite a
  "durable growth" label. Add a current rev_yoy floor; `_roce_now_ok` (roce-only)
  let PRCH's -103% ROE through as the code comment intended to block.
- **arch_quiet_compounder** — SOUND. Best-designed in the group: the -10%..+30%
  momentum band enforces "proven but undiscovered." Top reads exactly right —
  Heico, Iradimed, Omega Flex, Nathan's, Nobility Homes, Mind CTI. (INMD the only
  soft spot, rev -19%.)
- **arch_buyback_compounder** — MINOR. Mostly genuine shrinkers (USNA, Perdoceo,
  Skyline, Criteo, EPAM); MOMO (flat shares, corrupt FCF, declining) the weak top.
- **arch_owner_operator** — MINOR. Insider≥20% + 4/5 ROIC/FCF + non-dilution core
  is sound, but MHH (ROCE ~0), SSTK (-75% mom, ROE -4%) and JFIN leak in; the
  `rev_yoy>-0.15` floor is loose and there's no returns-magnitude floor.
- **arch_reinvest_inflect** — MINOR. Good names present (Amphenol, Ubiquiti, ISSC,
  Envela), but **#1 ACTG (Acacia)** is a lumpy IP-litigation holdco (ROE -3%,
  revenue driven by settlements) whose "ROIIC acceleration" is a one-off; JFIN
  again. A revenue-quality/recurring check would help.
- **arch_double_inflect** — MINOR. Pure two-signal (NOPAT-ROIC + cash-ROIC cross
  + rev>0) inflection; small (26). Cyclicals dominating (SSR gold, Bassett, LSB)
  is appropriate for an inflection; the weak tops are corrupt-multiple micros
  (FEDU, HLP). Structurally the cleanest inflection rule.
- **arch_cash_quality** — MINOR. cash-ROIC-minus-NOPAT-ROIC ≥5% + 4/5 FCF +
  non-dilution is a legit quality-of-earnings tell; MHH (ROCE ~0) and SSTK
  (collapsing) leak to the top via ETA + NaN-permissive roce floor.

---

## Verdict table

| Archetype | Verdict |
|---|---|
| cheap_per_roiic | NEEDS-WORK |
| tangible_value | NEEDS-WORK |
| large_cap_quality | NEEDS-WORK |
| midcap_garp | NEEDS-WORK |
| qarp | NEEDS-WORK |
| dead_option | NEEDS-WORK |
| narrative_lag | MINOR |
| fixed_cost_demand_shock | MINOR |
| capital_discipline | MINOR |
| regime_cyclical | MINOR |
| kpi_threshold | MINOR |
| blindspot | MINOR |
| micro_activist_inflect | MINOR |
| durable_reinvestment | MINOR |
| cash_reinvest | MINOR |
| roic_inflect | MINOR |
| lindy_margin | MINOR |
| lindy_fcf | MINOR |
| no_dilution | MINOR |
| lindy_growth | MINOR |
| buyback_compounder | MINOR |
| owner_operator | MINOR |
| reinvest_inflect | MINOR |
| double_inflect | MINOR |
| cash_quality | MINOR |
| discounted_vehicle | SOUND |
| quiet_compounder | SOUND |
