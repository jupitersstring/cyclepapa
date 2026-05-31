"""Fetch fundamentals from yfinance with on-disk caching and backoff.

Yahoo aggressively rate-limits cloud IPs (HTTP 429), so every ticker is
cached to ``cache/raw/<symbol>.json`` and re-used within ``CACHE_TTL_DAYS``.
Network calls retry with exponential backoff and use a curl_cffi session
impersonating a browser, which is the usual way to dodge the 429 wall.
"""
from __future__ import annotations

import json
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, metrics

NaN = float("nan")


# --------------------------------------------------------------------------- #
# Session
# --------------------------------------------------------------------------- #
def make_session():
    """Return a curl_cffi browser-impersonating session, or None on failure."""
    try:
        from curl_cffi import requests as cffi_requests

        return cffi_requests.Session(impersonate="chrome")
    except Exception:
        return None


def _ticker(symbol: str, session):
    import yfinance as yf

    if session is not None:
        try:
            return yf.Ticker(symbol, session=session)
        except TypeError:
            pass
    return yf.Ticker(symbol)


# --------------------------------------------------------------------------- #
# Statement parsing
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _resolve_row(stmt: pd.DataFrame, keys: list[str]) -> pd.Series | None:
    """Find a statement row matching any candidate name (case/space-insensitive)."""
    if stmt is None or getattr(stmt, "empty", True):
        return None
    norm_index = {_norm(idx): idx for idx in stmt.index}
    for key in keys:
        nk = _norm(key)
        if nk in norm_index:
            return stmt.loc[norm_index[nk]]
    # Fall back to substring match (e.g. odd EBITDA variants).
    for key in keys:
        nk = _norm(key)
        for nidx, orig in norm_index.items():
            if nk and nk in nidx:
                return stmt.loc[orig]
    return None


def _series(stmt: pd.DataFrame, keys: list[str]) -> list[float]:
    """Return the line-item values oldest -> newest as plain floats."""
    row = _resolve_row(stmt, keys)
    if row is None:
        return []
    row = row.sort_index()  # columns are period-end dates -> ascending
    out = []
    for v in row.tolist():
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = NaN
        out.append(f if not math.isnan(f) else NaN)
    return out


def _ebitda_series(stmt: pd.DataFrame) -> list[float]:
    """EBITDA line, or operating income + D&A reconstruction as a fallback."""
    direct = _series(stmt, config.EBITDA_KEYS)
    if any(not math.isnan(x) for x in direct):
        return direct
    opinc = _series(stmt, config.OPERATING_INCOME_KEYS)
    da = _series(stmt, config.DA_KEYS)
    if opinc and da and len(opinc) == len(da):
        return [
            (o + d) if not (math.isnan(o) or math.isnan(d)) else NaN
            for o, d in zip(opinc, da)
        ]
    return direct


def _dates(stmt: pd.DataFrame) -> list[str]:
    if stmt is None or getattr(stmt, "empty", True):
        return []
    cols = sorted(stmt.columns)
    return [str(getattr(c, "date", lambda: c)()) for c in cols]


def _statement_block(stmt: pd.DataFrame) -> dict:
    return {
        "dates": _dates(stmt),
        "revenue": _series(stmt, config.REVENUE_KEYS),
        "ebitda": _ebitda_series(stmt),
        "earnings": _series(stmt, config.NET_INCOME_KEYS),
        "eps": _series(stmt, config.EPS_KEYS),
    }


# --------------------------------------------------------------------------- #
# Prices -> trailing returns
# --------------------------------------------------------------------------- #
def _trailing_returns(hist: pd.DataFrame) -> dict:
    out = {"ret_1m": NaN, "ret_3m": NaN, "ret_6m": NaN, "ret_12m": NaN, "last_price": NaN}
    if hist is None or getattr(hist, "empty", True) or "Close" not in hist.columns:
        return out
    close = hist["Close"].dropna()
    if close.empty:
        return out
    last = float(close.iloc[-1])
    out["last_price"] = last
    last_date = close.index[-1]
    for label, months in (("ret_1m", 1), ("ret_3m", 3), ("ret_6m", 6), ("ret_12m", 12)):
        target = last_date - pd.DateOffset(months=months)
        prior = close.loc[:target]
        if not prior.empty:
            base = float(prior.iloc[-1])
            if base > 0:
                out[label] = last / base - 1.0
    return out


# --------------------------------------------------------------------------- #
# Cache I/O
# --------------------------------------------------------------------------- #
def _cache_path(symbol: str) -> Path:
    return config.RAW_CACHE_DIR / f"{symbol.replace('/', '_')}.json"


def load_raw(symbol: str, ttl_days: float = config.CACHE_TTL_DAYS) -> dict | None:
    path = _cache_path(symbol)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    asof = raw.get("asof")
    if asof and ttl_days is not None:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(asof)
            if age.total_seconds() > ttl_days * 86400:
                return None
        except ValueError:
            pass
    return raw


