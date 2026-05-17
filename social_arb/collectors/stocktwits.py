"""Stocktwits collector (unauthenticated public stream).

Stocktwits exposes per-symbol message streams without auth:

    https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json

Rate limit is roughly 200 requests/hour from a single IP. Returns ~30
messages per call with user-tagged bullish/bearish sentiment when authors
opted in. We trust their tagging where present and fall back to our own
scorer otherwise.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from ..config import Config
from ..sentiment import SentimentScorer
from .base import http_get_json, normalized_dataframe

log = logging.getLogger(__name__)


def collect_stocktwits(
    cfg: Config,
    sentiment: SentimentScorer,
    *,
    ticker: str,
) -> pd.DataFrame:
    url = f"{cfg.stocktwits_base}/streams/symbol/{ticker.upper()}.json"
    try:
        payload = http_get_json(url, cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning("stocktwits fetch failed for %s: %s", ticker, exc)
        return normalized_dataframe([])
    rows: list[dict] = []
    for msg in payload.get("messages", []):
        body = (msg.get("body") or "").strip()
        if not body:
            continue
        created = msg.get("created_at")
        try:
            ts = datetime.fromisoformat(created.replace("Z", "+00:00")) if created else datetime.now(timezone.utc)
        except (ValueError, AttributeError):
            ts = datetime.now(timezone.utc)
        # User-tagged sentiment if present.
        st_sent = (msg.get("entities") or {}).get("sentiment") or {}
        basic = (st_sent.get("basic") or "").lower() if isinstance(st_sent, dict) else ""
        if basic == "bullish":
            comp, label = 0.6, "bullish"
        elif basic == "bearish":
            comp, label = -0.6, "bearish"
        else:
            s = sentiment.score(body)
            comp, label = s.compound, s.label
        user = (msg.get("user") or {}).get("username")
        rows.append({
            "timestamp": ts,
            "source": "stocktwits",
            "source_id": str(msg.get("id")),
            "ticker": ticker.upper(),
            "alias": f"${ticker.lower()}",
            "confidence": 0.95,
            "via": "stocktwits_symbol_stream",
            "text": body[:4000],
            "sentiment": comp,
            "sentiment_label": label,
            "url": f"https://stocktwits.com/message/{msg.get('id')}",
            "author": user,
        })
    return normalized_dataframe(rows)
