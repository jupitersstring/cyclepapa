"""OpenInsider Form 4 cluster-buy scraper.

OpenInsider publishes free HTML tables of SEC Form 4 insider transactions
filtered by transaction type, period, and cluster signal. The cluster-buy
signal (multiple distinct insiders buying within ~30 days) is one of the
most replicated alpha signals in the public literature.

Endpoint patterns (no auth, no key):

    http://openinsider.com/screener?fd=30&t=...      <- standard screener
    http://openinsider.com/latest-cluster-buys       <- canonical landing
    http://openinsider.com/insider-purchases-25k     <- $25k+ purchases

We pull the cluster-buys landing as the default. Output rows feed
the `mentions` table tagged with source='openinsider' so they show
up in the social_signal_score breakdown alongside actual chatter.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import pandas as pd
import requests

from ..config import Config
from .base import normalized_dataframe

log = logging.getLogger(__name__)

OPENINSIDER_URL = "http://openinsider.com/latest-cluster-buys"


def collect_openinsider_cluster_buys(
    cfg: Config,
    *,
    url: str | None = None,
    timeout: float = 20.0,
) -> pd.DataFrame:
    """Scrape the OpenInsider 'cluster buys' table.

    Returns one mention row per (filing, ticker). The 'text' field is a
    one-line summary of the cluster buy; sentiment is set to +0.3 (mildly
    bullish, since cluster buying *is* a bullish signal but we leave room
    for the social-momentum stack to weight it).
    """
    target = url or OPENINSIDER_URL
    try:
        r = requests.get(target, headers={"User-Agent": cfg.user_agent}, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException as exc:
        log.warning("openinsider fetch failed: %s", exc)
        return normalized_dataframe([])

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("beautifulsoup4 not installed; openinsider disabled")
        return normalized_dataframe([])

    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table", class_=re.compile(r"tinytable|insider"))
    if table is None:
        log.warning("openinsider: no insider table on page")
        return normalized_dataframe([])

    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    # We rely on column positions rather than name (varies across pages):
    # Typical OpenInsider order: X | Filing Date | Trade Date | Ticker |
    # Company Name | Insider Name | Title | Trade Type | Price | Qty |
    # Owned | ΔOwn | Value
    rows: list[dict] = []
    now = datetime.now(timezone.utc)
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 7:
            continue
        try:
            filing_date = cells[1].get_text(strip=True)
            trade_date = cells[2].get_text(strip=True)
            ticker = cells[3].get_text(strip=True).upper()
            company = cells[4].get_text(strip=True)
            insider = cells[5].get_text(strip=True)
            title = cells[6].get_text(strip=True)
            trade_type = cells[7].get_text(strip=True) if len(cells) > 7 else ""
            value = cells[12].get_text(strip=True) if len(cells) > 12 else ""
        except Exception:  # noqa: BLE001
            continue
        if not ticker or len(ticker) > 6:
            continue
        try:
            ts = datetime.strptime(filing_date.split(" ")[0], "%Y-%m-%d")
            ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            ts = now
        text = (
            f"OpenInsider cluster buy: {insider} ({title}) bought {ticker} "
            f"on {trade_date}, value {value}."
        )
        sid = f"oi:{filing_date}:{ticker}:{insider[:30]}"
        rows.append({
            "timestamp": ts,
            "source": "openinsider",
            "source_id": sid,
            "ticker": ticker,
            "alias": ticker.lower(),
            "confidence": 0.95,
            "via": "form4_cluster",
            "text": text[:4000],
            "sentiment": 0.30,
            "sentiment_label": "bullish",
            "url": "http://openinsider.com/" + (target.split("/")[-1] or ""),
            "author": insider,
        })
    log.info("openinsider: %d cluster-buy rows scraped", len(rows))
    return normalized_dataframe(rows)
