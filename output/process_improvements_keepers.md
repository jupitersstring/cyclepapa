# Process improvements — sourcing-only distillation

Across four meta-survey passes we surfaced ~67 techniques. Most are
diligence/sizing/discipline additions that *don't help us find new
opportunities*. Per user feedback, this document filters down to the
sourcing-only subset — pollers, signal layers, and archetype
extensions that widen what we can identify — and explicitly discards
the rest.

## Already live (sourcing pipeline as of v4)

Six pollers + two signal-layer scrapers feeding `inbox_promote.py`:

| File | Source | Geography | Status |
|---|---|---|---|
| `src/edgar_poll.py` | SEC EDGAR full-text Tier-S | US | live |
| `src/uk_rns_poll.py` | FCA NSM | UK | live |
| `src/sedarplus_poll.py` | SEDAR+ | Canada | live |
| `src/jpx_tdnet_poll.py` | TDnet | Japan | live |
| `src/pacer_poll.py` | CourtListener RECAP | US bankruptcy | live |
| `src/cvm_poll.py` | CVM IPE | Brazil | live |
| `src/asx_poll.py` | Markit Digital | Australia/NZ | live |
| `src/spinoff_radar.py` | EDGAR 10-12B / 8-K spinoff | US | live |
| `src/cluster_buys.py` | EDGAR Form 4 (buys only) | US | live |

## Keepers — sourcing-additive techniques to build

Ordered by signal-per-hour of work. All produce new candidates or
catch existing candidates earlier.

### 1. SC 13D / 13D-A poller — `src/sc13d_poll.py`

**Source:** v3 §1. Post-Feb 2024, initial 13D window shortened
from 10 calendar days to 5 business days; amendments within 2
business days; XML/iXBRL format mandatory from Dec 18 2024.

**Why it's sourcing:** activist 5%+ stake disclosures are the
canonical revealed-preference signal — and they now arrive 5+ days
faster than under the old rule, with machine-parseable XBRL.

**Effort:** ~½ day. Thin wrapper over existing `edgar_poll.py`
infrastructure with form filter `SC 13D, SC 13D/A`.

### 2. Form 15 going-dark poller — `src/form15_poll.py`

**Source:** v3 §13. Form 15 filings (Section 12 deregistration)
suspend periodic-reporting obligations immediately; stocks move to
OTC Pink Sheet at predictable discount windows (30-90 days post-
filing).

**Why it's sourcing:** clean, dated, machine-readable event with
predictable forced-selling. The framework currently has no poller
for this; opens an entire new archetype (K3 going-dark).

**Effort:** ~½ day. EDGAR query filter `FORMS=15-12B,15-12G,15-15D`.

### 3. Insider cluster SELLS detector — extend `src/cluster_buys.py`

**Source:** v2 §13. Wirecard insiders sold heavily late 2019; SVB
CEO sold $3.6m on Feb 27 2023, 10 days before the run. SEC Form 4
data is the same as the existing buy-side Lakonishok-Lee signal,
just flipped.

**Why it's sourcing:** identifies names with structural problems
BEFORE the public market does. Combined with the 10b5-1 box check
(post-Feb 2023 rule), unplanned insider sells within 60 days of
material events become a clean red flag.

**Effort:** ~1 hour. Same XML parser; flip the buy/sell direction;
add a `--sells` mode.

### 4. Pre-pack same-day-4-filing detector — extend `src/pacer_poll.py`

**Source:** v2 §12. When Chapter 11 petition + RSA + DIP financing
motion + disclosure statement all file the same day, equity is
worth zero — and the framework should *immediately* downgrade any
related universe.md row, not auto-promote it.

**Why it's sourcing:** keeps the inbox clean of doomed-equity hits.
We're currently adding Chapter 11 names without checking the pre-
pack signature.

**Effort:** ~1 hour. Post-filter on filing-day patterns already
captured by `pacer_poll.py`.

### 5. DOJ FCPA enforcement RSS — `src/doj_fcpa_poll.py`

**Source:** v4 §1. Post-EO 14209 Feb 2025, the DOJ FCPA enforcement
framework refocused on cartel/TCO cases. Smartmatic + Comcel/
Millicom DPAs are the post-pause precedent. Investigations are
multi-year overhangs that compress re-rate.

**Why it's sourcing:** affects EM-heavy names in the universe (our
LatAm + Africa exposures). Names with open FCPA investigations need
that fact surfaced in their YAML notes; names that *settled* FCPA
matters in 2024-25 may now be unblocked for catalysts.

**Effort:** ~½ day. RSS-based, lightweight; cross-reference DOJ
press releases against universe.md tickers.

