"""Twitter/X collector via Twikit (session-token client).

Twikit (d60/twikit, 4,200+ GitHub stars) drives X's internal GraphQL
endpoints from a real session, giving full search-results access at
the same data depth as the website. No paid API tier required.

CREDENTIALS: Twikit requires a real (preferably throwaway) X account
to obtain the session token. Set these env vars:

    TWITTER_USERNAME=...
    TWITTER_EMAIL=...
    TWITTER_PASSWORD=...

A cookie file is written to `data/twikit_cookies.json` after the first
successful login so re-runs don't re-auth.

CAVEATS:
  * X actively detects automation; expect occasional account suspensions
    on burner accounts. Rotate as needed.
  * Production deployments should use residential proxies.

This collector is intentionally OPT-IN -- it raises a clear error if
the env vars aren't set so callers can pick the cheapest data path.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..config import Config
from ..entity_resolution import Resolver
from ..sentiment import SentimentScorer
from .base import normalized_dataframe

log = logging.getLogger(__name__)


def _ensure_cookies(client, cookies_path: Path) -> bool:
    """Load cookies if present, otherwise login + save them."""
    if cookies_path.exists():
        try:
            client.load_cookies(str(cookies_path))
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("twikit: failed to load cookies (%s); logging in", exc)
    user = os.environ.get("TWITTER_USERNAME")
    email = os.environ.get("TWITTER_EMAIL")
    pw = os.environ.get("TWITTER_PASSWORD")
    if not (user and email and pw):
        raise RuntimeError(
            "Twikit needs TWITTER_USERNAME, TWITTER_EMAIL, TWITTER_PASSWORD env vars"
        )
    asyncio.run(client.login(auth_info_1=user, auth_info_2=email, password=pw))
    client.save_cookies(str(cookies_path))
    return True


async def _search_async(query: str, count: int, product: str):
    from twikit import Client  # type: ignore
    client = Client("en-US")
    cookies_path = Path("data") / "twikit_cookies.json"
    cookies_path.parent.mkdir(parents=True, exist_ok=True)
    if cookies_path.exists():
        client.load_cookies(str(cookies_path))
    else:
        user = os.environ.get("TWITTER_USERNAME")
        email = os.environ.get("TWITTER_EMAIL")
        pw = os.environ.get("TWITTER_PASSWORD")
        if not (user and email and pw):
            raise RuntimeError(
                "Twikit needs TWITTER_USERNAME, TWITTER_EMAIL, TWITTER_PASSWORD env vars"
            )
        await client.login(auth_info_1=user, auth_info_2=email, password=pw)
        client.save_cookies(str(cookies_path))
    tweets = await client.search_tweet(query, product=product, count=count)
    return list(tweets)


def collect_twitter(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    query: str,
    count: int = 100,
    product: str = "Latest",  # "Top", "Latest", "Media", "People"
) -> pd.DataFrame:
    """Search X via Twikit's session-token GraphQL client."""
    try:
        import twikit  # noqa: F401
    except ImportError:
        log.warning("twikit not installed; pip install twikit")
        return normalized_dataframe([])
    try:
        tweets = asyncio.run(_search_async(query, count, product))
    except RuntimeError as exc:
        # Re-raised by _search_async if creds missing
        log.warning("twikit search failed: %s", exc)
        return normalized_dataframe([])
    except Exception as exc:  # noqa: BLE001
        log.warning("twikit error for '%s': %s", query, exc)
        return normalized_dataframe([])

    rows: list[dict] = []
    for t in tweets:
        text = (getattr(t, "text", "") or "").strip()
        if not text or len(text) < 5:
            continue
        mentions = resolver.resolve(text)
        if not mentions:
            continue
        created = getattr(t, "created_at", None)
        try:
            ts = datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y") if created else datetime.now(timezone.utc)
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)
        user = getattr(t, "user", None)
        author = getattr(user, "screen_name", None) if user else None
        sid = str(getattr(t, "id", ""))
        url = f"https://twitter.com/{author}/status/{sid}" if author and sid else ""
        s = sentiment.score(text)
        for m in mentions:
            rows.append({
                "timestamp": ts,
                "source": "twitter_twikit",
                "source_id": sid,
                "ticker": m.ticker,
                "alias": m.alias,
                "confidence": m.confidence,
                "via": m.via,
                "text": text[:4000],
                "sentiment": s.compound,
                "sentiment_label": s.label,
                "url": url,
                "author": author,
            })
    log.info("twikit: %d X mention rows for '%s'", len(rows), query)
    return normalized_dataframe(rows)
