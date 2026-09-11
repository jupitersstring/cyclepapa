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
  - ebitda_ttm = op_income + D&A (same-filing definitional construction)
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
import gzip
import threading
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
MAX_CACHE_AGE_DAYS = 30.0   # facts older than a month are refetched
# COMMITTED consolidated cache (survives container recycles — the raw
# edgar_cache/ dir is gitignored and container-local, which is how the whole
# universe went stale once). Holds ONLY the concepts the extractor reads,
# trimmed to recent observations, with a per-CIK fetch date.
OBS_CACHE_PATH = Path("edgar_obs_cache.json.gz")
OBS_KEEP_YEARS = 7
_obs_cache: dict = {}
_obs_cache_lock = threading.Lock()


def _needed_concepts() -> set:
    out = set()
    for name, val in globals().items():
        if name.endswith("_ALIASES") and isinstance(val, list):
            out.update(v for v in val if isinstance(v, str))
    return out


def trim_facts(facts: dict) -> dict:
    """Keep only needed concepts and recent observations (compact for git).
    Covers BOTH us-gaap and ifrs-full namespaces."""
    keep = _needed_concepts()
    cutoff = (datetime.now().replace(microsecond=0)).strftime("%Y-%m-%d")
    cut_year = int(cutoff[:4]) - OBS_KEEP_YEARS
    out = {}
    for ns in ("us-gaap", "ifrs-full", "dei"):
        gaap = _safe_get(facts, ns) or {}
        slim = {}
        for c, cval in gaap.items():
            if c not in keep or not isinstance(cval, dict):
                continue
            units = cval.get("units") or {}
            slim_units = {}
            for u, obs_list in units.items():
                if not isinstance(obs_list, list):
                    continue
                kept = [{k: o.get(k) for k in ("start", "end", "fp", "val")}
                        for o in obs_list
                        if isinstance(o, dict) and o.get("end")
                        and int(str(o["end"])[:4]) >= cut_year]
                if kept:
                    slim_units[u] = kept
            if slim_units:
                slim[c] = {"units": slim_units}
        if slim:
            out[ns] = slim
    return out


def load_obs_cache():
    global _obs_cache
    if OBS_CACHE_PATH.exists():
        try:
            with gzip.open(OBS_CACHE_PATH, "rt") as fh:
                _obs_cache = json.load(fh)
            print(f"  consolidated obs cache: {len(_obs_cache):,} CIKs",
                  file=sys.stderr)
        except Exception as e:
            print(f"  obs cache unreadable ({e}) — starting empty", file=sys.stderr)
            _obs_cache = {}


def save_obs_cache():
    try:
        # snapshot under the lock: fetch threads mutate the store concurrently
        # and json.dump iterating a live dict raises "dictionary changed size"
        # (caught live at the 2026-09-11 checkpoint).
        with _obs_cache_lock:
            _snap = dict(_obs_cache)
        with gzip.open(OBS_CACHE_PATH, "wt") as fh:
            json.dump(_snap, fh)
        print(f"  wrote {OBS_CACHE_PATH} ({len(_snap):,} CIKs, "
              f"{OBS_CACHE_PATH.stat().st_size/1e6:.1f} MB)", file=sys.stderr)
    except Exception as e:
        print(f"  obs cache write failed: {e}", file=sys.stderr)
CACHE_DIR.mkdir(exist_ok=True)


# --- Concept alias chains -------------------------------------------------
# Try each name in order; use the first that has any observations in USD.
REVENUE_ALIASES = [
    # ifrs-full
    "Revenue", "RevenueFromContractsWithCustomers",

    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]
OPINCOME_ALIASES = ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"]
NETINCOME_ALIASES = [
    # PARENT-ATTRIBUTABLE first (methodology audit): us-gaap ProfitLoss
    # INCLUDES noncontrolling interests — the mcap in P/E's numerator owns
    # only the parent share, so NetIncomeLoss must outrank it.
    "NetIncomeLoss",
    "ProfitLossAttributableToOwnersOfParent",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "ProfitLoss",
]
ASSETS_ALIASES = ["Assets"]
CURRENT_ASSETS_ALIASES = ["AssetsCurrent", "CurrentAssets"]
LIAB_ALIASES = ["Liabilities"]
CURRENT_LIAB_ALIASES = ["LiabilitiesCurrent", "CurrentLiabilities"]
EQUITY_ALIASES = [
    "Equity", "EquityAttributableToOwnersOfParent",

    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]
