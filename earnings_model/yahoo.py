"""Proxy-compatible Yahoo Finance client over plain urllib.

The agent egress proxy resets curl_cffi's impersonated-Chrome TLS handshake
(curl error 35), which kills yfinance's normal transport. Yahoo's public JSON
API, however, is reachable through the proxy with a standard urllib request +
a warmed cookie/crumb. This module talks to that API directly:

* :meth:`YahooClient.batch_quotes` — the ``v7/finance/quote`` endpoint takes up
  to ~100 symbols per request, so we can PRE-SCREEN a widened candidate list for
  liveness (has a marketCap) in one call per 100 names, instead of paying the
  ~50s-per-dead-ticker tax of a full fetch on delisted symbols.
* :func:`fetch_raw` — ``v10/finance/quoteSummary`` + ``v8/finance/chart`` rebuild
  the exact ``raw`` dict shape :func:`earnings_model.fundamentals.fetch_raw`
  produces, so the rest of the pipeline is unchanged.

This is a legitimate workaround: same public endpoints yfinance uses, same
rate-limit discipline (paced, cookie/crumb-warmed) — just a transport the proxy
doesn't reset. No IP masking.
"""
from __future__ import annotations

import http.cookiejar
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd

from . import config, fundamentals

NaN = float("nan")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_HOSTS = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")


class YahooClient:
    """Cookie/crumb-warmed urllib session for the Yahoo JSON API."""

    def __init__(self):
        self._cj = http.cookiejar.CookieJar()
        self._op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cj))
        self._crumb = None
        self.warm()

    def _raw_get(self, url: str, accept: str = "*/*", timeout: int = 20):
        req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": accept})
        return self._op.open(req, timeout=timeout)

    def warm(self) -> None:
        """Prime the A1/A3 consent cookies from a real quote page, then a crumb."""
        try:
            self._raw_get("https://finance.yahoo.com/quote/AAPL", "text/html").read()
        except Exception:
            pass
        for host in _HOSTS:
            try:
                c = self._raw_get(f"https://{host}/v1/test/getcrumb").read().decode().strip()
                if c and len(c) < 40:
                    self._crumb = c
                    return
            except Exception:
                continue

    def get_json(self, path: str, params: dict, retries: int = 3):
        """GET a JSON endpoint with the crumb attached.

        HTTP 404 is a DEFINITIVE answer (dead/unknown symbol) — raise immediately
        after trying the second host, with no backoff (a full retry cycle wasted
        ~16s per dead ticker). Auth-shaped failures (401/403/406) invalidate the
        crumb and re-warm on ANY attempt (a stale crumb on attempt 1+ was
        previously retried verbatim and failed deterministically)."""
        last = None
        for attempt in range(retries):
            q = dict(params)
            if self._crumb:
                q["crumb"] = self._crumb
            qs = urllib.parse.urlencode(q, safe=",")
            saw_404 = 0
            for host in _HOSTS:
                try:
                    r = self._raw_get(f"https://{host}{path}?{qs}", "application/json")
                    return json.loads(r.read())
                except urllib.error.HTTPError as e:
                    last = e
                    if e.code == 404:
                        saw_404 += 1
                        continue              # try the other host once, no backoff
                    if e.code in (401, 403, 406):
                        self._crumb = None    # stale crumb: invalidate, then re-prime
                        self.warm()
                        break
                    if e.code == 429:
                        break                 # throttled: back off (warm won't help)
                except Exception as e:
                    last = e
            if saw_404 == len(_HOSTS):
                raise RuntimeError(f"yahoo get_json 404 (dead symbol): {path}")
            if attempt < retries - 1:         # no useless sleep after the final try
                time.sleep(config.BACKOFF_BASE * (2 ** attempt))
        raise RuntimeError(f"yahoo get_json failed: {path}: {last}")

    # ---- batch pre-screen -------------------------------------------------- #
    def batch_quotes(self, symbols: list[str], chunk: int = 100) -> dict[str, dict]:
        """{symbol -> quote dict} for the live symbols (dead ones simply absent).

        The quote carries marketCap / regularMarketPrice / currency / trailingPE /
        priceToBook etc., enough to decide liveness and assign a size bucket.
        A failed chunk is retried once after a re-warm; symbols in chunks that
        still fail are recorded on ``self.failed_symbols`` so callers can
        distinguish "Yahoo said dead" from "request failed" (a silently dropped
        chunk would otherwise mark 100 live names dead in a pre-screen)."""
        out: dict[str, dict] = {}
        self.failed_symbols: list[str] = []
        for i in range(0, len(symbols), chunk):
            part = symbols[i:i + chunk]
            j = None
            for attempt in range(2):
                try:
                    j = self.get_json("/v7/finance/quote", {"symbols": ",".join(part)})
                    break
                except Exception:
                    if attempt == 0:
                        self.warm()
            if j is None:
                self.failed_symbols.extend(part)
                continue
            for q in (j.get("quoteResponse") or {}).get("result") or []:
                sym = q.get("symbol")
                if sym:
                    out[sym] = q
            time.sleep(config.RATE_MIN_INTERVAL)
        return out


