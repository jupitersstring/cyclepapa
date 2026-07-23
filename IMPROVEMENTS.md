# Honest improvements memo

Where the framework is weak today, ranked by ROI. The intent is
to be candid — not list everything that *could* be done, but to
distinguish the foundational gaps (without which the claim of
"empirically asymmetric" is unsupported) from polish items that
improve presentation without changing conclusions.

---

## Tier 1 — Foundational gaps

These materially weaken the claim that the convergent 12 are the
best-of-universe. Closing them changes what we conclude, not just
how we present it.

### 1.1 No backtest validation of the composite

**The problem.** We cite the Penn State spinoff result (+10%/yr
for 3y) and the Cohen-Malloy cluster result, but our specific
composite — the weighted blend of PSU forensics, governance,
buyback verification, tender role, 10b5-1, F4 — has *not been
backtested*. We are claiming alpha we haven't measured.

**What to build.**
- Per-signal alpha measurement: for each of the 8 rankers, compute
  6m / 12m / 24m forward excess return vs SPY for the top-N from a
  date 12-18 months back (so we have realised returns to evaluate).
- Combined-composite alpha: same procedure on `grand_unified_ranked`
  and `consensus_ranking` top-N.
- Stratified by mcap bucket (mcap < $500M, $500M-$5B, > $5B) and
  PSU%LTI bucket, because alpha probably differs by cohort.
- IC (information coefficient) by signal: rank-correlation between
  score and forward return.

**Decision point.** If the backtest fails (signals don't predict
forward returns), the framework needs reweighting before the
convergent twelve can be trusted as anything more than a
*pattern-recognition* exercise.

**Cost / Risk.** ~half-day to build the backtest harness if we
already have historical price series; *bigger* effort if we need
historical PSU and tender data to re-score historic accession
dates. Honest answer: probably 2-3 days for a defensible result.

### 1.2 Sector / industry tagging missing

**The problem.** The convergent 12 may be a concealed sector bet.
HFFG (food distribution), NUS (consumer), MAT (toys), LE (apparel),
GO (grocery), ADT (security), KMPR (insurance), RNR (reinsurance),
CSGP (RE data), LMT (defense), CDE (mining), GPRO (consumer
electronics) — eyeballing, it's a *consumer + value-cyclical*
basket. If we add sector tagging from yfinance metadata, we will
see whether "convergent" is structurally diversified or implicitly
a single-factor bet.

**What to build.**
- Add `sector` + `industry` columns to `consensus_ranking.csv`
  from yfinance overlay.
- Build a per-sector convergence histogram: how many names in
  each sector pass the convergence test? If consumer/value
  dominates, the framework is biased — possibly because PSU dollar
  hurdles are more common in consumer (B2C revenue is easier to
  forecast).
- A sector-neutral version of the ranker: best name per sector
  by composite score. Surfaces the *intra-sector* convergent
  best, not just the universe-wide best.

### 1.3 Form 4 coverage at 5.6% is the largest data gap

**The problem.** Form 4 P-buys layer covers only 346 of 6,164
tickers. The other 94% are *implicitly scored zero* on insider
conviction. That biases the composite *against* names whose
insiders have not bought recently — including names where
insiders may have bought 18 months ago but our scan window
missed them.

**What to build.**
- Expand Form 4 ingestion to the full universe with a rolling
  18-month window.
- Distinguish: (a) no Form 4 data scanned (true gap), (b) Form 4
  scanned, no recent buys (legitimate absence), (c) Form 4
  scanned, recent buys present (positive signal). Currently we
  conflate (a) and (b).
- Also add Form 4 *sales* layer (S code) — currently absent.
  Insider sales weighted negatively, with cap to avoid double-
  counting Form 144 proposed-sale signal.

**Why this matters most.** The unified composite top-50 was
heavily F4-cluster-weighted, so 47-of-50 different from
grand_unified. Closing this gap may change the convergent list.

### 1.4 No data-staleness or refresh-cadence flags

**The problem.** Some layers were last refreshed weeks ago. A
DEF 14A scanned in 2024 doesn't reflect a 2025 plan amendment.
A buyback_verify from January is missing the most recent two
quarters of shares outstanding. We don't track this per row.