GOODWILL_ALIASES = ["Goodwill"]
INTANGIBLE_ALIASES = [
    "IntangibleAssetsNetExcludingGoodwill",
    "FiniteLivedIntangibleAssetsNet",
]
CASH_ALIASES = [
    "CashAndCashEquivalents",
    "CashAndCashEquivalentsAtCarryingValue",
    "Cash",
    # restricted-inclusive concept is LAST RESORT only (it is a different
    # measure — ASU 2016-18 restricted-cash rollup)
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
]
# PURE noncurrent concepts only — us-gaap LongTermDebt and ifrs Borrowings
# are TOTALS (current portion INCLUDED); adding an ST bucket on top of them
# double-counted current maturities. Totals live in their own list and are
# used standalone, never summed with ST.
LT_DEBT_ALIASES = ["LongTermDebtNoncurrent", "NoncurrentBorrowings",
                   "FinanceLeaseLiabilityNoncurrent"]
TOTAL_DEBT_ALIASES = ["LongTermDebt", "Borrowings",
                      "DebtLongtermAndShorttermCombinedAmount"]
ST_DEBT_ALIASES = ["LongTermDebtCurrent", "ShortTermBorrowings",
                   "CurrentBorrowings", "DebtCurrent", "NotesPayableCurrent",
                   "CommercialPaper", "LinesOfCreditCurrent",
                   "FinanceLeaseLiabilityCurrent"]
CFO_ALIASES = ["NetCashProvidedByUsedInOperatingActivities",
               "CashFlowsFromUsedInOperatingActivities"]
CAPEX_ALIASES = [
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    "PurchaseOfPropertyPlantAndEquipment",

    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForCapitalImprovements",
    "PaymentsToAcquireProductiveAssets",
]
SHARES_ALIASES = ["CommonStockSharesOutstanding",
                  "NumberOfSharesOutstanding",          # ifrs-full
                  "EntityCommonStockSharesOutstanding"] # dei cover page
