"""USPTO PatentsView + TSDR (trademarks) -- free, no key.

Patents and trademarks are leading-indicators of corporate intent
that fund managers often overlook:

  * **PatentsView** API at https://search.patentsview.org/api/v1/patent
    Free, no key, granted patents queryable by assignee, year, CPC.
  * **USPTO TSDR** at https://tsdr.uspto.gov/  (HTML scrape; not JSON)
    Spec note: trademark filings are a leading indicator of retailer
    private-label launches.

PatentsView signal use case: a sudden spike in patents granted to a
small-cap with concentrated IP (e.g., a single-drug biotech, a
specific-tech industrial) is a leading earnings/IP-licensing signal.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from ..config import Config
from .base import normalized_dataframe

log = logging.getLogger(__name__)


PV_URL = "https://search.patentsview.org/api/v1/patent"
HEADERS = {"User-Agent": "social-arb/0.1", "Accept": "application/json"}


def fetch_patents_for_assignee(
    assignee_name: str,
    *,
    months_back: int = 12,
    limit: int = 100,
) -> list[dict]:
    """Query PatentsView for recent granted patents to one assignee."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=int(months_back) * 30)
    body = {
        "q": {
            "_and": [
                {"assignees.assignee_organization": assignee_name},
                {"_gte": {"patent_date": start.isoformat()}},
            ]
        },
        "f": [
            "patent_id", "patent_title", "patent_date", "patent_abstract",
            "assignees.assignee_organization",
        ],
        "o": {"size": int(limit), "sort": [{"patent_date": "desc"}]},
    }
    try:
        r = requests.post(PV_URL, json=body, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return (r.json() or {}).get("patents", []) or []
    except (requests.RequestException, ValueError) as exc:
        log.debug("patentsview %s failed: %s", assignee_name, exc)
        return []


def collect_patents(
    cfg: Config,
    assignee_to_ticker: dict[str, str],
    *,
    months_back: int = 12,
) -> pd.DataFrame:
    """Pull recent patents per assignee, emit mention rows."""
    rows: list[dict] = []
    for assignee, ticker in assignee_to_ticker.items():
        patents = fetch_patents_for_assignee(assignee, months_back=months_back)
        for p in patents:
            date_s = p.get("patent_date") or ""
            try:
                ts = datetime.strptime(date_s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                ts = datetime.now(timezone.utc)
            title = (p.get("patent_title") or "")[:200]
            text = f"USPTO patent {p.get('patent_id', '?')}: {title}"
            rows.append({
                "timestamp": ts,
                "source": "uspto_patents",
                "source_id": f"patent:{p.get('patent_id', '')}",
                "ticker": ticker.upper(),
                "alias": assignee.lower(),
                "confidence": 0.9,
                "via": "patent_grant",
                "text": text[:4000],
                "sentiment": 0.15,
                "sentiment_label": "bullish",
                "url": f"https://patents.google.com/patent/US{p.get('patent_id', '')}",
                "author": assignee,
            })
    log.info("uspto patents: %d rows", len(rows))
    return normalized_dataframe(rows)
