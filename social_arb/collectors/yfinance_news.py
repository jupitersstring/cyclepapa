"""yfinance news collector.

yfinance exposes Yahoo Finance's per-ticker news feed without any auth or
quota. Best for headline coverage on already-known tickers; pair with GDELT
for discovery-mode breadth.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from ..config import Config
from ..sentiment import SentimentScorer
from .base import normalized_dataframe

log = logging.getLogger(__name__)


def collect_yfinance_news(
    cfg: Config,
    sentiment: SentimentScorer,
    *,
    ticker: str,
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not installed")
        return normalized_dataframe([])
    try:
        news = yf.Ticker(ticker).news or []
    except Exception as exc:  # noqa: BLE001
        log.warning("yfinance news for %s failed: %s", ticker, exc)
        return normalized_dataframe([])
    rows: list[dict] = []
    for item in news:
        content = item.get("content") or item
        title = content.get("title") or item.get("title") or ""
        summary = content.get("summary") or item.get("summary") or ""
        text = (title + " " + summary).strip()
        if not text:
            continue
        ts_raw = content.get("pubDate") or item.get("providerPublishTime")
        ts = None
        if isinstance(ts_raw, (int, float)):
            ts = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
        elif isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                ts = None
        if ts is None:
            ts = datetime.now(timezone.utc)
        sid = str(item.get("uuid") or item.get("id") or content.get("id") or title[:80])
        url = (content.get("canonicalUrl") or {}).get("url") if isinstance(content.get("canonicalUrl"), dict) else None
        url = url or content.get("link") or item.get("link") or ""
        publisher = (content.get("provider") or {}).get("displayName") if isinstance(content.get("provider"), dict) else None
        publisher = publisher or item.get("publisher")
        s = sentiment.score(text)
        rows.append({
            "timestamp": ts,
            "source": "yfinance_news",
            "source_id": sid,
            "ticker": ticker.upper(),
            "alias": ticker.lower(),
            "confidence": 0.95,
            "via": "ticker_feed",
            "text": text[:4000],
            "sentiment": s.compound,
            "sentiment_label": s.label,
            "url": url,
            "author": publisher,
        })
    return normalized_dataframe(rows)
