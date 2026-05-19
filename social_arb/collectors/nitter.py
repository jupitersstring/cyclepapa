"""Nitter scraper -- public X/Twitter mirror, free, no auth.

Nitter is an open-source front-end for Twitter/X that exposes the same
content without auth or rate-limit gates. After Twitter's API monetization
many instances shut down, but a handful remain online in 2025-26:

    nitter.privacydev.net
    nitter.poast.org
    nitter.tiekoetter.com
    nitter.salastil.com
    nitter.lucabased.xyz

We try each in order and fall back through the list when one returns
non-200 / Cloudflare wall / empty.

Each instance's search endpoint:
    https://{instance}/search?q=...&f=tweets

Returns standard HTML; we parse with BeautifulSoup.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote_plus

import pandas as pd
import requests

from ..config import Config
from ..entity_resolution import Resolver
from ..sentiment import SentimentScorer
from .base import normalized_dataframe

log = logging.getLogger(__name__)

NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.tiekoetter.com",
    "https://nitter.salastil.com",
    "https://nitter.lucabased.xyz",
    "https://nitter.net",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.5",
}


def _try_instances(path: str, *, timeout: float = 15.0) -> str | None:
    """Try each Nitter instance until one returns 200 with usable HTML."""
    for base in NITTER_INSTANCES:
        url = f"{base}{path}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code != 200:
                log.debug("nitter %s returned %d", base, r.status_code)
                continue
            text = r.text
            if "Just a moment" in text or "Enable JavaScript" in text:
                log.debug("nitter %s: cloudflare wall", base)
                continue
            if len(text) < 500:
                continue
            return text
        except requests.RequestException as exc:
            log.debug("nitter %s failed: %s", base, exc)
            continue
    return None


def collect_nitter(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    query: str,
    max_tweets: int = 100,
) -> pd.DataFrame:
    """Search X via the first working Nitter instance and resolve mentions."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("beautifulsoup4 not installed; nitter collector disabled")
        return normalized_dataframe([])

    html = _try_instances(f"/search?f=tweets&q={quote_plus(query)}&since=&until=&near=")
    if html is None:
        log.warning("nitter: no working instance for '%s'", query)
        return normalized_dataframe([])

    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    timeline_items = soup.select("div.timeline-item")[: int(max_tweets)]
    for item in timeline_items:
        text_el = item.select_one("div.tweet-content")
        if not text_el:
            continue
        text = text_el.get_text(" ", strip=True)
        if not text or len(text) < 5:
            continue
        # Author / handle.
        handle_el = item.select_one("a.username")
        author = handle_el.get_text(strip=True) if handle_el else None
        # Date.
        date_el = item.select_one("span.tweet-date a")
        ts = datetime.now(timezone.utc)
        if date_el and date_el.has_attr("title"):
            try:
                ts = datetime.strptime(
                    date_el["title"].split(" · ")[0], "%b %d, %Y"
                ).replace(tzinfo=timezone.utc)
            except (ValueError, IndexError):
                pass
        # Permalink.
        link_el = item.select_one("a.tweet-link")
        href = link_el["href"] if link_el and link_el.has_attr("href") else ""
        url = f"https://twitter.com{href}" if href and not href.startswith("http") else href
        sid = href or f"nitter:{abs(hash(text))}"

        mentions = resolver.resolve(text)
        if not mentions:
            continue
        s = sentiment.score(text)
        for m in mentions:
            rows.append({
                "timestamp": ts,
                "source": "x_via_nitter",
                "source_id": sid,
                "ticker": m.ticker,
                "alias": m.alias,
                "confidence": m.confidence * 0.9,
                "via": m.via,
                "text": text[:4000],
                "sentiment": s.compound,
                "sentiment_label": s.label,
                "url": url,
                "author": author,
            })
    log.info("nitter: %d X mention rows from query='%s'", len(rows), query)
    return normalized_dataframe(rows)