# --------------------------------------------------------------------------- #
# Full raw fetch (quoteSummary + chart) -> the fundamentals.fetch_raw shape
# --------------------------------------------------------------------------- #
def _raw(node, key):
    v = (node or {}).get(key)
    if isinstance(v, dict):
        return v.get("raw")
    return v


# fundamentals-timeseries line item -> our block key. This endpoint (the one
# yfinance actually uses) gives EBITDA/EPS directly with correct alignment, unlike
# the legacy quoteSummary income module (which omits EBITDA and mis-states revenue
# for some filers, e.g. Toyota).
_TS_ITEMS = {"TotalRevenue": "revenue", "GrossProfit": "gross", "EBITDA": "ebitda",
             "NetIncome": "earnings", "BasicEPS": "eps"}
_TS_P1 = 1136073600  # 2006-01-01; Yahoo caps the window to what it has (~5y/8q)


def _timeseries_blocks(client: "YahooClient", symbol: str) -> tuple[dict, dict]:
    """(annual, quarterly) statement blocks from the fundamentals-timeseries API,
    aligned oldest->newest on the union of report dates (NaN where an item is
    missing) — the position-aligned shape metrics expects."""
    types = ",".join([f"annual{k}" for k in _TS_ITEMS] + [f"quarterly{k}" for k in _TS_ITEMS])
    try:
        j = client.get_json(f"/ws/fundamentals-timeseries/v1/finance/timeseries/{urllib.parse.quote(symbol, safe='')}",
                            {"type": types, "period1": _TS_P1, "period2": int(time.time())})
    except Exception:
        return {}, {}
    ann: dict[str, dict] = {}
    qtr: dict[str, dict] = {}
    for s in (j.get("timeseries") or {}).get("result") or []:
        typ = (s.get("meta", {}).get("type") or [None])[0]
        if not typ:
            continue
        bucket, prefix = (ann, "annual") if typ.startswith("annual") else (qtr, "quarterly")
        key = _TS_ITEMS.get(typ[len(prefix):])
        if not key:
            continue
        d = {}
        for pt in s.get(typ) or []:
            if pt and pt.get("asOfDate") and isinstance(pt.get("reportedValue"), dict):
                v = pt["reportedValue"].get("raw")
                if v is not None:
                    d[pt["asOfDate"]] = float(v)
        bucket[key] = d

    return _assemble_block(ann), _assemble_block(qtr, quarterly=True)


def _assemble_block(series: dict, quarterly: bool = False) -> dict:
    """Project {item -> {date: val}} onto a shared sorted date axis. For the
    quarterly axis, snap onto a COMPLETE quarter grid — metrics._q_yoy_block pairs
    vals[-1] with vals[-5] positionally, so a missing quarter in a plain union axis
    would compare the wrong quarters (measured on 13.6% of names); missing quarters
    become explicit NaN rows instead."""
    dates = sorted(set().union(*(set(d) for d in series.values()))) if series else []
    if quarterly and len(dates) >= 2:
        pidx = pd.PeriodIndex(pd.to_datetime(dates), freq="Q")
        by_period = dict(zip(pidx, dates))              # later date wins a collision
        grid = pd.period_range(pidx.min(), pidx.max(), freq="Q")
        dates = [by_period.get(p, str(p.end_time.date())) for p in grid]
        present = set(by_period.values())
        out = {"dates": dates}
        for key in _TS_ITEMS.values():
            d = series.get(key, {})
            out[key] = [d.get(dt, NaN) if dt in present else NaN for dt in dates]
        return out
    out = {"dates": dates}
    for key in _TS_ITEMS.values():
        d = series.get(key, {})
        out[key] = [d.get(dt, NaN) for dt in dates]
    return out


