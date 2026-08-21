"""
Plain-requests Yahoo Finance client.

Exists because yfinance's curl_cffi transport is incompatible with this
environment's TLS-intercepting egress proxy (the proxy resets impersonated
handshakes), while a plain `requests` session with a browser User-Agent goes
through cleanly. Endpoints used:

  - /v8/finance/chart/{sym}          OHLC bars (no crumb needed)
  - fc.yahoo.com + /v1/test/getcrumb cookie + crumb for quoteSummary
  - /v10/finance/quoteSummary/{sym}  fundamentals modules

Global request pacing + exponential backoff on 429 keeps us under Yahoo's
per-IP limits across worker threads.
"""
from __future__ import annotations

import random
import sys
import threading
import time

import pandas as pd

UA = ("Mozilla/5.0 (X11; Linux x86_64; rv:109.0) "
      "Gecko/20100101 Firefox/119.0")
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
QS_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{sym}"

QS_MODULES = ("summaryDetail,defaultKeyStatistics,financialData,price,"
              "summaryProfile,incomeStatementHistory")


class YahooClient:
    """Thread-safe, globally-paced Yahoo fetcher over plain requests."""

    def __init__(self, min_interval: float = 0.70):
        self._min_interval = min_interval
        self._pace_lock = threading.Lock()
        self._next_ok = 0.0
        self._local = threading.local()
        self._crumb: str | None = None
        self._crumb_lock = threading.Lock()

    # ------------------------------------------------------------- session
    def _session(self):
        import requests

        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            s.headers.update({"User-Agent": UA})
            self._local.session = s
        return s

    def _pace(self) -> None:
        with self._pace_lock:
            now = time.monotonic()
            wait = self._next_ok - now
            self._next_ok = max(now, self._next_ok) + self._min_interval
        if wait > 0:
            time.sleep(wait)

    def _get(self, url: str, params: dict | None = None, max_tries: int = 6):
        """Paced GET with 429 backoff. Returns Response or None."""
        s = self._session()
        for attempt in range(max_tries):
            self._pace()
            try:
                r = s.get(url, params=params, timeout=25)
            except Exception as e:  # noqa: BLE001
                if attempt == max_tries - 1:
                    print(f"  [warn] GET {url.split('/')[-1].split('?')[0]}: "
                          f"{type(e).__name__}", file=sys.stderr)
                    return None
                time.sleep(2 * (2 ** attempt))
                continue
            if r.status_code == 429:
                # Yahoo blocks can run long; wait patiently rather than churn.
                wait = min(600, 60 * (2 ** attempt)) + random.uniform(0, 10)
                print(f"  [rate-limit] 429, sleeping {wait:.0f}s ...",
                      file=sys.stderr, flush=True)
                time.sleep(wait)
                continue
            if r.status_code == 404:
                return None
            if r.status_code != 200:
                if attempt == max_tries - 1:
                    return None
                time.sleep(2 * (2 ** attempt))
                continue
            return r
        return None

    # --------------------------------------------------------------- OHLC
    def get_ohlc(self, symbol: str, range_: str = "3y") -> pd.DataFrame | None:
        """Adjusted OHLC frame (Open/High/Low/Close), or None."""
        r = self._get(CHART_URL.format(sym=symbol),
                      params={"range": range_, "interval": "1d",
                              "events": "div,splits"})
        if r is None:
            return None
        try:
            res = r.json()["chart"]["result"][0]
            ts = res.get("timestamp")
            q = res["indicators"]["quote"][0]
            if not ts or not q.get("close"):
                return None
            df = pd.DataFrame(
                {"Open": q["open"], "High": q["high"],
                 "Low": q["low"], "Close": q["close"]},
                index=pd.to_datetime(ts, unit="s", utc=True).tz_convert(None).normalize(),
            ).dropna(how="any")
            adj = res["indicators"].get("adjclose")
            if adj and adj[0].get("adjclose"):
                adj_s = pd.Series(
                    adj[0]["adjclose"],
                    index=pd.to_datetime(ts, unit="s", utc=True).tz_convert(None).normalize(),
                ).reindex(df.index)
                factor = (adj_s / df["Close"]).fillna(1.0)
                for c in ("Open", "High", "Low", "Close"):
                    df[c] = df[c] * factor
            return df if len(df) else None
        except Exception:  # noqa: BLE001
            return None

    # -------------------------------------------------------------- crumb
    def _ensure_crumb(self) -> str | None:
        with self._crumb_lock:
            if self._crumb:
                return self._crumb
            s = self._session()
            try:
                self._pace()
                s.get("https://fc.yahoo.com", timeout=20)
            except Exception:  # noqa: BLE001
                pass
            r = self._get(CRUMB_URL)
            if r is not None and r.text and "<" not in r.text:
                self._crumb = r.text.strip()
            return self._crumb

    # ------------------------------------------------------- fundamentals
    def get_fundamentals(self, symbol: str) -> dict | None:
        """quoteSummary modules flattened to a plain dict, or None."""
        crumb = self._ensure_crumb()
        params = {"modules": QS_MODULES}
        if crumb:
            params["crumb"] = crumb
        r = self._get(QS_URL.format(sym=symbol), params=params)
        if r is None:
            return None
        try:
            res = r.json()["quoteSummary"]["result"]
            if not res:
                return None
            d = res[0]
        except Exception:  # noqa: BLE001
            return None

        def raw(block: dict, key: str):
            v = block.get(key)
            if isinstance(v, dict):
                v = v.get("raw")
            if v is None:
                return float("nan")
            try:
                f = float(v)
                return f if f == f else float("nan")
            except (TypeError, ValueError):
                return float("nan")

        ks = d.get("defaultKeyStatistics", {}) or {}
        fin = d.get("financialData", {}) or {}
        sd = d.get("summaryDetail", {}) or {}
        pr = d.get("price", {}) or {}
        prof = d.get("summaryProfile", {}) or {}

        # Annual revenue series, most recent first.
        hist = ((d.get("incomeStatementHistory") or {})
                .get("incomeStatementHistory") or [])
        revenues = []
        for stmt in hist:
            v = raw(stmt or {}, "totalRevenue")
            if v == v and v is not None:
                revenues.append(v)

        return {
            "name": pr.get("longName") or pr.get("shortName") or symbol,
            "sector": prof.get("sector") or "",
            "market_cap": raw(pr, "marketCap") if "marketCap" in pr else raw(sd, "marketCap"),
            "pb": raw(ks, "priceToBook"),
            "ev_ebitda": raw(ks, "enterpriseToEbitda"),
            "ev_sales": raw(ks, "enterpriseToRevenue"),
            "fcf": raw(fin, "freeCashflow"),
            "op_margin": raw(fin, "operatingMargins"),
            "roe": raw(fin, "returnOnEquity"),
            "debt_to_equity": raw(fin, "debtToEquity"),
            "eps_q_growth": raw(ks, "earningsQuarterlyGrowth"),
            "rev_growth_ttm": raw(fin, "revenueGrowth"),
            "annual_revenues": revenues,
        }


