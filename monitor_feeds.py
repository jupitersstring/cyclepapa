"""Tier-3 source monitor — daily-news aggregator for the UK CEF beat.

Pulls headlines from the four research houses the meta-search
identified as authoritative on UK closed-end funds:

  QuotedData       — daily morning briefings, free RSS
  Citywire ITI     — Investment Trust Insider, RSS via citywire.com
  AIC              — Association of Investment Companies news
  Kepler           — Kepler Trust Intelligence research notes

Matches each headline against the tickers and names in our universe
and writes the matches to data/feed_matches.csv with a daily timestamp.

Purpose: catch catalyst events between screen runs, especially
strategic reviews, continuation votes, manager changes, tender
announcements, wind-down decisions. The signal that fires here
should drive a catalyst_date / catalyst tag update.

Usage:
    python3 monitor_feeds.py        # daily run, append to feed_matches.csv
    python3 monitor_feeds.py --since 7   # 7-day catch-up
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import metadata

USER_AGENT = "Mozilla/5.0 (compatible; CyclepapaFeedMonitor/1.0)"
FEED_MATCHES_PATH = Path(os.path.dirname(os.path.abspath(__file__))) / "data" / "feed_matches.csv"


# Tier-3 feeds confirmed in the meta-search. Each entry is
# (name, url, kind) where kind is "rss" or "google_news_search".
FEEDS = [
    # QuotedData has a WordPress site — uses standard RSS at /feed/
    ("QuotedData", "https://quoteddata.com/feed/", "rss"),
    # Citywire's investment-trust-insider RSS
    ("Citywire ITI", "https://citywire.com/funds-insider/news/rss", "rss"),
    # interactive investor — Discount Delver / weekly trust analysis
    ("interactive investor", "https://www.ii.co.uk/analysis-commentary/feed", "rss"),
    # Google News fallback queries for AIC + Kepler (no public RSS)
    ("AIC news",  "https://news.google.com/rss/search?q=site%3Atheaic.co.uk&hl=en-GB", "rss"),
    ("Kepler", "https://news.google.com/rss/search?q=%22Kepler+Trust+Intelligence%22&hl=en-GB", "rss"),
    # Investment Week — covers wind-down / strategic review news
    ("Investment Week",
     "https://news.google.com/rss/search?q=site%3Ainvestmentweek.co.uk+%22investment+trust%22&hl=en-GB",
     "rss"),
]


# Keywords the matcher cares about — anything mentioning these in
# combination with a universe ticker name is worth surfacing.
KEYWORDS = re.compile(
    r"wind[- ]?down|managed realisation|tender offer|continuation vote|"
    r"strategic review|going self.?managed|reset.*roadmap|"
    r"open[- ]?end(?:ed)? (?:fund|conversion)|"
    r"return of capital|capital distribution|"
    r"PDMR shareholding|TR-?1|holding\(s\) in company|"
    r"transaction in own shares|share buyback|share repurchase|"
    r"appointment of broker|appoints adviser|"
    r"discount control|annual tender|"
    r"saba|activist",
    re.IGNORECASE,
)


def _fetch(url: str, timeout: int = 20) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _parse_rss(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = []
    for node in list(root.iter("item")) + list(
            root.iter("{http://www.w3.org/2005/Atom}entry")):
        title = (node.findtext("title")
                 or node.findtext("{http://www.w3.org/2005/Atom}title")
                 or "").strip()
        link_node = node.find("link")
        link = link_node.text.strip() if link_node is not None and link_node.text else ""
        if not link:
            atom_link = node.find("{http://www.w3.org/2005/Atom}link")
            if atom_link is not None:
                link = atom_link.attrib.get("href", "")
        pub = (node.findtext("pubDate")
               or node.findtext("{http://www.w3.org/2005/Atom}updated")
               or node.findtext("{http://www.w3.org/2005/Atom}published")
               or "").strip()
        items.append({"title": title, "link": link, "pub": pub})
    return items


def _within(pub_str: str, days: int) -> bool:
    if not pub_str:
        return True
    try:
        dt = parsedate_to_datetime(pub_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) <= timedelta(days=days)
    except Exception:
        return True


def _build_name_index() -> dict[str, str]:
    """Return name(lower) -> ticker map for matching. Skips empty
    names and short two-letter aliases that would over-match."""
    u = metadata.load_universe()
    out: dict[str, str] = {}
    for tk, row in u.items():
        if row.name and len(row.name) >= 6:
            out[row.name.lower()] = tk
        # Also add EPIC alone in `LSE: XYZ` style strings
        if tk.endswith(".L"):
            epic = tk[:-2]
            out[f"({epic})"] = tk
            out[f"{epic}.L"] = tk
    return out


def scan(days: int = 1) -> list[dict]:
    name_idx = _build_name_index()
    matches: list[dict] = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for source, url, kind in FEEDS:
        xml = _fetch(url)
        if not xml:
            continue
        items = _parse_rss(xml)
        for it in items:
            title = it["title"]
            if not title:
                continue
            if not _within(it["pub"], days):
                continue
            tl = title.lower()
            # Match a universe name/ticker AND a keyword of interest
            matched_ticker = None
            for needle, ticker in name_idx.items():
                if needle in tl:
                    matched_ticker = ticker
                    break
            if not matched_ticker:
                continue
            if not KEYWORDS.search(title):
                continue
            matches.append({
                "scan_date": today,
                "source": source,
                "ticker": matched_ticker,
                "title": title[:200],
                "link": it["link"],
                "pub": it["pub"],
            })
    return matches


def append_matches(matches: list[dict]) -> int:
    """Append (deduped on title+ticker) to data/feed_matches.csv."""
    FEED_MATCHES_PATH.parent.mkdir(parents=True, exist_ok=True)
    fresh = not FEED_MATCHES_PATH.exists()
    existing_keys: set[tuple[str, str]] = set()
    if not fresh:
        with open(FEED_MATCHES_PATH) as f:
            for row in csv.DictReader(f):
                existing_keys.add((row["ticker"], row["title"]))
    written = 0
    with open(FEED_MATCHES_PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["scan_date", "source", "ticker",
                                          "title", "link", "pub"])
        if fresh:
            w.writeheader()
        for m in matches:
            key = (m["ticker"], m["title"])
            if key in existing_keys:
                continue
            existing_keys.add(key)
            w.writerow(m)
            written += 1
    return written


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--since", type=int, default=2,
                   help="Look back N days (default 2)")
    args = p.parse_args()
    ms = scan(days=args.since)
    print(f"[feeds] {len(ms)} headlines matched universe tickers within "
          f"the last {args.since} day(s)", file=sys.stderr)
    n = append_matches(ms)
    print(f"[feeds] {n} new (deduped). Total file: {FEED_MATCHES_PATH}",
          file=sys.stderr)
    for m in ms[:25]:
        print(f"  {m['ticker']:<8}  [{m['source']:<14}]  {m['title'][:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
