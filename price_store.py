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


def _safe_name(ticker: str) -> str:
    # parquet filenames can't contain ':' or '/'; replace exotic chars
    return ticker.replace("/", "_").replace(":", "_") + ".parquet"


def _path(ticker: str) -> Path:
    return DATA_DIR / _safe_name(ticker)


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _age_hours(p: Path) -> float:
    if not p.exists():
        return float("inf")
    return (time.time() - p.stat().st_mtime) / 3600.0


def _download(ticker: str, period: str = "5y") -> pd.DataFrame | None:
    try:
        d = yf.download(ticker, period=period, interval="1wk",
                        progress=False, auto_adjust=True)
    except Exception:
        return None
    if d is None or d.empty:
        return None
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    # Bad-tick hygiene
    bad = (d["Low"] <= 0) | d["Low"].isna()
    if bad.any():
        d.loc[bad, "Low"] = d.loc[bad, ["Open", "Close"]].min(axis=1)
    return d.dropna(subset=["Close", "Volume"])


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
