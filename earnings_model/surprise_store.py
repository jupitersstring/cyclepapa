"""Durable, git-trackable store for fetched EPS-surprise data.

EPS surprises are the one leg that is *network-expensive* (one Yahoo call each,
heavily rate-limited) and *rollback-fragile*: they live inside the ephemeral
``cache/raw/*.json`` and a hosted-container rollback reverts them. The big
``data/*.parquet`` snapshot is too heavy (~20 MB) to re-commit every few minutes,
so we keep the surprises in a **compact, separately committable** JSON:

    data/surprises.json          {symbol: [{"date":..,"surprise_pct":..}, ...]}
    data/surprises_checked.json  [symbol, ...]   # attempted (incl. no-coverage)

The back-fill writes both as it runs and commits them frequently, so progress
survives a rollback. ``reinject_into_cache`` copies the durable surprises back
into ``cache/raw`` so the normal rebuild path picks them up; ``seed_from_cache``
captures whatever surprises currently sit in the cache into the store.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config, fundamentals as F, util

_REPO = Path(__file__).resolve().parent.parent
DATA_DIR = _REPO / "data"
SURPRISES_PATH = DATA_DIR / "surprises.json"
CHECKED_PATH = DATA_DIR / "surprises_checked.json"


def load() -> dict[str, list]:
    if SURPRISES_PATH.exists():
        try:
            return json.loads(SURPRISES_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save(store: dict[str, list]) -> None:
    # Atomic: this file is the DURABLE surprise copy — truncation loses coverage.
    util.atomic_write_text(SURPRISES_PATH, json.dumps(store, separators=(",", ":"), sort_keys=True))


def load_checked() -> set[str]:
    if CHECKED_PATH.exists():
        try:
            return set(json.loads(CHECKED_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_checked(checked: set[str]) -> None:
    util.atomic_write_text(CHECKED_PATH, json.dumps(sorted(checked), separators=(",", ":")))


def seed_from_cache() -> dict[str, list]:
    """Fold any surprises currently in cache/raw into the durable store (union)."""
    import glob
    store = load()
    added = 0
    for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
        try:
            raw = json.loads(Path(p).read_text())
        except (json.JSONDecodeError, OSError):
            continue
        sym = raw.get("symbol")
        if sym and raw.get("surprises") and sym not in store:
            store[sym] = raw["surprises"]
            added += 1
    if added:
        save(store)
    return store


def reinject_into_cache() -> int:
    """Write durable surprises back into the matching cache/raw files. Returns count."""
    store = load()
    n = 0
    for sym, sur in store.items():
        raw = F.load_raw(sym, ttl_days=None, fail_ttl_days=None)
        if raw is None:
            continue
        if raw.get("surprises") != sur:
            raw["surprises"] = sur
            F.save_raw(sym, raw)
            n += 1
    return n
