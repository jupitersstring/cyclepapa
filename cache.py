"""On-disk cache for EDGAR documents, yfinance prices, and scored rows.

EDGAR proxies are immutable once filed -- accession numbers are perfect
cache keys with no TTL needed. Prices need a short TTL. Scored rows are
keyed by accession so a full pipeline rerun on the same filings is free.

Layout (under ./.cache by default):
    docs/<accession>.html         raw HTML, lazily downloaded
    scores/<accession>.json       full scored row, including snippets
    prices/<ticker>.json          spot price (TTL via mtime)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

CACHE_ROOT = Path(os.environ.get("PSU_CACHE_DIR", ".cache"))


def _safe(name: str) -> str:
    return name.replace("/", "_").replace(":", "_").replace("\\", "_")


# ---- raw filing HTML -----------------------------------------------------

def doc_path(accession: str) -> Path:
    return CACHE_ROOT / "docs" / f"{_safe(accession)}.html"


def get_doc(accession: str) -> str | None:
    p = doc_path(accession)
    if p.exists():
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return None
    return None


def put_doc(accession: str, html: str) -> None:
    p = doc_path(accession)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8", errors="ignore")


# ---- scored rows ---------------------------------------------------------

def score_path(accession: str) -> Path:
    return CACHE_ROOT / "scores" / f"{_safe(accession)}.json"


def get_score(accession: str) -> dict | None:
    p = score_path(accession)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def put_score(accession: str, row: dict) -> None:
    p = score_path(accession)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(row, default=str))


# ---- spot price ----------------------------------------------------------

def price_path(ticker: str) -> Path:
    return CACHE_ROOT / "prices" / f"{_safe(ticker.upper())}.json"


def get_price(ticker: str, ttl_seconds: int = 6 * 60 * 60) -> float | None:
    p = price_path(ticker)
    if not p.exists():
        return None
    if time.time() - p.stat().st_mtime > ttl_seconds:
        return None
    try:
        return float(p.read_text())
    except Exception:
        return None


def put_price(ticker: str, price: float) -> None:
    p = price_path(ticker)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(float(price)))
