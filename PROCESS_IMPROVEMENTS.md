# Process improvements — synthesized from meta-research

Sources surveyed (returned agents): academic alpha literature (Cohen-Malloy-Pomorski,
Bonaime, Eberhart-Altman, Coval-Stafford, Brav-Jiang, etc.); fund letters (Kingdom,
Voss, Arquitos, Alluvial, Tauraitis, Donerail, Coliseum); books (Marathon, Thorndike,
Whitman, Klarman, Carlisle, Mauboussin, Cornell); special-sits blogs (Walker, Howe,
MDC/Clark Street, Tobik, DeMuth, Net Net Hunter, Compounding Quality); historical
cases (Allstate, Host Marriott, Liberty Broadband, VLTO, NLOP, CURB, GE three-way,
Kellogg split, PayPal, Match, WBD).

The roadmap below is brutally pruned — only items that **(a)** would meaningfully
change top-of-universe ranking, **(b)** are systematizable from public EDGAR/FINRA
data, and **(c)** are not already covered by an existing leg. Repeating ideas
(Bastian liquidation arb, generic ROIC gates, qualitative scuttlebutt) are rejected.

---

## Tier 1 — Build immediately (highest alpha / lowest effort)

### 1. Odd-lot tender priority parser
- **Source convergence:** Tauraitis (17/17 historical), Walker (YAVB), Comment-Jarrell.
- **What:** regex SC TO body for "fewer than 100 shares" + "not subject to proration."
- **Why:** near-deterministic retail edge, multiple sources confirm 100% historical
  hit rate at small per-account size.
- **Effort:** half-day extension of `tender_scan.py`. Add `has_odd_lot_priority`
  boolean field per tender.

### 2. Cohen-Malloy-Pomorski opportunistic-vs-routine insider classifier
- **Alpha:** ~10%/yr abnormal for opportunistic-only portfolio vs ~5% blended
  (Cohen-Malloy-Pomorski JF 2012, NBER w16454).
- **What:** for every Form 4 filer, label as "routine" if they trade same calendar
  month each year for 3 years; opportunistic otherwise.
- **Effort:** 1-2 days on existing `form4_buys.json`. The cluster signal should only
  count *opportunistic* buyers.

### 3. Bonaime-Ryngaert insider-direction overlay on buyback layer
- **Alpha:** verified buyback + net insider BUY = abnormal returns persist 3 years;
  + insider SELL = abnormal returns die within 1 year (JCF 22, SSRN 1361738).
- **What:** quarter-level join of `buyback_verify` × Form 4 net direction. Score
  the AND, zero out the disagreements.
- **Effort:** trivial. Add as a multiplicative filter.

### 4. Tender-mechanism classifier (Comment-Jarrell weights)
- **Alpha:** fixed-price self-tender +11% CAR; Dutch +8%; open-market +2%
  (JF 46(4) 1991).
- **What:** parse Section 2 of SC TO-I for pricing structure; weight legs
  fixed-price 1.5× Dutch, 5× open-market.
- **Effort:** <1 day; existing tender scan already pulls SC TO-I.

---

## Tier 2 — Next sprint (moderate effort, strong signal)

### 5. Voss-style CIC-amendment triangulation
- **Source:** Voss Capital Q4 2025 (CHH case: 26% short interest + 40% insider +
  CIC amendment).
- **What:** DEF 14A "Potential Payments upon Termination/Change in Control" table
  parsed cross-year; flag delta > $X; intersect with insider % > 30% and FINRA
  short interest > 20%.
- **Effort:** 2-3 days; needs cross-year DEF 14A diff + FINRA short-interest feed.
- **Why high-priority:** direct M&A predictor, not just risk flag.

### 6. Spinoff calendar + Rich Howe 40% volume rule
- **Source:** Howe at stockspinoffinvesting.com.
- **What:** Form 10 → extract distribution ratio + shares outstanding; 8-K Item
  8.01 → distribution date + when-issued ticker; running cumulative-volume timer
  on the child ticker for 10 sessions post regular-way open; entry signal at
  40-50% of float traded.
