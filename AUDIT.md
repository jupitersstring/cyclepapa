# cyclepapa Pipeline Audit — Findings & Recommendations

*Date: 2026-06-25 · Auditor: review of pipeline + DB state*

---

## EXECUTIVE SUMMARY

The pipeline has **strong coverage breadth** (5,862 tickers ranked, 424/445 funds covered, 71,706 13F positions) and a **clean data-driven scoring formula** (`unified_score`). But there are **six high-impact gaps** that systematically bias rankings and silently drop signal. The biggest are: **(1)** 13D/G stale by 18 months, **(2)** 13F dollar values misread by ×1000 for ~30% of filers, **(3)** no dollar-weighted scoring (count-only), **(4)** position concentration `pct_book` ignored, **(5)** fund style not used to weight signal, and **(6)** no event-driven filings (8-K, DEF 14A, Form 144, S-1, NPORT).

---

## 1. EDGAR ENDPOINTS — USED VS AVAILABLE

### Endpoints we hit
| Endpoint | Purpose | Files using |
|----------|---------|-------------|
| `data.sec.gov/submissions/CIK*.json` | Filer's recent forms | ingest_13f, ingest_13d, scan_insider_batch, enrich_sectors |
| `data.sec.gov/api/xbrl/companyconcept/*.json` | Shares-out / fundamentals | enrich_tickers, enrich_fundamentals |
| `www.sec.gov/files/company_tickers*.json` | ticker→CIK map | many |
| `www.sec.gov/Archives/edgar/data/*/` | Filing index pages | ingest_13f, ingest_13d, ingest_edgar |
| `efts.sec.gov/LATEST/search-index` | Full-text search by name/form | full_universe_resolve, fill_gaps |
| `www.sec.gov/Archives/edgar/daily-index/*/form.*.idx` | Daily form index | discover |
| `www.sec.gov/cgi-bin/browse-edgar` | Browse-edgar HTML scrape | resolve_fund_ciks, ingest_13d |

### Endpoints / data we **DO NOT** use
| Source | Signal | Value |
|---|---|---|
| **8-K filings** | Material events: M&A, CEO change, dividend, restructuring | HIGH — leading catalyst |
| **DEF 14A / DEFA14A (proxy)** | Proxy contest, M&A vote, board changes | HIGH — activist trigger |
| **Form 144** | Planned sales (insider counter-signal) | MEDIUM |
| **Form 13H (large traders)** | Block-trader identity | LOW |
| **NPORT-P (mutual fund holdings)** | Monthly mutual-fund holdings | HIGH — finer-grained smart-money |
| **N-CSR (mutual fund annual)** | Manager commentary | MEDIUM |
| **S-1 / S-3 / 424B** | New issuance, dilution | HIGH — dilution counter-signal |
| **Form D (private placement)** | Capital raise pre-IPO | MEDIUM |
| **13F-NT** | "Reported by other" — find the umbrella filer | MEDIUM — closes ValueAct/Cascade gap |
| **10-K / 10-Q narrative** | Risk factors, business segments | MEDIUM (vs XBRL we already use) |
| **6-K (foreign filers)** | Foreign issuer disclosures | MEDIUM |
| **Form 13F-HR/A** | 13F amendments (corrections) | LOW — but ignored entirely |
| **EDGAR full-text search** | Free-text query across all filings | HIGH — Mantle Ridge, restructuring keywords |
| **Press release on 8-K Ex-99** | Specific event detail | HIGH |

---

## 2. DATA FRESHNESS

| Source | Latest data | Status |
|---|---|---|
| 13F-HR holdings | May 2026 (Q1 2026) for 242 funds | ✅ Current |
| Form 4 P-code buys | June 2026 (72 buys) | ✅ Current |
| Prices | 2026-06-18 | ✅ Current |
| ticker_meta enrichment | 2026-06-20 | ✅ Current |
| **SC 13D/G filings** | **Dec 2024** | ❌ **18 months stale** |

### 13D/G staleness root cause
The submissions API `recent[0:80]` window for high-volume filers (Starboard, Elliott, Icahn) is dominated by Form 4 / 144 entries, pushing SC 13D/G filings off the end. Starboard alone has filed **9+ SC 13D/A in 2026** that we're missing.

