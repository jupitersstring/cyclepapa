"""Telegram public-channel scraper via Telethon -- the spec's "sleeper hit".

Telethon drives Telegram's MTProto protocol from a real phone-number
account. With ONE phone number you can join 50+ public channels and
read their entire history + stream new messages live. The audience on
finance / crypto / consumer-launch Telegram is the most engaged anywhere
short of Discord-but-discoverable.

CREDENTIALS:
  Get TELEGRAM_API_ID and TELEGRAM_API_HASH from https://my.telegram.org
  Set TELEGRAM_PHONE env var to the SIM number used.
  A session file is saved to data/telethon.session for re-runs.

USAGE:
  collect_telegram(cfg, resolver, sentiment,
                   channels=["@WSBChatter", "@CryptoNewsPlus", ...],
                   limit_per_channel=200)

This collector is OPT-IN: raises a clear error when env vars missing.
Be polite -- Telegram aggressively bans accounts running mass scrapes
without rate-limiting.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ..config import Config
from ..entity_resolution import Resolver
from ..sentiment import SentimentScorer
from .base import normalized_dataframe

log = logging.getLogger(__name__)


async def _scrape(channels: list[str], limit: int) -> list[dict]:
    from telethon import TelegramClient  # type: ignore
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    phone = os.environ.get("TELEGRAM_PHONE")
    if not (api_id and api_hash and phone):
        raise RuntimeError(
            "Telegram needs TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_PHONE env vars"
        )
    session_path = Path("data") / "telethon.session"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session_path), int(api_id), api_hash)
    await client.start(phone=phone)
    rows: list[dict] = []
    for ch in channels:
        try:
            entity = await client.get_entity(ch)
            async for msg in client.iter_messages(entity, limit=int(limit)):
                if not msg.message:
                    continue
                rows.append({
                    "channel": ch,
                    "id": msg.id,
                    "date": msg.date,
                    "text": msg.message,
                    "sender": getattr(getattr(msg, "sender", None), "username", None),
                })
        except Exception as exc:  # noqa: BLE001
            log.warning("telegram channel %s failed: %s", ch, exc)
            continue
    await client.disconnect()
    return rows


def collect_telegram(
    cfg: Config,
    resolver: Resolver,
    sentiment: SentimentScorer,
    *,
    channels: list[str],
    limit_per_channel: int = 200,
) -> pd.DataFrame:
    try:
        import telethon  # noqa: F401
    except ImportError:
        log.warning("telethon not installed; `pip install telethon`")
        return normalized_dataframe([])
    try:
        raw = asyncio.run(_scrape(channels, limit_per_channel))
    except RuntimeError as exc:
        log.warning("telegram disabled: %s", exc)
        return normalized_dataframe([])
    except Exception as exc:  # noqa: BLE001
        log.warning("telegram scrape error: %s", exc)
        return normalized_dataframe([])

    out_rows: list[dict] = []
    for r in raw:
        text = (r["text"] or "").strip()
        if not text or len(text) < 10:
            continue
        mentions = resolver.resolve(text)
        if not mentions:
            continue
        ts = r["date"] if isinstance(r["date"], datetime) else datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        s = sentiment.score(text)
        for m in mentions:
            out_rows.append({
                "timestamp": ts,
                "source": f"telegram:{r['channel']}",
                "source_id": f"{r['channel']}:{r['id']}",
                "ticker": m.ticker,
                "alias": m.alias,
                "confidence": m.confidence * 0.9,
                "via": m.via,
                "text": text[:4000],
                "sentiment": s.compound,
                "sentiment_label": s.label,
                "url": "",
                "author": r["sender"],
            })
    log.info("telegram: %d mention rows from %d channels", len(out_rows), len(channels))
    return normalized_dataframe(out_rows)
