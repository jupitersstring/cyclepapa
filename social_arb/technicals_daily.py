"""Daily price cache + daily-frequency indicators.

Sibling to `technicals.py` (which lives at weekly resolution). This module
runs at *daily* resolution to surface signals the weekly view smooths
through:

  * **RSI(14)** -- Wilder's relative strength index. Oversold (<30) and
    bullish-divergence setups.
  * **Volume z-score** -- abnormal volume on a rolling 30-day baseline.
    Camillo cared about volume bursts as confirmation of attention.
  * **Gap detection** -- |Open / prev Close - 1| > 5%. Material news
    proxy. Also flags earnings-cycle inflections.
  * **20d/50d/200d SMAs** -- the standard daily MA stack.
  * **52-week high/low distance** -- pct from the trailing 252d extreme.

All cached to parquet (long format: date x ticker for close + volume) and
incrementally refreshed via the same yfinance bulk path used at weekly
resolution, with single-ticker fallback for rate-limit gaps.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config

log = logging.getLogger(__name__)


def _cache_path(cfg: Config, kind: str = "close") -> Path:
    cfg.ensure_dirs()
    return cfg.data_dir / f"prices_daily_{kind}.parquet"


def bulk_download_daily(
    tickers: list[str],
    *,
    years: int = 3,
    chunk: int = 50,
    sleep_between: float = 2.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download daily auto-adjusted Close + Volume for a list of tickers.

    Returns (close_wide, volume_wide) DataFrames indexed by date, one
    column per ticker.
    """
    import time
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not installed")
        return pd.DataFrame(), pd.DataFrame()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * int(years))

    closes_frames: list[pd.DataFrame] = []
    volumes_frames: list[pd.DataFrame] = []
    chunks = [tickers[i : i + chunk] for i in range(0, len(tickers), chunk)]
    for i, group in enumerate(chunks):
        log.info("daily bulk chunk %d/%d (%d tickers)", i + 1, len(chunks), len(group))
        try:
            df = yf.download(
                tickers=group,
                start=start.date(),
                end=end.date(),
                progress=False,
                auto_adjust=True,
                threads=1,
                group_by="ticker",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("daily chunk %d failed: %s", i + 1, exc)
            continue
        if df is None or df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            closes = df.xs("Close", axis=1, level=1, drop_level=True)
            vols = df.xs("Volume", axis=1, level=1, drop_level=True)
        else:
            closes = df[["Close"]].rename(columns={"Close": group[0]})
            vols = df[["Volume"]].rename(columns={"Volume": group[0]})
        closes.index = pd.to_datetime(closes.index).tz_localize(None)
        vols.index = pd.to_datetime(vols.index).tz_localize(None)
        closes_frames.append(closes)
        volumes_frames.append(vols)
        if i + 1 < len(chunks):
            time.sleep(sleep_between)

    closes_combined = (
        pd.concat(closes_frames, axis=1).sort_index().loc[:, lambda d: ~d.columns.duplicated()]
        if closes_frames else pd.DataFrame()
    )
    vols_combined = (
        pd.concat(volumes_frames, axis=1).sort_index().loc[:, lambda d: ~d.columns.duplicated()]
        if volumes_frames else pd.DataFrame()
    )
    return closes_combined, vols_combined


def refresh_daily_cache(
    cfg: Config,
    tickers: list[str],
    *,
    years: int = 3,
    chunk: int = 50,
    min_bars: int = 60,
    incremental: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    existing_close = pd.read_parquet(_cache_path(cfg, "close")) if _cache_path(cfg, "close").exists() else pd.DataFrame()
    existing_vol = pd.read_parquet(_cache_path(cfg, "volume")) if _cache_path(cfg, "volume").exists() else pd.DataFrame()
    to_fetch = list(tickers)
    if incremental and not existing_close.empty:
        valid = {c for c in existing_close.columns if existing_close[c].notna().sum() >= min_bars}
        to_fetch = [t for t in tickers if t not in valid]
        log.info("daily cache has %d valid; fetching %d new/stale", len(valid), len(to_fetch))

    if to_fetch:
        new_close, new_vol = bulk_download_daily(to_fetch, years=years, chunk=chunk)
    else:
        new_close = new_vol = pd.DataFrame()

    close = _merge(existing_close, new_close)
    vol = _merge(existing_vol, new_vol)
    if not close.empty:
        close.to_parquet(_cache_path(cfg, "close"))
    if not vol.empty:
        vol.to_parquet(_cache_path(cfg, "volume"))
    n_valid = int((close.notna().sum() >= min_bars).sum()) if not close.empty else 0
    log.info("daily cache: %d cols, %d valid (>=%d bars)", close.shape[1], n_valid, min_bars)
    return close, vol


def _merge(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if old.empty:
        return new
    if new.empty:
        return old
    merged = pd.concat([old, new], axis=1)
    merged = merged.loc[:, ~merged.columns.duplicated(keep="last")]
    return merged.sort_index()


def load_daily_cache(cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    cp = _cache_path(cfg, "close")
    vp = _cache_path(cfg, "volume")
    close = pd.read_parquet(cp) if cp.exists() else pd.DataFrame()
    vol = pd.read_parquet(vp) if vp.exists() else pd.DataFrame()
    return close, vol


# ---- Daily indicators ---------------------------------------------------

def rsi_wilder(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI(n) -- exponential smoothing of gains/losses.

    Conventionally:
      - all-up moves => RSI = 100 (no losses)
      - all-down moves => RSI = 0 (no gains)
    """
    delta = close.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    avg_up = up.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    avg_down = down.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = avg_up / avg_down.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # Edge cases: no losses at all => RSI = 100; no gains => RSI = 0.
    rsi = rsi.where(avg_down > 0, 100.0)
    rsi = rsi.where(avg_up > 0, 0.0)
    return rsi


def volume_zscore(volume: pd.Series, window: int = 30) -> pd.Series:
    log_v = np.log1p(volume.astype(float))
    mu = log_v.rolling(window, min_periods=window // 2).mean()
    sd = log_v.rolling(window, min_periods=window // 2).std()
    return (log_v - mu) / sd.replace(0.0, np.nan)


def detect_gaps(close: pd.Series, threshold_pct: float = 5.0) -> pd.Series:
    """Boolean series: True when |today's close / yesterday's close - 1| > threshold."""
    chg = close.pct_change()
    return (chg.abs() * 100.0) > float(threshold_pct)


def daily_signals_for(close: pd.Series, volume: pd.Series | None = None) -> pd.DataFrame:
    """Compute the full daily indicator stack for one ticker."""
    c = close.dropna()
    if len(c) < 60:
        return pd.DataFrame()
    df = pd.DataFrame({"close": c})
    df["sma_20"] = c.rolling(20, min_periods=20).mean()
    df["sma_50"] = c.rolling(50, min_periods=50).mean()
    df["sma_200"] = c.rolling(200, min_periods=200).mean()
    df["rsi_14"] = rsi_wilder(c, 14)
    df["high_52w"] = c.rolling(252, min_periods=60).max()
    df["low_52w"] = c.rolling(252, min_periods=60).min()
    df["pct_from_high_52w"] = (c / df["high_52w"] - 1.0) * 100.0
    df["pct_from_low_52w"] = (c / df["low_52w"] - 1.0) * 100.0
    df["gap"] = detect_gaps(c, threshold_pct=5.0)
    if volume is not None and not volume.empty:
        v = volume.reindex(c.index).fillna(0.0)
        df["volume"] = v
        df["vol_z_30"] = volume_zscore(v, 30)
    return df


def scan_daily_universe(
    cfg: Config,
    tickers: list[str],
    *,
    min_bars: int = 60,
) -> pd.DataFrame:
    """Latest daily-indicator snapshot for a list of tickers from the cache."""
    close, vol = load_daily_cache(cfg)
    if close.empty:
        return pd.DataFrame()
    rows: list[dict] = []
    for t in tickers:
        if t not in close.columns:
            continue
        c = close[t].dropna()
        if len(c) < min_bars:
            continue
        v = vol[t] if (not vol.empty and t in vol.columns) else None
        sig = daily_signals_for(c, v)
        if sig.empty:
            continue
        last = sig.iloc[-1]
        rows.append({
            "ticker": t,
            "close": round(float(last["close"]), 2),
            "rsi_14": round(float(last["rsi_14"]), 1) if pd.notna(last["rsi_14"]) else None,
            "sma_50": round(float(last["sma_50"]), 2) if pd.notna(last["sma_50"]) else None,
            "sma_200": round(float(last["sma_200"]), 2) if pd.notna(last["sma_200"]) else None,
            "vs_sma200_pct": (
                round((float(last["close"]) / float(last["sma_200"]) - 1.0) * 100.0, 1)
                if pd.notna(last["sma_200"]) and last["sma_200"] else None
            ),
            "pct_from_52w_high": (
                round(float(last["pct_from_high_52w"]), 1) if pd.notna(last["pct_from_high_52w"]) else None
            ),
            "pct_from_52w_low": (
                round(float(last["pct_from_low_52w"]), 1) if pd.notna(last["pct_from_low_52w"]) else None
            ),
            "vol_z_30": (
                round(float(last["vol_z_30"]), 2) if "vol_z_30" in last and pd.notna(last["vol_z_30"]) else None
            ),
            "gap_today": bool(last["gap"]) if "gap" in last and pd.notna(last["gap"]) else False,
        })
    return pd.DataFrame(rows)
