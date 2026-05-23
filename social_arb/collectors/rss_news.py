"""RSS news + body extraction via trafilatura.

The spec's recommended free path: feedparser-style RSS pulls give
unlimited headlines; trafilatura then extracts clean article body
for sentiment/NER. Covers Yahoo Finance per-ticker RSS, SeekingAlpha
search RSS, SEC EDGAR RSS, MarketWatch, IR pages.

Free, no key, no auth. Trafilatura is more robust than newspaper3k
or BeautifulSoup for body extraction.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import requests
import xml.etree.ElementTree as ET

from ..config import Config
from ..entity_resolution import Resolver
from ..sentiment import SentimentScorer
from .base import normalized_dataframe

log = logging.getLogger(__name__)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; social-arb/0.1)",
    "Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, */*;q=0.8",
}


def fetch_rss(url: str, timeout: float = 15.0) -> list[dict]:
    """Generic RSS / Atom parser using stdlib XML."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError) as exc:
        log.debug("rss %s failed: %s", url, exc)
        return []
    items: list[dict] = []
    # RSS 2.0
    for it in root.findall(".//item"):
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "description": (it.findtext("description") or "").strip(),
            "pub_date": (it.findtext("pubDate") or "").strip(),
        })
    # Atom
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for it in root.findall("atom:entry", ns):
        link_el = it.find("atom:link", ns)
        items.append({
            "title": (it.findtext("atom:title", default="", namespaces=ns) or "").strip(),
            "link": link_el.get("href") if link_el is not None else "",
            "description": (it.findtext("atom:summary", default="", namespaces=ns) or "").strip(),
            "pub_date": (it.findtext("atom:updated", default="", namespaces=ns) or "").strip(),
        })
    return items


def extract_body(url: str, timeout: float = 20.0) -> str:
    """Fetch a URL and extract clean article body via trafilatura."""
    try:
        import trafilatura  # type: ignore
    except ImportError:
        return ""
    try:
        downloaded = trafilatura.fetch_url(url, no_ssl=False)
        if not downloaded:
            return ""
        return trafilatura.extract(downloaded) or ""
    except Exception as exc:  # noqa: BLE001
        log.debug("trafilatura extract failed for %s: %s", url, exc)
        return ""


YAHOO_TICKER_RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
SA_TICKER_RSS = "https://seekingalpha.com/api/sa/combined/{ticker}.xml"


def collect_rss_for_ticker(
    cfg: Config,
    sentiment: SentimentScorer,
    *,
    ticker: str,
    fetch_bodies: bool = False,
) -> pd.DataFrame:
    """Pull Yahoo + SeekingAlpha RSS for one ticker and emit mentions."""
    sources = [
        ("yahoo_rss", YAHOO_TICKER_RSS.format(ticker=ticker.upper())),
        ("seekingalpha_rss", SA_TICKER_RSS.format(ticker=ticker.upper())),
    ]
    rows = []
    for src_name, url in sources:
        items = fetch_rss(url)
        for it in items:
            text = (it["title"] + " " + it["description"]).strip()
            if not text:
                continue
            if fetch_bodies and it["link"]:
                body = extract_body(it["link"])
                if body:
                    text = (text + " " + body)[:4000]
            ts_raw = it["pub_date"]
            ts = datetime.now(timezone.utc)
            for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%SZ"):
                try:
                    ts = datetime.strptime(ts_raw, fmt)
                    break
                except (ValueError, TypeError):
                    continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            s = sentiment.score(text)
            sid = f"{src_name}:{it['link'] or it['title'][:80]}"
            rows.append({
                "timestamp": ts,
                "source": src_name,
                "source_id": sid,
                "ticker": ticker.upper(),
                "alias": ticker.lower(),
                "confidence": 0.9,
                "via": "rss_feed",
                "text": text[:4000],
                "sentiment": s.compound,
                "sentiment_label": s.label,
                "url": it["link"],
                "author": None,
            })
    return normalized_dataframe(rows)
