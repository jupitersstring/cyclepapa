"""Apewisdom mention-count collector.

Apewisdom is a free, no-key aggregator that tracks ticker mentions across
WSB, r/stocks, r/cryptocurrency, and similar. Endpoint:

    https://apewisdom.io/api/v1.0/filter/{filter}/page/{page}

Returns the top tickers by 24h mentions plus deltas. We snapshot daily and
treat each filter row as a mention bucket (not individual posts -- since
Apewisdom abstracts that away).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from ..config import Config
from .base import http_get_json, normalized_dataframe

log = logging.getLogger(__name__)

VALID_FILTERS = {
    "all", "all-stocks", "all-crypto",
    "wallstreetbets", "stocks", "cryptocurrency", "stockmarket",
    "options", "investing",
}


def collect_apewisdom(
    cfg: Config,
    *,
    filter_name: str = "wallstreetbets",
    pages: int = 1,
) -> pd.DataFrame:
    if filter_name not in VALID_FILTERS:
        log.warning("apewisdom filter '%s' is non-standard", filter_name)
    rows: list[dict] = []
    now = datetime.now(timezone.utc)
    for page in range(1, max(1, pages) + 1):
        url = f"{cfg.apewisdom_base}/filter/{filter_name}/page/{page}"
        try:
            payload = http_get_json(url, cfg)
        except Exception as exc:  # noqa: BLE001
            log.warning("apewisdom fetch failed: %s", exc)
            break
        for entry in payload.get("results", []):
            ticker = (entry.get("ticker") or "").upper()
            if not ticker:
                continue
            mentions_24h = int(entry.get("mentions") or 0)
            mentions_24h_prev = int(entry.get("mentions_24h_ago") or 0)
            rank = entry.get("rank")
            sentiment = entry.get("sentiment")
            try:
                sentiment_val = float(sentiment) if sentiment is not None else 0.0
            except (TypeError, ValueError):
                sentiment_val = 0.0
            # Emit one synthetic row per ticker per day.
            source_id = f"{filter_name}:{now.date().isoformat()}:{ticker}"
            text = (
                f"apewisdom {filter_name} rank={rank} mentions={mentions_24h} "
                f"prev24h={mentions_24h_prev} sentiment={sentiment}"
            )
            for _ in range(max(1, mentions_24h)):
                # Apewisdom collapses individual posts; we emit one synthetic
                # row per mention for compatibility with the daily-count
                # aggregation downstream. Set confidence at 0.7 to reflect
                # that we don't have post-level text.
                rows.append({
                    "timestamp": now,
                    "source": f"apewisdom:{filter_name}",
                    "source_id": f"{source_id}:{_}",
                    "ticker": ticker,
                    "alias": ticker.lower(),
                    "confidence": 0.7,
                    "via": "apewisdom",
                    "text": text,
                    "sentiment": sentiment_val,
                    "sentiment_label": (
                        "bullish" if sentiment_val > 60
                        else "bearish" if sentiment_val < 40
                        else "neutral"
                    ),
                    "url": "https://apewisdom.io",
                    "author": None,
                })
    return normalized_dataframe(rows)


def fetch_top(
    cfg: Config,
    *,
    filter_name: str = "wallstreetbets",
    page: int = 1,
) -> pd.DataFrame:
    """Return Apewisdom's leaderboard as a tidy DataFrame, no row explosion."""
    url = f"{cfg.apewisdom_base}/filter/{filter_name}/page/{page}"
    payload = http_get_json(url, cfg)
    results = payload.get("results", [])
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    keep = [c for c in ["rank", "ticker", "name", "mentions", "mentions_24h_ago", "upvotes", "sentiment"] if c in df.columns]
    df = df[keep].copy()
    df["captured_at"] = datetime.now(timezone.utc)
    return df
