# Sources & Analysis Audit — what we consume, what we trust, what we do with it

Date: 2026-08-20. Completes the audit series: INCENTIVE_AUDIT.md
(extraction correctness), COVERAGE_AUDIT.md (breadth/truncation), and
this — the authority of the sources themselves and the quality of the
analysis performed on them. Integration counts measured by grep over the
live codebase; absences verified the same way.

---

## Part 1 — The source ledger, by authority tier

**Tier 1 — Primary regulatory (SEC).** ~110 integration points
(EFTS full-text 41, Archives/`www.sec.gov` 46, submissions/XBRL
`data.sec.gov` 27). DEF 14A, 8-K, Form 4/144, 13F, 10-Q/K, N-PORT,
tender schedules, XBRL facts. This is the right backbone: the system of
record, versioned, point-in-time, free. One caveat: EFTS
(`efts.sec.gov/LATEST/search-index`) is an unofficial endpoint that
500s intermittently (observed) and could change shape without notice —
every 8-K engine depends on it, so the retry wrapper is load-bearing.

**Tier 2 — Primary content via third-party availability.** investegate
(RNS re-publisher, 4 integration points): the *content* is primary
regulatory disclosure; the *availability* is a scraped aggregator that
renders 5 items/page server-side. Fine for a monitor, not an archive.

