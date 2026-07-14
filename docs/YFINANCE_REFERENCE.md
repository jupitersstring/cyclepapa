# yfinance Reference (as of June 2026, v1.4.x)

Definitive map of every public endpoint on `yfinance.Ticker` and the related
`yf.*` classes, plus alternatives for data yfinance cannot supply. Compiled
from a 5-angle audit of the `ranaroussi/yfinance` source tree, GitHub issues,
the official docs site, and adjacent libraries.

Use this file when planning any data-fetch work in this repo. Refresh after
any major yfinance version bump.

---

## 1. Financial statements (income / balance sheet / cash flow)

All three statements ultimately call ONE Yahoo endpoint:
```
https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}
```
via `Fundamentals.financials.get_{income|balance_sheet|cash_flow}_time_series(freq=...)`.
`freq` accepts `"yearly"`, `"quarterly"`, `"trailing"`. **No `legacy=` or `proxy=`
parameter exists on any `get_*` method.**

### Endpoint matrix

| Endpoint | Aliases | Calls | freq | TTM? | Returns |
|---|---|---|---|---|---|
| `income_stmt` (prop) | `financials`, `incomestmt` | `get_income_stmt(pretty=True)` | yearly | no | DataFrame, pretty index |
| `quarterly_income_stmt` | `quarterly_financials`, `quarterly_incomestmt` | `get_income_stmt(pretty=True, freq='quarterly')` | quarterly | no | DataFrame |
| `ttm_income_stmt` | `ttm_financials`, `ttm_incomestmt` | `get_income_stmt(pretty=True, freq='trailing')` | trailing | yes (1 col) | Single-column DataFrame |
| `balance_sheet` | `balancesheet` | `get_balance_sheet(pretty=True)` | yearly | — | DataFrame |
| `quarterly_balance_sheet` | `quarterly_balancesheet` | `get_balance_sheet(pretty=True, freq='quarterly')` | quarterly | — | DataFrame |
| (no `ttm_balance_sheet`) | — | — | — | N/A | — |
| `cash_flow` | `cashflow` | `get_cash_flow(pretty=True, freq="yearly")` | yearly | no | DataFrame |
| `quarterly_cash_flow` | `quarterly_cashflow` | `get_cash_flow(pretty=True, freq='quarterly')` | quarterly | no | DataFrame |
| `ttm_cash_flow` | `ttm_cashflow` | `get_cash_flow(pretty=True, freq='trailing')` | trailing | yes | Single-column DataFrame |

Method signatures (all identical pattern):
```python
def get_income_stmt(self, as_dict=False, pretty=False, freq="yearly")
def get_balance_sheet(self, as_dict=False, pretty=False, freq="yearly")
def get_cash_flow(self, as_dict=False, pretty=False, freq="yearly")
```
`get_financials`, `get_incomestmt`, `get_balancesheet`, `get_cashflow` are
thin one-line wrappers.

### Important behavior
- The **property** sets `pretty=True` ("Total Revenue") while
  `get_income_stmt()` defaults to `pretty=False` (`TotalRevenue`). Prefer
  `pretty=False` for stable programmatic keys; `as_dict=True` returns
  JSON-friendly dicts.
- **No "more rows" alternative** — depth is whatever Yahoo serves.
  Typical: ~4 annual periods, ~4–5 quarterly periods. Hard server-side cap.
