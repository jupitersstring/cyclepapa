"""GDELT DOC 2.0 collector.

GDELT is free, no auth, refreshed every ~15 minutes, multilingual. Useful
endpoints:

    /api/v2/doc/doc?query=...&mode=artlist&format=json
    /api/v2/doc/doc?query=...&mode=timelinevol&format=json    (volume curve)
    /api/v2/doc/doc?query=...&mode=tonechart&format=json      (sentiment)

We support `artlist` (article rows) and `timelinevol` (daily mention volume).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from ..config import Config
from ..entity_resolution import Resolver
from ..sentiment import SentimentScorer
from .base import http_get_json, normalized_dataframe

log = logging.getLogger(__name__)


def _format_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y%m%d%H%M%S")


def collect_gdelt(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    query: str,
    hours_back: int = 24,
    max_records: int = 250,
) -> pd.DataFrame:
    """Pull article rows from GDELT DOC, resolve entities, score sentiment."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours_back)
    params: dict[str, Any] = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": min(int(max_records), 250),
        "startdatetime": _format_dt(start),
        "enddatetime": _format_dt(end),
        "sort": "datedesc",
    }
    try:
        payload = http_get_json(cfg.gdelt_doc_base, cfg, params=params)
    except Exception as exc:  # noqa: BLE001
        log.warning("gdelt fetch failed: %s", exc)
        return normalized_dataframe([])
    rows: list[dict] = []
    for art in payload.get("articles", []):
        title = art.get("title") or ""
        snippet = art.get("seendate") or ""
        text = title
        if not text:
            continue
        mentions = resolver.resolve(text)
        if not mentions:
            continue
        # Parse GDELT's compact timestamp like '20240517T123000Z'
        ts_raw = art.get("seendate") or art.get("date") or ""
        ts = None
        if ts_raw:
            try:
                ts = datetime.strptime(ts_raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                ts = None
        s = sentiment.score(text)
        url = art.get("url") or ""
        sid = art.get("url") or art.get("docid") or title[:80]
        for m in mentions:
            rows.append({
                "timestamp": ts or end,
                "source": "gdelt",
                "source_id": sid,
                "ticker": m.ticker,
                "alias": m.alias,
                "confidence": m.confidence,
                "via": m.via,
                "text": text[:4000],
                "sentiment": s.compound,
                "sentiment_label": s.label,
                "url": url,
                "author": art.get("domain"),
            })
    log.info("gdelt: %d mention rows from %d articles", len(rows), len(payload.get("articles", [])))
    return normalized_dataframe(rows)


def timeline_volume(cfg: Config, query: str, days_back: int = 90) -> pd.DataFrame:
    """Daily article-volume timeline (GDELT's `timelinevol` mode).

    Returns columns: date, value (percent of all articles indexed for that day).
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(days_back))
    params = {
        "query": query,
        "mode": "timelinevol",
        "format": "json",
        "startdatetime": _format_dt(start),
        "enddatetime": _format_dt(end),
    }
    try:
        payload = http_get_json(cfg.gdelt_doc_base, cfg, params=params)
    except Exception as exc:  # noqa: BLE001
        log.warning("gdelt timeline failed: %s", exc)
        return pd.DataFrame(columns=["date", "value"])
    series = (payload.get("timeline") or [{}])[0].get("data", [])
    if not series:
        return pd.DataFrame(columns=["date", "value"])
    df = pd.DataFrame(series)
    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna()
