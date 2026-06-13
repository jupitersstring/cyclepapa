"""TikTok Creative Center scraper -- free, no login, no auth.

TikTok publishes a public business-facing dashboard at:
    https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/

Top hashtags ranked by 7/30/120-day post velocity, top products on
TikTok Shop, trending songs, keyword insights. No API, but their
internal JSON endpoint (`/web/api/v1/inspiration/center/...`) returns
JSON when called with a browser-like User-Agent.

Spec calls this the underrated free tool. We surface hashtag-velocity
deltas as a leading indicator -- a hashtag jumping 7d-vs-30d velocity
often precedes the same product/brand appearing in news/Reddit by
weeks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import requests

from ..config import Config
from .base import normalized_dataframe

log = logging.getLogger(__name__)

TT_HASHTAG_URL = (
    "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list"
)
TT_PRODUCT_URL = (
    "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/product/list"
)
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://ads.tiktok.com/business/creativecenter/",
}


def fetch_top_hashtags(
    cfg: Config,
    *,
    period: int = 30,
    country_code: str = "US",
    limit: int = 100,
) -> pd.DataFrame:
    """Top hashtags by `period`-day post velocity.

    period in {7, 30, 120}.
    """
    params = {
        "period": int(period),
        "country_code": country_code,
        "limit": int(limit),
        "page": 1,
        "sort_by": "popular",
    }
    try:
        r = requests.get(TT_HASHTAG_URL, params=params, headers=BROWSER_HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("tiktok creative center failed: %s", exc)
        return pd.DataFrame()
    hashtags = (data.get("data") or {}).get("list", [])
    if not hashtags:
        return pd.DataFrame()
    rows = []
    for h in hashtags:
        rows.append({
            "hashtag": h.get("hashtag_name") or h.get("name"),
            "publish_cnt": int(h.get("publish_cnt", 0) or 0),
            "video_views": int(h.get("video_views", 0) or 0),
            "rank": h.get("rank"),
            "rank_diff": h.get("rank_diff"),
            "trend": (h.get("trend") or {}).get("trend_type"),
        })
    out = pd.DataFrame(rows)
    out["period_days"] = period
    out["captured_at"] = datetime.now(timezone.utc)
    return out


def hashtag_velocity_delta(cfg: Config, country_code: str = "US") -> pd.DataFrame:
    """7d vs 30d hashtag velocity delta -- accelerating hashtags.

    A hashtag jumping in 7d velocity vs its 30d baseline is the earliest
    detectable consumer-product trend signal on TikTok.
    """
    d7 = fetch_top_hashtags(cfg, period=7, country_code=country_code, limit=100)
    d30 = fetch_top_hashtags(cfg, period=30, country_code=country_code, limit=100)
    if d7.empty or d30.empty:
        return pd.DataFrame()
    merged = d7.merge(d30, on="hashtag", suffixes=("_7d", "_30d"), how="outer").fillna({
        "publish_cnt_7d": 0, "publish_cnt_30d": 0,
        "video_views_7d": 0, "video_views_30d": 0,
    })
    # Per-day rates and acceleration.
    merged["per_day_7d"] = merged["publish_cnt_7d"] / 7.0
    merged["per_day_30d"] = merged["publish_cnt_30d"] / 30.0
    merged["velocity_ratio"] = merged["per_day_7d"] / merged["per_day_30d"].replace(0, 1.0)
    return merged.sort_values("velocity_ratio", ascending=False).head(50).reset_index(drop=True)


def collect_tiktok_hashtags_as_mentions(
    cfg: Config,
    hashtag_to_ticker: dict[str, str],
    *,
    country_code: str = "US",
) -> pd.DataFrame:
    """Map curated hashtag -> ticker dict to mention rows.

    Spec note: hashtag-to-ticker mapping is a hand-curated dictionary
    (e.g., {"#celsius": "CELH", "#stanleycup": "ELUX-B.ST"}). When a
    target hashtag appears in the top-N, its publish_cnt becomes the
    attention metric for the ticker.
    """
    df = fetch_top_hashtags(cfg, period=30, country_code=country_code, limit=200)
    if df.empty or not hashtag_to_ticker:
        return normalized_dataframe([])
    df_low = df.copy()
    df_low["hashtag_norm"] = df_low["hashtag"].astype(str).str.lower().str.lstrip("#")
    rows = []
    now = datetime.now(timezone.utc)
    for tag, ticker in hashtag_to_ticker.items():
        norm = tag.lower().lstrip("#")
        match = df_low[df_low["hashtag_norm"] == norm]
        if match.empty:
            continue
        m = match.iloc[0]
        publish_cnt = int(m["publish_cnt"])
        if publish_cnt <= 0:
            continue
        # Phase 2: ONE weighted row per hashtag observation.
        import math
        text = (
            f"TikTok Creative Center 30d hashtag '{tag}' "
            f"publish_cnt={publish_cnt} views={int(m['video_views'])}"
        )
        rows.append({
            "timestamp": now,
            "source": "tiktok_creative_center",
            "source_id": f"tiktok:{tag}:{now.date().isoformat()}",
            "ticker": ticker.upper(),
            "alias": norm,
            "confidence": 0.8,
            "via": "tiktok_hashtag",
            "text": text,
            "sentiment": 0.0,
            "sentiment_label": "neutral",
            "url": f"https://www.tiktok.com/tag/{norm}",
            "author": None,
            "weight": float(math.log1p(publish_cnt) * 2.0),
        })
    return normalized_dataframe(rows)
