"""Mastodon federated-search collector.

Mastodon is the decentralized X alternative; each instance runs its own
ActivityPub server. The instance's REST API exposes public search at:

    https://{instance}/api/v2/search?q=...&type=statuses&resolve=true

No auth required for public search; the instance is the rate limiter.
The post-Twitter migrant base on Mastodon skews heavily toward
infosec, journalism, and tech-adjacent finance discussion, with
mastodon.social, infosec.exchange, and ~~mas.to~~ being the largest
generalist English instances.

We try a list of large English-language instances; the federated nature
of Mastodon means a search on one instance will also surface relevant
content from other instances it federates with.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import requests

from ..config import Config
from ..entity_resolution import Resolver
from ..sentiment import SentimentScorer
from .base import normalized_dataframe

log = logging.getLogger(__name__)

MASTODON_INSTANCES = [
    "https://mastodon.social",
    "https://mastodon.online",
    "https://mas.to",
    "https://hachyderm.io",
    "https://infosec.exchange",
]


def _try_search(instance: str, query: str, limit: int, cfg: Config) -> list[dict]:
    url = f"{instance}/api/v2/search"
    try:
        r = requests.get(
            url, params={"q": query, "type": "statuses", "limit": min(int(limit), 40)},
            headers={"User-Agent": cfg.user_agent, "Accept": "application/json"},
            timeout=cfg.http_timeout,
        )
        if r.status_code != 200:
            return []
        return (r.json() or {}).get("statuses", []) or []
    except (requests.RequestException, ValueError) as exc:
        log.debug("mastodon %s failed: %s", instance, exc)
        return []


def collect_mastodon(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    query: str,
    limit: int = 40,
) -> pd.DataFrame:
    """Search Mastodon for `query` across multiple instances."""
    seen: set[str] = set()
    rows: list[dict] = []
    for instance in MASTODON_INSTANCES:
        statuses = _try_search(instance, query, limit, cfg)
        if not statuses:
            continue
        for st in statuses:
            sid = str(st.get("id") or st.get("uri") or "")
            if sid in seen:
                continue
            seen.add(sid)
            # `content` is HTML; strip tags.
            html = st.get("content") or ""
            import re as _re
            text = _re.sub(r"<[^>]+>", " ", html).strip()
            if not text or len(text) < 10:
                continue
            mentions = resolver.resolve(text)
            if not mentions:
                continue
            ts_raw = st.get("created_at")
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else datetime.now(timezone.utc)
            except (ValueError, AttributeError):
                ts = datetime.now(timezone.utc)
            account = (st.get("account") or {}).get("acct") or "?"
            url = st.get("url") or ""
            s = sentiment.score(text)
            for m in mentions:
                rows.append({
                    "timestamp": ts,
                    "source": f"mastodon:{instance.replace('https://','')}",
                    "source_id": sid,
                    "ticker": m.ticker,
                    "alias": m.alias,
                    "confidence": m.confidence * 0.9,
                    "via": m.via,
                    "text": text[:4000],
                    "sentiment": s.compound,
                    "sentiment_label": s.label,
                    "url": url,
                    "author": account,
                })
        if rows:
            break  # one good instance is enough
    log.info("mastodon: %d rows for '%s'", len(rows), query)
    return normalized_dataframe(rows)