def _block_to_series(block: dict) -> dict:
    """{item -> {date: val}} from a stored block's parallel lists, dropping NaN /
    non-numeric cells — the inverse of :func:`_assemble_block`."""
    dates = (block or {}).get("dates") or []
    series = {}
    for key in _TS_ITEMS.values():
        vals = block.get(key) or []
        series[key] = {dt: v for dt, v in zip(dates, vals)
                       if isinstance(v, (int, float)) and v == v}
    return series


def regrid_quarterly(block: dict) -> dict:
    """Repair a cached quarterly statement block IN PLACE (no network): rebuild its
    {date: val} series from the stored parallel lists and re-assemble onto the
    complete quarter grid. For blocks fetched before the grid fix, this inserts the
    NaN rows for skipped quarters so positional YoY realigns."""
    if len((block or {}).get("dates") or []) < 2:
        return block
    return _assemble_block(_block_to_series(block), quarterly=True)


def merge_statement_blocks(base: dict, new: dict, quarterly: bool = False) -> dict:
    """Union two statement blocks by period-END date and re-assemble.

    NEW wins a same-date collision (a restated/updated figure supersedes the
    original), but base values are RETAINED wherever ``new`` lacks that date — so
    folding in the ~5y/8q Yahoo timeseries appends the freshly reported periods
    without truncating deeper cached history (the whole point: never shorten an
    EDGAR-deep annual series or a long quarterly run to Yahoo's window).
    """
    base_s = _block_to_series(base)
    new_s = _block_to_series(new)
    merged = {}
    for key in _TS_ITEMS.values():
        d = dict(base_s.get(key, {}))
        d.update(new_s.get(key, {}))          # new supersedes on a date collision
        merged[key] = d
    return _assemble_block(merged, quarterly=quarterly)


def _price_block(client: YahooClient, symbol: str):
    """Monthly close history from v8/chart -> (features, monthly) via the existing
    price-feature math, so trailing returns match the curl_cffi path exactly."""
    try:
        j = client.get_json(f"/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}",
                            {"range": config.PRICE_LOOKBACK, "interval": "1mo"})
        res = (j.get("chart") or {}).get("result") or []
        if not res:
            return {k: NaN for k in config.PRICE_FEATURE_KEYS}, {"dates": [], "close": []}
        r0 = res[0]
        ts = r0.get("timestamp") or []
        ind = r0.get("indicators") or {}
        # Prefer ADJUSTED closes (splits + dividends), matching yfinance
        # history(auto_adjust=True): raw quote closes exclude dividends, which
        # understates trailing returns for dividend payers (KO 12m: 23.0% raw vs
        # 26.5% adjusted) and would bias the dormancy/price-response ranks.
        closes = ((ind.get("adjclose") or [{}])[0]).get("adjclose") or \
                 ((ind.get("quote") or [{}])[0]).get("close") or []
        idx = pd.to_datetime([datetime.fromtimestamp(t, timezone.utc) for t in ts])
        hist = pd.DataFrame({"Close": closes}, index=idx).dropna()
        return fundamentals._price_features(hist)
    except Exception:
        return {k: NaN for k in config.PRICE_FEATURE_KEYS}, {"dates": [], "close": []}


# Valuation / profile / surprises come from quoteSummary; the STATEMENTS come from
# the fundamentals-timeseries endpoint (see _timeseries_blocks).
_QS_MODULES = "defaultKeyStatistics,summaryDetail,financialData,price,assetProfile,earningsHistory"