**Fix**: paginate via `j.filings.files[]` to get older filings, OR use `efts.sec.gov/LATEST/search-index?ciks=...&forms=SC+13D,SC+13D/A,SC+13G,SC+13G/A&dateRange=custom`.

---

## 3. SCORING FORMULA — STRUCTURAL GAPS

### Current `unified_score`
```
score = log(n_funds_13F) × 2
      + 3.0 × n_funds_section3        ← new MAJOR
      + 1.5 × n_funds_section4        ← material adds
      + 2.0 × n_funds_section1        ← top picks
      + 0.5 × activist_max_pct
      + cluster_step(n_insiders)
      + log(form4_dollars + 1) × 2
      + micro_bonus
      + 0.5 × expected_return_pct
```

### What's missing
| Gap | Impact | Example |
|---|---|---|
| **No dollar weighting** | Count-only treats $10M Bonhoeffer position = $5B Citadel position | A name held by Citadel $1B + Bridgewater $800M scores same as Bonhoeffer $20M + Greenwood $25M |
| **`pct_book` ignored** | Highest-conviction positions (10%+ of book) not flagged | Mantle Ridge 100% pct_book → no extra score |
| **No fund-style weighting** | Multi-strat noise = activist signal | Bridgewater holding GME ≠ Engaged Capital holding GME |
| **No 13D vs 13G distinction** | Activist 13D much stronger than passive 13G | Both count as `activist_filings += 1` |
| **No 13D amendment trajectory** | 5%→10% buildup = strong signal | Lost vs simple count |
| **No insider sales (S-code)** | Heavy CEO sells = counter-signal not captured | 29 S-code rows in DB, all ignored |
| **No 10b5-1 plan filter** | Pre-scheduled sales misclassified as discretionary | Form 4 footnotes ignored |
| **No catalyst date** | Pre-earnings cluster ≠ random cluster | All time-decay equal |

---

## 4. DATA QUALITY BUGS

### 4.1 13F value unit ambiguity (CRITICAL)
**Bug**: Citadel showing $618T, Berkshire $263T, Millennium $240T in `total_value_k`. Pre-2023 13F-HR reports `value` in $1000s (thousands); post-2023 sometimes raw dollars. Our parser stores everything as `value_k` (thousands).

**Effect**: 30%+ of fund totals are 1000× too large. Dollar-weighted aggregates (e.g. consensus by $) are unusable.

**Fix**: Detect filer's reporting convention from `<reportType>` or post-process by checking summaryPage's `tableValueTotal` against sum-of-values, then normalize.