### 6. OFAC General License feed — `src/ofac_poll.py`

**Source:** v4 §3. OFAC publishes General Licenses with named issuer/
sector scope + expiration dates. Venezuela energy GLs, Russia sov-
debt wind-down GLs, Cuba humanitarian carve-outs all created dated
re-rating windows for affected paper.

**Why it's sourcing:** for sanctioned-jurisdiction restructurings,
GLs *are* the regulatory calendar. Argentine paper, Venezuelan
equity, Russian residual claims all have OFAC-licensing windows
that determine when a thesis can be acted on.

**Effort:** ~½ day. JSON feed at `ofac.treasury.gov/recent-actions`;
clean parse.

### 7. Lobbying disclosure poller — `src/lobbying_poll.py`

**Source:** v1 §4. House LD-1/LD-2 + Senate LDA bulk downloads + STOCK
Act Member-trade disclosures. Lobbying registrations precede policy
decisions by 1-3 quarters; STOCK Act trades >$1k disclosed within 45
days.

**Why it's sourcing:** for A2 (sovereign industrial policy) names,
lobbying engagements are pre-anchor signals. When a target issuer
hires a former DOE Loan Programs Office director, that precedes the
ATVM term-sheet by ~6 months. Same for FCC spectrum, FDA AdComm,
defense procurement.

**Effort:** ~1 day. Quarterly bulk download + name-match + simple
schema.

### 8. KEDM archetype extensions K1–K8 — extend `src/universe_screen.py`

