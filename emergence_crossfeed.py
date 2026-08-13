"""Emergence cross-feed layer — post-reorg entities from the pollers
subsystem.

The repository's OTHER research system (emergence/pollers, branch
claude/capital-structure-screening-*) tracks Chapter 11 emergences
through five independent EDGAR channels (plan-effective 8-K, emergence
8-K prose, Form 15 deregistration, Form 25 old-share delisting, Item
1.03) and grades each entity's confidence by corroboration. Its master
file covers ~587 entities vs the 29 in this engine's own
post_ch11_emergence.json — a major coverage upgrade for the
Eberhart-Altman post-reorg pattern (newly-emerged equity is
structurally under-followed and historically outperforms).

This module reads a committed snapshot (emergence_master_snapshot.json,
refreshed by copying data/emergence_master.json from that branch) and
scores each US-ticker entity for the consensus:

  - confidence: multi-channel corroborated ("high") outranks a single
    primary source, which outranks corroborating-signals-only.
  - channel breadth: each independent detection channel beyond the
    first adds a little (independent confirmations, same thesis).
  - recency: the mispricing window concentrates in the first months
    post-emergence; stale emergences decay to a token score.
  - pending (still in Ch11, Q-suffix ticker): tracked but NOT scored --
    pre-emergence equity is a different (usually worthless) instrument.

Output: emergence_crossfeed.json {ticker: {score, ...}} — additive; the
existing post_ch11 layer is untouched and the correlation stage will
report any overlap honestly.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/user/cyclepapa")
SRC = ROOT / "emergence_master_snapshot.json"
OUT = ROOT / "emergence_crossfeed.json"

_TICKER_BLOCKLIST = {"NONE", "N/A", "NA", "NAN", "NULL", "", "-"}
_TICKER_RX = re.compile(r"^[A-Z][A-Z0-9.\-]{0,6}$")


def is_valid_ticker(tk) -> bool:
    if not tk or not isinstance(tk, str):
        return False
    t = tk.strip().upper()
    if t in _TICKER_BLOCKLIST or t.startswith("CIK"):
        return False
    return bool(_TICKER_RX.match(t))


def confidence_base(confidence: str) -> float:
    """Map the pollers subsystem's confidence grade to a base score."""
    c = (confidence or "").lower()
    if c.startswith("high"):
        return 20.0
    if c.startswith("medium (single primary"):
        return 12.0
    if c.startswith("medium"):
        return 8.0
    if c.startswith("low"):
        return 4.0
    return 0.0


def recency_factor(last_filed: str, today: datetime | None = None) -> float:
    """Post-reorg mispricing decays; scale by age of the last filing."""
    if today is None:
        today = datetime.now(timezone.utc)
    try:
        d = datetime.strptime(str(last_filed)[:10], "%Y-%m-%d")
        d = d.replace(tzinfo=timezone.utc)
    except Exception:
        return 0.5
    age = (today - d).days
    if age <= 90:
        return 1.0
    if age <= 180:
        return 0.75
    if age <= 365:
        return 0.5
    return 0.25


def score_entity(e: dict, today: datetime | None = None) -> dict | None:
    tk = (e.get("ticker") or "").strip().upper()
    if not is_valid_ticker(tk):
        return None
    if e.get("pending"):
        # still in Chapter 11 -- old equity, not the emergence instrument
        return None
    base = confidence_base(e.get("confidence"))
    if base <= 0:
        return None
    channels = e.get("channels") or {}
    n_channels = len(channels)
    breadth = min(3, max(0, n_channels - 1)) * 3.0
    rec = recency_factor(e.get("last_filed"), today)
    score = round((base + breadth) * rec, 1)
    if score <= 0:
        return None
    return {
        "ticker": tk,
        "name": e.get("name"),
        "confidence": e.get("confidence"),
        "n_channels": n_channels,
        "channels": sorted(channels.keys()),
        "first_filed": e.get("first_filed"),
        "last_filed": e.get("last_filed"),
        "score": score,
    }


def main() -> int:
    if not SRC.exists():
        print(f"missing {SRC}; copy data/emergence_master.json from the "
              "capital-structure-screening branch")
        return 1
    entities = json.loads(SRC.read_text())
    print(f"loaded emergence master snapshot: {len(entities)} entities")

    out = {}
    for e in entities:
        if not isinstance(e, dict):
            continue
        rec = score_entity(e)
        if rec is None:
            continue
        prev = out.get(rec["ticker"])
        if prev is None or rec["score"] > prev["score"]:
            out[rec["ticker"]] = rec

    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT} ({len(out)} scored tickers)")

    ranked = sorted(out.values(), key=lambda r: -r["score"])
    print("\n=== TOP 20 emergence cross-feed ===")
    print(f"{'TKR':<8}{'SCR':>6}{'CH':>4}  {'LAST':<12}NAME")
    for r in ranked[:20]:
        print(f"{r['ticker']:<8}{r['score']:>6.1f}{r['n_channels']:>4}  "
              f"{str(r['last_filed'])[:10]:<12}{(r['name'] or '')[:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