**Tier 3 — Third-party market data: yfinance, 188 references — the
most-referenced source in the codebase and the least reliable.** It has
broken twice this project (curl_cffi TLS, rate-limiting), covers 46% of
the universe, and its quotes/mcap gate a dozen downstream layers. Our
concentration risk is inverted: the most fragile source is the most
depended-upon. (COVERAGE_AUDIT item C — the XBRL frames store — removes
the *fundamentals* half of this dependence; a free daily-price mirror
such as Stooq's bulk CSVs would remove the *price* half.)

**Tier 4 — Hand-curated.** sohn_pitches (conference coverage),
asymmetry_events (revealed-preference events), hidden_asset_watch (SSP
et al.), emergence_master_snapshot. All carry explicit provenance and
refresh instructions — honest, but staleness-by-design; each should be
dated on the Coverage tab (freshness ledger covers only some).

**The unconsumed fleet (biggest finding).** The sibling branch
(capital-structure subsystem) runs ~27 pollers the 38-layer engine never
sees: `distressed_13d_poll`, `going_concern_poll`,
`equity_committee_poll` (an equity committee in Ch11 is one of the
strongest stub-survival signals that exists), `form15_poll`,
`eightk_items_poll` (item-level routing), `pacer_emergence_poll`,
`credit_spread_poll`, `lobbying_poll`, `ofac_poll`, plus international
feeds (HKEX, JPX/TDnet, ASX, Euronext, JSE, CVM, SEDAR+). Exactly ONE
(emergence_master) is cross-fed today. Widening that bridge is the
cheapest source expansion available — the collection code is already
written, tested, and in the same repository.

**Missing entirely (grep-verified zero modules):**

| Source | Why it matters | Cost |
|---|---|---|
| FINRA short interest (bi-monthly official file) | replaces yfinance short% with the primary source; squeeze/crowding signal | free |
| Form 4 SELL codes (S) | we scan buys only; the sell side exists only via Form 144 *proposals* — an asymmetric blind spot | free (same feed we already parse) |
| 10-K Item 1A risk-factor diffs | year-over-year additions are management's own new-worry disclosures; EDGAR-native | free |
| Earnings-call transcripts | tone/guidance deltas; the one text source regex can't reach | paid or scrape-fragile — defer |
| Options market (put/call skew, term structure) | market-implied asymmetry check on candidates | yfinance has chains; fragile |
| TRACE bond prints | credit market's live verdict on distressed names | free via FINRA, parsing effort |
| 13G (passive→active flips), N-CEN | ownership structure changes | free, low priority |
| Proxy advisors (ISS/GL) | vote recommendations | paid — skip |

## Part 2 — The analysis audit

**A1 (the big one) — Zero outcome validation.** 38 layers, every weight
a hand-set integer, and not one layer has been tested against forward
returns. The single validation in the codebase is one point-in-time
case (PSIX, May-2024 — it passed, which is evidence the *assembly
logic* works, not that the *weights* are calibrated). Most signal JSONs
already carry event dates; a signal-date event-study harness (signal →
forward 1/3/6/12-month return vs universe median → per-layer hit-rate
and information coefficient) needs only a daily price store. This
converts the framework's honest limitation ("structurally sound
pattern-recognition, not yet validated alpha") into a measured table —
and would let weights be set by evidence instead of judgment.

**A2 — The correlation analysis is display-only.** We compute pairwise
layer correlation and report "38 raw ≈ N effective-independent," but the
consensus still credits each layer equally: a name firing the three
correlated insider layers gets 3 confirmations' credit for ~1.5
independent facts. A cluster-aware consensus column (contribution ÷
cluster size, published *alongside* the raw count, not replacing it)
closes the gap between what the methodology tab admits and what the
ranking does.

**A3 — Regex-only semantics has a measured ceiling.** Three audit
rounds found FP/FN classes by hand (negation, boilerplate, comma
truncation); each fix is a new fixed pattern awaiting the next failure
mode. The bounded upgrade: an LLM second-pass over the TOP-N candidates
only (the names that reach the workbook), extracting structured fields
regex cannot — full claim counts, covenant terms, waterfall mechanics,
negation-in-context — and validating the regex extraction. Cost scales
with the shortlist, not the universe.

**A4 — The book is one-sided.** Buy-side layers dominate 35-to-3
(bearish: f144, c10b51 negatives, caution flags). There is no
short-side assembly — no "deteriorating unit economics + maturity wall
+ insider selling + dilution machinery" conjunction, even though every
component's mirror image already exists in the codebase. Form 4 S-codes
+ FINRA short interest (Part 1) supply the missing inputs.

**A5 — Catalyst decay is inconsistent.** Some layers age their signals
(emergence, Sohn, step-change freshness), others never expire (tender
roles, 13E-3, activist letters, hidden-asset flags persist at full
strength indefinitely). The freshness ledger records ages but the decay
multiplier remains opt-in and unused. One pass to give every
event-layer an explicit half-life would stop stale catalysts from
impersonating live ones.

**A6 — Point-in-time discipline exists for one name.** The frames
store (COVERAGE_AUDIT C) makes as-of evaluation systematic: run the
assembly engine quarterly-as-of over trailing years and measure what
top-decile assemblies did next. That is the PSIX backtest generalized
from anecdote to distribution — and it is the prerequisite for trusting
A1's weight recalibration.

## Part 3 — Engineering errors & blind spots

All evidence first-hand from this project's own history or measured
against the live tree.

**E1 — Durability is bolted on, not built in.** Three sandbox resets
this session alone; only pushed commits survived. 36 of 46 JSON
producers write output non-atomically (`OUT.write_text` — a reset
mid-write corrupts the file); only 10 use the tmp+replace pattern
proxy_scan uses. The checkpoint-commit chain was invented reactively,
and the original push-retry loop tested the exit code of `tail`, not
`git push` — a failed push "succeeded." Rules that should be uniform:
atomic writes everywhere, push-verification against the remote ref
(`ls-remote == HEAD`), long jobs checkpoint-push natively.

**E2 — Concurrency was never designed for.** The checkpoint chain and
the interactive session commit to the same branch (non-fast-forward
collisions observed); two scanners writing the same JSON would silently
last-writer-win (avoided so far by care, not by locks); and a
`git rebase` onto the remote from a shallow clone with a divergent
graft replayed *years* of history and left conflict markers inside the
live scanner's source while it ran (survived only because Python had
the modules in memory). Standing rules: cherry-pick, never rebase, in
shallow clones; one writer per data file; a lockfile for the scan.

