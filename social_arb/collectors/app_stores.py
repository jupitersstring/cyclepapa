"""App store rank + review collectors (free, no key).

Google Play (`google-play-scraper`) returns 65+ fields per app
including install bands, ratings, paginated reviews. The spec's
recommended free path. Categorical install bands give a rough size
proxy. Review volume deltas are the actionable signal.

iOS app-store-scraper exposes ranking and reviews but install counts
aren't published.

Combined: track the apps belonging to retailer/consumer-product
tickers, surface review-volume spikes and rating shifts.

PIP DEPS: pip install google-play-scraper app-store-scraper
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from ..config import Config
from .base import normalized_dataframe

log = logging.getLogger(__name__)


def fetch_google_play_app(app_id: str) -> dict:
    """Fetch a single app's metadata from Google Play."""
    try:
        from google_play_scraper import app  # type: ignore
    except ImportError:
        log.warning("google-play-scraper not installed")
        return {}
    try:
        data = app(app_id, lang="en", country="us")
    except Exception as exc:  # noqa: BLE001
        log.debug("google-play app %s failed: %s", app_id, exc)
        return {}
    return data


def fetch_google_play_reviews(
    app_id: str, count: int = 100, lang: str = "en", country: str = "us"
) -> list[dict]:
    try:
        from google_play_scraper import reviews, Sort  # type: ignore
    except ImportError:
        return []
    try:
        result, _ = reviews(
            app_id, lang=lang, country=country, sort=Sort.NEWEST, count=int(count),
        )
        return result
    except Exception as exc:  # noqa: BLE001
        log.debug("google-play reviews %s failed: %s", app_id, exc)
        return []


def collect_app_signals(
    cfg: Config,
    app_to_ticker: dict[str, str],
    *,
    reviews_per_app: int = 100,
) -> pd.DataFrame:
    """Pull app metadata + recent reviews and emit mention rows.

    `app_to_ticker` is e.g. {"com.celsius.celsius": "CELH",
                             "com.temu.android": "PDD",
                             "com.shein.shein": "SHEIN_PRIVATE"}.
    """
    rows: list[dict] = []
    now = datetime.now(timezone.utc)
    for app_id, ticker in app_to_ticker.items():
        meta = fetch_google_play_app(app_id)
        if meta:
            text = (
                f"Google Play: {meta.get('title', app_id)} -- "
                f"installs={meta.get('installs', '?')} "
                f"score={meta.get('score', '?'):.2f} reviews={meta.get('reviews', 0)}"
            )
            rows.append({
                "timestamp": now,
                "source": "google_play_app",
                "source_id": f"play:{app_id}:{now.date().isoformat()}",
                "ticker": ticker.upper(),
                "alias": app_id,
                "confidence": 0.85,
                "via": "app_store_meta",
                "text": text,
                "sentiment": 0.0,
                "sentiment_label": "neutral",
                "url": f"https://play.google.com/store/apps/details?id={app_id}",
                "author": None,
            })
        # Recent reviews -- each review is a mention with VADER sentiment.
        revs = fetch_google_play_reviews(app_id, count=int(reviews_per_app))
        try:
            from ..sentiment import SentimentScorer
            scorer = SentimentScorer()
        except Exception:  # noqa: BLE001
            scorer = None
        for r in revs:
            text = (r.get("content") or "").strip()
            if not text or len(text) < 10:
                continue
            ts = r.get("at") or now
            if not isinstance(ts, datetime):
                ts = now
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            sentiment_val = 0.0
            label = "neutral"
            if scorer is not None:
                s = scorer.score(text)
                sentiment_val, label = s.compound, s.label
            # Star rating overlay: 5-star -> bump positive, 1-star -> bump negative.
            rating = int(r.get("score") or 3)
            sentiment_val = max(-1.0, min(1.0, sentiment_val + (rating - 3) * 0.15))
            rows.append({
                "timestamp": ts,
                "source": "google_play_review",
                "source_id": str(r.get("reviewId") or r.get("at")),
                "ticker": ticker.upper(),
                "alias": app_id,
                "confidence": 0.9,
                "via": "app_review",
                "text": text[:4000],
                "sentiment": sentiment_val,
                "sentiment_label": label,
                "url": f"https://play.google.com/store/apps/details?id={app_id}",
                "author": r.get("userName"),
            })
    return normalized_dataframe(rows)
