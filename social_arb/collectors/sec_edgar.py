"""SEC EDGAR Form 4 insider-buy collector.

SEC EDGAR is free, no key, just needs a User-Agent identifying the
requester (per SEC policy). We query the recent Form 4 filings index and
attribute insider open-market buys to tickers as a bullish signal.

Form 4 cluster buys (multiple insiders buying within ~30 days) are one of
the most replicated alpha signals in the public literature; OpenInsider
makes a business of exposing them.

Endpoint used (full-text search across recent filings):

    https://efts.sec.gov/LATEST/search-index?q=&dateRange=custom&forms=4

A lightweight approach that doesn't require parsing every Form 4 XML.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from ..config import Config
from .base import http_get_json, normalized_dataframe

log = logging.getLogger(__name__)

EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"


def collect_form4(
    cfg: Config,
    *,
    days_back: int = 7,
    max_records: int = 100,
) -> pd.DataFrame:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=int(days_back))
    params = {
        "q": "",
        "dateRange": "custom",
        "startdt": start.isoformat(),
        "enddt": end.isoformat(),
        "forms": "4",
    }
    # SEC blocks generic UAs; require an "Org Contact email" format per
    # https://www.sec.gov/os/accessing-edgar-data
    ua = cfg.user_agent
    if "@" not in ua:
        ua = "social-arb research social-arb@example.com"
    headers = {
        "User-Agent": ua,
        "Accept": "application/json",
        "Host": "efts.sec.gov",
    }
    try:
        payload = http_get_json(EDGAR_SEARCH, cfg, params=params, extra_headers=headers)
    except Exception as exc:  # noqa: BLE001
        log.warning("edgar form 4 fetch failed: %s", exc)
        return normalized_dataframe([])
    hits = (payload.get("hits") or {}).get("hits", [])
    rows: list[dict] = []
    for h in hits[: int(max_records)]:
        src = h.get("_source") or {}
        tickers = src.get("tickers") or []
        filed = src.get("file_date") or src.get("filed_date") or src.get("@timestamp")
        try:
            ts = datetime.fromisoformat(str(filed)) if filed else datetime.now(timezone.utc)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            ts = datetime.now(timezone.utc)
        sid = h.get("_id") or src.get("adsh") or ""
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&action=getcompany&CIK={src.get('ciks', [''])[0] if src.get('ciks') else ''}&type=4"
        for t in tickers:
            rows.append({
                "timestamp": ts,
                "source": "sec_form4",
                "source_id": f"{sid}:{t}",
                "ticker": str(t).upper(),
                "alias": str(t).lower(),
                "confidence": 0.95,
                "via": "form4_filing",
                "text": f"Form 4 filing for {t} on {ts.date().isoformat()}",
                # Form 4 filings without P-code transaction parsing are
                # attention only; flag as mildly bullish to weight slightly
                # toward insider activity, but rely on volume not polarity.
                "sentiment": 0.1,
                "sentiment_label": "neutral",
                "url": url,
                "author": ",".join(src.get("display_names") or [])[:200],
            })
    log.info("edgar form 4: %d ticker-rows from %d filings", len(rows), len(hits))
    return normalized_dataframe(rows)
