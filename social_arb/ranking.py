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
