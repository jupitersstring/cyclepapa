# Process improvements v2 — second-pass meta-survey

Builds on `output/process_improvements.md` (first pass, June 2026). Six
of those 16 recommendations were implemented in the intervening week
(PACER, CVM, ASX pollers; YAML schema additions for crowd-check,
sell-side conflict, days-since-recap, MFN/fiduciary-out/springing-
covenant red flags, consensus_pricing/catalyst_independence/expert_calls
blocks). This second pass deliberately stays in the layer below the
canonical Klarman/Marks/Moyer/Voss material and focuses on novelty per
word — what specific technique we missed, where it slots, and the
single source that justifies it.

Grouped by (a) Sourcing additions, (b) Diligence-depth additions,
(c) Position-sizing additions, (d) Anti-pattern / forensic-accounting
checks, (e) Recently-bankrupt case studies, (f) International
sovereign-restructuring playbook, (g) LLM-augmented techniques.

---

## (a) Sourcing additions beyond the first pass

### 1. Bond-market credit-spread monitor as equity-event leading indicator

**Source:** Lazard's [2020-2025 Sovereign Debt Crisis paper](https://www.lazard.com/research-insights/the-2020-2025-sovereign-debt-crisis-what-have-we-learnt-and-what-lies-ahead)
documents that across nine sovereign defaults (Argentina, Belize, Ghana,
Ecuador, Lebanon, Sri Lanka, Russia, Suriname, Zambia), bond-spread
widening preceded the formal default event by 6-12 months in every
case. The same lead-lag holds at the corporate level — bond OAS
expansion preceded the SVB, BBBY, and Wirecard equity collapses by
1-3 quarters.

**Technique:** poll daily option-adjusted spreads (OAS) on USD-
denominated corporate paper for every universe.md ticker that has a
public bond. When 30-day spread widening exceeds 100 bps, surface as
a `red_flag.credit_spread_widening` event in the inbox.

**Slot:** new `src/credit_spread_poll.py`. ICE BofA OAS series are
free via FRED (`fred.stlouisfed.org/series/BAMLH0A0HYM2` for high-yield
master, plus per-issuer series for top issuers). Cross-reference against
universe tickers; emit inbox records when spread widens past threshold.
Wire into `inbox_promote.py` as a new `red_flag` subquery.

### 2. Index reconstitution calendar — Russell + MSCI + S&P

**Source:** Index-inclusion-effect literature (Shleifer 1986; Wurgler-
Zhuravskaya 2002; more recent: Bennett-Stulz-Wang 2020 finding 4-6%
abnormal returns around inclusion/deletion). Russell rebalances
quarterly (mostly June), MSCI semi-annually (May/Nov), S&P committees
ad-hoc with announcement-to-effective gaps. Net inclusion buying
pressure produces predictable price action; net deletion produces
forced selling that creates entry windows in distressed names.

**Technique:** maintain a calendar of upcoming rebalance effective
dates per index. For names on the candidate list with potential
inclusion/exclusion, score `d24_index_reconstitution_timing`.

**Slot:** new `src/index_calendar.py`. Three feeds:
- Russell: indices.research.ftse.com (quarterly preliminary lists)
- MSCI: msci.com index-changes feed
- S&P: spglobal.com SPDJI announcement RSS
Output `data/index_calendar.json` consumed by `score.py` to flag YAMLs
with reconstitution events in the next 90 days.

### 3. Kuppy's Event Driven Monitor (KEDM) — categorical event taxonomy

