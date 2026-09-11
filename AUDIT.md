# Cyclepapa Pipeline Audit

Brutally honest assessment of the framework as it stands at 25 scoring
layers, ~6,169-ticker universe, 30+ data files. Where we're solid;
where we're papering over weakness; where we're vulnerable.

The intent is not to inventory everything that could improve. It is
to identify the **load-bearing weaknesses** — things that, if a sharp
critic poked at the framework today, would expose us.

---

## SEVERITY 1 — These are foundational weaknesses we cannot defend

### S1.1 No backtest has ever been run

We claim alpha by citing Cohen-Malloy-Pomorski (+10%/yr opportunistic),
Eberhart-Altman (+24% / 200d), Bonaime-Ryngaert (3y persistence on
direction-confirmed buybacks), etc. Each cited paper has its own
backtest. **Our SPECIFIC composite that weights and combines these
has zero realized-return validation.**

If a portfolio manager asked "show me the IC of your composite vs
forward 6m/12m returns, stratified by mcap and sector", the honest
answer is *we don't know*.

This is the single most uncomfortable gap. Until we do this, "best of
universe" remains a *plausibility* argument, not measured evidence.

**Cost to fix:** 2-3 focused days. Pull historical prices for the
universe; for each ticker on a date 12-18 months back, recompute
what the composite WOULD have said; measure forward excess return vs
SPY. Stratify by mcap, sector, layer-firing count. Publish IC per
layer + overall.

### S1.2 Sector concentration is invisible

The convergent top-20 looks like:
- ADT (security), FOUR (payments), HUBS (SaaS), OLED (tech), GPGI
  (consumer), EPAM (consulting), DXC (IT services), CRM (SaaS),
  POOL (consumer), BLND (mortgage), ZTS (animal health), HDSN
  (refrigerant), GIII (apparel), PAR (restaurant tech), BV (BPO).

That's a **tech + consumer-cyclical concentration**. Probably 70%
explained by two factors. If a recession hits both, the basket
implodes simultaneously. We do not currently track this.

**Cost to fix:** half a day. Add a sector-neutral ranking sleeve
(best within each GICS sector) alongside the universe-wide ranking.
Surface concentration in the cover tab.

### S1.3 PSU forensics is the rate-limiting layer for half the universe

40% of the 6,164 universe has no PSU program (1,754 tickers).
Another 1,989 have proxy data but their PSU forensic score is 0.
Net: **~3,743 names cannot meaningfully contribute on the PSU leg**,
which is the most-cited differentiator of the framework.

This means our convergent set is structurally biased toward names
that grant PSUs — which correlates with company size, industry
(SaaS / consumer / industrial favored over biotech / financials
/ utilities), and management sophistication.

**Cost to acknowledge:** 0 — it's documented now. But the implication
is that for biotech, financials, and small-cap pinks, we need
DIFFERENT primary screens.

### S1.4 No validation that "layers firing" treats layers as independent

The consensus says ADT fires 8 layers and is therefore the empirical
top of universe. **But are those 8 layers actually independent?**

For example: PSU + opportunistic insiders + verified buyback + bb
insider overlay — these all reward "company doing the right thing
for shareholders." They are positively correlated. Each one firing
on the same name isn't 4 independent confirmations; it's 1.5
independent confirmations.

We have not computed the pairwise correlation matrix of layer scores.
We do not know how much our "8 layers" really represents.

**Cost to fix:** half a day. Compute layer-pair correlation across
the universe. If two layers correlate > 0.7, fold them into a
"composite leg" with shared weight. Re-publish layer count using
this collapsed view.

---

## SEVERITY 2 — Significant weaknesses limiting framework precision

### S2.1 Form 4 history depth: 6-12 months, need 3+ years

Cohen-Malloy-Pomorski requires 3 years of history to distinguish
routine (mechanical RSU vesting) from opportunistic (informational)
insiders. We have ~6-12 months. Currently the classifier flags
every insider as opportunistic — which functions as a filtered F4
strengthener but isn't the ~10%/yr alpha signal.

Backfilling Form 4 for the top-1000 names by mcap × insider activity,
over 36 months, would convert the classifier from approximate-to-real.

**Cost to fix:** 1-2 days. EDGAR submissions API gives historical
Form 4 by CIK; bulk-fetch over 3y for the priority list.

### S2.2 Coval-Stafford is a proxy, not the real signal

