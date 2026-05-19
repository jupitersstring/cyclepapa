"""YouTube comments collector via `youtube-comment-downloader`.

YouTube comments are public, no auth/key required. We use the
`youtube-comment-downloader` library (pip install youtube-comment-downloader)
which scrapes the public watch-page JSON-RPC endpoints. The official
Data API has a 10k-units/day quota; this scraper has no quota.

Two flows:

  1. **Per-video** -- `collect_video_comments(url_or_id)` pulls all
     comments from a known influencer review video.
  2. **Search-driven** -- `collect_search_videos(query)` uses yt-dlp to
     find the top-N videos matching a query (e.g. 'CELH review',
     'Stanley tumbler review'), then pulls comments from each.

The signal: when *consumers* are commenting "I just bought this" or
"this is everywhere" on product-review videos, that's Camillo's exact
field-research move at internet scale.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

import pandas as pd

from ..config import Config
from ..entity_resolution import Resolver
from ..sentiment import SentimentScorer
from .base import normalized_dataframe

log = logging.getLogger(__name__)


def _extract_video_id(url_or_id: str) -> str:
    """Accept either a raw 11-char video ID or a full URL."""
    s = url_or_id.strip()
    if len(s) == 11 and not s.startswith("http"):
        return s
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/|/v/)([A-Za-z0-9_-]{11})", s)
    return m.group(1) if m else s


def collect_video_comments(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    video: str,
    ticker_hint: str | None = None,
    sort_by: int = 0,  # 0 = popular, 1 = recent
    max_comments: int = 300,
) -> pd.DataFrame:
    """Pull comments from one YouTube video.

    If `ticker_hint` is given, every comment is treated as a mention of
    that ticker (useful when the video is a known review of a specific
    product), in addition to the entity resolver pass.
    """
    try:
        from youtube_comment_downloader import YoutubeCommentDownloader, SORT_BY_POPULAR
    except ImportError:
        log.warning("youtube-comment-downloader not installed; disabled")
        return normalized_dataframe([])

    vid = _extract_video_id(video)
    downloader = YoutubeCommentDownloader()
    try:
        generator = downloader.get_comments(vid, sort_by=sort_by)
    except Exception as exc:  # noqa: BLE001
        log.warning("youtube comments failed for %s: %s", vid, exc)
        return normalized_dataframe([])

    rows: list[dict] = []
    seen_ids: set[str] = set()
    count = 0
    for c in generator:
        if count >= int(max_comments):
            break
        count += 1
        text = (c.get("text") or "").strip()
        if not text or len(text) < 5:
            continue
        cid = str(c.get("cid") or c.get("id") or "")
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        # Parse relative time "2 weeks ago" -> rough timestamp.
        ts_raw = c.get("time_parsed") or c.get("time")
        if isinstance(ts_raw, (int, float)):
            ts = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)
        s = sentiment.score(text)
        mentions = resolver.resolve(text)
        # If a ticker_hint was provided, attribute every comment to it.
        if ticker_hint and not any(m.ticker == ticker_hint for m in mentions):
            tickers_to_emit = [(ticker_hint, ticker_hint.lower(), 0.7, "video_context")]
        else:
            tickers_to_emit = [(m.ticker, m.alias, m.confidence, m.via) for m in mentions]
        if not tickers_to_emit:
            continue
        url = f"https://youtube.com/watch?v={vid}&lc={cid}"
        for ticker, alias, conf, via in tickers_to_emit:
            rows.append({
                "timestamp": ts,
                "source": "youtube_comments",
                "source_id": f"{vid}:{cid}",
                "ticker": ticker,
                "alias": alias,
                "confidence": conf,
                "via": via,
                "text": text[:4000],
                "sentiment": s.compound,
                "sentiment_label": s.label,
                "url": url,
                "author": c.get("author"),
            })
    log.info("youtube comments %s: %d rows from %d comments", vid, len(rows), count)
    return normalized_dataframe(rows)


def collect_search_videos(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    query: str,
    ticker_hint: str | None = None,
    max_videos: int = 5,
    max_comments_per_video: int = 100,
) -> pd.DataFrame:
    """Search YouTube for `query`, pull comments from the top videos."""
    try:
        import yt_dlp
    except ImportError:
        log.warning("yt-dlp not installed; search-mode disabled")
        return normalized_dataframe([])

    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "skip_download": True,
        "playlistend": int(max_videos),
    }
    search_url = f"ytsearch{max_videos}:{query}"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_url, download=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("yt-dlp search failed for '%s': %s", query, exc)
        return normalized_dataframe([])

    videos = (info or {}).get("entries", []) or []
    all_rows: list[pd.DataFrame] = []
    for v in videos:
        vid = v.get("id") or v.get("url")
        if not vid:
            continue
        df = collect_video_comments(
            cfg, resolver, sentiment,
            video=vid, ticker_hint=ticker_hint,
            max_comments=max_comments_per_video,
        )
        if not df.empty:
            all_rows.append(df)
        time.sleep(0.3)
    if not all_rows:
        return normalized_dataframe([])
    return pd.concat(all_rows, ignore_index=True)