**Source:** Praetorian Capital ([Idea Brunch interview](https://www.readideabrunch.com/p/idea-brunch-with-harris-kuppy-kupperman)).
Kupperman built KEDM as a systematized event-driven taxonomy that
tracks "over two-dozen Event-Driven strategies" — including specific
trade structures like de-SPAC redemption arb, post-IPO lockup expiry,
secondary-offering pricing windows, M&A break-fee arb, going-dark
delisting, and reverse-merger shells. This is a richer taxonomy than
our framework's 9 archetypes (A1-H).

**Technique:** extend our archetype taxonomy with the 8 KEDM-style
sub-archetypes our current set doesn't cover:
- `K1` de-SPAC redemption arb (announced trust value > current price)
- `K2` post-IPO lockup expiry (90/180 day cliff sell pressure)
- `K3` going-dark / Form 15 delisting candidates
- `K4` SPAC trust value-at-redemption arb
- `K5` reverse-merger shell-company filings
- `K6` NOL shell preserved tax-asset cases
- `K7` litigation-settlement event arb (judgment day + appeal)
- `K8` commodity-cycle inflection trades with binding supply-side data

**Slot:** extend `ARCHETYPE_PATTERNS` in `src/universe_screen.py` with
these 8 codes. Update yaml schema to allow them in the `archetype:`
list. The framework's existing taxonomy was deliberately limited to
restructuring archetypes — KEDM widens the net to non-distress
event-driven setups that share the structural-asymmetry property.

### 4. J Capital / Hempton-style ground-truth verification

**Source:** Wirecard collapse ([Dan McCrum / J Capital coverage](https://alternativefundinsight.com/mccrum-takeaways/));
in 2016 J Capital Research published a short report that "could find
no company at all" at two of Wirecard's claimed Asian partner
addresses, despite multi-hundred-million-euro reported transactions.
The technique generalises: when an issuer's revenue concentrates in a
single named off-balance-sheet vehicle or "trust account," physical
verification of the counterparty's existence is the cheapest fraud check.

**Technique:** for every Tier-1 YAML, add a `ground_truth_checks`
block listing the issuer's largest related-party counterparties + a
flag for whether a verification visit / phone confirmation has been
completed.

**Slot:** YAML schema addition. Audit script flags Tier-1 names whose
related-party counterparties are unverified > 180 days.

---

## (b) Diligence-depth additions

### 5. Five-signal fundamental distress checklist (BBBY case)

**Source:** [Yahoo Finance / GuruFocus BBBY post-mortem](https://finance.yahoo.com/news/bed-bath-beyond-5-fundamental-175317783.html).
Five fundamental indicators triggered 12+ months before the April 2023
Chapter 11:
- Current ratio < 1.0 (BBBY: 0.73)
- Debt/equity negative (BBBY: -4.55 → negative equity = technical insolvency)
- Operating margin negative for ≥ 9 consecutive quarters
- Inventory turnover < 1.0 (BBBY: 0.65)
- Negative free-cash-flow per share

Each is independently bearish but stacked they're conclusive.

**Technique:** add a `distress_screen` block to YAML schema with 5
explicit thresholds.

**Slot:** `src/score.py` — new SCORE_RULES dimensions:
```
d25_current_ratio:        ≥1.5 → 2; ≥1.0 → 1; <1.0 → 0
d26_debt_equity:          ≥0 → 2; ≥-1 → 1; <-1 → 0
d27_negative_om_quarters: 0 → 2; ≤3 → 1; >3 → 0
d28_inventory_turnover:   ≥4 → 2; ≥2 → 1; <2 → 0
d29_fcf_per_share:        positive → 2; near-zero → 1; negative → 0
```
For Tier-1 names with `archetype: E` (court-supervised) the
`distress_screen` is permitted to be 0 — they're in distress by design.
For other archetypes, any zero is a hard kill criterion.

### 6. Wirecard six-symptom forensic test

**Source:** [Dan McCrum FT coverage / Money Men](https://alternativefundinsight.com/mccrum-takeaways/).
McCrum's six symptoms of Wirecard-style fraud:
1. Big reported profits but no free cash flow
2. Cash spent on acquisitions, always at year-end (window dressing)
3. Inconsistencies between local subsidiary accounts and group accounts
4. Heavy reliance on non-GAAP / "adjusted" metrics
5. Unusual profitability vs sector peers (positive outlier on margins)
6. Year-on-year revenue growth at named ROW geographies that can't
   be independently verified

**Technique:** add a `wirecard_check` boolean field to YAML schema —
True/False on each of the 6 symptoms. Score 2+ True = `red_flag.wirecard`
auto-flag.

**Slot:** YAML red_flags block. Add to `EXPECTED_RED_FLAGS` in
`src/score.py`:
- `profit_fcf_gap_>30pct`
- `year_end_acquisition_pattern`
- `local_vs_group_account_inconsistency`
- `adjusted_metric_reliance`
- `peer_margin_outlier_positive`
- `unverified_rowe_growth`

### 7. Schilit's seven Financial Shenanigans categories — quantitative tests

**Source:** Howard Schilit ([Financial Shenanigans, 4th ed.](https://www.mheducation.com/highered/product/financial-shenanigans-fourth-edition-how-detect-accounting-gimmicks-fraud-financial-reports-engelhart-schilit/9781260117264.html)).
Seven categories — most are quantifiable directly from XBRL:
1. **Recording revenue too soon** — DSO trend > 90-day MA proxy
2. **Recording fictitious revenue** — receivables grow > 2× revenue growth
3. **Boosting income with one-time gains** — extraordinary items > 10% of net income
4. **Shifting current expenses to a later period** — capitalised costs grow > revenue
5. **Failing to record liabilities** — operating-lease obligations / debt > 1.5x stated
6. **Shifting current revenue to a later period** — deferred revenue spike (selectively)
7. **Shifting future expenses to the current period** — restructuring-reserve cookie jars

**Technique:** add `d30_shenanigan_score` to scorecard — count of
Schilit categories triggered on the last 4 quarters of filings. 0
= clean; ≥3 = `red_flag.schilit_shenanigan` and kill-criterion eligible.

**Slot:** XBRL-based screen. EDGAR's structured financials API gives
us standardised line items per filing. New `src/shenanigan_screen.py`
that runs the seven tests over the last 4 quarters of XBRL data for
every Tier-1+2 YAML.

### 8. Hindenburg-style related-party-transaction graph

**Source:** [Hindenburg's investigative methodology](https://hindenburgresearch.com/about-us/) —
"undisclosed related-party transactions" appear across their major
reports (Aphria, Adani, Block, Eros, etc.). The pattern: insiders
hold undisclosed stakes in the buyer of company assets.

**Technique:** for each Tier-1 YAML, build a `related_party_graph`
listing all named counterparties in `deal.fields` and `anchor.parties`
plus the issuer's own disclosed officers/directors. Look for edges
where the same legal entity / family / fund appears on both sides of
a transaction.

**Slot:** YAML schema — `related_party_graph` block. Manual fill-in
initially; can be partially automated by parsing EDGAR 8-K Item 1.01
filings (material agreements).

---

## (c) Position-sizing additions

### 9. Greenberg concentration rule — 5% min, 10 names max

**Source:** Glenn Greenberg / Brave Warrior Advisors ([Insurance NewsNet profile](https://insurancenewsnet.com/oarticle/glenn-greenberg-portfolio-uncovered-top-holdings-and-strategies)):
"holdings rarely take less than 5% of the portfolio, and he usually
holds up to 10 companies." Stated reason: "the more companies you own,
the less you will know about each, and the less you know about a
business, the more likely you are to make mistakes." Returns ~12%
compounded since 1984.

Our framework currently uses ¼-Kelly + correlation haircut + cluster
cap + 60% invested cap with 21 active names. Greenberg's framing
suggests this is structurally over-diversified: at 21 names the
average weight is 2.86%, half Greenberg's 5% minimum.

**Technique:** add a `position_floor` parameter to `src/portfolio.py`
— if a name's haircut weight would drop below 5%, either size up to
5% (and let the global cap re-bite) or drop the name entirely.

**Slot:** `src/portfolio.py`. Implement as opt-in mode. Default
remains current; `--concentration greenberg` mode imposes the 5%/10
floor.

### 10. Lou punch-card discipline — multi-year holding-period bias

**Source:** Norbert Lou / Punch Card Capital ([Guru Gems](https://www.gurugems.org/p/norbert-lou-the-punch-card-mindset)):
3-6 stocks at a time, ~25% cash sleeve when nothing's actionable.
Q1 2026 portfolio: Berkshire 38%, Crocs 18%, T-bills 17%, PDD 16%,
PayPal 11%. 5 positions total.

The discipline: ask "would I be happy holding this for 5 years if the
exchange closed tomorrow?" before sizing. If no, don't size.

**Technique:** add a `five_year_holdability:` field to YAML — True/
False, with rationale required. Tier 1 + state:core requires True.

**Slot:** YAML schema + score.py validation. Boolean discipline check.

### 11. Praetorian inflection-required gate

**Source:** Harris Kupperman / Praetorian Capital ([Q4 2023 letter](https://seekingalpha.com/article/4664015-praetorian-capital-fund-q4-2023-investor-letter)):
"concentrated investments exhibiting inflecting secular or cyclical
tailwinds, and Event Driven special situations." Praetorian rejects
any thesis that doesn't have a clear cycle-inflection or event-trigger
component. This is more restrictive than our Condition 7 (operational
inflection gate) — Praetorian also requires a quantitative supply-side
deficit on commodity-cycle plays (e.g. uranium 30M lb production deficit).

**Technique:** add `inflection_quantification:` block to YAML — for
each thesis, a specific number that converts the inflection narrative
into a falsifiable forecast.

**Slot:** YAML schema. For commodity-cycle names (LAC, MP, UREE, TMQ)
back-fill with explicit production-deficit numbers.

---

## (d) Anti-pattern / forensic-accounting checks

### 12. Pre-pack bankruptcy pattern detection

**Source:** Greenlight Capital's Allied Capital playbook and
distressed-debt practitioner convention. A *pre-pack* (pre-packaged
bankruptcy) is filed with a fully-negotiated plan ready for
confirmation in 30-60 days; equity is usually wiped. Pre-pack
indicators in court docket: same-day filing of (a) Chapter 11
petition, (b) RSA / plan support agreement, (c) DIP financing motion,
(d) disclosure statement. If all four hit the same day, equity is
worth zero.

**Technique:** `src/pacer_poll.py` already monitors docket entries.
Add a `same_day_4_filing_pattern` detector — when Chapter 11 +
RSA + DIP + disclosure statement all file day-of, emit a
`red_flag.prepack` record into inbox immediately.

**Slot:** `src/pacer_poll.py`. Already structured per-court; add
post-filtering on filing-day patterns.

### 13. Insider-net-seller window — 60-day pre-event lookback

**Source:** SEC Form 4 academic literature (Lakonishok-Lee 2001, the
basis for our existing cluster_buys.py) extended with the converse:
clusters of *sales* in the 60-day window pre-event are the canonical
red flag for insider-disclosed-bad-news. Wirecard insiders sold
heavily in late 2019; SVB CEO sold $3.6m on Feb 27 2023, 10 days
before the run.

**Technique:** flip `src/cluster_buys.py` to also detect cluster
*sales*. New label `red_flag.cluster_sales_pre_event`.

**Slot:** `src/cluster_buys.py` — add a `--sells` mode that mirrors
the buys logic. Tier 1 names with ≥ 2 insider sells in last 60 days
get a `red_flag.insider_cluster_sells` field auto-set.

---

## (e) Recently-bankrupt cases — playbook lessons

### 14. SVB-style duration-mismatch + uninsured-deposit screen

**Source:** SVB Financial Group March 2023 collapse. Two specific
quantitative red flags:
- Held-to-maturity securities duration ≈ 6 years vs deposit beta ≈ 0.5
  → 30% MTM loss not reflected in TBV
- Uninsured deposits > 90% of total deposits → run risk on any whiff
  of trouble

For banking-archetype names in our universe (FLG, GTCO, SAB),
explicit checks on these two metrics.

**Technique:** add `d31_htm_duration_yrs` and `d32_uninsured_deposit_pct`
to bank-archetype scorecard.

**Slot:** `src/score.py` SCORE_RULES, conditionally applied when
archetype is banking-related. New YAML fields populated from 10-K
disclosures.

### 15. Endo-style mass-tort litigation calendar

**Source:** Endo Pharmaceuticals (2022 Chapter 11), Mallinckrodt
(2020 + 2023), Purdue Pharma, J&J Talc. Opioid / talc / asbestos
exposures aren't always quantified in the 10-K but always have a
court-docket signature. The technique: scrape multidistrict
litigation (MDL) dockets for every Tier-1 name's defendants list.

**Technique:** subsidiary use of PACER — extend `src/pacer_poll.py`
to additionally monitor JPML (Judicial Panel on Multidistrict
Litigation) dockets where universe.md issuers appear as defendants.

**Slot:** `src/pacer_poll.py` extension. JPML docket numbers all
start with "MDL-NNNN".

---

## (f) International sovereign-restructuring playbook

### 16. Sovereign-restructuring equity-recovery calendar

**Source:** Lazard's [2020-2025 Sovereign Debt Crisis paper](https://www.lazard.com/research-insights/the-2020-2025-sovereign-debt-crisis-what-have-we-learnt-and-what-lies-ahead).
Nine sovereign defaults in the window: Argentina (2020), Belize,
Ghana (2022-23), Ecuador (2020), Lebanon (ongoing), Sri Lanka
(2022-23), Russia (2022), Suriname (2020), Zambia (2020-23). Each
produces equity-recovery opportunities **post-restructuring** as
local-currency liquidity returns and import-input costs normalise.
YPF in our basket is the Argentine-restructuring leg already.

Sequencing observation from the paper: domestic debt restructuring
(DDR) plus external (EDR) sequenced correctly yields faster equity
re-rate than EDR-only. Argentina, Ghana, Sri Lanka did both;
Chad/Ecuador/Ethiopia/Malawi/Zambia did EDR-only.

**Technique:** add a `sovereign_restructuring_calendar.md` doc
listing each restructuring's expected completion date + DDR/EDR
sequence. Cross-reference universe.md issuers headquartered in each
country.

**Slot:** new `data/sovereign_restructuring_calendar.md`. Maintained
manually + cross-referenced from `output/universe_screened.md`.

### 17. SCDI / Value-Recovery-Instrument identification

**Source:** Lazard paper notes SCDIs (State-Contingent Debt
Instruments) used in Sri Lanka and Zambia restructurings (also
Argentina + Ukraine historically). VRIs/SCDIs are sovereign warrants
on GDP growth or commodity revenue — they sometimes mis-price
relative to the implied volatility on the underlying. The Argentine
GDP warrants traded 90% below their model value pre-Milei.

**Technique:** add a `sovereign_warrants` archetype subcategory
(K9 in our extended KEDM-style taxonomy). Tag relevant universe rows.

**Slot:** `src/universe_screen.py` ARCHETYPE_PATTERNS — keyword
patterns for "VRI", "SCDI", "GDP warrant", "value recovery
instrument."

---

## (g) LLM-augmented techniques

### 18. Bond-prospectus / indenture deep-read automation

**Source:** [Resonanz Capital article on hedge-fund AI use](https://resonanzcapital.com/insights/how-hedge-funds-are-really-using-generative-ai-and-why-it-matters-for-manager-selection):
"ingest and summarize thousands of bond prospectuses and indentures"
— this is exactly the Moyer-style indenture analysis from the first
pass, automated. Specific tools: AlphaSense Generative Search,
Tegus AI Search, Hebbia. Claimed productivity gain: "analysts can
cover more securities with greater speed and consistency."

**Technique:** for every Tier-1 YAML with a tradeable bond, run an
LLM-driven extraction of the indenture's covenant package
(restricted-payments basket, debt-incurrence test, sale-leaseback
restrictions, change-of-control put, etc.). Store extracted
covenants in a new `indenture_covenants:` block.

**Slot:** new `src/indenture_extract.py`. Uses Claude or GPT-4o via
the Anthropic / OpenAI API to convert indenture PDFs (sourced from
EDGAR S-1/Ex-4.X exhibits) into structured covenant fields.
~$0.50 per indenture at current API pricing.

### 19. Overnight earnings-call sentiment delta detection

**Source:** Resonanz article: "GenAI to scan and summarize dozens of
earnings transcripts overnight, highlighting sentiment shifts or
changes in management tone." The signal is the *delta* between
quarterly calls — when prepared remarks shift from confident-future
to defensive-explanation, that precedes earnings disappointments by
1-2 quarters.

**Technique:** for every Tier-1 YAML's issuer, monthly run an LLM
prompt over the last 4 earnings transcripts that scores tone (1-5)
on prepared remarks + Q&A defensiveness. Store time series in
`tone_score:` block.

**Slot:** `src/earnings_call_tone.py`. Pulls Seeking Alpha-style
transcripts (paywalled but a single transcript fetch via WebFetch
costs ~$0.001).

### 20. Compliance-monitoring on auto-promoted hits

**Source:** Resonanz: "review internal Slack channels, flagging
language that suggests insider information." We don't have Slack
but we have the inbox. The same technique applied to OUR inbox:
LLM-check each auto-promoted record's notes against a hard-coded
"this looks like a fraud / accounting irregularity / pump-and-dump"
prompt and flag any borderline hits before they reach universe.md.

**Technique:** in `src/inbox_promote.py`, before writing rows to
universe.md, run each candidate's notes through an LLM check
prompt: "Does this disclosure look like (a) a real restructuring,
(b) a routine corporate-action, (c) potential fraud / pump pattern?"
Skip promotion if (c).

**Slot:** `src/inbox_promote.py` — optional LLM-check stage between
the dedup step and the write step.

### 21. Claude / GPT-augmented YAML draft generation from filings

**Source:** [AlphaSense's 2025 innovations release](https://www.prnewswire.com/news-releases/alphasense-innovations-in-end-to-end-ai-workflows-for-structured-financial-data-expert-content-and-enterprise-intelligence-fuel-rapid-growth-302577532.html):
"end-to-end AI workflows for structured financial data" now ingest
expert content + filings + earnings transcripts in a single pass.
The endpoint state of this is: an LLM can draft a Tier-3 skeleton
YAML directly from an SEC filing.

**Technique:** extend `src/yaml_skeleton.py` to optionally call an
LLM API to populate the `deal.mechanic` narrative directly from the
issuer's most recent material-event filing (8-K, 6-K, NT 10-Q, etc.).

**Slot:** `src/yaml_skeleton.py` — `--llm-augment` mode. Reads the
issuer's most recent filings from inbox, sends to LLM with the
canonical YAML schema as the response format. Output gets manual
review before commit (Tier 3 → Tier 2 promotion still requires
human verification).

---

## Implementation sequencing — this week

Highest signal per hour of work:

1. **5-signal distress checklist (BBBY case) → src/score.py** —
   5 new SCORE_RULES dimensions, all derivable from existing 10-K
   data. Closes a real gap and is fully back-compat.
2. **Wirecard 6-symptom checks → red_flags block** — 6 new
   boolean fields in `EXPECTED_RED_FLAGS`. Trivial schema work;
   immediate uplift in fraud-detection rigor.
3. **Pre-pack pattern in src/pacer_poll.py** — extend the existing
   PACER poller to surface same-day-4-filing patterns. The poller
   infrastructure already exists; just add the detector.
4. **Insider-cluster-sells in src/cluster_buys.py** — flip the
   existing buy-side detector to also detect sells. Same code,
   complementary signal.
5. **Greenberg 5%/10 concentration rule → src/portfolio.py** —
   opt-in `--concentration greenberg` mode. Provides an alternative
   sizing methodology without disrupting current default.
6. **KEDM archetype extension (K1-K8) → src/universe_screen.py** —
   widens the framework's event taxonomy beyond restructuring.
   8 new ARCHETYPE_PATTERNS entries.

Deferred (require external work or paid feeds):

7. Schilit XBRL screen (`src/shenanigan_screen.py`) — needs XBRL
   parser; ~1-2 days of work.
8. Bond prospectus / indenture LLM extraction — needs API key
   + spend governance.
9. ICE BofA bond-spread monitor — FRED endpoint is free but
   per-issuer series require Bloomberg or ICE Data Indices subscription.
10. Index reconstitution calendar — three feeds; non-trivial but
    one-time setup.

---

## Sources

Concrete primary sources cited in this synthesis (in order of first
appearance):

- [Lazard — The 2020-2025 Sovereign Debt Crisis](https://www.lazard.com/research-insights/the-2020-2025-sovereign-debt-crisis-what-have-we-learnt-and-what-lies-ahead)
- [Praetorian Capital — Idea Brunch with Kuppy](https://www.readideabrunch.com/p/idea-brunch-with-harris-kuppy-kupperman)
- [Praetorian Capital Fund Q4 2023 letter](https://seekingalpha.com/article/4664015-praetorian-capital-fund-q4-2023-investor-letter)
- [Dan McCrum on Wirecard — 5 takeaways](https://alternativefundinsight.com/mccrum-takeaways/)
- [Hindenburg Research methodology page](https://hindenburgresearch.com/about-us/)
- [Yahoo Finance / GuruFocus — 5 BBBY warning signals](https://finance.yahoo.com/news/bed-bath-beyond-5-fundamental-175317783.html)
- [Resonanz Capital — How hedge funds are really using GenAI](https://resonanzcapital.com/insights/how-hedge-funds-are-really-using-generative-ai-and-why-it-matters-for-manager-selection)
- [AlphaSense 2025 innovations release](https://www.prnewswire.com/news-releases/alphasense-innovations-in-end-to-end-ai-workflows-for-structured-financial-data-expert-content-and-enterprise-intelligence-fuel-rapid-growth-302577532.html)
- [Norbert Lou / Punch Card Mindset — Guru Gems](https://www.gurugems.org/p/norbert-lou-the-punch-card-mindset)
- [Glenn Greenberg / Brave Warrior — Insurance NewsNet profile](https://insurancenewsnet.com/oarticle/glenn-greenberg-portfolio-uncovered-top-holdings-and-strategies)
- [Howard Schilit — Financial Shenanigans, 4th ed.](https://www.mheducation.com/highered/product/financial-shenanigans-fourth-edition-how-detect-accounting-gimmicks-fraud-financial-reports-engelhart-schilit/9781260117264.html)
- [Behind the Balance Sheet — Dan McCrum interview](https://behindthebalancesheet.com/podcasts-singles/11-dan-mccrum/)
