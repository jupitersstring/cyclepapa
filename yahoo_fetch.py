"""Proxy-routed Yahoo price fetcher (plain requests).

yfinance's curl_cffi transport gets 429'd through the agent proxy, but a normal
requests call with a browser UA works. This module fetches adjusted OHLCV bars
that match yfinance auto_adjust=True output, so the durable cache stays
format-compatible with momentum_rank.
"""
import os
import time
import threading
import pandas as pd
import requests

_CA = "/root/.ccr/ca-bundle.crt"
_PX = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
_local = threading.local()


def _session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        if _PX:
            s.proxies = {"https": _PX, "http": _PX}
        if os.path.exists(_CA):
            s.verify = _CA
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        _local.s = s
    return s


def fetch_ohlcv(ticker, rng="2y", interval="1d", tries=4):
    """Return an auto-adjusted OHLCV DataFrame (DatetimeIndex) or None.

    Mirrors yfinance auto_adjust=True: every OHLC value is scaled by
    adjclose/close so splits/dividends are baked in."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?range={rng}&interval={interval}")
    backoff = 2.0
    for attempt in range(tries):
        try:
            r = _session().get(url, timeout=25)
        except Exception:
            time.sleep(backoff); backoff *= 2; continue
        if r.status_code == 429:
            time.sleep(backoff); backoff *= 2; continue
        if r.status_code != 200:
            return None
        try:
            res = r.json()["chart"]["result"][0]
        except Exception:
            return None
        ts = res.get("timestamp")
        if not ts:
            return None
        q = res["indicators"]["quote"][0]
        adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
        idx = pd.to_datetime(ts, unit="s").normalize()
        df = pd.DataFrame({
            "Open": q.get("open"), "High": q.get("high"), "Low": q.get("low"),
            "Close": q.get("close"), "Volume": q.get("volume"),
        }, index=idx)
        if adj is not None:
            adj = pd.Series(adj, index=idx)
            factor = (adj / df["Close"]).where(df["Close"] > 0)
            for c in ("Open", "High", "Low", "Close"):
                df[c] = df[c] * factor
        df = df.dropna(subset=["Close"])
        df.index.name = "Date"
        return df if len(df) else None
    return None
