"""Reddit RSS collector -- a no-auth fallback when PullPush lags.

Reddit serves a public RSS/Atom feed at:

    https://www.reddit.com/r/{subreddit}/new/.rss
    https://www.reddit.com/r/{subreddit}/.rss
    https://www.reddit.com/r/{subreddit}/top/.rss?t=week

No OAuth, no API key, no PRAW client setup -- just a User-Agent header.
Limited to ~25 newest posts per feed; pair with PRAW for breadth.
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


def _parse(feed_url: str, cfg: Config) -> list[dict]:
    """Parse Reddit's Atom feed using stdlib xml.etree (no feedparser dep).

    Reddit blocks the default `requests` UA. Use an old.reddit subdomain plus
    a browser-style UA -- both reliably serve the public RSS without auth.
    """
    import xml.etree.ElementTree as ET
    # old.reddit.com is more permissive than www.reddit.com for RSS.
    feed_url = feed_url.replace("www.reddit.com", "old.reddit.com")
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 social-arb/0.1",
        "Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    }
    r = requests.get(feed_url, headers=headers, timeout=cfg.http_timeout)
    r.raise_for_status()
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError as exc:
        log.warning("rss parse failed for %s: %s", feed_url, exc)
        return []
    out: list[dict] = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        summary = (entry.findtext("atom:content", default="", namespaces=ns) or "").strip()
        link_el = entry.find("atom:link", ns)
        link = link_el.get("href") if link_el is not None else ""
        eid = (entry.findtext("atom:id", default="", namespaces=ns) or link).strip()
        author = (entry.findtext("atom:author/atom:name", default="", namespaces=ns) or "").strip()
        updated = (entry.findtext("atom:updated", default="", namespaces=ns)
                   or entry.findtext("atom:published", default="", namespaces=ns)
                   or "").strip()
        published = None
        if updated:
            try:
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(updated.replace("Z", "+00:00"))
                published = dt.timetuple()
            except ValueError:
                published = None
        out.append({
            "title": title,
            "summary": summary,
            "link": link,
            "id": eid,
            "author": author,
            "published": published,
        })
    return out


def collect_reddit_rss(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    subreddit: str,
    listing: str = "new",
    period: str | None = None,
) -> pd.DataFrame:
    """listing in {'new', 'hot', 'top'}; period in {'hour','day','week','month','year','all'}."""
    if listing == "top" and period:
        url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t={period}"
    else:
        url = f"https://www.reddit.com/r/{subreddit}/{listing}/.rss"
    try:
        entries = _parse(url, cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning("reddit rss r/%s failed: %s", subreddit, exc)
        return normalized_dataframe([])
    rows: list[dict] = []
    for e in entries:
        text = " ".join(filter(None, [e["title"], e["summary"]])).strip()
        # Strip basic HTML tags from RSS summary.
        text = _strip_html(text)
        if not text:
            continue
        mentions = resolver.resolve(text)
        if not mentions:
            continue
        ts_struct = e["published"]
        if ts_struct:
            ts = datetime(*ts_struct[:6], tzinfo=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)
        s = sentiment.score(text)
        for m in mentions:
            rows.append({
                "timestamp": ts,
                "source": f"reddit_rss:{subreddit}",
                "source_id": e["id"],
                "ticker": m.ticker,
                "alias": m.alias,
                "confidence": m.confidence,
                "via": m.via,
                "text": text[:4000],
                "sentiment": s.compound,
                "sentiment_label": s.label,
                "url": e["link"],
                "author": e.get("author"),
            })
    log.info("reddit_rss r/%s: %d mention rows from %d entries", subreddit, len(rows), len(entries))
    return normalized_dataframe(rows)


def _strip_html(s: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", s).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()
