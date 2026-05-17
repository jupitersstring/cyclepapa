"""Price helpers (yfinance wrapper).

The pipeline only needs daily closes for event studies and overlays in the
dashboard. yfinance is unofficial but free and reliable enough for these
horizons.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

log = logging.getLogger(__name__)


def daily_close(ticker: str, start: datetime | None = None, end: datetime | None = None) -> pd.Series:
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not installed")
        return pd.Series(dtype=float, name=ticker)
    if end is None:
        end = datetime.now(timezone.utc)
    if start is None:
        start = end - timedelta(days=365 * 3)
    df = yf.download(
        ticker,
        start=start.date(),
        end=end.date(),
        progress=False,
        auto_adjust=True,
        threads=False,
    )
    if df is None or df.empty:
        return pd.Series(dtype=float, name=ticker)
    close = df["Close"]
    if isinstance(close, pd.DataFrame):  # multiindex case
        close = close.iloc[:, 0]
    close.name = ticker
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


def returns(close: pd.Series, periods: int = 1) -> pd.Series:
    return close.pct_change(periods=periods)
