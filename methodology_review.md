# Methodology Review — Critical Examination & Improvement Roadmap

A red-team review of the full system (`capital_structure_screening.md`,
`universe.md`, `shortlist.md`, `final.md`, `screen.md`). Organized as:
validity threats first (things that could make the whole exercise wrong),
then analytical enhancements, new methods, engineering, and process.
Each item states the flaw, why it matters, and the fix.

---

## 1. Validity threats — flaws that undermine the conclusions

### 1.1 No base rates. The framework has never been backtested.

Every asymmetry estimate in the system ("3–5×", "5–10× or zero") is
narrative, not empirical. We cite winners (Goodman 60×, Rolls-Royce 10×,
Rolls-Royce 10×) but have never measured the **full distribution** of
outcomes for distressed rights issues: what fraction multibag, what
fraction flatline, what fraction re-restructure? Without the denominator,
the case-study section is a collection of survivors, and the scorecard
thresholds (≥18/28 investable) are arbitrary.

**Fix.** Assemble a labeled historical dataset and measure conditional
base rates. This is feasible: LSE RNS archives contain essentially every
UK rights issue 2000–2020 (~hundreds of deals); EDGAR full-text gives US
exchange offers; the deal features we score (discount to TERP, insider
take-up, maturity extension, dilution) are all in the announcement
documents. Target output: a table of *P(2× within 3 years | scorecard
bucket)* and *P(re-restructuring | scorecard bucket)*. Even 200 deals
gives usable signal. Until this exists, every score should be read as a
hypothesis, not a probability.

### 1.2 Hindsight contamination in the case studies

We scored Provident "8/28 *in hindsight*" — an explicit admission that
the scorecard cannot reliably be computed ex ante. Several case scores
quietly use information unavailable at deal date (e.g., we know Spirit
refiled, so it scores 3; would the framework have scored it 3 in March
2025, when it had just shed $795m of debt and taken $350m of new equity?
Probably not — it would plausibly have scored 14–16).

