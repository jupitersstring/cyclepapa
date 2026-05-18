"""4chan /biz/ collector via the public JSON API.

4chan exposes a completely free, no-auth JSON API:

    https://a.4cdn.org/biz/catalog.json     <- list of all active threads
    https://a.4cdn.org/biz/thread/{id}.json <- full thread w/ all replies
    https://archive.4plebs.org/biz/...       <- historical archive

/biz/ is the finance / crypto / business board. Audience skews
contrarian and frequently early on speculative micro-caps, meme moves,
and crypto-adjacent equity narratives. Note: signal is noisy and the
sentiment lexicon is unusual; we tag rows source='fourchan_biz' so the
leaderboard's per-source breakdown isolates them.

Be polite -- 4chan's TOS requests <= 1 req/sec.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from ..config import Config
from ..entity_resolution import Resolver
from ..sentiment import SentimentScorer
from .base import normalized_dataframe

log = logging.getLogger(__name__)

CATALOG_URL = "https://a.4cdn.org/biz/catalog.json"
THREAD_URL = "https://a.4cdn.org/biz/thread/{thread_id}.json"


def _fetch(url: str, cfg: Config) -> dict | None:
    try:
        r = requests.get(url, headers={"User-Agent": cfg.user_agent}, timeout=20)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as exc:
        log.debug("4chan fetch failed %s: %s", url, exc)
        return None


def collect_fourchan_biz(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    max_threads: int = 50,
    min_replies: int = 5,
    sleep_between: float = 1.1,
) -> pd.DataFrame:
    """Scrape /biz/ catalog -> sample threads -> extract ticker mentions.

    Picks the `max_threads` busiest threads (by reply count, capped by
    `min_replies`) and pulls all posts in each.
    """
    catalog = _fetch(CATALOG_URL, cfg)
    if not catalog:
        return normalized_dataframe([])

    # Catalog is a list of pages, each with a "threads" list of OP metadata.
    threads: list[dict] = []
    for page in catalog:
        for t in page.get("threads", []):
            replies = int(t.get("replies", 0) or 0)
            if replies < min_replies:
                continue
            threads.append({"no": int(t["no"]), "replies": replies,
                            "sub": (t.get("sub") or t.get("com") or "")[:200]})
    threads.sort(key=lambda r: r["replies"], reverse=True)
    threads = threads[: int(max_threads)]
    log.info("4chan /biz/: %d high-activity threads selected", len(threads))

    all_rows: list[dict] = []
    for th in threads:
        time.sleep(sleep_between)
        data = _fetch(THREAD_URL.format(thread_id=th["no"]), cfg)
        if not data:
            continue
        posts = data.get("posts", [])
        for post in posts:
            com = post.get("com") or ""
            # 4chan HTML uses <br>, links etc. Strip tags very simply.
            import re as _re
            text = _re.sub(r"<[^>]+>", " ", com)
            text = (text.replace("&gt;", ">").replace("&lt;", "<")
                    .replace("&quot;", '"').replace("&#039;", "'")
                    .replace("&amp;", "&")).strip()
            if not text or len(text) < 15:
                continue
            mentions = resolver.resolve(text)
            if not mentions:
                continue
            ts_raw = post.get("time")
            ts = (datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
                  if ts_raw else datetime.now(timezone.utc))
            s = sentiment.score(text)
            sid = f"4ch:{th['no']}:{post.get('no')}"
            url = f"https://boards.4chan.org/biz/thread/{th['no']}#p{post.get('no')}"
            for m in mentions:
                all_rows.append({
                    "timestamp": ts,
                    "source": "fourchan_biz",
                    "source_id": sid,
                    "ticker": m.ticker,
                    "alias": m.alias,
                    "confidence": m.confidence * 0.85,  # noisy source, downweight
                    "via": m.via,
                    "text": text[:4000],
                    "sentiment": s.compound,
                    "sentiment_label": s.label,
                    "url": url,
                    "author": (post.get("name") or "Anonymous")[:80],
                })
    log.info("4chan /biz/: %d mention rows from %d threads", len(all_rows), len(threads))
    return normalized_dataframe(all_rows)
