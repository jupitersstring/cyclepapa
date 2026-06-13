"""Per-source z-scores + breadth scoring.

The spec's "validate via independent signals" is operationalised as
breadth: how many distinct sources show a positive z-score for the
same ticker in the same window. This is structurally different from
a pooled z-score (which is dominated by whichever source happens to
be backfilled deepest) -- a ticker lighting up on 3 sources at z>1
each is a much higher-conviction signal than the same total magnitude
concentrated on one source.

Two outputs:

  - per_source_z(window_days, baseline_days): for each (ticker, source),
    the recent-vs-baseline z-score of SUM(weight) per day. Returns a
    long-form DataFrame.

  - breadth_score(z_threshold, ...): aggregates the per-source z into:
        n_sources_positive  -- count of sources with z >= threshold
        max_source_z        -- the strongest single-source signal
        mean_positive_z     -- average z across sources that fired
        combined_score      -- breadth-weighted composite
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .config import Config

log = logging.getLogger(__name__)


def _load_weighted_daily(cfg: Config) -> pd.DataFrame:
    """Long-form: one row per (ticker, source, date) with SUM(weight)
    and AVG(sentiment) -- the clean primitive for downstream stats."""
    from . import storage
    with storage.connect(cfg) as con:
        return con.execute(
            """
            SELECT
                CAST(timestamp AS DATE) AS date,
                ticker,
                source,
                SUM(COALESCE(weight, 1.0)) AS weight,
                AVG(sentiment) AS sentiment
            FROM mentions
            GROUP BY 1, 2, 3
            ORDER BY 1
            """
        ).df()


def per_source_z(
    cfg: Config,
    *,
    window_days: int = 5,
    baseline_days: int = 30,
    min_baseline_weight: float = 1.0,
    as_of: pd.Timestamp | None = None,
    df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Per (ticker, source) recent-vs-baseline z-score on weighted mentions.

    `as_of` -- compute the signal AS OF this date (the "end" date for the
    recent window). Defaults to the latest date in the store. Pass an
    explicit date for backtesting/event-study sweeps over history.

    `df` -- pre-loaded weighted-daily frame (from _load_weighted_daily).
    Passing it lets a walker compute many `as_of` dates without re-querying
    DuckDB each time.
    """
    if df is None:
        df = _load_weighted_daily(cfg)
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    end = pd.Timestamp(as_of) if as_of is not None else df["date"].max()
    recent_cutoff = end - pd.Timedelta(days=int(window_days) - 1)
    baseline_cutoff = end - pd.Timedelta(days=int(baseline_days) + int(window_days))

    # IMPORTANT: cap the recent window at `end` so historical sweeps don't
    # leak future data into the "recent" stats.
    recent = df[(df["date"] >= recent_cutoff) & (df["date"] <= end)]
    baseline = df[(df["date"] < recent_cutoff) & (df["date"] >= baseline_cutoff)]
    rstats = recent.groupby(["ticker", "source"]).agg(
        recent_weight_mean=("weight", "mean"),
        recent_sent_mean=("sentiment", "mean"),
    )
    bstats = baseline.groupby(["ticker", "source"]).agg(
        baseline_weight_mean=("weight", "mean"),
        baseline_weight_std=("weight", "std"),
        baseline_sent_mean=("sentiment", "mean"),
    )
    out = rstats.join(bstats, how="inner").reset_index()
    if out.empty:
        return out
    out = out[out["baseline_weight_mean"] >= float(min_baseline_weight)]
    out["baseline_weight_std"] = out["baseline_weight_std"].replace(0.0, np.nan)
    out["z"] = (
        (out["recent_weight_mean"] - out["baseline_weight_mean"])
        / out["baseline_weight_std"]
    )
    out["z"] = out["z"].fillna(0.0).round(2)
    out["recent_weight_mean"] = out["recent_weight_mean"].round(2)
    out["baseline_weight_mean"] = out["baseline_weight_mean"].round(2)
    return out


def breadth_score(
    cfg: Config,
    *,
    z_threshold: float = 1.0,
    window_days: int = 5,
    baseline_days: int = 30,
    min_breadth: int = 2,
    top: int = 30,
    as_of: pd.Timestamp | None = None,
    df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Aggregate per-source z into a per-ticker breadth signal.

    Returns the top `top` tickers ranked by `combined_score`:

      n_sources_positive : how many distinct sources show z >= z_threshold
      max_source_z       : strongest single-source signal
      mean_positive_z    : mean z across firing sources
      sentiment_change   : recent_sent - baseline_sent (weighted by recent rows)
      combined_score     : 2*n_sources_positive + 0.5*max_source_z +
                           mean_positive_z + sentiment_change*3
    """
    per = per_source_z(
        cfg, window_days=window_days, baseline_days=baseline_days,
        as_of=as_of, df=df,
    )
    if per.empty:
        return pd.DataFrame()
    positive = per[per["z"] >= float(z_threshold)]
    by_ticker = positive.groupby("ticker").agg(
        n_sources_positive=("source", "nunique"),
        max_source_z=("z", "max"),
        mean_positive_z=("z", "mean"),
        sources=("source", lambda s: ",".join(sorted(set(s)))),
    )
    sent = per.groupby("ticker").agg(
        sentiment_change=("recent_sent_mean", "mean"),  # placeholder
    )
    sent_delta = per.copy()
    sent_delta["delta"] = sent_delta["recent_sent_mean"] - sent_delta["baseline_sent_mean"]
    sent_delta = sent_delta.groupby("ticker")["delta"].mean()
    by_ticker["sentiment_change"] = sent_delta.reindex(by_ticker.index).fillna(0.0).round(2)
    by_ticker["max_source_z"] = by_ticker["max_source_z"].round(2)
    by_ticker["mean_positive_z"] = by_ticker["mean_positive_z"].round(2)
    by_ticker = by_ticker[by_ticker["n_sources_positive"] >= int(min_breadth)]
    by_ticker["combined_score"] = (
        2.0 * by_ticker["n_sources_positive"]
        + 0.5 * by_ticker["max_source_z"]
        + by_ticker["mean_positive_z"]
        + by_ticker["sentiment_change"] * 3.0
    ).round(2)
    by_ticker = by_ticker.sort_values(
        ["n_sources_positive", "combined_score"], ascending=[False, False],
    ).head(int(top))
    return by_ticker.reset_index()
