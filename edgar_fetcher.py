"""SEC EDGAR quarterly fundamentals fetcher.

Drop-in replacement for the yfinance fetch path that returns 24+ quarters of
historical revenue, EBITDA, FCF, and EPS -- yfinance's 5-7 quarter cap on
quarterly statements is server-side and cannot be worked around.

This module exposes one public function:

    fetch_fundamentals_edgar(cache_dir, ticker, ua) -> dict[str, DataFrame]

Return shape is the same `{income, cashflow, eps_history}` dict that the
main analysis script's `fetch_fundamentals()` produces, with column names
chosen to match the existing `*_FIELDS` lookup constants so `extract_metrics`
needs no changes.

Endpoints (SEC EDGAR):
- Ticker -> CIK:  https://www.sec.gov/files/company_tickers.json (~1.5MB)
- Company facts: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json

Rate limit: 10 req/sec per source IP. Exceeding triggers HTTP 403 + a
10-minute IP ban. We sleep ~0.12s between calls (single-threaded use) for
margin. The User-Agent header is REQUIRED by SEC fair-use policy and must
identify a real person/email.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd
import requests

log = logging.getLogger("earnings_price.edgar")

# --------------------------------------------------------------------------- #
# Tag selection                                                               #
# --------------------------------------------------------------------------- #

# Each metric: candidate XBRL tags in preference order. The first tag that
# yields data wins. Companies inconsistently use these (e.g., revenue is
# `RevenueFromContractWithCustomerExcludingAssessedTax` for ASC-606 era,
# `Revenues` for older filings; many issuers carry both).
TAG_CANDIDATES: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ),
    "op_income": (
        "OperatingIncomeLoss",
    ),
    "net_income": (
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ),
    "d_and_a": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
    ),
    "ocf": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
    ),
    "eps_diluted": (
        "EarningsPerShareDiluted",
        "IncomeLossFromContinuingOperationsPerDilutedShare",
    ),
    "eps_basic": (
        "EarningsPerShareBasic",
        "IncomeLossFromContinuingOperationsPerBasicShare",
    ),
    # Diluted shares outstanding (weighted average over the period). Used to
    # convert dollar revenue/EBITDA/FCF into per-share figures so dilution
    # and buybacks are normalized out. Same denominator EPS uses, so per-
    # share metrics line up cleanly.
    "shares_diluted": (
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfDilutedSharesOutstandingNetOfTreasuryStock",
    ),
    "shares_basic": (
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ),
    # Balance-sheet line for book value per share -> P/B valuation overlay.
    # Common stockholders' equity excludes preferred; falls back to total
    # equity if the cleaner tag is absent.
    "stockholders_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "CommonStockholdersEquity",
    ),
    # Net-net / Graham NCAV inputs: Current Assets minus Total Liabilities.
    "assets_current": (
        "AssetsCurrent",
    ),
    "liabilities_total": (
        "Liabilities",
        "LiabilitiesAndStockholdersEquity",   # rare; only sum of L + equity
    ),
    # For EV / negative-EV cross-check against yfinance info.enterpriseValue.
    "cash_and_equivalents": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "Cash",
    ),
    "short_term_investments": (
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
    ),
    "long_term_debt": (
        "LongTermDebt",
        "LongTermDebtNoncurrent",
    ),
    "short_term_debt": (
        "ShortTermBorrowings",
        "DebtCurrent",
        "LongTermDebtCurrent",
    ),
}

QUARTER_DAYS_RANGE = (80, 100)      # ~one quarter
ANNUAL_DAYS_RANGE = (350, 380)      # ~one fiscal year


# --------------------------------------------------------------------------- #
# Session / ticker map                                                        #
# --------------------------------------------------------------------------- #

_SESSION: Optional[requests.Session] = None
_TICKER_MAP: Optional[dict[str, int]] = None


def _session(ua: str) -> requests.Session:
    """Lazily build a requests.Session with the SEC-required headers."""
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": ua,
            "Accept-Encoding": "gzip, deflate",
        })
        _SESSION = s
    return _SESSION


def _ticker_map(cache_dir: Path, ua: str) -> dict[str, int]:
    """Return {TICKER: CIK} dict, cached to disk for 24h."""
    global _TICKER_MAP
    if _TICKER_MAP is not None:
        return _TICKER_MAP
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / "company_tickers.json"
    stale = (not cache.exists()) or (time.time() - cache.stat().st_mtime > 86400)
    if stale:
        log.info("downloading SEC ticker->CIK map")
        r = _session(ua).get("https://www.sec.gov/files/company_tickers.json", timeout=15)
        r.raise_for_status()
        cache.write_text(r.text)
    raw = json.loads(cache.read_text())
    m: dict[str, int] = {}
    for rec in raw.values():
        tkr = str(rec.get("ticker", "")).upper().strip()
        if tkr:
            m[tkr] = int(rec["cik_str"])
    _TICKER_MAP = m
    return m


# --------------------------------------------------------------------------- #
# Company facts fetch + parse                                                 #
# --------------------------------------------------------------------------- #


def _companyfacts_path(cache_dir: Path, cik: int) -> Path:
    return cache_dir / f"CF_{cik:010d}.json.gz"


def _fetch_companyfacts(cache_dir: Path, cik: int, ua: str, max_age_days: int = 7) -> Optional[dict]:
    """Pull the full company-facts JSON for a CIK; cache to disk as gzipped JSON.

    Returns None on ANY failure -- caller falls back to yfinance. Catches
    generic Exception, not just RequestException, so a malformed JSON or
    socket-level error doesn't crash the worker thread.
    """
    import gzip
    path = _companyfacts_path(cache_dir, cik)
    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_days * 86400:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass  # corrupt cache; refetch
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    time.sleep(0.12)
    try:
        r = _session(ua).get(url, timeout=20)
    except Exception as exc:  # broadened from RequestException for robustness
        log.debug("companyfacts request failed for CIK %d: %s", cik, exc)
        return None
    if r.status_code == 404:
        # Issuers under ~$75M float can be exempt from XBRL filing; legitimately empty.
        return None
    if r.status_code == 403:
        log.warning("EDGAR returned 403 (rate limited) for CIK %d; backing off 30s", cik)
        time.sleep(30)
        return None
    if not r.ok:
        log.debug("companyfacts non-OK %d for CIK %d", r.status_code, cik)
        return None
    try:
        payload = r.json()
    except Exception as exc:
        log.debug("companyfacts JSON parse failed for CIK %d: %s", cik, exc)
        return None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception as exc:
        log.debug("companyfacts cache-write failed for CIK %d: %s", cik, exc)
    return payload


def _instant_records(records: Iterable[dict]) -> dict[pd.Timestamp, dict]:
    """Balance-sheet records: one value per period-end date (point-in-time).

    These records carry only an `end` date (no `start`/duration). Per the
    XBRL spec, they represent the balance as of `end`. Dedup amendments by
    keeping the latest `filed` per `end`.
    """
    out: dict[pd.Timestamp, dict] = {}
    for r in records:
        form = str(r.get("form", ""))
        if not (form.startswith("10-Q") or form.startswith("10-K")):
            continue
        if "end" not in r or "start" in r:
            continue  # skip duration records that found their way into this stream
        try:
            end = pd.Timestamp(r["end"])
        except Exception:
            continue
        prior = out.get(end)
        if prior is None or str(r.get("filed", "")) > str(prior.get("filed", "")):
            out[end] = dict(r)
    return out


def _quarterly_records(records: Iterable[dict]) -> dict[pd.Timestamp, dict]:
    """Filter raw XBRL records to one entry per quarter-end.

    Steps (per the spec):
      1. Only flow-statement records (those with both `start` and `end`).
      2. Keep period lengths in [80, 100] days (quarterly) or [350, 380]
         (annual; used to derive Q4 = annual - Q1+Q2+Q3).
      3. Dedup amendments by `max(filed)` per (period_end, is_annual).

    Returns {pd.Timestamp(period_end): record_dict}.
    Annual records are tagged with record['_is_annual'] = True so the caller
    can derive Q4.
    """
    out: dict[tuple[pd.Timestamp, bool], dict] = {}
    for r in records:
        form = str(r.get("form", ""))
        if not (form.startswith("10-Q") or form.startswith("10-K")):
            continue
        if "start" not in r or "end" not in r:
            continue
        try:
            start = pd.Timestamp(r["start"])
            end = pd.Timestamp(r["end"])
        except Exception:
            continue
        days = (end - start).days
        is_annual = ANNUAL_DAYS_RANGE[0] <= days <= ANNUAL_DAYS_RANGE[1]
        is_quarter = QUARTER_DAYS_RANGE[0] <= days <= QUARTER_DAYS_RANGE[1]
        if not (is_quarter or is_annual):
            continue
        key = (end, is_annual)
        prior = out.get(key)
        if prior is None or str(r.get("filed", "")) > str(prior.get("filed", "")):
            r2 = dict(r)
            r2["_is_annual"] = is_annual
            r2["_end_ts"] = end
            out[key] = r2
    return out


def _select_metric(facts_us_gaap: dict, candidates: tuple[str, ...], unit: str) -> dict:
    """First-non-empty alternate-tag fallback. Returns the quarterly_records dict."""
    for tag in candidates:
        node = facts_us_gaap.get(tag)
        if not node:
            continue
        units = node.get("units", {})
        if unit not in units:
            continue
        recs = _quarterly_records(units[unit])
        if recs:
            return recs
    return {}


def _series_from_records(recs: dict[tuple[pd.Timestamp, bool], dict]) -> tuple[pd.Series, pd.Series]:
    """Split into (quarterly_series, annual_series), both indexed by period_end.

    No Q4 derivation here -- callers can choose to derive it or not.
    """
    q_idx, q_val, a_idx, a_val = [], [], [], []
    for (end_ts, is_annual), r in recs.items():
        v = r.get("val")
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if is_annual:
            a_idx.append(end_ts); a_val.append(v)
        else:
            q_idx.append(end_ts); q_val.append(v)
    qs = pd.Series(q_val, index=pd.DatetimeIndex(q_idx)).sort_index()
    ans = pd.Series(a_val, index=pd.DatetimeIndex(a_idx)).sort_index()
    qs = qs[~qs.index.duplicated(keep="last")]
    ans = ans[~ans.index.duplicated(keep="last")]
    return qs, ans


def _derive_q4(qs: pd.Series, ans: pd.Series) -> pd.Series:
    """For flow metrics, the 10-K carries the annual value but no separate Q4
    record. Derive Q4 = annual - (Q1+Q2+Q3) for each fiscal year-end where we
    have all three prior quarters.
    """
    if qs.empty or ans.empty:
        return qs
    out = qs.copy()
    for year_end, annual_val in ans.items():
        # Find the three prior quarters ending within the same fiscal year.
        candidates = qs[(qs.index <= year_end) & (qs.index > year_end - pd.Timedelta(days=320))]
        if len(candidates) < 3:
            continue
        # Take the latest three before year_end.
        prior_three = candidates.sort_index().iloc[-3:]
        if year_end in prior_three.index:
            continue  # Q4 already directly reported
        derived = annual_val - float(prior_three.sum())
        out.loc[year_end] = derived
    return out.sort_index()


def _assemble_quarterly_frame(facts_us_gaap: dict) -> dict[str, pd.Series]:
    """Pull all wanted metrics into a {metric_name: Series} dict."""
    metrics: dict[str, pd.Series] = {}

    # Balance-sheet (point-in-time / instant) metrics: parsed differently
    # because their records have only `end` not `start`.
    INSTANT_METRICS = {
        "stockholders_equity",
        "assets_current", "liabilities_total",
        "cash_and_equivalents", "short_term_investments",
        "long_term_debt", "short_term_debt",
    }

    for name, candidates in TAG_CANDIDATES.items():
        if name.startswith("eps_"):
            unit = "USD/shares"
        elif name.startswith("shares_"):
            unit = "shares"
        else:
            unit = "USD"

        if name in INSTANT_METRICS:
            # Bypass the flow-metric path; balance-sheet stream.
            recs = {}
            for tag in candidates:
                node = facts_us_gaap.get(tag)
                if not node:
                    continue
                units = node.get("units", {})
                if unit not in units:
                    continue
                inst = _instant_records(units[unit])
                if inst:
                    recs = inst
                    break
            if not recs:
                metrics[name] = pd.Series(dtype=float)
                continue
            idx, vals = [], []
            for end_ts, r in recs.items():
                v = r.get("val")
                if v is None:
                    continue
                try:
                    vals.append(float(v)); idx.append(end_ts)
                except (TypeError, ValueError):
                    continue
            s = pd.Series(vals, index=pd.DatetimeIndex(idx)).sort_index()
            s = s[~s.index.duplicated(keep="last")]
            metrics[name] = s
            continue

        recs = _select_metric(facts_us_gaap, candidates, unit)
        if not recs:
            metrics[name] = pd.Series(dtype=float)
            continue
        qs, ans = _series_from_records(recs)
        if name in ("revenue", "op_income", "net_income", "d_and_a", "ocf", "capex"):
            # Flow metrics: 10-K carries the annual sum, derive Q4 from it.
            qs = _derive_q4(qs, ans)
        # shares_* records are typically weighted-average for the period, so
        # both quarterly and annual values are valid as-is; we don't derive
        # a Q4 for them (would mix avg-period semantics).
        metrics[name] = qs

    return metrics


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #


def fetch_fundamentals_edgar(
    cache_dir: Path,
    ticker: str,
    ua: str,
) -> Optional[dict[str, pd.DataFrame]]:
    """Pull quarterly fundamentals from EDGAR and return in the same shape
    the main script's fetch_fundamentals() returns:

        {
          "income":      DataFrame indexed by quarter-end with columns
                         matching yfinance's income-statement field names
                         (so extract_metrics works unchanged),
          "cashflow":    same, for the cash flow statement,
          "eps_history": DataFrame with single column 'Reported EPS' and
                         quarter-end index.
        }

    Returns None on hard failure (issuer not in SEC map, persistent rate
    limit, etc.). Caller can fall back to yfinance.
    """
    cache_dir = Path(cache_dir)
    tmap = _ticker_map(cache_dir, ua)
    cik = tmap.get(ticker.upper().strip())
    if cik is None:
        log.debug("ticker %s not in SEC ticker map", ticker)
        return None

    payload = _fetch_companyfacts(cache_dir, cik, ua)
    if payload is None:
        return None
    facts = payload.get("facts", {}).get("us-gaap")
    if not facts:
        return None

    series = _assemble_quarterly_frame(facts)

    # EBITDA = OpIncome + D&A. NaN-safe addition; either missing => NaN.
    op_inc = series.get("op_income", pd.Series(dtype=float))
    da = series.get("d_and_a", pd.Series(dtype=float))
    if not op_inc.empty and not da.empty:
        idx = op_inc.index.union(da.index)
        ebitda = op_inc.reindex(idx).add(da.reindex(idx).abs(), fill_value=np.nan)
    else:
        ebitda = pd.Series(dtype=float)

    # FCF = OCF - |CapEx|. CapEx is stored negative in XBRL (cash outflow).
    ocf = series.get("ocf", pd.Series(dtype=float))
    capex = series.get("capex", pd.Series(dtype=float))
    if not ocf.empty and not capex.empty:
        idx = ocf.index.union(capex.index)
        fcf = ocf.reindex(idx) - capex.reindex(idx).abs()
    else:
        fcf = pd.Series(dtype=float)

    # EPS: prefer diluted, fall back to basic. EDGAR EPS is in USD/shares.
    eps = series.get("eps_diluted", pd.Series(dtype=float))
    if eps.empty:
        eps = series.get("eps_basic", pd.Series(dtype=float))

    # Diluted weighted-average shares for per-share normalization downstream.
    shares = series.get("shares_diluted", pd.Series(dtype=float))
    if shares.empty:
        shares = series.get("shares_basic", pd.Series(dtype=float))

    # Build income-statement DataFrame with yfinance-compatible column names
    # (so extract_metrics's *_FIELDS lookups work without modification).
    income_cols: dict[str, pd.Series] = {}
    if not series["revenue"].empty:
        income_cols["Total Revenue"] = series["revenue"]
    if not series["op_income"].empty:
        income_cols["Operating Income"] = series["op_income"]
    if not series["net_income"].empty:
        income_cols["Net Income"] = series["net_income"]
    if not ebitda.empty:
        income_cols["EBITDA"] = ebitda
    if not da.empty:
        income_cols["Depreciation And Amortization"] = da
    if not eps.empty:
        income_cols["Diluted EPS"] = eps
    if not shares.empty:
        # Match yfinance column name so existing DILUTED_SHARES_FIELDS lookup hits.
        income_cols["Diluted Average Shares"] = shares
    # Stockholders' equity (book value) for P/B valuation overlay.
    se = series.get("stockholders_equity", pd.Series(dtype=float))
    if not se.empty:
        income_cols["Stockholders Equity"] = se
    # NCAV / net-net / EV inputs (all balance-sheet, point-in-time).
    for label, key in (
        ("Assets Current",        "assets_current"),
        ("Total Liabilities",     "liabilities_total"),
        ("Cash And Equivalents",  "cash_and_equivalents"),
        ("Short Term Investments","short_term_investments"),
        ("Long Term Debt",        "long_term_debt"),
        ("Short Term Debt",       "short_term_debt"),
    ):
        s = series.get(key, pd.Series(dtype=float))
        if not s.empty:
            income_cols[label] = s

    cashflow_cols: dict[str, pd.Series] = {}
    if not ocf.empty:
        cashflow_cols["Operating Cash Flow"] = ocf
    if not capex.empty:
        cashflow_cols["Capital Expenditure"] = capex
    if not fcf.empty:
        cashflow_cols["Free Cash Flow"] = fcf

    income_df = pd.DataFrame(income_cols).sort_index() if income_cols else pd.DataFrame()
    cashflow_df = pd.DataFrame(cashflow_cols).sort_index() if cashflow_cols else pd.DataFrame()

    eps_hist_df = (
        pd.DataFrame({"Reported EPS": eps}).sort_index() if not eps.empty
        else pd.DataFrame()
    )

    return {"income": income_df, "cashflow": cashflow_df, "eps_history": eps_hist_df}


__all__ = ["fetch_fundamentals_edgar"]