**Source:** v2 §3 (Praetorian / Kupperman's Event Driven Monitor).
Adds 8 event-driven sub-archetypes beyond our current 9 (A1-H):
K1 de-SPAC redemption arb, K2 post-IPO lockup expiry, K3 going-
dark (matched to #2 above), K4 SPAC trust arb, K5 reverse-merger
shells, K6 NOL shells, K7 litigation-settlement events, K8
commodity-cycle inflections.

**Why it's sourcing:** widens what the universe screener flags. Our
current taxonomy is restructuring-only; KEDM widens to non-distress
event-driven setups that share the asymmetry property.

**Effort:** ~1 hour per archetype = 1 day total. Pure keyword pattern
additions to `ARCHETYPE_PATTERNS` in `src/universe_screen.py`.

---

## Medium-priority keepers

### 9. Bond credit-spread monitor — FRED + ICE BofA OAS

**Source:** v2 §1. Bond OAS widening preceded SVB, BBBY, Wirecard
equity collapses by 1-3 quarters. Same pattern at sovereign level
(Lazard 9-default analysis).

**Why it's sourcing:** equity-event leading indicator. FRED is free
for sector-level OAS; per-issuer requires Bloomberg or ICE Data
Indices subscription.

**Effort:** ½ day for sector-level (free FRED); per-issuer deferred
to paid feeds.

### 10. Index reconstitution calendar — Russell/MSCI/S&P

**Source:** v2 §2. Forced-flow windows from quarterly Russell rebal
(June), semi-annual MSCI reviews (May/Nov), ad-hoc S&P committee
changes.

**Why it's sourcing:** deletion-driven forced selling creates entry
windows in already-distressed names. Adds dated context to the
existing universe.

**Effort:** ½ day. Three RSS / preliminary-list feeds. Manual
maintenance acceptable.

### 11. F2 equity carve-out / F3 butterfly archetype subcodes

**Source:** v3 §6 + v4 §7. Equity carve-outs and butterfly split-ups
share the F-spinoff event mechanic but differ in scoring (parent
retains conglomerate discount for carve-outs; cleaner price discovery
for butterflies).

**Why it's sourcing:** more precise archetype tagging = better
candidate scoring.

**Effort:** ~30 minutes. Keyword patterns in
`ARCHETYPE_PATTERNS`.

### 12. CFIUS calendar — Treasury annual report cross-reference

**Source:** v4 §2. CFIUS pendulum is binary risk to cross-border
anchor stakes (Nippon Steel / U.S. Steel 2025 reversal).

**Why it's sourcing:** flags A2 cross-border names where CFIUS
political risk is active; suppresses upside-only theses that ignore
the anchor's permission risk.

**Effort:** ½ day quarterly cadence. Manual update from Treasury.

### 13. ITC Section 337 investigations — `src/itc_poll.py`

**Source:** v4 §4. IP-driven exclusion orders frequently trigger
strategic-sale or going-private transactions within 6-12 months.

**Why it's sourcing:** identifies names entering a multi-month
transaction window. ITC EDIS has documented search API.

**Effort:** 1 day. Lower priority — narrower applicability.

### 14. SCDI / VRI archetype (K9) — sovereign warrant tags

**Source:** v3 §17. State-Contingent Debt Instruments / Value
Recovery Instruments from sovereign restructurings (Sri Lanka, Zambia,
Argentina GDP warrants).

**Why it's sourcing:** under-priced when sovereign cycles inflect
(Argentine GDP warrants traded 90% below model pre-Milei).

**Effort:** ½ day. Universe screener archetype addition + 5-10 manual
universe.md entries for known SCDIs.

### 15. Cusatis spinoff 24-36 month forward window

**Source:** v3 §4. Spinoff parent + sub combined deliver +25-34%
matched-firm-adjusted returns over 24-36 months *post*-distribution,
driven by takeover incidence. US-only — doesn't replicate in Europe.

**Why it's sourcing:** flags names *currently* in the Cusatis
window (i.e. spinoffs completed in last 6-36 months) as elevated
takeover candidates. Auto-derived from `deal.date` for F-archetype
names.

**Effort:** ½ day. Schema field + calc in `src/score.py`.

---

## Discard pile

Surfaced in earlier passes but not sourcing-additive — these are
diligence/sizing/discipline/case-study material. Documented here so
future passes don't re-surface them as gaps:

| Item | Pass | Reason discarded |
|---|---|---|
| Klarman 10-rule checklist | v1 | Diligence framing — doesn't surface new names |
| Marks "what does market need to believe" / consensus_pricing block | v1 | Diligence; per-name analysis |
| Moyer MFN / fiduciary-out / springing-covenant red flags | v1 | Diligence — applied to existing YAMLs |
| Voss catalyst_independence score | v1 | Diligence scoring |
| Walker days_since_recap field | v1 | Diligence scoring |
| Expert-network call protocol (expert_calls block) | v1 | Diligence |
| Klarman crowd-check / sell-side conflict / EBITDA range bands | v1 | Diligence (d20, d21 already added as no-op fields) |
| BBBY 5-signal distress checklist | v2 | Forensic accounting / diligence |
| Wirecard 6-symptom forensic test | v2 | Forensic accounting / diligence |
| Schilit 7 shenanigan categories | v2 | Forensic accounting / diligence |
| Hindenburg related-party graph | v2 | Diligence |
| Greenberg 5% min / 10 names max | v2 | Position sizing |
| Lou punch-card 5-year holdability gate | v2 | Position sizing |
| Praetorian inflection-quantification gate | v2 | Position sizing |
| SVB duration-mismatch + uninsured-deposit screen | v2 | Diligence (bank-archetype specific) |
| Endo MDL docket monitoring | v2 | Diligence (litigation-exposure specific) |
| Sovereign equity-recovery calendar | v2 | Diligence calendar; sovereign exposures already in universe |
| LLM-augmented diligence (bond prospectus, earnings call tone, compliance check, YAML drafting) | v2 | Diligence acceleration; no new candidates |
| Mallinckrodt + Endo catalyst_chain template | v3 | Schema for existing-name catalysts |
| Hertz solvent-debtor exception / make-whole exposure | v3 | Diligence (debt-stack specific) |
| Cineworld UK Part 26A cross-border re-restructure | v3 | Schema for refiled_within_12m extension |
| Akre three-legged stool block | v3 | Compounding discipline |
| Hayden Capital 100hr research budget | v3 | Discipline / honesty tracking |
| Aikya quality+valuation EM frame | v3 | EM discipline |
| Section 355 / 382 NOL preservation | v4 | Tax diligence |
| F-reorganization detector | v4 | Tax diligence (8-K already captured) |
| Schultz utilization / borrow-rate short-squeeze signals | v4 | Position sizing / risk management |
| Cremers-Petajisto vs AQR active-share debate | v4 | Position sizing discipline |
| Carlisle Acquirer's Multiple steady-state | v4 | Value framing / sizing |

---

## Recommended sequence — next 5 builds

1. **`src/sc13d_poll.py`** — activist signals, ½ day
2. **`src/form15_poll.py`** — going-dark forced-selling, ½ day
3. **Cluster sells extension to `src/cluster_buys.py`** — ~1 hour
4. **Pre-pack detector in `src/pacer_poll.py`** — ~1 hour
5. **`src/ofac_poll.py`** — sanctions-restructuring calendar, ½ day

Total: ~2 days of work covers the five highest-value additions.
Each produces inbox records that flow through the existing
inbox_promote → universe_screen → universe_risk_reward → workbook
chain.

After those five are live, the universe-wide top-10 will include
activist-13D'd targets, going-dark stubs at forced-selling discount,
and sanctions-window restructurings that don't currently surface.
