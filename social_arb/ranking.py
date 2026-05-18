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

import math

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
class TechScoreParams:
    """Weekly technical Camillo score (price-only, no social).

    Captures the *price* side of Camillo's framework so we can compute it
    historically (years of weekly bars) and then look at *first* and
    *second derivatives* -- which names are climbing the ranks and which
    are accelerating.

    A clean way to surface "this is turning right now" without waiting for
    Wall Street recognition (= the social signal lagging).
    """
    w_state_golden: float = 2.0       # +2 when in golden state (SMA + HMA + slope)
    w_state_hma_up: float = 1.0       # +1 for hma_up only
    w_state_mixed: float = 0.0
    w_state_hma_down: float = -1.0
    w_state_death: float = -2.0
    w_clean_entry: float = 1.5        # -25% <= close vs 40w <= +10%
    w_stretched_pen: float = 0.05     # subtract per % above +25% from SMA40
    w_broken_pen: float = 0.05        # subtract per % below -35% from SMA40
    slope_scale: float = 0.5          # multiplied onto sign(slope)*log(|slope|+1)
    slope_cap: float = 2.0            # cap absolute slope contribution


def technical_score_history(close: pd.Series, params: TechScoreParams | None = None) -> pd.Series:
    """Weekly technical Camillo score history for one ticker.

    Returns a pd.Series indexed like the weekly close, with the score at
    each historical week. Used by `rank_improvers` and `rank_inflecters`.
    """
    if params is None:
        params = TechScoreParams()
    from .technicals import signals_for_close
    sig = signals_for_close(close.dropna())
    if sig is None or sig.empty:
        return pd.Series(dtype=float, name=close.name)

    sma_l = sig["sma_40w"]
    close_v = sig["close"]
    vs_sma40 = (close_v / sma_l - 1.0) * 100.0
    slope = sig["hma_slope_20w"]

    state_map = {
        "golden": params.w_state_golden,
        "hma_up": params.w_state_hma_up,
        "mixed": params.w_state_mixed,
        "hma_down": params.w_state_hma_down,
        "death": params.w_state_death,
    }
    state_pts = sig["state"].map(state_map).astype(float).fillna(0.0)

    clean = ((vs_sma40 >= -25.0) & (vs_sma40 <= 10.0)).astype(float) * params.w_clean_entry
    stretched = np.maximum(vs_sma40 - 25.0, 0.0) * -params.w_stretched_pen
    broken = np.maximum(-(vs_sma40 + 35.0), 0.0) * -params.w_broken_pen

    sl = np.sign(slope.fillna(0.0)) * np.log1p(np.abs(slope.fillna(0.0))) * params.slope_scale
    sl = sl.clip(-params.slope_cap, params.slope_cap)

    score = state_pts + clean + stretched + broken + sl
    score.name = close.name
    return score


def _scores_at(cache: pd.DataFrame, tickers: list[str], weeks: list[int]) -> pd.DataFrame:
    """For a list of (negative) week-offsets like [-8, -4, 0], return a
    DataFrame indexed by ticker with one column per offset."""
    rows: dict[str, dict[int, float]] = {}
    for t in tickers:
        if t not in cache.columns:
            continue
        close = cache[t].dropna()
        if len(close) < 50:
            continue
        sh = technical_score_history(close)
        if sh is None or sh.empty:
            continue
        row: dict[int, float] = {}
        for w in weeks:
            idx = len(sh) - 1 + w  # w is <= 0; w=0 is latest
            if idx < 0 or idx >= len(sh):
                continue
            row[w] = float(sh.iloc[idx])
        if row:
            rows[t] = row
    return pd.DataFrame.from_dict(rows, orient="index")


def rank_improvers(
    cfg: Config,
    tickers: list[str],
    *,
    lookback_weeks: int = 4,
    top: int = 30,
    min_score_now: float | None = None,
) -> pd.DataFrame:
    """Tickers whose technical Camillo score has improved over `lookback_weeks`.

    Ranked by (score_now - score_lookback_ago), descending. Optional
    `min_score_now` keeps the list to currently-bullish names rather than
    "least bearish".
    """
    from .technicals import load_price_cache
    cache = load_price_cache(cfg)
    if cache.empty:
        return pd.DataFrame()
    scores = _scores_at(cache, tickers, weeks=[-lookback_weeks, 0])
    if scores.empty:
        return scores
    scores.columns = ["score_prev", "score_now"]
    scores["improvement"] = scores["score_now"] - scores["score_prev"]
    if min_score_now is not None:
        scores = scores[scores["score_now"] >= float(min_score_now)]
    return _decorate(cfg, cache, scores.sort_values("improvement", ascending=False).head(top))


def social_price_divergence(
    cfg: Config,
    *,
    top: int = 30,
    lookback_weeks: int = 13,
    min_mentions_per_week: float = 2.0,
    min_total_mentions: int = 15,
    require_positive: bool = True,
) -> pd.DataFrame:
    """Find tickers where social attention is leading price.

    For each ticker with enough history we compute:
      social_z = rolling z-score of log(weekly mentions) over `lookback_weeks`
      price_z  = rolling z-score of weekly log-return over same window
      divergence = social_z - price_z   (LATEST WEEK)

    Positive divergence = mentions spiking while price hasn't moved
    (or has even fallen) -- the information-edge zone Camillo trades.
    """
    from .technicals import load_price_cache
    daily = _per_ticker_daily(cfg)
    if daily.empty:
        return pd.DataFrame()
    price_cache = load_price_cache(cfg)
    if price_cache.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for ticker, grp in daily.groupby("ticker"):
        total = int(grp["mentions"].sum())
        if total < int(min_total_mentions):
            continue
        if ticker not in price_cache.columns:
            continue
        # Weekly mention totals.
        m_daily = grp.set_index("date")["mentions"].sort_index()
        m_daily.index = pd.to_datetime(m_daily.index)
        m_weekly = m_daily.asfreq("D", fill_value=0.0).resample("W-FRI").sum()
        if len(m_weekly) < lookback_weeks // 2:
            continue
        if float(m_weekly.mean()) < min_mentions_per_week:
            continue

        m_log = np.log1p(m_weekly.astype(float))
        m_mu = m_log.rolling(lookback_weeks, min_periods=4).mean()
        m_sd = m_log.rolling(lookback_weeks, min_periods=4).std().replace(0.0, np.nan)
        social_z = (m_log - m_mu) / m_sd

        # Aligned weekly returns.
        price = price_cache[ticker].dropna()
        if price.empty:
            continue
        p_w = price.reindex(m_weekly.index).ffill()
        ret = np.log(p_w / p_w.shift(1))
        p_mu = ret.rolling(lookback_weeks, min_periods=4).mean()
        p_sd = ret.rolling(lookback_weeks, min_periods=4).std().replace(0.0, np.nan)
        price_z = (ret - p_mu) / p_sd

        divergence = (social_z - price_z).dropna()
        if divergence.empty:
            continue
        last_div = float(divergence.iloc[-1])
        last_social_z = float(social_z.iloc[-1]) if pd.notna(social_z.iloc[-1]) else 0.0
        last_price_z = float(price_z.iloc[-1]) if pd.notna(price_z.iloc[-1]) else 0.0
        # Mean divergence over last 4 weeks (smooths single-week noise).
        recent_div = float(divergence.tail(4).mean())

        if require_positive and last_div <= 0:
            continue

        rows.append({
            "ticker": ticker,
            "divergence": round(last_div, 2),
            "divergence_4w": round(recent_div, 2),
            "social_z": round(last_social_z, 2),
            "price_z": round(last_price_z, 2),
            "weekly_mentions": float(m_weekly.iloc[-1]),
            "total_mentions": total,
            "close": round(float(price.iloc[-1]), 2),
            "price_4w_return_pct": round(
                (float(price.iloc[-1]) / float(price.iloc[-min(5, len(price))]) - 1.0) * 100.0, 1
            ),
        })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values("divergence", ascending=False).head(int(top)).reset_index(drop=True)
    return out


