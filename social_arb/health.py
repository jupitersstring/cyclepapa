"""Pipeline health & coverage audit.

A single function that returns a tidy report on:
  * universe sizes (financedatabase total / US-liquid / consumer)
  * price cache (weekly + daily): cols, valid coverage, last bar date
  * mention store: row count, distinct tickers, sources, last ingest
  * collector lineage: which sources contributed how many rows
  * sentiment library status (VADER / LM / FinBERT)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .config import Config


@dataclass
class HealthReport:
    universe: dict[str, Any] = field(default_factory=dict)
    weekly_cache: dict[str, Any] = field(default_factory=dict)
    daily_cache: dict[str, Any] = field(default_factory=dict)
    mentions: dict[str, Any] = field(default_factory=dict)
    sources: pd.DataFrame = field(default_factory=pd.DataFrame)
    sentiment: dict[str, Any] = field(default_factory=dict)

    def to_text(self) -> str:
        lines: list[str] = []
        lines.append("=== UNIVERSE ===")
        for k, v in self.universe.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("=== WEEKLY PRICE CACHE ===")
        for k, v in self.weekly_cache.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("=== DAILY PRICE CACHE ===")
        for k, v in self.daily_cache.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("=== MENTION STORE ===")
        for k, v in self.mentions.items():
            lines.append(f"  {k}: {v}")
        if not self.sources.empty:
            lines.append("")
            lines.append("=== SOURCE BREAKDOWN ===")
            lines.append(self.sources.to_string(index=False))
        lines.append("")
        lines.append("=== SENTIMENT LIBRARIES ===")
        for k, v in self.sentiment.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)


def collect(cfg: Config) -> HealthReport:
    rep = HealthReport()

    # Universe
    try:
        from . import universe as uni_mod
        full = uni_mod.build_universe(cfg)
        us = uni_mod.filter_us_liquid(full)
        cons = uni_mod.filter_consumer_focused(us)
        try:
            na = uni_mod.filter_north_american_liquid(full)
        except Exception:
            na = pd.DataFrame()
        rep.universe = {
            "financedatabase_total_equities": len(full),
            "us_liquid": len(us),
            "us_liquid_consumer_comms": len(cons),
            "north_american_liquid_us_plus_canada": len(na),
            "sectors_in_us_universe": dict(us["sector"].value_counts().head(10)) if "sector" in us.columns else {},
        }
    except Exception as exc:  # noqa: BLE001
        rep.universe = {"error": str(exc)}

    # Weekly cache
    try:
        from .technicals import load_price_cache
        cache = load_price_cache(cfg)
        valid = (cache.notna().sum() >= 42)
        rep.weekly_cache = {
            "tickers_in_cache": int(cache.shape[1]) if not cache.empty else 0,
            "valid_tickers_ge_42_bars": int(valid.sum()) if not cache.empty else 0,
            "weeks_of_history": int(len(cache)) if not cache.empty else 0,
            "last_weekly_bar": str(cache.index[-1].date()) if not cache.empty and len(cache.index) else None,
        }
    except Exception as exc:  # noqa: BLE001
        rep.weekly_cache = {"error": str(exc)}

    # Daily cache
    try:
        from .technicals_daily import load_daily_cache
        dclose, dvol = load_daily_cache(cfg)
        valid_d = (dclose.notna().sum() >= 60) if not dclose.empty else pd.Series(dtype=bool)
        rep.daily_cache = {
            "tickers_in_cache": int(dclose.shape[1]) if not dclose.empty else 0,
            "valid_tickers_ge_60_bars": int(valid_d.sum()) if not dclose.empty else 0,
            "days_of_history": int(len(dclose)) if not dclose.empty else 0,
            "last_daily_bar": str(dclose.index[-1].date()) if not dclose.empty and len(dclose.index) else None,
            "volume_cache_present": (not dvol.empty),
        }
    except Exception as exc:  # noqa: BLE001
        rep.daily_cache = {"error": str(exc)}

    # Mentions store
    try:
        from . import storage
        with storage.connect(cfg) as con:
            n_rows = con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
            n_tickers = con.execute("SELECT COUNT(DISTINCT ticker) FROM mentions").fetchone()[0]
            ts_min, ts_max = con.execute("SELECT MIN(timestamp), MAX(timestamp) FROM mentions").fetchone()
            src_rows = con.execute(
                "SELECT source, COUNT(*) AS rows, COUNT(DISTINCT ticker) AS tickers, "
                "MAX(timestamp) AS last_seen FROM mentions GROUP BY source ORDER BY rows DESC"
            ).df()
        rep.mentions = {
            "rows": int(n_rows),
            "distinct_tickers": int(n_tickers),
            "earliest_mention": str(ts_min) if ts_min else None,
            "latest_mention": str(ts_max) if ts_max else None,
        }
        rep.sources = src_rows
    except Exception as exc:  # noqa: BLE001
        rep.mentions = {"error": str(exc)}

    # Sentiment libraries
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        SentimentIntensityAnalyzer()
        vader = "OK"
    except Exception as exc:  # noqa: BLE001
        vader = f"unavailable ({exc})"
    try:
        from .sentiment_lm import LM_POSITIVE, LM_NEGATIVE
        lm = f"OK ({len(LM_POSITIVE)} pos, {len(LM_NEGATIVE)} neg embedded)"
    except Exception as exc:  # noqa: BLE001
        lm = f"unavailable ({exc})"
    rep.sentiment = {
        "vader": vader,
        "loughran_mcdonald": lm,
    }
    return rep
