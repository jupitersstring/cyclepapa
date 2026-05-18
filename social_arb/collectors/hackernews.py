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


def backfill_hackernews(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    query: str,
    days_back: int = 365,
    chunk_days: int = 14,
    hits_per_chunk: int = 200,
) -> pd.DataFrame:
    """Sweep HN history in `chunk_days` windows for `days_back` total.

    Algolia's HN index supports numeric range filters via
    `numericFilters=created_at_i>...,created_at_i<...`. We slide a window
    backward from now to days_back, accumulating mention rows.
    """
    import time
    end = datetime.now(timezone.utc)
    cur_end = end
    cur_start = cur_end - timedelta(days=int(chunk_days))
    earliest = end - timedelta(days=int(days_back))
    all_rows: list[dict] = []
    while cur_end > earliest:
        params = {
            "query": query,
            "tags": "(story,comment)",
            "numericFilters": (
                f"created_at_i>{int(cur_start.timestamp())},"
                f"created_at_i<{int(cur_end.timestamp())}"
            ),
            "hitsPerPage": min(int(hits_per_chunk), 1000),
        }
        try:
            payload = http_get_json(HN_BASE, cfg, params=params)
        except Exception as exc:  # noqa: BLE001
            log.warning("hn backfill chunk failed: %s", exc)
            cur_end = cur_start
            cur_start = cur_end - timedelta(days=int(chunk_days))
            continue
        hits = payload.get("hits", []) or []
        for hit in hits:
            text = " ".join(filter(None, [
                hit.get("title"), hit.get("story_title"),
                hit.get("comment_text"), hit.get("story_text"),
            ])).strip()
            if not text:
                continue
            mentions = resolver.resolve(text)
            if not mentions:
                continue
            created = hit.get("created_at_i")
            ts = datetime.fromtimestamp(int(created), tz=timezone.utc) if created else cur_end
            s = sentiment.score(text)
            sid = str(hit.get("objectID") or hit.get("story_id") or "")
            for m in mentions:
                all_rows.append({
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
                    "url": hit.get("url") or f"https://news.ycombinator.com/item?id={sid}",
                    "author": hit.get("author"),
                })
        cur_end = cur_start
        cur_start = cur_end - timedelta(days=int(chunk_days))
        time.sleep(0.5)  # be polite
    log.info("hn backfill '%s' (%dd): %d mention rows", query, days_back, len(all_rows))
    return normalized_dataframe(all_rows)


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
