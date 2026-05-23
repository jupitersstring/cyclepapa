"""Congressional trading via CapitolTrades + Senate Stock Watcher.

CapitolTrades.com publishes a clean public dashboard of all Senate
and House STOCK-Act filings, with a JSON-accessible endpoint at:

    https://bff.capitoltrades.com/trades

No auth, no key. Returns recent trades with politician, asset_traded,
side (B = buy / S = sell), publication_date, transaction_date,
disclosure_lag_days.

Spec note: a single politician's buy is noise; clusters and especially
*pre-earnings* buys are real signal. We emit one mention row per
filing tagged source='capitol_trades' so the per-source breakdown in
`health` distinguishes it from other layers.

Senate Stock Watcher is a sibling free site; the Senate-only JSON is at
    https://senatestockwatcher.com/api/v1/all_transactions
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import requests

from ..config import Config
from .base import normalized_dataframe

log = logging.getLogger(__name__)


CT_URL = "https://bff.capitoltrades.com/trades"
HEADERS = {"User-Agent": "social-arb/0.1", "Accept": "application/json"}


def fetch_capitol_trades(days_back: int = 30, page_size: int = 96) -> list[dict]:
    """Pull recent trades from CapitolTrades' BFF."""
    params = {
        "sortBy": "-pubDate",
        "pageSize": int(page_size),
    }
    try:
        r = requests.get(CT_URL, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("capitol_trades failed: %s", exc)
        return []
    return data.get("data", []) or []


def collect_capitol_trades(
    cfg: Config,
    *,
    days_back: int = 30,
    page_size: int = 96,
) -> pd.DataFrame:
    rows = []
    trades = fetch_capitol_trades(days_back=days_back, page_size=page_size)
    for t in trades:
        ticker = (t.get("asset") or {}).get("assetTicker") or ""
        if not ticker:
            continue
        side = (t.get("txType") or "").lower()
        # B = Buy, S = Sell; map to sentiment.
        if "buy" in side or side == "b":
            sentiment, label = 0.25, "bullish"
        elif "sell" in side or side == "s":
            sentiment, label = -0.25, "bearish"
        else:
            sentiment, label = 0.0, "neutral"
        pol = (t.get("politician") or {}).get("fullName") or "?"
        party = (t.get("politician") or {}).get("party") or ""
        chamber = (t.get("politician") or {}).get("chamber") or ""
        ts_raw = t.get("pubDate") or t.get("txDate")
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else datetime.now(timezone.utc)
        except (ValueError, AttributeError):
            ts = datetime.now(timezone.utc)
        text = (
            f"CapitolTrades: {pol} ({party} {chamber}) {side} {ticker} on {ts.date().isoformat()}"
        )
        rows.append({
            "timestamp": ts,
            "source": "capitol_trades",
            "source_id": f"ct:{t.get('id') or ts.isoformat()}:{ticker}",
            "ticker": ticker.upper(),
            "alias": ticker.lower(),
            "confidence": 0.95,
            "via": "stock_act_filing",
            "text": text[:4000],
            "sentiment": sentiment,
            "sentiment_label": label,
            "url": "https://www.capitoltrades.com/",
            "author": pol,
        })
    log.info("capitol_trades: %d filings -> mention rows", len(rows))
    return normalized_dataframe(rows)
