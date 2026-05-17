"""Hacker News collector via the Algolia search API.

Algolia hosts HN's full-text search index for free with no auth:

    https://hn.algolia.com/api/v1/search?query=...&tags=story&numericFilters=created_at_i>{epoch}

Useful for tech/consumer trends with a heavy SF-tech bias -- a leading
indicator for ARM/NVDA/AMD/PLTR/AI plays and a complement to Reddit.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from ..config import Config
from ..entity_resolution import Resolver
from ..sentiment import SentimentScorer
from .base import http_get_json, normalized_dataframe

log = logging.getLogger(__name__)

HN_BASE = "https://hn.algolia.com/api/v1/search"


def collect_hackernews(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    query: str,
    hours_back: int = 24,
    hits: int = 100,
) -> pd.DataFrame:
    after = datetime.now(timezone.utc) - timedelta(hours=int(hours_back))
    params = {
        "query": query,
        "tags": "(story,comment)",
        "numericFilters": f"created_at_i>{int(after.timestamp())}",
        "hitsPerPage": min(int(hits), 1000),
    }
    try:
        payload = http_get_json(HN_BASE, cfg, params=params)
    except Exception as exc:  # noqa: BLE001
        log.warning("hn fetch failed: %s", exc)
        return normalized_dataframe([])
    rows: list[dict] = []
    for hit in payload.get("hits", []):
        text = " ".join(filter(None, [hit.get("title"), hit.get("story_title"), hit.get("comment_text"), hit.get("story_text")])).strip()
        if not text:
            continue
        mentions = resolver.resolve(text)
        if not mentions:
            continue
        created = hit.get("created_at_i")
        ts = datetime.fromtimestamp(int(created), tz=timezone.utc) if created else datetime.now(timezone.utc)
        s = sentiment.score(text)
        sid = str(hit.get("objectID") or hit.get("story_id") or "")
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={sid}"
        for m in mentions:
            rows.append({
                "timestamp": ts,
                "source": "hackernews",
                "source_id": sid,
                "ticker": m.ticker,
                "alias": m.alias,
                "confidence": m.confidence,
                "via": m.via,
                "text": text[:4000],
                "sentiment": s.compound,
                "sentiment_label": s.label,
                "url": url,
                "author": hit.get("author"),
            })
    log.info("hn: %d mentions from %d hits", len(rows), len(payload.get("hits", [])))
    return normalized_dataframe(rows)
