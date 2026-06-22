# Process improvements v3 — third-pass addendum

Builds on `output/process_improvements.md` (v1) and
`output/process_improvements_v2.md` (v2). Total surfaced techniques now
~57 specific recommendations.

v3 focuses on three under-mined corners the prior passes missed:
**(I) regulatory rule changes 2023-2024 that created new signals**,
**(II) academic finance anomalies with quantified post-event drift
windows**, and **(III) recent 2024-2025 restructuring case studies
with multi-step event chains**. 13 new techniques.

---

## (I) New regulatory signals from 2023-2024 SEC rule changes

### 1. Shortened 13D filing window — accelerated activist signal

**Source:** [Paul Weiss memo on the 2023 final rule](https://www.paulweiss.com/insights/client-memos/sec-adopts-schedule-13dg-amendments-that-are-far-less-helpful-to-investors-than-originally-expected);
[Sidley Austin / Skadden updates](https://www.skadden.com/insights/publications/2024/02/reminders-amended-beneficial-ownership-rules-effective);
[SEC press release 2023-219](https://www.sec.gov/newsroom/press-releases/2023-219).
Effective February 5, 2024:
- Initial Schedule 13D filing window cut from **10 calendar days to
  5 business days**
- Subsequent amendments must be filed within **2 business days**
- Mandatory XML structured format starting **December 18, 2024**

**Why it matters for us:** the framework's existing `cluster_buys.py`
catches Form 4 insider buys, but activist 13Ds are the higher-quality
signal — and now they arrive 5+ business days *earlier* than before
the rule change, AND the XML format makes them machine-parseable
without bespoke scrapers.

**Technique:** poll EDGAR for new SC 13D filings + 13D/A amendments
daily. Cross-reference issuer against universe.md tickers. The XML
schema (Inline XBRL after Dec 2024) has clean fields for filer name,
holdings %, purpose code (G = passive vs D = activist), and any
recent transactions. Activist filings (purpose code = 1) on existing
basket names → `tier_s.activist_13d`.

**Slot:** new `src/sc13d_poll.py`. EDGAR full-text search already
indexes "SCHEDULE 13D"; this is a thin layer on the existing
`src/edgar_poll.py` infrastructure. Targets the XML/XBRL feed once
Dec 2024 transition is universal.

### 2. Rule 10b5-1 cooling-off period — 90-day insider-trade signal window

**Source:** [SEC.gov small-business compliance guide](https://www.sec.gov/resources-small-businesses/small-business-compliance-guides/insider-trading-arrangements-and-related-disclosures);
[Greenberg Traurig analysis](https://www.gtlaw.com/en/insights/2023/1/sec-adopts-final-amendments-to-rule-10b5-1-and-new-disclosure-requirements).
Effective February 27, 2023:
- Directors/officers: 90-day cooling-off after plan adoption (or 2
  business days post-10-Q/10-K, whichever is later, capped at 120 days)
- Non-D&O insiders: 30-day cooling-off
- **One single-trade 10b5-1 plan per 12-month period** (closes the
  "I'll claim 10b5-1 affirmative defense" loophole for one-off sales)
- New disclosure: Form 4 reports must check a box if the trade was
  under a 10b5-1 plan

**Why it matters:** before this rule, insiders could adopt a 10b5-1
plan and execute trades the same day. Now there's a structural 90-day
gap. **An insider buy or sale within 90 days of plan adoption is no
longer protected by 10b5-1 affirmative defense** — which means it
was either un-protected or pre-announced. Either way, the signal is
cleaner.

The Form 4 box check is the operational hook: every Form 4 now
declares whether it was 10b5-1-covered.

**Technique:** extend `src/cluster_buys.py` to record the 10b5-1 flag
per Form 4. Cluster sells *without* 10b5-1 cover within 60 days of
material events → `red_flag.unplanned_insider_sells_pre_event`.

**Slot:** `src/cluster_buys.py` — Form 4 XML parse already has the
field (`isReportingPersonOfficer`, `affirmativeDefenseDate`). Add
the 10b5-1 boolean.

### 3. XBRL-structured 13D/13G filings (Dec 2024 onward)

**Source:** [Thompson Coburn memo](https://www.thompsoncoburn.com/insights/final-rules-issued-amending-sec-schedules-13d-and-13g-beneficial-ownership-reporting-requirements/);
[AQMetrics 2024 guide](https://aqmetrics.com/blog/sec-13d-13g-2024-amendments-guide/).
From December 18, 2024, ALL Schedule 13D and 13G filings must be in
machine-readable Inline XBRL format. The structured fields include:
filer identity (LEI-tagged), beneficial ownership %, purpose-of-
transaction code, source of funds, prior transactions (last 60 days).

**Why it matters:** prior 13Ds were free-form text PDFs that required
NLP to extract. The XBRL schema gives us clean tabular data, free,
machine-readable, no scraping needed.

**Technique:** consume the EDGAR XBRL filing-bulletin for 13D/G
directly. Build a per-name `13d_ownership_history` time series.

**Slot:** new field in YAML schema: `cap_table_history` (list of
{date, filer, pct, purpose_code}). Populate from XBRL 13D/G feed.
The data is the cleanest revealed-preference signal we'd have for
Leg 3 triangulation.

---

## (II) Academic anomaly literature — quantified event-window drift

### 4. Cusatis-Miles-Woolridge spinoff anomaly — 25-34% 2-3yr excess returns

**Source:** [Cusatis, Miles, Woolridge 1993](https://www.sciencedirect.com/science/article/abs/pii/0304405X9390009Z),
"Restructuring through spinoffs: The stock market evidence."
- 2-year matched-firm-adjusted returns: **+25.0%**, statistically
  significant at 5%
- 3-year matched-firm-adjusted returns: **+33.6%**, statistically
  significant at 5%
- Driver: spinoffs had **unusually high takeover incidence** —
  abnormal returns were concentrated in firms involved in subsequent
  takeover activity

This is the foundational empirical paper for our F archetype (spinoff
cascade) bucket. The framework's `spinoff_radar.py` poller catches
Form 10-12B announcements but doesn't operationalise the *24-36
month forward holding window* with the explicit takeover-watch
overlay.

**Technique:** for every spinoff-archetype YAML (`F` or `A1+F`), add
two new schema fields:
- `spinoff_completion_date` — the actual distribution date
- `post_spinoff_takeover_watch_window` — derived as
  `[completion_date + 6 months, completion_date + 36 months]`

During this window, the spun-off entity is statistically over-
represented among M&A targets. Up-weight `catalysts:` accordingly.

**Slot:** `src/score.py` derives the window from `deal.date`.
Annotate matching catalysts with `cmw_window: True`.

### 5. European spinoff non-anomaly — geography gate

**Source:** Same Cusatis line of literature notes "studies using
European data have not indicated the presence of significant
abnormal stock returns following spin-offs"
([EFM 2011 review](https://www.efmaefm.org/0efmameetings/efma%20annual%20meetings/2011-braga/papers/0415.pdf)).
The takeover-driven part of the US anomaly doesn't replicate in
Europe because hostile-takeover protections are stronger
(poison-pill law variation, German co-determination, French
loi-Florange double-voting, etc.).

**Why it matters:** the framework should NOT apply the same
spinoff-anomaly tailwind to European F-archetype names. Currently
the scorecard treats them identically.

**Technique:** parameterise the spinoff up-weight by jurisdiction.
US/CA → full tailwind. UK/EU → partial (still works for clean
spinoffs but the takeover overlay is weaker). LatAm/EM → no tailwind.

**Slot:** `src/score.py` — add `spinoff_jurisdiction_weight` dict
keyed on `jurisdiction` field.

### 6. Equity carve-out parent-co re-rate window

**Source:** ResearchGate / Cusatis et al follow-up work documenting
that equity carve-outs (parent IPO's a subsidiary, retains control)
also produce significant parent-co re-rates in the 12 months post-
carve-out, but the magnitude is smaller (8-15%) than full spinoffs
because the parent retains attribution to the conglomerate discount.

**Technique:** add `carve_out` as a new archetype subcode (distinct
from F = full spinoff). Add the 12-month post-carve-out re-rate
expectation to the scorecard for that subcode.

**Slot:** `src/universe_screen.py` ARCHETYPE_PATTERNS — add `F2`
code matching "equity carve-out", "IPO of subsidiary", "majority-
retained spinoff".

---

## (III) Recent 2024-2025 restructuring case studies — event chains

### 7. Mallinckrodt + Endo merger → planned spinoff — multi-step event chain

**Source:** [Mallinckrodt 8-K March 2025 merger announcement](https://www.sec.gov/Archives/edgar/data/0001567892/000110465925023217/tm259039d1_ex99-1.htm);
completion August 2025; planned spinoff of generics business 4Q25.
Two emerged-from-bankruptcy specialty-pharma issuers combined into
one with a *pre-announced spinoff* baked into the deal terms.

**Why it matters for us:** this is the canonical "second-derivative"
event chain — the merger is the primary catalyst, AND the
post-merger spinoff is a pre-dated secondary catalyst. The framework's
catalyst block can already model this but the existing 21 Tier-1+2
YAMLs largely have single-catalyst theses.

**Technique:** add a `catalyst_chain:` block to YAML schema —
ordered list of dated catalysts where each later one depends on
the prior's resolution. Score on chain length, not just catalyst
count.

**Slot:** YAML schema. `src/score.py` validates that catalyst chain
items are ordered by `window[0]` and that each chain step references
a triggering condition tied to the prior step.

### 8. Hertz solvent-debtor exception — make-whole claim recovery

**Source:** Third Circuit 2024 decision *In re Hertz Corp.*, [Jones
Day November-December 2024 review](https://www.jonesday.com/en/insights/2024/12/business-restructuring-review-vol-23-no-6--novemberdecember-2024).
The court held that when a debtor exits bankruptcy *solvent* (as
Hertz did, with equity in the money), the "solvent-debtor exception"
preserves prepetition bondholders' right to make-whole premium
claims under their indentures. Equity recovers fully BUT must pay
out a substantial bondholder claim that pre-bankruptcy law
sometimes wiped.

**Why it matters:** for any YAML where the debtor has a meaningful
chance of emerging solvent (LAC if commodity cycle inflects, FLG if
bank recovers, etc.), the make-whole premium contingent liability
is a *named* risk. Currently our `red_flags` block has nothing on
this.

**Technique:** add `solvent_debtor_makewhole_exposure:` to YAML
schema for any name with bonds outstanding. Boolean: are make-whole
premiums in the indenture? Estimated exposure if triggered.

**Slot:** YAML schema. Feed from the LLM-augmented indenture
extraction in v2 §18.

### 9. Cineworld 2024 restructuring plan — UK Part 26A vs US Chapter 11 cross-border

**Source:** [Debenhams Ottaway analysis](https://www.debenhamsottaway.co.uk/news/2024/10/cineworlds-latest-restructuring-plan-passes-strong-support-despite-landlord-opposition/).
Cineworld used a UK Part 26A restructuring plan (Companies Act 2006)
to *re-restructure* after a 2022 US Chapter 11 emergence — proves
the increasingly common cross-jurisdictional pattern of "first
restructure in US, then in UK if not enough."

**Why it matters:** the framework's existing `refiled_within_12m`
red flag catches names that re-file Chapter 11 within 12 months,
but doesn't catch *cross-border* re-restructurings (US Ch 11 then
UK Part 26A or vice versa). That's a category-of-one signal that
the first restructure didn't fix the cap stack.

**Technique:** extend `refiled_within_12m` red flag to also detect
Companies Act Part 26A / Brazilian Recuperação Judicial / German
StaRUG / French sauvegarde / Spanish concurso filings within 24
months of any prior restructuring (regardless of jurisdiction).

**Slot:** `src/score.py` EXPECTED_RED_FLAGS — extend with
`cross_border_re_restructure_24m`.

---

## (IV) Discipline-frame additions from practitioner research

### 10. Akre three-legged stool + 32-quarter holding period

**Source:** [Quartr / Akre profile](https://quartr.com/insights/investment-strategy/chuck-akre-s-three-legged-stool-a-long-term-investing-framework);
[Acquirer's Multiple discussion](https://acquirersmultiple.com/2026/01/chuck-akre-quality-compounding-through-trim-discipline/).
Akre Capital Management's three-legged stool:
- Leg 1: ROE + free-cash-flow generation that is *enduring and
  predictable*
- Leg 2: management that treats public shareholders as partners
  (skill + integrity in equal parts)
- Leg 3: ability to *reinvest capital at attractive rates*

Average holding period: **32 quarters (~8 years)**.
Annualised turnover: **3%**. Concentration: 25 positions.

**Why it matters for the framework:** our existing triangulation
(Leg 1 = valuation, Leg 2 = game theory, Leg 3 = revealed
preference) is event-driven; Akre's three legs are quality-driven.
The two frameworks are complementary — Akre's check is *whether
the underlying business deserves the framework attention in the
first place*.

**Technique:** add an `akre_check:` block to YAML schema for any
Tier-1+2 candidate where the *post-restructuring* business is
expected to compound. Three booleans: `enduring_high_roe`,
`partner_management`, `reinvestment_moat`.

**Slot:** YAML schema. Tier-1 promotion requires all three True
for restructurings expected to deliver multi-year compounding
(distinct from event-driven trades that exit on catalyst).

### 11. Hayden Capital 100+ hour research budget per investment

**Source:** [Hayden Capital tearsheet](https://www.haydencapital.com/wp-content/uploads/Hayden-Capital-Tearsheet.pdf);
[Good Investing profile of Fred Liu](https://www.good-investing.net/2020/10/15/fred-liu-hayden-capital/).
"Conducting over 100 hours of analysis per investment" is Liu's
stated bar. Concentrated EM-focused, ~10 names.

**Why it matters:** the framework's 21 hand-built YAMLs vary widely
in research depth. Adding an explicit `hours_logged` field forces
honesty about which names are deeply diligenced vs which are
skeleton-tier.

**Technique:** add `research_hours_logged:` field. Tier-1 promotion
requires >= 100 hours (Hayden benchmark). Tier-2 requires >= 40.

**Slot:** YAML schema. `src/score.py` validation. Honest tracking
is the discipline; the threshold is a forcing function for not
fooling ourselves.

### 12. Aikya quality+valuation EM frame — geography-pricing arbitrage

**Source:** [Aikya January 2023 Investor Letter (Seeking Alpha)](https://seekingalpha.com/article/4583735-aikya-january-2023-investor-letter);
[Aikya firm description](https://aikya.co.uk/). Their stated
discipline:
- Only invest in high-quality EM companies *when available at
  sensible valuations*
- Reduced Indian exposure as valuations stretched (Biocon, Marico,
  Dr. Reddy's trimmed)
- "Strong downside protection" as explicit objective alongside
  return

**Why it matters:** EM special-situations are sometimes confused
with EM cycle-trades. Aikya's discipline of separating quality
(structural) from valuation (cyclical) clarifies which lever a
given thesis is pulling. For our LatAm-heavy top 10 (4 Argentine
A1s + Brazilian additions), this is the right frame.

**Technique:** add `em_thesis_type:` field with enum values:
{quality_at_valuation, cycle_trade, idiosyncratic_event,
sovereign_recovery}. Mandatory for any EM/frontier-archetype Tier
1 name.

**Slot:** YAML schema. Forces explicit attribution of what's
driving the upside.

---

## (V) Going-dark / Form 15 as an event-driven setup

### 13. Going-dark deregistration window — forced-selling entry signal

**Source:** [Dorsey & Whitney 2013 update on Going Dark](https://www.dorsey.com/newsresources/publications/2013/01/going-dark--the-simple-path-to-exiting-the-us-pu__);
[Securities Law Blog on Section 12 termination](https://securities-law-blog.com/2022/11/22/termination-of-registration-under-section-12-of-the-exchange-act/);
[DDR S analysis](https://www.ddrs.com/going-dark-a-process-for-delisting-and-deregistration-of-public-company-securities/).
A US issuer goes dark by:
- Filing Form 15 (certifies < 300 holders, or < 500 with assets
  < $10m, or < 1200 for banks)
- Periodic-report obligation suspended **immediately** on Form 15
  filing (90-day formal deregistration window)
- Stock typically moves to OTC Pink Sheet with "PK" suffix

The forced selling created by the loss of SEC-registered status
(institutional investors mandated to sell un-registered) creates
predictable 30-90 day discount windows. Combined with the typical
1/3 information asymmetry (filings cease but the business continues),
post-going-dark stubs occasionally trade at 50-70% discount to
intrinsic value — and the canonical recovery comes when the issuer
either re-emerges (rare) or is acquired (common).

**Why it matters:** the framework has no current poller for Form 15
filings. This is a clean, dated, machine-readable event with a
predictable forced-selling window. KEDM (v2 §3) listed this as K3
in the extended archetype list but didn't operationalise it.

**Technique:** poll EDGAR for Form 15 filings daily. For each, emit
`tier_s.going_dark` record. Track the issuer's last reported
financials → estimate intrinsic value → flag if last-traded price
post-Form 15 is < 50% of estimate.

**Slot:** new `src/form15_poll.py`. Hooks into existing
`src/edgar_poll.py` queries via the form filter `FORMS=15-12B,15-12G,15-15D`.

---

## Implementation queue (post-v2 sequencing)

Lower-friction items first:

1. **SC 13D / 13D/A poller** (`src/sc13d_poll.py`) — reuses EDGAR
   infrastructure; 5-business-day window means signals arrive faster
   than under old rule.
2. **Form 15 going-dark poller** (`src/form15_poll.py`) — same
   EDGAR layer; opens the K3 event-driven archetype with real data.
3. **Spinoff Cusatis window** — schema-level addition in `score.py`;
   auto-derives the 24-36mo forward window from `deal.date`.
4. **10b5-1 flag in cluster_buys.py** — extend Form 4 XML parser to
   capture the 10b5-1 boolean; surface `red_flag.unplanned_insider_sells`.
5. **Akre three-legged stool block** — YAML schema; Tier-1 gate.
6. **`catalyst_chain` block** — YAML schema; for multi-step event
   chains (Mallinckrodt+Endo+spinoff template).
7. **`solvent_debtor_makewhole_exposure`** — YAML field; feed from
   v2 §18 indenture extraction once that's live.
8. **`research_hours_logged`** — YAML field; honest tracking.

Deferred (require additional research / negotiation):

9. **XBRL 13D/G consumer** — needs the post-Dec 2024 schema docs
   from SEC + an XBRL parser.
10. **Cross-border re-restructure detector** — needs multi-
    jurisdiction filing-graph (US PACER + UK Insolvency Gazette
    + German Bundesanzeiger + Brazil CVM Recuperação Judicial).

---

## Sources

- [Paul Weiss — SEC adopts Schedule 13D/G amendments](https://www.paulweiss.com/insights/client-memos/sec-adopts-schedule-13dg-amendments-that-are-far-less-helpful-to-investors-than-originally-expected)
- [Skadden — Amended Beneficial Ownership Rules Effective](https://www.skadden.com/insights/publications/2024/02/reminders-amended-beneficial-ownership-rules-effective)
- [SEC press release 2023-219](https://www.sec.gov/newsroom/press-releases/2023-219)
- [Thompson Coburn — 13D/13G amendments memo](https://www.thompsoncoburn.com/insights/final-rules-issued-amending-sec-schedules-13d-and-13g-beneficial-ownership-reporting-requirements/)
- [Sidley Austin — Shortened 13D/G filing deadlines](https://www.sidley.com/en/insights/newsupdates/2023/10/sec-shortens-filing-deadlines-for-schedules-13d-g)
- [SEC small-business compliance guide — 10b5-1](https://www.sec.gov/resources-small-businesses/small-business-compliance-guides/insider-trading-arrangements-and-related-disclosures)
- [Greenberg Traurig — 10b5-1 final amendments](https://www.gtlaw.com/en/insights/2023/1/sec-adopts-final-amendments-to-rule-10b5-1-and-new-disclosure-requirements)
- [Cusatis-Miles-Woolridge 1993 (JFE)](https://www.sciencedirect.com/science/article/abs/pii/0304405X9390009Z)
- [EFM 2011 international spinoff review](https://www.efmaefm.org/0efmameetings/efma%20annual%20meetings/2011-braga/papers/0415.pdf)
- [Mallinckrodt-Endo merger 8-K March 2025](https://www.sec.gov/Archives/edgar/data/0001567892/000110465925023217/tm259039d1_ex99-1.htm)
- [Jones Day — Business Restructuring Review Nov-Dec 2024 (Hertz)](https://www.jonesday.com/en/insights/2024/12/business-restructuring-review-vol-23-no-6--novemberdecember-2024)
- [Debenhams Ottaway — Cineworld 2024 Part 26A plan](https://www.debenhamsottaway.co.uk/news/2024/10/cineworlds-latest-restructuring-plan-passes-strong-support-despite-landlord-opposition/)
- [Quartr — Chuck Akre's three-legged stool](https://quartr.com/insights/investment-strategy/chuck-akre-s-three-legged-stool-a-long-term-investing-framework)
- [Hayden Capital tearsheet](https://www.haydencapital.com/wp-content/uploads/Hayden-Capital-Tearsheet.pdf)
- [Aikya January 2023 letter](https://seekingalpha.com/article/4583735-aikya-january-2023-investor-letter)
- [Dorsey & Whitney — Going Dark voluntary delisting](https://www.dorsey.com/newsresources/publications/2013/01/going-dark--the-simple-path-to-exiting-the-us-pu__)
- [Securities Law Blog — Section 12 deregistration](https://securities-law-blog.com/2022/11/22/termination-of-registration-under-section-12-of-the-exchange-act/)
