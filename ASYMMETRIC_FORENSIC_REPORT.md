# Forensic Asymmetry Report

*Generated 2026-06-02. Source artefacts (all permanently committed):
`forensic_asymmetry.py`, `forensic_asymmetry.{csv,json}`,
`.cache/docs/{accession}.html` per ticker, `form4_buys.json`,
`psu_forensics_v2.json`.*

## Methodology

The previous pass scored on whole-document regex matches, which conflated
"separation from service" boilerplate with corporate spin-offs and
"calendar year" RSU prorating with FDA milestones. This pass is
deliberately methodical:

1. **Multi-anchor section windowing**. For each filing, take the union
   of ~6KB windows around every PSU/PRSU/CD&A/Performance-Highlights/
   Annual-Incentive-Plan/LTIP/Performance-Goals header. Cap at 80KB
   per filing. This brings in the CD&A 'Performance Highlights' and
   'Annual Incentive Plan' subsections that contain the real dollar
   targets, without dragging in the death/disability RSU appendix.

2. **Proximity-constrained extraction**. Each conditionality regex
   requires a vesting-intent anchor (`vest`, `earn`, `payable`, `for
   purposes of`, `achievement of`, `under the ... plan`, `weighted
   factor`, `performance goal`) within ~220 chars of the business
   trigger. Bidirectional — verb→trigger or trigger→verb.

3. **Boilerplate subtraction**. Snippets containing "separation from
   service", "general release of claims", "post-employment", "base
   salary", "Mr.|Ms." in employment-arrangement context, "insurance
   market" (WRB-style false-positive on FDA pattern) are filtered out.
   `spin_separation` is the strictest: it requires unambiguous corporate
   spin language (`Spin-Off`, `Distribution Date`, `Separation and
   Distribution Agreement`, `RemainCo/SpinCo`, `Form 10-12B`, `newly
   independent company`).

4. **PSU archetype labelling**. Each filing is bucketed:
   - **A** — Per-share return heavy (ROIC/ROIIC/EPS/FCF/share dominant)
   - **B** — Multi-tranche stock-price ladder (≥3 distinct $ hurdles)
   - **C** — Relative TSR (peer or index)
   - **D** — Dollar metric target (named EBITDA/Revenue/FCF $)
   - **E** — Event-triggered (M&A close, spin, regulatory milestone)

5. **Role-weighted insider scoring**. CEO 1.50, CFO 1.20, COO/President
   1.10-1.15, Chair 1.10, Director 0.85. Cluster detection: max
   distinct persons buying within any rolling 14-day window. Explicit
   CEO+CFO simultaneous-buy boost (institutional conviction).

6. **Plan-evolution markers**. New metric added / period extended /
   ownership requirement added / responsive to shareholder feedback /
   front-loaded grant / clawback strengthened / anti-hedge-pledge.

Composite: `0.32×pattern_match + 0.27×conditionality + 0.10×plan_delta + 0.26×insider + 0.05×step_change_residual`.

---

## Tier 1 — Insider cluster + business-specific PSU conditionality verified

### HFFG · HF Foods Group · $102M / $1.90 · forensic score 36

**Archetypes**: B (price ladder $2.15–$8.00) + C (relative TSR) + D ($1.232B / $1.281B revenue).
**PSU 50% of LTI**.

**Verbatim PSU condition** (subsection "The performance goals for net revenue and..."):
> *"vest at 100%, the Company must have achieved a revenue of $1.232 billion"*
> *"vest at 100%, the Company must achieve a revenue of $1.281 billion"*

The PSU has explicit, dollarised revenue targets across two years
(2.5% growth 2025, 4% growth 2026). The stock-price ladder runs
$2.15-$8.00 against a $1.90 spot — top hurdle is 4.2× current.

**Insider cluster** (cluster size 4, window 2026-03-18 to 2026-03-19,
CEO+CFO both bought):
- 2026-03-18 Lin Xi, **President & CEO**, $15,028
- 2026-03-18 McGarry Paul E, **CFO**, $4,400
- 2026-03-18 Chang Christine, **Chief Administrative Officer**, $6,960
- 2026-03-19 Lam Dennis, **Director**, $14,549

