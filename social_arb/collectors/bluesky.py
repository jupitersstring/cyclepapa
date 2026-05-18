"""Bluesky collector via the public AT Protocol search endpoint.

Bluesky's public app-view exposes search-by-query at:

    https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=...&limit=...

No auth needed, no rate-limit advertised for read-only (be polite at
~1-2 req/sec). Bluesky has become the primary X-emigration destination
for the finance / VC / tech-product crowd in 2025-2026, so it's high
ROI as a fresh social-signal source where the audience hasn't been
saturated yet by alt-data desks.

Output rows feed the same `mentions` table as every other collector.
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

BSKY_BASE = "https://public.api.bsky.app/xrpc"


def collect_bluesky(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    query: str,
    hours_back: int = 24,
    limit: int = 100,
) -> pd.DataFrame:
    """Search Bluesky posts for `query` and return mention rows."""
    after = datetime.now(timezone.utc) - timedelta(hours=int(hours_back))
    url = f"{BSKY_BASE}/app.bsky.feed.searchPosts"
    params = {
        "q": query,
        "limit": min(int(limit), 100),
        "sort": "latest",
        "since": after.isoformat(),
    }
    try:
        payload = http_get_json(url, cfg, params=params)
    except Exception as exc:  # noqa: BLE001
        log.warning("bluesky fetch failed for '%s': %s", query, exc)
        return normalized_dataframe([])

    rows: list[dict] = []
    for post in payload.get("posts", []):
        record = post.get("record") or {}
        text = (record.get("text") or "").strip()
        if not text:
            continue
        mentions = resolver.resolve(text)
        if not mentions:
            continue
        ts_raw = record.get("createdAt") or post.get("indexedAt")
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else datetime.now(timezone.utc)
        except (ValueError, AttributeError):
            ts = datetime.now(timezone.utc)
        sid = post.get("uri") or ""  # at://did:plc:.../.../...
        author = (post.get("author") or {}).get("handle")
        url_view = None
        if sid.startswith("at://"):
            # Translate at-URI to a viewable bsky.app URL.
            parts = sid.replace("at://", "").split("/")
            if len(parts) >= 3:
                url_view = f"https://bsky.app/profile/{parts[0]}/post/{parts[2]}"
        s = sentiment.score(text)
        for m in mentions:
            rows.append({
                "timestamp": ts,
                "source": "bluesky",
                "source_id": sid,
                "ticker": m.ticker,
                "alias": m.alias,
                "confidence": m.confidence,
                "via": m.via,
                "text": text[:4000],
                "sentiment": s.compound,
                "sentiment_label": s.label,
                "url": url_view or "",
                "author": author,
            })
    log.info("bluesky '%s': %d mentions from %d posts", query, len(rows), len(payload.get("posts", [])))
    return normalized_dataframe(rows)
