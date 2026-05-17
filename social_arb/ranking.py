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


def crossover_intersect_social(
    cfg: Config,
    technical_scan: pd.DataFrame,
    *,
    signals: tuple[str, ...] = ("golden_cross_recent", "hma_flip_up_recent"),
    min_total_mentions: int = 5,
) -> pd.DataFrame:
    """Intersect a technical scan with social mentions.

    Returns the rows from `technical_scan` for which we have at least
    `min_total_mentions` stored mentions, sorted by descending total
    attention.
    """
    if technical_scan is None or technical_scan.empty:
        return pd.DataFrame()
    daily = _per_ticker_daily(cfg)
    if daily.empty:
        return technical_scan.head(0)
    totals = daily.groupby("ticker")["mentions"].sum().rename("total_mentions")
    sent = daily.groupby("ticker")["sentiment_mean"].mean().rename("sentiment_mean")
    soc = pd.concat([totals, sent], axis=1).reset_index()
    out = technical_scan.merge(soc, on="ticker", how="inner")
    out = out[out["total_mentions"] >= int(min_total_mentions)]
    if signals:
        out = out[out["signal"].isin(list(signals)) | out["state"].isin(("golden", "hma_up"))]
    return out.sort_values(["total_mentions", "hma_slope_20w"], ascending=[False, False]).reset_index(drop=True)


@dataclass
class CamilloParams:
    """Weights for the Camillo composite.

    Each weight is roughly normalised so a healthy contributor adds ~1 point.
    Defaults reflect the priorities in Schwager's Unknown Market Wizards
    chapter: attention growth + organic positive sentiment + technical
    confirmation + NOT being a stretched / consensus name.
    """
    w_mention_z: float = 1.0          # latest mention z-score (capped 0..6)
    w_sentiment: float = 3.0          # sentiment_14d, multiplied to z-units
    w_growth: float = 1.5             # log_growth_7d (capped at +3.0)
    w_tech_confirm: float = 1.0       # +1 if state in {hma_up, golden}
    w_clean_entry: float = 1.5        # +1.5 if -25 <= vs SMA40 <= +10
    w_stretched_pen: float = 0.05     # subtract per % above +25% of SMA40
    w_smallcap: float = 0.5           # +0.5 if close <= $50 (price proxy)
    w_microcap: float = 0.3           # additional +0.3 if close <= $10


def camillo_ranking(
    cfg: Config,
    technical_scan: pd.DataFrame,
    *,
    params: CamilloParams | None = None,
    min_total_mentions: int = 5,
    top: int = 25,
) -> pd.DataFrame:
    """Camillo composite: socially-attended, technically confirmed, NOT consensus.

    The score deliberately *penalises* tickers more than 25% above their 40w
    SMA -- per Camillo, when a name is that stretched the information edge
    is gone (Wall Street has caught up). It also tilts to small/mid-caps
    on price -- a crude but useful proxy since financedatabase doesn't ship
    market-cap natively and live mcap lookups would burn yfinance calls.
    """
    if params is None:
        params = CamilloParams()
    if technical_scan is None or technical_scan.empty:
        return pd.DataFrame()

    soc = bullish_ranking(cfg, params=RankParams(min_total_mentions=min_total_mentions), top=10000)
    if soc.empty:
        return pd.DataFrame()

    merged = soc.merge(technical_scan, on="ticker", how="inner")
    if merged.empty:
        return merged

    def _score(row) -> float:
        # Hard exclusions -- not bullish under Camillo's framework, period:
        #   - attention is actually FADING (z < 0)
        #   - price is in confirmed downtrend (death or hma_down)
        z = row.get("latest_z")
        state = row.get("state")
        if state in ("death", "hma_down"):
            return float("-inf")
        if pd.notna(z) and z < -1.0:
            return float("-inf")

        s = 0.0
        if pd.notna(z) and z > 0:
            s += params.w_mention_z * min(float(z), 6.0)
        sent = row.get("sentiment_14d")
        if pd.notna(sent) and sent > 0:
            s += params.w_sentiment * float(sent)
        grow = row.get("log_growth_7d")
        if pd.notna(grow) and grow > 0:
            s += params.w_growth * min(float(grow), 3.0)
        if state in ("hma_up", "golden"):
            s += params.w_tech_confirm
        v40 = row.get("close_vs_sma40_pct")
        if pd.notna(v40):
            v40f = float(v40)
            if -25.0 <= v40f <= 10.0:
                s += params.w_clean_entry
            if v40f > 25.0:
                s -= params.w_stretched_pen * (v40f - 25.0)
        close = row.get("close")
        if pd.notna(close):
            if float(close) <= 50.0:
                s += params.w_smallcap
            if float(close) <= 10.0:
                s += params.w_microcap
        return round(s, 3)

    merged["camillo_score"] = merged.apply(_score, axis=1)
    merged = merged[merged["camillo_score"] > float("-inf")]
    out = merged.sort_values("camillo_score", ascending=False)
    cols = [
        "ticker", "camillo_score",
        "latest_z", "sentiment_14d", "log_growth_7d", "total_mentions",
        "close", "close_vs_sma40_pct", "state", "weeks_in_state",
        "signal", "hma_slope_20w",
    ]
    cols = [c for c in cols if c in out.columns]
    return out[cols].head(top).reset_index(drop=True)


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