DA_ALIASES = [
    "DepreciationAndAmortisationExpense",

    "DepreciationDepletionAndAmortization",
    "DepreciationAndAmortization",
    "Depreciation",
]
# Capital-allocation concepts (audit June 2026 — direct cash spent on
# dividends + buybacks, instead of inferring from share-count deltas).
DIVIDEND_ALIASES = [
    "DividendsPaidClassifiedAsFinancingActivities", "DividendsPaid",
    "PaymentsOfDividendsCommonStock",
    "PaymentsOfDividends",
    # PaymentsOfDividendsMinorityInterest REMOVED — cash to NCI holders of
    # subsidiaries is not a return to this company's shareholders.
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
    "ProfitLossBeforeTax",

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
# interest EXPENSE preferred over cash interest PAID (capitalized/PIK/
# timing gaps make paid understate the true charge and overstate coverage)
INTEREST_PAID_ALIASES = ["InterestExpense", "InterestExpenseNonoperating",
                         "FinanceCosts", "InterestPaidNet", "InterestPaid"]
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
    """Yield observations for a concept in the requested unit.

    Looks in BOTH the us-gaap and ifrs-full namespaces: 20-F foreign private
    issuers (GASS-class) file under ifrs-full and were previously invisible,
    which made their "EDGAR" rows ancient or missing. USD-units-only remains
    the policy — home-currency IFRS filers stay Yahoo-constructed rather than
    risk unit mixing (the NOL lesson).
    """
    info = _safe_get(facts, "us-gaap", concept, "units", unit)
    if info:
        return info
    info = _safe_get(facts, "ifrs-full", concept, "units", unit)
    if info:
        return info
    # dei carries the cover-page share count (the most reliable one)
    info = _safe_get(facts, "dei", concept, "units", unit)
    return info or []


def latest_point_value(facts: dict, aliases: list[str], unit: str = "USD"):
    """FIRST alias with observations wins; newest snapshot WITHIN that
    concept. Pooling across aliases mixed different measures (restricted-
    inclusive cash beating clean cash, total-debt beating noncurrent) —
    the alias order is the documented priority and is now honored."""
    for c in aliases:
        best = None
        for obs in _facts_unit_iter(facts, c, unit=unit):
            end = obs.get("end")
            if not end or obs.get("val") is None:
                continue
            if best is None or end > best.get("end", ""):
                best = obs
        if best is not None:
            best["_concept"] = c
            return best
    return None


def latest_annual_value(facts: dict, aliases: list[str], unit: str = "USD"):
    """Most recent TRUE-annual observation: first alias with one wins, and
    the row must span >= 330 days — a Q4 3-month row tagged fp=FY (or a
    short transition period) must never masquerade as a fiscal year."""
    for c in aliases:
        best = None
        for obs in _facts_unit_iter(facts, c, unit=unit):
            if obs.get("fp") != "FY":
                continue
            end = obs.get("end")
            if not end or obs.get("val") is None:
                continue
            if obs.get("start"):
                try:
                    dur = (datetime.strptime(end, "%Y-%m-%d")
                           - datetime.strptime(obs["start"], "%Y-%m-%d")).days
                    if dur < 330:
                        continue
                except Exception:
                    pass
            if best is None or end > best.get("end", ""):
                best = obs
        if best is not None:
            best["_concept"] = c
            return best
    return None


def ttm_value(facts: dict, aliases: list[str], unit: str = "USD",
              allow_rollfwd: bool = True):
    """Trailing-twelve-month value, built ROBUSTLY (methodology audit 2026-09-11).

    The old implementation summed the 4 most recent 3-month rows with NO
    consecutiveness or recency requirement (its docstring promised a 380-day
    window that was never coded) — when the Q4 3-month row was absent (very
    common in XBRL companyfacts) it silently summed NON-consecutive quarters
    (e.g. Q3'25+Q2'25+Q1'25+Q3'24), double-counting one season and skipping
    another. That, plus a never-expiring cache, was the source of the wild
    EDGAR-vs-Yahoo divergences.

    New construction, in order of preference:
      1. ROLL-FORWARD (standard XBRL method): TTM = FY + R - P, where R is the
         newest flow observation (any duration: 3m quarter, 6m/9m YTD), P is
         the SAME-duration observation ending ~1 year before R, and FY is the
         annual observation ending between P and R. Exact for every fiscal
         calendar; needs no Q4 row.
      2. FOUR CONSECUTIVE 3-month quarters (successive ends 80-100 days apart).
      3. FY directly, when it is the newest period available.
    Returns {"val", "end", "concept", "kind"} or None.
    """
    # SINGLE-CONCEPT construction: F, R and P (and every chained quarter)
    # must come from the SAME concept — pooling let the roll-forward
    # difference e.g. Revenue-excluding-tax against Revenue-including-tax,
    # or parent NetIncomeLoss against NCI-inclusive ProfitLoss, yielding a
    # "TTM" of nothing. Aliases are tried IN ORDER; the first concept that
    # yields a TTM by any strategy wins.
    for _c_try in aliases:
        obs_pool = [{**o, "_concept": _c_try}
                    for o in _facts_unit_iter(facts, _c_try, unit=unit)
                    if o.get("end") and o.get("val") is not None]
        if not obs_pool:
            continue
        _res = _ttm_from_pool(obs_pool, allow_rollfwd)
        if _res is not None:
            return _res
    return None


def _ttm_from_pool(obs_pool: list, allow_rollfwd: bool = True):

    def _d(x):
        try:
            return datetime.strptime(x, "%Y-%m-%d")
        except Exception:
            return None

    seen = set()
    unique = []
    for o in obs_pool:
        key = (o.get("start"), o.get("end"), o.get("val"))
        if key in seen:
            continue
        seen.add(key)
        dur = None
        if o.get("start"):
            ds, de = _d(o["start"]), _d(o["end"])
            if ds and de:
                dur = (de - ds).days
        o["_dur"] = dur
        o["_end_dt"] = _d(o["end"])
        if o["_end_dt"] is not None:
            unique.append(o)
    if not unique:
        return None
    unique.sort(key=lambda o: o["_end_dt"], reverse=True)

    annuals = [o for o in unique if (o.get("fp") == "FY" and (o["_dur"] is None or o["_dur"] >= 330))
               or (o["_dur"] is not None and 330 <= o["_dur"] <= 380)]
    flows = [o for o in unique if o["_dur"] is not None and 60 <= o["_dur"] <= 290]

    # --- 1) roll-forward: TTM = FY + R - P
    # ...but an ANNUAL row NEWER than every flow row IS the freshest TTM
    # (a June-FY 10-K lands with no Q4 flow row; MSFT's Jun-2026 FY must beat
    # a Mar-2026 roll-forward). FY wins when it is the newest period.
    if annuals and flows and annuals[0]["_end_dt"] >= flows[0]["_end_dt"]:
        F = annuals[0]
        return {"val": F["val"], "end": F.get("end"),
                "concept": F.get("_concept"), "kind": "FY"}
    for R in (flows[:3] if allow_rollfwd else []):   # newest few flow rows
        _r_start = _d(R.get("start")) if R.get("start") else None
        for P in flows:
            if P is R or P["_dur"] is None or R["_dur"] is None:
                continue
            gap = (R["_end_dt"] - P["_end_dt"]).days
            if not (330 <= gap <= 395):
                continue
            if abs(P["_dur"] - R["_dur"]) > 20:
                continue
            for F in annuals:
                if not (P["_end_dt"] <= F["_end_dt"] < R["_end_dt"]):
                    continue
                # R must START at the fiscal-year end (the post-FY YTD
                # stub) — a bare Q3 3-month row satisfies every other
                # check yet makes FY + R - P swap current-year H1 for
                # prior-year H1. Small tolerance for 52/53-week calendars.
                if _r_start is not None:
                    _off = (_r_start - F["_end_dt"]).days
                    if not (-7 <= _off <= 21):
                        continue
                return {"val": F["val"] + R["val"] - P["val"],
                        "end": R.get("end"),
                        "concept": R.get("_concept"),
                        "kind": "TTM_rollfwd"}
    # --- 2) four CONSECUTIVE 3-month quarters
    q3m = [o for o in flows if 60 <= (o["_dur"] or 0) <= 100]
    if len(q3m) >= 4:
        chain = [q3m[0]]
        for o in q3m[1:]:
            if len(chain) == 4:
                break
            gap = (chain[-1]["_end_dt"] - o["_end_dt"]).days
            if 80 <= gap <= 100:
                chain.append(o)
            elif gap > 100:
                break                        # a hole in the quarter chain — stop
        if len(chain) == 4:
            return {"val": sum(o["val"] for o in chain),
                    "end": chain[0].get("end"),
                    "concept": chain[0].get("_concept"),
                    "kind": "TTM4Q"}
    # --- 3) FY directly when it is the newest thing we have
    if annuals:
        F = annuals[0]
        newest_flow = flows[0]["_end_dt"] if flows else None
        if newest_flow is None or (newest_flow - F["_end_dt"]).days <= 100:
            return {"val": F["val"], "end": F.get("end"),
                    "concept": F.get("_concept"), "kind": "FY"}
    return None


def fetch_companyfacts(cik: int) -> dict | None:
    """Fetch and cache companyfacts JSON for one CIK."""
    cache_path = CACHE_DIR / f"CIK{cik:010d}.json"
    # L2: consolidated COMMITTED cache (fresh entries only)
    _k = str(cik)
    _ent = _obs_cache.get(_k)
    if _ent and (time.time() - _ent.get("fetched_at", 0)) / 86400.0 <= MAX_CACHE_AGE_DAYS:
        return {"facts": _ent["facts"]}
    gz_path = Path(str(cache_path) + ".gz")
    if gz_path.exists():
        age_days = (time.time() - gz_path.stat().st_mtime) / 86400.0
        if age_days <= MAX_CACHE_AGE_DAYS:
            try:
                with gzip.open(gz_path, "rt") as _gz:
                    data = json.loads(_gz.read())
                with _obs_cache_lock:
                    _obs_cache[_k] = {"fetched_at": gz_path.stat().st_mtime,
                                      "facts": trim_facts(data.get("facts", {}))}
                return data
            except Exception:
                pass
    if cache_path.exists():
        # NEVER-EXPIRING cache was the staleness root cause (Q1-2026 facts
        # served in September). Serve from cache only while fresh.
        age_days = (time.time() - cache_path.stat().st_mtime) / 86400.0
        if age_days <= MAX_CACHE_AGE_DAYS:
            try:
                data = json.loads(cache_path.read_text())
                with _obs_cache_lock:
                    _obs_cache[_k] = {"fetched_at": cache_path.stat().st_mtime,
                                      "facts": trim_facts(data.get("facts", {}))}
                return data
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
            with gzip.open(str(cache_path) + ".gz", "wt") as _gz:
                _gz.write(json.dumps(data))
            with _obs_cache_lock:
                _obs_cache[_k] = {"fetched_at": time.time(),
                                  "facts": trim_facts(data.get("facts", {}))}
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
        "concept_count": (len(facts.get("us-gaap") or {})
                          + len(facts.get("ifrs-full") or {})),
    }
    # BOTH namespaces count — a pure-IFRS 20-F filer (the population the
    # dual-namespace support exists for) was returned EMPTY here and then
    # dropped downstream on concept_count == 0.
    if not (facts.get("us-gaap") or facts.get("ifrs-full")):
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
    pt(TOTAL_DEBT_ALIASES, "total_debt_standalone")
    pt(SHARES_ALIASES, "shares_outstanding", units="shares")
    # Capital-allocation balance-sheet point-in-time
    pt(RETAINED_EARNINGS_ALIASES, "retained_earnings")
    pt(PPE_NET_ALIASES, "ppe_net")

    # ---- MULTI-YEAR AVERAGES (Graham/Templeton smoothing; robustness to
    # single-year accounting quirks). Per-FY series aligned by fiscal year:
    # OE_fy = NI + D&A - capex; averaged over up to the last 5 FYs (>=3
    # required). Also average NI (Graham average earnings) and average FCF.
    def _annual_series(aliases):
        out = {}
        for c in aliases:
            for o in _facts_unit_iter(facts, c, unit="USD"):
                if o.get("val") is None or not o.get("end"):
                    continue
                dur = None
                if o.get("start"):
                    try:
                        dur = (datetime.strptime(o["end"], "%Y-%m-%d")
                               - datetime.strptime(o["start"], "%Y-%m-%d")).days
                    except Exception:
                        dur = None
                if (o.get("fp") == "FY" and (dur is None or dur >= 330)) or                         (dur is not None and 330 <= dur <= 380):
                    y = o["end"][:4]
                    if y not in out:          # newest wins per year
                        out[y] = float(o["val"])
        return out

    def _avg_over(series_list, n=5, min_years=3):
        """Average the SUM of aligned per-year values over the last n years."""
        if not series_list:
            return None, 0
        common = set(series_list[0])
        for sd in series_list[1:]:
            common &= set(sd)
        years = sorted(common, reverse=True)[:n]
        if len(years) < min_years:
            return None, len(years)
        vals = [sum(sd[y] for sd in series_list) for y in years]
        return sum(vals) / len(vals), len(years)

    _ni_s = _annual_series(NETINCOME_ALIASES)
    _da_s = _annual_series(DA_ALIASES)
    _cx_s = _annual_series(CAPEX_ALIASES)
    _cfo_s = _annual_series(CFO_ALIASES)
    _neg_cx = {y: -v for y, v in _cx_s.items()}
    _oe_avg, _oe_n = _avg_over([_ni_s, _da_s, _neg_cx])
    if _oe_avg is not None:
        row["oe_avg"] = _oe_avg
        row["oe_avg_years"] = _oe_n
    _ni_avg, _ni_n = _avg_over([_ni_s])
    if _ni_avg is not None:
        row["ni_avg"] = _ni_avg
        row["ni_avg_years"] = _ni_n
    _fcf_avg, _fcf_n = _avg_over([_cfo_s, _neg_cx])
    if _fcf_avg is not None:
        row["fcf_avg"] = _fcf_avg
        row["fcf_avg_years"] = _fcf_n
    _cx_avg, _cx_n = _avg_over([_cx_s])
    if _cx_avg is not None:
        row["capex_avg"] = _cx_avg
        row["capex_avg_years"] = _cx_n
    # audited book-value compounding (F14): equity 5y CAGR from FY series
    _eq_s = _annual_series(EQUITY_ALIASES)
    if len(_eq_s) >= 3:
        _yrs_eq = sorted(_eq_s, reverse=True)[:5]
        _new_e, _old_e = _eq_s[_yrs_eq[0]], _eq_s[_yrs_eq[-1]]
        _span = int(_yrs_eq[0]) - int(_yrs_eq[-1])
        if _new_e > 0 and _old_e > 0 and _span >= 2:
            row["equity_cagr_5y"] = (_new_e / _old_e) ** (1.0 / _span) - 1.0
            row["equity_cagr_years"] = _span

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
        # per-share series are NOT additive flows: FY-EPS + Q-EPS - Q-EPS
        # divides by three different weighted share counts. Only the
        # 4-consecutive-quarter sum (conventional approximation) or the FY
        # itself is admissible.
        ttm = ttm_value(facts, aliases, unit=units, allow_rollfwd=False)
        if ttm:
            row[field + "_ttm"] = ttm["val"]
        ann = latest_annual_value(facts, aliases, unit=units)
        if ann:
            row[field + "_fy"] = ann["val"]

    fl_units(EPS_BASIC_ALIASES, "eps_basic", "USD/shares")
    fl_units(EPS_DILUTED_ALIASES, "eps_diluted", "USD/shares")

    # Derived — a value is only computed from OBSERVED constituents; a
    # missing goodwill/intangibles concept legitimately means none, but a
    # missing EQUITY concept must never fabricate tangible_equity = 0.
    equity = row.get("equity")
    goodwill = row.get("goodwill") or 0
    intangibles = row.get("intangibles") or 0
    if equity is not None:
        row["tangible_equity"] = equity - goodwill - intangibles
        if row.get("shares_outstanding"):
            row["tangible_book_per_share"] = row["tangible_equity"] / row["shares_outstanding"]
    # Total debt: the pure-noncurrent + current split when observed; else a
    # STANDALONE total concept (LongTermDebt/Borrowings — current portion
    # already included, never summed with ST). When NO debt concept was
    # observed the field stays ABSENT — "we saw no debt tag" is not "zero
    # debt" (the revolver-under-unseen-alias lesson).
    if row.get("lt_debt") is not None or row.get("st_debt") is not None:
        row["total_debt"] = (row.get("lt_debt") or 0) + (row.get("st_debt") or 0)
    elif row.get("total_debt_standalone") is not None:
        row["total_debt"] = row["total_debt_standalone"]
    if row.get("cash") is not None and row.get("total_debt") is not None:
        row["net_cash"] = row["cash"] - row["total_debt"]
    # WINDOW-MATCHED pairs: a subtraction or ratio of two TTMs is only
    # meaningful when both windows end together (one component a quarter
    # fresher, or one an FY-fallback, silently mixes periods).
    def _ends_match(a, b, days=14):
        ea, eb = row.get(a), row.get(b)
        if not ea or not eb:
            return True          # missing end metadata: keep old behavior
        try:
            return abs((datetime.strptime(str(ea)[:10], "%Y-%m-%d")
                        - datetime.strptime(str(eb)[:10], "%Y-%m-%d")).days) <= days
        except Exception:
            return True
    # FCF = CFO - capex (capex reported as positive outflow)
    if "cfo_ttm" in row and "capex_ttm" in row             and _ends_match("cfo_ttm_end", "capex_ttm_end"):
        row["fcf_ttm"] = row["cfo_ttm"] - row["capex_ttm"]
    if "cfo_fy" in row and "capex_fy" in row:
        row["fcf_fy"] = row["cfo_fy"] - row["capex_fy"]
    # EBITDA = op income + D&A (same-filing definitional construction)
    if "opinc_ttm" in row and "da_ttm" in row             and _ends_match("opinc_ttm_end", "da_ttm_end"):
        row["ebitda_ttm"] = row["opinc_ttm"] + row["da_ttm"]
    if "opinc_fy" in row and "da_fy" in row:
        row["ebitda_fy"] = row["opinc_fy"] + row["da_fy"]
    # Margins: numerator and denominator on the SAME cadence — both TTM
    # (ends matching) or both FY; never a TTM numerator over an FY
    # denominator.
    def _pair(num_ttm, num_end, num_fy, den_ttm_ok):
        if row.get(num_ttm) is not None and den_ttm_ok                 and _ends_match(num_end, "revenue_ttm_end"):
            return row[num_ttm], row.get("revenue_ttm")
        if row.get(num_fy) is not None and row.get("revenue_fy") is not None:
            return row[num_fy], row.get("revenue_fy")
        return None, None
    _has_rev_ttm = row.get("revenue_ttm") is not None
    rev = row.get("revenue_ttm") if _has_rev_ttm else row.get("revenue_fy")
    opi = row.get("opinc_ttm") if _has_rev_ttm and row.get("opinc_ttm") is not None else row.get("opinc_fy")
    ebi = row.get("ebitda_ttm") if _has_rev_ttm and row.get("ebitda_ttm") is not None else row.get("ebitda_fy")
    ni = row.get("netinc_ttm") if _has_rev_ttm and row.get("netinc_ttm") is not None else row.get("netinc_fy")
    fcf = row.get("fcf_ttm") if _has_rev_ttm and row.get("fcf_ttm") is not None else row.get("fcf_fy")
    for _mk, _nt, _ne, _nf in (("op_margin", "opinc_ttm", "opinc_ttm_end", "opinc_fy"),
                               ("ebitda_margin", "ebitda_ttm", "opinc_ttm_end", "ebitda_fy"),
                               ("net_margin", "netinc_ttm", "netinc_ttm_end", "netinc_fy"),
                               ("fcf_margin", "fcf_ttm", "cfo_ttm_end", "fcf_fy")):
        _n, _r = _pair(_nt, _ne, _nf)
        if _n is not None and _r and _r > 0:
            row[_mk] = _n / _r
    # ROIC / ROCE (EBIT proxy = opinc) — requires an OBSERVED equity level
    # (equity silently defaulted to 0 made invested = debt - cash and
    # printed wildly inflated returns).
    invested = None
    if equity is not None:
        invested = equity + (row.get("total_debt") or 0) - (row.get("cash") or 0)
    if invested and invested > 0 and opi is not None:
        row["roce"] = opi / invested

    # ----- Capital-allocation derived (audit June 2026) -----
    div = row.get("dividends_ttm")
    bb = row.get("buybacks_ttm")
    # Total capital returned to shareholders (positive outflow magnitudes).
    # Written ONLY when at least one payout concept was observed — "no
    # concept found" must stay distinguishable from "returned nothing".
    if div is not None or bb is not None:
        row["capital_return_ttm"] = (div or 0) + (bb or 0)

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

    # SBC-adjusted operating income & ROIC. A company with NO SBC concept
    # is treated as sbc = 0 (flagged via sbc_observed) — requiring the
    # concept excluded every non-SBC reporter from ROIC screens and biased
    # them toward tech names (audit L3).
    _sbc_eff = sbc if sbc is not None else (0.0 if opi is not None else None)
    row["sbc_observed"] = int(sbc is not None)
    if _sbc_eff is not None and opi is not None:
        row["cash_ebit_ttm"] = opi - _sbc_eff
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

    load_obs_cache()
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
                save_obs_cache()   # crash-safe L2 checkpoint
    save_obs_cache()

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
