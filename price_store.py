"""Local OHLCV cache (parquet) for the screening universe.

Why: the v2 screener did 438 serial yf.download calls every run, with
errors silently swallowed per row. A cached store makes runs fast
(seconds for a re-run), exposes per-ticker coverage gaps, and is the
prerequisite for the historical event-study backtest.

Layout: data/prices/<ticker>.parquet, one parquet per ticker.
Each parquet has columns Open, High, Low, Close, Volume + a
DatetimeIndex of weekly bars (Friday close convention).

Refresh policy:
  * `get(ticker)` returns from cache if file age < ttl_hours.
  * Otherwise refetches the full 5y window via yfinance.
  * `refresh_all(tickers)` runs serially with a small sleep — cheap
    parallelism is left for the caller if needed.

Coverage report:
  * `coverage_report(tickers)` returns a list of {ticker, bars,
    last_date, refreshed_at, ok} — flag the ones that failed instead
    of silently dropping them.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


DATA_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "data" / "prices"
DAILY_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "data" / "prices_daily"


def _safe_name(ticker: str) -> str:
    # parquet filenames can't contain ':' or '/'; replace exotic chars
    return ticker.replace("/", "_").replace(":", "_") + ".parquet"


def _path(ticker: str) -> Path:
    return DATA_DIR / _safe_name(ticker)


def _path_daily(ticker: str) -> Path:
    return DAILY_DIR / _safe_name(ticker)


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)


def _age_hours(p: Path) -> float:
    if not p.exists():
        return float("inf")
    return (time.time() - p.stat().st_mtime) / 3600.0


# --- yfinance transport fix (RCA 2026-07-16) -------------------------
# yfinance's new_session() hardcodes curl_cffi impersonate="chrome".
# Modern Chrome/Firefox ClientHellos carry post-quantum key shares and
# ECH, which some TLS-terminating egress proxies cannot parse — they
# reset the connection ("curl: (35) Recv failure"). Profile matrix
# tested against this environment's proxy:
#     chrome / chrome120 / chrome131 / firefox  -> connection reset
#     chrome110 / safari184 / edge              -> 200 OK
#     no impersonation                          -> 429 (Yahoo rate-limits)
# So we inject our own session with a pre-PQ profile: full proxy
# compatibility AND Yahoo's bot-filter is satisfied. Ordered
# candidates in case Yahoo ever blocks the older fingerprint.
_YF_IMPERSONATE_CANDIDATES = ("chrome110", "safari184", "edge")
_YF_SESSION = None


def _yf_session():
    """Shared curl_cffi session with a proxy-compatible TLS profile.
    Falls back to None (yfinance default) if curl_cffi is missing."""
    global _YF_SESSION
    if _YF_SESSION is not None:
        return _YF_SESSION
    try:
        from curl_cffi import requests as _creq
    except ImportError:
        return None
    for prof in _YF_IMPERSONATE_CANDIDATES:
        try:
            s = _creq.Session(impersonate=prof)
            # Cheap probe — any HTTP status means TLS + proxy work
            s.get("https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
                  "?range=1d&interval=1d", timeout=8)
            _YF_SESSION = s
            return s
        except Exception:
            continue
    return None


# Circuit breaker: retained as a belt-and-braces layer — if even the
# fixed session fails repeatedly (proxy policy change, Yahoo outage)
# we stop paying per-name retry latency and go straight to the urllib
# chart API. Any yfinance success resets the counter.
_YF_CONSECUTIVE_FAILURES = 0
_YF_BREAKER_THRESHOLD = 3


def _download(ticker: str, period: str = "5y",
              interval: str = "1wk") -> pd.DataFrame | None:
    """Download OHLCV. Tries yfinance first; falls back to the Yahoo
    chart API via urllib. The fallback matters in proxied
    environments: yfinance's curl_cffi backend bypasses HTTPS_PROXY
    and dies on TLS, while urllib honours the proxy and works."""
    global _YF_CONSECUTIVE_FAILURES
    d = None
    if _YF_CONSECUTIVE_FAILURES < _YF_BREAKER_THRESHOLD:
        try:
            d = yf.download(ticker, period=period, interval=interval,
                            progress=False, auto_adjust=True,
                            session=_yf_session())
        except Exception:
            d = None
        if d is None or d.empty:
            _YF_CONSECUTIVE_FAILURES += 1
        else:
            _YF_CONSECUTIVE_FAILURES = 0
    if d is None or d.empty:
        d = _download_via_chart_api(ticker, period=period, interval=interval)
    if d is None or d.empty:
        return None
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    # Bad-tick hygiene
    bad = (d["Low"] <= 0) | d["Low"].isna()
    if bad.any():
        d.loc[bad, "Low"] = d.loc[bad, ["Open", "Close"]].min(axis=1)
    return d.dropna(subset=["Close", "Volume"])


def _download_via_chart_api(ticker: str, period: str = "5y",
                            interval: str = "1wk") -> pd.DataFrame | None:
    """Direct Yahoo v8 chart API via urllib (proxy-friendly)."""
    import json
    import urllib.parse
    import urllib.request
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker)}?range={period}&interval={interval}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; CyclepapaPrices/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    try:
        result = payload["chart"]["result"][0]
        ts = result["timestamp"]
        q = result["indicators"]["quote"][0]
        df = pd.DataFrame({
            "Open": q["open"], "High": q["high"], "Low": q["low"],
            "Close": q["close"], "Volume": q["volume"],
        }, index=pd.to_datetime(ts, unit="s"))
        # Use adjclose when present (matches auto_adjust=True closer)
        adj = result["indicators"].get("adjclose")
        if adj and adj[0].get("adjclose"):
            ratio = pd.Series(adj[0]["adjclose"], index=df.index) / df["Close"]
            for col in ("Open", "High", "Low", "Close"):
                df[col] = df[col] * ratio
        return df.dropna(subset=["Close"])
    except (KeyError, IndexError, TypeError):
        return None


def get(ticker: str, *, ttl_hours: float = 24.0,
        force_refresh: bool = False) -> pd.DataFrame | None:
    _ensure_dir()
    p = _path(ticker)
    if not force_refresh and _age_hours(p) < ttl_hours and p.exists():
        try:
            return pd.read_parquet(p)
        except Exception:
            pass
    d = _download(ticker)
    if d is None or d.empty:
        # STALE-CACHE FALLBACK: a failed refresh must not erase
        # coverage we already have. Serving yesterday's parquet beats
        # dropping the name from the screen entirely (the June-24
        # "255 of 653" coverage collapse was exactly this).
        if p.exists():
            try:
                return pd.read_parquet(p)
            except Exception:
                pass
        return None
    try:
        d.to_parquet(p)
    except Exception:
        pass
    return d


def get_daily(ticker: str, *, ttl_hours: float = 24.0,
              force_refresh: bool = False, days: int = 180) -> pd.DataFrame | None:
    """Daily bars for the last `days` days. Used to detect single-bar
    volume spikes that a weekly bar would smooth over."""
    _ensure_dir()
    p = _path_daily(ticker)
    if not force_refresh and _age_hours(p) < ttl_hours and p.exists():
        try:
            return pd.read_parquet(p)
        except Exception:
            pass
    period = "6mo" if days <= 180 else "1y"
    d = _download(ticker, period=period, interval="1d")
    if d is None or d.empty:
        # Stale-cache fallback — same rationale as get()
        if p.exists():
            try:
                return pd.read_parquet(p)
            except Exception:
                pass
        return None
    try:
        d.to_parquet(p)
    except Exception:
        pass
    return d


def refresh_all(tickers: list[str], *, ttl_hours: float = 24.0,
                sleep_s: float = 0.1, verbose: bool = False) -> dict[str, int]:
    """Refresh the store. Returns {ticker: bars} for successful fetches."""
    out: dict[str, int] = {}
    n = len(tickers)
    for i, t in enumerate(tickers, 1):
        d = get(t, ttl_hours=ttl_hours)
        if d is not None:
            out[t] = len(d)
        if verbose and i % 25 == 0:
            print(f"  [{i}/{n}] cached", flush=True)
        time.sleep(sleep_s)
    return out


def coverage_report(tickers: list[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        p = _path(t)
        if not p.exists():
            rows.append({"ticker": t, "ok": False, "bars": 0,
                         "last_date": None, "age_h": None})
            continue
        try:
            d = pd.read_parquet(p)
            rows.append({
                "ticker": t,
                "ok": len(d) >= 30,
                "bars": len(d),
                "last_date": str(d.index[-1].date()) if len(d) else None,
                "age_h": round(_age_hours(p), 1),
            })
        except Exception:
            rows.append({"ticker": t, "ok": False, "bars": 0,
                         "last_date": None, "age_h": None})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import metadata
    tickers = metadata.all_tickers()[:5]
    for t in tickers:
        d = get(t)
        print(f"  {t}: {len(d) if d is not None else 0} bars")
    rpt = coverage_report(tickers)
    print(rpt.to_string(index=False))
