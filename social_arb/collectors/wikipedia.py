"""Wikipedia pageviews collector.

Wikipedia's REST API exposes daily pageviews per article with zero auth:

    https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/
        en.wikipedia/all-access/all-agents/{title}/daily/{start}/{end}

Pageview spikes were one of the cleanest attention signals studied in the
academic literature (a close cousin of Da/Engelberg/Gao's abnormal SVI).
Useful when Google Trends quotas bite. We persist one synthetic "mention"
row per pageview unit so the existing anomaly machinery works unchanged.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from ..config import Config
from .base import http_get_json, normalized_dataframe

log = logging.getLogger(__name__)

WIKI_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"


def fetch_pageviews(
    cfg: Config,
    *,
    title: str,
    days_back: int = 60,
    project: str = "en.wikipedia",
) -> pd.DataFrame:
    """Return DataFrame [date, views] for one article."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=int(days_back))
    safe_title = title.replace(" ", "_")
    url = (
        f"{WIKI_BASE}/{project}/all-access/all-agents/{safe_title}/daily/"
        f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    )
    try:
        payload = http_get_json(url, cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning("wikipedia pageviews failed for %s: %s", title, exc)
        return pd.DataFrame(columns=["date", "views"])
    rows = []
    for item in payload.get("items", []):
        ts = item.get("timestamp", "")
        try:
            d = datetime.strptime(ts[:8], "%Y%m%d").date()
        except ValueError:
            continue
        rows.append({"date": d, "views": int(item.get("views", 0))})
    return pd.DataFrame(rows)


def collect_wikipedia(
    cfg: Config,
    *,
    title: str,
    ticker: str,
    days_back: int = 60,
) -> pd.DataFrame:
    """Map a Wikipedia title to a ticker and emit mention rows."""
    pv = fetch_pageviews(cfg, title=title, days_back=days_back)
    if pv.empty:
        return normalized_dataframe([])
    rows: list[dict] = []
    for r in pv.itertuples(index=False):
        # One synthetic row per article-day, with views encoded in the text.
        # Sentiment is neutral (0.0) -- Wikipedia is an attention signal,
        # not a sentiment signal.
        ts = datetime.combine(r.date, datetime.min.time(), tzinfo=timezone.utc)
        sid = f"wiki:{title}:{r.date.isoformat()}"
        rows.append({
            "timestamp": ts,
            "source": "wikipedia",
            "source_id": sid,
            "ticker": ticker.upper(),
            "alias": title.lower(),
            "confidence": 0.95,
            "via": "wikipedia_pageviews",
            "text": f"wikipedia {title} views={r.views}",
            # Encode views magnitude as a weight on a synthetic mention count
            # via repetition: but to avoid blowing the row count, we just
            # store views in the sentiment-mean slot? No -- cleaner: keep a
            # single row and let the dashboard handle the views column.
            "sentiment": 0.0,
            "sentiment_label": "neutral",
            "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
            "author": None,
        })
        # Repeat the row `min(views // 100, 50)` times so the count-based
        # anomaly detector sees scale (each row = ~100 daily views).
        scale = min(int(r.views) // 100, 50)
        for i in range(scale):
            rows.append({**rows[-1], "source_id": f"{sid}:{i}"})
    return normalized_dataframe(rows)
