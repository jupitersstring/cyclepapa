# SEC EDGAR Quarterly Fundamentals Fetcher — Engineering Spec

## 1. Endpoints

| Purpose | URL |
|---|---|
| Ticker -> CIK map | `https://www.sec.gov/files/company_tickers.json` |
| Company Facts (all XBRL tags for one issuer) | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json` |
| Company Concept (single tag) | `https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/us-gaap/{Tag}.json` |
| Bulk nightly archive | `https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip` |

**Required headers** (per <https://www.sec.gov/os/accessing-edgar-data>):

```
User-Agent: "<Org or Person Name> <contact-email>"
Accept-Encoding: gzip, deflate
Host: data.sec.gov
```

**Rate limit:** 10 requests/sec, per source IP. Exceeding it returns HTTP 403 with a 10-minute IP ban. Use a token-bucket limiter (e.g. `aiolimiter.AsyncLimiter(10, 1)`) and back off on 429/403.

## 2. Ticker -> CIK Mapping

- Download `company_tickers.json` once per day, cache to disk (~1.5 MB).
- Format: `{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}` indexed by row number, not by ticker. Build a `{ticker.upper(): cik_str}` dict on load.
- Zero-pad the CIK to **10 digits** for the URL: `f"CIK{cik:010d}"` -> `CIK0000320193`.
- Coverage gap: only issuers with active stock tickers appear here. For dark/foreign issuers, fall back to `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=10-K`.

## 3. XBRL Tag Selection (US-GAAP namespace)

Filers do not use a single canonical tag; check in order until one returns data.

| Metric | Primary | Alternates |
|---|---|---|
| Revenue | `RevenueFromContractWithCustomerExcludingAssessedTax` (ASC 606, 2018+) | `Revenues`, `SalesRevenueNet`, `SalesRevenueGoodsNet`, `RevenueFromContractWithCustomerIncludingAssessedTax` |
| Operating Income | `OperatingIncomeLoss` | `IncomeLossFromContinuingOperationsBeforeInterestExpenseInterestIncomeIncomeTaxesExtraordinaryItemsNoncontrollingInterestsNet` (rare) |
| Net Income | `NetIncomeLoss` | `ProfitLoss`, `NetIncomeLossAvailableToCommonStockholdersBasic` |
| D&A | `DepreciationDepletionAndAmortization` | `DepreciationAndAmortization`, `Depreciation` + `AmortizationOfIntangibleAssets` (sum), `DepreciationAmortizationAndAccretionNet` |
| Operating Cash Flow | `NetCashProvidedByUsedInOperatingActivities` | `NetCashProvidedByUsedInOperatingActivitiesContinuingOperations` |
| CapEx | `PaymentsToAcquirePropertyPlantAndEquipment` | `PaymentsToAcquireProductiveAssets`, `PaymentsForCapitalImprovements`, `PaymentsToAcquirePropertyPlantAndEquipmentExcludingTenantImprovements` |
| EPS (diluted) | `EarningsPerShareDiluted` | `EarningsPerShareBasic`, `IncomeLossFromContinuingOperationsPerDilutedShare` |

## 4. Parsing Semantics

Path: `facts -> us-gaap -> <tag> -> units -> USD (or "USD/shares" for EPS) -> [records]`.

Each record: `{start, end, val, fy, fp, form, accn, filed, frame?}`.

**Quarterly filter algorithm:**

1. Keep records where `form in {"10-Q","10-Q/A","10-K","10-K/A","20-F","20-F/A","40-F"}`.
2. Compute `period_days = (end - start).days` for flow metrics (income statement, cash flow). Keep rows with `80 <= period_days <= 100` (one quarter). Balance-sheet tags have only `end` — treat as instantaneous.
3. For Q4: 10-K filings carry the **annual** flow value (`period_days ~= 365`). Derive Q4 = annual - (Q1 + Q2 + Q3) for the same `fy`. Some issuers also file a separate Q4 inside the 10-K's segment data; never trust it without checking `period_days`.
4. **Dedup amendments:** group by `end` (period_days bucket), keep `max(filed)`. This automatically resolves 10-Q/A restatements.
5. Index the result by `end` date.

## 5. EBITDA Computation

EDGAR does not have an EBITDA XBRL tag (it is non-GAAP). Build it:

```
ebitda_q = operating_income_q + d_and_a_q
```

If `DepreciationDepletionAndAmortization` is absent, sum `Depreciation` + `AmortizationOfIntangibleAssets` (+ `AmortizationOfDeferredCharges` if present). Caveats:
- Software-heavy companies expense some D&A inside COGS — you will under-count vs. their press-release EBITDA.
- REITs report `DepreciationAndAmortization` differently (property-level); their EBITDA proxy is questionable.
- For roughly 5-10% of small caps neither D&A tag is present at quarterly grain — return NaN, don't fabricate.

## 6. FCF Computation

```
fcf_q = ocf_q - capex_q   # capex is reported positive as a cash outflow
```

CapEx in the cash flow statement is already negative in XBRL records (`val < 0`). Standardize by taking `abs(capex_q)` before subtraction. Verify sign by spot-checking a known issuer (e.g. AAPL Q1 2024).

## 7. Code Sketch

```python
import pandas as pd, requests, time
from functools import lru_cache