**Fix.** Re-score every historical case **point-in-time**: only
information available on announcement day. Keep two columns: ex-ante
score and outcome. The gap between them *is* the measure of the
framework's real predictive power, and identifies which dimensions are
actually knowable at decision time (insider participation: yes; "second
restructuring risk": mostly not).

### 1.3 Asymmetry multiples without probabilities are not expected values

"3–5× upside, 70% downside" is incomplete until multiplied by
probabilities. Kaisa "5–10× or zero" at P(bull)=15% is EV ≈ 0.75–1.5×
invested capital — i.e., *negative expected value at the midpoint*. The
current tiering ranks by upside magnitude, which systematically favors
binaries over steadier compounders.

**Fix.** Force every Tier 1/2 name through an explicit EV line:
`EV = P(bull)×bull + P(base)×base + P(bear)×bear`, with the probabilities
written down and dated. Rank by EV and by EV per unit of drawdown, not by
headline multiple. Use fractional Kelly (¼ Kelly given parameter
uncertainty) for sizing instead of the current full/half/quarter-weight
tiers, which encode no probability information at all.

### 1.4 The alignment-gap ratio overstates mispricing for strategic buyers

Our headline metric (anchor entry ÷ market) treats the anchor's price as
a pure financial valuation. It isn't. The French State paying €4.00 for
Eutelsat is buying *sovereign LEO capability* — its utility includes
IRIS² industrial policy, not just equity returns. Bharti gets OneWeb
synergies. VW PowerCo's 65% premium to PMET's VWAP buys *offtake
security*, which a public shareholder does not receive. The gap is
therefore an upper bound on mispricing, not an estimate of it.

**Fix.** Decompose each alignment gap into (a) financial component and
(b) strategic-utility component. Practical heuristics: gaps from
*financial* anchors (Gilinski at Metro, 3G at Americanas, Desmond at
MPVD) deserve near-full weight; gaps from *sovereign/strategic* anchors
deserve a haircut of 30–50%; gaps attached to offtake or procurement
agreements should be cross-checked against what the offtake alone is
worth. Add a scorecard sub-field: "would this anchor still have paid
this price with no strategic side-benefit?"

### 1.5 Verified and unverified claims are indistinguishable

The shortlist mixes numbers I generated, numbers from pasted third-party
research (citation markers stripped), and numbers from memory. There is
no way for a reader — including us, three months from now — to know
which deal terms have been confirmed against a prospectus and which are
hearsay. For a system whose core claim is "read the primary documents,"
this is self-undermining.

**Fix.** Per-name source ledger: each load-bearing number (issue price,
anchor stake, maturity dates, debt quantum) gets a status tag —
`[verified: <doc, date>]` / `[reported: <outlet>]` / `[unverified]` —
and sizing is blocked until the five key numbers per name are verified
against the primary filing. This converts the §2 scorecard into
something auditable.

### 1.6 Returns lack a time axis

"Peak ~60×" (Goodman) is not a realizable return — it's the maximum of
a path. Goodman's 60× took 12 years; Lotus's 8.6× took two months. The
system never distinguishes IRR from multiple, which makes cross-case
comparison meaningless and flatters slow compounders.

**Fix.** Standardize all outcome claims to: multiple at fixed horizons
(1y / 3y / 5y from deal close), plus max drawdown along the path. Adopt
the same convention for forward asymmetry estimates ("3× over ~3 years
≈ 44% IRR" reads very differently from "3× over 8 years ≈ 15%").

### 1.7 The "basket" is not diversified — it's the same three bets in 60 tickers

Factor-decompose the current list and most of it collapses onto: (1)
China property/policy beta (Sunac, Kaisa, CIFI, Sino-Ocean, Novaland,
Vanke-watch), (2) critical-minerals/EV-cycle beta (LAC, PMET, Lynas,
Vulcan, Lotus, Paladin, Sigma, Liontown, Sibanye), (3) EM currency and
small-cap illiquidity everywhere else. A 60-name equal-weight basket of
these is roughly a 3-factor portfolio with concentrated tail risk, not a
diversified recovery book.

**Fix.** Tag every name with its dominant return driver (commodity
cycle / policy decision / idiosyncratic operational / multiple
normalization) and cap *factor* exposure, not name count. Separately,
be honest per-name about how much of the thesis is **structure alpha**
(the recap changed the payoff) versus **cycle beta** (you're long
lithium with extra steps). Mountain Province is mostly diamond beta plus
a genuinely idiosyncratic alignment structure; Paladin is nearly pure
uranium beta and doesn't need this framework to own.

---

## 2. Analytical enhancements

### 2.1 Replace the additive scorecard with a calibrated model

The 14-dimension equal-weight 0–2 scorecard double-counts correlated
dimensions (anchor identity ↔ backstop terms ↔ alignment gap are nearly
the same fact measured three times) and underweights the two veto
dimensions we already concede dominate (#11 catalyst, #13 second-RX
risk). Once the base-rate dataset (§1.1) exists, fit something simple —
logistic regression or a decision stump per dimension — and let the data
set the weights. Until then, restructure the scorecard hierarchically:
three veto gates (alignment, maturity wall, catalyst) that must all
pass, then a small additive score among survivors. Fewer numbers,
honestly derived.

### 2.2 Bayesian updating instead of re-tallying

The framework says "re-score on every amendment," which invites anchoring.
Better: treat the initial scorecard as a prior in odds form, and treat
each subsequent event as a likelihood ratio. Insider open-market buy
during the subscription window ≈ LR 2–3×; backstop investor selling rump
within 90 days ≈ LR 0.2×; state backstop made conditional (Vanke) ≈ LR
0.1×. This makes "how much should one Form 4 move my conviction?" a
stated, criticizable number instead of a vibe.

### 2.3 Bonds lead equity — use the cross-asset signal we already describe but never operationalize

The fulcrum-math section (§4) computes implied recoveries but the system
never uses *relative* moves: when an issuer's bonds rally 15 points and
the equity is flat, the equity is lagging information the credit market
already has (this is one of the best-documented distressed phenomena).
Add to the weekly cadence: Δ(bond price) vs Δ(equity) for every active
name; flag divergences >10 points / 4 weeks in either direction. TRACE
covers the US names; for Eutelsat/Worldline-type names use listed bond
prices. The same data gives a live read on dimension 9d (implied
recovery) instead of the static at-filing number.

### 2.4 Structural credit model as a sanity check

Replace narrative "equity is a call option" with the actual model: a
Merton-style distance-to-default using PF debt, equity vol, and asset
value gives (a) a model equity value to compare against market, and (b)
a default probability to feed the EV math of §1.3. This catches cases
where the "cheap option" is actually fairly priced because vol is
enormous — a failure mode the current framework can't see.

### 2.5 Monte Carlo the waterfall instead of three scenarios

The bear/base/bull EV walk hides correlation between EBITDA and exit
multiple (both cycle-driven — they compress together, which fattens the
left tail far beyond what three discrete scenarios show). A 10k-draw
simulation over (EBITDA percentile, multiple percentile with ρ≈0.6,
dilution-event indicator) per name is a few dozen lines of code and
produces a real distribution: P(loss > 50%), P(3×), median IRR. The
three-scenario table stays as the communication layer; the simulation
becomes the sizing layer.

### 2.6 Sponsor track-record scorecards

The framework treats "Gilinski," "Křetínský," "Niel," "Mudrick,"
"Oaktree" as qualitative anchor-identity inputs. Their historical hit
rates are measurable: list every prior recap each repeat sponsor has
anchored and what happened to minority common alongside them within 3
years. Niel-adjacent stubs (Solocal, GAM) and Křetínský deals (Casino —
already flashing repeat-RX risk) would get empirical priors instead of
name-brand glow. This is a one-time research build with permanent reuse.

### 2.7 Crowding and edge-decay metrics

The alignment gap is public information; once it becomes consensus
(Eutelsat's gap has been written about widely), entry prices erode.
Track per name: short interest trend, borrow cost, 13F overlap with
event-driven funds, and sell-side initiation count. Add a "crowding"
field to the candidate schema; an uncrowded 2.5× gap can be better than
a crowded 6.9× one.

### 2.8 Catalyst calendar with magnitudes

"C7 dated" is binary in the current screen. Upgrade to a dated catalyst
ledger per name: event, date window, P(favorable), expected re-rate if
favorable, expected hit if not (e.g., Eutelsat: IRIS² programme
milestone, window 2026-2029, P≈55%, +180–350% / −30%). This converts the tier system
into a forward calendar the daily cadence can actually monitor, and
makes post-hoc calibration (§5.2) possible.

---

## 3. New methods worth adding

### 3.1 LLM-assisted term extraction (highest-leverage automation)

The discovery pipeline (§1 of the methodology) finds filings; a human
still reads 400-page documents. Add an extraction stage: LLM parses each
prospectus/scheme into a structured record — issue price, TERP discount,
backstop parties and fees, warrant strikes, maturity schedule before/
after, MIP terms, releases, new-money IRR (the Petrofac field), implied
liquidation recovery — with page-anchored quotes for each field so
verification (§1.5) is one click, not a re-read. Rules then compute the
quantitative scorecard automatically. This is the difference between a
methodology document and a screening machine, and it's now cheap to
build.

### 3.2 Options overlay for expressing convexity

For optionable names (LUMN, WOLF, WW, HE, IHRT, CHTR-style), long-dated
calls or call spreads express the same convex thesis with defined
downside, often at attractive prices because post-recap IV tends to be
elevated then decay. Conversely, elevated IV makes cash-secured puts a
paid entry into names you want anyway. Add an instrument-selection row
to the §4 matrix: "listed options exist → compare 2y call spread cost vs
equity drawdown risk." For binaries (WW at $10 vs $37 PT), options are
strictly better risk shapes than common.

### 3.3 The natural short leg / capital-structure arb

The false-friends list is currently dead weight — research effort that
generates no P&L. Two uses: (a) short the legacy stub in identified
creditor-takeover deals between announcement and effectiveness (Atos,
Country Garden pattern), where dilution math is known and the drift is
reliably down; (b) cap-structure arb in Bucket C names — long fulcrum
debt / short equity — which monetizes the same analysis with much lower
variance. Even if shorting is out of mandate, tracking the false-friend
basket's forward returns validates (or falsifies) the framework's
negative calls — see §5.2.

### 3.4 Scheme-document NLP forensics

Hypothesis worth testing on the historical dataset: document complexity
correlates with creditor value extraction. Releases-and-indemnities
section length, count of new instrument classes, intercreditor
amendments, MAC carve-out density — these are extractable features. If
the correlation holds (it did directionally in Petrofac vs Pierre &
Vacances), it becomes a cheap automated red-flag scorer for incoming
deals.

### 3.5 Use the in-repo cycle tool for Condition 7

The repo's existing `cycle` Streamlit app (FFT/spectral cycle analysis
on FRED/yfinance series) is currently unrelated to the framework —
connect it. C7 for cyclicals is a claim about cycle position: run the
tool on diamond prices (MPVD), spodumene (PMET/LAC), uranium (PDN/LOT),
NdPr (MP/Lynas), and DRAM-style memory analogues, and emit a
"cycle-percentile" field per commodity-linked name. A trough claim
backed by spectral evidence and percentile rank beats "diamond cycle
near trough" as prose.

### 3.6 Rights-issue microstructure backtest

The event-timeline section asserts nil-paid rights trade 5–15% cheap and
rump auctions clear low — both are testable against the historical UK/
European rights dataset (§1.1 gives it to us for free). Measure actual
TERP-discount capture by entry window. If the claim survives, the
timing playbook gets empirical teeth; if not, cut it before it costs
money.

---

## 4. Engineering — the repo doesn't match the system it describes

### 4.1 One canonical data store; the five-file drift is already visible

Worldline is ranked #3 in `final.md` and #2 in `screen.md`/`shortlist.md`.
Tier definitions differ between `final.md` (top-25) and `screen.md`
(top-10) without either file referencing the other's supersession. The
same deal terms are hand-duplicated in up to four places. This is the
classic copy-paste data smell, and it will get worse with every update.

**Fix.** Restructure:

```
/data/candidates/<ticker>.yaml   # single source of truth per name
/data/sources.yaml               # verification ledger (§1.5)
/docs/methodology.md             # the framework (current main doc)
/src/score.py                    # compiles YAML → scores, tiers, tables
/src/screen_edgar.py             # the §1.8 poller, as real code
/src/waterfall.py                # §2.5 Monte Carlo
/output/screen.md                # GENERATED — never hand-edited
```

Per-name YAML carries: deal terms (with source tags), scorecard inputs,
catalyst calendar, kill criteria, state (watch/option/core/pass), and a
history block. Every markdown ranking becomes generated output. Rank
drift becomes impossible by construction.

### 4.2 Point-in-time snapshots

"Re-score on every amendment" requires versioned state. The YAML +
git history gives this almost for free *if* updates go through the data
files. Add a nightly snapshot job (or just disciplined commits) so that
six months from now we can ask "what did we believe about Sunac on the
day the MCBs converted?" — which is the raw material for §1.2's
point-in-time honesty and §5.2's calibration.

### 4.3 Actually build the ingestion pipeline

The methodology describes RSS feeds, regex tiers, and an EDGAR query
recipe — none of it executes. Minimum viable build, in order: (1) the
EDGAR full-text poller (code already drafted in §1.8 of the methodology,
needs ~an hour to make real), writing hits to `/data/inbox/`; (2) the
regex tierer over hit titles; (3) a GitHub Action or cron running it
daily and committing the inbox. UCC scraping, SEDI/PDMR feeds, and LLM
extraction (§3.1) layer on after. Until step (1) exists, the "daily
inbox of 5–20 candidates" is fiction.

### 4.4 Validation and CI

With YAML as source of truth: schema validation (required fields,
enum values for bucket/archetype/state), referential checks (every name
in a generated table exists in `/data`), and a "stale" linter (any
candidate untouched for 30 days without a `state` justification gets
flagged — enforcing the no-purgatory rule the methodology already
states but cannot currently enforce).

---

## 5. Process discipline

### 5.1 Define "win" — make the system falsifiable

Nowhere does the system state what outcome counts as success. Propose:
a pick "works" if it returns ≥2× within 3 years of entry without an
intervening restructuring event; the false-friend call "works" if the
name underperforms its sector by ≥30% or restructures again within 2
years. Write these down per name at entry. Without this, every outcome
can be narrated as consistent with the framework.

### 5.2 Forecast log + calibration scoring

Every dated claim (catalyst windows, kill criteria, asymmetry ranges)
goes in a forecast log with resolution dates. Score quarterly (Brier or
simple hit-rate). The first honest calibration report will be
uncomfortable and is the single highest-value process artifact this
system can produce — it converts the framework from a narrative engine
into an instrument that improves.

### 5.3 Mandatory pre-mortem per Tier-1 name

For each core position, a written bear memo by construction: "It is
2028 and this lost 70% — what happened?" The Spirit and Petrofac
post-mortems show the failure modes were visible ex ante (operating
impairment; disproportionate new-money IRR). The pre-mortem forces the
search for the specific document section where that failure mode would
show up *before* sizing, not after.

### 5.4 Exit and trim rules — the missing half of the playbook

Kill criteria exist; profit discipline doesn't. Multibaggers require
holding through 30–50% drawdowns, so price-based stops are wrong here —
but so is "hold forever." Propose state-based exits: trim when the
peer-multiple gap closes below ~20% (the re-rate is done — the Lotus/
Thai Airways situation); exit when the holding's thesis migrates from
structure-alpha to pure cycle-beta (you can own that cheaper and more
liquid elsewhere); full exit on any kill-criterion regardless of price.
Add a "completed arc" detector to the cadence: names re-rated past
Condition 7 move out automatically, the way Greek banks/Saipem/BMPS
eventually did in our own files — but months after the fact.

### 5.5 Quarterly framework retro

A standing review: which signals fired and worked, which fired and
failed, which dimensions never discriminated. Feed the answers back
into §2.1's weights. The framework grew by accreting every good idea
from each research pass (this review included); it also needs a
mechanism for *removing* dimensions that don't earn their complexity.

---

## 6. Prioritized roadmap

| # | Item | Effort | Impact | Why this order |
|---|------|--------|--------|----------------|
| 1 | Canonical YAML data store + generated outputs (§4.1) | Medium | High | Stops the drift that's already corrupting the rankings; prerequisite for everything below |
| 2 | Source-verification ledger, tag every load-bearing number (§1.5) | Low | High | The current mix of verified/unverified is the most dangerous latent flaw |
| 3 | EV lines with explicit probabilities + fractional Kelly sizing (§1.3) | Low | High | Re-ranks the book immediately; binaries fall, compounders rise |
| 4 | EDGAR poller as running code (§4.3) | Low | Medium | Makes the discovery pipeline real; one hour of work |
| 5 | Historical base-rate study on UK/US rights issues (§1.1) | High | Very high | The single thing that converts this from narrative to evidence |
| 6 | Point-in-time re-scoring of all case studies (§1.2) | Medium | High | Measures the framework's true ex-ante power; cheap once #1 exists |
| 7 | Bonds-vs-equity divergence monitor (§2.3) | Low | Medium | Best live signal we describe but don't use |
| 8 | Forecast log + quarterly calibration (§5.2) | Low | High | Compounds forever; start now so there's data in a year |
| 9 | LLM term-extraction stage (§3.1) | Medium | High | Scales the deep-read step, feeds #2 automatically |
| 10 | Monte Carlo waterfall (§2.5) + Merton check (§2.4) | Medium | Medium | Upgrades sizing from scenario tables to distributions |
| 11 | Sponsor track-record scorecards (§2.6) | Medium | Medium | One-time build, permanent prior |
| 12 | Factor tagging + exposure caps on the basket (§1.7) | Low | Medium | Prevents the 3-factor concentration masquerading as diversification |
| 13 | Options overlay + short-leg design (§3.2, §3.3) | Medium | Medium | New P&L from analysis already done |
| 14 | Cycle-tool integration for C7 percentiles (§3.5) | Low | Low-Med | Uses the asset already in the repo |

The honest summary: the system is now a strong *qualitative* framework
with good vocabulary, a wide discovery net, and a disciplined tiering
ritual — but its numbers (scores, asymmetries, tiers) are stories with
digits attached. Items 1–6 are what turn it into something whose error
rate can be known. Everything else is leverage on top of that.
