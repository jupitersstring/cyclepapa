"""Reddit collector via PullPush.io.

PullPush is a public Pushshift-API-compatible replacement; no auth required.
Two endpoints used:

  /reddit/search/submission/?q=...&subreddit=...&after=...&before=...&size=...
  /reddit/search/comment/?q=...

Default rate limit reported by PullPush is roughly 2,000 req/min.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from ..config import Config
from ..entity_resolution import Resolver
from ..sentiment import SentimentScorer
from .base import http_get_json, normalized_dataframe

log = logging.getLogger(__name__)


def _epoch(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _search(cfg: Config, kind: str, params: dict) -> list[dict]:
    url = f"{cfg.pullpush_base}/search/{kind}/"
    payload = http_get_json(url, cfg, params=params)
    if isinstance(payload, dict) and "data" in payload:
        return list(payload["data"])
    return []


def collect_pullpush(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    query: str | None = None,
    subreddit: str | None = None,
    after: datetime | None = None,
    before: datetime | None = None,
    size: int = 100,
    include_comments: bool = False,
) -> pd.DataFrame:
    """Pull submissions (and optionally comments) and emit a mention DataFrame.

    Either `query` or `subreddit` must be provided.
    """
    if not query and not subreddit:
        raise ValueError("collect_pullpush requires query or subreddit")

    base_params: dict = {"size": min(int(size), 100)}
    if query:
        base_params["q"] = query
    if subreddit:
        base_params["subreddit"] = subreddit
    if after is not None:
        base_params["after"] = _epoch(after)
    if before is not None:
        base_params["before"] = _epoch(before)

    submissions = _search(cfg, "submission", base_params)
    comments = _search(cfg, "comment", base_params) if include_comments else []
    log.info("pullpush: %d submissions, %d comments", len(submissions), len(comments))

    rows: list[dict] = []
    for s in submissions:
        text = " ".join(filter(None, [s.get("title"), s.get("selftext")])).strip()
        rows.extend(_emit(text, s, "reddit_submission", resolver, sentiment))
    for c in comments:
        text = (c.get("body") or "").strip()
        rows.extend(_emit(text, c, "reddit_comment", resolver, sentiment))

    return normalized_dataframe(rows)


def _emit(text: str, raw: dict, source: str, resolver: Resolver, sentiment: SentimentScorer) -> list[dict]:
    if not text or text in {"[deleted]", "[removed]"}:
        return []
    mentions = resolver.resolve(text)
    if not mentions:
        return []
    ts = raw.get("created_utc")
    timestamp = datetime.fromtimestamp(int(ts), tz=timezone.utc) if ts else None
    perma = raw.get("permalink") or ""
    url = f"https://reddit.com{perma}" if perma and not perma.startswith("http") else perma
    sid = str(raw.get("id") or raw.get("name") or "")
    s = sentiment.score(text)
    out: list[dict] = []
    for m in mentions:
        out.append({
            "timestamp": timestamp,
            "source": source,
            "source_id": sid,
            "ticker": m.ticker,
            "alias": m.alias,
            "confidence": m.confidence,
            "via": m.via,
            "text": text[:4000],
            "sentiment": s.compound,
            "sentiment_label": s.label,
            "url": url,
            "author": raw.get("author"),
        })
    return out