def wait_until_clear(client: YahooClient, probe: str = "AAPL",
                     max_wait: float = 8 * 3600.0,
                     probe_every: float = 600.0) -> bool:
    """Block until Yahoo stops 429-ing us.

    Uses a SINGLE bare request per probe (no internal retries) so the
    cooldown itself doesn't extend the block, and probes only every
    `probe_every` seconds. Blocks after a heavy hammering can run for
    hours — default patience is 8h.
    """
    import requests

    t0 = time.time()
    n = 0
    while time.time() - t0 < max_wait:
        n += 1
        try:
            r = requests.get(
                CHART_URL.format(sym=probe),
                params={"range": "5d", "interval": "1d"},
                headers={"User-Agent": UA}, timeout=20,
            )
            if r.status_code == 200:
                print(f"  [cooldown] clear after {(time.time()-t0)/60:.0f} min "
                      f"({n} probes)", file=sys.stderr, flush=True)
                return True
            status = r.status_code
        except Exception as e:  # noqa: BLE001
            status = type(e).__name__
        print(f"  [cooldown] probe {n}: {status}; elapsed "
              f"{(time.time()-t0)/60:.0f} min, next probe in "
              f"{probe_every/60:.0f} min", file=sys.stderr, flush=True)
        time.sleep(probe_every)
    return False
