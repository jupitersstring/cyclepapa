"""Brave Search API as a search-trend backstop.

Brave's free tier is 2,000 web-search queries per month, requires a free
API key from `https://api.search.brave.com/app/keys` set via the
BRAVE_SEARCH_API_KEY environment variable.

Used here as a *search-volume backstop* when Google Trends rate-limits:
for each ticker we issue a tightly-scoped query like
`"$CELH" stock OR earnings` and read the **estimated total results**
count. A rising count over time is a search-attention proxy.

Endpoint:
    https://api.search.brave.com/res/v1/web/search?q=...

Headers:
    X-Subscription-Token: <key>
    Accept: application/json
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import pandas as pd
import requests

from ..config import Config
from .base import normalized_dataframe

log = logging.getLogger(__name__)

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


def fetch_brave_result_count(
    query: str,
    *,
    api_key: str | None = None,
    timeout: float = 12.0,
) -> int | None:
    """Return estimated total results for `query`, or None on failure."""
    key = api_key or os.environ.get("BRAVE_SEARCH_API_KEY")
    if not key:
        log.debug("BRAVE_SEARCH_API_KEY not set")
        return None
    try:
        r = requests.get(
            BRAVE_URL,
            params={"q": query, "count": 1, "result_filter": "web"},
            headers={
                "X-Subscription-Token": key,
                "Accept": "application/json",
                "User-Agent": "social-arb/0.1",
            },
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as exc:
        log.warning("brave search failed for '%s': %s", query, exc)
        return None
    web = data.get("web") or {}
    # Brave returns either a results array or an "estimated_total_results" hint.
    if "estimated_total_results" in web:
        try:
            return int(web["estimated_total_results"])
        except (TypeError, ValueError):
            return None
    # Otherwise fall back to len(results) as a weak signal.
    results = web.get("results") or []
    return len(results) if results else None


def collect_brave_search_attention(
    cfg: Config,
    *,
    ticker: str,
    extra_terms: str = "stock OR earnings",
) -> pd.DataFrame:
    """One-shot search-attention snapshot for a ticker as a mention row.

    Designed to be called daily so the trend builds in our store over
    time; each call emits one mention row with `mentions` equal to
    log(estimated_total_results+1) so big numbers don't blow up the
    z-score.
    """
    q = f"\"${ticker.upper()}\" {extra_terms}"
    n = fetch_brave_result_count(q)
    if n is None or n <= 0:
        return normalized_dataframe([])
    import math
    # Phase 2: ONE weighted row carrying log1p(n) as weight.
    now = datetime.now(timezone.utc)
    rows = [{
        "timestamp": now,
        "source": "brave_search",
        "source_id": f"brave:{ticker.upper()}:{now.date().isoformat()}",
        "ticker": ticker.upper(),
        "alias": f"${ticker.lower()}",
        "confidence": 0.75,
        "via": "search_volume",
        "text": f"brave_search results={n} for query='{q}'",
        "sentiment": 0.0,
        "sentiment_label": "neutral",
        "url": "https://search.brave.com/search?q=" + q.replace(" ", "+"),
        "author": None,
        "weight": float(math.log1p(n)),
    }]
    return normalized_dataframe(rows)
