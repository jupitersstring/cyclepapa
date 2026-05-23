"""Data collectors. Each collector returns a normalized DataFrame with the
columns expected by `social_arb.storage.upsert_mentions`."""

from .base import CollectorError, http_get_json, normalized_dataframe
from .apewisdom import collect_apewisdom
from .app_stores import collect_app_signals
from .bluesky import collect_bluesky
from .brave_search import collect_brave_search_attention
from .capitol_trades import collect_capitol_trades
from .fourchan import collect_fourchan_biz
from .gdelt import collect_gdelt
from .google_trends import collect_google_trends
from .hackernews import collect_hackernews
from .job_postings import collect_job_postings
from .mastodon import collect_mastodon
from .nitter import collect_nitter
from .openinsider import collect_openinsider_cluster_buys
from .pullpush import collect_pullpush
from .reddit_chat import collect_reddit_chat
from .reddit_rss import collect_reddit_rss
from .rss_news import collect_rss_for_ticker
from .sec_edgar import collect_form4
from .stocktwits import collect_stocktwits
from .telegram import collect_telegram
from .tiktok_creative import collect_tiktok_hashtags_as_mentions, hashtag_velocity_delta
from .twitter_twikit import collect_twitter
from .uspto import collect_patents
from .wikipedia import collect_wikipedia
from .yahoo_conversations import collect_yahoo_conversations
from .yfinance_news import collect_yfinance_news
from .youtube_comments import collect_search_videos, collect_video_comments

__all__ = [
    "CollectorError", "http_get_json", "normalized_dataframe",
    "collect_apewisdom", "collect_app_signals", "collect_bluesky",
    "collect_brave_search_attention", "collect_capitol_trades",
    "collect_form4", "collect_fourchan_biz", "collect_gdelt",
    "collect_google_trends", "collect_hackernews", "collect_job_postings",
    "collect_mastodon", "collect_nitter", "collect_openinsider_cluster_buys",
    "collect_patents", "collect_pullpush", "collect_reddit_chat",
    "collect_reddit_rss", "collect_rss_for_ticker", "collect_stocktwits",
    "collect_telegram", "collect_tiktok_hashtags_as_mentions",
    "collect_twitter", "collect_wikipedia", "collect_yahoo_conversations",
    "collect_yfinance_news", "collect_search_videos", "collect_video_comments",
    "hashtag_velocity_delta",
]