def fetch_raw(symbol: str, client: YahooClient, with_surprises: bool = False) -> dict:
    """Fetch one ticker via the urllib JSON API, in fetch_raw's dict shape."""
    try:
        j = client.get_json(f"/v10/finance/quoteSummary/{urllib.parse.quote(symbol, safe='')}",
                            {"modules": _QS_MODULES})
        res = ((j.get("quoteSummary") or {}).get("result") or [None])[0]
        if res is None:
            raise ValueError("no quoteSummary result")
    except Exception as err:
        # "surprises" present-but-empty so the negative-cache accept check in
        # build_fundamentals doesn't refetch dead tickers on every surprise run.
        return {"symbol": symbol, "asof": datetime.now(timezone.utc).isoformat(),
                "annual": {}, "quarterly": {}, "valuation": {}, "prices": {},
                "surprises": [], "fetch_ok": False, "rate_limited": False, "error": str(err)}

    ann, qtr = _timeseries_blocks(client, symbol)
    valuation = _valuation_from(res)
    feats, monthly = _price_block(client, symbol)
    surprises = _surprises_from(res) if with_surprises else []

    has_data = any(any(not math.isnan(x) for x in ann.get(k, []))
                   for k in ("revenue", "ebitda", "earnings"))
    return {"symbol": symbol, "asof": datetime.now(timezone.utc).isoformat(),
            "annual": ann, "quarterly": qtr, "valuation": valuation,
            "prices": {**feats, "monthly": monthly}, "surprises": surprises,
            "statement_source": "yahoo-urllib",
            "fetch_ok": bool(has_data or valuation.get("marketCap"))}


def _valuation_from(res: dict) -> dict:
    sd, ks = res.get("summaryDetail", {}), res.get("defaultKeyStatistics", {})
    fd_, pr, ap = res.get("financialData", {}), res.get("price", {}), res.get("assetProfile", {})
    return {
        "trailingPE": _raw(sd, "trailingPE"), "forwardPE": _raw(sd, "forwardPE"),
        "enterpriseToEbitda": _raw(ks, "enterpriseToEbitda"),
        "priceToSalesTrailing12Months": _raw(sd, "priceToSalesTrailing12Months"),
        "priceToBook": _raw(ks, "priceToBook"), "pegRatio": _raw(ks, "pegRatio"),
        "marketCap": _raw(sd, "marketCap") or _raw(pr, "marketCap"),
        "enterpriseValue": _raw(ks, "enterpriseValue"),
        "currency": pr.get("currency"), "sector": ap.get("sector"), "industry": ap.get("industry"),
        "trailingEps": _raw(ks, "trailingEps"), "forwardEps": _raw(ks, "forwardEps"),
        "numberOfAnalystOpinions": _raw(fd_, "numberOfAnalystOpinions"),
    }


def _surprises_from(res: dict) -> list:
    out = []
    for h in res.get("earningsHistory", {}).get("history", []) or []:
        sp = _raw(h, "surprisePercent")     # DECIMAL FRACTION -> percent
        dt = _raw(h, "quarter")
        if sp is not None:
            out.append({"date": datetime.fromtimestamp(dt, timezone.utc).date().isoformat() if dt else None,
                        "surprise_pct": max(-200.0, min(200.0, float(sp) * 100.0))})
    # Yahoo's ordering is usually ascending but NOT guaranteed (observed shuffled
    # in the wild); surprise_block treats sp[-1] as the latest quarter, so sort.
    out.sort(key=lambda s: s["date"] or "")
    return out[-12:]


def merge_surprises(old: list | None, new: list | None, keep: int = 12) -> list:
    """Union two surprise histories by date (new wins a collision), sorted, last
    ``keep``. quoteSummary's earningsHistory only carries ~4 quarters, so REPLACING
    a stored 12-quarter history with it silently halves the window the 8-quarter
    surprise metrics (cum8/trend/robust) are computed on — always merge."""
    by_date = {e["date"]: e for e in (old or []) if e.get("date")}
    by_date.update({e["date"]: e for e in (new or []) if e.get("date")})
    return [by_date[d] for d in sorted(by_date)][-keep:]


