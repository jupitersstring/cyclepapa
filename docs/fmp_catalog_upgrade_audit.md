# FMP catalogue upgrade audit: every endpoint vs every `arch_*`

Date: 2026-09-26. This builds on the first audit (`scratchpad/archetype_upgrade_audit.md`, cited below as **A1 §x**) and does
not repeat it. Inputs: the 1,242-variable, 232-endpoint FMP catalogue; `archetype_tags.py` (167 `arch_*`); the engines and
overlays in the repo. No repo files were edited.

**Probing.** I made about 60 FMP calls in total. That was single-symbol probes plus one stream each of `eod-bulk`,
`profile-bulk`, `peers-bulk`, `income-statement-bulk`, `price-target-summary-bulk` and `earnings-surprises-bulk`. Scripts are
`scratchpad/probe2..5.py`. The measurement joins are in `scratchpad/m2.py`, run on the current CSVs.

**Denominator.** INV is investable operating names: non-financial, non-REIT, non-utility, `market_cap_usd >= $10M`. That is
24,704 names. "Firers" means INV rows with `arch_*==1`.

**Deliverables.**
- This report.
- `scratchpad/archetype_endpoint_matrix.csv`: 167 rows, one per archetype (section E).

---

## 0. Headline findings and top recommendations

### 0.1 State of play (what changed since A1)

- **Four new data layers exist but are not wired into tagging (P0, zero calls).** The layers are `ts_snapshot.csv` (`ts_*`,
  33k symbols), `fmp_throughcycle.csv` (`tc_*`, 38k), `fmp_quarterly_ext.csv` (`fqx_*`, 32k) and `fmp_events.csv` (`ev_*`).
  `archetype_tags.py` merges `base_snapshot`, `fmp_sentiment`, `fmp_institutional` and `fmp_quarterly` (lines 236–264). It
  references **zero** `ts_`, `tc_` or `fqx_` columns and no event `ev_*` columns. Every A1 recommendation that reads
  `ts_r52`, `tc_min_opm` and the like is therefore still unimplemented. The fix is four `_merge_fmp_overlay` lines after
  line 264, then the rule swaps in section E.
- **`fmp_events.csv` is a 2,000-row partial run.** `ev_beats_8q` covers 1,432 INV names. Only 367 of the 2,445
  `asleep_at_wheel` firers have it.
- **Naming hazard.** The event layer's `ev_` prefix collides with the valuation family already in the code (`ev_ebitda`,
  `ev_sales`, `ev_ebit`, `ev_norm_ebitda`, `ev_ebitda_gy`). A `grep ev_` or a careless `startswith('ev_')` will mix them.
  Rename the event layer to `evt_*` before wiring it.

### 0.2 Probe results that change the plan

| finding | evidence | consequence |
|---|---|---|
| **`earnings-surprises-bulk` is global and cheap** | 2024 alone: 68,418 rows (US 32k, .L 4.3k, .NS 2.5k, .BO 2.4k, .TO 2.3k, .T 2.2k, .SS/.SZ, .TW, .DE, .ST …) | About 13 calls (one per year, 2014–2026) replace the ~30k per-symbol `earnings` calls A1 D#5 budgeted, for the EPS beat history. Revenue surprise still needs per-symbol `earnings`; pull it for firers only. |
| **`income-statement-bulk` (year, period) is global** | FY2024: 55,315 rows (50,394 with revenue) | Annual and quarterly panel refresh: 3 statements × (FY + Q1–Q4) × years, about 15 calls per year of history, versus 3 × 30k. |
| **`eod-bulk` gives one date for the whole market** | 2026-09-25: 58,858 rows | Weekly panel update = 1 call per week (Friday), versus 30k symbol calls. |
| **`profile-bulk` carries ipoDate, CEO and employees** | part 0: 23,347 rows; ipoDate 99.9%, ceo 75%, employees 66% | Global new-listing detection (spin-off reach) and a CEO name for owner matching. It is **rate-limited**: a second call about 2 minutes later got HTTP 429 ×4. |
| **`peers-bulk` is one call** | 82,937 symbols with peer lists | Peer-relative margins for `xr_peer_margin_gap`, and peer RS. |
| **`historical-market-capitalization` defaults to 3 months** | GAW.L: 65 rows by default, 2,964 daily rows from 2015 with `from`/`to` | Point-in-time mcap and share path. **Always pass `from`/`to`.** |
| **`financial-growth` has deep per-share history** | 6861.T: 12 FYs (2015–2026) with 3/5/10-year **cumulative** per-share growth on every FY row | Per-share compounding *consistency* in one call. Convert: CAGR = (1+x)^(1/n) − 1. |
| **`key-executives` carries founder titles** | AXON "Founder, Chief Executive Officer & Director", EVO.ST "Co-Founder, Chairman & President"; `yearBorn` often present; `titleSince` is always null | A global founder-in-management leg for owner_operator, flyover and baron. No tenure. |
| **`funds/disclosure-holders-latest` (N-PORT) covers non-US names** | GAW.L: 24 US funds holding, with `change` | The only institutional-flow lens for non-US names, since 13F is US-listed only and `symbol-positions-summary` is empty for GAW.L. Rate-limited (429 on the second call). |
| **`etf/asset-exposure` is global** | AAPL held by 3,768 ETFs; GAW.L by 449 | Passive-ownership share, which feeds orphan/forced-seller and "undiscovered". |
| **`institutional-ownership/extract-analytics/holder` gives holder-level data** | CROX: `firstAdded`, `holdingPeriod`, `isNew`, `avgPricePaid`, ownership change | "Who is buying" quality, US 13F. |
| **`holder-performance-summary` scores each holder** | Berkshire: 3-year performance vs S&P, turnover, average holding period | Weight accumulation by holder skill and patience. |
| **US-only feeds (correcting A1)** | `mergers-acquisitions-latest` links are SEC S-4 filings (IRT→CSR, PATK→LCII). `price-target-news` is empty for GAW.L and `price-target-summary-bulk` covers 5,318 names. `insider-trading/statistics`, `employee-count` and `historical-employee-count` return nothing for GAW.L / 6861.T. | A1 §A.5 called the M&A feed "global". It is **US SEC-derived**. Non-US deal and target reach needs another source (8-K has none either). |
| **`grades-historical` does cover Japan** | 6861.T: 62 monthly snapshots | Sentiment change lenses work beyond the US where FMP carries ratings. |
| **Dividends are global and deep** | 7203.T: 56 payments since 1999, including the declared next payment | `ev_div_raise_streak` can be global. Use `adjDividend`, same currency as the price. |
| **Clinical biotech leaks into momentum and perception** | `is_clinical_biotech` firers: kullamagie 92, analyst_awakening 90, weinstein 60, rerating_confirmed 30, oneil 5 | This violates the house rule on binary-event mechanisms. Exclude them and add a biotech variant flag (section D Z2). |

### 0.3 Top recommendations (ranked by value ÷ effort)

1. **Wire the four built layers and implement the A1 swaps (zero calls).** This covers `ts_r52` for every price_yoy gate,
   the `tc_*` through-cycle minima, `fqx_*` TTM growth and incremental margin, and the `evt_*` reactions. Section E lists
   each rule.
2. **Exceptional tiers from data already on disk (zero calls).** Measured survivors of the "core" tests:

   | archetype | core rule | survivors |
   |---|---|---|
   | lindy_margin | `tc_min_opm>=15%` over ≥7 FY | 1,275 / 6,290 |
   | lindy_fcf | 8/8 FCF+ with ≥10% average FCF margin, 5-year drawdown shallower than 40% | 669 / 8,683 |
   | no_dilution | 5-year shares ≤0, ROIC lindy ≥15%, FCF/share rising | 256 / 6,672 |
   | quiet_compounder | measured "quiet" | 291 / 2,111 |
   | narrative_lag | growth-not-rewarded core | 362 / 6,524 |
   | weinstein_stage2 | Stage 2A | 216 / 2,591 |
   | oneil_canslim | true C, market RS, near high | 96 / 307 |
   | kullamagie_breakout | RS95, tight, $5M/week | 158 / 1,032 |
   | coiled_base | USD tradeable | 458 / 645 |
   | base_ignition | volume spike, above MA30, MRS>0 | 35 / 116 |
   | bottleneck | `tc_min_gm>=40%` | 931 / 1,780 |
   | greenblatt_magic | TTM ROIC ≥20% | 485 / 743 |
   | capital_returner | no uncovered payout in 3 FYs | 1,292 / 3,815 |
   | xr_forced_seller | `ts_r52<=-40%` | 102 / 239 |
   | insider_conviction | buying ≥30% off the high | 195 / 392 |

   Each becomes `*_core` (or `*_exceptional`) with the current rule kept as `*_watch`, per the breadth doctrine.
3. **`earnings-surprises-bulk` (about 13 calls).** Universe-wide 8–40-quarter beat history. It unlocks the asleep family,
   the reaction lenses (with the panel), EP/ignition and the O'Neil C cross-check. It is the single largest reach gain per
   call in the catalogue.
4. **Bulk CSV path with caching (engineering).** `fmp_client.stream_bulk_csv` exists but is uncached, takes no year/period
   loop and has no 429 cool-down. Add `get_bulk_frame(endpoint, params, ttl)` that persists parquet under
   `fmp_cache/bulk/`, with ≥60 s back-off on 429. Then pull `profile-bulk`, `peers-bulk`, `*-statement-bulk`, `eod-bulk`
   and the `*-consensus-bulk` feeds.
5. **Owner / insider verification (per-symbol, US plus global).** Use `key-executives` founder titles (global) and 13D/G
   holders of type `IN` matched to executive names (US). Add `insider-trading/statistics` quarterly buys (US, point in
   time). Together these turn owner_operator, flyover, baron and asset_owner from a Yahoo `insider%` level (59% of
   owner_operator firers are ≥50% held, i.e. subsidiaries; A1) into revealed alignment.
6. **Point-in-time mcap (`historical-market-capitalization`, about 25k calls).** It gives size bands at the time
   (index-candidate, event study), a share-count path (mcap/price) with no statement dependency, and buyback-at-discount
   timing.
7. **Holder quality for `institutional_accumulation` and base ignition.** Use `extract-analytics/holder` (`isNew`,
   `holdingPeriod`) with `holder-performance-summary` for the US. Use N-PORT `funds/disclosure-holders-latest` as the first
   institutional lens for non-US names.
8. **Event anchors.** Spin-off (10-12B/G dates from the existing `fmp_events`, plus a global `ipoDate` new-listing test
   with no 424B4 IPO prospectus). Index (S&P / Nasdaq-100 / Dow history). Deals (US S-4 M&A feed). Activist (13D). Only
   2,000 names have been run.
9. **Robustness swaps (section C).** Use `splits` for the reverse-split heuristic. Compute same-currency dividend yield from
   `dividends`. Take the currency map from `financial-statement-symbol-list` (reporting vs trading currency). Use observed
   analyst counts in place of "missing = neglected".
10. **Transcripts, targeted.** Pull `earning-call-transcript` (available back to 2005 for AAPL) for about 3k firers of
    order_conversion, contracted_backlog, bottleneck and pre_scale. They give the backlog, book-to-bill, pricing and
    capacity legs non-US filers cannot get from EDGAR.

---

## A. Endpoint-by-endpoint catalogue review

**Legend.**
- **Status:** U = used already; U* = used, but with unused variables that matter; N = not used.
- **PIT:** H = dated history (point-in-time capable); S = snapshot only.
- **Cov:** US = SEC-derived / US-centric; G = global.
- **Cost** assumes about 30k live symbols, 24.7k INV and about 7k US.

### A.1 Statements and derived fundamentals

