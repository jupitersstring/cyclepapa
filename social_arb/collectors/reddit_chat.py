"""Reddit chat-flow collector: subreddit megathread comments.

Reddit Chat proper (DMs / group chat) is private and OAuth-only. But the
*pinned daily megathreads* in WSB / r/stocks / r/options / r/StockMarket
function as public chat -- thousands of short, real-time comments per
day with explicit tickers and reactions.

We find megathreads by title patterns (e.g. "What Are Your Moves
Tomorrow", "Daily Discussion Thread", "Options Questions Safe Haven
Thread") then fetch every comment in those threads via PullPush's
`link_id` query. This gives the high-frequency chat-flow signal that
the slower submission-level scrape misses.

Free, no auth needed (uses PullPush.io).
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


# Title patterns that identify the daily megathreads per subreddit.
MEGATHREAD_QUERIES: dict[str, list[str]] = {
    "wallstreetbets": [
        "What Are Your Moves Tomorrow",
        "Daily Discussion Thread",
        "Weekend Discussion Thread",
    ],
    "stocks": ["Daily Discussion", "Rate My Portfolio"],
    "options": ["Options Questions Safe Haven Thread"],
    "StockMarket": ["Discussion Thread"],
    "investing": ["Daily General Discussion"],
    "Daytrading": ["Daily Discussion"],
    "pennystocks": ["Daily Discussion"],
    "smallstreetbets": ["Daily Discussion"],
}


def _find_megathread_ids(
    cfg: Config, *, subreddit: str, query: str, days_back: int = 14, max_threads: int = 30
) -> list[str]:
    """Search PullPush submissions for megathread posts matching `query`."""
    import time
    end = datetime.now(timezone.utc)
    after_ts = int((end - pd.Timedelta(days=int(days_back))).timestamp())
    url = f"{cfg.pullpush_base}/search/submission/"
    params = {
        "q": query,
        "subreddit": subreddit,
        "after": after_ts,
        "size": 100,
        "sort": "desc",
    }
    try:
        payload = http_get_json(url, cfg, params=params)
    except Exception as exc:  # noqa: BLE001
        log.warning("megathread search failed in r/%s: %s", subreddit, exc)
        return []
    data = (payload.get("data") or []) if isinstance(payload, dict) else []
    ids: list[str] = []
    for s in data:
        title = (s.get("title") or "").lower()
        if query.lower() not in title:
            continue
        sid = s.get("id")
        if sid:
            ids.append(sid)
        if len(ids) >= max_threads:
            break
    time.sleep(0.4)
    return ids


def _fetch_thread_comments(
    cfg: Config, *, link_id: str, max_pages: int = 5
) -> list[dict]:
    """Pull all comments under a Reddit submission via PullPush.

    PullPush returns comments tagged with `link_id == t3_{submission_id}`.
    `size=100` per page; iterate with `before=` until empty.
    """
    import time
    out: list[dict] = []
    cursor = None
    url = f"{cfg.pullpush_base}/search/comment/"
    for _ in range(max_pages):
        params = {"link_id": f"t3_{link_id}", "size": 100, "sort": "desc"}
        if cursor:
            params["before"] = cursor
        try:
            payload = http_get_json(url, cfg, params=params)
        except Exception as exc:  # noqa: BLE001
            log.debug("comment fetch failed for %s: %s", link_id, exc)
            break
        batch = (payload.get("data") or []) if isinstance(payload, dict) else []
        if not batch:
            break
        out.extend(batch)
        cursor = batch[-1].get("created_utc")
        if cursor is None:
            break
        time.sleep(0.2)
    return out


def collect_reddit_chat(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    subreddit: str,
    days_back: int = 7,
    max_threads_per_query: int = 10,
) -> pd.DataFrame:
    """Pull all comments from recent megathreads in a subreddit.

    Output rows tagged source=`reddit_chat:{subreddit}` so the per-source
    leaderboard distinguishes high-frequency chat-flow from slow-post
    feed (which lives under `reddit_submission` / `reddit_comment`).
    """
    queries = MEGATHREAD_QUERIES.get(subreddit, ["Daily Discussion"])
    all_rows: list[dict] = []
    for q in queries:
        thread_ids = _find_megathread_ids(
            cfg, subreddit=subreddit, query=q, days_back=days_back,
            max_threads=max_threads_per_query,
        )
        log.info("r/%s '%s': %d megathreads found", subreddit, q, len(thread_ids))
        for link_id in thread_ids:
            comments = _fetch_thread_comments(cfg, link_id=link_id)
            for c in comments:
                body = (c.get("body") or "").strip()
                if not body or body in {"[deleted]", "[removed]"}:
                    continue
                if len(body) < 10:  # skip "lol" / single emoji comments
                    continue
                mentions = resolver.resolve(body)
                if not mentions:
                    continue
                ts_raw = c.get("created_utc")
                ts = (datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
                      if ts_raw else datetime.now(timezone.utc))
                s = sentiment.score(body)
                sid = str(c.get("id") or c.get("name") or "")
                permalink = c.get("permalink") or ""
                url_view = f"https://reddit.com{permalink}" if permalink else ""
                for m in mentions:
                    all_rows.append({
                        "timestamp": ts,
                        "source": f"reddit_chat:{subreddit}",
                        "source_id": sid,
                        "ticker": m.ticker,
                        "alias": m.alias,
                        "confidence": m.confidence,
                        "via": m.via,
                        "text": body[:4000],
                        "sentiment": s.compound,
                        "sentiment_label": s.label,
                        "url": url_view,
                        "author": c.get("author"),
                    })
    return normalized_dataframe(all_rows)