**What to build.**
- Add `last_refreshed` timestamp per layer per ticker.
- In `grand_unified_ranker.py`, decay points by age:
  - DEF 14A older than 18 months → 0.7x weight
  - Form 4 cluster older than 90 days → 0.5x weight
  - Tender filing older than 60 days → 0.5x weight (since the
    bid may have closed)
  - Buyback verify older than 90 days → refresh required
- Surface "stale" warnings in the Excel.

**Decision point.** Some convergent names may drop out under
staleness-decay (e.g., tender deal closed, plan amended).

---

## Tier 2 — Coverage gaps that limit scope

These don't break the existing framework but cap the universe we
can scan.

### 2.1 No 8-K covenant numeric parsing (the BBGI gap)

Already documented in `TRANSFORMATION_VS_BASTIAN.md` and Case E
of `CASE_WORKBOOK.md`. Our 8-K full-text scanner catches keywords
("exchange offer", "PIK notes", "springing maturity") but doesn't
parse:
- Debt principal reduced (numeric)
- Equity conversion percentage
- Forced-deadline date
- Asset-sale proceeds target

**What to build.** Add a parser that extracts these numerics
from exchange-offer cover pages. The Bastian equity-torque
formula then becomes computable per ticker, and the entire
RGS/BBGI archetype becomes scoreable. Today these names
literally don't appear in our universe-ranked output.

### 2.2 Foreign jurisdiction layer entirely missing

**The problem.** The playbook explicitly identifies Japan TSE
PBR<1 reform, Korea Value-Up, UK schemes-of-arrangement, and
German Spruchverfahren as multi-year catalyst-rich opportunities.
Our universe is US-only. The PBR<1 universe in Japan alone is
~43% of Japanese listings (a number cited in the playbook from
TSE data).

**What to build.**
- yfinance non-US ticker fetch (`.T` for TSE, `.KS` for KOSPI,
  `.L` for LSE, `.HK` for HKEX, `.AX` for ASX, `.TO`/`.V` for TSX).
- JPX disclosure-list ingestion: TSE publishes a monthly list
  of "compliant with cost-of-capital management" companies — and,
  by implication, a non-compliance list, which is the alpha pool.
- Korea: DART API for treasury-cancellation announcements.
- UK: RNS feed for scheme-of-arrangement notices, PUSU dates,
  Rule 8 disclosures.

**Practical version.** The yfinance non-US fetch alone is probably
1 day's work and would expose ~5,000-10,000 new tickers across
JP/KR/UK/HK/AU/CA with valuation + sector data.

### 2.3 No correlation matrix among convergent names

**The problem.** We recommend 5% concentrated in HFFG, CSGP, RNR.
If these three are highly correlated (e.g., to small-cap-value
or consumer-discretionary factor), they're a *single bet at 15%*,
not three diversified bets at 5%.

**What to build.** 1-year daily-return correlation matrix among
the convergent 12. Anything above 0.6 correlation is one bet,
not two. Factor decomposition (against SPY, IWM, value/growth)
to estimate residual idiosyncratic alpha.

### 2.4 No event timeline / catalyst calendar

**The problem.** We know HFFG needs revenue of $1.232B to vest
PSUs at 100%. We don't track *when*. The dollar hurdle becomes
actionable when we know the deadline (PSU performance period
end date, typically 3 years from grant).

**What to build.** Parse PSU plan grant dates and performance-
period-end dates. Surface a per-name catalyst calendar: when
does each PSU hurdle need to be hit? When does each tender close?
When does each 14D-9 timeline expire? Sortable timeline → action
sequencing.

---

## Tier 3 — Polish and methodology rigor

These don't change conclusions but improve defensibility.

### 3.1 PSU scoring weights are unvalidated constants

`psu_core × 0.4 capped at 25` — why 0.4? Why cap at 25? These
were reasonable guesses early in the framework. They should be:
- Backtested for IC against forward returns (validates the weight)
- Bootstrap-resampled to test sensitivity (validates the cap)
- Compared against ridge/lasso regression coefficients on the
  same factors (validates the linearity assumption)

