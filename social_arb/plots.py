"""Plotting helpers for ticker drill-down.

`plot_ticker_panel(ticker)` produces a stacked 3-panel figure:

    Panel 1 (top): weekly close + 10w/40w SMA + 9w/20w Hull MA
    Panel 2 (middle): smoothed weekly mention volume + EMA(short)/EMA(long)
    Panel 3 (bottom): smoothed weekly sentiment + EMA(short)/EMA(long),
                      with the bull/bear cross highlighted

Saves the figure to a PNG and returns the path. Designed for matplotlib
only -- no plotly / no streamlit dep -- so it works in CLI scripts and
the streamlit dashboard already imports matplotlib.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from .config import Config

log = logging.getLogger(__name__)


def _weekly_mentions_sentiment(cfg: Config, ticker: str) -> pd.DataFrame:
    """Return weekly-resampled mention count + sentiment for one ticker."""
    from . import storage
    with storage.connect(cfg) as con:
        df = con.execute(
            "SELECT CAST(timestamp AS DATE) AS d, COUNT(*) AS mentions, "
            "AVG(sentiment) AS sentiment_mean FROM mentions "
            "WHERE ticker = ? GROUP BY 1 ORDER BY 1", [ticker.upper()],
        ).df()
    if df.empty:
        return df
    df["d"] = pd.to_datetime(df["d"])
    df = df.set_index("d").sort_index().asfreq("D")
    df["mentions"] = df["mentions"].fillna(0.0)
    df["sentiment_mean"] = df["sentiment_mean"].ffill()
    weekly = df.resample("W-FRI").agg(
        mentions=("mentions", "sum"),
        sentiment_mean=("sentiment_mean", "mean"),
    )
    return weekly


def _weekly_price(cfg: Config, ticker: str) -> pd.Series:
    from .technicals import load_price_cache
    cache = load_price_cache(cfg)
    if cache.empty or ticker not in cache.columns:
        return pd.Series(dtype=float, name=ticker)
    return cache[ticker].dropna()


def plot_ticker_panel(
    ticker: str,
    *,
    out_dir: Path | str | None = None,
    short: int = 20,
    long: int = 50,
    min_periods_ratio: float = 0.3,
    months: int = 24,
) -> Path | None:
    """Plot the 3-panel chart for `ticker` and save to PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    cfg = Config()
    price = _weekly_price(cfg, ticker)
    social = _weekly_mentions_sentiment(cfg, ticker)
    if price.empty:
        log.warning("no weekly price for %s", ticker)
    if social.empty:
        log.warning("no social mentions for %s", ticker)
    if price.empty and social.empty:
        return None

    end = max(
        price.index.max() if not price.empty else pd.Timestamp.min,
        social.index.max() if not social.empty else pd.Timestamp.min,
    )
    start = end - pd.DateOffset(months=int(months))
    if not price.empty:
        price = price.loc[price.index >= start]
    if not social.empty:
        social = social.loc[social.index >= start]

    # Technicals on the weekly price.
    from .technicals import hma, sma
    sma_10 = sma(price, 10) if not price.empty else pd.Series(dtype=float)
    sma_40 = sma(price, 40) if not price.empty else pd.Series(dtype=float)
    hma_9 = hma(price, 9) if not price.empty else pd.Series(dtype=float)
    hma_20 = hma(price, 20) if not price.empty else pd.Series(dtype=float)

    # EMAs on smoothed social series.
    def _ema_pair(s: pd.Series) -> tuple[pd.Series, pd.Series]:
        sf = s.ffill().fillna(0.0)
        es = sf.ewm(span=short, adjust=False, min_periods=int(short * min_periods_ratio)).mean()
        el = sf.ewm(span=long, adjust=False, min_periods=int(long * min_periods_ratio)).mean()
        return es, el

    if not social.empty:
        m_ema_s, m_ema_l = _ema_pair(social["mentions"])
        s_ema_s, s_ema_l = _ema_pair(social["sentiment_mean"])
        m_smooth = social["mentions"].rolling(4, min_periods=1).mean()
        s_smooth = social["sentiment_mean"].rolling(4, min_periods=1).mean()
    else:
        m_ema_s = m_ema_l = m_smooth = pd.Series(dtype=float)
        s_ema_s = s_ema_l = s_smooth = pd.Series(dtype=float)

    fig, axes = plt.subplots(
        3, 1, figsize=(12, 10), sharex=True,
        gridspec_kw={"height_ratios": [3, 2, 2], "hspace": 0.08},
    )
    ax_p, ax_m, ax_s = axes

    # === Panel 1: price + MAs ===
    if not price.empty:
        ax_p.plot(price.index, price.values, color="#1f1f1f", linewidth=1.6, label="close")
        if sma_10.notna().any():
            ax_p.plot(sma_10.index, sma_10.values, color="#4c78a8", linewidth=1.0, label="SMA 10w", alpha=0.8)
        if sma_40.notna().any():
            ax_p.plot(sma_40.index, sma_40.values, color="#e45756", linewidth=1.0, label="SMA 40w", alpha=0.8)
        if hma_20.notna().any():
            ax_p.plot(hma_20.index, hma_20.values, color="#54a24b", linewidth=1.3, label="HMA 20w")
    ax_p.set_title(f"{ticker.upper()}  ·  weekly price + MAs   /   smoothed social + EMA({short})/EMA({long})",
                   fontsize=13, loc="left")
    ax_p.set_ylabel("Price ($)")
    ax_p.legend(loc="upper left", fontsize=9, frameon=False)
    ax_p.grid(True, alpha=0.25)

    # === Panel 2: smoothed weekly mention volume + EMAs ===
    if not social.empty:
        ax_m.bar(social.index, social["mentions"], width=4.5, color="#cccccc",
                 alpha=0.45, label="weekly mentions")
        ax_m.plot(m_smooth.index, m_smooth.values, color="#888888",
                  linewidth=1.2, label="4w MA")
        if m_ema_s.notna().any():
            ax_m.plot(m_ema_s.index, m_ema_s.values, color="#4c78a8",
                      linewidth=1.6, label=f"EMA({short})")
        if m_ema_l.notna().any():
            ax_m.plot(m_ema_l.index, m_ema_l.values, color="#e45756",
                      linewidth=1.6, label=f"EMA({long})")
    ax_m.set_ylabel("Mentions / week")
    ax_m.legend(loc="upper left", fontsize=9, frameon=False)
    ax_m.grid(True, alpha=0.25)

    # === Panel 3: smoothed weekly sentiment + EMAs + zero line ===
    if not social.empty:
        ax_s.axhline(0.0, color="#999999", linewidth=0.5, linestyle="--")
        ax_s.plot(s_smooth.index, s_smooth.values, color="#888888",
                  linewidth=1.1, alpha=0.8, label="4w MA sentiment")
        if s_ema_s.notna().any():
            ax_s.plot(s_ema_s.index, s_ema_s.values, color="#4c78a8",
                      linewidth=1.8, label=f"EMA({short})")
        if s_ema_l.notna().any():
            ax_s.plot(s_ema_l.index, s_ema_l.values, color="#e45756",
                      linewidth=1.8, label=f"EMA({long})")
        # Shade bullish / bearish region (spread positive / negative)
        if s_ema_s.notna().any() and s_ema_l.notna().any():
            common = s_ema_s.index.intersection(s_ema_l.index)
            es = s_ema_s.loc[common]
            el = s_ema_l.loc[common]
            ax_s.fill_between(common, el, es, where=(es >= el),
                              color="#54a24b", alpha=0.15)
            ax_s.fill_between(common, el, es, where=(es < el),
                              color="#e45756", alpha=0.12)
    ax_s.set_ylabel("Sentiment")
    ax_s.legend(loc="upper left", fontsize=9, frameon=False)
    ax_s.grid(True, alpha=0.25)
    ax_s.set_xlabel("Week (Friday close)")
    ax_s.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax_s.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate(rotation=0, ha="center")

    out_dir = Path(out_dir) if out_dir else cfg.data_dir / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ticker.upper()}_panel.png"
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    log.info("saved plot -> %s", path)
    return path


def plot_many(tickers: Sequence[str], **kwargs) -> list[Path]:
    out: list[Path] = []
    for t in tickers:
        p = plot_ticker_panel(t, **kwargs)
        if p is not None:
            out.append(p)
    return out
