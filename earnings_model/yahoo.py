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
        """GET a JSON endpoint with the crumb attached; re-warm once on auth failure."""
        for attempt in range(retries):
            q = dict(params)
            if self._crumb:
                q["crumb"] = self._crumb
            qs = urllib.parse.urlencode(q, safe=",")
            last = None
            for host in _HOSTS:
                try:
                    r = self._raw_get(f"https://{host}{path}?{qs}", "application/json")
                    return json.loads(r.read())
                except urllib.error.HTTPError as e:
                    last = e
                    if e.code in (401, 403, 406, 429) and attempt == 0:
                        self.warm()  # stale crumb / throttle — re-prime once
                        break
                except Exception as e:
                    last = e
            time.sleep(config.BACKOFF_BASE * (2 ** attempt))
        raise RuntimeError(f"yahoo get_json failed: {path}: {last}")

    # ---- batch pre-screen -------------------------------------------------- #
    def batch_quotes(self, symbols: list[str], chunk: int = 100) -> dict[str, dict]:
        """{symbol -> quote dict} for the live symbols (dead ones simply absent).

        The quote carries marketCap / regularMarketPrice / currency / trailingPE /
        priceToBook etc., enough to decide liveness and assign a size bucket."""
        out: dict[str, dict] = {}
        for i in range(0, len(symbols), chunk):
            part = symbols[i:i + chunk]
            try:
                j = self.get_json("/v7/finance/quote", {"symbols": ",".join(part)})
            except Exception:
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
        j = client.get_json(f"/ws/fundamentals-timeseries/v1/finance/timeseries/{urllib.parse.quote(symbol)}",
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

    def _assemble(series: dict) -> dict:
        dates = sorted(set().union(*(set(d) for d in series.values()))) if series else []
        out = {"dates": dates}
        for key in _TS_ITEMS.values():
            d = series.get(key, {})
            out[key] = [d.get(dt, NaN) for dt in dates]
        return out

    return _assemble(ann), _assemble(qtr)


def _price_block(client: YahooClient, symbol: str):
    """Monthly close history from v8/chart -> (features, monthly) via the existing
    price-feature math, so trailing returns match the curl_cffi path exactly."""
    try:
        j = client.get_json(f"/v8/finance/chart/{urllib.parse.quote(symbol)}",
                            {"range": config.PRICE_LOOKBACK, "interval": "1mo"})
        res = (j.get("chart") or {}).get("result") or []
        if not res:
            return {k: NaN for k in config.PRICE_FEATURE_KEYS}, {"dates": [], "close": []}
        r0 = res[0]
        ts = r0.get("timestamp") or []
        closes = (((r0.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
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
        j = client.get_json(f"/v10/finance/quoteSummary/{urllib.parse.quote(symbol)}",
                            {"modules": _QS_MODULES})
        res = ((j.get("quoteSummary") or {}).get("result") or [None])[0]
        if res is None:
            raise ValueError("no quoteSummary result")
    except Exception as err:
        return {"symbol": symbol, "asof": datetime.now(timezone.utc).isoformat(),
                "annual": {}, "quarterly": {}, "valuation": {}, "prices": {},
                "fetch_ok": False, "rate_limited": False, "error": str(err)}

    ann, qtr = _timeseries_blocks(client, symbol)

    sd, ks = res.get("summaryDetail", {}), res.get("defaultKeyStatistics", {})
    fd_, pr, ap = res.get("financialData", {}), res.get("price", {}), res.get("assetProfile", {})
    valuation = {
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
    feats, monthly = _price_block(client, symbol)
    surprises = []
    if with_surprises:
        for h in res.get("earningsHistory", {}).get("history", []) or []:
            sp = _raw(h, "surprisePercent")   # DECIMAL FRACTION -> percent
            dt = _raw(h, "quarter")
            if sp is not None:
                surprises.append({"date": datetime.fromtimestamp(dt, timezone.utc).date().isoformat()
                                  if dt else None,
                                  "surprise_pct": max(-200.0, min(200.0, float(sp) * 100.0))})
        surprises = surprises[-12:]

    has_data = any(any(not math.isnan(x) for x in ann.get(k, []))
                   for k in ("revenue", "ebitda", "earnings"))
    return {"symbol": symbol, "asof": datetime.now(timezone.utc).isoformat(),
            "annual": ann, "quarterly": qtr, "valuation": valuation,
            "prices": {**feats, "monthly": monthly}, "surprises": surprises,
            "statement_source": "yahoo-urllib",
            "fetch_ok": bool(has_data or valuation.get("marketCap"))}