UA = "{ua_email}"  # required by SEC
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})

TAGS = {
    "revenue":   ["RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet"],
    "op_income": ["OperatingIncomeLoss"],
    "net_income":["NetIncomeLoss","ProfitLoss"],
    "d_and_a":   ["DepreciationDepletionAndAmortization","DepreciationAndAmortization"],
    "ocf":       ["NetCashProvidedByUsedInOperatingActivities"],
    "capex":     ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "eps":       ["EarningsPerShareDiluted","EarningsPerShareBasic"],
}

@lru_cache(maxsize=1)
def _ticker_map():
    j = SESSION.get("https://www.sec.gov/files/company_tickers.json", timeout=10).json()
    return {r["ticker"].upper(): int(r["cik_str"]) for r in j.values()}

def _quarterly_series(records, unit="USD"):
    # Keep 10-Q/10-K, filter ~quarter-length, dedup amendments by max(filed)
    rows = [r for r in records if r["form"].startswith(("10-Q","10-K"))]
    out = {}
    for r in rows:
        if "start" not in r: continue
        days = (pd.Timestamp(r["end"]) - pd.Timestamp(r["start"])).days
        if not (80 <= days <= 100 or 350 <= days <= 380): continue
        key = (r["end"], days > 200)  # (period_end, is_annual)
        if key not in out or r["filed"] > out[key]["filed"]:
            out[key] = r
    return out  # caller derives Q4 = annual - sum(Q1..Q3)

def fetch_edgar_fundamentals(ticker: str, ua_email: str) -> pd.DataFrame:
    cik = _ticker_map()[ticker.upper()]
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    time.sleep(0.11)  # 10 req/sec ceiling
    facts = SESSION.get(url, timeout=15).json()["facts"]["us-gaap"]

    series = {}
    for metric, candidates in TAGS.items():
        unit = "USD/shares" if metric == "eps" else "USD"
        for tag in candidates:
            if tag in facts and unit in facts[tag]["units"]:
                series[metric] = _quarterly_series(facts[tag]["units"][unit], unit)
                break
        else:
            series[metric] = {}

    # Pivot to DataFrame indexed by quarter-end. Derive Q4 from annual where needed.
    df = _assemble_quarterly_frame(series)            # not shown; ~15 lines
    df["ebitda"] = df["op_income"] + df["d_and_a"]
    df["fcf"]    = df["ocf"] - df["capex"].abs()
    return df[["revenue","op_income","d_and_a","ebitda","ocf","capex","fcf","net_income","eps"]]
```

For thousands of tickers, swap `requests` for `httpx.AsyncClient` + `aiolimiter` and parallelize at 10 req/sec.

## 8. Top Gotchas

1. **Missing tags.** ~10-15% of small caps don't use the primary revenue tag; you must try all alternates and still expect NaNs. Log which tag matched per ticker.
2. **Fiscal-year mismatch.** Companies with non-Dec year-ends (e.g. AAPL Sep, WMT Jan, ORCL May) have `fp=Q1` corresponding to different calendar quarters. Always index by `end` date, never by `fy`/`fp`.
3. **Restatements / amendments.** 10-Q/A filings repeat the same `end` with different `val`. Always keep `max(filed)` per period. Old extracts will silently disagree with newer ones.
4. **Q4 derivation.** Q4 is not reported as a quarter — only as part of the 10-K annual. Forgetting to subtract Q1+Q2+Q3 yields a 4x Q4 spike.
5. **Segment / parent-only confusion.** Some records carry a `frame` like `CY2023Q1USD` (consolidated) vs. dimensional rollups (segment, geography). The Company Facts endpoint generally exposes only consolidated values, but a few filers tag segment data into the same concept — sanity-check totals against revenue rank.
6. **Sign conventions.** CapEx, dividends paid, share repurchases are negative in XBRL but reported positive in press releases. Standardize with `abs()` for CapEx in FCF.
7. **No XBRL at all.** Issuers under ~$75M public float can file in paper or non-XBRL form (very small caps, ADR Form 6-K filers). The companyfacts endpoint will 404 — handle and skip.