### 4.2 holder_13d parse gaps
- **39%** of filings have no parsed `subject_ticker` (regex fragility in SUBJECT COMPANY block)
- **16%** have no parsed `pct_class` (% statement regex doesn't catch all phrasings)

**Fix**: Parse the actual 13D XML where available (recent filings have structured data), not just the text header. Use the cover-page schema.

### 4.3 Ticker mapping failures by fund
| Fund | Unmapped % |
|---|---|
| Land & Buildings | 90% |
| Veradace Partners | 89% |
| Funicular Funds | 77% |
| Magnetar Capital | 74% |
| Northern Right Capital | 72% |
| FPA Crescent / First Pacific | 65% |

**Fix**: Magnetar holds many foreign ADRs + preferreds where our SEC `company_tickers_exchange` lookup fails. Add CUSIP-based fallback via `fund_13f_holdings.cusip` → CUSIP master.

### 4.4 No event-driven signal at all
`edgar_filings` table holds **only Form 4** (768 rows). 8-K, S-1, DEF 14A, NPORT not pulled, so:
- M&A announcements not in score
- Proxy contests not surfaced beyond 13D Item 4 parse
- Dilution events (S-1) silently missed
- Mutual-fund monthly NPORT data (better than quarterly 13F) untapped

---

## 5. RECOMMENDATIONS — PRIORITIZED

### TIER 1 — Quick wins (≤1 hour each)

**R1: Fix 13D/G staleness** *(highest impact)*
- Use efts.sec.gov full-text search per holder CIK for 2025-2026 SC 13D/G
- Paginate `submissions.json.filings.files[]` for older entries
- Expected: 500+ new activist filings, current to last week

**R2: Add `pct_book` to scoring**
- High-conviction signal already in DB; just unused
- New formula term: `+ 4 × log(1 + max_fund_pct_book)`
- Surfaces names where any fund put >10% of book

**R3: Add dollar-weighted smart money**
- `dollar_value = sum(fund_13f_holdings.value_k)` per ticker
- New term: `+ log(1 + dollar_value_m) × 1.5`
- Distinguishes Citadel $1B position from Bonhoeffer $20M

**R4: Normalize 13F value units**
- Cross-check `total_value_k` against `summaryPage.tableValueTotal` from primary_doc.xml
- If ratio is ~1000 → values were raw $; normalize to thousands
- Fixes Citadel/Berkshire/Millennium/etc. dollar figures

### TIER 2 — Medium effort (half day each)

**R5: Ingest 8-K filings for universe tickers**
- `data.sec.gov/submissions/CIK*.json` already gives form list
- Parse Items 1.01 (M&A), 2.01 (acquisition), 5.02 (director change), 8.01 (other events)
- Adds the catalyst layer

**R6: NPORT-P mutual fund holdings**
- Pulls Wellington, Capital Group, T Rowe Price, Vanguard active monthly
- Adds a finer-grained smart-money tier
- Endpoint: `data.sec.gov/api/xbrl/companyfacts/` for NPORT XBRL

**R7: Form 4 sells layer**
- We have 29 S-code rows already
- Add S-code aggregation per ticker as counter-signal
- Filter out 10b5-1 plans (footnote)

**R8: Fund-style weighting**
- `fund_style` table maps fund → macro_style
- Weight signals: activist=1.5×, value=1.3×, multi-strat=0.7×
- Reduces Citadel/Bridgewater noise dominance

### TIER 3 — Heavy lift (1-2 days)

**R9: Proxy contest signals (DEF 14A / DEFA14A)**
- Parse for ISS recommendations, vote outcomes
- Detect contested elections (signal: dissident slate)

**R10: CUSIP master for ticker fallback**
- Resolves the 60-90% unmapped issue for foreign-heavy funds
- SEC's `company_tickers_exchange` doesn't have CUSIP; need a CUSIP→ticker source

**R11: Event-driven catalyst layer**
- 8-K + Press release Ex-99 text classification
- Link to earnings dates, FDA dates, court dates
- Time-decay weighting of signals (recent > old)

---

## 6. MISSING PIPELINE ELEMENTS — STRUCTURAL

- **No historical 13F snapshots** — we have only "latest". Can't compute Δposition vs prior quarter, which is the cleanest "new initiation" / "material add" detector.
- **No earnings date integration** — can't time-cluster signals around catalysts
- **No short-interest data** — short squeeze setups invisible
- **No options flow** — high P/C ratio names invisible
- **No fund AUM** — score doesn't differentiate $300M fund vs $50B fund's signals
- **No backtest of `unified_score`** — formula is intuitive but unvalidated against forward returns

---

## SCOREBOARD

| Layer | Status | Confidence in current ranking |
|---|---|---|
| 13F holdings ingest | ✅ Current | HIGH (with value-unit caveat) |
| 13F→ticker mapping | ⚠️ 60-90% gaps for some funds | MEDIUM |
| 13D/G activist | ❌ 18 mo stale | LOW |
| Form 4 insider buys | ✅ Current | HIGH |
| Insider clusters | ✅ 6 live, current | HIGH |
| Mcap enrichment | ✅ 76% resolved | HIGH |
| Sector (SIC) | ✅ 86% resolved | HIGH |
| Score formula | ⚠️ Missing key terms | MEDIUM |
| Fund coverage | ✅ 95.3% | HIGH |

**Overall**: The ranking is directionally correct but **systematically biased** toward:
- Tickers with many small-fund holders (count-weight only)
- Equal weighting of activist vs passive 13G  
- Stale activist data (cuts off Dec 2024)
- Inflated dollar figures for top funds

Top picks (HHH, WGS, KBR, ALKT, NSP) are still robust because they rely on count + insider signals, but the **right ordering** of names within a bucket would change materially with R1+R2+R3+R4.

---

*End of audit.*
