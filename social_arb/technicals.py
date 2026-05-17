"""Weekly technical signals: classic MA crossovers + Hull MA.

Free price data via yfinance. We expose three things:

  1. `wma`, `hma` -- weighted MA and Hull MA primitives.
  2. `weekly_signals(ticker)` -- single-ticker DataFrame with:
       close, sma_10w, sma_40w, hma_9w, hma_20w, hma_slope_20w,
       gc (golden cross today), dc (death cross today),
       hma_flip_up, hma_flip_down,
       state ('golden', 'death', 'hma_up', 'hma_down', 'mixed', 'neutral'),
       days_since_state
  3. `scan_technicals(tickers)` -- one-row-per-ticker snapshot for a list.

Conventions:

* Weekly bars are Friday-close resampled from daily auto-adjusted closes.
* Short/long crossover defaults to 10w / 40w (= 50d / 200d in trading-day
  units, which is the standard "Mansfield" / golden-cross spec).
* Hull MA: HMA(n) = WMA(2 WMA(n/2) - WMA(n), sqrt(n)). Alan Hull's
  reduced-lag MA -- often used in 9-period and 20-period forms.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .prices import daily_close

log = logging.getLogger(__name__)


# ---- MA primitives --------------------------------------------------------

def wma(series: pd.Series, n: int) -> pd.Series:
    """Linearly-weighted moving average over n periods."""
    if n <= 1:
        return series.copy()
    weights = np.arange(1, n + 1, dtype=float)
    weights /= weights.sum()
    return series.rolling(n, min_periods=n).apply(
        lambda x: float(np.dot(x, weights)), raw=True
    )


def hma(series: pd.Series, n: int) -> pd.Series:
    """Hull moving average: WMA(2*WMA(n/2) - WMA(n), sqrt(n))."""
    if n <= 1:
        return series.copy()
    half = max(int(n // 2), 1)
    sqrt_n = max(int(round(math.sqrt(n))), 1)
    inner = 2 * wma(series, half) - wma(series, n)
    return wma(inner, sqrt_n)


def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n, min_periods=n).mean()


# ---- Weekly resample -----------------------------------------------------

def to_weekly(close: pd.Series) -> pd.Series:
    """Resample a daily close series to weekly (Friday close)."""
    if close.empty:
        return close
    s = close.copy()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.resample("W-FRI").last().dropna()


# ---- Signal computation --------------------------------------------------

def weekly_signals(
    ticker: str,
    *,
    years: int = 5,
    short_w: int = 10,
    long_w: int = 40,
    hma_short_w: int = 9,
    hma_long_w: int = 20,
) -> pd.DataFrame:
    """Return weekly OHLC-derived technical state for one ticker."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * int(years))
    close = daily_close(ticker, start, end)
    if close.empty:
        return pd.DataFrame()

    w = to_weekly(close).rename("close")
    if len(w) < max(long_w, hma_long_w) + 2:
        return pd.DataFrame()

    sma_s = sma(w, short_w).rename(f"sma_{short_w}w")
    sma_l = sma(w, long_w).rename(f"sma_{long_w}w")
    hma_s = hma(w, hma_short_w).rename(f"hma_{hma_short_w}w")
    hma_l = hma(w, hma_long_w).rename(f"hma_{hma_long_w}w")
    hma_slope = hma_l.diff().rename(f"hma_slope_{hma_long_w}w")

    df = pd.concat([w, sma_s, sma_l, hma_s, hma_l, hma_slope], axis=1)

    cross_up_sma = (sma_s > sma_l) & (sma_s.shift(1) <= sma_l.shift(1))
    cross_dn_sma = (sma_s < sma_l) & (sma_s.shift(1) >= sma_l.shift(1))
    cross_up_hma = (hma_s > hma_l) & (hma_s.shift(1) <= hma_l.shift(1))
    cross_dn_hma = (hma_s < hma_l) & (hma_s.shift(1) >= hma_l.shift(1))
    df["gc"] = cross_up_sma.fillna(False)
    df["dc"] = cross_dn_sma.fillna(False)
    df["hma_flip_up"] = cross_up_hma.fillna(False)
    df["hma_flip_down"] = cross_dn_hma.fillna(False)

    sma_above = (df[f"sma_{short_w}w"] > df[f"sma_{long_w}w"])
    hma_above = (df[f"hma_{hma_short_w}w"] > df[f"hma_{hma_long_w}w"])
    hma_rising = hma_slope > 0
    state = []
    for sa, ha, hr in zip(sma_above, hma_above, hma_rising):
        if pd.isna(sa) or pd.isna(ha) or pd.isna(hr):
            state.append("warmup")
        elif sa and ha and hr:
            state.append("golden")
        elif (not sa) and (not ha) and (not hr):
            state.append("death")
        elif ha and hr:
            state.append("hma_up")
        elif (not ha) and (not hr):
            state.append("hma_down")
        else:
            state.append("mixed")
    df["state"] = state

    # days_since_state: weeks since most recent state change.
    weeks_since = []
    last_state = None
    streak = 0
    for s in df["state"]:
        if s != last_state:
            streak = 0
            last_state = s
        weeks_since.append(streak)
        streak += 1
    df["weeks_since_state"] = weeks_since
    return df


def scan_technicals(tickers: list[str], **kwargs) -> pd.DataFrame:
    """Snapshot the latest weekly state for each ticker.

    Returns one row per ticker with the most recent close, MAs, state, and
    "weeks since" plus a `signal` column that surfaces the strongest fresh
    event in the trailing 4 weeks (golden_cross_recent / hma_flip_up_recent
    / etc.).
    """
    rows: list[dict] = []
    for t in tickers:
        try:
            df = weekly_signals(t, **kwargs)
        except Exception as exc:  # noqa: BLE001
            log.warning("technicals failed for %s: %s", t, exc)
            continue
        if df.empty:
            continue
        last = df.iloc[-1]
        tail4 = df.tail(4)
        # Strongest fresh signal: prefer GC/DC over HMA flip; bullish over mixed.
        signal = "none"
        if tail4["gc"].any():
            signal = "golden_cross_recent"
        elif tail4["dc"].any():
            signal = "death_cross_recent"
        elif tail4["hma_flip_up"].any():
            signal = "hma_flip_up_recent"
        elif tail4["hma_flip_down"].any():
            signal = "hma_flip_down_recent"

        rows.append({
            "ticker": t,
            "close": round(float(last["close"]), 2),
            "sma_10w": round(float(last.get("sma_10w", np.nan)), 2),
            "sma_40w": round(float(last.get("sma_40w", np.nan)), 2),
            "hma_9w": round(float(last.get("hma_9w", np.nan)), 2),
            "hma_20w": round(float(last.get("hma_20w", np.nan)), 2),
            "hma_slope_20w": round(float(last.get("hma_slope_20w", np.nan)), 3),
            "state": last["state"],
            "weeks_in_state": int(last["weeks_since_state"]),
            "signal": signal,
            "close_vs_sma40_pct": round(
                100.0 * (float(last["close"]) / float(last["sma_40w"]) - 1.0), 1
            ) if pd.notna(last.get("sma_40w")) else None,
        })
    return pd.DataFrame(rows)