Built as institutional% + short% + drawdown approximation. The real
Coval-Stafford signal requires N-PORT mutual fund holdings monthly
deltas. We do not yet ingest these. Our current proxy will fire on
quality-stress names (heavy institutional + drawdown) that aren't
actually being fire-sold.

**Cost to fix:** 5-7 days. Build N-PORT parser; SEC publishes them
quarterly per fund. Each fund holdings file is ~3-10MB JSON.

### S2.3 No tracking of when each layer was last refreshed

Some scans are 6 weeks old. Others ran today. Our consensus weights
them equally. A 6-week-old tender_scan may be missing names that
have started a tender in the meantime.

**What we need:** per-layer `last_refreshed` timestamp + age-decay
weighting + a dashboard showing freshness per layer.

**Cost to fix:** 1 day. Add timestamp to every output JSON; add
decay multiplier to consensus.

### S2.4 No quarterly 10-Q parser

We use annual data: DEF 14A (annual), 10-K (annual), yfinance balance
sheet (annual). For NCAV, current ratio, debt levels, cash burn —
these change quarterly and our data is up to 12 months stale on the
worst case. Whitman "Safe & Cheap" gate and NCAV are particularly
vulnerable.

**Cost to fix:** 2-3 days. Extend EDGAR full-text scan to 10-Q;
parse balance sheet items into a quarterly time series.

### S2.5 No bond / credit spread overlay

Klarman's distressed-claim-ladder method (and the BBGI archetype
Case E in workbook) explicitly needs bond prices. A name with
unsecured bonds at 35¢ is a different beast than at 75¢.

We currently track 8-K exchange-offer keywords but not the bond
prices themselves. We can't compute distressed equity from
fulcrum-security position.

**Cost to fix:** 3-5 days. TRACE has dealer-reported corporate bond
prices (FINRA, publicly accessible); subscribe + nightly pull.

### S2.6 No foreign markets

The Special Situations Sourcing Playbook explicitly cited Japan
(TSE PBR<1 reform), Korea (Value-Up + treasury cancellation), UK
(schemes of arrangement / trust wind-downs) as the highest-EV
under-covered terrain. **Our universe is 100% US.**

**Cost to fix:** 5-10 days per jurisdiction. yfinance covers the
non-US tickers we need; the harder part is the local filing
language. Japan PSU plans don't even exist; we'd score governance
differently.

### S2.7 No insider lobbying / FOIA / regulatory event data

Whose Form 4 buys correlate with FDA approval, antitrust clearance,
state contract awards? OpenSecrets + LDA-2 lobbying disclosures are
public. We don't ingest them.

This is the difference between "insider believes something" and
"insider HAS something." High-value but heavy to build.

---

## SEVERITY 3 — Operational hygiene gaps

### S3.1 No orchestration / scheduler

Every scan is manually invoked. No cron / no central
"refresh_everything" runner. If we walk away for a week the data
goes stale silently.

**Cost to fix:** 1 day. Write `refresh_all.sh` that runs the layers
in dependency order with appropriate sleeps. Wire to cron.

### S3.2 No error telemetry

Some scans fail silently — empty output looks identical to "scan
worked, found nothing." We had this exact bug with the tender HTML
fetcher (0 cached, looked like 0 hits).

**Cost to fix:** 0.5 day. Each script writes a `meta` field with
`{n_fetched, n_failed, n_passing, runtime_s, started_at, exit_code}`.
Central dashboard tab in xlsx surfaces meta from every layer.

### S3.3 Many scoring weights are heuristic guesses

The +25 / +18 / +12 / +6 / +4 scoring buckets I wrote into each layer
are not derived from anything. They're "feels reasonable" numbers.
Tiny changes ripple through the composite.

**Cost to fix:** 1-2 days after the backtest is built. Use the
backtest to learn weights per layer via ridge regression on
forward returns.

### S3.4 No xlsx diff / "what changed since last week"

The workbook is regenerated fresh each commit. There's no way to
see "ADT was at rank 7 last week, jumped to rank 2 this week." That
delta is the actionable signal.

**Cost to fix:** 1 day. Snapshot last-week consensus; diff and add
a "Delta This Week" tab.

### S3.5 25+ JSON files growing without schema versioning

Each layer writes its own JSON. Field names drift (e.g.,
`max_cluster_size` in one, `n_opportunistic_buyers` in another). If
we ever change a layer's schema, every downstream consumer breaks
silently.

**Cost to fix:** 2 days. Define a `LayerOutput` Pydantic schema
with `{ticker, score, last_refreshed, reasons, layer_version,
layer_name, raw_fields}`. Migrate all 25 layers.

