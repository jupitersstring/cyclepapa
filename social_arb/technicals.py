"""Weekly technical signals: classic MA crossovers + Hull MA.

Includes a bulk scanner for hundreds-to-thousands of tickers using
yfinance.download() and a parquet-cached price store so re-runs are
near-instant.

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
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
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


# ---- Bulk price cache ----------------------------------------------------

def _cache_path(cfg: Config) -> Path:
    cfg.ensure_dirs()
    return cfg.data_dir / "prices_weekly.parquet"


def bulk_download_weekly(
    tickers: list[str],
    *,
    years: int = 5,
    chunk: int = 50,
    max_workers: int = 1,
    sleep_between: float = 2.0,
    retry_failed: bool = True,
) -> pd.DataFrame:
    """Bulk-download daily closes via yfinance.download and resample weekly.

    Returns a wide DataFrame indexed by Friday weekly close with one column
    per ticker (auto-adjusted close). Tickers that fail to fetch are
    silently dropped.

    Yahoo rate-limits bursty parallel requests aggressively. Defaults here
    are deliberately conservative: chunks of 50, 2-second sleep between
    chunks, single threaded. One follow-up retry pass for failed tickers
    after a longer cool-down.
    """
    try:
        import time
        import yfinance as yf
    except ImportError:  # pragma: no cover
        log.warning("yfinance not installed")
        return pd.DataFrame()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * int(years))

    def _fetch_chunk(group: list[str]) -> pd.DataFrame | None:
        try:
            df = yf.download(
                tickers=group,
                start=start.date(),
                end=end.date(),
                progress=False,
                auto_adjust=True,
                threads=min(max_workers, 4),
                group_by="ticker",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("bulk download chunk failed: %s", exc)
            return None
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            closes = df.xs("Close", axis=1, level=1, drop_level=True)
        else:
            closes = df[["Close"]].rename(columns={"Close": group[0]})
        closes.index = pd.to_datetime(closes.index).tz_localize(None)
        return closes

    frames: list[pd.DataFrame] = []
    failed: list[str] = []
    chunks = [tickers[i : i + chunk] for i in range(0, len(tickers), chunk)]
    for i, group in enumerate(chunks):
        log.info("bulk download chunk %d/%d (%d tickers)", i + 1, len(chunks), len(group))
        closes = _fetch_chunk(group)
        if closes is None or closes.empty:
            failed.extend(group)
        else:
            # Identify which tickers came back empty (rate-limited).
            empty_cols = [c for c in closes.columns if closes[c].notna().sum() == 0]
            failed.extend(empty_cols)
            frames.append(closes)
        if i + 1 < len(chunks):
            time.sleep(sleep_between)

    if retry_failed and failed:
        log.info("retry pass for %d failed tickers (cool-down 10s)", len(failed))
        time.sleep(10.0)
        retry_chunks = [failed[i : i + chunk] for i in range(0, len(failed), chunk)]
        for i, group in enumerate(retry_chunks):
            log.info("retry chunk %d/%d (%d tickers)", i + 1, len(retry_chunks), len(group))
            closes = _fetch_chunk(group)
            if closes is not None and not closes.empty:
                frames.append(closes)
            if i + 1 < len(retry_chunks):
                time.sleep(sleep_between * 2)

    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, axis=1).sort_index()
    combined = combined.loc[:, ~combined.columns.duplicated()]
    weekly = combined.resample("W-FRI").last().dropna(how="all")
    return weekly


def refresh_price_cache(
    cfg: Config,
    tickers: list[str],
    *,
    years: int = 5,
    chunk: int = 200,
    incremental: bool = True,
    min_bars: int = 42,
    stooq_fallback: bool = True,
    stooq_sleep: float = 0.25,
) -> pd.DataFrame:
    """Bulk-download and persist to parquet. Returns the cached DataFrame.

    If `incremental=True`, only fetch tickers that are missing or have fewer
    than `min_bars` weekly bars in the existing cache. Merges into the
    existing parquet so prior fetches survive yfinance rate-limit gaps.
    """
    existing = load_price_cache(cfg) if incremental else pd.DataFrame()
    to_fetch = list(tickers)
    if not existing.empty:
        valid = {c for c in existing.columns if existing[c].notna().sum() >= min_bars}
        to_fetch = [t for t in tickers if t not in valid]
        log.info(
            "cache already has %d valid tickers; fetching %d new/stale",
            len(valid), len(to_fetch),
        )
    if to_fetch:
        weekly_new = bulk_download_weekly(to_fetch, years=years, chunk=chunk)
    else:
        weekly_new = pd.DataFrame()

    if existing.empty and weekly_new.empty:
        weekly = pd.DataFrame()
    elif existing.empty:
        weekly = weekly_new
    elif weekly_new.empty:
        weekly = existing
    else:
        weekly = pd.concat([existing, weekly_new], axis=1)
        weekly = weekly.loc[:, ~weekly.columns.duplicated(keep="last")]
        weekly = weekly.sort_index()

    # Stooq fallback for any ticker yfinance still hasn't covered.
    if stooq_fallback:
        if weekly.empty:
            valid = set()
        else:
            valid = {c for c in weekly.columns if weekly[c].notna().sum() >= min_bars}
        still_missing = [t for t in tickers if t not in valid]
        if still_missing:
            log.info("stooq fallback for %d tickers (yfinance failed)", len(still_missing))
            from .prices_stooq import stooq_bulk
            stooq_df = stooq_bulk(still_missing, years=years, sleep_between=stooq_sleep, min_bars=min_bars)
            if not stooq_df.empty:
                if weekly.empty:
                    weekly = stooq_df
                else:
                    weekly = pd.concat([weekly, stooq_df], axis=1)
                    weekly = weekly.loc[:, ~weekly.columns.duplicated(keep="last")]
                    weekly = weekly.sort_index()
    if weekly.empty:
        return weekly
    path = _cache_path(cfg)
    weekly.to_parquet(path)
    n_valid = int((weekly.notna().sum() >= min_bars).sum())
    log.info(
        "cached %d weekly bars x %d cols (%d valid >= %d bars) -> %s",
        len(weekly), weekly.shape[1], n_valid, min_bars, path,
    )
    return weekly


def load_price_cache(cfg: Config) -> pd.DataFrame:
    path = _cache_path(cfg)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


# ---- Bulk signal computation --------------------------------------------

def signals_for_close(
    close: pd.Series,
    *,
    short_w: int = 10,
    long_w: int = 40,
    hma_short_w: int = 9,
    hma_long_w: int = 20,
) -> pd.DataFrame | None:
    """Compute the same signal columns as `weekly_signals` for an already-
    weekly close series. Returns None if there isn't enough data."""
    w = close.dropna()
    if len(w) < max(long_w, hma_long_w) + 2:
        return None
    sma_s = sma(w, short_w)
    sma_l = sma(w, long_w)
    hma_s = hma(w, hma_short_w)
    hma_l = hma(w, hma_long_w)
    hma_slope = hma_l.diff()

    df = pd.DataFrame({
        "close": w,
        f"sma_{short_w}w": sma_s,
        f"sma_{long_w}w": sma_l,
        f"hma_{hma_short_w}w": hma_s,
        f"hma_{hma_long_w}w": hma_l,
        f"hma_slope_{hma_long_w}w": hma_slope,
    })
    df["gc"] = ((sma_s > sma_l) & (sma_s.shift(1) <= sma_l.shift(1))).fillna(False)
    df["dc"] = ((sma_s < sma_l) & (sma_s.shift(1) >= sma_l.shift(1))).fillna(False)
    df["hma_flip_up"] = ((hma_s > hma_l) & (hma_s.shift(1) <= hma_l.shift(1))).fillna(False)
    df["hma_flip_down"] = ((hma_s < hma_l) & (hma_s.shift(1) >= hma_l.shift(1))).fillna(False)

    sa = sma_s > sma_l
    ha = hma_s > hma_l
    hr = hma_slope > 0
    state = np.where(
        sa.isna() | ha.isna() | hr.isna(), "warmup",
        np.where(sa & ha & hr, "golden",
        np.where((~sa) & (~ha) & (~hr), "death",
        np.where(ha & hr, "hma_up",
        np.where((~ha) & (~hr), "hma_down", "mixed")))),
    )
    df["state"] = state
    # weeks_since_state without a Python loop.
    chg = df["state"] != df["state"].shift(1)
    grp = chg.cumsum()
    df["weeks_since_state"] = df.groupby(grp).cumcount()
    return df