| endpoint(s) | status | what it adds | archetypes / how | key variables | PIT | cov | cost |
|---|---|---|---|---|---|---|---|
| `income-statement`, `balance-sheet-statement`, `cash-flow-statement` (+`-ttm`) | U | core fundamentals (fmp_statements / fmp_quarterly / throughcycle) | — | — | H (restated values) | G | done |
| `*-statement-bulk` (year, period) | N | the same data, whole universe per call | every fq/tc/fqx consumer; refresh cadence | all statement lines | H | G | ~15 calls/yr of history (CSV) |
| `*-statement-growth` (+bulk) | N | YoY growth of each line (derivable locally) | none beyond local compute | — | H | G | skip (derive) |
| `*-statement-as-reported`, `financial-statement-full-as-reported`, `financial-reports-json/dates` | N | as-filed (unrestated) values | the event-study PIT reconstruction only (restatement-free backtests) | raw XBRL tags | H | US mostly | per symbol; event-study subset only |
| **`financial-growth`** | N | 3/5/10-year **per-share** cumulative growth of revenue, NI, OCF, equity, DPS on every FY row, plus `weightedAverageSharesDilutedGrowth` | durable_reinvestment, cash_reinvest, lindy_growth, qarp, large_cap_quality, book_compounder_discount (**global reach**), xr_baron, xr_compounding_deployer, lynch_pegy/evgy denominators, tenbagger, buyback_compounder, no_dilution. **Tighten-to-exceptional:** per-share compounding that held in *every* FY window | `tenY/fiveY/threeYRevenueGrowthPerShare`, `…OperatingCFGrowthPerShare`, `…NetIncomeGrowthPerShare`, `…ShareholdersEquityGrowthPerShare`, `…DividendperShareGrowthPerShare`, `weightedAverageSharesDilutedGrowth`, `rdexpenseGrowth`, `sgaexpensesGrowth` | H (per FY; add a ~90-day filing lag) | G (JP 12 FYs) | ~25k (annual, limit 12); quarterly optional |
| `ratios`, `key-metrics` (+ttm, ttm-bulk) | U* | provider ratios | — (robustness: prefer own same-currency computes, section C) | `grahamNetNet`, `incomeQuality` already used | H/S | G | done |
| `owner-earnings` | U* | `maintenanceCapex`, `growthCapex` (the Greenwald split, global) | xr_growth_capex_masked (global second lens), overdepreciated_assets, xr_harvest_distribution cross-check | `maintenanceCapex`, `growthCapex`, `ownersEarningsPerShare` | H | G | cached |
| `enterprise-values` | U | EV history (fmp_dynamics) | — | — | H | G | done |
| `financial-scores`, `scores-bulk` | U | Piotroski, Altman | surfaced flags only (no veto) | — | S | G | done |
| `discounted-cash-flow`, `levered-`, `custom-*`, `dcf-bulk` | N | provider DCF | none; opaque assumptions. Skip. | — | S | G | skip |
| `ratings-historical`, `ratings-snapshot`, `rating-bulk` | N | FMP letter score built from ratios | none; a composite of ratios we already hold. Skip. | — | H | G | skip |
| `latest-financial-statements` | N | date of the latest filing | freshness / staleness flag for tc/fq staleness | `date`, `dateAdded` | S | G | 1 paged call |
| `financial-statement-symbol-list` | N | `reportingCurrency` vs `tradingCurrency` per symbol | **robustness**: the one-currency map behind `_fx_coherent` (hidden_assets, forensic family) | `reportingCurrency`, `tradingCurrency` | S | G | 1 call |
| `revenue-product/geographic-segmentation` | U | segments | — | — | H | G | done |
| `employee-count`, `historical-employee-count` | N (tested) | dated headcount from SEC filings | capital_light_pivot, xr_pre_scale_margin, xr_reusable_assembler: revenue per employee (operating-leverage proof) | `employeeCount`, `periodOfReport`, `filingDate` | H | **US only** (JP/UK empty) | ~7k |

### A.2 Earnings, estimates, analysts (perception)