def sentiment_ema_history_weekly(
    cfg: Config,
    ticker: str,
    *,
    short: int = 20,
    long: int = 50,
    min_periods_ratio: float = 0.4,
) -> pd.DataFrame:
    """Weekly-resampled sentiment EMA history.

    Same shape as `sentiment_ema_history` but on Friday-weekly bars,
    matching the technicals weekly cadence. With enough historical
    backfill (e.g. PullPush + Wikipedia + HN sweeps) the classic 20/50
    weekly EMA crossover becomes meaningful on a multi-quarter window.
    """
    daily = _per_ticker_daily(cfg)
    sub = daily[daily["ticker"] == ticker]
    if sub.empty:
        return pd.DataFrame()
    sub = sub.copy()
    sub["date"] = pd.to_datetime(sub["date"])
    agg = sub.groupby("date").agg(
        mentions=("mentions", "sum"),
        sentiment_mean=("sentiment_mean", "mean"),
    ).sort_index()
    # Weekly resample: take the mean sentiment per week (weighted via mean
    # of daily means; perfect would be mention-weighted but expensive).
    agg = agg.resample("W-FRI").agg(
        mentions=("mentions", "sum"),
        sentiment_mean=("sentiment_mean", "mean"),
    )
    sent = agg["sentiment_mean"].ffill().fillna(0.0)
    if len(sent) < int(long * min_periods_ratio):
        return pd.DataFrame()
    ema_s = sent.ewm(span=short, adjust=False, min_periods=int(short * min_periods_ratio)).mean()
    ema_l = sent.ewm(span=long, adjust=False, min_periods=int(long * min_periods_ratio)).mean()
    spread = ema_s - ema_l
    cross_up = (spread > 0) & (spread.shift(1) <= 0)
    cross_down = (spread < 0) & (spread.shift(1) >= 0)
    state = np.where(
        spread.isna(), "warmup",
        np.where(spread > 0, "bullish", "bearish"),
    )
    return pd.DataFrame({
        "mentions": agg["mentions"].fillna(0.0),
        "sentiment_mean": agg["sentiment_mean"],
        "ema_short_w": ema_s,
        "ema_long_w": ema_l,
        "spread_w": spread,
        "ema_cross_up_w": cross_up.fillna(False),
        "ema_cross_down_w": cross_down.fillna(False),
        "state_w": state,
    })