- **Effort:** 2-3 days. Pairs cleanly with our existing Form 10 leg; no new feeds.

### 7. Eberhart-Altman post-Ch11 fresh-start equity leg
- **Alpha:** +24.6% to +138.8% CAR over 200 days (JF 54(5) 1999, n=131).
- **What:** 8-K Item 1.03 emergence filter + new CUSIP detection. Separate from
  NOL shell leg (different phenomenon).
- **Effort:** 1-2 days. Hertz 2021, Six Flags, JCPenney all qualifying patterns.

### 8. External-manager internalization screener
- **Source:** Clark Street Value (Braemar/Ashford ~$480M termination fee unlocked
  15-30% NAV).
- **What:** scan DEF 14A for "external advisor" + "termination fee" schedule in
  10-K Exhibit 10 + recent board composition change in 8-K Item 5.02; cross with
  REIT/BDC discount-to-NAV > 20%.
- **Effort:** 2 days. Mostly EDGAR text parsing on already-fetched filings.

### 9. Bumpitrage tender-decline signal (Walker)
- **What:** flag open tender offers where sequential extensions show declining
  acceptance percentage; combined with post-announcement peer-index drift >
  announcement premium AND known activist holder > 10%.
- **Effort:** 2 days; extends `tender_scan.py` with amendment-series parsing.

---

## Tier 3 — Next quarter (need new data sources or heavier plumbing)

### 10. Coval-Stafford fire-sale flow-pressure leg
- **Alpha:** -7.9% during fire-sale quarter, +5% reversion over next 18 months
  (JFE 86(2) 2007).
- **What:** 13F + N-PORT mutual fund outflow z-score per ticker; long bottom-
  decile pressure.