| endpoint(s) | status | adds | archetypes / how | variables | PIT | cov | cost |
|---|---|---|---|---|---|---|---|
| `earnings` | U* (210 names in enrich; 2,000 in fmp_events) | EPS **and revenue** actual vs estimate, dated | asleep family, wolf_seal, base_ignition, kullamagie EP, oneil C | `epsActual/Estimated`, `revenueActual/Estimated`, `date` | H | G (7203.T since 2014) | per symbol; firers only (~5k) once ESB is in |
| **`earnings-surprises-bulk`** (year) | N | EPS surprise for every symbol and year | as above, universe-wide: `evt_beats_8q`, beat streaks, surprise size, with the panel for reactions | `date`, `epsActual`, `epsEstimated` | H | **G** (68k rows/yr) | **~13 calls** (CSV) |
| `earnings-calendar` | N | upcoming report dates (global: 807 in a week) | catalyst proximity for coiled_base / base_ignition / wolf_value_catalyst / biotech; avoid stale "ignition" on the eve of a print | `date`, `epsEstimated` | H | G | ~52 calls/yr |
| `analyst-estimates` | U* | `numAnalystsEps/Revenue`, `epsHigh/Low` (dispersion) are unused | **observed neglect** for coiled_base, liger ×3, blindspot, flyover, quiet_compounder (A1 D#2). Dispersion (high−low)/\|avg\| as "uncertainty" for perception archetypes | `numAnalystsEps`, `numAnalystsRevenue`, `epsHigh`, `epsLow` | **S** (current consensus only; not PIT) | G | cached (0) |
| `grades-historical` | U | monthly rating counts | sentiment change lenses (JP covered) | — | H | G-partial | done / finish run |
| `grades`, `grades-news`, `grades-latest-news` | N | dated rating actions; `grades-news` adds `priceWhenPosted` | analyst_awakening / rerating_confirmed: upgrade **lead vs chase** (upgrade after a +20% run = chase; upgrade with price flat = lead) | `action`, `newGrade`, `previousGrade`, `gradingCompany`, `priceWhenPosted`, `publishedDate` | H | US-centric | ~30k (or firers) |
| `grades-consensus`, `upgrades-downgrades-consensus-bulk` | N | current buy/hold/sell counts | observed coverage count (neglect) in one bulk call | `strongBuy…strongSell` | S | G-partial | 1 bulk |
| `price-target-news`, `price-target-latest-news` | U (fmp_events, event study) | dated targets with `priceWhenPosted` | pt lead/chase flags (built in fmp_events) | — | H | **US/CA** (GAW.L empty) | per symbol |
| `price-target-summary` (+bulk), `price-target-consensus` | U / N | target averages by window | the bulk gives attention counts for 5,318 names in 1 call | `lastQuarterCount`, `lastYearCount` | S | US-centric | 1 bulk |
| `earning-call-transcript` (+dates, latest, list) | N | full call text | order_conversion, xr_contracted_backlog, xr_deferred_revenue_lead, bottleneck, xr_pre_scale_margin, biotech catalysts: **NLP legs** ("backlog", "book-to-bill", "price increase", "capacity constrained", "sole source") | `content`, `date`, `period` | H | G where covered (AAPL from 2005) | targeted ~3k × 2 |

### A.3 Ownership, insiders, institutions

| endpoint(s) | status | adds | archetypes / how | variables | PIT | cov | cost |
|---|---|---|---|---|---|---|---|
| `insider-trading/search` | U (enrich: 213 names) | Form 4 rows | insider_conviction; capitulation | `transactionType`, `securitiesOwned`, `typeOfOwner` | H | US | per symbol |
| **`insider-trading/statistics`** | U (event study only) | quarterly purchases/sales since 2007 | xr_insider_capitulation (PIT crash-quarter buying), insider_conviction persistence (≥2 of 4 quarters), owner_operator / capital_discipline revealed alignment, base_ignition leg, spinoff (spinco insider buying) | `totalPurchases`, `totalSales`, `acquiredDisposedRatio`, `year`, `quarter` | H | **US** | ~7k |
| **`acquisition-of-beneficial-ownership`** (13D/13G) | U (event study only) | dated ≥5% holders with `percentOfClass` and `typeOfReportingPerson` (IN individual, IA adviser, CO corporate, HC holding company) | micro_activist_inflect (**the missing half**), xr_value_unlock, owner_operator (individual 5%+ matched to an executive), controlled_sub_flag (CO/HC ≥50%), base_ignition (new 5% holder), special_situation | `filingDate`, `percentOfClass`, `typeOfReportingPerson`, `nameOfReportingPerson` | H | **US** | ~7k |
| `institutional-ownership/symbol-positions-summary` | U* (3 quarters) | 13F aggregate | extend to 8 quarters (A1) | `newPositions`, `closedPositions`, `investorsHoldingChange`, `putCallRatio` | H | US-listed | +5 per US name |
| **`institutional-ownership/extract-analytics/holder`** | N | per-holder `isNew`, `firstAdded`, `holdingPeriod`, `avgPricePaid`, ownership change | institutional_accumulation / base_ignition: *who* is arriving (new, patient holders) rather than the aggregate | as listed | H (quarterly) | US-listed | paged per symbol per quarter; firers only (~3k × 2) |
| **`institutional-ownership/holder-performance-summary`** | N | per-CIK 3y/5y performance vs S&P, turnover, average holding period | weight new holders by skill (`performance3yearRelativeToSP500Percentage>0`) and patience (`turnover<0.3`, `averageHoldingPeriod`) | as listed | H | US 13F filers | per CIK (~2k active CIKs) |
| `institutional-ownership/holder-industry-breakdown`, `/industry-summary`, `/extract`, `/dates`, `/latest` | N | holder portfolios, filing index | low; industry rotation context only | — | H | US | skip |
| **`funds/disclosure-holders-latest`** (N-PORT) | N | US-registered funds holding **any** security, with `change` | non-US institutional discovery: institutional_accumulation reach, coiled_base perception ("no US fund owns it"), blindspot, liger | `holder`, `shares`, `change`, `weightPercent`, `dateReported` | S (latest) / H via `funds/disclosure` | **global holdings by US funds** | ~5k firers (rate-limited) |
| `funds/disclosure`, `-dates`, `-holders-search` | N | a fund's full N-PORT | history of the above (expensive) | — | H | — | skip |
| **`etf/asset-exposure`** | N | every ETF holding the stock | passive share = Σ sharesNumber / outstanding: orphan / forced-seller context, "undiscovered" (passive share <2%), index-orphan. Global. | `symbol` (ETF), `sharesNumber`, `weightPercentage` | S | G | ~25k or firers |
| `etf/holdings`, `etf-holder-bulk`, `etf/info`, `etf/sector/country-weightings`, `etf-list` | N / partial | ETF-side view | the bulk (parts) is the cheap route to the same passive share | — | S | G | bulk parts |
| `shares-float`, `shares-float-all` | U (fmp_events) | free float % | O'Neil S, controlled_sub_flag corroboration, index eligibility | `freeFloat`, `floatShares` | **S** (dated now) | G | done |
| `governance-executive-compensation` | U (103 names) | exec pay (US proxy) | owner alignment: stock awards vs cash (low value) | `stockAward`, `salary` | H | US | skip wider |
| `executive-compensation-benchmark` | N | industry average pay | pay-vs-peers flag (low) | — | H | US | skip |
| **`key-executives`** | N | titles with "Founder", `yearBorn`, pay | owner_operator, flyover, xr_baron, xr_asset_owner_catalyst: founder-in-management leg. Age of CEO (succession risk, surfaced). **No tenure** (`titleSince` null). | `title`, `name`, `yearBorn`, `pay`, `active` | **S** | G | ~25k or firers (~9k) |
| `senate-*`, `house-*` | N | congressional trades | none. Skip. | — | — | — | — |

### A.4 Corporate events, index, listings

| endpoint(s) | status | adds | archetypes / how | variables | PIT | cov | cost |
|---|---|---|---|---|---|---|---|
| `historical-sp500-constituent`, `sp500-constituent` | U (fmp_events) | dated adds/removals, members | xr_forced_seller (named seller), xr_gaap_profit_crossover (candidate/addition) | `dateAdded`, `removedTicker`, `reason` | H | US | done |
| **`historical-nasdaq-constituent`**, **`historical-dowjones-constituent`**, `nasdaq-constituent`, `dowjones-constituent` | N | same for Nasdaq-100 (451 events since 1985) and the Dow | adds reach to the index-orphan and index-candidate legs | as above | H | US | 4 calls |
| `mergers-acquisitions-latest`, `-search` | U (fmp_events) | deal announcements from S-4 filings | special_situation. **US-only** (correcting A1). | `targetedSymbol`, `transactionDate` | H | **US** | paged |
| `sec-filings-search/symbol`, `/form-type`, `/cik` | U (fmp_events) | filing index by form | spin 10-12B/G, SC 13D, SC TO-T, DEFM14A, 8-K | `formType`, `filingDate` | H | US | ~7k |
| `sec-filings-8k` | N | all 8-Ks by date window (no item numbers in the fields; `hasFinancials`) | a dated catalyst stream; item parsing needs the link | `formType`, `acceptedDate`, `finalLink` | H | US | ~250 calls/yr |
| `sec-filings-financials`, `sec-filings-company-search/*`, `sec-profile`, `all-industry-classification`, `industry-classification-search`, `standard-industrial-classification-list` | N | SIC codes, `fiscalYearEnd`, registrant type | SIC-based heavy-asset / biotech classification cross-check (`is_clinical_biotech` validity); fiscal-year-end for PIT lags | `sicCode`, `fiscalYearEnd` | S | US | ~7k or 1 bulk-ish |
| `ipos-calendar`, `ipos-disclosure`, `ipos-prospectus` | N | IPO dates and 424B4 pricing | distinguishes an IPO from a spin/new listing (spin = new listing **without** a 424B4); IPO-price anchor for new issues | `ipoDate`, `pricePublicPerShare`, `form` | H | US | ~50 paged |
| `symbol-change` | N | ticker changes | identity continuity for the panel (spins, renames) | `oldSymbol`, `newSymbol`, `date` | H | US-mostly | paged |
| `delisted-companies` | U | delistings | survivorship in the event study | — | H | G | done |
| `splits`, `splits-calendar` | N | dated splits with ratio | **robustness**: replaces the "−30% share drop = split" heuristic in no_dilution, buyback_compounder, cannibal_at_discount, cluseau_buyback_accel, xr_cannibal_*, growth_algo | `date`, `numerator`, `denominator`, `splitType` | H | G | ~25k or only names with a share-count drop ≥20% (~2k) |
| `dividends`, `dividends-calendar` | U (fmp_events) | payment history | capital_returner, dividend_verified_value, xr_triple_floor, cundill #5, financials_value: streaks and cuts; same-currency yield | `adjDividend`, `date`, `frequency` | H | G (7203.T since 1999) | ~15k payers |
| `profile`, `profile-bulk`, `profile-cik`, `search-exchange-variants` | U (profile) / N | `ipoDate`, `ceo`, `fullTimeEmployees`, `isAdr`, `description` | spinoff reach (new listings globally), owner matching (CEO name vs 13D name), dual-listing dedupe (`search-exchange-variants`) | as listed | S | G | bulk ~4 parts (rate-limited) |
| `company-screener`, `stock-list`, `actively-trading-list`, `available-*`, `cik-list`, `search-*` | N | universe maintenance | validity guards only | — | S | G | trivial |
| `company-notes` | N | listed debt notes | levered-stub archetypes: listed notes exist (low) | `title` | S | US | skip |

### A.5 Prices, market context

| endpoint(s) | status | adds | archetypes / how | variables | PIT | cov | cost |
|---|---|---|---|---|---|---|---|
| `historical-price-eod/dividend-adjusted`, `/light` | U | weekly panel, indices | — | — | H | G | done |
| **`eod-bulk`** | N | one date, all symbols | panel refresh at 1 call per week | OHLCV, `adjClose` | H | G | 52/yr |
| `historical-price-eod/full` | N | `vwap`, `changePercent` | low (weekly VWAP is not needed) | `vwap` | H | G | skip |
| `historical-price-eod/non-split-adjusted` | N | raw prices | split verification and quote-unit sanity (GBp) | — | H | G | targeted |
| **`historical-market-capitalization`** (pass `from`/`to`) | N | daily mcap | PIT size bands (index-candidate, event study), share path = mcap/price, buyback-at-discount timing, EV/Sales history for non-dynamics names | `marketCap`, `date` | H | G | ~25k |
| `market-capitalization(-batch)`, `quote`, `batch-quote`, `quote-short`, `stock-price-change` | N | snapshots | redundant with the panel. Skip. | — | S | G | skip |
| `historical-chart/*` (intraday), `aftermarket-*`, `batch-*` (crypto/fx/commodity/index quotes) | N | intraday | Kullamägi ORH trigger only; out of scope. Skip. | — | — | — | skip |
| `technical-indicators/*` | N | SMA/EMA/RSI/ADX | redundant with `ts_*`. Skip. | — | — | — | skip |
| `sector/industry-performance(-snapshot)`, `historical-sector/industry-performance`, `sector/industry-pe(-snapshot)`, `historical-*-pe` | N | exchange-level sector/industry aggregates | industry-group RS for O'Neil is better computed from the panel with profile industry. The historical industry PE series I probed ended 2024-03 (stale). Low. | — | H (patchy) | G | skip |
| `biggest-gainers/losers`, `most-actives` | N | intraday lists | skip | — | S | — | — |
| `treasury-rates`, `market-risk-premium`, `economic-calendar`, `economic-indicators` | N | macro | O'Neil "M" and discount-rate context only (low) | `year10`, `totalEquityRiskPremium` | H | US/G | trivial |
| `exchange-market-hours`, `holidays-by-exchange`, `all-exchange-market-hours` | N | calendars | W-FRI panel alignment for markets closed on Friday (validity) | — | — | G | trivial |

### A.6 Skipped (one line each)

- `crowdfunding-offerings-*` and `fundraising-*` (Reg CF / Form D): private issuers, not listed equities.
- `commitment-of-traders-*`: futures positioning, not stock-level.
- `house-*` and `senate-*`: congressional trades; tiny coverage, no thesis fit.
- `esg-ratings`, `esg-disclosures` and `esg-benchmark`: no archetype spirit uses ESG. A governance-score "surfaced flag" is
  conceivable but is not a mispricing lens.
- `news/*`, `fmp-articles`, `news/press-releases`: attention-spike flag only (A1 C#13). It is low value per call; defer.
- `cryptocurrency-list`, `forex-list`, `commodities-list`, `index-list`: reference lists.
- `Suite-derived` (`fmp_drv_*`): the user's own suite columns. Most duplicate repo measures (`fmp_drv_pct_off_high` ≈
  `ts_dist_hi52`, `fmp_drv_shares_yoy` ≈ `fq_shares_yoy`). Use the repo's point-in-time versions.

---

## B. "Truly exceptional" specifications (top ~1–5% of genuine instances)

Each spec is a **core / exceptional tier**, never a veto. The current rule stays as the `*_watch` membership. Measured counts
are current firers that pass, on current coverage (INV). Threshold rationale is given inline.

### B.1 Growth-not-rewarded / re-rating / perception

1. **`arch_coiled_base` (645 → exceptional 33 on today's coverage).** The ordinary member is flat for two years with some
   coil. The exceptional member has **three independent coils plus proof nobody is watching**.
   - `ts_dvol26_usd>=250k` (validity; 458 pass). `coil_n>=2`, e.g. `bs_coil_rev>=log1.3` AND `fqx_ebit_ttm_g>=0.20`.
   - EPS rising in `fqx_eps_pos_share_8>=0.75` of quarters (value accreting every quarter, not one jump).
   - `ts_weinstein_stage==1` (a true base, not stage 4).
   - **Observed** neglect: `numAnalystsEps<=2` from the cached `analyst-estimates`, no N-PORT US-fund holder, and ETF
     passive share <2% (`etf/asset-exposure`).
   - Rationale: the dry-run lift sat in the top quintile of coil depth. Requiring the perception lag to be *observed* removes
     the 54% of firers whose neglect is merely missing data.
2. **`arch_base_ignition` (116 → 35).** On top of the above: `ts_vol_spike4>=3 & ts_above_ma30 & ts_mrs>0` (35 pass). Plus
   one *dated* trigger:
   - an earnings-week reaction ≥+8% on a beat (`evt_react_last` from ESB dates and the panel), or
   - a new 13D/13G ≤90 days (`acquisition-of-beneficial-ownership`, US), or
   - ≥3 US funds initiating in N-PORT (`change>0`, non-US).

   Rationale: Kullamägi/EP studies put the lift on volume ≥3× and gap-ups ≥8–10%.
3. **`arch_narrative_lag` → growth-not-rewarded core (6,524 → 362).** `fqx_ebit_ttm_g>=0.20 & ts_r52<=0 &
   fqx_eps_pos_share_8>=0.75`. Exceptional adds `evt_ignored_beats_2y>=3` (beats the price did not reward) and
   `ts_r104<=0.10` (the lag persists over two years).
4. **`arch_asleep_at_wheel` (2,445; only 367 have event data).** Exceptional:
   - ≥7 of 8 EPS beats (ESB).
   - Median surprise ≥5%.
   - Revenue beats in ≥6 of 8 (per-symbol `earnings`).
   - `ev_react_beats_4q<=0` (the market fades them).
   - `fmp_dyn_fwd_underestimate_gap>0` (the street still models slower growth).

   Measured on current coverage: 7/8 beats plus ≥3 ignored gives 127 of 367. Rationale: 40% of covered names have a
   4-quarter beat rate ≥0.75, so only an 8-quarter record with *ignored* reactions is rare.
5. **`arch_asleep_unrerated` / `arch_xr_audited_streak_unrerated`.** Exceptional:
   - The beats as above, with `fmp_dyn_unrerated_gap>=0.25`.
   - The multiple has not expanded on the dated EV history: EV/Sales now ≤ its 3-year median from `enterprise-values` or
     HMC.
   - At least 2 of the 6 no-rerate lenses agree.
6. **`arch_evsales_derating`.**
   - TTM revenue growth ≥25% on `fqx`, with FG `threeYRevenueGrowthPerShare>=+52%` (15%/yr; not a one-year pop).
   - EV/Sales down ≥30% over 2 years on the dated EV series.
   - Incremental EBIT margin `fqx_inc_ebit_margin>=0.15`: the derate happened while unit economics improved.
7. **`arch_analyst_awakening` (2,102; A1 change-or-turn 933).** Exceptional:
   - The street is **leading, not chasing**: `ev_pt_lead_flag==1` (targets up ≥10% in 90 days while price moved <5%), or
     ≥2 upgrades in `grades-news` whose `priceWhenPosted` sits within 5% of the 13-week-ago close.
   - `sent_n_analysts_d12>=2` (coverage growing).
   - `ts_mrs` rising from <0.
   - Exclude `is_clinical_biotech` (90 current firers) into a `biotech_awakening_watch` flag.
8. **`arch_analyst_rerating_confirmed`.** Exceptional: abs 52-week high (`ts_dist_hi52>=0.97`) **and** `ts_rs_at_hi` **and**
   `ts_ma30_slope13>0`. Plus the first upgrade inside 13 weeks of the breakout (confirmation, not a late chase:
   `ev_pt_chase_flag==0`).
9. **`arch_institutional_accumulation`.**
   - US exceptional: ≥3 holders `isNew` this quarter (IOH) whose `holder-performance-summary`
     `performance3yearRelativeToSP500Percentage>0` and `turnover<0.3`, plus aggregate adding for ≥3 of the last 4 quarters
     (8-quarter history), while `ts_r26<=0`.
   - Non-US: ≥3 US funds with N-PORT `change>0` and no fund selling.
   - Rationale: aggregate 13F deltas are dominated by passive rebalancing; skilled, patient *new* entrants are the rare
     signal.
10. **`arch_liger_neglected_survivor` / `arch_liger_lagging_inflect` / `arch_blindspot`.** Exceptional:
    - Coverage *observed* 0–1 (AE / GH), no N-PORT holder, ETF passive share <2%.
    - Shock-sized inflection: `fqx_inc_ebit_margin>=0.30` or `fqx_eps_turned`.
    - Insider buying in the last 2 quarters (IST, US) or buyback (`fq_shares_yoy<=-0.02`, global).
    - `ts_dvol26_usd` between $50k and $2M per week (tradeable but under the radar).

### B.2 Quality / compounder lindy

11. **`arch_lindy_fcf` (8,683 → core 2,125 → exceptional 669).** Core: `tc_fcf_pos==tc_fcf_years>=7 &
    tc_fcf_margin_avg>=0.10`. Exceptional adds the price-lindy `ts_maxdd_5y>=-0.40` (only 17% of INV). Rationale: 4/5 FCF
    years is the base rate of profitable firms (A1). Every year positive over 7–8 with a double-digit margin is the
    Lindy claim.
12. **`arch_lindy_margin` (6,290 → 1,275).** `tc_min_opm>=0.15` over ≥7 FYs, and current op margin ≥0.8×`tc_med_opm`.
    Exceptional: `tc_min_gm>=0.40` as well (gross pricing power never broke).
13. **`arch_no_dilution` / `arch_buyback_compounder` (6,672 → 256).** `fmp_st_shares_growth_5y<=0 & roic_lindy>=0.15 &
    fqx_fcf_ps_g>0`.
    - Exceptional buyback_compounder: FG `weightedAverageSharesDilutedGrowth<0` in ≥4 of 5 FYs.
    - Plus **counter-cyclical** execution: buyback/HMC-mcap higher in FYs where the price was ≥20% off its high.
    - Any share drop must be confirmed as a buyback by `splits` (no reverse split on that date).
14. **`arch_durable_reinvestment` / `arch_cash_reinvest` / `arch_qarp` / `arch_xr_compounding_deployer`.** Exceptional:
    - Per-share compounding held in **every** window. FG `fiveYRevenueGrowthPerShare>=0.61` and
      `fiveYOperatingCFGrowthPerShare>=0.61` (10%/yr) on each of the last 5 FY rows, and `tenYRevenueGrowthPerShare>=1.59`.
    - `tc_min_opm>0`.
    - `ts_maxdd_5y` shallower than the name's market median.
    - Rationale: rolling ROIIC on small deltas is noisy (A1). Per-share multi-window growth consistency is what the
      100-bagger literature actually measures.
15. **`arch_quiet_compounder` (2,111 → 291).** `ts_r52<=0.20 & ts_maxdd_5y>-0.45 & fqx_ebit_ttm_g>=0.10`, then observed
    coverage ≤3. Exceptional adds a founder or owner leg (`key-executives` "founder" / 13D individual) and no US-fund N-PORT
    holder.
16. **`arch_owner_operator` / `arch_flyover`.** Core: insider 10–60% (3,246 of 5,345; excludes ≥60% parent-controlled
    subsidiaries, surfaced as `controlled_sub_flag`). Exceptional:
    - A founder in an executive title (`key-executives`), or a 13D/13G with `typeOfReportingPerson=='IN'` whose name
      matches an executive (US).
    - **and** net insider buying in ≥1 of the last 4 quarters (IST) or 5-year shares ≤0.
    - **and** ROIC ≥15% through the cycle (`tc_min_opm>0` & `roic_lindy>=0.15`).
    - Flyover also requires observed coverage ≤2.
17. **`arch_bottleneck` (1,780 → 931).** `tc_min_gm>=0.40` over ≥7 FYs. Exceptional:
    - `tc_min_opm>=0.20`.
    - Gross margin up in the latest TTM (quarterly panel).
    - Transcript pricing/capacity language ("price increase", "capacity constrained", "sole source", "allocation") in ≥2 of
      the last 4 calls (targeted `earning-call-transcript`).
18. **`arch_large_cap_quality` / `arch_capital_returner`.**
    - Capital_returner core: `tc_uncov_payout_3y==0` (1,292 of 3,815). Exceptional: `ev_div_raise_streak>=10` (global via
      `dividends`) with no cut, and buyback counter-cyclical.
    - Large-cap exceptional: `tc_min_opm>=0.20` and FG `tenYRevenueGrowthPerShare>=0.97` (7%/yr).

### B.3 Momentum / technical

19. **`arch_weinstein_stage2` (2,591 → 216).** `ts_weinstein_stage==2 & ts_mrs_13ago<=0 & ts_vol_spike4>=2`. Exceptional:
    - A breakout from a ≥2-year base (`ts_multi_year_high==1`).
    - `ts_mkt_breadth30>=0.5` (market in gear).
    - An earnings beat in the breakout window (ESB).
    - Exclude clinical biotech (60).
20. **`arch_oneil_canslim` (307 → 96).**
    - C: `fqx_eps_q_yoy>=0.25 & fqx_eps_accel>0`.
    - A: FG `threeYNetIncomeGrowthPerShare>=0.52`.
    - N: `ts_dist_hi52>=0.85`.
    - L: `ts_rs_pct_mkt>=0.80`.
    - S: `freeFloat` 20–80%.
    - I: `fmp_inst_new_q0>0`.
    - M: `ts_mkt_breadth30>=0.5`.
    - Exceptional: C ≥+40% with **revenue** surprise too (earnings), and an RS line at a high before price
      (`ts_rs_at_hi & ts_dist_hi52<0.97`).
21. **`arch_kullamagie_breakout` (1,032 → 158).** `ts_rs_pct_mkt>=0.95 & ts_tight5<=0.10 & close>ts_ma10>ts_ma30 &
    ts_dvol26_usd>=$5M/week`. Exceptional: the prior impulse is an **episodic pivot**: an earnings-week gap ≥+10% on ≥3×
    volume within 26 weeks (ESB dates plus panel). Exclude clinical biotech (92) into a `biotech_momentum_watch` flag.
22. **`arch_wolf_seal`.** A beat (ESB) with `ev_react_last<=-0.05`, `ts_r52>=+0.10` and `fqx_eps_accel>0`. The dip is on the
    print, not on the business.

### B.4 Event-driven

23. **`arch_spinoff_value/quality/asset` (3/2/2 firers).**
    - Reach: the spin anchor = `ev_spin_filing_date` (10-12B/G) or a global new listing (`profile-bulk` `ipoDate`≤24m with
      no `ipos-prospectus` 424B4 and no `ipos-calendar` entry), cross-checked by `symbol-change`.
    - Exceptional: 3–18 months after listing; **orphan price action** `ts_r13<0` while the parent is flat or up; insider
      purchases at the spinco in its first 2 quarters (IST); ETF passive share below the parent's (index funds not yet in).
24. **`arch_special_situation`.**
    - Anchor: `ev_ma_target_date` / `ev_tender_date` / `ev_merger_proxy_date` (US).
    - Exceptional: spread ≥8% annualised to deal close with a cash consideration; the acquirer is not financing-contingent
      (S-4 vs cash: an S-4 link implies stock consideration, so a tender-offer/cash deal ranks higher); freshness ≤6 months.
25. **`arch_xr_gaap_profit_crossover` → index candidate.**
    - US, not an S&P 500 member (`ev_sp500_member==0`).
    - Sum of the last 4 quarters of GAAP NI >0 and the latest quarter >0 (quarterly panel; this is the S&P earnings rule).
    - `freeFloat>=10%`, and HMC mcap in the S&P eligibility band (or the S&P 400/600 band for the lower rung).
    - `ts_rs_pct_mkt>=0.7`.
    - Exceptional: already in the Nasdaq-100 or S&P 400 (a promotion path; `historical-nasdaq-constituent`).
26. **`arch_xr_forced_seller` (239 → 102 on `ts_r52<=-0.40`).** Exceptional: a **named** seller —
    - removal from the S&P 500, Nasdaq-100 or Dow ≤12 months (the IDX endpoints), or
    - 13F `fmp_inst_own_chg_q0<=-5pp`, or
    - the ETF passive share dropped.

    Plus TTM revenue ≥+5% and no dilution.
27. **`arch_micro_activist_inflect` / `arch_xr_value_unlock`.**
    - The board/activist half: a new 13D (first filing ≤12 months, `percentOfClass>=5`, reporting type IA/IN, not
      CO/HC), and/or an 8-K item 5.02 appointment.
    - Exceptional: the activist's `holder-performance-summary` 3-year relative performance >0 (a proven allocator), and
      insider buying after the appointment.
28. **`arch_insider_conviction` / `arch_xr_insider_capitulation` (392 → 195 on `ts_dist_hi52<=0.7`).** Exceptional:
    - purchases in ≥2 of the last 4 quarters (IST), with ≥3 distinct buyers or CEO/CFO among them,
    - into a ≥40% drawdown, with TTM revenue ≥−10% and `tc_min_opm>0`.

### B.5 Value / turnaround and forensic XR

29. **`arch_cundill_deep_value` / `arch_templeton_pessimism` (templeton 2,033 → 1,330 at ≤0.5).**
    - Cundill point 2 exactly: `ts_dist_hi260<=0.5`.
    - Exceptional: EV/normalized EBITDA ≤6, `tc_min_opm>0` (never a loss year in 8), dividend not cut (DIV), insider buying
      (IST).
30. **`arch_xr_quality_crisis` (A1 527).** Exceptional:
    - ≥7/8 FCF years and `tc_min_opm>=0.10` (quality proven through a cycle).
    - `ts_dist_hi260<=0.5`.
    - TTM revenue ≥0.
    - `ts_maxdd_5y` for the *prior* 5 years shallower than −30%, i.e. an unusual drawdown for this name (`ts_dd_unusual`).
31. **`arch_dead_option` / `arch_regime_cyclical` / `arch_xr_cyclical_trough`.** Exceptional:
    - op margin below `tc_med_opm` by ≥5pp and turning up (`fqx_ebit_ttm_g>0`),
    - measured asset intensity (A1 A.4),
    - `ts_dist_hi260<=0.5` with `ts_r13>0` (no longer collapsing),
    - insider or company buying.
32. **`arch_xr_leverage_detonation` / `arch_tenbagger_credible` / `arch_cheap_sales_scaler`.** Exceptional:
    - `fqx_inc_ebit_margin>=0.35` on TTM revenue ≥+20%,
    - first positive TTM EBIT inside the last 2 quarters (`fmp_dyn_opinc_turned_positive`),
    - SPL-verified flat share count,
    - `ts_weinstein_stage` in {1, 2}.
33. **`arch_post_reorg`.** Exceptional: 8-K item 1.03 / effective date ≤24 months, EBITDA yield ≥20% at the emergence
    price (HMC mcap at emergence, not today), and net debt falling (fq).

---

## C. Robustness: fragile measures and the catalogue fix

| fragile measure (where) | why fragile | robust replacement |
|---|---|---|
| `price_yoy`, `momentum_12m`, `roc_12m`, `roc_6m` (tape gates across ~25 archetypes) | snapshot, price-only, noisy vs panel (A1 §0.3) | `ts_r52`, `ts_r26`, `ts_r13` (total return, PIT) |
| `price_pct_of_5y_range`, `beaten_down_any` 52w lens | not the "former high"; local-currency snapshots | `ts_dist_hi260`, `ts_dist_hi52` |
| `yf_beta` (bab ×3) | shrunk, stale; Spearman 0.46 vs panel | `ts_beta_1y/3y`, `ts_beta_*_rk` |
| pew `avg_dollar_volume` (blindspot, bab) | 8% coverage, 0% on blindspot firers | `ts_dvol26_usd` (quote-unit aware) |
| `bs_med_dvol26` (coiled_base gate, line 6014) | listing currency (JPY/KRW/GBp) | `ts_dvol26_usd` |
| `yf_earnings_growth` (lynch_pegy) | single quarter, 100% cap | `fqx_ni_ttm_g`, FG `threeYNetIncomeGrowthPerShare` |
| `rev_yoy`, `rev_accel`, `ebitda_yoy` (growth gates) | one annual/TTM point, base effects | `fqx_*_ttm_g` (date-matched), FG 3y/5y per-share |
| `oper_lev_any` (6 ORed angles) | includes raw sequential moves | `fqx_inc_ebit_margin` |
| `incremental_ebitda_margin` (annual) | one-year delta | `fqx_inc_ebit_margin` (TTM) |
| annual `*_first_positive` flags | annual, FCF working-capital noise | `fmp_dyn_*_turned_positive`, `fqx_eps_turned` (dated) |
| `op_margin_lindy`, `n_yrs_positive_*` (4 of 5) | averages and base-rate counts | `tc_min_opm`, `tc_min_gm`, `tc_fcf_pos/tc_fcf_years` (8 FY) |
| `interest_coverage` (strong_coverage) | one period | `tc_min_ic` |
| `roce` single period (greenblatt, flyover, quiet) | provider ratio, one period, tiny-denominator artifacts | `fqx_roic_ttm` + `tc_med_opm` |
| `earnings_beat_rate` (4 quarters) | base rate (40% ≥0.75) | ESB 8–40 quarters; `evt_beats_8q` |
| `analyst_target_upside_pct`, `yf_recommendation_mean` | levels, not change; stale for small caps | `sent_*_d12`, `price-target-news` revision, `grades-news` with `priceWhenPosted` |
| `n_analysts` missing ⇒ neglected (liger, flyover, blindspot, coiled) | missing ≠ neglected (84% of liger firers have no field) | `numAnalystsEps` (cached AE), `grades-consensus` bulk counts, `price-target-summary-bulk` |
| `insider_ownership_pct` (Yahoo; owner, flyover, quiet, baron) | includes corporate parents (59% of owner firers ≥50%) | 13D/G `typeOfReportingPerson` (IN vs CO/HC), `freeFloat`, `key-executives` founder, IST |
| `insider_cluster_buy_flag` (Form 4 window) | window snapshot | IST quarterly purchases (PIT since 2007) |
| `yf_institution_pct` (coiled perception leg) | Yahoo level, US-biased | `fmp_inst_own_pct` (US), N-PORT holders (non-US), ETF passive share |
| `shares_yoy <= -30%` "reverse split" heuristic (7 archetypes) | guesswork; a genuine big buyback is misread | `splits` (dated ratio, `splitType`) |
| `dividend_yield` provider TTM (triple_floor, dividend_verified) | FX-corruptible (the code notes this for `earnings_yield`) | Σ `adjDividend` 12m / price, both in listing currency (`dividends` + panel) |
| `net_cash_pct`, `earnings_yield`, `ncav_pct` (level-over-mcap forensic gates) | currency mix (Kalbe, JFU class) | balance sheet in `reportedCurrency` / mcap converted via `fmp_fx`, gated on `financial-statement-symbol-list` reporting vs trading currency |
| `ev_sales_change_yoy` reconstructed from `price_yoy` | one noisy point | `enterprise-values` history (fmp_dyn) or HMC mcap history + fq net debt |
| `spin_flag`, `merger_flag` (EDGAR Form-10 only) | 58 and 300 names | `ev_spin_filing_date`, `ev_ma_target_date`, profile `ipoDate` without 424B4 |
| `HEAVY_ASSET_SECTORS` label (fixed_cost, regime, cyclical_trough) | sector label | quarterly `ppe/assets`, `da/revenue`, capex intensity (A1 A.4) |
| sector median op margin (xr_peer_margin_gap) | sector too coarse | `peers-bulk` peer set or profile industry (≥20 names) |
| `mcap` snapshot in historical comparisons (event study, size bands) | not PIT | `historical-market-capitalization` |
| `analyst-estimates` consensus in any backtest | not PIT (current only) | grades-historical, price-target-news and ESB `epsEstimated` (the dated pre-report consensus) |
| FMP statements in backtests | restated values | `*-as-reported` / `financial-statement-full-as-reported` (US), plus filing-date lags |

---

## D. Ranked implementation plan

### D.1 Zero-call (cache or existing files)

| # | item | code-level change | value |
|---|---|---|---|
| Z1 | Wire the built layers | `archetype_tags.py` after line 264: `_merge_fmp_overlay(df, 'ts_snapshot.csv')`, `'fmp_throughcycle.csv'`, `'fmp_quarterly_ext.csv'`, `'fmp_events.csv'`. Rename the event columns `ev_*`→`evt_*` in `fmp_events.py` first (collision hazard). | very high |
| Z2 | Biotech separation (house rule) | In kullamagie (2444), weinstein (2463), oneil (2492), analyst_awakening (5791), analyst_rerating_confirmed (5831), coiled_base (6016): `& ~_is_clinical_biotech`. `_is_clinical_biotech` is defined at line 6410, after these archetypes, so
hoist its definition (and `_is_drug_dev` / `_commercial`) above line 2444 first. Surface `biotech_momentum_watch` / `biotech_awakening_watch` for the excluded names (92 / 60 / 5 / 90 / 30). | high (doctrine) |
| Z3 | A1 proxy swaps | `ts_r52` for `price_yoy`/`momentum_12m` in `flat_or_down`, `_lag_tape`, `beaten_down_any` (1029), `not_too_deep_any` (1044), forced_seller (3849), asleep_unrerated `_pyw_au` (5234), evsales `_stk_ret` (5518), institutional `_ip12/_ip6`. `ts_dvol26_usd` in `_cb_valid` (6014) and the blindspot/bab ADV gates. `ts_beta_*_rk` in bab (1920–1945). | very high |
| Z4 | Exceptional tiers (section B) as `*_core` plus `*_watch` columns | lindy_margin / lindy_fcf / no_dilution / capital_returner / strong_coverage / bottleneck from `tc_*`; greenblatt / oneil / wolf from `fqx_*`; weinstein / kullamagie / ignition from `ts_*` | high |
| Z5 | Observed neglect | extract `numAnalystsEps`, `numAnalystsRevenue`, `epsHigh/Low` from the cached `analyst-estimates` payload in `fmp_dynamics.py` → `fmp_dyn_n_analysts_eps`, `fmp_dyn_eps_dispersion`. Replace `~(n_analysts_v > 3)` (missing permissive) with the observed count where present, and keep missing as `*_watch`. | high |
| Z6 | Event-study features into the live layer | `event_study_pit.features_for` already computes `ins_buys_8q`, `ins_buy_quarters_4q`, `bo_new_holders_12m`, `bo_increasing_12m` from cached IST / BO. Emit the latest-date row per symbol in `fmp_events.py` (same cache keys). | medium-high |
| Z7 | `tc_uncov_payout_3y` into balance_sheet_return / forensic_payout_confirmed / capital_returner | direct column swaps (A1 B.1) | medium |

### D.2 Cheap one-off calls (bulk / paged)

| # | endpoint | calls | output / wiring | value |
|---|---|---|---|---|
| C1 | `earnings-surprises-bulk?year=2014..2026` | 13 (CSV) | `fmp_earnings_bulk.parquet` → `fmp_events` beat stats universe-wide (`evt_beats_8q`, streak, median surprise, reactions via the panel) | very high |
| C2 | `peers-bulk`, `upgrades-downgrades-consensus-bulk`, `price-target-summary-bulk`, `financial-statement-symbol-list`, `latest-financial-statements` | ~5 | peer sets; observed coverage counts; currency map; staleness flag | high |
| C3 | `profile-bulk?part=0..3` | ~4 (≥60 s apart) | `ipoDate`, `ceo`, `fullTimeEmployees`, `isAdr` → spin/new-listing anchor; CEO name for 13D matching | high |
| C4 | `historical-nasdaq-constituent`, `historical-dowjones-constituent`, `nasdaq-constituent`, `dowjones-constituent` | 4 | `evt_ndx_removed_12m`, `evt_dow_removed_12m`, members | medium |
| C5 | `ipos-prospectus` / `ipos-calendar` (paged, 3 years) | ~60 | IPO vs spin discrimination | medium |
| C6 | `earnings-calendar` (weekly window) | 52/yr | `evt_next_report_days` | medium |
| C7 | `*-statement-bulk` (year × period) | ~15 per history-year | replaces per-symbol statement refreshes (engineering E1 first) | medium (cost saver) |
| C8 | `eod-bulk` (each Friday) | 1/week | incremental panel refresh | medium (cost saver) |
| C9 | `symbol-change` (paged), `sec-filings-8k` (by date) | ~300 | identity continuity; 8-K catalyst stream | low-medium |

### D.3 Per-symbol pulls (ranked)

| # | endpoint | scope | calls | unlocks |
|---|---|---|---|---|
| S1 | finish `fmp_events` (earnings limit 100, price-target-news, dividends, SECF forms) | all live | ~30k × 3–4 (earnings drops to firers once C1 lands) | reactions, pt lead/chase, dividend streaks, spin / 13D / tender / merger dates |
| S2 | `key-executives` | INV or firers of owner/flyover/quiet/baron/asset_owner (~9k) | 9k–25k | founder leg, CEO age |
| S3 | `insider-trading/statistics` + `acquisition-of-beneficial-ownership` | US (~7k) | ~14k (partly cached by the event study) | PIT insider buying; activist/13D; individual-owner match; controlled_sub corroboration |
| S4 | `financial-growth` annual (limit 12) | INV | ~25k | per-share compounding consistency (B.14); global book compounding |
| S5 | `historical-market-capitalization` (from 2015) | INV | ~25k | PIT size, share path, counter-cyclical buybacks, emergence price |
| S6 | `dividends` | payers (~15k) | 15k (part of S1) | streaks and cuts, same-currency yield |
| S7 | `splits` | names with any share-count drop ≥20% (~2k) or all (25k) | 2k–25k | split guard |
| S8 | `etf/asset-exposure` | INV | ~25k | passive share (orphan, undiscovered) |
| S9 | `funds/disclosure-holders-latest` | non-US firers of coiled / liger / blindspot / institutional (~5k) | 5k (rate-limited) | non-US institutional discovery |
| S10 | `institutional-ownership/extract-analytics/holder` (2 quarters) + `holder-performance-summary` (CIKs seen) | US firers (~3k) + ~2k CIKs | ~8k | holder quality for accumulation / ignition |
| S11 | `symbol-positions-summary` to 8 quarters | US | +5 per name (~35k) | persistence baseline (A1) |
| S12 | `earnings` (revenue surprise) | asleep / awakening / oneil firers (~5k) | 5k | revenue-beat legs |
| S13 | `historical-employee-count` | US (~7k) | 7k | revenue/employee |
| S14 | `earning-call-transcript` | targeted firers (~3k × 2) | 6k | backlog / pricing / capacity NLP legs |
| S15 | `grades-news` | US firers of awakening / rerating (~3k) | 3k | upgrade lead vs chase |

### D.4 Engineering items

- **E1: cached bulk path.** Add `fmp_client.get_bulk_frame(endpoint, params, ttl, cols=None) -> pd.DataFrame`. It wraps
  `stream_bulk_csv` and writes `fmp_cache/bulk/<endpoint>/<k=v…>.parquet`. It returns the cached frame when fresh. On HTTP
  429 it sleeps ≥60 s with exponential back-off, because the current 4 × (3→24 s) retries fail on `profile-bulk`. It
  should also accept a row filter to keep memory low. Callers: C1, C2, C3, C7, C8.
- **E2: prefix hygiene.** Rename the event columns to `evt_*`, and add an assertion in `_merge_fmp_overlay` that no
  overlay column collides with an existing master column prefix family.
- **E3: PIT lags.** Store `filingDate` / `acceptedDate` beside every FY/quarter row (the statements carry them; FG does
  not, so join on `date`). The event study must apply `acceptedDate` or `date + 90d`.
- **E4: currency map.** Build `ccy_map.csv` (symbol, reportingCurrency, tradingCurrency, quote_unit) from
  `financial-statement-symbol-list` plus the GBp / ZAc / ILA units. Replace ad hoc `_fx_coherent` inference.
- **E5: HMC gotcha.** `historical-market-capitalization` silently returns 3 months without `from`/`to`. Wrap it in a helper
  that always passes both.
- **E6: US-only feed flags.** Mark `mergers-acquisitions-*`, `price-target-news`, `insider-*`, `acquisition-of-beneficial-ownership`,
  `employee-count` and `sec-*` as US-only in the data dictionary. Their absence for non-US names must never read as
  "no event" (breadth doctrine: missing ≠ negative).

---

## E. Complete per-archetype matrix (167 rows)

The CSV version is `scratchpad/archetype_endpoint_matrix.csv`. Its columns are `archetype`, `line`, `firers`, `spirit`,
`current_key_inputs`, `augmenting_endpoints_variables`, `gain_type`, `impact` and `concrete_rule_change`.

"Firers" counts all rows. Measured counts inside the cells are INV. Gain types: REACH, PROXY (replace a proxy), LEG (new
evidence leg), EXC (tighten toward the exceptional), NONE.

**Abbreviations.**

| group | abbreviations |
|---|---|
| Layers already built | TS = `ts_snapshot.csv`, TC = `fmp_throughcycle.csv`, FQX = `fmp_quarterly_ext.csv`, EVT = `fmp_events.csv` (`ev_*`, to be renamed `evt_*`), SENT = `fmp_sentiment.csv` |
| Insider and ownership filings | IST = `insider-trading/statistics`, BO = `acquisition-of-beneficial-ownership` |
| Earnings and fundamentals | ESB = `earnings-surprises-bulk`, FG = `financial-growth`, OE = `owner-earnings` |
| Management, price and float history | KE = `key-executives`, HMC = `historical-market-capitalization`, SPL = `splits`, DIV = `dividends`, SF = `shares-float` |
| Analysts | AE = `analyst-estimates`, GH = `grades-historical`, PTN = `price-target-news`, GN = `grades-news` |
| Institutions and funds | IOH = `institutional-ownership/extract-analytics/holder`, HPS = `holder-performance-summary`, NPORT = `funds/disclosure-holders-latest`, ETFX = `etf/asset-exposure` |
| Filings, index and calendar | SECF = `sec-filings-search/symbol`, 8K = `sec-filings-8k`, IDX = historical index constituents, TR = `earning-call-transcript`, ECAL = `earnings-calendar` |
| Profiles and peers | PROF = `profile(-bulk)`, EMP = `historical-employee-count`, PEERS = `peers-bulk` |
| Cross-references | A1 = first audit section |

**Summary.** Impact is High for 32 archetypes, Medium for 59 and Low for 76. Of the Low group, 43 are "NONE". Those are
mostly EDGAR-specific forensic archetypes whose inputs are already direct.

| archetype (line, firers) | spirit | current key inputs | augment with | gain | impact | concrete rule change |
|---|---|---|---|---|---|---|
| `narrative_lag` (1152, 6524) | price/narrative lags genuinely improving fundamentals | _lag_tape (price_yoy/momentum_12m<0 or bs base), _adv_breadth>=2, pb<3/fcf_yield>=3% | TS ts_r52/ts_r104; FQX fqx_ebit_ttm_g, fqx_eps_pos_share_8; EVT ev_ignored_beats_2y; ESB | PROXY+EXC | H | A1 A.2: lag measured vs the advance (log(1+TTM g) - log(1+ts_r52) >= log 1.2). Core: fqx_ebit_ttm_g>=0.20 & ts_r52<=0 & fqx_eps_pos_share_8>=0.75 (362 of 6,524 measured); narrative_lag_watch = current rule |
| `fixed_cost_demand_shock` (1162, 2975) | heavy fixed-cost asset base meets a demand shock (operating leverage) | HEAVY_ASSET_SECTORS label, rev_accel>0, rev_yoy>0, nde cap | quarterly panel ppe/assets, da/rev; FQX fqx_inc_ebit_margin; TC tc_med_opm | PROXY+LEG | M | A1 A.4 measured asset intensity replaces the sector label; add fqx_inc_ebit_margin>=0.30 as the drop-through proof; exceptional: current op margin <= tc_med_opm-5pp with TTM rev >= +10% (headroom to mid-cycle) |
| `discounted_vehicle` (1182, 1255) | net-cash operating company below 0.85x book | pb, cash_gt_ev, net_cash_pct, nde | BO (activist 13D), EVT ev_sc13d_date | LEG | L | surface ev_sc13d_date<=365d as a catalyst score term; no rule change |
| `capital_discipline` (1220, 3293) | discipline evidenced by an allocation ACTION plus real returns | _own_aligned (insider>=20% or action), returns floor, _op_viable | TC tc_uncov_payout_3y; fmp_st_financing_outflow_years; IST; SPL; HMC | EXC | M | A1 B.1: action OR (insider & financing outflow >=80% of FYs). Exceptional: tc_uncov_payout_3y==0 & 5y shares<=0 & counter-cyclical buybacks (buyback yield higher in FYs where HMC price was >=20% off its high) |
| `regime_cyclical` (1233, 1305) | heavy-asset cyclical at a regime change, revenue turning up | HEAVY_ASSET_SECTORS, beaten_down_any(0.20), rev_yoy>0 | TS ts_dist_hi260; TC tc_med_opm; FQX fqx_ebit_ttm_g | PROXY | M | A1 A.4 (measured asset intensity, ts_dist_hi260). Exceptional: op margin below tc_med_opm and fqx_ebit_ttm_g>0 (margin turning from below mid-cycle) |
| `dead_option` (1257, 1617) | priced as dead while still a cash cow | beaten_down_any(0.40), cash yield, ebitda_margin>0, _op_viable | TS ts_dist_hi260, ts_r13; TC tc_fcf_pos; IST | PROXY+EXC | M | A1 A.4: >=40% below the 5y high and ts_r13>-0.10 (805 of 1,617). Exceptional: tc_fcf_pos>=6 of 8 FYs + insider buying (IST) in the drawdown |
| `kpi_threshold` (1285, 4123) | an operating KPI crosses its threshold | annual first-positive flags, margin_confirming/roce_today | fmp_dyn_*_turned_positive; FQX fqx_eps_turned, fqx_inc_ebit_margin; ESB | PROXY | M | A1 B.1: confirm on quarterly TTM (1,946 of 4,123). Exceptional: TTM turn with fqx_inc_ebit_margin>=0.30 and a beat in the turning quarter |
| `blindspot` (1297, 3244) | under-covered small caps in blind-spot markets | country list, mcap<$400M, pew ADV (0% present on firers) | TS ts_dvol26_usd; AE numAnalystsEps; GH analyst count; NPORT; ETFX | PROXY+REACH | H | A1 B.1 (707 of 3,244). Exceptional: observed coverage 0-1 (AE/GH), no US-fund N-PORT holder, ETF passive share <2%, operating business, ts_dvol26_usd $50k-$2M/week |
| `micro_activist_inflect` (1330, 769) | microcap inflection plus a new capital-allocation board member | mcap<$250M, inflection_now, net cash, EV/EBITDA<=8 (board half not measured) | BO (percentOfClass, typeOfReportingPerson), SECF SC 13D / 8-K 5.02, 8K by date, IST | LEG | H | add the missing half for US filers: new 13D (BO first filing <=12m, percentOfClass>=5, reporting person IA/IN not CO parent) OR 8-K 5.02 director appointment <=12m; fire arch_micro_activist_inflect_core; keep quant-only as _watch |
| `durable_reinvestment` (1360, 1805) | high lindy ROIIC reinvested over a cycle | roic_lindy, n_yrs_positive_roic, roiic_lindy band, asset growth | FG fiveY/tenY*GrowthPerShare per FY; TC; TS ts_maxdd_5y | EXC | M | A1 A.3 price-lindy. Exceptional: FG fiveYRevenueGrowthPerShare and fiveYOperatingCFGrowthPerShare each >= +61% (10%/yr) in every one of the last 5 FY rows (per-share compounding that never broke) |
| `cash_reinvest` (1371, 1264) | cash-confirmed reinvestment returns | cash_roic_lindy, cash_roiic_lindy, asset growth | FG fiveYOperatingCFGrowthPerShare; TC tc_fcf_margin_avg | EXC | L | exceptional: cash ROIIC corroborated by FG per-share OCF 5y growth >= +61% and tc_fcf_pos==tc_fcf_years |
| `roic_inflect` (1382, 1101) | ROIC crossed zero from below, cash confirms | roic_inflection_flag, cash_roic_lindy>0, rev_yoy>0 | FQX fqx_roic_ttm; fmp_dyn_opinc_turned_positive | PROXY | M | confirm the annual cross on TTM: fqx_roic_ttm>0 and fmp_dyn_opinc_turned_positive==1 (a quarterly, dated turn) |
| `cheap_per_roiic` (1393, 4147) | cheap per unit of reinvestment return | EV/EBITDA / (roiic_lindy x100), 92% FMP-filled ROIIC | TC; FG; fmp_st_cash_roiic_lindy | EXC | M | A1 B.1: cash ROIIC>=0.08 and asset 3y CAGR>=5% (1,530 of 4,147) |
| `tangible_value` (1402, 1068) | P/TB<0.7 on real (non-goodwill) assets | p_tb, tangible equity share | HMC (same-date mcap vs balance sheet) | NONE | L | no material gain; optional PIT: book date matched to HMC mcap |
| `lindy_margin` (1435, 6752) | durable HIGH operating margin | op_margin_lindy>=0.10, ebitda_margin_lindy>=0.12, years>=5 | TC tc_min_opm, tc_med_opm, tc_years | EXC | H | core: tc_min_opm>=0.15 over tc_years>=7 (measured 1,275 of 6,290) — the worst year, not the average; watch = current |
| `lindy_fcf` (1446, 9356) | cash-generation durability | n_yrs_positive_fcf/opinc >=4 of 5, years>=5 | TC tc_fcf_pos, tc_fcf_years, tc_fcf_margin_avg; TS ts_maxdd_5y | EXC | H | core: tc_fcf_pos==tc_fcf_years>=7 & tc_fcf_margin_avg>=0.10 (2,125 of 8,683); exceptional: + ts_maxdd_5y>=-0.40 (669) |
| `no_dilution` (1465, 7144) | reinvesting at HIGH returns without tapping equity | shares 3y<=+2%, FCF 4/5, ROIC 4/5, -30% split heuristic | fmp_st_shares_growth_5y; FQX fqx_fcf_ps_g; FG weightedAverageSharesDilutedGrowth per FY; SPL | EXC+PROXY | H | core: roic_lindy>=0.10 (A1). Exceptional: 5y shares<=0 & roic_lindy>=0.15 & fqx_fcf_ps_g>0 (256 of 6,672); SPL reverse-split dates replace the -30% heuristic |
| `capital_returner` (1506, 3879) | material, FCF-funded shareholder yield | total yield 5-30%, FCF>0 | TC tc_uncov_payout_3y; EVT ev_div_raise_streak, ev_div_cut_2y; DIV | EXC | H | core: tc_uncov_payout_3y==0 (1,292 of 3,815); exceptional: + ev_div_raise_streak>=5 and no cut |
| `balance_sheet_return` (1528, 3287) | payout funded by the balance sheet, not FCF | _uncovered (one TTM) / _neg_ev | TC tc_uncov_payout_3y | PROXY | M | A1 B.1: uncovered branch requires tc_uncov_payout_3y>=2 (now zero-call); neg-EV branch moves to negative_ev_value |
| `low_sbc_quality` (1539, 1352) | clean accounting (SBC<2% rev) and profitable | sbc_pct_revenue (EDGAR; missing fails) | cash-flow-statement(-bulk) stockBasedCompensation; fmp_st_sbc_pct_revenue (8.8k) | REACH | M | fill SBC globally from FMP cash-flow stockBasedCompensation / revenue (same reportedCurrency); 3-FY average, not one year |
| `tax_efficient` (1556, 214) | legitimately low tax rate on real profit | effective_tax_rate 3-15%, pretax>0 | income-statement 8FY incomeTaxExpense/incomeBeforeTax (cached) | EXC | L | require ETR in band in >=3 of the last 5 FYs (structure, not a one-year credit) |
| `strong_coverage` (1572, 8385) | debt trivially serviceable | IC>=8 / nde<=0 / net cash>=20%, EBITDA>0 | TC tc_min_ic | EXC | M | A1: demote to strong_coverage_flag or core = tc_min_ic>=8 through the cycle (3,418 of 8,385) or net cash with FCF>0 |
| `diversified_segments` (1596, 235) | 4+ segments, HHI<=0.40 | segment_count, segment_hhi | (segments already wired) | NONE | L | no material gain |
| `concentrated_segments` (1612, 529) | negative flag: one segment dominates | segment_hhi, largest share | (segments already wired) | NONE | L | no material gain |
| `geographic_global` (1620, 666) | 4+ reporting geographies | geographic_region_count | (segments already wired) | NONE | L | no material gain |
| `fastest_segment` (1672, 611) | hidden fast segment engine | segment yoy/margins (FMP quarterly segments) | TR (segment commentary) | NONE | L | no material gain beyond optional transcript corroboration |
| `lindy_growth` (1685, 1486) | durable, accelerating growth | 5y CAGR>=8%, accel, asset growth | FG fiveY/tenYRevenueGrowthPerShare; FQX TTM growth; TS ts_maxdd_5y | EXC | M | A1 A.3 (TTM >= half the 5y CAGR). Exceptional: FG tenYRevenueGrowthPerShare>=+159% (10%/yr per share) and no FY with revenueGrowth<0 |
| `quiet_compounder` (1728, 2172) | proven ROIC, not noticed yet | insider>=10%, ROIC paths, momentum band | TS ts_r52, ts_maxdd_5y; FQX fqx_ebit_ttm_g; AE numAnalystsEps; GH; ETFX/NPORT | EXC+PROXY | H | quiet measured: ts_r52<=0.20 & ts_maxdd_5y>-0.45 & fqx_ebit_ttm_g>=0.10 (291 of 2,111); + observed coverage <=3 |
| `buyback_compounder` (1748, 734) | shrinking count + durable ROIC + clean balance sheet | shares 5y/3y shrink, buyback_yield, roic_lindy>=8% | SPL; HMC (price paid); TC; FG weightedAverageSharesDilutedGrowth | EXC | M | exceptional: shrink in >=4 of 5 FYs (FG) with buybacks larger in FYs the stock was down (counter-cyclical), SPL-verified |
| `owner_operator` (1774, 5505) | skin in the game plus discipline | Yahoo insider>=20% (incl. corporate parents), ROIC/FCF history | KE founder title/yearBorn; BO typeOfReportingPerson IN; IST; SF freeFloat | PROXY+LEG | H | A1: insider 20-60% or revealed alignment; surface controlled_sub_flag. New leg: KE title contains 'founder' OR a 13D/G holder with type IN whose name matches a KE executive; exceptional adds IST net buying |
| `qarp` (1787, 2221) | high ROIIC at a fair price | roiic_lindy>=0.15, multiples, ROIC 4/5 | TS price-lindy; FG consistency; FQX | EXC | M | A1 (1,450 of 2,221 price-lindy core); exceptional: FG 5y per-share EPS and OCF growth >=+61% every FY |
| `reinvest_inflect` (1800, 985) | ROIIC accelerating from a positive base | roiic_acceleration, asset growth | FQX fqx_inc_ebit_margin | LEG | L | confirm on TTM incremental margin>0.2 |
| `double_inflect` (1812, 187) | NOPAT and cash ROIC both crossed zero | roic/cash roic inflection flags | FQX fqx_roic_ttm, fqx_eps_turned | LEG | L | confirm with fqx_roic_ttm>0 |
| `cash_quality` (1824, 2011) | cash ROIC ahead of NOPAT ROIC | cash_roic_lindy - roic_lindy | fq_cash_leads_earnings_flag; TS | EXC | M | A1 A.3 (1,115 of 2,011 price-lindy) |
| `large_cap_quality` (1842, 818) | durable large-cap franchise | mcap>=10bn, margins, FCF, nde | TS ts_maxdd_5y; FG tenY growth; TC | EXC | L | A1 (625 of 818 price-lindy); exceptional: tc_min_opm>=0.20 and FG tenYRevenueGrowthPerShare>=+97% (7%/yr) |
| `capital_light_pivot` (1862, 2234) | asset-light transition, ROIC turning up | rev 3y>=8%, asset < rev growth, roic accel or lindy>10% | EMP employeeCount history (US); FQX fqx_roic_ttm | PROXY+LEG | M | A1: drop roic_lindy>0.10 escape (1,697); new leg: revenue/employee +15% YoY with headcount flat (EMP, US) |
| `bab_low_beta` (1920, 92) | low-beta quality (Frazzini-Pedersen) | Yahoo yf_beta shrunk, pew ADV (8% coverage) | TS ts_beta_1y/3y, ts_beta_1y_rk, ts_dvol26_usd | PROXY+REACH | H | A1: panel beta rank within market; ADV gate -> ts_dvol26_usd>=$0.5M/week (reach: 92 firers today) |
| `bab_becoming` (1931, 1702) | beta compressing | margin/cash de-risking proxy ('no beta series') | TS ts_beta_1y_rk, ts_beta_3y_rk, ts_vol_1y/3y | PROXY | H | measure it: ts_beta_1y_rk <= ts_beta_3y_rk-0.10 or ts_vol_1y<0.85*ts_vol_3y (A1: 517 of 1,702) |
| `bab_multibagger` (1945, 160) | low/declining beta quality that is also cheap/multibagger | yf_beta, ADV, yartseva legs | TS ts_beta_*_rk, ts_dvol26_usd | PROXY | M | same beta/ADV swap as bab_low_beta |
| `lynch_pegy` (1993, 7952) | Lynch PEGY <=1 on durable growth | yf_earnings_growth (single quarter, 38% at the 100% cap) | FQX fqx_ni_ttm_g; FG threeYNetIncomeGrowthPerShare; ESB | PROXY | H | A1 B.1: growth = TTM NI growth 8-50% plus EPS durability (1,836 total); exceptional: FG 3y per-share NI growth also >= +26% (8%/yr) |
| `lynch_evgy` (2003, 6873) | EV/EBITDA per unit growth+yield | 1y EBITDA growth | FG ebitdaGrowth history, threeYRevenueGrowthPerShare; FQX | PROXY | H | A1: denominator = min(EBITDA YoY, 3y rev CAGR) capped 50% (2,457) |
| `midcap_garp` (2117, 1308) | reinvestment quality on a growing earnings stream | ROIIC or proxy, E/P, ebit_g | FQX fqx_ebit_ttm_g | PROXY | M | growth from fqx_ebit_ttm_g (date-matched TTM) |
| `financials_value` (2362, 285) | bank/insurer below book with ROE>=10% | pb, roe, pe | FG bookValueperShareGrowth per FY; DIV | LEG | L | exceptional: book/share compounding >=8%/yr in >=4 of 5 FYs (FG) and no dividend cut (DIV) |
| `net_cash_returner` (2379, 1898) | net cash >=30% of mcap actively returned | net_cash_pct, _returning | TC tc_uncov_payout_3y; DIV | EXC | M | require returns in >=2 of 3 FYs covered by FCF (tc_uncov_payout_3y==0) |
| `sustainable_scaler` (2399, 864) | real small-cap durable growth, self-funded | rev 3y, FCF/share, shares 3y | FQX fqx_fcf_ps_g; FG | PROXY | M | A1: FCF/share from fqx_fcf_ps_g |
| `kullamagie_breakout` (2444, 1158) | liquid momentum leader tightening near highs after an impulse | global _pctrank(roc_6m, momentum_12m), monthly squeeze | TS ts_rs_pct_mkt, ts_tight5, ts_ma10/30, ts_dvol26_usd; EVT ev_react_last; ESB | PROXY+EXC | H | A1: leader within market; exceptional: ts_rs_pct_mkt>=0.95 & ts_tight5<=0.10 & ts_dvol26_usd>=$5M (158 of 1,032). Exclude is_clinical_biotech (92 firers) -> biotech variant |
| `weinstein_stage2` (2463, 4307) | early Stage 2 above a rising 30w MA with RS | momentum_12m, 5y range, rel_pct_52w_high | TS ts_weinstein_stage, ts_ma30_slope, ts_mrs, ts_mrs_13ago, ts_vol_spike4 | PROXY+EXC | H | core: ts_weinstein_stage==2 & ts_mrs_13ago<=0 & ts_vol_spike4>=2 (216 of 2,591); exclude clinical biotech (60) |
| `oneil_canslim` (2492, 334) | CAN SLIM leader | eps streak/rev_yoy for C, roce A, RS via _pctrank | FQX fqx_eps_q_yoy, fqx_eps_accel; TS ts_rs_pct_mkt, ts_dist_hi52, ts_mkt_breadth30; fmp_institutional; SF | PROXY | H | true C accel + RS80 in market + near high: 96 of 307; M = ts_mkt_breadth30>=0.5; I = fmp_inst_new_q0>0; S = SF freeFloat |
| `cundill_deep_value` (2534, 291) | Cundill 6-point checklist | _c1.._c6 (52w high as 'former high') | TS ts_dist_hi260; DIV; IST | PROXY | M | point 2 = ts_dist_hi260<=0.5 exactly; point 5 dividend history from DIV; insider buying as score |
| `wolf_trifecta` (2586, 779) | double-digit growth + margin up + operating leverage, cheap | rev_yoy, oper_lev_any | FQX fqx_inc_ebit_margin, fqx_ebit_ttm_g | PROXY | M | oper_lev = fqx_inc_ebit_margin>=0.20 and fqx_ebit_ttm_g>rev TTM growth |
| `wolf_turnaround` (2602, 731) | loss-maker crossing into the black while growing | annual first-positive flags | FQX fqx_eps_turned; fmp_dyn turned flags | PROXY | M | dated TTM turn replaces annual flags |
| `wolf_value_catalyst` (2626, 732) | growing cash-generative microcap, fortress BS, catalyst | net cash / NCAV / FCF yield | 8K/press releases; ECAL next report | LEG | L | score term: next earnings within 45d (ECAL) or 8-K material event <=90d |
| `wolf_emerging` (2652, 2) | nascent grower with cash discipline | cfo>0, low SBC, multiple band | - | NONE | L | 2 firers; no material gain |
| `wolf_seal` (2662, 2244) | earnings inflection bought on a post-earnings DIP | inflection_print, mom12>=0.10 | EVT ev_react_last, ev_beats_8q; ESB; TS ts_r13/ts_r52 | PROXY+EXC | H | dip measured: ev_react_last<=-0.05 on a beat, ts_r52>=+0.10 (A1: proxy 256 of 2,244) |
| `wolf_compounder` (2677, 234) | sustained accelerating grower at a low multiple | rev_yoy 25-150%, accel, op viable | FQX; ESB beat streak | EXC | M | exceptional: >=4 consecutive beats (ESB) and fqx_eps_accel>0 |
| `liger_asset_backed` (2700, 2211) | neglected net-cash asset play | n_analysts<=4 (missing permissive) | AE numAnalystsEps; GH | PROXY | M | observed coverage (A1) |
| `liger_lagging_inflect` (2715, 2706) | neglected inflection the market has not processed | rev legs, oper_lev_any, flat_or_down/base | TS ts_r52; FQX | PROXY | M | A1: coil lag measured (1,418 of 2,706) |
| `liger_neglected_survivor` (2735, 3849) | neglected, survivable, cheap, early inflection | n_analysts<=3 missing=neglected | AE numAnalystsEps; GH; NPORT; FQX | PROXY | H | A1: observed neglect + shock/first-positive (2,581 of 3,849) |
| `oak_resource_leverage` (2756, 37) | low-cost resource producer, cheap, cash-rich | E/M sector, ev_ebitda<8, margin>=25% | TS ts_dist_hi260; TC tc_min_opm | LEG | L | cost-curve proxy: tc_min_opm>0 through the cycle (survived the trough) |
| `oak_deleveraging` (2770, 837) | heavy FCF paying down moderate debt | fcf_yield>=10%, fq deleveraging | - | NONE | L | already uses fq; no material gain |
| `oak_deep_value` (2798, 668) | crushed price with hard-asset parachute, cash-generative | beaten_down_any(0.50), pb/ncav | TS ts_dist_hi260 | PROXY | L | beaten = ts_dist_hi260<=0.5 |
| `oak_nav_discount` (2836, 51) | NAV vehicle below NAV, paying | pb, div yield | - | NONE | L | no material gain |
| `oak_asset_floor` (2845, 1973) | mcap at/below cash + hard assets | net cash, NCAV | - | NONE | L | no material gain |
| `crisis_asset_backed_recovery` (2884, 623) | crashed asset-heavy name below tangible book | _car_crash, _car_asset_heavy | TS ts_dist_hi260; IST | PROXY | M | crash = ts_dist_hi260<=0.5; insider buying as score |
| `cluseau_realizable_book` (2930, 191) | deep sub-tangible book that is cash and being returned | ptb, realizable share, returning | DIV; TC | LEG | L | returning persistence from DIV / tc |
| `cluseau_buyback_accel` (2944, 12) | buybacks accelerating into a discount | buyback yield, _cl_accel | annual cash-flow 8FY (cached); HMC | PROXY | M | acceleration measured over 3 FYs of repurchases/mcap at the FY-end HMC mcap (3%->5%->7%) |
| `hidden_assets` (3041, 1995) | off-EV assets >=25% of mcap | hidden_pct, net cash | - | NONE | L | no material gain |
| `overdepreciated_assets` (3101, 632) | D&A far above replacement capex | maint capex vs D&A | OE maintenanceCapex | LEG | L | cross-check maintenance capex with FMP owner-earnings maintenanceCapex (already fetched) |
| `understated_earnings` (3133, 1917) | cash well above book earnings, durable | cfo/ni, cash_conversion | - | NONE | L | no material gain |
| `expensed_growth_value` (3155, 217) | fat GM, thin op margin: growth expensed | GM, GP/mcap | FG rdexpenseGrowth, sgaexpensesGrowth | LEG | L | optional: R&D/SG&A growth > revenue growth (still investing) |
| `cash_adjusted_pe` (3190, 1701) | cheap ex-cash on positive earnings | mcap-net cash / NI | - | NONE | L | no material gain |
| `owner_earnings_power` (3219, 1108) | owner earnings >=1.4x NI | OE ratio | - | NONE | L | no material gain (owner-earnings already used) |
| `retained_earnings_discount` (3245, 1358) | retained earnings > market cap | retained earnings, pb | - | NONE | L | no material gain |
| `customer_float` (3265, 1692) | negative working capital / CCC | nwc, ccc, fq op NWC | - | NONE | L | no material gain |
| `capex_famine_harvest` (3290, 1368) | capex far below own history | capex vs 5y avg | - | NONE | L | no material gain |
| `dividend_verified_value` (3308, 153) | fat covered dividend at sub-book | div yield, payout vs NI/FCF | DIV; EVT ev_div_raise_streak, ev_div_cut_2y | LEG | M | exceptional: no cut in 10 years (DIV) and payout covered in each of 3 FYs |
| `tax_verified_earnings` (3328, 162) | earnings verified by a real tax bill | ETR 18-40%, p_e<=12 | income-statement 8FY | EXC | L | ETR in band in >=3 of 5 FYs |
| `cannibal_at_discount` (3348, 676) | buying back stock below book | pb<1, shrink, split guard | SPL; HMC | PROXY | L | SPL replaces the -30% heuristic |
| `self_funded_returner` (3371, 3121) | no-Ponzi financing, cheap | fin CF<0, persistence, FCF>0 | TC | EXC | M | A1: FCF >= financing outflow (1,785 of 3,121) |
| `book_compounder_discount` (3387, 1574) | book compounding >=8%/yr priced below book | EDGAR equity CAGR | FG bookValueperShareGrowth, fiveYShareholdersEquityGrowthPerShare | REACH | M | global reach via FG fiveYShareholdersEquityGrowthPerShare >= +47% (8%/yr) per share |
| `lifo_hidden_reserve` (3407, 7) | LIFO reserve understates book | EDGAR LIFO reserve | - | NONE | L | no material gain (EDGAR-specific) |
| `pension_overfunded` (3419, 9) | pension surplus is a hidden asset | EDGAR funded status | - | NONE | L | no material gain |
| `dta_reversal` (3432, 213) | valuation allowance about to reverse | EDGAR DTA VA | - | NONE | L | no material gain |
| `xr_neg_ev_growth` (3447, 221) | paid to own a growing profitable business | cash>=EV, rev_yoy or streak | FQX TTM growth | LEG | L | use TTM growth (date-matched) as the growth lens |
| `xr_triple_floor` (3465, 139) | net cash + earnings + paid dividend, growing | net cash, ni, dividend_yield | DIV | LEG | L | dividend PAID in each of the last 3 FYs (DIV), not a TTM yield |
| `xr_floor_inflection` (3487, 579) | hard floor as inflection appears on a beaten tape | _xr_floor, _xr_inflect, beaten_down_any(0.30) | TS; FQX fqx_eps_turned | PROXY | L | beaten via ts_dist_hi52/hi260; inflection dated on TTM |
| `xr_quality_crisis` (3515, 2676) | multi-year quality at a crisis price | oe/ni averages, 5y range | TC; TS ts_dist_hi260; FQX | EXC | H | A1: >=2 multi-year lenses + ts_dist_hi260<=0.6 + TTM revenue >= -10% (527 of 2,676); exceptional adds tc_min_opm>0 (never lost money) |
| `xr_forensic_floor_growth` (3534, 839) | invisible floor under a grower | hidden floor, rev_yoy | FQX TTM growth | LEG | L | TTM growth confirmation |
| `xr_forensic_multiple_gap` (3551, 396) | headline P/E vs forensic OE multiple | OE best vs mcap | - | NONE | L | no material gain |
| `xr_harvest_distribution` (3573, 250) | controlled harvest paid out below book | maint capex vs D&A, payout | OE maintenanceCapex; DIV | LEG | L | payout persistence from DIV |
| `xr_paydown_yield` (3589, 826) | financing line proves a big paydown | financing CF/mcap, nde | fq_netdebt_change_pct_assets | PROXY | L | require net debt actually falling (fq) not just financing outflow |
| `xr_clean_net_net` (3605, 308) | NCAV covers price, earning and paying | ncav, ni_avg, payout | DIV | NONE | L | no material gain |
| `xr_compounding_deployer` (3621, 466) | high ROIIC self-funded deployment | roiic_lindy, financing<=0, streak | FG; TS | EXC | L | exceptional: FG per-share OCF 5y >=+61% every FY |
| `xr_float_compounding` (3696, 369) | real customer float compounding | deferred rev / NWC, cfo/ni | - | NONE | L | no material gain |
| `xr_bigbath_rebound` (3717, 547) | non-cash bath pollutes trailing line | normalized EBITDA vs TTM, cfo | TS; FQX | LEG | L | rebound evidence: TTM EBIT re-growing (fqx) |
| `xr_depreciation_cliff` (3735, 22) | D&A about to roll off | D&A/PPE, capex | - | NONE | L | no material gain |
| `xr_wc_normalization` (3751, 350) | WC glut crushed FCF, will snap back | fcf yield, cash_conversion | - | NONE | L | no material gain (fq CCC wired) |
| `xr_amortization_mask` (3775, 96) | acquired-intangible amortization masks EPS | goodwill share, OE/NI | - | NONE | L | no material gain |
| `xr_cannibal_below_cash` (3795, 80) | buyback below net cash | net cash>=mcap, buyback | SPL | PROXY | L | SPL guard |
| `xr_double_trough` (3830, 328) | cheap on mid-cycle at a trough, fortress | pct_off_52w_high, 5y range, mid-cycle | TS ts_dist_hi260; TC tc_med_opm | PROXY | M | trough price = ts_dist_hi260<=0.5; trough earnings vs tc_med_opm |
| `xr_forced_seller` (3849, 255) | seller-driven collapse of a growing business | price_yoy<=-0.40, rev growth, no dilution | TS ts_r52; EVT ev_sp500_removed_12m; IDX nasdaq/dow removals; fmp_inst_own_chg_q0; ETFX | PROXY+LEG | H | ts_r52<=-0.40 (102 of 239 survive); exceptional: a NAMED forced seller (index removal <=12m, 13F ownership -5pp, or ETF passive share drop) |
| `xr_leverage_detonation` (3866, 60) | breakeven crossing with high drop-through | incremental_ebitda_margin (annual), first-positive | FQX fqx_inc_ebit_margin, fqx_eps_turned | PROXY | M | drop-through on TTM (fqx_inc_ebit_margin>=0.35) |
| `xr_baron_compounder` (3890, 744) | founder-led decade-length growth, reinvesting | insider>=10%, growth duration | KE founder title; FG tenYRevenueGrowthPerShare; BO | LEG | M | founder leg from KE; decade duration from FG ten-year per-share revenue >= +159% |
| `xr_insider_capitulation` (3915, 67) | insiders cluster-buy their own crash | insider_cluster_buy_flag (Form 4), beaten_down_any(0.40) | IST totalPurchases per quarter; TS ts_dist_hi52 | PROXY | M | PIT quarterly buys (IST) in the crash quarter; crash from TS (US only) |
| `xr_reusable_assembler` (3943, 377) | incremental margins above average on a built substrate | incremental_ebitda_margin | FQX fqx_inc_ebit_margin | PROXY | M | TTM incremental margin replaces annual |
| `xr_asset_owner_catalyst` (3973, 906) | asset below value + owner + catalyst in motion | insider>=15%, _av, _cat | KE; BO; EVT; 8K | LEG | M | owner verified by KE founder / BO individual holder; catalyst from EVT dates |
| `xr_pre_scale_margin` (4004, 167) | fat gross margin not yet in op line | GM, op margin gap | TR ('operating leverage', 'scale'); FQX | LEG | L | optional transcript leg |
| `xr_latent_inflection_floor` (4042, 623) | improving toward positive under a floor | _improving_lat, floor | FQX trends | LEG | L | improvement measured on TTM |
| `xr_latent_bath_floor` (4065, 587) | depressed line with a hard floor | normalized EBITDA, floor | - | NONE | L | no material gain |
| `xr_cyclical_trough` (4088, 522) | cyclical at asset discount below mid-cycle | sector set, pb<1, normalized | quarterly panel asset intensity; TC tc_med_opm | PROXY | M | A1: measured asset-heavy replaces sector set; trough vs tc_med_opm |
| `xr_nol_shield` (4125, 21) | loss deficit shielding new profits | retained deficit, NI>0, ETR | - | NONE | L | no material gain |
| `xr_growth_capex_masked` (4164, 16) | growth capex masks FCF | capex vs D&A, Greenwald split | OE growthCapex/maintenanceCapex | REACH | M | use FMP owner-earnings growthCapex globally as the second lens |
| `xr_look_through_value` (4185, 17) | associate stakes >=30% of mcap | assoc pct | - | NONE | L | no material gain |
| `xr_cannibal_below_tbook` (4201, 674) | buyback below tangible book | ptb<1, buyback | SPL | PROXY | L | SPL guard |
| `xr_oneoff_loss_mask` (4223, 85) | cash-gushing business reporting a GAAP loss | NI<0, EBITDA margin | - | NONE | L | no material gain |
| `xr_monetization_trifecta` (4247, 5) | net cash + NOL + inflection | NOL, net cash | - | NONE | L | no material gain |
| `xr_contracted_backlog` (4266, 105) | RPO >= 1 yr of revenue, priced on trailing | EDGAR RPO | TR (backlog, RPO, book-to-bill) | REACH | M | transcript-extracted backlog for non-US filers (targeted pulls) |
| `xr_hidden_segment_compounder` (4292, 39) | fast profitable segment masked | segments | - | NONE | L | no material gain |
| `xr_segment_justifies_whole` (4318, 73) | best segment covers EV | segments | - | NONE | L | no material gain |
| `xr_margin_mixshift` (4341, 82) | richer segment gaining share | segments | - | NONE | L | no material gain |
| `xr_gross_margin_lead` (4370, 478) | GM inflects before op margin | gross_margin_delta_yoy | quarterly panel GM; TC tc_min_gm | LEG | L | GM lead measured on 2 consecutive TTM quarters |
| `xr_gaap_profit_crossover` (4393, 1052) | first GAAP profit unlocks mandate/index demand | net_income_first_positive | EVT ev_sp500_member; IDX; ESB; SF freeFloat; HMC | LEG | H | index-candidate leg: US, not a member, sum of last 4 quarters GAAP NI>0 and latest quarter>0 (quarterly panel), mcap in the S&P band (HMC), float>=10% (SF) |
| `xr_deferred_revenue_lead` (4418, 631) | forward book building, priced cheap | deferred revenue ratio | TR | LEG | L | optional transcript bookings leg |
| `xr_cash_tax_advantage` (4466, 278) | cash tax far below book tax, persistent | EDGAR/FMP cash tax | - | NONE | L | no material gain (fq wired) |
| `xr_owned_realestate_value` (4488, 86) | owned property at historical cost | PPE gross, accum dep | - | NONE | L | no material gain |
| `xr_discops_mask` (4531, 103) | discontinued ops mask a profitable core | continuing income | - | NONE | L | no material gain |
| `xr_verified_deleveraging` (4550, 67) | verified debt paydown on levered stub | fq_deleveraging_flag | - | NONE | L | no material gain (already fq) |
| `xr_cash_leads_book` (4569, 546) | cash runs ahead of earnings | fq_cash_leads_earnings_flag | - | NONE | L | no material gain |
| `xr_peer_margin_gap` (4596, 1858) | margin far below peers with self-help | sector median op margin (>=20 peers) | PEERS peers-bulk; PROF industry | PROXY | M | peer median over FMP peer list (or industry) instead of sector (A1 A.6) |
| `xr_investment_remark` (4620, 11) | JV stake remeasured to fair value | EDGAR | - | NONE | L | no material gain |
| `xr_stake_fv_gap` (4639, 4) | disclosed stake FV > carrying value | EDGAR | - | NONE | L | no material gain |
| `xr_lookthrough_earner` (4654, 18) | associate earnings engine | EDGAR | - | NONE | L | no material gain |
| `xr_value_unlock` (4689, 153) | cheap plus a live unlock catalyst | EDGAR language, event flags | BO 13D; EVT ev_sc13d_date, ev_tender_date, ev_merger_proxy_date; 8K | LEG | M | dated catalyst leg: 13D/DEFA14A/8-K 1.01 <=180d |
| `forensic_payout_confirmed` (4816, 7751) | forensic member also returning capital | _forensic_any & _payout_any (tautological) | TC tc_uncov_payout_3y; DIV | EXC | M | A1: non-payout members only, material and FCF-covered payout (3,458 of 7,751) |
| `oak_order_conversion` (4823, 3953) | backlog -> revenue conversion | rev accel + margin expansion (oper_lev_any) | TR backlog/book-to-bill; FQX fqx_inc_ebit_margin | LEG+EXC | M | A1: shock-sized margin + >=10% TTM growth (1,891); forward-book leg from transcripts |
| `weschler_levered_equity` (4896, 673) | levered stub on robust cash yield | robust cash yield, nde | fq_netdebt_change_pct_assets | LEG | L | deleveraging proof from fq |
| `asymmetric_assembly` (4938, 145) | bad headline, better economics, deleveraging | oper_lev_any, heavy debt | fq_deleveraging_flag; FQX | LEG | L | A1 A.4 direct deleveraging proof |
| `levered_inflection` (4964, 378) | levered stub inflecting and deleveraging | oper_lev_any, EBITDA rising | fq_deleveraging_flag; FQX | LEG | L | A1 A.4 |
| `insider_conviction` (4994, 572) | open-market insider buying | Form 4 cluster/officer/10% flags | IST quarterly totalPurchases; BO; TS ts_dist_hi52 | EXC | M | exceptional: buying in >=2 of the last 4 quarters (IST) into ts_dist_hi52<=0.7 (195 of 392) |
| `cheap_sales_scaler` (5022, 2529) | cheap on sales, operating leverage arriving | psg, oper_lev_any | FQX fqx_inc_ebit_margin | PROXY | M | A1: incremental EBIT margin>=0.15 (472) |
| `exceptional_evsg` (5046, 1144) | exceptionally low EV/sales per growth | evsg (1y rev_yoy) | FQX TTM growth | PROXY | M | growth on date-matched TTM |
| `negative_ev_value` (5075, 4682) | paid to own the business | neg EV or pb<0.7 | - | EXC | M | A1: keep only the neg-EV branch (1,420) |
| `growth_algo` (5108, 527) | GP growth + op leverage + shrinking count | rev_yoy, oper_lev, fcf_yoy | FQX fqx_fcf_ps_g; SPL | PROXY | M | A1: FCF/share TTM |
| `asleep_at_wheel` (5171, 3168) | street chronically under-estimates the business | 4-quarter earnings_beat_rate>=0.75 (a base rate) | ESB (10+ years, global, ~13 calls); EVT ev_beats_8q, ev_ignored_beats_2y; earnings revenue surprise | PROXY+REACH | H | A1 core 7/8 beats + surprise + streak; only 367 of 2,445 firers have ev_* today -> ESB closes it. Exceptional: >=7 of 8 beats & >=3 ignored beats (127 on current coverage) |
| `asleep_unrerated` (5234, 1466) | beats and still no re-rating | price_yoy, ev_sales_change_yoy, coil | TS ts_r52; EVT ev_react_beats_4q | PROXY | H | A1: ts_r52; add ev_react_beats_4q<=0 (the market fades the beats) |
| `xr_audited_streak_unrerated` (5267, 2126) | 8+ audited growth quarters, not re-rated | streaks, _no_rerate_au (6 ORed lenses) | TS; EVT | EXC | M | A1: >=2 no-rerate lenses (1,696) |
| `xr_confluence` (5327, 1210) | >=3 XR classes agree | xr family count | - | NONE | L | meta; inherits member changes |
| `templeton_pessimism` (5371, 2050) | cheap vs mid-cycle at maximum pessimism | EV/normalized EBITDA, 5y range | TS ts_dist_hi260 | PROXY | M | ts_dist_hi260<=0.65 (A1: 1,645); exceptional <=0.5 (1,330 of 2,033) plus TC tc_min_opm>0 |
| `tenbagger_path` (5443, 2034) | the 10x arithmetic closes on demonstrated growth | rev_yoy, CAGR, P/S | FQX; FG threeYRevenueGrowthPerShare | EXC | M | A1: no score escape (1,526); per-share growth from FG |
| `tenbagger_credible` (5487, 1323) | 10x path with owner cash and stable count | real owner cash, stable share count | SPL; FG weightedAverageSharesDilutedGrowth | LEG | L | stable count across 3 FYs |
| `evsales_derating` (5535, 1735) | EV/Sales compressing while sales rip | rev_yoy-price_yoy, roc_3_5y | TS ts_r52, ts_r156; FQX; fmp_dyn EV history; HMC | PROXY | H | A1 (852 with TTM growth) |
| `lynch_reward` (5667, 1043) | years of progress not yet paid | monthly/quarterly asym, roc | TS ts_r156/ts_r260; weekly coil | PROXY | M | A1 A.1 |
| `analyst_awakening` (5791, 2102) | perception CHANGING toward bullish while price has only begun | yf rating level, target upside, n_analysts | SENT change lenses; GH; PTN, GN priceWhenPosted (US); EVT ev_pt_lead_flag | PROXY+EXC | H | A1: change-or-turn (933). Exceptional: ev_pt_lead_flag or GN upgrades with priceWhenPosted within 5% of the pre-upgrade price. Exclude clinical biotech (90) |
| `analyst_rerating_confirmed` (5831, 390) | analysts bullish and price confirms at a high | lynch tape 52w high | TS ts_dist_hi52, ts_rs_at_hi, ts_above_ma30 | PROXY | M | A1: abs OR (rel AND above MA30); exclude clinical biotech (30) |
| `institutional_accumulation` (5895, 499) | 13F adding while tape flat/down | 3 quarters symbol-positions-summary | IOH isNew/firstAdded/holdingPeriod; HPS performance3yearRelativeToSP500Percentage, turnover; NPORT (non-US); TS | REACH+EXC | H | US exceptional: >=3 new holders whose HPS 3y relative performance >0 and turnover <0.3 (patient, skilled); non-US reach via NPORT 'change'>0 across >=3 US funds |
| `coiled_base` (6016, 651) | flat 2 years, value accreting, nobody watching | bs_* (local-ccy dvol), fq coil, sent, yf_institution_pct | TS ts_dvol26_usd, ts_weinstein_stage; FQX; ESB; AE numAnalystsEps; NPORT | PROXY+EXC | H | validity on ts_dvol26_usd>=250k (458 of 645). Exceptional: coil_n>=2 & observed coverage<=2 & fqx_eps_pos_share_8>=0.75 & ts_weinstein_stage==1 (33 on current data) |
| `base_ignition` (6020, 116) | first buyers arriving at a coiled base | bs_dvol_trend, bs_updown_vol, rs26, inst/insider, sent | TS ts_vol_spike4, ts_above_ma30, ts_mrs; EVT ev_react_last; IST; BO new 5% holders | EXC+LEG | H | exceptional: ts_vol_spike4>=3 & ts_above_ma30 & ts_mrs>0 (35 of 116) plus a dated trigger (earnings-week reaction >=+8% or new 13D/G <=90d) |
| `biotech_deep_value` (6438, 149) | clinical biotech below cash with runway | net cash pct, runway | fq cash/FCF runway; TR/8K catalyst dates; ECAL | LEG | M | A1 A.6 runway from fq; catalyst proximity as a surfaced score |
| `bottleneck` (6465, 1799) | chokepoint economics, fat non-eroding GM | GM>=0.40, GM delta, roce | TC tc_min_gm; TR pricing/capacity language | EXC | M | tc_min_gm>=0.40 over >=7 FYs (931 of 1,780) |
| `flyover` (6483, 2631) | high quality, low coverage, owner-controlled | n_analysts<=5 (missing passes), insider>=20% | KE founder; BO; AE numAnalystsEps; SF freeFloat | PROXY+LEG | H | A1: insider 20-60% (1,488); observed coverage; founder leg |
| `spinoff_value` (6552, 3) | forced-selling orphan, cheap | EDGAR Form-10 spin_flag (58 names) | EVT ev_spin_filing_date (SECF 10-12B/G); PROF ipoDate; symbol-change; TS; IST | REACH | H | spin anchor = 10-12B/G effective date (US) or new-listing date (PROF ipoDate<=24m with no 424B4 IPO prospectus) ; freshness 3-18m |
| `spinoff_quality` (6571, 2) | high-return franchise cast off at a fair multiple | spin_flag, roce, op margin | same as spinoff_value | REACH | H | same anchor; exceptional adds insider buying at the spinco (IST) in the first 2 quarters |
| `spinoff_asset` (6595, 2) | spun entity below asset backing | spin_flag, asset floor | same as spinoff_value | REACH | M | same anchor |
| `greenblatt_magic` (6609, 763) | high EBIT/EV and high ROC | ev_ebit, roce | FQX fqx_roic_ttm | PROXY | M | ROC from fqx_roic_ttm>=0.20 (485 of 743) |
| `post_reorg` (6697, 2) | fresh-start equity re-rating | EDGAR reorg flag/date | SECF 8-K item 1.03, 'emergence'; TS | LEG | M | firmer emergence date from 8-K 1.03 / EFFECTIVE date |
| `special_situation` (6713, 255) | dated merger/tender/take-private with spread | EDGAR merger/tender | EVT ev_ma_target_date, ev_tender_date, ev_merger_proxy_date; M&A feed (US S-4 based); TS | REACH | H | deal anchor from EVT; spread = offer vs last weekly close; freshness <=9 months |
| `nol_shell` (6728, 66) | NOL >=0.5x mcap on survivable balance sheet | nol_usd (EDGAR) | - | NONE | L | no material gain |

---

Reproducibility: probes `scratchpad/probe2.py`–`probe5.py`; measurements `scratchpad/m2.py`; archetype extraction `scratchpad/extract_arch.py` → `arch_extract.json`; matrix source `scratchpad/matrix_rows.py`.
