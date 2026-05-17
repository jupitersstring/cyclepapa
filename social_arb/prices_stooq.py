"""Per-ticker price fallback when yfinance.download() rate-limits.

Originally intended to use Stooq.com's free CSV endpoint -- and Stooq is
still a great free source. But Stooq blocks requests from many datacenter
IP ranges, so on cloud runners we fall back to `yfinance.Ticker.history()`,
which goes through a different Yahoo endpoint than `yfinance.download()`
and has separate rate-limit budgets.

The function name is preserved (`stooq_weekly` / `stooq_bulk`) so the
wiring in `technicals.refresh_price_cache` doesn't change. Source
selection happens here.
"""

from __future__ import annotations

import logging
import time

import pandas as pd

log = logging.getLogger(__name__)


def stooq_weekly(ticker: str, *, years: int = 5, **kwargs) -> pd.Series:
    """Single-ticker weekly close via yfinance.Ticker.history (private API).

    Independent of yfinance.download()'s rate-limit budget, so this often
    succeeds when the bulk path is being throttled.
    """
    try:
        import yfinance as yf
    except ImportError:
        return pd.Series(dtype=float, name=ticker)
    try:
        t = yf.Ticker(ticker)
        period = f"{int(years)}y" if years <= 10 else "max"
        h = t.history(period=period, interval="1wk", auto_adjust=True)
    except Exception as exc:  # noqa: BLE001
        log.debug("yf.Ticker.history(%s) failed: %s", ticker, exc)
        return pd.Series(dtype=float, name=ticker)
    if h is None or h.empty or "Close" not in h.columns:
        return pd.Series(dtype=float, name=ticker)
    close = h["Close"].astype(float)
    if isinstance(close.index, pd.DatetimeIndex):
        close.index = close.index.tz_localize(None)
    close.name = ticker
    return close


def stooq_bulk(
    tickers: list[str],
    *,
    years: int = 5,
    sleep_between: float = 0.30,
    min_bars: int = 42,
) -> pd.DataFrame:
    series_list: list[pd.Series] = []
    ok = 0
    for i, t in enumerate(tickers):
        s = stooq_weekly(t, years=years)
        if not s.empty and s.notna().sum() >= min_bars:
            series_list.append(s)
            ok += 1
        if (i + 1) % 50 == 0:
            log.info("fallback fetch: %d/%d (kept %d)", i + 1, len(tickers), ok)
        time.sleep(sleep_between)
    if not series_list:
        return pd.DataFrame()
    df = pd.concat(series_list, axis=1).sort_index()
    df = df.loc[:, ~df.columns.duplicated()]
    weekly = df.resample("W-FRI").last().dropna(how="all")
    log.info("fallback: cached %d tickers x %d weekly bars", weekly.shape[1], len(weekly))
    return weekly