### S3.6 No tests

Zero automated tests run. The whole framework is "did the script
finish without printing an exception?" If a refactor breaks the
opportunistic classifier silently, we won't know until the
convergent list looks weird three weeks later.

**Cost to fix:** 2-3 days. Property tests on each layer ("score
function is bounded", "no NaN propagates", "ticker universe is a
subset of cancel_10b5_1"), integration test on consensus.

### S3.7 Single workbook builder is ~1500 lines

`build_most_asymmetric_xlsx.py` has become a monolith. Adding a tab
requires understanding the existing structure. Refactor would help
future tabs ship faster.

**Cost to fix:** 2-3 days, low return. Defer.

---

## SEVERITY 4 — Coverage and completeness

### S4.1 No options / IV data
Realized vol vs implied vol divergence is a tradeable signal.
Gamma squeeze pattern detection (high short interest + retail option
buying + low float) caught GME, AMC. We don't see it.

### S4.2 No analyst estimate dispersion
Krishnaswami-Subramaniam (in the academic agent's notes) showed
that pre-spinoff information asymmetry — captured by analyst
estimate dispersion — predicts spinoff CAR. We don't ingest analyst
estimates.

### S4.3 No biotech catalyst calendar (PDUFA, AdCom)
For our biotech long tail (Vincerx, Gossamer Bio, etc.) the
single biggest catalyst is the FDA event. We don't track PDUFA
dates from clinicaltrials.gov or Drugs@FDA.

### S4.4 No earnings calendar / whisper data
EPS surprise + post-earnings drift is a documented anomaly. We
have nothing here.

### S4.5 No short-borrow rate data
Short interest doesn't tell you the *cost* of being short. Hard-
to-borrow + high borrow rate signals shorts are committed at
high cost — bullish for the long. We don't track this.

### S4.6 No 13F change tracking
Coval-Stafford partially addresses this with our proxy. The real
13F delta layer would surface "JPM dumped 30% of their position
in X this quarter" — which the public reports but we don't parse.

---

## What's working that we shouldn't break

These are the load-bearing strengths. If a refactor breaks them,
the framework loses real value.

1. **Coverage-normalised scoring.** The `sqrt(7 / n_layers_present)`
   reweighting in `grand_unified_ranker` correctly handles names
   missing some layers. Don't regress this.

2. **All layers are additive.** Tier 1, 2, 3, NCAV, activist
   added without modifying existing weights. Preserve this
   discipline — never silently change a leg's score.

3. **Editorial overlay vs membership decision separation.**
   Annotations dictionaries are typed-out by hand; membership
   decisions are derived from disk. Audit script
   (`verify_universe_methodology.py`) checks this every run.
   Maintain the discipline.

4. **Full universe (6,169) is processed every consensus run.**
   No top-N truncation. This was a hard-won fix; preserve it.

5. **The proxy_scan PSU forensics is genuinely deep and unique.**
   Forward-conditional cond_cats, plan-evolution flags, gov_score
   composition — no other framework reads DEF 14A this way. The
   capacity-cycle / activist / spinoff layers are all useful, but
   the PSU leg is the proprietary moat.

---

## Priority of fixes — what to build first

If you can build only 3 things:

1. **S1.1 backtest** — without it, alpha claims are aspirational
2. **S1.2 sector-neutral ranking** — without it, we have a hidden
   factor bet
3. **S2.3 freshness timestamps** — without it, stale data drives
   present-tense recommendations

If you can build 5:

4. **S1.4 layer correlation matrix** — to know how independent the
   "layers firing" count really is
5. **S2.1 Form 4 3-year history backfill** — to make Cohen-Malloy
   actually work as intended

The remaining items can be sequenced over weeks. Several (foreign
markets, options data, biotech calendar) are mandate-specific and
should be built only if the user is actually trading those
mandates.

---

## What this audit is NOT saying

This is not a "the framework is broken" assessment. The framework
correctly identifies several known structurally asymmetric names
(HFFG, ADT, NUS, LMT) using signals other systems don't read. It
handles the 6,169 universe systematically. It captures rare
forcing-function patterns (BBGI archetype, post-Ch11 emergence,
Voss CIC triangulation).

The honest statement is: **the framework is a structurally sound
pattern-recognition system that has not yet been validated against
realized returns.** Closing that loop converts it from "plausibility
argument" to "measured edge."

That's S1.1. Everything else is downstream of it.
