"""Cross-ticker ranking: most bullish + strongest weekly momentum.

Two scores are computed from the stored mention table:

  * **bullish_score** -- composite of (mention z-score) + (mean sentiment)
    + (recent mention growth). Tickers with positive attention AND positive
    sentiment AND accelerating mentions rank highest. This is the closest
    free-data analog to Camillo's "needle-moving consumer trend with
    bullish framing."

  * **weekly_momentum** -- last-7-days mentions vs prior-7-days mentions,
    expressed as a log ratio (so 2x = 0.69, 0.5x = -0.69). Reported alongside
    sentiment so the user can distinguish "spiking AND happy" from
    "spiking AND angry" (the GME / short-squeeze fingerprint).

Both functions return a tidy DataFrame ranked descending.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .anomaly import AnomalyParams, ewma_zscore
from .config import Config
from .storage import daily_counts


@dataclass
class RankParams:
    min_total_mentions: int = 20   # filter noise floor
    halflife_days: int = 14
    window_days: int = 90
    w_zscore: float = 1.0
    w_sentiment: float = 1.0
    w_growth: float = 0.75


def _per_ticker_daily(cfg: Config) -> pd.DataFrame:
    """Returns (date, ticker, mentions, sentiment_mean) collapsed across sources."""
    df = daily_counts(cfg)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    out = df.groupby(["date", "ticker"]).agg(
        mentions=("mentions", "sum"),
        sentiment_mean=("sentiment_mean", "mean"),
    ).reset_index()
    return out


def _ticker_series(df: pd.DataFrame, ticker: str) -> tuple[pd.Series, pd.Series]:
    sub = df[df["ticker"] == ticker].set_index("date").sort_index()
    if sub.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    mentions = sub["mentions"].astype(float).asfreq("D", fill_value=0.0)
    sent = sub["sentiment_mean"].astype(float).reindex(mentions.index).fillna(0.0)
    return mentions, sent


def bullish_ranking(cfg: Config, params: RankParams | None = None, top: int = 25) -> pd.DataFrame:
    if params is None:
        params = RankParams()
    df = _per_ticker_daily(cfg)
    if df.empty:
        return pd.DataFrame(columns=["ticker", "bullish_score"])
    cutoff = df["date"].max() - pd.Timedelta(days=int(params.window_days))
    recent = df[df["date"] >= cutoff]
    rows: list[dict] = []
    for ticker, sub in recent.groupby("ticker"):
        total = int(sub["mentions"].sum())
        if total < params.min_total_mentions:
            continue
        mentions, sent = _ticker_series(recent, ticker)
        if len(mentions) < 3:
            continue
        # z-score of latest day vs trailing distribution.
        z_df = ewma_zscore(mentions, AnomalyParams(params.halflife_days, 3.0, min_periods=3))
        latest_z = float(z_df["z"].iloc[-1]) if not z_df["z"].dropna().empty else 0.0
        # Sentiment over last min(14, span) days.
        tail = sent.tail(14)
        sentiment_tail = float(tail.mean()) if not tail.empty else 0.0
        # Growth: log ratio of last 7d vs prior 7d.
        last7 = mentions.tail(7).sum()
        prev7 = mentions.tail(14).head(7).sum()
        growth = float(np.log1p(last7) - np.log1p(prev7))
        score = (
            params.w_zscore * (latest_z if np.isfinite(latest_z) else 0.0)
            + params.w_sentiment * sentiment_tail * 3.0   # scale sentiment into z-units
            + params.w_growth * growth
        )
        rows.append({
            "ticker": ticker,
            "bullish_score": round(score, 3),
            "latest_z": round(latest_z, 2) if np.isfinite(latest_z) else None,
            "sentiment_14d": round(sentiment_tail, 3),
            "mentions_7d": int(last7),
            "mentions_prev7d": int(prev7),
            "log_growth_7d": round(growth, 3),
            "total_mentions": total,
        })
    out = pd.DataFrame(rows).sort_values("bullish_score", ascending=False).reset_index(drop=True)
    return out.head(int(top))


def weekly_momentum(cfg: Config, min_total: int = 10, top: int = 25) -> pd.DataFrame:
    """Ranks by last-7d vs prior-7d mention growth (log ratio).

    Returns ticker, mentions_7d, mentions_prev7d, log_growth_7d, sentiment_14d,
    label_7d ('bullish_momentum' | 'bearish_momentum' | 'mixed').
    """
    df = _per_ticker_daily(cfg)
    if df.empty:
        return pd.DataFrame()
    end = df["date"].max()
    last7_cutoff = end - pd.Timedelta(days=7)
    prev7_cutoff = end - pd.Timedelta(days=14)
    last7 = df[df["date"] > last7_cutoff].groupby("ticker").agg(
        mentions_7d=("mentions", "sum"),
        sent_7d=("sentiment_mean", "mean"),
    )
    prev7 = df[(df["date"] > prev7_cutoff) & (df["date"] <= last7_cutoff)].groupby("ticker").agg(
        mentions_prev7d=("mentions", "sum"),
        sent_prev7d=("sentiment_mean", "mean"),
    )
    out = last7.join(prev7, how="outer").fillna(0.0).reset_index()
    out["log_growth_7d"] = np.log1p(out["mentions_7d"]) - np.log1p(out["mentions_prev7d"])
    out["sentiment_14d"] = (out["sent_7d"] + out["sent_prev7d"]) / 2.0
    out = out[(out["mentions_7d"] + out["mentions_prev7d"]) >= int(min_total)]
    out["label_7d"] = np.where(
        (out["log_growth_7d"] > 0.5) & (out["sentiment_14d"] >= 0),
        "bullish_momentum",
        np.where(
            (out["log_growth_7d"] > 0.5) & (out["sentiment_14d"] < 0),
            "negative_attention",
            np.where(out["log_growth_7d"] < -0.5, "fading", "stable"),
        ),
    )
    out = out.sort_values("log_growth_7d", ascending=False).reset_index(drop=True)
    return out.head(int(top))
