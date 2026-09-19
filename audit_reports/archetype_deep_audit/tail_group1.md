# Deep-Tail Spirit Audit — Group 1 (27 archetypes), RANKS 50-100

Method: `scratch_diligence_dump.py <arch>` (ETA-ranked firers), judgment focused on the **ranks 50-100**
band, each firer checked against the STATED SPIRIT + legs in `archetype_tags.py`. Ranks 1-50 excluded
(reviewed twice already). Already-guarded leaks (financials/REIT/utility, net-cash stubs, sub-$20M growth,
rev_yoy<0 inflections, data corruption, preferreds, sub-$2M shells, clinical biotech) are NOT re-flagged.
Local mcap columns (KRW/JPY/etc.) were not mistaken for the USD size gate. Worst-first.

Recurring root cause in the tail: an archetype whose SIBLINGS carry `_roce_now_ok` (current-returns floor)
was never given it, so a backward-looking history leg (n-yr ROIC/FCF streak, lindy margin, a first-positive
print, a margin-delta off a negative base) admits names whose CURRENT state is a loss, a collapse, or a
melting balance sheet. Same one-line fix pattern repeats.

---

## 1. arch_qarp — MISSING `is_operating` AND `_roce_now_ok` entirely (WORST, [C])
Structural gap: every EDGAR sibling (durable_reinvestment, cash_reinvest, reinvest_inflect, cash_quality)
carries `is_operating & _roce_now_ok &`; **qarp carries NEITHER** (def lines 1031-1036 are just
`roiic_lindy>=0.15 & _qarp_cheap & n_yrs_roic_pos>=4 & shares_growth_3y<=0.02`). Because there is no
`is_operating`, qarp is also a HOLE in the universe-wide financial-exclusion invariant.
- **CABO Cable One — sector=Financials, roce −0.048 NEGATIVE, op_margin −0.142, net_debt_ebitda 23.8x** (#70).
  A financials-tagged name with negative returns and 24x leverage passing "quality at a reasonable price".
- **OPFI Oppfi — subprime consumer LENDER (mislabeled sector=IT), roce NaN, shares_yoy +0.32 (+32% dilution)** (#72).
  Diluting +32% YoY yet passes the "no dilution" leg on the 3y proxy; roiic is a loan-book artifact.
- ZUMZ Zumiez (op_margin −0.079 NEGATIVE, #50).
Root-cause: the two sibling gates were never added. **FIX:** prepend `is_operating & _roce_now_ok &` to the
qarp def (the exact gate the rest of the EDGAR family carries). Plugs both the financial leak and the
negative-returns leak in one change. **[C]**

## 2. arch_owner_operator — no current-state floor; trailing-history compounders now collapsing ([C])
`insider>=0.20 & n_yrs_roic_pos>=4 & n_yrs_fcf_pos>=4 & shares_growth_3y<=0.02 & years>=5`, NO `_roce_now_ok`,
no rev floor. The prior 1-50 audit RECOMMENDED `& _roce_now_ok & (rev_yoy>−0.15)` (quality report #9); it
never landed, and the deep tail holds the worst offenders:
- **FF FutureFuel — roce −0.513, op_margin −0.569, ebitda_margin −0.412, rev_yoy −0.607 (revenue collapsing −61%)** (#98).
- **MGPI MGP Ingredients — roce −0.160, op_margin −0.263, ebitda_margin −0.463, rev_yoy −0.259** (#78).
- **KHC Kraft Heinz — roce −0.088, op_margin −0.187, ebitda_margin −0.141 (goodwill impairment)** (#79).
- NL Industries (roce −0.204, ebitda −0.297, #52); FORR Forrester (roce −0.064, op −0.249, rev −0.119, #86);
  LE Lands' End (roce −0.054, fcf_yield −0.51, #54); AMR Alpha Met (roce −0.042, rev −0.30, #88).
Root-cause leg: backward-looking `n_yrs_*` streaks with no present-state gate. **FIX:** `& _roce_now_ok &
(rev_yoy > −0.15)`. **[C]**

## 3. arch_kpi_threshold — `margin_confirming` OR-substitutes for the roce floor ([C])
Comment (line 578) says "positive ROCE today (>=5%)", but the implementation is
`first_pos_print & (margin_confirming | roce_today)` — an OR, so `margin_confirming` (any >=0.01 margin delta,
i.e. a loss NARROWING off a negative base) alone qualifies a deeply loss-making name. No `_roce_now_ok`.
- **MKTW MarketWise — roce −0.755 NEGATIVE, rev_yoy −0.213** (#56).
- **GLFGF Global Fashion Group — roce −0.446, op_margin −0.074, ebitda_margin +0.002 (barely)** (#60).
- **ILINK.BK Interlink — roce −0.185, ebitda_margin −0.042 NEGATIVE, rev_yoy −0.385, nde +13.2** (#59).
- **SIMTF SIM Technology — op_margin −0.066, ebitda_margin −0.023 NEGATIVE, nde +100** (#91).
Root-cause leg: the `margin_confirming | roce_today` disjunction. **FIX:** add `& _roce_now_ok` and require a
positive current margin `& ((s('op_margin')>0)|(ebitda_margin>0))` so a loss-narrowing print can't qualify. **[C]**

## 4. arch_micro_activist_inflect — "profitable" = ebitda_margin>=0.05 only; no op/roce floor ([C])
`profitable = ebitda_margin>=0.05` is the sole profitability test; no `_roce_now_ok`, no op_margin gate. Names
that are EBITDA-positive but bleeding at the operating line or destroying capital leak:
- **SOGP Sound Group — roce −0.956 NEGATIVE (−95.6%)** (#87).
- **PRISMX.BO — op_margin −4.074 (−407%, near-zero-revenue artifact)** (#60).
- **Shindo Eng. (290520.KQ) — op_margin −0.990 (−99%), fcf_yield −0.157, rev_yoy +2.08 base-effect** (#71).
- Cerespo (op_margin −0.214, #50); Jiransecurity (op_margin −0.190, #70); Genie Music (roce −0.224, #52).
Root-cause leg: `profitable` tests only EBITDA margin. **FIX:** `& _roce_now_ok & (s('op_margin')>0)` — an
"activist profit inflection" microcap should be operating-profitable now. **[C]**

## 5. arch_fixed_cost_demand_shock — margin-shock leg fires on loss-narrowing; no margin floor, no leverage cap ([C])
`sector∈HEAVY_ASSET & rev_accel>0 & rev_yoy>0 & (ebitda_margin_delta∈[.02,.20] | margin_shock_any)`. The margin
leg accepts a >=2-pt improvement off a deeply NEGATIVE base, and there is no positive-margin floor and no
leverage cap, so loss-makers and over-levered names read as a "demand shock with operating leverage":
- **VEEE Twin Vee PowerCats — op_margin −0.742 (−74%), roce −0.678, ebitda_margin −0.432 NEGATIVE** (#97).
- **ENM Holdings (0128.HK) — op_margin −0.459 NEGATIVE** (#73); Shinpoong Paper (op_margin −0.094, #98).
- Magnora (SVMRF) net_debt_ebitda 42.3; EOLU-B.ST (roce −0.300, ebitda −0.099, rev +2.0 base-effect, #82).
Root-cause: no operating-result floor on the "flow-through". **FIX:** `& ((s('op_margin')>0)|(ebitda_margin>0))
& (nde <= 4.0)` — the fixed-cost base must actually be covered, and the cyclical must not be drowning in debt. **[C]**

## 6. arch_regime_cyclical — same root cause as #5 (loss-narrowing "regime change", no leverage cap) ([C])
`sector∈HEAVY_ASSET & beaten_down(.20) & rev_yoy>0 & (ebitda_inflection|ebitda_first_pos|margin_delta|
margin_shock_any) & not_priced_in>.20`. No margin floor, no `_roce_now_ok`, no leverage cap:
- **NEXE.V — ebitda_margin −5.61 (−561%), roce −0.336, net_debt_ebitda 11.8** (#82).
- **ODV Osisko Development — op_margin −4.141 (−414%), ebitda_margin −2.164, roce −0.084** (#86).
- **AWLCF Awilco Drilling — net_debt_ebitda 38.3** (#97); **China Primary Energy (8117.HK) — roce −0.019,
  op_margin −0.043, net_debt_ebitda 24.8** (#99); NOVA.BK (nde 12.9, #95).
**FIX:** same as #5 — `& ((s('op_margin')>0)|(ebitda_margin>0)) & (nde <= 4.0)`. **[C]**

## 7. arch_capital_discipline — the `fcf_yield>=0.05` returns-floor disjunct lets a melting diluter pass ([C])
Post-fix def has `op_margin>0` + `_cd_returns_floor = (roce>=.10 | roic_asbc>=.10 | fcf_yield>=.05)`, but NO
`_roce_now_ok`, and the `fcf_yield>=0.05` disjunct alone satisfies "returns on capital":
- **MKTW MarketWise — roce −0.755 NEGATIVE, shares_yoy +0.231 (DILUTING +23%), passes on fcf_yield 0.73** (#95).
  A value-destroyer issuing stock is the opposite of capital-allocation discipline; the huge fcf_yield is a
  one-off. (STG Sunlands also present, roce 1.02 tiny-equity artifact, #73.)
Root-cause legs: no current-returns floor + the bare `fcf_yield` disjunct. **FIX:** add `& _roce_now_ok` (drops
MKTW immediately); optionally pair the `fcf_yield` disjunct with `roce>0`. **[C]**

## 8. arch_discounted_vehicle — net-cash leg lacks the `_netcash_not_contradicted` guard ([C])
`is_operating & pb<0.85 & (cash_gt_ev>0 | net_cash_pct_sane>0.20) & mcap<2e9`. The `net_cash_pct_sane>0.20`
leg has NO contradiction guard, so names carrying REAL positive net debt still claim a cash cushion (the exact
stale-snapshot contradiction `_netcash_not_contradicted` was built for, but it isn't wired in here):
- **Newtree (270870.KQ) — claims net_cash 77% of mcap yet net_debt_ebitda +2.12** (#91).
- **PBMPOLY.BO — net_cash 78% yet nde +0.97, roce −0.005, fcf_yield −0.174** (#98); Sungwoo Elec (nde +0.79, #67).
- Also PRISMX.BO op_margin −4.07 corrupt artifact (#92).
Root-cause leg: `(net_cash_pct_sane > 0.20)` without the contradiction guard. **FIX:** append
`& _netcash_not_contradicted` to that disjunct (same guard already applied elsewhere). **[C], moderate volume.**

## 9. arch_narrative_lag — no `_roce_now_ok`; deteriorating names read as "narrative lagging IMPROVING fundamentals" ([T]/[C])
Spirit (comment lines 462-466): price/narrative LAGS *genuinely improving* fundamentals. `_adv_breadth>=2` is
satisfiable by a margin-delta off a negative base + a stale first-positive print, and there is no current-state
floor, so deteriorating names qualify:
- **UCID.JK Uni-Charm Indonesia — roce −0.243, ebitda_margin −0.075 NEGATIVE, rev_yoy −0.180** (#52).
- **ILINK.BK — roce −0.185, ebitda_margin −0.042, rev_yoy −0.385** (#57); **GLFGF — roce −0.446, fcf_yield −0.083,
  op_margin −0.074, rev_yoy −0.059** (#60).
Root-cause: no `_roce_now_ok`; "improving fundamentals" measured off a negative base. **FIX:** `& _roce_now_ok`
(a name with negative current roce + negative margin + declining revenue has no improving fundamentals to lag).
Large archetype (4784 firers), breadth intentional — this trims only the clearly-deteriorating tail. **[T]→[C]**

---

## SOFT / TUNING (lower priority)

- **arch_no_dilution [C, 1 offender]** — **BRLT Brilliant Earth (roce −0.192, shares_yoy −0.85 = a REVERSE
  SPLIT, not a buyback, #60)** slips the `_not_split` guard via the shares_growth_3y path. No `_roce_now_ok`.
  FIX: `& _roce_now_ok` (prior audit recommended; not landed). Rest of tail clean.
- **arch_roic_inflect [T]** — inflection tolerates weak entry returns (op_margin>0 floor present), but heavily
  levered negative-roce names leak: **IHRTB iHeartMedia (nde 15.1, roce −0.007, #94)**, **CC Chemours (nde 11.8,
  roce −0.007, #91)**, SJM Smucker (ebitda_margin −0.017 impairment, #95). FIX: `& _roce_now_ok & (nde<=4.0)`.
- **arch_dead_option [T]** — `op_margin>0 & ebitda_margin>0 & nde<=3` floors already present; residual is
  deep negative-roce with positive op margin (impairment signature): **Chiyoda (roce −0.405, #59)**, Minwise
  (roce −0.386, #86), IH Ihuman (roce −0.270, #72). Optional `& _roce_now_ok`.
- **arch_large_cap_quality [T, known]** — tail continues the prior #12 pattern: deep commodity cyclicals as
  "durable franchises" via the `dividend_yield>=0.015`-alone return leg — **China Coal (rev −0.22), Shaanxi Coal
  (rev −0.14), PTT (rev −0.13)** (all roce ok but declining cyclicals). Add a globally-available `roce>=0.12`
  requirement to the return gate rather than bare dividend yield.
- **arch_reinvest_inflect [T, soft]** — reinvestment funded by heavy dilution, no issuance cap: **LIVE Live
  Ventures (shares_yoy +0.47, #67)**, MUX McEwen (+0.28, #53), BROS Dutch Bros (+0.21). All positive roce; spirit
  is ROIIC acceleration, so soft. Optional `& (shares_yoy <= 0.10)`.
- **arch_midcap_garp [data]** — one anomaly: row #70 shows symbol **COLB (Columbia Banking, a BANK) carrying the
  name "Stem, Inc." with op_margin 0.507 / ebitda_margin 0.0 / roce NaN** — a ticker/name mismatch worth a data
  check, not a rule bug. SISE.IS breakeven op_margin −0.003 (#74). Otherwise clean.

## Cross-cutting
**OppFi (subprime lender, sector mislabeled "Information Technology", name has no bank/finance keyword)** leaks
qarp #72, durable_reinvestment #75, and owner_operator; its roic/reinvestment are loan-book artifacts. The
name-string financial backstop misses "Oppfi". Overlaps the already-guarded financial-misclassification issue,
but note the `is_operating` fix in #1 does not catch it (sector is IT, not Financials) — only qarp's `_roce_now_ok`
+ dilution behaviour trims it there.

---

## CLEAN in the deep tail (no action needed)
- **arch_lindy_margin** — `_roce_now_ok` + op_margin cap hold; tail flags are share issuance / M&A on genuine
  durable-margin names (EQT, IDCC, ESP). Clean.
- **arch_lindy_fcf** — clean; only residue is positive-roce shrinkers (NUS rev −14%).
- **arch_cash_quality** — clean (all tail names positive roce; UPBD, ATHM).
- **arch_buyback_compounder** — clean; SIGA rev decline is lumpy govt orders on 33% roce.
- **arch_durable_reinvestment / arch_cash_reinvest** — clean except the OppFi misclassification (durable) and
  CORT op_margin −0.30 data noise on +14.5% roce (cash_reinvest). Well-gated post-fix.
- **arch_cheap_per_roiic** — clean; `_roce_now_ok` holds, all tail names positive roce/op margin.
- **arch_lindy_growth** — clean; tail dilution is M&A (JBT-Marel merger +61%), all positive roce, growing.
- **arch_blindspot** — a pure geography+size+ADV UNIVERSE screen with no fundamental thesis by design; financials
  present (Thai Reinsurance, Heungkuk Insurance) are the geography-universe design and covered by the universe-wide
  financial invariant, not a per-rule spirit break. Clean w.r.t. its (minimal) spirit.

## No deep-tail band (< 50 firers — nothing to audit in 50-100)
- **arch_tangible_value** (5 firers), **arch_quiet_compounder** (22), **arch_double_inflect** (26).

## Highest-impact fixes (do first)
1. **qarp**: prepend `is_operating & _roce_now_ok &` (#1) — closes a financial-invariant hole + negative-returns leak.
2. **owner_operator**: `& _roce_now_ok & (rev_yoy>−0.15)` (#2) — kills FF (−51% roce/−61% rev), MGPI, KHC.
3. **kpi_threshold**: `& _roce_now_ok & ((op_margin>0)|(ebitda_margin>0))` (#3) — kills MKTW (−75%), GLFGF, ILINK, SIMTF.
4. **micro_activist_inflect**: `& _roce_now_ok & (op_margin>0)` (#4) — kills SOGP (−95.6%), PRISMX (−407%), Shindo.
5. **fixed_cost_demand_shock + regime_cyclical**: `& ((op_margin>0)|(ebitda_margin>0)) & (nde<=4.0)` (#5,#6) —
   kills VEEE, NEXE (−561% ebitda), ODV (−414% op), AWLCF (38x), China Primary Energy (24.8x).
6. **capital_discipline**: `& _roce_now_ok` (#7) — kills MKTW (−75% roce diluting +23%).
7. **discounted_vehicle**: append `& _netcash_not_contradicted` to the net-cash leg (#8) — kills Newtree/PBMPOLY.