- **Effort:** significant. Need 13F parser (we don't have) + N-PORT flow extraction.
  ~5-7 days. Likely highest marginal alpha vs effort in this tier.

### 11. Arquitos subsidiary-stake anchor parser
- **Source:** Arquitos Q1 2025 (ENDI / CrossingBridge $26M for 25% implied sub
  value > parent mcap).
- **What:** 8-K Item 1.01/2.01 disclosing minority equity sale; calculate implied
  subsidiary valuation; flag when > 0.8× parent mcap.
- **Effort:** 2-3 days. Tiny universe of hits per year but large per-hit returns.

### 12. Sub-13D activist public-letter feed
- **Source:** Donerail (PENN +20% intraday).
- **What:** PR Newswire / BusinessWire scrape filtered to curated activist list
  (Donerail, Engaged, Land & Buildings, Ancora, Politan, Trian, JANA, Mantle
  Ridge, Coliseum, Engine). Trigger on letters citing SOTP > 1.5× current.
- **Effort:** 3+ days. Captures the *pre-13D* version of activist pressure that
  our current 13D sweep misses.

### 13. FDIC Call Report mining for Form 15 dark banks
- **Source:** Tobik / Oddball Stocks (CompleteBankData).
- **What:** when a community bank holdco files Form 15 (deregisters), keep
  valuing it from the lead bank subsidiary's quarterly FFIEC Call Report
  (Schedules RC, RC-K, RC-N, RC-O, RI). FDIC Cert # bridges holdco → subsidiary.
- **Effort:** 2 days. FFIEC API is public.

### 14. Backstopped rights-offering arbitrage parser
- **Source:** Clark Street Value (Seaport, GCI Liberty: $27.20 sub price vs $36.09
  trading).
- **What:** Form 10 / S-1 oversubscription clause + backstop-agreement 8-K
  exhibit; flag where (subscription price + pro-rata oversubscribe) < market.
- **Effort:** 1-2 days.

### 15. Plan-of-liquidation + debt-maturity forcing date
- **Source:** Clark Street Value (FSP debt-matures 4/1/26).
- **What:** 8-K Item 1.01/2.03 + proxy "plan of liquidation" keyword + 10-Q
  debt-maturity table extraction; rank by months-to-maturity.
- **Effort:** 1 day. Ties the existing 8-K restructuring keyword scan to a dated
  forcing event.

---

## Tier 4 — Top-down overlays (no per-ticker action; affects weighting)

### 16. Marathon capital-cycle industry scorecard
- **What:** per-SIC scorecard: aggregate capex/D&A ratio, capacity growth vs
  demand growth, IPO + secondary $ issuance volume, HHI concentration delta.
  Long-tilt sectors with capex/D&A < 0.8 AND rising HHI; tag-out > 1.5.
- **Effort:** 2-3 days; needs aggregated industry financials (Compustat or
  yfinance sector aggregation).

### 17. Whitman "Safe & Cheap" four-pillar conjunction gate
- **What:** hard AND: net-debt/tangible-equity < 0.5 AND current ratio > 2.0
  AND P/TBV < 0.67 AND positive 3y FCF.
- **Effort:** 1 day; all fields already in extended yfinance overlay.

### 18. Net Net Hunter Core-7 NCAV scorecard
- **What:** price/NCAV < 0.66 AND current ratio > 1.5 AND burn rate > -15% AND
  Piotroski F-score ≥ 5 AND insider ownership > 0 AND non-China.
- **Effort:** 2 days; needs Piotroski F-score build + NCAV calculation. Lower
  marginal alpha than special-sits-specific legs but cleanly orthogonal.

---

## Calibrations to existing legs (no new build, just reweighting)

| Existing leg | Calibration |
|---|---|
| Buyback verification | Weight verified ≥ 3× announced (was 1.5×); penalize tickers with <60% trailing 3y completion (Bonaime SSRN 1361800) |
| Spinoff (Form 10 / 10-12B) | Add sub-signals: parent SIC vs SpinCo SIC delta ≥ 2 digits (Krishnaswami); index-exclusion flag; dividend-policy divergence vs parent; insider P-buys in 90d post-spin (Cornell) |
| EV/EBIT screen (when added) | Run TWO sleeves — Magic Formula (cheap × quality) AND pure-cheap (no quality screen) — Carlisle finds the pure-cheap tail benefits from ROIC mean reversion |
| Recent-incentive-change | Add red-flag count from Larcker-Lynch-Tayan: <60d cooling-off, single-trade plans, pre-earnings trades — weight termination signals by red-flag count of the cancelled plan |
| Activist 13D | Tag by filer track record (recent campaigns won/lost, abnormal-return median per Brav-Jiang); weight known-repeat activists 2× first-time filers |

---

## Cross-verification techniques

1. **Bonaime-Ryngaert direction check** — every verified buyback signal must be
   cross-checked against insider direction same quarter. Disagreement kills the score.
2. **Cohen-Malloy routine check** — every insider cluster signal must filter to
   opportunistic-only buyers before scoring.
3. **Comment-Jarrell mechanism check** — every tender must be classified by
   pricing structure; open-market tenders weighted ~20% of fixed-price.
4. **Parent vs SpinCo SIC divergence** — every Form 10 hit must check parent
   SIC ≠ SpinCo SIC at the 2-digit level; same-industry spinoffs underperform
   (Veld-Veld-Merkoulova meta-analysis).
5. **Norbert Lou BRK-spread** — every concentrated candidate must clear the
   "would I rather just buy more Berkshire?" hurdle (expected IRR − 10%).

---

## Process improvements (workflow / cadence)

- **Mauboussin base-rate tagging.** Every position in the workbook gets a
  reference-class hit rate stamp (e.g., "spinoff sub, parent SIC ≠ SpinCo SIC,
  no recent buyback, no live activist" → check base-rate panel for this
  combination). Forces explicit prior probability vs implied probability in price.
- **Watchlist-age field.** Years observed before action (Lou watched TGS-Nopec
  for 7 years). Add per-ticker `watchlist_entry_date` so the framework can ask
  "how long have we been waiting on this?"
- **Hard position cap + cash reserve.** Lou: ≤6 concentrated + up to 25% cash.
  We don't currently enforce a count cap.
- **Daily calendar.** Calendar each: open tender expirations, when-issued spinoff
  start dates, distribution dates, Russell rebalance, SC TO amendments. Build a
  forward-looking `event_calendar.csv` with `T-days` countdown.

---

## Case studies to add to CASE_WORKBOOK.md

Now-verified cases ready for the workbook (each cleanly maps to an existing or
proposed leg):

1. **Allstate / Sears (1995)** — non-promoted parent stub + 1995/96 +73%/+41%
   (vs SPY +37%/+23%) [Tier 1, Spin-Off]
2. **Host Marriott (1993)** — Bollenbach career-skin-in-game; ~3× in 4 months
   [Bollenbach turnaround leg, already built]
3. **Liberty Broadband (2014)** — Malone ~48% voting power + Charter look-through
   [Voss CIC triangulation analogue]
4. **VLTO (Danaher 2023)** — Danaher Business System playbook +35% to ATH
   [Spinoff + clean carve-out template]
5. **NLOP (WPC 2023)** — managed-liquidation deep-value; +31.66% / 52w vs SPY
   +11%; serial specials
   [Tier 3 #15 — plan-of-liquidation leg]
6. **CURB (SITC 2024)** — parent funded SpinCo with $800M cash + zero debt;
   CURB +41.93% TSR vs SPY +17.7% — strongest relative
   [Spinoff template: "pre-funded clean SpinCo"]
7. **GE three-way (2023/24)** — GEHC underperformed, GEV +143-165% trailing, GE
   Aerospace RemainCo outperformed; Culp's $230M PSU package the structural tell
   [Bollenbach + Tier 2 #6]
8. **Kellogg split (2023)** — both halves M&A within 24m (Kellanova → Mars at
   $83.50/+44%; KLG → Ferrero at $23.00/+40%)
   [Spinoff sub-signal: small-stub-undercovered pattern]
9. **PayPal / eBay (2015)** — Icahn-forced spin; ~flat 1y
   [Activist-forced spinoff, Tier 3 #12]
10. **Match / IAC (2020)** — staged separation; MTCH ATH $169.43 vs spin
    [Tracker-to-spin pattern]
11. **WBD (2022)** — cautionary: index orphan + dividend cut + structural
    decline; -40% one-year
    [Cautionary case for spinoff thesis — failure mode where indiscriminate
     selling doesn't reverse]

---

## Rejected as noise

- **Compounding Quality six-metric quality gate** — different lens (quality
  compounders, not special sits)
- **Fisher scuttlebutt proxies (Glassdoor / NPS scrapes)** — low signal-to-noise
  for systematic framework
- **Hedgehogging behavioral cycles** — too coarse to act on
- **13F low-AUM emerging-manager overlap** — data-heavy, low marginal alpha
- **Generic Kingdom/Alluvial REIT liquidation arb** — already covered by
  existing restructuring + buyback verification stack
- **When-issued spinoff overvaluation short** (Howe) — interesting but WI quote
  data is the bottleneck and reward is modest

---

## What to ship first

Single-week sprint (highest ROI):
1. Odd-lot tender parser  (T1.1)
2. Cohen-Malloy opportunistic classifier  (T1.2)
3. Buyback × insider direction join  (T1.3)
4. Tender mechanism weights  (T1.4)
5. Bonaime completion weighting calibration

These are all small but compound — they materially sharpen four existing legs
(tender, insider cluster, buyback) without new data sources. Expected effect:
fewer false positives in the convergent list; opportunistic insider buyers move
up; verified-buyback-only-but-insiders-selling names drop down.

Two-week follow-up: Voss CIC triangulation + Howe 40% spinoff timer + Whitman
four-pillar gate. These three add three orthogonal positive signals.

Next quarter: Coval-Stafford fire-sale (highest single-leg alpha; significant
plumbing) + post-Ch11 emergence + external-manager internalization.
