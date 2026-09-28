"""Narrative / sector labels for tokens from CoinGecko category lists (no key).

A token takes the first matching sector in SECTORS order, so a Solana memecoin
is a memecoin and an AI agent token on Base is AI. Matching to FMP symbols is
on ticker plus a normalised-name check.
"""
from __future__ import annotations

import json
import re
import time

import pandas as pd
import requests

from .config import CACHE_DIR

CG = "https://api.coingecko.com/api/v3/coins/markets"
SECTORS = [  # (label, coingecko category ids)
    ("Memecoins", ["meme-token"]),
    ("AI", ["artificial-intelligence", "ai-agents"]),
    ("Gaming / metaverse", ["gaming", "metaverse", "play-to-earn"]),
    ("DeFi", ["decentralized-finance-defi"]),
    ("Layer 1", ["layer-1"]),
    ("Layer 2 / scaling", ["layer-2", "zero-knowledge-zk"]),
    ("Infrastructure", ["infrastructure", "oracle", "storage", "depin"]),
    ("Exchange tokens", ["exchange-based-tokens", "centralized-exchange-token-cex"]),
    ("RWA", ["real-world-assets-rwa"]),
    ("Privacy", ["privacy-coins"]),
]
PAGES = 4


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def fetch_category(cat: str) -> list[dict]:
    path = CACHE_DIR / "coingecko" / f"{cat}.json"
    if path.exists():
        return json.loads(path.read_text())
    out = []
    for page in range(1, PAGES + 1):
        for attempt in range(6):
            r = requests.get(CG, params={"vs_currency": "usd", "category": cat, "per_page": 250, "page": page},
                             timeout=60)
            if r.status_code == 429:
                time.sleep(30 + 15 * attempt)
                continue
            break
        if r.status_code != 200:
            break
        rows = r.json()
        out.extend({"id": x["id"], "symbol": x["symbol"], "name": x["name"]} for x in rows)
        time.sleep(7)
        if len(rows) < 250:
            break
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def build(meta: pd.DataFrame) -> pd.Series:
    """Series symbol -> sector label for FMP symbols."""
    tick = pd.Series(meta.index.str.replace(r"USD$", "", regex=True).str.lower(), index=meta.index)
    names = meta["name"].map(_norm)
    label = pd.Series(index=meta.index, dtype=object)
    for sector, cats in SECTORS:
        for cat in cats:
            for x in fetch_category(cat):
                cand = tick.index[(tick == x["symbol"].lower())]
                for s in cand:
                    if pd.isna(label[s]) and (names[s] == _norm(x["name"]) or names[s] == _norm(x["id"])
                                              or (len(cand) == 1 and names[s][:4] == _norm(x["name"])[:4])):
                        label[s] = sector
    out = label.dropna()
    out.to_csv(CACHE_DIR / "sectors.csv", header=["sector"])
    return out