def refresh_market(symbol: str, client: YahooClient, base_raw: dict,
                   with_surprises: bool = False) -> dict | None:
    """Refresh ONLY the market-derived blocks (valuation + prices [+ surprises]) on
    an existing raw, KEEPING its statement blocks — so a stale-price update never
    clobbers the EDGAR deep-history overlay (or any cached statements). Two urllib
    calls (quoteSummary valuation + chart) vs three for a full fetch.

    Returns None on failure (never a stale copy of the input: the caller must be
    able to distinguish failure, and the input may carry a ``market_refreshed``
    stamp from a PRIOR run that would masquerade as success). The prices block is
    only replaced when the chart leg actually returned data, and surprises are
    MERGED (see :func:`merge_surprises`), never truncated to quoteSummary's ~4q.
    """
    try:
        j = client.get_json(f"/v10/finance/quoteSummary/{urllib.parse.quote(symbol, safe='')}",
                            {"modules": _QS_MODULES})
        res = ((j.get("quoteSummary") or {}).get("result") or [None])[0]
        if res is None:
            raise ValueError("no quoteSummary result")
    except Exception:
        return None
    out = dict(base_raw)
    new_val = _valuation_from(res)
    old_val = base_raw.get("valuation") or {}
    if new_val.get("marketCap") or not old_val.get("marketCap"):
        out["valuation"] = new_val
    # else: quoteSummary answered with an empty shell (modules present, values
    # null — a transient Yahoo degradation) while the cache holds a real
    # valuation; keep the older real block, mirroring the chart-leg guard below.
    feats, monthly = _price_block(client, symbol)
    if monthly.get("dates"):                     # chart leg succeeded
        out["prices"] = {**feats, "monthly": monthly}
    # else: keep the existing (older but real) price block — an all-NaN overwrite
    # would erase good return history on a transient chart failure.
    if with_surprises:
        out["surprises"] = merge_surprises(base_raw.get("surprises"), _surprises_from(res))
    out["asof"] = datetime.now(timezone.utc).isoformat()
    out["market_refreshed"] = out["asof"]
    has_stmt = any(any(not math.isnan(x) for x in (out.get("annual", {}) or {}).get(k, []))
                   for k in ("revenue", "ebitda", "earnings"))
    out["fetch_ok"] = bool(has_stmt or out["valuation"].get("marketCap"))
    return out


def refresh_statements(symbol: str, client: "YahooClient", base_raw: dict) -> dict | None:
    """Refresh the STATEMENT blocks by MERGING a fresh Yahoo timeseries into the
    cached blocks (append newly reported periods; never truncate deep history).

    Complements :func:`refresh_market` (which leaves statements untouched): here
    the quarterly block — where a just-reported quarter lands, driving q_yoy /
    acceleration / margin-delta metrics — is always merged, and the annual block
    is merged too EXCEPT for EDGAR-overlaid names, whose annual is authoritative
    and deeper than Yahoo's ~5y window (a separate ``fetch_edgar`` refresh owns
    it; letting Yahoo overwrite it here would both shorten it and risk a
    cross-source period-end-date mismatch). Valuation/prices/surprises are kept
    from ``base_raw`` verbatim — those are refresh_market's job.

    Returns None when Yahoo yields no usable statements (transient failure or a
    genuinely statement-less security), so the caller keeps the cached raw rather
    than blanking it.
    """
    new_ann, new_qtr = _timeseries_blocks(client, symbol)
    if not ((new_ann.get("dates") or new_qtr.get("dates"))):
        return None                              # nothing usable came back
    out = dict(base_raw)
    if base_raw.get("statement_source") != "edgar-annual":
        out["annual"] = merge_statement_blocks(base_raw.get("annual"), new_ann)
    out["quarterly"] = merge_statement_blocks(base_raw.get("quarterly"), new_qtr, quarterly=True)
    out["asof"] = datetime.now(timezone.utc).isoformat()
    out["statements_refreshed"] = out["asof"]
    has_stmt = any(any(not math.isnan(x) for x in (out.get("annual", {}) or {}).get(k, []))
                   for k in ("revenue", "ebitda", "earnings"))
    out["fetch_ok"] = bool(has_stmt or (out.get("valuation") or {}).get("marketCap"))
    return out
