"""Pull XBRL company-facts from SEC EDGAR for every ticker in the SEC
universe (~10,400 entities) and emit a flat per-ticker fundamentals
CSV mirroring our yartseva-schema columns.

EDGAR provides XBRL-tagged audited filings; this is higher-quality
data than yfinance's parsed statements. Captures:
  - balance sheet: assets, current assets, liabilities, current
    liabilities, equity, goodwill, intangibles, cash, total debt
  - income statement: revenue, op income, net income (annual + TTM)
  - cash flow: CFO, capex, FCF (annual + TTM)
  - meta: shares outstanding (latest), period_end

Plus derived fields specific to multibagger work:
  - tangible_equity = equity - goodwill - intangibles
  - tangible_book_per_share = tangible_equity / shares_outstanding
  - ebitda_proxy = op_income + (capex / 4)  (D&A proxy when D&A row missing)
  - fcf_yield (filled later when price + shares are joined)

API:
  https://www.sec.gov/files/company_tickers.json     - ticker map
  https://data.sec.gov/api/xbrl/companyfacts/CIK########.json - facts

SEC's published rate limit is 10 req/sec with a polite-UA requirement.

Output:
  edgar_cache/CIK########.json - raw cache
  edgar_universe_facts.csv     - extracted flat table
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests


HEADERS = {
    "User-Agent": "multibagger-research opensource@multibagger.dev",
    "Accept": "application/json",
}
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
CACHE_DIR = Path("edgar_cache")
CACHE_DIR.mkdir(exist_ok=True)


# --- Concept alias chains -------------------------------------------------
# Try each name in order; use the first that has any observations in USD.
REVENUE_ALIASES = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]
OPINCOME_ALIASES = ["OperatingIncomeLoss"]
NETINCOME_ALIASES = [
    "NetIncomeLoss",
    "ProfitLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
]
ASSETS_ALIASES = ["Assets"]
CURRENT_ASSETS_ALIASES = ["AssetsCurrent"]
LIAB_ALIASES = ["Liabilities"]
CURRENT_LIAB_ALIASES = ["LiabilitiesCurrent"]
EQUITY_ALIASES = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]
GOODWILL_ALIASES = ["Goodwill"]
INTANGIBLE_ALIASES = [
    "IntangibleAssetsNetExcludingGoodwill",
    "FiniteLivedIntangibleAssetsNet",
]
CASH_ALIASES = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "Cash",
]
LT_DEBT_ALIASES = ["LongTermDebtNoncurrent", "LongTermDebt"]
ST_DEBT_ALIASES = ["LongTermDebtCurrent", "ShortTermBorrowings"]
CFO_ALIASES = ["NetCashProvidedByUsedInOperatingActivities"]
CAPEX_ALIASES = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForCapitalImprovements",
    "PaymentsToAcquireProductiveAssets",
]
SHARES_ALIASES = ["CommonStockSharesOutstanding"]
DA_ALIASES = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization",
    "Depreciation",
]
# Capital-allocation concepts (audit June 2026 — direct cash spent on
# dividends + buybacks, instead of inferring from share-count deltas).
DIVIDEND_ALIASES = [
    "PaymentsOfDividendsCommonStock",
    "PaymentsOfDividends",
    "PaymentsOfDividendsMinorityInterest",
]
BUYBACK_ALIASES = [
    "PaymentsForRepurchaseOfCommonStock",
    "PaymentsForRepurchaseOfEquity",
    "TreasuryStockValueAcquiredCostMethod",
]
SBC_ALIASES = [
    "ShareBasedCompensation",
    "AllocatedShareBasedCompensationExpense",
]
TAX_EXPENSE_ALIASES = ["IncomeTaxExpenseBenefit"]
PRETAX_INCOME_ALIASES = [
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
]
RETAINED_EARNINGS_ALIASES = ["RetainedEarningsAccumulatedDeficit"]
EPS_BASIC_ALIASES = ["EarningsPerShareBasic"]
EPS_DILUTED_ALIASES = ["EarningsPerShareDiluted"]
PPE_NET_ALIASES = [
    "PropertyPlantAndEquipmentNet",
    "PropertyPlantAndEquipmentNetOfDepreciation",
]
INTEREST_PAID_ALIASES = ["InterestPaidNet", "InterestPaid"]
FIN_CF_ALIASES = ["NetCashProvidedByUsedInFinancingActivities"]
INV_CF_ALIASES = ["NetCashProvidedByUsedInInvestingActivities"]


def _safe_get(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def _facts_unit_iter(facts: dict, concept: str, unit: str = "USD"):
    """Yield observations for a concept in the requested unit."""
    info = _safe_get(facts, "us-gaap", concept, "units", unit)
    if not info:
        return []
    return info


def latest_point_value(facts: dict, aliases: list[str], unit: str = "USD"):
    """Pick the most recent observation across alias concepts (point-in-time).

    Used for balance-sheet items where we want the latest snapshot
    regardless of fiscal period."""
    best = None
    for c in aliases:
        for obs in _facts_unit_iter(facts, c, unit=unit):
            end = obs.get("end")
            if not end:
                continue
            if best is None or end > best.get("end", ""):
                best = obs
                best["_concept"] = c
    return best


def latest_annual_value(facts: dict, aliases: list[str], unit: str = "USD"):
    """Pick the most recent FY (annual) observation."""
    best = None
    for c in aliases:
        for obs in _facts_unit_iter(facts, c, unit=unit):
            if obs.get("fp") != "FY":
                continue
            end = obs.get("end")
            if not end:
                continue
            if best is None or end > best.get("end", ""):
                best = obs
                best["_concept"] = c
    return best


def ttm_value(facts: dict, aliases: list[str], unit: str = "USD"):
    """Sum the most recent 4 unique quarter-end observations.

    XBRL flow items (revenue, op-income, net-income, CFO, capex) come
    in fp = Q1/Q2/Q3/Q4 for the trailing quarter (val is the quarter's
    flow) or FY for the full year. We want the rolling 4-quarter sum.
    """
    # Collect observations from any alias; prefer concepts with more data
    obs_pool: list[dict] = []
    for c in aliases:
        for o in _facts_unit_iter(facts, c, unit=unit):
            if o.get("fp") in ("Q1", "Q2", "Q3", "Q4", "FY"):
                obs_pool.append({**o, "_concept": c})
    if not obs_pool:
        return None
    # Dedupe by (end, fp, val) and sort newest first
    seen = set()
    unique = []
    for o in obs_pool:
        key = (o.get("end"), o.get("fp"), o.get("val"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(o)
    unique.sort(key=lambda o: (o.get("end") or "", o.get("fp") or ""), reverse=True)

    # Strategy: pick the latest period end. If it's an FY, return its val
    # directly (already trailing-twelve). If it's a Q quarter, sum the last
    # 4 quarter-end observations whose ends fall within the last 380 days.
    latest = unique[0]
    if latest.get("fp") == "FY":
        return {"val": latest["val"], "end": latest.get("end"),
                "concept": latest.get("_concept"), "kind": "FY"}

    # Quarterly: build 4-quarter trailing sum.
    # Each Q in XBRL companyfacts is a YTD figure with 3-month duration.
    # We need to back into 3-month quarter values: pick the 4 most recent
    # quarter-ends, ensure their durations are ~quarterly, and sum.
    quart_obs = [o for o in unique if o.get("fp") in ("Q1", "Q2", "Q3", "Q4")]
    if not quart_obs:
        return None
    # Filter to quarter-duration only (3 months ~= 90 days).
    def dur_days(o):
        try:
            s = datetime.strptime(o["start"], "%Y-%m-%d")
            e = datetime.strptime(o["end"], "%Y-%m-%d")
            return (e - s).days
        except Exception:
            return None
    q3m = [o for o in quart_obs if (dur_days(o) is not None and 60 <= dur_days(o) <= 100)]
    if len(q3m) >= 4:
        last4 = q3m[:4]
        return {"val": sum(o["val"] for o in last4),
                "end": last4[0].get("end"),
                "concept": last4[0].get("_concept"),
                "kind": "TTM4Q"}
    # Fallback: if duration filter rejected too many, just use first 4
    if len(quart_obs) >= 4:
        last4 = quart_obs[:4]
        return {"val": sum(o["val"] for o in last4),
                "end": last4[0].get("end"),
                "concept": last4[0].get("_concept"),
                "kind": "TTM4Q_loose"}
    return None


def fetch_companyfacts(cik: int) -> dict | None:
    """Fetch and cache companyfacts JSON for one CIK."""
    cache_path = CACHE_DIR / f"CIK{cik:010d}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except json.JSONDecodeError:
            pass
    url = FACTS_URL.format(cik=cik)
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 404:
                # Cache the 404 so we skip on resume
                cache_path.write_text("{}")
                return {}
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            cache_path.write_text(json.dumps(data))
            return data
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout):
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
    return None


def extract_row(ticker: str, cik: int, data: dict) -> dict:
    """Compute a flat row of metrics from a companyfacts payload."""
    facts = data.get("facts") or {}
    row = {
        "symbol": ticker,
        "cik": cik,
        "name": data.get("entityName"),
        "concept_count": len(facts.get("us-gaap") or {}),
    }
    if not facts.get("us-gaap"):
        return row

    # Balance sheet (latest point-in-time)
    def pt(aliases, field, units="USD"):
        obs = latest_point_value(facts, aliases, unit=units)
        if obs:
            row[field] = obs["val"]
            row[field + "_end"] = obs.get("end")
            row[field + "_concept"] = obs.get("_concept")

    pt(ASSETS_ALIASES, "assets")
    pt(CURRENT_ASSETS_ALIASES, "current_assets")
    pt(LIAB_ALIASES, "liabilities")
    pt(CURRENT_LIAB_ALIASES, "current_liab")
    pt(EQUITY_ALIASES, "equity")
    pt(GOODWILL_ALIASES, "goodwill")
    pt(INTANGIBLE_ALIASES, "intangibles")
    pt(CASH_ALIASES, "cash")
    pt(LT_DEBT_ALIASES, "lt_debt")
    pt(ST_DEBT_ALIASES, "st_debt")
    pt(SHARES_ALIASES, "shares_outstanding", units="shares")
    # Capital-allocation balance-sheet point-in-time
    pt(RETAINED_EARNINGS_ALIASES, "retained_earnings")
    pt(PPE_NET_ALIASES, "ppe_net")

    # Flow items: TTM + annual
    def fl(aliases, field):
        ttm = ttm_value(facts, aliases)
        if ttm:
            row[field + "_ttm"] = ttm["val"]
            row[field + "_ttm_end"] = ttm["end"]
            row[field + "_ttm_kind"] = ttm["kind"]
        ann = latest_annual_value(facts, aliases)
        if ann:
            row[field + "_fy"] = ann["val"]
            row[field + "_fy_end"] = ann.get("end")

    fl(REVENUE_ALIASES, "revenue")
    fl(OPINCOME_ALIASES, "opinc")
    fl(NETINCOME_ALIASES, "netinc")
    fl(CFO_ALIASES, "cfo")
    fl(CAPEX_ALIASES, "capex")
    fl(DA_ALIASES, "da")
    # NEW (audit June 2026): capital-allocation cash flows + tax + SBC
    fl(DIVIDEND_ALIASES, "dividends")
    fl(BUYBACK_ALIASES, "buybacks")
    fl(SBC_ALIASES, "sbc")
    fl(TAX_EXPENSE_ALIASES, "tax_expense")
    fl(PRETAX_INCOME_ALIASES, "pretax_income")
    fl(INTEREST_PAID_ALIASES, "interest_paid")
    fl(FIN_CF_ALIASES, "financing_cf")
    fl(INV_CF_ALIASES, "investing_cf")

    # EPS uses a different unit (USD/shares)
    def fl_units(aliases, field, units):
        ttm = ttm_value(facts, aliases, unit=units)
        if ttm:
            row[field + "_ttm"] = ttm["val"]
        ann = latest_annual_value(facts, aliases, unit=units)
        if ann:
            row[field + "_fy"] = ann["val"]

    fl_units(EPS_BASIC_ALIASES, "eps_basic", "USD/shares")
    fl_units(EPS_DILUTED_ALIASES, "eps_diluted", "USD/shares")

    # Derived
    equity = row.get("equity") or 0
    goodwill = row.get("goodwill") or 0
    intangibles = row.get("intangibles") or 0
    row["tangible_equity"] = equity - goodwill - intangibles
    if row.get("shares_outstanding"):
        row["tangible_book_per_share"] = row["tangible_equity"] / row["shares_outstanding"]
    # Total debt
    row["total_debt"] = (row.get("lt_debt") or 0) + (row.get("st_debt") or 0)
    row["net_cash"] = (row.get("cash") or 0) - row["total_debt"]
    # FCF = CFO - capex (capex is reported positive as cash outflow, so subtract)
    if "cfo_ttm" in row and "capex_ttm" in row:
        row["fcf_ttm"] = row["cfo_ttm"] - row["capex_ttm"]
    if "cfo_fy" in row and "capex_fy" in row:
        row["fcf_fy"] = row["cfo_fy"] - row["capex_fy"]
    # EBITDA proxy = op income + D&A
    if "opinc_ttm" in row and "da_ttm" in row:
        row["ebitda_ttm"] = row["opinc_ttm"] + row["da_ttm"]
    if "opinc_fy" in row and "da_fy" in row:
        row["ebitda_fy"] = row["opinc_fy"] + row["da_fy"]
    # Margins (TTM-preferred, FY fallback)
    rev = row.get("revenue_ttm") or row.get("revenue_fy")
    opi = row.get("opinc_ttm") or row.get("opinc_fy")
    ebi = row.get("ebitda_ttm") or row.get("ebitda_fy")
    ni = row.get("netinc_ttm") or row.get("netinc_fy")
    fcf = row.get("fcf_ttm") or row.get("fcf_fy")
    if rev and rev > 0:
        if opi is not None:
            row["op_margin"] = opi / rev
        if ebi is not None:
            row["ebitda_margin"] = ebi / rev
        if ni is not None:
            row["net_margin"] = ni / rev
        if fcf is not None:
            row["fcf_margin"] = fcf / rev
    # ROIC / ROCE (EBIT proxy = opinc)
    invested = equity + row.get("total_debt", 0) - (row.get("cash") or 0)
    if invested and invested > 0 and opi is not None:
        row["roce"] = opi / invested

    # ----- Capital-allocation derived (audit June 2026) -----
    div = row.get("dividends_ttm") or 0
    bb = row.get("buybacks_ttm") or 0
    # Total capital returned to shareholders. Dividends + buybacks are
    # already-paid cash; treat both as positive returns (XBRL reports
    # them as positive outflows in financing activities).
    row["capital_return_ttm"] = div + bb

    # Real effective tax rate (clipped to sensible range).
    tax = row.get("tax_expense_ttm")
    pretax = row.get("pretax_income_ttm")
    if tax is not None and pretax and pretax > 0:
        rate = tax / pretax
        if -0.10 < rate < 0.60:
            row["effective_tax_rate"] = rate

    # SBC as % of revenue — quality of earnings flag
    sbc = row.get("sbc_ttm")
    if sbc is not None and rev and rev > 0:
        row["sbc_pct_revenue"] = sbc / rev

    # SBC-adjusted operating income & ROIC
    if sbc is not None and opi is not None:
        row["cash_ebit_ttm"] = opi - sbc
        if invested and invested > 0:
            # Use real tax rate when available, fall back to 0.25
            t = row.get("effective_tax_rate", 0.25)
            row["roic_after_sbc"] = (row["cash_ebit_ttm"] * (1 - t)) / invested

    # Interest coverage
    ip = row.get("interest_paid_ttm")
    if ip and ip > 0 and opi is not None:
        row["interest_coverage"] = opi / ip

    return row


def load_ticker_map() -> pd.DataFrame:
    cache = Path("sec_company_tickers.json")
    if cache.exists() and (time.time() - cache.stat().st_mtime) < 86400 * 7:
        data = json.loads(cache.read_text())
    else:
        r = requests.get(TICKERS_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        cache.write_text(json.dumps(data))
    rows = [
        {"symbol": v["ticker"].upper(), "cik": int(v["cik_str"]),
         "title": v.get("title", "")}
        for v in data.values()
    ]
    return pd.DataFrame(rows).drop_duplicates("symbol")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0, help="limit tickers (0 = all)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="edgar_universe_facts.csv")
    ap.add_argument("--start-at", type=int, default=0,
                    help="resume from index N (after sorted alpha by symbol)")
    args = ap.parse_args()

    print("loading SEC ticker map...", file=sys.stderr)
    tmap = load_ticker_map().sort_values("symbol").reset_index(drop=True)
    if args.start_at:
        tmap = tmap.iloc[args.start_at:].reset_index(drop=True)
    if args.max > 0:
        tmap = tmap.head(args.max)
    print(f"  {len(tmap):,} tickers to process", file=sys.stderr)

    start = time.time()
    completed = 0
    rows: list[dict] = []
    # Per-thread polite delay so we approach but don't exceed SEC's 10 req/sec
    base_delay = max(0.10, args.workers / 10.0 - 0.05)

    def task(rec):
        time.sleep(base_delay)
        data = fetch_companyfacts(int(rec.cik))
        if data is None:
            return None
        return extract_row(rec.symbol, int(rec.cik), data)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(task, rec): rec for rec in tmap.itertuples(index=False)}
        for fut in as_completed(futures):
            rec = futures[fut]
            try:
                row = fut.result()
            except Exception as e:
                row = {"symbol": rec.symbol, "cik": int(rec.cik), "error": str(e)[:80]}
            if row is not None:
                rows.append(row)
            completed += 1
            if completed % 250 == 0:
                rate = completed / (time.time() - start)
                eta = (len(tmap) - completed) / rate if rate > 0 else 0
                print(f"  {completed:,}/{len(tmap):,} done ({rate:.1f}/s, ETA {eta/60:.1f}m)",
                      file=sys.stderr)
                # Periodic checkpoint
                pd.DataFrame(rows).to_csv(args.out + ".partial", index=False)

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    print(f"\nwrote {args.out}: {len(df):,} rows in {time.time()-start:.0f}s",
          file=sys.stderr)
    # Diagnostic: coverage of key fields
    for c in ["assets", "equity", "goodwill", "intangibles", "revenue_ttm",
              "opinc_ttm", "cfo_ttm", "fcf_ttm", "tangible_equity", "ebitda_margin"]:
        if c in df.columns:
            n = df[c].notna().sum()
            print(f"  {c:30s} {n:,} / {len(df):,} ({100*n/len(df):.1f}%)",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
