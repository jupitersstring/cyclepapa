"""Yahoo Finance Conversations scraper.

Yahoo retired the classic message boards in 2017 and replaced them with
"Conversations" (powered by Spot.IM / OpenWeb) on each stock quote page:

    https://finance.yahoo.com/quote/{TICKER}/community/

These are public, no auth required, and contain real-time retail
chatter on a per-ticker basis. The conversation feed loads via JS
calls to OpenWeb's API:

    https://api-2-0.spot.im/v1.0.0/conversation/read
        ?spot_id=sp_Rba9aFpG
        &post_id=finance-{TICKER}

The `spot_id` is constant for Yahoo Finance. We hit the public OpenWeb
endpoint directly so we don't need a browser.

Free, no key, modest rate limit (~1 req/sec polite).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from ..config import Config
from ..sentiment import SentimentScorer
from .base import normalized_dataframe

log = logging.getLogger(__name__)

OPENWEB_URL = "https://api-2-0.spot.im/v1.0.0/conversation/read"
YAHOO_SPOT_ID = "sp_Rba9aFpG"


def collect_yahoo_conversations(
    cfg: Config,
    sentiment: SentimentScorer,
    *,
    ticker: str,
    count: int = 50,
    timeout: float = 15.0,
) -> pd.DataFrame:
    """Pull the Yahoo Finance Conversations stream for one ticker."""
    params = {
        "spot_id": YAHOO_SPOT_ID,
        "post_id": f"finance-{ticker.upper()}",
        "count": min(int(count), 100),
        "depth": 2,
        "sort_by": "newest",
    }
    headers = {
        "User-Agent": cfg.user_agent,
        "Accept": "application/json",
        "Referer": f"https://finance.yahoo.com/quote/{ticker.upper()}/community/",
    }
    try:
        r = requests.get(OPENWEB_URL, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        log.debug("yahoo conversations failed for %s: %s", ticker, exc)
        return normalized_dataframe([])

    conv = data.get("conversation") or {}
    comments = conv.get("comments", []) or []
    rows: list[dict] = []
    for c in comments:
        # The OpenWeb response wraps each comment as a dict; the text is
        # under content[0].text typically, with timestamps in epoch.
        content_list = c.get("content") or []
        text_parts = []
        for block in content_list:
            t = (block.get("text") or "").strip()
            if t:
                text_parts.append(t)
        text = " ".join(text_parts).strip()
        if not text or len(text) < 10:
            continue
        ts_raw = c.get("written_at") or c.get("created_at")
        ts = (datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
              if ts_raw else datetime.now(timezone.utc))
        s = sentiment.score(text)
        sid = str(c.get("id") or c.get("conversation_id") or "")
        user = (c.get("user") or {}).get("display_name") or (c.get("user") or {}).get("user_name")
        rows.append({
            "timestamp": ts,
            "source": "yahoo_conversations",
            "source_id": f"yc:{ticker.upper()}:{sid}",
            "ticker": ticker.upper(),
            "alias": f"${ticker.lower()}",
            "confidence": 0.9,
            "via": "yahoo_conversations",
            "text": text[:4000],
            "sentiment": s.compound,
            "sentiment_label": s.label,
            "url": f"https://finance.yahoo.com/quote/{ticker.upper()}/community/",
            "author": user,
        })
    log.info("yahoo conversations %s: %d comments", ticker, len(rows))
    time.sleep(0.5)
    return normalized_dataframe(rows)