- **TTM** branches added in v0.2.55 (PR #2321, Feb 2025).
- `Ticker.earnings` and `quarterly_earnings` are **deprecated and return
  None**. Replacement: read Net Income from `income_stmt`.

### Shares outstanding
- **`Ticker.get_shares_full(start=None, end=None)`** — returns `pd.Series`
  indexed by tz-aware DatetimeIndex with share-count values, or `None` on
  failure. Sparse daily (only dates with changes). Defaults: `end=now`,
  `start=now - 548d` (~18 months). Added v0.2.4 (PR #1301).
- **`Ticker.get_shares()`** returns a small recent DataFrame.
- Annual shares history is also embedded in `income_stmt`
  ("Diluted/Basic Average Shares").

### Errors and rate limits (June 2026 state)
- `get_*` methods return **empty DataFrame** when Yahoo returns no rows;
  raise on HTTP errors after the curl_cffi migration.
- `YfRateLimitError` introduced v0.2.52 (#2108); rate-limit detection during
  crumb fetch added v0.2.62 (#2491).
- v1.2.0 switched to **curl_cffi** (browser TLS fingerprint impersonation)
  to defeat Yahoo's anti-bot. v1.4.0 made it optional with a `requests`
  fallback.
- Symptoms: HTTP 401 on crumb fetch (cookie expiry), HTTP 429 under loops.
  yfinance is **unreliable for high-volume polling** — fine for ad-hoc.
  Mitigations: `curl_cffi` session with `impersonate="chrome"`, backoff,
  rotate IPs.

---

## 2. Analyst forecasts and calendar

All on `yfinance.Ticker`. Source: `yfinance/scrapers/analysis.py`.

```python
import yfinance as yf
t = yf.Ticker("AAPL")
```

### Snapshot endpoints (quoteSummary modules)

| Endpoint | Returns | Module | Notes |
|---|---|---|---|
| `t.calendar` | `dict` | `calendarEvents` | Keys: `Dividend Date`, `Ex-Dividend Date`, `Earnings Date` (list), `Earnings High/Low/Average`, `Revenue High/Low/Average`. US-reliable; non-US returns partial. |
| `t.analyst_price_targets` | `dict` | `financialData` | Keys: `current, low, high, mean, median`. Snapshot only — no time series. |
| `t.recommendations` / `t.recommendations_summary` | DataFrame | `recommendationTrend` | Cols: `period, strongBuy, buy, hold, sell, strongSell`. 4 rows (0m / -1m / -2m / -3m). Aliases. |
| `t.upgrades_downgrades` | DataFrame | `upgradeDowngradeHistory` | Index: `GradeDate`. Cols: `Firm, ToGrade, FromGrade, Action`. Raises `YFDataException` when empty. |

### Forward analyst estimates (from `earningsTrend` module)

All return DataFrame indexed by period `[0q, +1q, 0y, +1y]` — current quarter,
next quarter, current year, next year. Accept `as_dict=False` via `get_*()`.

| Endpoint | Cols |
|---|---|
| `t.earnings_estimate` | `numberOfAnalysts, avg, low, high, yearAgoEps, growth` |
| `t.revenue_estimate` | `numberOfAnalysts, avg, low, high, yearAgoRevenue, growth` |
| `t.eps_trend` | `current, 7daysAgo, 30daysAgo, 60daysAgo, 90daysAgo` (analyst mean drift) |
| `t.eps_revisions` | `upLast7days, upLast30days, downLast7days, downLast30days` (revision counts) |

There is **no standalone `t.eps_estimate`** — closest is `earnings_estimate`.

`t.growth_estimates` extends the index with `[+5y, -5y]` and adds columns
`stock, industry, sector, index` (peer comparisons). Added v0.2.50 (#2127).

### Historical earnings

| Endpoint | Returns | Notes |
|---|---|---|
| `t.earnings_history` | DataFrame | Last ~4 quarters. Cols: `epsEstimate, epsActual, epsDifference, surprisePercent`. |
| `t.earnings_dates` | DataFrame | Default 12 rows; `get_earnings_dates(limit=12, offset=0)` (limit cap 100). Cols: `EPS Estimate, Reported EPS, Surprise(%)`. **BUGGY since summer 2025** — see Gotchas. |

### News and options

| Endpoint | Returns | Notes |
|---|---|---|
| `t.news` / `t.get_news(count=10, tab='news')` | list[dict] | `tab ∈ {'news', 'all', 'press releases'}`. POSTs to `/xhr/ncp`. |
| `t.option_chain(date=None, tz=None)` | namedtuple `(calls, puts, underlying)` | `calls`/`puts`: DataFrames (strike, bid, ask, lastPrice, volume, openInterest, impliedVolatility). `t.options` lists expiries. |

---

## 3. Holdings, insider, ownership

Source: `yfinance/scrapers/holders.py`. Backed by quoteSummary modules
(`majorHoldersBreakdown`, `institutionOwnership`, `fundOwnership`,
`insiderHolders`, `netSharePurchaseActivity`, `insiderTransactions`).

| Endpoint | Returns | Notes |
|---|---|---|
| `t.major_holders` | DataFrame | Single col `Value`. Rows: % insiders, % institutions, % float held by inst., # institutions |
| `t.institutional_holders` | DataFrame | Cols: `Date Reported, Holder, pctHeld, Shares, Value`. Top ~10 current. |
| `t.mutualfund_holders` | DataFrame | Same cols. Top ~10. |
| `t.insider_purchases` | DataFrame | "Insider Purchases Last 6m" with shares + trans counts/%. |
| `t.insider_transactions` | DataFrame | Cols: `Shares, Value, URL, Text, Insider, Position, Transaction, Start Date, Ownership`. Rolling list of recent filings. |
| `t.insider_roster_holders` | DataFrame | Cols: `Name, Position, Most Recent Transaction, Latest Transaction Date, Shares Owned Directly/Indirectly, Position Direct Date, URL`. |

**No native 13F time-series.** Yahoo only surfaces latest "Date Reported"
per holder — to build a 13F panel you must snapshot daily yourself.

**Reliability:** US large-caps OK. ADRs/non-US/ETFs frequently return empty
or 404 (#1904). Data corruption reported in #2242 (Jan 2025).

---

## 4. Fast info, history metadata, ESG

### `t.fast_info`
Dict-like `FastInfo` object (replaces deprecated `basic_info`). Keys:
`currency, quoteType, exchange, timezone, shares, marketCap, lastPrice,
previousClose, open, dayHigh, dayLow, regularMarketPreviousClose, lastVolume,
fiftyDayAverage, twoHundredDayAverage, tenDayAverageVolume,
threeMonthAverageVolume, yearHigh, yearLow, yearChange`. Accepts both
camelCase and snake_case. Pulls from `/chart` — faster than `info` but
historically buggy (#1636, #1951).

### `t.history_metadata`
Dict populated after any `history()` call (else triggers a 1d fetch). Keys:
`currency, symbol, exchangeName, fullExchangeName, instrumentType,
firstTradeDate, regularMarketTime, hasPrePostMarketData, gmtoffset, timezone,
exchangeTimezoneName, regularMarketPrice, chartPreviousClose, priceHint,
currentTradingPeriod{pre,regular,post}, tradingPeriods, dataGranularity,
range, validRanges`. `tradingPeriods` is a DataFrame of session start/end
for intraday ranges.

### `t.sustainability`
DataFrame of ESG scores: `totalEsg, environmentScore, socialScore,
governanceScore, highestControversy`, plus peer info. Single column = the
symbol. **Empty DataFrame** if `esgScores` module missing (most non-US,
most ETFs). No other ESG endpoints.

---

## 5. Funds, sectors, industries

### `Ticker.funds_data` / `get_funds_data()` → `FundsData`
ETF/mutual fund only. Raises `WrongSecurityTypeException` on equities.
Source: `yfinance/scrapers/funds.py`. Attributes:
- `description, fund_overview` (dict: categoryName, family, legalType)
- `fund_operations` (DF: expense ratio, turnover, NAV vs Category Avg)
- `asset_classes` (dict: cash/stock/bond/preferred/convertible/other)
- `top_holdings` (DF idx Symbol; cols Name, Holding Percent — typically top 10)
- `equity_holdings` (P/E, P/B, P/S, P/CF, MedMktCap, 3Y EarnGrowth)
- `bond_holdings` (Duration, Maturity, Credit Quality)
- `bond_ratings` (dict)
- `sector_weightings` (dict)

### `yf.Sector(key)` and `yf.Industry(key)`
Source: `yfinance/domain/sector.py`, `industry.py`. Snapshots only.

`Sector` exposes: `key, name, symbol, ticker, overview, top_companies`
(DF), `top_etfs` (dict), `top_mutual_funds` (dict), `industries` (DF: key,
name, symbol, market weight), `research_reports`. `region=` kwarg supports
ISO-2 codes.

`Industry` adds: `sector_key, sector_name, top_performing_companies,
top_growth_companies`.

### `yf.Lookup("query")` → `Lookup`
Methods: `get_all/stock/etf/mutualfund/future/currency/cryptocurrency/index`
plus same-named properties with defaults. `lang/region` hardcoded `en-US`/`US`.

### `yf.screen(query, offset=0, size=25, sortField='ticker', sortAsc=False)`
Source: `yfinance/screener/screener.py`. Max size 250.

`query` is either a predefined string (24 options: `day_gainers`,
`most_actives`, `undervalued_growth_stocks`, `top_etfs_us`,
`top_mutual_funds`, etc.) or an `EquityQuery` / `FundQuery` / `ETFQuery`
expression.

Operators: `EQ, IS-IN, BTWN, GT/LT/GTE/LTE`. Combined via `AND/OR`.
`Query.valid_fields` / `valid_values` enumerate available fields.

```python
q = yf.EquityQuery('and', [
    yf.EquityQuery('is-in', ['exchange', 'NMS', 'NYQ']),
    yf.EquityQuery('lt', ['epsgrowth.lasttwelvemonths', 15]),
])
yf.screen(q, size=50)
```

---

## 6. Segment / business-unit revenue — NOT IN yfinance

**Verdict:** neither `yfinance` nor Yahoo Finance's `quoteSummary` API
exposes business-segment or geographic-segment revenue. The full 33-module
`quote_summary_valid_modules` list in `yfinance/const.py` has nothing
relevant. `yahooquery` (sister library, 37 modules) also lacks it. Even
scraping Yahoo's `/quote/{TICKER}/financials` page yields only consolidated
totals — Yahoo strips segment detail before display.

### Workarounds
1. **SEC EDGAR XBRL** (free, official, US issuers only): segment data is
   tagged under `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`
   with dimensional axes like `srt:ProductOrServiceAxis`,
   `us-gaap:StatementBusinessSegmentsAxis`, `srt:StatementGeographicalAxis`.
   The SEC `companyfacts` JSON API at
   `https://data.sec.gov/api/xbrl/companyfacts/CIK{padded-cik}.json` is
   structured as tag → units → fact and does NOT cleanly surface dimensions
   — you get consolidated totals only.
2. **DERA Financial Statement Data Sets**: SEC's quarterly bulk archives.
   In **December 2024** they added a `segments` column to the NUM file in
   reprocessed archives. The legacy `DIM` file also carries axis/member
   tuples. This is the only bulk source.
3. **Commercial APIs** (mostly paid):
   - Finnhub `/stock/revenue-breakdown` — paid tier mostly
   - FMP `/revenue-product-segmentation` — sits on paid plan; free tier
     250 req/day cap makes backfill impractical
   - Intrinio — $200+/mo Bronze
4. **Unofficial scrapers** of stockanalysis.com (e.g. `stockanalysis-scraper`
   on PyPI, `haskaomni/stockanalysis` on GitHub).

### Recommended Python libraries for segment data
| Library | License | Cost | Segment support | Use |
|---|---|---|---|---|
| **`edgartools`** | MIT | Free | YES — auto-surfaces dimensional facts; `query_facts(dimensions={...})` | Per-filing, latest 10-K/10-Q |
| **`secfsdstools`** | Apache 2.0 | Free | YES — v2 added `segments` column from DERA Dec-2024 reprocess | Bulk backfill across all filers |
| `sec-edgar-api`, `sec-edgar-downloader`, `secedgar` | various | Free | NO | Downloaders only |
| `simfin` free | Apache 2.0 | Free | NO | IS/BS/CF only |
| `financialmodelingprep` free | — | Free tier | Endpoint exists but rate-limited | Spot checks only |

**Reference code** (edgartools):
```python
from edgar import Company
xbrl = Company("AAPL").get_filings(form="10-K").latest().xbrl()
df = xbrl.statements.income_statement().to_dataframe(view="detailed")
# Or direct axis query:
xbrl.facts.query().by_dimension('Segment').to_dataframe()
xbrl.instance.query_facts(
    dimensions={'srt:ProductOrServiceAxis': 'aapl:IPhoneMember'},
    end_date='2023-09-30')
```

**Reference code** (secfsdstools):
```python
from secfsdstools.e_collector.reportcollecting import SingleReportCollector
from secfsdstools.e_presenter.presenting import StandardStatementPresenter

c = SingleReportCollector.get_report_by_adsh(adsh="0000320193-22-000108")
df = c.collect().join().present(StandardStatementPresenter(show_segments=True))
```

---

## 7. Known gotchas / quick lookup

- **Empty DataFrame vs error.** Most `get_*` return empty DF when Yahoo
  returns no rows. HTTP errors raise after the curl_cffi migration.
- **Non-US tickers**: analyst forecasts (`earnings_estimate`, `eps_trend`,
  etc.), insider tables, ESG often empty. Holders/financials better but
  inconsistent.
- **`earnings_dates` is unreliable since summer 2025** (#2566, #2594):
  Yahoo's screener-API endpoint stopped updating; yfinance fell back to
  HTML scraping. Future earnings dates often missing.
- **`calendar`** intermittent KeyError `'Earnings Date'` (#2143, #2200).
- **`Ticker.earnings`** returns `None` since Yahoo removed the underlying
  `earnings` block. Use `income_stmt` instead.
- **`fast_info`**: faster than `info` but historically buggy (#1636, #1951).
  Cross-check critical values against `info`.
- **Rate limits**: high-volume looping over thousands of tickers triggers
  401/429. Use `curl_cffi` session with `impersonate="chrome"`, add
  exponential backoff, rotate IPs if needed.
- **No `freq=` parameter for deeper history**. Yahoo's hard cap is ~4
  annual / ~4–5 quarterly per call.

---

## Source links

- Source repo: <https://github.com/ranaroussi/yfinance>
- Docs: <https://ranaroussi.github.io/yfinance/>
- CHANGELOG: <https://github.com/ranaroussi/yfinance/blob/main/CHANGELOG.rst>
- Issues search: <https://github.com/ranaroussi/yfinance/issues>
- Key files:
  - `yfinance/ticker.py` — all property definitions
  - `yfinance/base.py` — `get_*` methods, `get_shares_full`
  - `yfinance/scrapers/fundamentals.py` — `Financials.get_{income|balance_sheet|cash_flow}_time_series`
  - `yfinance/scrapers/quote.py` — `info`, `fast_info`
  - `yfinance/scrapers/analysis.py` — analyst-forecast endpoints
  - `yfinance/scrapers/holders.py` — institutional / insider tables
  - `yfinance/scrapers/funds.py` — ETF/MF data
  - `yfinance/screener/screener.py` — `yf.screen` + Query classes
  - `yfinance/domain/sector.py`, `domain/industry.py` — `Sector` / `Industry`
  - `yfinance/lookup.py` — `yf.Lookup`
  - `yfinance/const.py` — full quoteSummary module list