Four executives buying in a 48-hour window after a proxy filing that
codifies a $1.232B revenue hurdle is the cleanest skin-in-the-game
signal in this universe. **Risk**: absolute dollars are tiny ($41K
total) — these are token buys on a microcap. Need a fundamental view
on Chinese-American foodservice distribution before sizing.

**Plan evolution**: clawback strengthened.

---

## Tier 1.5 — Strong qualitative on two of three signals

### PLBY · Playboy · $197M / $1.71 · forensic score 30

**Archetypes**: C + D. PSU 50% of LTI.

**Three layered conditionalities**, all verbatim:
> *"closing of the Business Combination, a special grant of
> performance-based restricted stock units (the "Initial PSUs") that
> if earned…"*
> *"Adjusted EBITDA target for 2025 of $15.2 million, in each case as
> such metrics are defined and/or determined as set forth in the
> Company's 2025 Annual Report on Form 10-K"*
> *"achievement of an annual revenue target for 2025 of $120.5 million"*

PLBY's PSUs explicitly trigger off **business-combination close** AND
have dollar EBITDA/revenue targets — three independent vesting
conditions stacked. The $20 stock-price hurdle is 11.7× the current
$1.71 (deep OTM, classic transformation grant).

**Insider cluster**: none — but the merger context means insiders are
typically locked, which is consistent.

**Risk**: business-combination subject to close-risk; the $15.2M
EBITDA target was set when the deal was structured and may already
have moved.

---

### GOSS · Gossamer Bio · $87M / $0.37 · forensic score 20

**Archetypes**: B + C + D. Microcap biotech.

**Verbatim**:
> *"Phase 3 PROSERA study and need to evaluate capital allocation,
> the compensation committee determined our corporate performance
> percentage to be 65% of the target performance"*

Real clinical-readout conditionality. Price ladder $0.9–$10 against
$0.37 spot = top hurdle is 27× the share price. This is binary
biotech: PROSERA Phase 3 success would re-rate the stock 5-10× and
collapse all PSU hurdles below. **Risk**: trial failure leaves equity
near zero. The PSU explicitly tells you the bet.

---

### OCUL · Ocular Therapeutix · $2.05B / $9.43 · forensic score 19

**Archetype**: B (ladder $7.44/$15/$30).

**Verbatim**:
> *"completion of enrollment and randomization in the SOL-R Phase 3"*
> *"achievement of last patient visit for the Week 52 timepoint in
> the SOL-1 Phase 3"*

Two distinct Phase-3 milestones (SOL-R + SOL-1) explicitly named as
PSU achievement triggers. Top price hurdle $30 = 3.2× current. The
2025 PSUs are tied to operational trial milestones, not just stock
price — which is the highest-quality biotech PSU structure.

---

### NCLH · Norwegian Cruise Line · $8.6B / $18.81 · forensic score 20

**Archetypes**: A + C + D. **PSU 60% of LTI** with TSR+EPS+ROIC+EBITDA
metric stack (the cleanest in our entire set).

**Insider cluster** (cluster size 3, window 2026-05-11 to 2026-05-12):
- 2026-05-11 Byng-Thorne Zillah, **Director**, **$521,394**
- 2026-05-11 Lansberry Kevin Allen, **Director**, $196,992
- 2026-05-12 MacDonald Brian P, **Director**, $248,100

$966K total in two days — the largest credible director cluster in the
set in absolute dollar terms (HFFG is bigger by count but smaller by
dollar).

**Plan evolution**: front-loaded grant flag.

**No explicit dollar conditionality flagged** in the PSU section
narrowly — the asymmetry here is **PSU quality × director conviction**.
ROIC in the PSU means the board has told management that
deleveraging matters (NCLH carries $13B+ debt against $8.6B mcap),
which is the right incentive for a post-pandemic cruise-line recovery
trade.

---

### CRM · Salesforce · $148.7B / $181.82 · forensic score 21

**Archetype**: C only (relative TSR). **PSU 67% of LTI**.

**Insider cluster** (size 2, window 2026-03-18 to 2026-03-19):
- 2026-03-19 Alber Laura, **Director**, $500,266
- 2026-03-18 Kirk David Blair, **Director**, $500,178

Two directors buying ~$500K each on the same two days.