def sentiment_momentum_scan_weekly(
    cfg: Config,
    *,
    top: int = 30,
    short: int = 20,
    long: int = 50,
    min_mentions: int = 20,
    min_periods_ratio: float = 0.4,
) -> pd.DataFrame:
    """Cross-ticker weekly-EMA scan; same composite shape as the daily one."""
    daily = _per_ticker_daily(cfg)
    if daily.empty:
        return pd.DataFrame()
    rows: list[dict] = []
    for ticker in daily["ticker"].unique():
        sub = daily[daily["ticker"] == ticker]
        if int(sub["mentions"].sum()) < int(min_mentions):
            continue
        hist = sentiment_ema_history_weekly(
            cfg, ticker, short=short, long=long, min_periods_ratio=min_periods_ratio,
        )
        if hist.empty:
            continue
        m_series = hist["mentions"].fillna(0.0)
        m_ema_s = m_series.ewm(span=short, adjust=False, min_periods=int(short * min_periods_ratio)).mean()
        m_ema_l = m_series.ewm(span=long, adjust=False, min_periods=int(long * min_periods_ratio)).mean()
        m_spread = m_ema_s - m_ema_l
        m_cross_up = (m_spread > 0) & (m_spread.shift(1) <= 0)
        last = hist.iloc[-1]
        if pd.isna(last["spread_w"]):
            continue
        weeks_observed = int(len(hist))
        recent_w = min(weeks_observed, 4)
        s_cross_recent = bool(hist["ema_cross_up_w"].tail(recent_w).any())
        m_cross_recent = bool(m_cross_up.tail(recent_w).any())
        spread_chg = float(last["spread_w"] - hist["spread_w"].iloc[-min(weeks_observed, 3)])

        score = 0.0
        score += min(float(last["spread_w"]) * 5.0, 4.0) if last["spread_w"] > 0 else max(float(last["spread_w"]) * 5.0, -4.0)
        if s_cross_recent: score += 3.0
        if float(last["ema_short_w"]) > 0.15: score += 1.5
        if m_cross_recent: score += 2.0
        score += min(spread_chg * 5.0, 2.0) if spread_chg > 0 else max(spread_chg * 5.0, -2.0)
        score += min(float(m_ema_s.iloc[-1]) / 5.0, 1.5) if pd.notna(m_ema_s.iloc[-1]) else 0.0

        rows.append({
            "ticker": ticker,
            "sent_momentum_w": round(score, 2),
            "state_w": str(last["state_w"]),
            "ema_short_w": round(float(last["ema_short_w"]), 3) if pd.notna(last["ema_short_w"]) else None,
            "ema_long_w": round(float(last["ema_long_w"]), 3) if pd.notna(last["ema_long_w"]) else None,
            "spread_w": round(float(last["spread_w"]), 3),
            "spread_3w_chg": round(spread_chg, 3),
            "sent_cross_up_recent_w": s_cross_recent,
            "mentions_ema_short_w": round(float(m_ema_s.iloc[-1]), 1) if pd.notna(m_ema_s.iloc[-1]) else None,
            "mentions_ema_long_w": round(float(m_ema_l.iloc[-1]), 1) if pd.notna(m_ema_l.iloc[-1]) else None,
            "mention_cross_up_recent_w": m_cross_recent,
            "total_mentions": int(sub["mentions"].sum()),
            "weeks_observed": weeks_observed,
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("sent_momentum_w", ascending=False).head(int(top)).reset_index(drop=True)


def bullish_leaderboard(
    cfg: Config,
    *,
    top: int = 50,
    min_mentions: int = 5,
) -> dict:
    """Run every bullish ranker and surface the union of top-N per measure.

    Returns a dict of DataFrames:
      "social_momentum"    -- pure_social_momentum top N
      "sentiment_ema_d"    -- sentiment_momentum_scan top N (daily EMAs)
      "sentiment_ema_w"    -- sentiment_momentum_scan_weekly top N (weekly EMAs)
      "polarity_gap"       -- top N by bull_minus_bear_7d (extracted from
                              pure_social_momentum)
      "polarity_growth"    -- top N by polarity_vol_growth
      "composite"          -- per-ticker average of percentile ranks across
                              all the above (single ranking)
    """
    out: dict[str, pd.DataFrame] = {}

    sm = pure_social_momentum(cfg, top=1000, min_mentions=min_mentions)
    if not sm.empty:
        out["social_momentum"] = sm.head(top).reset_index(drop=True)
        polg = sm.sort_values("bull_minus_bear_7d", ascending=False).head(top).reset_index(drop=True)
        out["polarity_gap"] = polg[["ticker", "bull_minus_bear_7d", "bull_7d", "bear_7d",
                                    "polarity_volume_7d", "polarity_vol_growth", "bull_share"]]
        polg2 = sm.sort_values("polarity_vol_growth", ascending=False).head(top).reset_index(drop=True)
        out["polarity_growth"] = polg2[["ticker", "polarity_vol_growth", "polarity_volume_7d",
                                        "bull_minus_bear_7d", "mentions_7d"]]
    sed = sentiment_momentum_scan(cfg, top=1000, short=5, long=14, min_mentions=min_mentions)
    if not sed.empty:
        out["sentiment_ema_d"] = sed.head(top).reset_index(drop=True)
    sew = sentiment_momentum_scan_weekly(cfg, top=1000, short=20, long=50, min_mentions=min_mentions * 2)
    if not sew.empty:
        out["sentiment_ema_w"] = sew.head(top).reset_index(drop=True)

    # Composite: per-ticker average percentile rank across the measures.
    score_cols = {
        "social_momentum": "social_momentum",
        "sentiment_ema_d": "sent_momentum",
        "sentiment_ema_w": "sent_momentum_w",
    }
    components: list[pd.Series] = []
    for key, col in score_cols.items():
        if key in out and col in out[key].columns:
            full = (sm if key == "social_momentum" else
                    sed if key == "sentiment_ema_d" else
                    sew if key == "sentiment_ema_w" else None)
            if full is None or full.empty:
                continue
            ranked = full[["ticker", col]].copy()
            ranked["pct"] = ranked[col].rank(pct=True) * 100.0
            components.append(ranked.set_index("ticker")["pct"].rename(key))
    if not components:
        out["composite"] = pd.DataFrame()
        return out
    comp = pd.concat(components, axis=1)
    comp["composite_pct"] = comp.mean(axis=1, skipna=True).round(1)
    comp = comp.sort_values("composite_pct", ascending=False).head(top)
    comp = comp.reset_index()
    out["composite"] = comp
    return out


def sentiment_ema_history(
    cfg: Config,
    ticker: str,
    *,
    short: int = 20,
    long: int = 50,
    min_periods_ratio: float = 0.5,
) -> pd.DataFrame:
    """Daily sentiment time series for one ticker with short/long EMAs.

    Returns a DataFrame indexed by date with columns:
      mentions, sentiment_mean, ema_short, ema_long, spread,
      ema_cross_up, ema_cross_down, state ('bullish'|'bearish'|'warmup').

    Sentiment time series is mean sentiment per day (weighted by per-row
    sentiment field). Days with no mentions are filled with NaN -- EMAs
    skip them via `ffill` so a holiday doesn't trigger a fake cross.
    """
    daily = _per_ticker_daily(cfg)
    sub = daily[daily["ticker"] == ticker]
    if sub.empty:
        return pd.DataFrame()
    sub = sub.copy()
    sub["date"] = pd.to_datetime(sub["date"])
    agg = sub.groupby("date").agg(
        mentions=("mentions", "sum"),
        sentiment_mean=("sentiment_mean", "mean"),
    ).sort_index()
    # Fill calendar so EMAs are correctly spaced.
    agg = agg.asfreq("D")
    # Sentiment EMAs use ffill so non-mention days persist last value,
    # rather than crashing to 0 (which would create artificial crossovers).
    sent = agg["sentiment_mean"].ffill().fillna(0.0)
    if len(sent) < int(long * min_periods_ratio):
        return pd.DataFrame()  # not enough history

    ema_s = sent.ewm(span=short, adjust=False, min_periods=int(short * min_periods_ratio)).mean()
    ema_l = sent.ewm(span=long, adjust=False, min_periods=int(long * min_periods_ratio)).mean()
    spread = ema_s - ema_l
    cross_up = (spread > 0) & (spread.shift(1) <= 0)
    cross_down = (spread < 0) & (spread.shift(1) >= 0)

    state = np.where(
        spread.isna(), "warmup",
        np.where(spread > 0, "bullish", "bearish"),
    )
    return pd.DataFrame({
        "mentions": agg["mentions"].fillna(0.0),
        "sentiment_mean": agg["sentiment_mean"],
        "ema_short": ema_s,
        "ema_long": ema_l,
        "spread": spread,
        "ema_cross_up": cross_up.fillna(False),
        "ema_cross_down": cross_down.fillna(False),
        "state": state,
    })


def sentiment_momentum_scan(
    cfg: Config,
    *,
    top: int = 30,
    short: int = 20,
    long: int = 50,
    min_mentions: int = 5,
    min_periods_ratio: float = 0.5,
) -> pd.DataFrame:
    """Rank tickers by sentiment-EMA momentum.

    For each ticker with enough mention history we compute:

      * `ema_short` -- short EMA of daily sentiment
      * `ema_long`  -- long EMA of daily sentiment
      * `spread`    -- ema_short - ema_long (signed momentum)
      * `cross_up_recent` -- bullish EMA cross within last 7 days
      * `state` -- "bullish" if spread > 0
      * `mentions_ema_short / long` -- same EMAs on mention VOLUME (the
        attention side; rising EMA(20) on mentions = audience is growing)

    Composite ranks by:
        + spread (capped)
        + bullish cross bonus
        + positive ema_short bonus
        + mentions EMA cross-up bonus
        + spread acceleration (widening = stronger trend)
    """
    daily = _per_ticker_daily(cfg)
    if daily.empty:
        return pd.DataFrame()
    end = pd.to_datetime(daily["date"]).max()
    recent_cut = end - pd.Timedelta(days=7)

    rows: list[dict] = []
    for ticker in daily["ticker"].unique():
        sub = daily[daily["ticker"] == ticker]
        if int(sub["mentions"].sum()) < int(min_mentions):
            continue
        hist = sentiment_ema_history(
            cfg, ticker, short=short, long=long, min_periods_ratio=min_periods_ratio,
        )
        if hist.empty:
            continue
        # Also EMAs on mention volume (attention momentum).
        m_series = hist["mentions"].fillna(0.0)
        m_ema_s = m_series.ewm(span=short, adjust=False, min_periods=int(short * min_periods_ratio)).mean()
        m_ema_l = m_series.ewm(span=long, adjust=False, min_periods=int(long * min_periods_ratio)).mean()
        m_spread = m_ema_s - m_ema_l
        m_cross_up = (m_spread > 0) & (m_spread.shift(1) <= 0)
        m_cross_recent = bool(m_cross_up.tail(7).any())

        last = hist.iloc[-1]
        if pd.isna(last["spread"]):
            continue
        s_cross_recent = bool(hist["ema_cross_up"].tail(7).any())
        # Spread acceleration: latest spread - spread 5 days ago.
        if len(hist) >= 6:
            spread_chg = float(last["spread"]) - float(hist["spread"].iloc[-6])
        else:
            spread_chg = 0.0

        score = 0.0
        score += min(float(last["spread"]) * 5.0, 4.0) if last["spread"] > 0 else max(float(last["spread"]) * 5.0, -4.0)
        if s_cross_recent:
            score += 3.0
        if float(last["ema_short"]) > 0.15:
            score += 1.5
        if m_cross_recent:
            score += 2.0
        score += min(spread_chg * 5.0, 2.0) if spread_chg > 0 else max(spread_chg * 5.0, -2.0)
        score += min(float(m_ema_s.iloc[-1]) / 5.0, 1.5) if pd.notna(m_ema_s.iloc[-1]) else 0.0

        rows.append({
            "ticker": ticker,
            "sent_momentum": round(score, 2),
            "state": str(last["state"]),
            "ema_short": round(float(last["ema_short"]), 3) if pd.notna(last["ema_short"]) else None,
            "ema_long": round(float(last["ema_long"]), 3) if pd.notna(last["ema_long"]) else None,
            "spread": round(float(last["spread"]), 3),
            "spread_5d_chg": round(spread_chg, 3),
            "sent_cross_up_recent": s_cross_recent,
            "mentions_ema_short": round(float(m_ema_s.iloc[-1]), 1) if pd.notna(m_ema_s.iloc[-1]) else None,
            "mentions_ema_long": round(float(m_ema_l.iloc[-1]), 1) if pd.notna(m_ema_l.iloc[-1]) else None,
            "mention_cross_up_recent": m_cross_recent,
            "total_mentions": int(sub["mentions"].sum()),
            "days_observed": int(len(hist)),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("sent_momentum", ascending=False).head(int(top)).reset_index(drop=True)


def pure_social_momentum(
    cfg: Config,
    *,
    top: int = 30,
    min_mentions: int = 5,
    half_life: int = 14,
    require_positive_sentiment: bool = False,
) -> pd.DataFrame:
    """Pure social momentum ranking -- no price, no technicals.

    Aggregates the mention store and ranks tickers by a composite of:

      * **mention_z**       -- EWMA z-score of daily mentions
      * **growth_7d**       -- log(last7) - log(prev7) (1st derivative)
      * **growth_3d**       -- log(last3) - log(prior3) (short-end)
      * **inflection**      -- (recent growth) - (prior growth) (2nd deriv)
      * **sentiment_delta** -- last-7d mean sentiment - prior-7d mean

    PLUS explicit sentiment-volume measures (the key Camillo edge --
    "people are talking about this, and the conversation has flipped"):

      * **bull_minus_bear_7d**    -- COUNT bullish - COUNT bearish, last 7d.
                                     A POLARITY GAP that ignores neutral
                                     noise. The actual bull/bear *vote*.
      * **bull_bear_delta**       -- gap_now - gap_prev. Did the conversation
                                     just flip from neutral/bearish to bullish?
      * **polarity_volume_7d**    -- bullish + bearish counts last 7d.
                                     How LOUD the polarized conversation is,
                                     independent of which way it leans.
      * **polarity_volume_growth**-- log ratio of polarity_volume now vs prev7d.
                                     The room got louder this week.

      * **new_sources**     -- # distinct sources active in last 7d but not
                               in prior 7d (= the topic is spreading)
      * **source_count**    -- # distinct sources currently active

    Composite = weighted sum, with explicit caps so a single dimension
    can't dominate. Tickers with `min_mentions` cumulative mentions or
    fewer are filtered out.
    """
    from . import storage
    daily = _per_ticker_daily(cfg)
    if daily.empty:
        return pd.DataFrame()

    # Source-level breakdown per ticker per day, for diversity metrics.
    try:
        with storage.connect(cfg) as con:
            src_df = con.execute(
                "SELECT CAST(timestamp AS DATE) AS date, ticker, source, "
                "COUNT(*) AS n FROM mentions GROUP BY 1, 2, 3"
            ).df()
        src_df["date"] = pd.to_datetime(src_df["date"])
    except Exception:  # noqa: BLE001
        src_df = pd.DataFrame()

    # Per-ticker per-day per-label counts for sentiment-polarity volumes.
    try:
        with storage.connect(cfg) as con:
            pol_df = con.execute(
                "SELECT CAST(timestamp AS DATE) AS date, ticker, sentiment_label, "
                "COUNT(*) AS n FROM mentions GROUP BY 1, 2, 3"
            ).df()
        pol_df["date"] = pd.to_datetime(pol_df["date"])
    except Exception:  # noqa: BLE001
        pol_df = pd.DataFrame()

    end_date = pd.to_datetime(daily["date"]).max()
    last7_cut = end_date - pd.Timedelta(days=6)
    prev7_cut = end_date - pd.Timedelta(days=13)
    last3_cut = end_date - pd.Timedelta(days=2)
    prior3_cut = end_date - pd.Timedelta(days=5)

    rows: list[dict] = []
    for ticker, grp in daily.groupby("ticker"):
        total = int(grp["mentions"].sum())
        if total < int(min_mentions):
            continue
        series = grp.set_index("date")["mentions"].sort_index()
        series.index = pd.to_datetime(series.index)
        series = series.asfreq("D", fill_value=0.0)

        # EWMA z-score on log mentions.
        log_s = np.log1p(series)
        if len(log_s) >= 3:
            mu = log_s.ewm(halflife=half_life, min_periods=3).mean()
            sd = log_s.ewm(halflife=half_life, min_periods=3).std().replace(0.0, np.nan)
            z = float(((log_s - mu) / sd).iloc[-1]) if sd.notna().iloc[-1] else 0.0
        else:
            z = 0.0

        last7 = float(series.loc[series.index >= last7_cut].sum())
        prev7 = float(series.loc[(series.index >= prev7_cut) & (series.index < last7_cut)].sum())
        last3 = float(series.loc[series.index >= last3_cut].sum())
        prior3 = float(series.loc[(series.index >= prior3_cut) & (series.index < last3_cut)].sum())

        growth_7d = float(np.log1p(last7) - np.log1p(prev7))
        growth_3d = float(np.log1p(last3) - np.log1p(prior3))
        # 2nd derivative: short-window growth vs longer-window growth.
        inflection = growth_3d - growth_7d / 2.0

        # Sentiment delta last7 vs prev7.
        sent_series = grp.set_index("date")["sentiment_mean"].sort_index()
        sent_series.index = pd.to_datetime(sent_series.index)
        sent_last7 = float(sent_series.loc[sent_series.index >= last7_cut].mean()) if not sent_series.empty else 0.0
        sent_prev7 = float(sent_series.loc[(sent_series.index >= prev7_cut) & (sent_series.index < last7_cut)].mean()) if not sent_series.empty else 0.0
        if pd.isna(sent_last7): sent_last7 = 0.0
        if pd.isna(sent_prev7): sent_prev7 = 0.0
        sent_delta = sent_last7 - sent_prev7
        if require_positive_sentiment and sent_last7 < 0:
            continue

        # Source diversity.
        n_sources_now = 0
        new_sources_n = 0
        if not src_df.empty:
            sub_src = src_df[src_df["ticker"] == ticker]
            srcs_last7 = set(sub_src.loc[sub_src["date"] >= last7_cut, "source"])
            srcs_prev7 = set(sub_src.loc[(sub_src["date"] >= prev7_cut) & (sub_src["date"] < last7_cut), "source"])
            n_sources_now = len(srcs_last7)
            new_sources_n = len(srcs_last7 - srcs_prev7)

        # Sentiment-polarity volumes (count of bullish vs bearish vs neutral).
        bull_7 = bear_7 = neu_7 = 0
        bull_p = bear_p = 0
        if not pol_df.empty:
            sub_pol = pol_df[pol_df["ticker"] == ticker]
            last_pol = sub_pol[sub_pol["date"] >= last7_cut]
            prev_pol = sub_pol[(sub_pol["date"] >= prev7_cut) & (sub_pol["date"] < last7_cut)]
            bull_7 = int(last_pol.loc[last_pol["sentiment_label"] == "bullish", "n"].sum())
            bear_7 = int(last_pol.loc[last_pol["sentiment_label"] == "bearish", "n"].sum())
            neu_7 = int(last_pol.loc[last_pol["sentiment_label"] == "neutral", "n"].sum())
            bull_p = int(prev_pol.loc[prev_pol["sentiment_label"] == "bullish", "n"].sum())
            bear_p = int(prev_pol.loc[prev_pol["sentiment_label"] == "bearish", "n"].sum())
        bull_minus_bear_7d = bull_7 - bear_7
        bull_minus_bear_prev = bull_p - bear_p
        bull_bear_delta = bull_minus_bear_7d - bull_minus_bear_prev
        polarity_volume_7d = bull_7 + bear_7
        polarity_volume_prev = bull_p + bear_p
        polarity_volume_growth = float(np.log1p(polarity_volume_7d) - np.log1p(polarity_volume_prev))
        # Polarised share: what fraction of last-7d mentions actually took a
        # side, vs being neutral. A noisy stock with mostly neutral chatter
        # carries less signal than one whose audience has formed an opinion.
        last7_total_int = bull_7 + bear_7 + neu_7
        polarised_share = (bull_7 + bear_7) / max(1, last7_total_int)
        # Bull-vote share: of polarized mentions, what fraction are bullish.
        bull_share = bull_7 / max(1, bull_7 + bear_7)

        # Composite, cap each contribution.
        score = 0.0
        score += min(max(z, 0.0), 4.0) * 1.0
        score += min(growth_7d, 3.0) * 1.0 if growth_7d > 0 else 0.0
        score += min(growth_3d, 3.0) * 0.7 if growth_3d > 0 else 0.0
        score += min(inflection, 3.0) * 1.2 if inflection > 0 else 0.0
        score += min(sent_delta * 5.0, 2.0) if sent_delta > 0 else max(sent_delta * 3.0, -2.0)
        score += min(sent_last7 * 3.0, 1.5) if sent_last7 > 0 else 0.0
        score += min(n_sources_now, 4) * 0.5
        score += min(new_sources_n, 3) * 0.75
        # Bull/bear polarity weight: log scaling so a 100-bull / 5-bear week
        # contributes more than 5-bull / 1-bear without going parabolic.
        if bull_minus_bear_7d > 0:
            score += min(np.log1p(bull_minus_bear_7d), 3.0) * 1.0
        elif bull_minus_bear_7d < 0:
            score -= min(np.log1p(abs(bull_minus_bear_7d)), 3.0) * 1.0
        # Flip bonus: net polarity gap improved week-over-week.
        if bull_bear_delta > 0:
            score += min(np.log1p(bull_bear_delta), 2.5) * 1.0
        # Polarity volume growth: the polarized room got louder.
        if polarity_volume_growth > 0:
            score += min(polarity_volume_growth, 3.0) * 0.7
        # Polarised share bonus: real conviction vs noise.
        score += polarised_share * 1.0
        # Volume floor: more mentions = more reliable signal.
        score += min(np.log1p(total) / 2.0, 1.5)

        rows.append({
            "ticker": ticker,
            "social_momentum": round(score, 2),
            "total_mentions": total,
            "mentions_7d": int(last7),
            "mentions_prev7d": int(prev7),
            "growth_7d": round(growth_7d, 2),
            "growth_3d": round(growth_3d, 2),
            "inflection": round(inflection, 2),
            "mention_z": round(z, 2),
            "sentiment_7d": round(sent_last7, 2),
            "sentiment_delta": round(sent_delta, 2),
            "bull_7d": bull_7,
            "bear_7d": bear_7,
            "neutral_7d": neu_7,
            "bull_minus_bear_7d": bull_minus_bear_7d,
            "bull_bear_delta": bull_bear_delta,
            "polarity_volume_7d": polarity_volume_7d,
            "polarity_vol_growth": round(polarity_volume_growth, 2),
            "polarised_share": round(polarised_share, 2),
            "bull_share": round(bull_share, 2),
            "sources_now": n_sources_now,
            "new_sources": new_sources_n,
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("social_momentum", ascending=False).head(int(top)).reset_index(drop=True)


def social_signal_score(cfg: Config, ticker: str) -> dict:
    """Per-ticker rolled-up social/alt-data signal.

    Aggregates everything we have for a single ticker into a small dict:

        total_mentions   -- all-time count in our store
        latest_z         -- EWMA z-score of daily mentions (last day)
        log_growth_7d    -- log(last7) - log(prev7)
        sentiment_14d    -- mean sentiment over last 14 days
        n_sources        -- distinct sources contributing mentions
        wiki_growth_pct  -- 30d Wikipedia pageviews trend (if cached)
        social_score     -- composite 0..10
        positive         -- bool: is the signal CONSTRUCTIVE?
    """
    from . import storage
    daily = _per_ticker_daily(cfg)
    sub = daily[daily["ticker"] == ticker]
    if sub.empty:
        return {
            "total_mentions": 0, "latest_z": 0.0, "log_growth_7d": 0.0,
            "sentiment_14d": 0.0, "n_sources": 0, "wiki_growth_pct": 0.0,
            "social_score": 0.0, "positive": False,
        }
    total = int(sub["mentions"].sum())
    # Per-day series and EWMA z-score.
    series = sub.groupby("date")["mentions"].sum().sort_index()
    series.index = pd.to_datetime(series.index)
    series = series.asfreq("D", fill_value=0.0)
    log_s = np.log1p(series)
    if len(log_s) >= 5:
        mu = log_s.ewm(halflife=14, min_periods=3).mean()
        sd = log_s.ewm(halflife=14, min_periods=3).std().replace(0.0, np.nan)
        z = float(((log_s - mu) / sd).iloc[-1]) if sd.notna().iloc[-1] else 0.0
    else:
        z = 0.0
    last7 = float(series.tail(7).sum())
    prev7 = float(series.tail(14).head(7).sum())
    growth = float(np.log1p(last7) - np.log1p(prev7))
    sent_14d = float(sub.tail(14)["sentiment_mean"].mean()) if not sub.empty else 0.0

    # Source diversity from raw store.
    try:
        with storage.connect(cfg) as con:
            n_sources = int(con.execute(
                "SELECT COUNT(DISTINCT source) FROM mentions WHERE ticker = ?", [ticker]
            ).fetchone()[0])
    except Exception:  # noqa: BLE001
        n_sources = 0

    # Wikipedia pageview growth (last 7d vs prior 7d).
    wiki_growth = 0.0
    try:
        with storage.connect(cfg) as con:
            wiki = con.execute(
                "SELECT CAST(timestamp AS DATE) AS d, COUNT(*) AS n "
                "FROM mentions WHERE ticker = ? AND source = 'wikipedia' "
                "GROUP BY 1 ORDER BY 1", [ticker]
            ).df()
        if not wiki.empty and len(wiki) >= 14:
            wn = wiki.tail(7)["n"].sum()
            wp = wiki.tail(14).head(7)["n"].sum()
            if wp > 0:
                wiki_growth = (wn / wp - 1.0) * 100.0
    except Exception:  # noqa: BLE001
        pass

    # Composite social score 0..10.
    s = 0.0
    if z > 0:
        s += min(z, 4.0) * 1.0
    if sent_14d > 0:
        s += min(sent_14d * 5.0, 3.0)
    if growth > 0:
        s += min(growth * 1.5, 2.5)
    if n_sources >= 2:
        s += min(n_sources / 3.0, 1.5)
    if total >= 30:
        s += 1.0
    if wiki_growth > 20:
        s += min(wiki_growth / 50.0, 1.5)

    positive = (z > 0.5 or sent_14d > 0.15 or growth > 0.3) and sent_14d >= -0.05

    return {
        "total_mentions": total, "latest_z": z, "log_growth_7d": growth,
        "sentiment_14d": sent_14d, "n_sources": n_sources,
        "wiki_growth_pct": wiki_growth, "social_score": round(s, 2),
        "positive": positive,
    }


def social_asymmetric_setups(
    cfg: Config,
    tickers: list[str] | None = None,
    *,
    top: int = 30,
    min_mentions: int = 5,
    min_upside_pct: float = 30.0,
    min_social_score: float = 1.5,
    enrich_finviz: int = 0,
) -> pd.DataFrame:
    """Information-arbitrage ranker: broken price + rising social signal.

    The Camillo edge. Pure-price asymmetry surfaces *how cheap* a name
    is; that's necessary but not sufficient. The information imbalance
    is when the *alt-data* (social mentions, sentiment, attention, news
    coverage diversity) is constructive AT THE SAME TIME as the price
    is washed out. Wall Street hasn't priced the turn yet -- the
    observation has not become consensus.

    Composite = price-asymmetric score + social-signal score +
    explicit **divergence** bonus when both fire.
    """
    from .technicals import load_price_cache, signals_for_close
    from .technicals_daily import daily_signals_for, load_daily_cache

    weekly = load_price_cache(cfg)
    if weekly.empty:
        return pd.DataFrame()
    daily_close, daily_vol = load_daily_cache(cfg)

    daily = _per_ticker_daily(cfg)
    if daily.empty:
        return pd.DataFrame()
    universe_with_mentions = set(daily["ticker"].unique())
    if tickers is None:
        tickers = sorted(universe_with_mentions & set(weekly.columns))
    else:
        tickers = sorted(set(tickers) & universe_with_mentions & set(weekly.columns))

    rows: list[dict] = []
    for t in tickers:
        soc = social_signal_score(cfg, t)
        if soc["total_mentions"] < int(min_mentions):
            continue
        if soc["social_score"] < float(min_social_score):
            continue

        wclose = weekly[t].dropna()
        if len(wclose) < 50:
            continue
        wsig = signals_for_close(wclose)
        if wsig is None or wsig.empty:
            continue
        wlast = wsig.iloc[-1]

        # 52w range, prefer daily.
        rsi14 = vol_z = None
        from_high = from_low = None
        if not daily_close.empty and t in daily_close.columns:
            dc = daily_close[t].dropna()
            dv = daily_vol[t] if (not daily_vol.empty and t in daily_vol.columns) else None
            if len(dc) >= 60:
                dsig = daily_signals_for(dc, dv)
                if not dsig.empty:
                    dlast = dsig.iloc[-1]
                    rsi14 = float(dlast["rsi_14"]) if pd.notna(dlast["rsi_14"]) else None
                    from_high = float(dlast["pct_from_high_52w"]) if pd.notna(dlast["pct_from_high_52w"]) else None
                    from_low = float(dlast["pct_from_low_52w"]) if pd.notna(dlast["pct_from_low_52w"]) else None
                    vol_z = float(dlast.get("vol_z_30")) if pd.notna(dlast.get("vol_z_30", np.nan)) else None
        if from_high is None or from_low is None:
            wh = float(wclose.tail(52).max())
            wl = float(wclose.tail(52).min())
            c = float(wclose.iloc[-1])
            from_high = (c / wh - 1.0) * 100.0
            from_low = (c / wl - 1.0) * 100.0

        upside = -from_high if from_high < 0 else 0.0
        downside = max(from_low, 0.0)
        if upside < float(min_upside_pct):
            continue
        asym_ratio = upside / max(downside, 1.0)

        # Price-pain score (= broken-and-cheap, capped 8).
        price_score = min(upside / 7.0, 6.0) + min(asym_ratio / 5.0, 2.0)
        if rsi14 is not None and rsi14 <= 35:
            price_score += 1.0

        # Social signal score (already 0..10).
        social = float(soc["social_score"])

        # Divergence bonus: BOTH broken price AND constructive social.
        divergence = 0.0
        if soc["positive"] and upside >= 30.0:
            divergence = 3.0  # explicit Camillo edge
        # Penalty if sentiment is actively negative -- broken price + crowd
        # screaming "short it" is the GME-2024-style fade, not the Camillo trade.
        if soc["sentiment_14d"] < -0.1 and not soc["positive"]:
            divergence -= 2.0

        total = round(price_score + social + divergence, 2)

        rows.append({
            "ticker": t,
            "social_asym_score": total,
            "price_score": round(price_score, 1),
            "social_score": social,
            "divergence_bonus": divergence,
            "close": round(float(wlast["close"]), 2),
            "from_52w_high_pct": round(from_high, 1),
            "from_52w_low_pct": round(from_low, 1),
            "asym_ratio": round(asym_ratio, 1),
            "rsi_14": round(rsi14, 1) if rsi14 is not None else None,
            "vol_z_30": round(vol_z, 1) if vol_z is not None else None,
            "state": str(wlast["state"]),
            "mentions": int(soc["total_mentions"]),
            "mention_z": round(soc["latest_z"], 2),
            "mention_growth_7d": round(soc["log_growth_7d"], 2),
            "sentiment_14d": round(soc["sentiment_14d"], 2),
            "n_sources": int(soc["n_sources"]),
            "wiki_growth_pct": round(soc["wiki_growth_pct"], 0),
        })

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("social_asym_score", ascending=False).head(int(top))

    if enrich_finviz and len(df) > 0:
        from .collectors.finviz import collect_finviz_batch
        fv = collect_finviz_batch(df["ticker"].head(int(enrich_finviz)).tolist(), sleep_between=0.7)
        if not fv.empty:
            cols = ["ticker", "market_cap", "short_float_pct", "earnings_date", "sector", "industry"]
            cols = [c for c in cols if c in fv.columns]
            df = df.merge(fv[cols], on="ticker", how="left")

    return df.reset_index(drop=True)


def small_mid_cap_asymmetric(
    cfg: Config,
    tickers: list[str] | None = None,
    *,
    top: int = 30,
    candidate_pool: int = 200,
    enrich_top: int = 120,
    mcap_min: float = 250e6,
    mcap_max: float = 10e9,
    min_upside_pct: float = 50.0,
    min_asym_ratio: float = 3.0,
    min_close: float = 1.5,
) -> pd.DataFrame:
    """Asymmetric setups filtered to the small/mid-cap band ($250M-$10B).

    Camillo's edge is structurally in this band -- multi-billion funds
    can't size in, retail can. We run the price-asymmetric scan on a
    deep candidate pool, Finviz-enrich the top, filter by market cap,
    then add a social-spike bonus and rerank.

    Social-spike bonus comes from the social_price_divergence layer:
    +2 if divergence > 1.0 AND social_z > 1.5 (anomalous mention spike
    where price hasn't followed = textbook Camillo information edge).
    """
    # 1) Get a deep technical-asymmetric candidate pool.
    base = asymmetric_setups(
        cfg, tickers=tickers, top=candidate_pool,
        enrich_finviz=0, min_close=min_close,
        min_upside_pct=min_upside_pct, min_asym_ratio=min_asym_ratio,
    )
    if base.empty:
        return base

    # 2) Finviz-enrich the top `enrich_top` for market cap + short float.
    from .collectors.finviz import collect_finviz_batch
    top_pool = base.head(int(enrich_top)).copy()
    fv = collect_finviz_batch(top_pool["ticker"].tolist(), sleep_between=0.5)
    if fv.empty:
        log.warning("Finviz returned no data; using price-proxy filter only")
        return base.head(int(top))

    keep_cols = [c for c in [
        "ticker", "market_cap", "short_float_pct", "insider_trans_pct",
        "earnings_date", "sector", "industry",
    ] if c in fv.columns]
    merged = top_pool.merge(fv[keep_cols], on="ticker", how="left")

    # 3) Filter to the small/mid cap band.
    merged = merged[merged["market_cap"].notna()]
    merged = merged[(merged["market_cap"] >= mcap_min) & (merged["market_cap"] <= mcap_max)]
    if merged.empty:
        return merged

    # 4) Pull divergence scores for each.
    div = social_price_divergence(
        cfg, top=10000, lookback_weeks=8,
        min_mentions_per_week=1.0, min_total_mentions=10,
        require_positive=False,
    )
    if not div.empty:
        merged = merged.merge(
            div[["ticker", "divergence", "divergence_4w", "social_z", "price_z"]],
            on="ticker", how="left",
        )
    else:
        for c in ["divergence", "divergence_4w", "social_z", "price_z"]:
            merged[c] = None

    # 5) Composite: asym_score + short-squeeze + earnings-near + social-spike.
    def _bonus(row) -> float:
        bonus = 0.0
        sf = row.get("short_float_pct")
        if pd.notna(sf) and float(sf) >= 10.0:
            bonus += min(float(sf), 30.0) / 5.0
        ed = row.get("earnings_date")
        if isinstance(ed, str) and ed:
            try:
                from datetime import datetime as _dt
                for fmt in ("%b %d", "%b %d %Y"):
                    try:
                        d = _dt.strptime(ed.split(" AMC")[0].split(" BMO")[0], fmt)
                        d = d.replace(year=_dt.now().year)
                        if 0 <= (d - _dt.now()).days <= 30:
                            bonus += 1.0
                        break
                    except ValueError:
                        continue
            except Exception:  # noqa: BLE001
                pass
        # Social-spike bonus: anomalous mention z + price flat/down.
        sz = row.get("social_z")
        pz = row.get("price_z")
        if pd.notna(sz) and pd.notna(pz) and float(sz) >= 1.5 and float(pz) <= 0.5:
            bonus += 3.0
        elif pd.notna(sz) and float(sz) >= 1.0 and pd.notna(pz) and float(pz) <= 0.0:
            bonus += 1.5
        # Sustained 4w divergence
        d4 = row.get("divergence_4w")
        if pd.notna(d4) and float(d4) >= 1.0:
            bonus += 1.5
        return bonus

    merged["bonus"] = merged.apply(_bonus, axis=1)
    merged["composite"] = (merged["asym_score"] + merged["bonus"]).round(2)
    merged["mcap_$M"] = (merged["market_cap"] / 1e6).round(0).astype(int)
    out = merged.sort_values("composite", ascending=False).head(int(top))

    # Cleaner column order for display.
    display_cols = [
        "ticker", "composite", "asym_score", "bonus", "close", "mcap_$M",
        "from_52w_high_pct", "from_52w_low_pct", "asym_ratio",
        "rsi_14", "vol_z_30", "state",
        "short_float_pct", "earnings_date",
        "divergence", "divergence_4w", "social_z", "price_z",
        "sector", "industry",
    ]
    cols = [c for c in display_cols if c in out.columns]
    return out[cols].reset_index(drop=True)


def asymmetric_setups(
    cfg: Config,
    tickers: list[str] | None = None,
    *,
    top: int = 30,
    enrich_finviz: int = 0,
    min_close: float = 1.0,
    min_upside_pct: float = 30.0,
    min_asym_ratio: float = 2.0,
) -> pd.DataFrame:
    """Find Camillo-style asymmetric setups: capped downside + large upside.

    Combines weekly state + daily indicators (RSI, 52w distance, vol z)
    into a single asymmetric score. Optionally fetches Finviz for short
    float + earnings date on the top N candidates (`enrich_finviz`).

    Score components (additive):

      * `cheap_pct`     -- (1 − close / 52w_high) * 10        cap 5
      * `near_low`      -- (1 − (close − 52w_low) / 52w_low * 20) cap 5
      * `asym_ratio`    -- upside_to_52w_high / downside_to_52w_low cap 5
      * `oversold`      -- RSI <= 35 → +1.5
      * `capitulation`  -- vol_z >= 2 → vol_z * 0.5 cap 5
      * `tech_turn`     -- weekly state in {hma_up, golden} → +2
      * `flip_up`       -- weekly hma_flip_up_recent → +1
      * `short_squeeze` -- short_float >= 10% (Finviz) → +short_float / 5 cap 6
      * `earnings_near` -- earnings within next 30 days (Finviz) → +1
      * `attention`     -- stored mentions present → +0.5
    """
    from .technicals import load_price_cache, signals_for_close
    from .technicals_daily import daily_signals_for, load_daily_cache

    weekly = load_price_cache(cfg)
    if weekly.empty:
        return pd.DataFrame()
    daily_close, daily_vol = load_daily_cache(cfg)

    if tickers is None:
        tickers = list(weekly.columns)

    daily = _per_ticker_daily(cfg)
    mention_totals = daily.groupby("ticker")["mentions"].sum() if not daily.empty else None
    sentiment_totals = daily.groupby("ticker")["sentiment_mean"].mean() if not daily.empty else None

    rows: list[dict] = []
    for t in tickers:
        if t not in weekly.columns:
            continue
        wclose = weekly[t].dropna()
        if len(wclose) < 50:
            continue
        if float(wclose.iloc[-1]) < min_close:
            continue
        wsig = signals_for_close(wclose)
        if wsig is None or wsig.empty:
            continue
        wlast = wsig.iloc[-1]

        # 52-week range -- prefer daily if available (more accurate), fall back to weekly.
        rsi14 = vol_z = None
        from_high = from_low = None
        gap_today = False
        if not daily_close.empty and t in daily_close.columns:
            dc = daily_close[t].dropna()
            dv = daily_vol[t] if (not daily_vol.empty and t in daily_vol.columns) else None
            if len(dc) >= 60:
                dsig = daily_signals_for(dc, dv)
                if not dsig.empty:
                    dlast = dsig.iloc[-1]
                    rsi14 = float(dlast["rsi_14"]) if pd.notna(dlast["rsi_14"]) else None
                    from_high = float(dlast["pct_from_high_52w"]) if pd.notna(dlast["pct_from_high_52w"]) else None
                    from_low = float(dlast["pct_from_low_52w"]) if pd.notna(dlast["pct_from_low_52w"]) else None
                    vol_z = float(dlast.get("vol_z_30")) if pd.notna(dlast.get("vol_z_30", np.nan)) else None
                    gap_today = bool(dlast.get("gap", False))
        if from_high is None or from_low is None:
            # Weekly fallback.
            wh = float(wclose.tail(52).max())
            wl = float(wclose.tail(52).min())
            c = float(wclose.iloc[-1])
            from_high = (c / wh - 1.0) * 100.0
            from_low = (c / wl - 1.0) * 100.0

        upside_to_high = -from_high if from_high < 0 else 0.0   # positive number = headroom
        downside_to_low = max(from_low, 0.0)
        if upside_to_high < min_upside_pct:
            continue
        asym_ratio = upside_to_high / max(downside_to_low, 1.0)
        if asym_ratio < min_asym_ratio:
            continue

        score = 0.0
        cheap = min(upside_to_high / 10.0, 5.0)
        score += cheap
        near_low_bonus = max(0.0, 5.0 - downside_to_low / 4.0)
        score += near_low_bonus
        score += min(asym_ratio / 2.0, 5.0)
        if rsi14 is not None and rsi14 <= 35:
            score += 1.5
        if vol_z is not None and vol_z >= 2.0:
            score += min(vol_z * 0.5, 5.0)
        if str(wlast["state"]) in ("hma_up", "golden"):
            score += 2.0
        # Weekly Hull flip-up within last 4 bars.
        tail = wsig.tail(4)
        if bool(tail["hma_flip_up"].any()):
            score += 1.0
        mentions_n = int(mention_totals[t]) if mention_totals is not None and t in mention_totals.index else 0
        sent_v = float(sentiment_totals[t]) if sentiment_totals is not None and t in sentiment_totals.index else 0.0
        if mentions_n > 0 and sent_v >= 0:
            score += 0.5

        rows.append({
            "ticker": t,
            "asym_score": round(score, 2),
            "close": round(float(wlast["close"]), 2),
            "from_52w_high_pct": round(from_high, 1) if from_high is not None else None,
            "from_52w_low_pct": round(from_low, 1) if from_low is not None else None,
            "upside_pct": round(upside_to_high, 1),
            "downside_pct": round(downside_to_low, 1),
            "asym_ratio": round(asym_ratio, 1),
            "rsi_14": round(rsi14, 1) if rsi14 is not None else None,
            "vol_z_30": round(vol_z, 1) if vol_z is not None else None,
            "gap_today": gap_today,
            "state": str(wlast["state"]),
            "mentions": mentions_n,
            "sentiment": round(sent_v, 2),
        })

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("asym_score", ascending=False).head(int(top))

    if enrich_finviz and len(df) > 0:
        from .collectors.finviz import collect_finviz_batch
        fv = collect_finviz_batch(df["ticker"].head(int(enrich_finviz)).tolist(), sleep_between=0.7)
        if not fv.empty:
            cols = ["ticker", "market_cap", "short_float_pct", "insider_trans_pct",
                    "earnings_date", "sector", "industry"]
            cols = [c for c in cols if c in fv.columns]
            df = df.merge(fv[cols], on="ticker", how="left")
            # Add short-squeeze and earnings-near bonuses post-hoc.
            def _post_bonus(row) -> float:
                bonus = 0.0
                sf = row.get("short_float_pct")
                if pd.notna(sf) and float(sf) >= 10.0:
                    bonus += min(float(sf), 30.0) / 5.0
                # earnings_date strings like 'May 20 AMC'
                ed = row.get("earnings_date")
                if isinstance(ed, str) and ed:
                    try:
                        from datetime import datetime
                        for fmt in ("%b %d", "%b %d %Y"):
                            try:
                                d = datetime.strptime(ed.split(" AMC")[0].split(" BMO")[0], fmt)
                                d = d.replace(year=datetime.now().year)
                                if 0 <= (d - datetime.now()).days <= 30:
                                    bonus += 1.0
                                break
                            except ValueError:
                                continue
                    except Exception:  # noqa: BLE001
                        pass
                return bonus
            df["finviz_bonus"] = df.apply(_post_bonus, axis=1)
            df["asym_score"] = (df["asym_score"] + df["finviz_bonus"]).round(2)
            df = df.sort_values("asym_score", ascending=False)

    return df.reset_index(drop=True)


def best_today(
    cfg: Config,
    tickers: list[str],
    *,
    top: int = 30,
    short_w: int = 4,
    long_w: int = 8,
    history_lookback: int = 156,        # ~3 years of weekly bars
    min_score_now: float = 0.0,
    weights: tuple[float, float, float] = (1.0, 1.0, 1.0),
    min_close: float = 1.0,
) -> pd.DataFrame:
    """Rank "what's best TODAY" using both own-history and cross-section.

    For each ticker we compute three measures, each normalised:

      * **own_pct_now** -- percentile rank of the current technical score
        within the ticker's *own* last `history_lookback` weeks.
        100 = best level this name has seen in ~3 years.
      * **own_pct_improvement** -- percentile rank of the most recent
        `short_w` score change within the ticker's own distribution of
        rolling `short_w` changes. 100 = biggest improvement this name
        has ever had.
      * **own_pct_inflection** -- percentile rank of the most recent
        second-derivative (recent_change - prior_change) within its own
        distribution.

    We then **cross-section rank** the same three quantities across the
    whole tradeable universe at this single timestamp and z-score each.
    The final composite is a weighted sum of cross-sectional z-scores so
    a name that's both at a personal best *and* leading the universe
    today rises to the top.

    No social-mention filter is applied -- this is a pure observation
    layer over the universe, so it finds names Camillo's framework
    would surface *before* social-media chatter.
    """
    from .technicals import load_price_cache
    cache = load_price_cache(cfg)
    if cache.empty:
        return pd.DataFrame()

    per_ticker: dict[str, dict[str, float]] = {}
    for t in tickers:
        if t not in cache.columns:
            continue
        close = cache[t].dropna()
        if len(close) < max(history_lookback // 4, 30):
            continue
        if float(close.iloc[-1]) < min_close:
            continue
        sh = technical_score_history(close)
        if sh is None or sh.empty or len(sh) < short_w + long_w + 5:
            continue
        score_now = float(sh.iloc[-1])
        if score_now < min_score_now:
            continue
        # Restrict to recent history (avoid old regime).
        window = sh.iloc[-history_lookback:] if len(sh) > history_lookback else sh

        # 1) own-history percentile of CURRENT score
        own_pct_now = float((window <= score_now).sum() / len(window) * 100.0)

        # 2) own-history percentile of the LATEST short-window change
        change_short = sh.diff(short_w).dropna()
        latest_change = float(change_short.iloc[-1]) if len(change_short) else 0.0
        chg_window = change_short.iloc[-history_lookback:] if len(change_short) > history_lookback else change_short
        own_pct_improvement = (
            float((chg_window <= latest_change).sum() / len(chg_window) * 100.0)
            if len(chg_window) >= 5 else 50.0
        )

        # 3) own-history percentile of latest INFLECTION (2nd derivative)
        recent = sh.diff(short_w)
        prior = sh.diff(short_w).shift(short_w)
        infl_series = (recent - prior).dropna()
        latest_infl = float(infl_series.iloc[-1]) if len(infl_series) else 0.0
        infl_window = infl_series.iloc[-history_lookback:] if len(infl_series) > history_lookback else infl_series
        own_pct_inflection = (
            float((infl_window <= latest_infl).sum() / len(infl_window) * 100.0)
            if len(infl_window) >= 5 else 50.0
        )

        per_ticker[t] = {
            "score_now": score_now,
            "change_short": latest_change,
            "inflection": latest_infl,
            "own_pct_now": own_pct_now,
            "own_pct_improvement": own_pct_improvement,
            "own_pct_inflection": own_pct_inflection,
        }

    if not per_ticker:
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(per_ticker, orient="index").reset_index().rename(columns={"index": "ticker"})

    # Cross-section z-scores at this single timestamp.
    def _z(col: str) -> pd.Series:
        s = df[col].astype(float)
        mu = s.mean()
        sd = s.std(ddof=0)
        return (s - mu) / (sd if sd > 0 else 1.0)

    df["cs_z_now"] = _z("score_now")
    df["cs_z_change"] = _z("change_short")
    df["cs_z_inflection"] = _z("inflection")

    w1, w2, w3 = weights
    # Composite -- average of own-history-percentile (scaled to z-equivalent)
    # plus cross-sectional z. Own percentile is on 0-100 so divide by 50 then -1
    # to roughly center on 0 with scale similar to a z-score.
    def _pct_to_z(pct: pd.Series) -> pd.Series:
        return (pct - 50.0) / 25.0

    df["best_today_score"] = (
        w1 * (df["cs_z_now"] + _pct_to_z(df["own_pct_now"])) +
        w2 * (df["cs_z_change"] + _pct_to_z(df["own_pct_improvement"])) +
        w3 * (df["cs_z_inflection"] + _pct_to_z(df["own_pct_inflection"]))
    )
    df = df.sort_values("best_today_score", ascending=False).head(top)

    # Decorate with latest state/close/vs_sma40/mentions for verification.
    from .technicals import signals_for_close
    daily = _per_ticker_daily(cfg)
    soc = daily.groupby("ticker")["mentions"].sum() if not daily.empty else None
    rows: list[dict] = []
    for _, r in df.iterrows():
        t = r["ticker"]
        close = cache[t].dropna()
        sig = signals_for_close(close)
        last = sig.iloc[-1] if sig is not None and not sig.empty else None
        v40 = None
        if last is not None and pd.notna(last.get("sma_40w")) and last["sma_40w"]:
            v40 = round((float(last["close"]) / float(last["sma_40w"]) - 1.0) * 100.0, 1)
        rows.append({
            "ticker": t,
            "best_today_score": round(float(r["best_today_score"]), 2),
            "own_pct_now": round(float(r["own_pct_now"]), 0),
            "own_pct_improve": round(float(r["own_pct_improvement"]), 0),
            "own_pct_inflect": round(float(r["own_pct_inflection"]), 0),
            "cs_z_now": round(float(r["cs_z_now"]), 2),
            "cs_z_change": round(float(r["cs_z_change"]), 2),
            "cs_z_inflect": round(float(r["cs_z_inflection"]), 2),
            "close": round(float(last["close"]), 2) if last is not None else None,
            "vs_sma40_pct": v40,
            "state": str(last["state"]) if last is not None else None,
            "mentions": int(soc[t]) if soc is not None and t in soc.index else 0,
        })
    return pd.DataFrame(rows)


def union_ranking(
    cfg: Config,
    tickers: list[str],
    *,
    top_each: int = 50,
    weeks: int = 4,
    short: int = 4,
    long: int = 8,
    min_score_now: float = 1.0,
) -> pd.DataFrame:
    """Surface names that show up in multiple Camillo views.

    For each ticker, count whether it lands in the top `top_each` of:
      - Camillo composite (current state, social + technical)
      - Improvers   (4w technical-score gain)
      - Inflecters  (acceleration)
    Plus a `confluence` score equal to the count, used to rank.
    Always reports the latest underlying metrics so the user can verify.
    """
    from .technicals import load_price_cache, scan_universe
    cache = load_price_cache(cfg)
    if cache.empty:
        return pd.DataFrame()
    snap = scan_universe(cfg, tickers, use_cache=True)
    cam = camillo_ranking(cfg, snap, min_total_mentions=1, top=top_each)
    imp = rank_improvers(cfg, tickers, lookback_weeks=weeks, top=top_each, min_score_now=min_score_now)
    inf = rank_inflecters(cfg, tickers, short=short, long=long, top=top_each, min_score_now=min_score_now)

    def _set(df):
        return set(df["ticker"].tolist()) if not df.empty and "ticker" in df.columns else set()

    cam_set, imp_set, inf_set = _set(cam), _set(imp), _set(inf)
    all_t = sorted(cam_set | imp_set | inf_set)
    rows: list[dict] = []
    for t in all_t:
        in_cam = t in cam_set
        in_imp = t in imp_set
        in_inf = t in inf_set
        conf = int(in_cam) + int(in_imp) + int(in_inf)
        # pull metrics from whichever frame has them
        cam_score = float(cam.loc[cam["ticker"] == t, "camillo_score"].iloc[0]) if in_cam else None
        improvement = float(imp.loc[imp["ticker"] == t, "improvement"].iloc[0]) if in_imp else None
        inflection = float(inf.loc[inf["ticker"] == t, "inflection"].iloc[0]) if in_inf else None
        snap_row = snap[snap["ticker"] == t]
        close = float(snap_row["close"].iloc[0]) if not snap_row.empty else None
        v40 = float(snap_row["close_vs_sma40_pct"].iloc[0]) if not snap_row.empty and pd.notna(snap_row["close_vs_sma40_pct"].iloc[0]) else None
        state = str(snap_row["state"].iloc[0]) if not snap_row.empty else None
        signal = str(snap_row["signal"].iloc[0]) if not snap_row.empty else None
        daily = _per_ticker_daily(cfg)
        mentions = int(daily.loc[daily["ticker"] == t, "mentions"].sum()) if not daily.empty else 0
        rows.append({
            "ticker": t,
            "confluence": conf,
            "in_cam": in_cam,
            "in_imp": in_imp,
            "in_inf": in_inf,
            "cam_score": round(cam_score, 2) if cam_score is not None else None,
            "improvement": round(improvement, 2) if improvement is not None else None,
            "inflection": round(inflection, 2) if inflection is not None else None,
            "close": round(close, 2) if close is not None else None,
            "vs_sma40_pct": round(v40, 1) if v40 is not None else None,
            "state": state,
            "signal": signal,
            "mentions": mentions,
        })
    out = pd.DataFrame(rows)
    # Sort by confluence desc, then by best available signal score.
    out["sort_key"] = out[["cam_score", "improvement", "inflection"]].max(axis=1)
    return out.sort_values(["confluence", "sort_key"], ascending=[False, False]).drop(columns=["sort_key"]).reset_index(drop=True)


def rank_inflecters(
    cfg: Config,
    tickers: list[str],
    *,
    short: int = 4,
    long: int = 8,
    top: int = 30,
    min_score_now: float | None = None,
) -> pd.DataFrame:
    """Tickers whose technical score is *accelerating*.

    Inflection = (score_now - score_short_ago) - (score_short_ago - score_long_ago)
    A positive value means the rate of improvement has increased -- the
    second derivative is positive. These are the "the turn is happening
    right now" names, before they show up in golden-cross / improver lists.
    """
    from .technicals import load_price_cache
    cache = load_price_cache(cfg)
    if cache.empty:
        return pd.DataFrame()
    scores = _scores_at(cache, tickers, weeks=[-long, -short, 0])
    if scores.empty:
        return scores
    scores.columns = ["score_long", "score_short", "score_now"]
    recent = scores["score_now"] - scores["score_short"]
    prior = scores["score_short"] - scores["score_long"]
    scores["delta_recent"] = recent
    scores["delta_prior"] = prior
    scores["inflection"] = recent - prior
    if min_score_now is not None:
        scores = scores[scores["score_now"] >= float(min_score_now)]
    return _decorate(cfg, cache, scores.sort_values("inflection", ascending=False).head(top))


def _decorate(cfg: Config, cache: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Attach close, vs SMA40, state, signal, and social-mention totals."""
    from .technicals import signals_for_close
    out_rows: list[dict] = []
    daily = _per_ticker_daily(cfg)
    soc = daily.groupby("ticker")["mentions"].sum() if not daily.empty else None
    for ticker, row in df.iterrows():
        close = cache[ticker].dropna()
        sig = signals_for_close(close)
        if sig is None or sig.empty:
            continue
        last = sig.iloc[-1]
        v40 = (float(last["close"]) / float(last["sma_40w"]) - 1.0) * 100.0 if pd.notna(last["sma_40w"]) and last["sma_40w"] else None
        entry = {
            "ticker": ticker,
            **{c: round(float(row[c]), 3) for c in df.columns if pd.notna(row[c])},
            "close": round(float(last["close"]), 2),
            "vs_sma40_pct": round(v40, 1) if v40 is not None else None,
            "state": str(last["state"]),
            "hma_slope_20w": round(float(last["hma_slope_20w"]), 3) if pd.notna(last["hma_slope_20w"]) else None,
            "mentions": int(soc[ticker]) if soc is not None and ticker in soc.index else 0,
        }
        out_rows.append(entry)
    return pd.DataFrame(out_rows)


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
