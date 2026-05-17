"""High-level orchestration for the social arbitrage pipeline.

`Pipeline` wires the universe, aliases, resolver, sentiment scorer, and
storage together; collectors call into it to persist mentions, and the
dashboard/notebook reads from it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from . import aliases as aliases_mod
from . import storage, universe
from .anomaly import AnomalyParams, ewma_zscore, joint_signal
from .collectors import (
    collect_apewisdom,
    collect_form4,
    collect_gdelt,
    collect_hackernews,
    collect_pullpush,
    collect_reddit_rss,
    collect_stocktwits,
    collect_wikipedia,
    collect_yfinance_news,
)
from .config import Config
from .entity_resolution import Resolver
from .sentiment import SentimentScorer

log = logging.getLogger(__name__)


@dataclass
class Pipeline:
    cfg: Config
    resolver: Resolver
    sentiment: SentimentScorer
    universe_df: pd.DataFrame

    @classmethod
    def build(cls, cfg: Config | None = None, refresh_universe: bool = False) -> "Pipeline":
        cfg = cfg or Config()
        cfg.ensure_dirs()
        uni = universe.build_universe(cfg, refresh=refresh_universe)
        aliases = aliases_mod.load_aliases(cfg) + aliases_mod.from_universe(uni)
        resolver = Resolver(aliases)
        sentiment = SentimentScorer()
        return cls(cfg=cfg, resolver=resolver, sentiment=sentiment, universe_df=uni)

    # ---- collectors -----------------------------------------------------

    def run_reddit(
        self,
        *,
        query: str | None = None,
        subreddit: str | None = None,
        days_back: int = 1,
        include_comments: bool = False,
        size: int = 100,
    ) -> int:
        after = datetime.utcnow() - timedelta(days=days_back)
        df = collect_pullpush(
            self.cfg, self.resolver, self.sentiment,
            query=query, subreddit=subreddit, after=after,
            size=size, include_comments=include_comments,
        )
        return storage.upsert_mentions(self.cfg, df)

    def run_apewisdom(self, *, filter_name: str = "wallstreetbets", pages: int = 1) -> int:
        df = collect_apewisdom(self.cfg, filter_name=filter_name, pages=pages)
        return storage.upsert_mentions(self.cfg, df)

    def run_gdelt(self, *, query: str, hours_back: int = 24, max_records: int = 250) -> int:
        df = collect_gdelt(
            self.cfg, self.resolver, self.sentiment,
            query=query, hours_back=hours_back, max_records=max_records,
        )
        return storage.upsert_mentions(self.cfg, df)

    def run_stocktwits(self, *, ticker: str) -> int:
        df = collect_stocktwits(self.cfg, self.sentiment, ticker=ticker)
        return storage.upsert_mentions(self.cfg, df)

    def run_hackernews(self, *, query: str, hours_back: int = 24, hits: int = 100) -> int:
        df = collect_hackernews(
            self.cfg, self.resolver, self.sentiment,
            query=query, hours_back=hours_back, hits=hits,
        )
        return storage.upsert_mentions(self.cfg, df)

    def run_reddit_rss(self, *, subreddit: str, listing: str = "new", period: str | None = None) -> int:
        df = collect_reddit_rss(
            self.cfg, self.resolver, self.sentiment,
            subreddit=subreddit, listing=listing, period=period,
        )
        return storage.upsert_mentions(self.cfg, df)

    def run_yfinance_news(self, *, ticker: str) -> int:
        df = collect_yfinance_news(self.cfg, self.sentiment, ticker=ticker)
        return storage.upsert_mentions(self.cfg, df)

    def run_wikipedia(self, *, title: str, ticker: str, days_back: int = 60) -> int:
        df = collect_wikipedia(self.cfg, title=title, ticker=ticker, days_back=days_back)
        return storage.upsert_mentions(self.cfg, df)

    def run_form4(self, *, days_back: int = 7, max_records: int = 100) -> int:
        df = collect_form4(self.cfg, days_back=days_back, max_records=max_records)
        return storage.upsert_mentions(self.cfg, df)

    # ---- analysis -------------------------------------------------------

    def daily_counts(self, ticker: str | None = None, source: str | None = None) -> pd.DataFrame:
        return storage.daily_counts(self.cfg, ticker=ticker, source=source)

    def detect_anomalies(
        self,
        ticker: str,
        *,
        params: AnomalyParams | None = None,
    ) -> pd.DataFrame:
        counts = self.daily_counts(ticker=ticker)
        if counts.empty:
            return pd.DataFrame()
        series = counts.groupby("date")["mentions"].sum()
        series.index = pd.to_datetime(series.index)
        series = series.asfreq("D", fill_value=0)
        return ewma_zscore(series, params)

    def detect_joint_signals(
        self,
        ticker: str,
        *,
        z_mentions: float = 2.0,
        z_sent: float = 1.5,
    ) -> pd.DataFrame:
        counts = self.daily_counts(ticker=ticker)
        if counts.empty:
            return pd.DataFrame()
        agg = counts.groupby("date").agg(
            mentions=("mentions", "sum"),
            sentiment_mean=("sentiment_mean", "mean"),
        )
        agg.index = pd.to_datetime(agg.index)
        agg = agg.asfreq("D", fill_value=0.0)
        return joint_signal(
            agg["mentions"], agg["sentiment_mean"],
            z_mentions=z_mentions, z_sent=z_sent,
        )

    def all_tickers(self) -> list[str]:
        return storage.all_tickers(self.cfg)