If a regression says `psu_core` should be 0.6 (not 0.4) the
convergent list might shift.

### 3.2 Coverage-normalisation transform unvalidated

We use `sqrt(7 / n_layers_present)` to normalise sparse rows.
This is a *guess*. The defensible alternative is an empirical
Bayes shrinkage where the prior is the universe-wide median
score on each layer. Names with missing layers get pushed
toward the prior, not artificially upscaled.

### 3.3 No regime-conditional analysis

The framework treats 2026 like any other year. But PSU dollar
hurdles set in 2024 assumed a different macro environment.
Convergent names may underperform if the regime that justified
the hurdle has reversed. Backtest stratified by macro regime
(recession, expansion, inflation, low-rate) would show whether
the framework is regime-robust or regime-dependent.

### 3.4 No factor attribution

The convergent 12 likely has implicit exposure to value (P/B
< 1 dominated), small-cap (microcap floor in selection),
quality (governance score). A Fama-French-Carhart 5-factor
regression on the basket would tell us how much of the apparent
edge is *factor compensation* vs *true idiosyncratic alpha*.

Important because if 70% of the convergent-12 return is value
+ small-cap factor, a cheap value-small-cap ETF captures it
without the diligence.

### 3.5 No liquidity gate by use case

HFFG at $98M mcap is recommended concentrated 5%+. For a $1M
portfolio that's $50K — fine. For a $100M portfolio that's
$5M — likely 5-10 days of average daily volume. The framework
doesn't track ADV.

**What to build.** Add ADV to yfinance overlay; gate sizing
by `position_size_USD / ADV` < 0.5 (rule of thumb: position
should be < half a day's ADV). The convergent 12 may shrink
for large-AUM users.

### 3.6 Excel improvements

Sequential polish:
- Cross-tab hyperlinks (cover ticker → Most Asymmetric row)
- Sortable headers (turn AutoFilter on for data tabs)
- Conditional formatting on numeric columns (red/green for
  P/B, drawdown)
- One-page printable summary view (currently optimised for
  screen reading)
- Embed methodology footnotes per-tab rather than appendix-only

### 3.7 Per-name PSU snippet not exposed

The most informative artifact per name is the *actual PSU plan
text* — e.g., HFFG's "vest at 100%, the Company must have achieved
a revenue of $1.232 billion." We have this in `fwd_snippets` in
proxy_scan but don't expose it in the Excel or diligence sheets.
Should be quoted verbatim.

---

## Quick-win matrix

```
Item                                 Effort      Impact      Priority
------------------------------------------------------------------------
1.1 Backtest validation              2-3 days   foundational  P0
1.2 Sector tagging + neutral rank    1 day      foundational  P0
1.3 Form 4 universe expansion        1-2 days   foundational  P0
1.4 Data-staleness flags             1 day      foundational  P0
2.1 8-K covenant numerics            2 days     coverage      P1
2.2 Foreign yfinance fetch           1 day      coverage      P1
2.3 Correlation matrix               half-day   coverage      P1
2.4 Catalyst calendar                1 day      coverage      P1
3.1-3.5 Methodology rigor            varies     polish        P2
3.6 Excel polish                     half-day   polish        P2
3.7 PSU snippet exposure             half-day   polish        P2
```

---

## Recommended order

If picking three, do **1.1 (backtest) + 1.2 (sector) + 1.3 (Form 4)**.
That trio answers the questions: "does this actually work?" and
"is the convergent twelve a real diversified bet or a hidden
sector concentration?" and "would the convergent list change if
we had complete insider data?"

If picking one, do **1.1 (backtest)**. Without measured alpha
per signal, the framework is a *plausibility argument* — strong,
but not yet quantified evidence. The user asked us to ensure the
selections are the *best across the universe*; the most honest
next step is to measure whether the existing selections actually
outperform.

---

*Companion to MOST_ASYMMETRIC.xlsx + the entire framework. This
memo is intentionally candid; a polished version omits the cost
estimates and Tier 3 minutiae.*