**Plan evolution**: **ownership requirement added** (positive — board
is forcing more share ownership). SOP support 77% — shareholder
unease.

**Bull case**: At $148B mcap, two directors writing same-size checks
two days apart after a proxy that introduced new ownership
requirements is structurally suggestive. The PSU section itself is
TSR-only — Salesforce hasn't tied PSUs to event-specific business
triggers — but the wider step-change stack ($25B buyback, spin
declared, governance reset all 47d) compensates.

---

## Tier 2 — Plan-evolution flags without insider follow-through

### KDP · Keurig Dr Pepper · $39.6B / $29.09 · forensic score 12 *but flags 4 plan-deltas*

**Archetypes**: A (per-share return) + C (relative TSR). **PSU 75% of LTI**.

**Four simultaneous plan changes** in the most recent proxy:
- `responsive_to_shareholders` — explicit "in response to stockholder feedback"
- `front_load_grant` — explicit "one-time Transformation" grant
- `clawback_strengthened` — Rule 10D-1 clawback adopted
- `anti_hedge_pledge_added` — pledging now prohibited

This is the densest plan-evolution cluster in the universe.
Historically, when a comp committee makes four governance tightenings
in a single year, it's because they expect a multi-year transformation
to come — they're locking down the framework before the next
strategic move. **No insider buying yet** — this is a watchlist name
for follow-through.

---

## Tier 3 — Single-signal, watch for confirmation

| TKR | Mcap | Px | Forensic | Hook |
|---|---|---|---|---|
| CCI | $39.5B | 90.57 | 21 | $4.044B AIP EBITDA disclosed; 1 director $74K |
| ARRY | $1.3B | 8.57 | 19 | $178M EBITDA LIP target; B+D archetype |
| SPOK | $221M | 10.65 | 19 | $29M EBITDA achieved; CEO bought $107K |
| LAZ | $4.7B | 48.08 | 21 | Clean PSU structure, no event triggers |
| WTRG | $10.6B | 37.47 | 21 | Pending American Water merger arb |
| CP | $74B | 83.09 | 22 | Per-share + ladder; no event/insider |
| EYE | $1.8B | 22.34 | 20 | Cleanest pure-PSU structure, no triggers |
| EVRG | $18.9B | 81.78 | 18 | Utility, clean PSU only |
| BIIB | $27.6B | 187 | 15 | Plan-delta: responsive to shareholders |
| DOV | $29.6B | 220 | 16 | Plan-deltas: responsive + clawback |

---

## What's not a setup (filtered)

Names previously flagged that turned out to be boilerplate after the
methodical rerun:

- **WRB** (Berkley Insurance): "FDA milestone" hit was actually
  "insurance market" — false positive. Now filtered.
- **CAVA, KMPR, CLOV, HBIO, TARS**: "spin_separation" hits were all
  employment-termination "Separation Date" / "executive separation" —
  not corporate spin-offs. Now filtered.
- **IRWD**: "spin_separation" was Cyclerion 2019 (legacy), not a new
  spin in the current PSU.
- Most "regulatory_milestone" matches in the v1 pass were
  calendar-year RSU prorating boilerplate on death/disability — only
  GOSS (Phase 3 PROSERA) and OCUL (SOL-R / SOL-1 Phase 3) survive the
  strict filter.

---

## What this analysis cannot tell you

- Whether the PSU dollar hurdle is achievable — that requires a
  fundamentals model on the underlying business.
- Whether the insider buy is informational vs. routine — small-dollar
  director buys can be optical. HFFG's $4-15K-per-buyer is qualitatively
  different from NCLH's $200-520K-per-buyer.
- Whether the merger/spin actually closes — break risk is real (PLBY,
  WTRG).
- The 50 filings analysed here are the top of `psu_step_change.csv`.
  Names not in that list (e.g. older filings outside the 270-day
  freshness window) are not assessed.

---

## Persistence

`.gitignore` excludes only `__pycache__/`, `.venv/`, `.env`,
`.DS_Store`, `*.log`. Every artefact in this analysis (Python, JSON,
CSV, cached HTML, this markdown report) is committed and recoverable
from `origin/claude/create-new-feature-Oopqq`.
