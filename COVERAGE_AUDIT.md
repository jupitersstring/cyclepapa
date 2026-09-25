# Sourcing & Coverage Audit — where the framework is blind, and the ranked fixes

Date: 2026-08-20. Every number below measured against the live outputs
(38-layer consensus over 6,166 names, proxy-v2 majority) or probed
directly against the source APIs. Companion to INCENTIVE_AUDIT.md
(extraction quality); this audit is about *what we never see at all*.

---

## A. The quantified coverage picture

Fire-rates are healthy at the top (psu 2,886, recent_incentive 2,791,
valuation 1,588) and thin exactly where sourcing — not signal rarity —
is the binding constraint:

| Layer | Fires | Binding constraint (verified) |
|---|---|---|
| quarterly_10q / net_net | 121 / 208 | 10-Q parser ran with `--limit 200`; 164 balance sheets for 6,166 names (2.7%) |
| f4 / discretionary / opportunistic | 131 / 139 / 303 | form4_buys covers 346 tickers from a ~30-day sweep; the 45-day cluster window is WIDER than the data window |
| form_13f_delta | 16 (12 neg) | 45 tickers, 12 filers, value-parse artifacts zeroed → effectively 4 credible records |
| asymmetry_assembly | 5 | XBRL enrichment ran on a 28-name shortlist; C2 leg starves on 10-Q coverage |
| premium_injection | 1 | real rarity + EFTS truncation (below) |
| spinoff_volume / arquitos | 0 | data files EMPTY — Yahoo rate-limit casualties never re-run; two dead layers |
| valuation | 1,588 | yfinance covers 2,807/6,166 (46%); every mcap/P-B gate downstream inherits the hole |
| uk_rns_events | 2 | single shallow poll of a 45-item server-rendered listing |

f144 (288, correctly all-negative), tender (75), sohn (17) are fine —
signal-sparse by design, not sourcing-starved.

## B. Confirmed sourcing defects

**B1 (HIGH) — Silent EFTS truncation in every 8-K scanner.** All five
EFTS engines (distressed-stub, selective-buyback, hidden-asset,
premium-injection, inducement) read only the FIRST page and cap at
40–60 hits per phrase with `from=0`. Measured against live totals:

    "restructuring support agreement"   total=90     cap=60   truncated
    "gain on extinguishment of debt"    total=253    cap=60   truncated
    "accelerated share repurchase"      total=284    cap=40   truncated
    "securities purchase agreement"     total=2,954  cap=50   truncated 98%

This violates the framework's own "no silent caps" rule. EFTS paginates
(`from=` offset, 100/page, hard cap 10k) — pagination is a small loop.
The premium-injection scanner is the worst hit: 98% of candidate
issuance filings are never examined, so "1 premium injection found"
badly understates the real rate.

**B2 (HIGH) — Verification is top-N only.** Counter-signals
(distressed: priming/wipeout/toxic-dilution), block-from-holder and
discount/premium (selective-buyback), and premium extraction all fetch
filing text only for the top 25–30 by phrase score. Everything below is
scored on headline phrases with NO waterfall check — precisely the names
where a phrase match without verification is most misleading.

**B3 (HIGH) — Two dead layers.** `spinoff_volume_timer.json` and
`arquitos_subsidiary_anchor.json` are empty (the Yahoo-rate-limit
casualties from the earlier session were code-fixed but never re-run).
Two of 38 layers contribute literally nothing; the workbook's coverage
tab reports them as layers regardless.

