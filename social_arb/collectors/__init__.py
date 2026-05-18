"""Data collectors. Each collector returns a normalized DataFrame with the
columns expected by `social_arb.storage.upsert_mentions`."""

from .base import CollectorError, http_get_json, normalized_dataframe
from .apewisdom import collect_apewisdom
from .bluesky import collect_bluesky
from .fourchan import collect_fourchan_biz
from .gdelt import collect_gdelt
from .hackernews import collect_hackernews
from .openinsider import collect_openinsider_cluster_buys
from .pullpush import collect_pullpush
from .reddit_chat import collect_reddit_chat
from .reddit_rss import collect_reddit_rss
from .sec_edgar import collect_form4
from .stocktwits import collect_stocktwits
from .wikipedia import collect_wikipedia
from .yahoo_conversations import collect_yahoo_conversations
from .yfinance_news import collect_yfinance_news

__all__ = [
    "CollectorError", "http_get_json", "normalized_dataframe",
    "collect_apewisdom", "collect_bluesky", "collect_form4",
    "collect_fourchan_biz", "collect_gdelt", "collect_hackernews",
    "collect_openinsider_cluster_buys", "collect_pullpush",
    "collect_reddit_chat", "collect_reddit_rss", "collect_stocktwits",
    "collect_wikipedia", "collect_yahoo_conversations", "collect_yfinance_news",
]