def save_raw(symbol: str, raw: dict) -> None:
    config.RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(symbol).write_text(json.dumps(raw, default=str))


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
def fetch_raw(symbol: str, session=None, max_retries: int = config.MAX_RETRIES) -> dict:
    """Fetch one ticker's raw fundamentals with retry/backoff."""
    last_err = None
    for attempt in range(max_retries):
        try:
            tk = _ticker(symbol, session)
            try:
                info = tk.info or {}
            except Exception:
                info = {}
            annual = _statement_block(tk.income_stmt)
            quarterly = _statement_block(tk.quarterly_income_stmt)
            try:
                hist = tk.history(period=config.PRICE_LOOKBACK, auto_adjust=True)
            except Exception:
                hist = None

            valuation = {f: info.get(f) for f in config.VALUATION_FIELDS}
            has_data = any(
                any(not math.isnan(x) for x in annual.get(k, []))
                for k in ("revenue", "ebitda", "earnings")
            )
            return {
                "symbol": symbol,
                "asof": datetime.now(timezone.utc).isoformat(),
                "annual": annual,
                "quarterly": quarterly,
                "valuation": valuation,
                "prices": _trailing_returns(hist),
                "fetch_ok": bool(has_data or valuation.get("marketCap")),
            }
        except Exception as err:  # noqa: BLE001 — broad on purpose, then back off
            last_err = err
            if attempt < max_retries - 1:
                time.sleep(config.BACKOFF_BASE * (2**attempt))
    return {
        "symbol": symbol,
        "asof": datetime.now(timezone.utc).isoformat(),
        "annual": {},
        "quarterly": {},
        "valuation": {},
        "prices": {},
        "fetch_ok": False,
        "error": str(last_err) if last_err else "unknown",
    }


def load_or_fetch(symbol: str, session=None, refresh: bool = False,
                  ttl_days: float = config.CACHE_TTL_DAYS) -> dict:
    if not refresh:
        cached = load_raw(symbol, ttl_days=ttl_days)
        if cached is not None:
            return cached
    raw = fetch_raw(symbol, session=session)
    if raw.get("fetch_ok"):
        save_raw(symbol, raw)
    return raw


# --------------------------------------------------------------------------- #
# Build the flat fundamentals + metrics table
# --------------------------------------------------------------------------- #
_ID_COLS = ["symbol", "name", "sector", "industry_group", "industry", "size_bucket", "currency"]
# yfinance .info fields renamed to avoid clobbering financedatabase grouping keys.
_RENAME = {"sector": "yf_sector", "industry": "yf_industry", "currency": "yf_currency"}


def build_fundamentals(
    universe: pd.DataFrame,
    limit: int | None = None,
    symbols: list[str] | None = None,
    refresh: bool = False,
    verbose: bool = True,
) -> pd.DataFrame:
    """Fetch + compute metrics for the universe, returning a flat table."""
    if symbols is not None:
        syms = list(symbols)
    else:
        syms = universe["symbol"].tolist()
        if limit:
            syms = syms[:limit]

    session = make_session()
    rows = []
    n = len(syms)
    for i, sym in enumerate(syms, 1):
        cached = None if refresh else load_raw(sym)
        if cached is not None:
            raw, from_cache = cached, True
        else:
            raw = fetch_raw(sym, session=session)
            if raw.get("fetch_ok"):
                save_raw(sym, raw)
            from_cache = False
        row = metrics.compute_metrics(raw)
        # Rename yfinance info fields that collide with fd grouping columns.
        for src, dst in _RENAME.items():
            if src in row:
                row[dst] = row.pop(src)
        row["fetch_ok"] = raw.get("fetch_ok", False)
        rows.append(row)
        if verbose and (i % 25 == 0 or i == n):
            ok = sum(1 for r in rows if r.get("fetch_ok"))
            print(f"  [{i}/{n}] processed, {ok} with data", flush=True)
        if not from_cache:  # only pause between live network calls
            time.sleep(random.uniform(*config.REQUEST_JITTER))

    metrics_df = pd.DataFrame(rows)
    id_cols = [c for c in _ID_COLS if c in universe.columns]
    out = metrics_df.merge(universe[id_cols], on="symbol", how="left")
    return _sanitize(out)


# yfinance .info occasionally returns strings ('Infinity', 'N/A') for these
# numeric fields, which makes the column object-typed and unwritable to parquet.
_NUMERIC_INFO = [
    "trailingPE", "forwardPE", "enterpriseToEbitda",
    "priceToSalesTrailing12Months", "priceToBook", "pegRatio",
    "marketCap", "enterpriseValue",
]


def _sanitize(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce numeric info fields and strip ±inf so the table is parquet-safe."""
    out = df.copy()
    for col in _NUMERIC_INFO:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    num = out.select_dtypes(include=["number"]).columns
    if len(num):
        out[num] = out[num].replace([np.inf, -np.inf], np.nan)
    return out


def save_fundamentals(df: pd.DataFrame, path: Path = config.FUNDAMENTALS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def load_fundamentals(path: Path = config.FUNDAMENTALS_PATH) -> pd.DataFrame:
    return pd.read_parquet(path)