**B4 (MED) — Form 4 window vs cluster window mismatch.** The sweep
holds ~30 days of filings, but the conviction leg's Lakonishok-Lee
window is 45 days: clusters that straddle the data boundary are
systematically under-counted, and the layer sees only 346 tickers.
A rolling sweep (append, don't replace; prune >120d) fixes both.

**B5 (MED) — 13F delta effectively dead.** 12 filers, name-matching
mis-attribution (the GPGI $86B class), 27/45 records zeroed. The layer
needs a rebuild on structured 13F data (EDGAR provides XML info tables;
CUSIP→ticker via the openfigi-style map or the SEC company_tickers
file) before its count-based signals are trustworthy.

**B6 (MED) — yfinance as a single point of failure.** Price/mcap/P-B
gates appear in valuation, coval, distressed-stub distress gate,
hidden-asset small-cap weighting, and assembly C1/C3 — all inherit the
46% coverage hole and the curl_cffi/proxy fragility that has already
bitten twice.

**B7 (LOW) — UK monitor depth.** 5 announcements/page server-rendered;
one poll ≈ one afternoon of RNS. Without a Companies House key or
scheduled accumulation it stays a demo-depth feed.

## C. The big unlock: SEC XBRL *frames* API (probed, works)

One call returns one concept for EVERY filer in a quarter:

    GrossProfit             CY2026Q1  → 1,830 companies / call
    Revenues                CY2026Q1  → 1,692
    StockholdersEquity      CY2026Q1I → 5,209
    LongTermDebtNoncurrent  CY2026Q1I → 1,496

~60–100 calls (a dozen concepts × 8 quarters, incl. tag fallbacks)
build a **universe-wide quarterly fundamentals store** — no per-ticker
fetching, no Yahoo dependence, no rate-limit drama. That single store:

1. lifts balance-sheet coverage 164 → ~5,000+ (C2 leveraged-survivor,
   NCAV, current-ratio distress gates);
2. runs the C6/C7 operating-inflection + deleveraging engines over the
   FULL universe instead of a 28-name shortlist — the asymmetry
   assembly stops being shortlist-bound (5 assemblies today is a
   sourcing artifact, not the real base rate);
3. supplies equity for P/B and debt for EV wherever yfinance is blind;
4. gives the PSIX-recipe backtests a point-in-time store for free
   (frames are as-filed history).

This is the highest-leverage sourcing change available and it is all
one publisher (SEC), one JSON shape, EDGAR-polite.

## D. Ranked implementation plan

1. **xbrl_frames_store.py** (C): pull ~12 concepts × trailing 8
   quarters into `xbrl_frames/{concept}_{period}.json` + a per-ticker
   pivot; rewire quarterly/net-net/C2/C6/C7/assembly loaders to prefer
   it. Biggest coverage multiple per unit of work.
2. **EFTS pagination helper** (B1): shared `efts_all(phrase, forms,
   window)` that walks `from=` pages to the true total (bounded, e.g.
   1,000/phrase) and logs dropped counts loudly; adopt in all five
   scanners.
3. **Re-run the two dead layers** (B3): spinoff + arquitos on the
   frames/quote fallback path; if still quote-blocked, mark them
   excluded from the layer count rather than silently zero.
4. **Rolling Form 4 store** (B4): append-mode sweep with 120-day
   retention so the cluster window is fully inside the data window;
   coverage grows ~4x per quarter of operation.
5. **Verification budget by materiality** (B2): verify top-N *plus*
   every name that passes the distress/assembly gates (they are the
   consumers who care); log the unverified remainder count.
6. **13F rebuild** (B5): structured info-table XML + CUSIP map,
   plausibility gates at parse time; then raise filer count 12 → 40.
7. **UK accumulation** (B7): keep appending poll results (the monitor
   already dedupes by announcement id); a Companies House key remains
   the step-change when available.

Items 1–2 change the shape of the framework's vision; 3–7 are repairs
and compounding improvements. Nothing above alters any scoring weight —
additive discipline untouched; these widen what the existing layers see.

---

## Addendum (2026-08-20) — findings while wiring the frames store

- **Frames store shipped** (5,139 names) and wired into the assembly:
  full assemblies 5 -> 14, C2 leverage 164-capped -> 2,394, C6 inflection
  28 -> 490, C7 383. The "5 assemblies" was confirmed a sourcing
  artifact.
- **Negative book equity (923 names) was an unused signal AND a latent
  bug.** The assembly's C2 leverage path required `equity > 0`, so it
  silently skipped the ~900 MOST-levered names. Negative equity is the
  maximal-torque residual-stub condition; it now fires C2, and
  negative-equity-plus-positive-operating-income (122 names: HLF, OTIS,
  LIND, ARRY, WK ...) is tagged as the PSIX residual-stub pattern the
  whole thesis targets.
- **P/B backfill from frames is a non-opportunity** (measured): only 8
  names have yfinance mcap without a p_b, because yfinance p_b coverage
  already tracks its mcap coverage. The frames store's value is
  fundamentals breadth (equity/debt/revenue/GP), not price ratios --
  the price half of the yfinance dependence still needs a daily-price
  mirror (Stooq).
- **XBRL unit sanity checked**: no absurd equity values (>$5T) in the
  store; the frames API's structured USD units avoid the scale-error
  class that plagued the regex dollar extraction.