**E3 — Silent failure is the house style.** 341 bare
`except Exception` sites; every runner line ends `|| true`. This is why
the framework's own audits keep finding whole dead layers: an empty or
missing source file scores 0 exactly like "no signal" — spinoff and
arquitos fed zeros for weeks; the wrong-field-name class (score vs
points vs signed_score) silently killed 3 layers for longer. There is
no health gate that *distinguishes absent-source from zero-signal*. Fix
is small: rebuild_all ends with a source-health check that fails loudly
when any consumed file is missing, empty, or lacks its required keys.

**E4 — Copy-paste infrastructure.** `efts()`, `fetch_text()`,
`_valid()`, the display-names regex exist in 5 near-identical copies;
caps, retries and sleeps have already diverged between them, and the
EFTS parser fix had to be applied five times. One shared `edgar_efts.py`
with pagination (COVERAGE B1) retires the whole class.

**E5 — No CI, informal tests.** Tests are assertion scripts run by
hand via run_all.sh; there is no workflow file, so nothing runs on
push — a regression lives until someone remembers. The suite is good;
its *triggering* is the gap.

**E6 — Entity identity is ticker-keyed.** Everything joins on ticker
strings; the canonical SEC identity (CIK) is carried but never used as
the key. Measured consequence: NOTV and NOTVQ appear as two names in
the distressed output (same company, pre/post-suffix); the 13F
name-matcher mis-attributed an $86B position. Tickers change, dual-list,
and gain Q-suffixes; CIK-canonical keying with tickers as aliases ends
the class.

**E7 — Config by magic number.** Caps (40/50/60), windows (30/45/120/
150/180/365d), sleeps (0.15/0.3), thresholds (rank-decay 500, $25B,
8x, 550d) are hardcoded per file with no registry — several already
disagree between engines that should match (COVERAGE B1/B4 are both
this defect wearing different hats).

**E8 — Repo weight is an availability risk.** Large data snapshots in
git history caused the original 124MB truncated-clone incident and keep
every fresh sandbox on shallow fetches; the 2.6GB HTML cache lives in
archive commits this environment cannot even afford to pull. The
artifact strategy (data snapshots out of history — LFS, releases, or an
object store) was flagged in the first recovery and remains undone.

**E9 — Observability is print-based.** Scanner progress goes to stderr
buffers (lost when a pipe buffers or a sandbox resets); there is no
structured run ledger (which scan ran, when, over what inputs, with what
version) beyond proxy_scan's EXTRACT_VERSION — which exists precisely
because that one file needed it. Generalizing version-stamping + a runs
table in state.py makes every "why is this stale?" question answerable.

Priorities: E3 (source-health gate) and E1 (atomic writes) are
afternoon-sized and remove the silent-zero class entirely; E4+E7 merge
into the shared EFTS module; E6 (CIK keying) is the deepest change and
pays off across every join in the system.



1. **Event-study harness + daily price store** (A1/A6): the framework's
   largest open question — does any of this predict returns — becomes
   answerable. Everything else calibrates against it.
2. **Widen the sibling cross-feed** (sources): consume distressed-13D,
   going-concern, equity-committee, Form-15 and 8-K-item pollers as
   additive layers; the code already exists in-repo.
3. **Bear-side inputs** (A4 + sources): Form 4 S-codes in the existing
   sweep + FINRA short-interest file; then a short-side assembly mirror.
4. **Cluster-aware consensus column** (A2): one function, honest math.
5. **Catalyst half-lives** (A5): one decay pass over event layers.
6. **LLM second-pass verification** (A3): bounded to workbook-bound
   names; replaces the next three rounds of regex whack-a-mole.
7. **Risk-factor diff scanner** (sources): EDGAR-native new signal.

As with the coverage plan: nothing here alters existing weights until
A1's measurements justify it — additive discipline holds.