def scan_universe(
    cfg: Config,
    tickers: list[str],
    *,
    years: int = 5,
    use_cache: bool = True,
    lookback_weeks: int = 4,
) -> pd.DataFrame:
    """Scan a large universe by relying on the bulk price cache.

    If `use_cache=True` and a parquet cache exists, use it; otherwise
    `refresh_price_cache` first.
    """
    weekly = load_price_cache(cfg) if use_cache else pd.DataFrame()
    if weekly.empty:
        weekly = refresh_price_cache(cfg, tickers, years=years)
    if weekly.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for ticker in tickers:
        if ticker not in weekly.columns:
            continue
        s = weekly[ticker].dropna()
        sig = signals_for_close(s)
        if sig is None or sig.empty:
            continue
        last = sig.iloc[-1]
        tail = sig.tail(lookback_weeks)
        signal = "none"
        if tail["gc"].any():
            signal = "golden_cross_recent"
        elif tail["dc"].any():
            signal = "death_cross_recent"
        elif tail["hma_flip_up"].any():
            signal = "hma_flip_up_recent"
        elif tail["hma_flip_down"].any():
            signal = "hma_flip_down_recent"

        close_v = float(last["close"])
        sma40 = float(last.get("sma_40w", np.nan))
        rows.append({
            "ticker": ticker,
            "close": round(close_v, 2),
            "sma_10w": round(float(last.get("sma_10w", np.nan)), 2),
            "sma_40w": round(sma40, 2) if pd.notna(sma40) else None,
            "hma_20w": round(float(last.get("hma_20w", np.nan)), 2),
            "hma_slope_20w": round(float(last.get("hma_slope_20w", np.nan)), 3),
            "state": str(last["state"]),
            "weeks_in_state": int(last["weeks_since_state"]),
            "signal": signal,
            "close_vs_sma40_pct": (
                round(100.0 * (close_v / sma40 - 1.0), 1)
                if pd.notna(sma40) and sma40 > 0 else None
            ),
        })
    return pd.DataFrame(rows)


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
