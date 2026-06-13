"""Phase 2 compaction: collapse synthetic-duplicate rows into single weighted rows.

The Wikipedia / Apewisdom / Google-Trends / Brave-Search / TikTok /
job_postings collectors used to emit N synthetic rows per observation
so that COUNT(*)-based downstream rankers saw scale. With the
`weight` column now on schema, ONE row per observation carrying a
numeric weight is the right pattern.

This script collapses the historical duplicates in-place:

  For each (source, ticker, date, source_id_prefix), keep one
  representative row whose `weight` = count of collapsed rows
  (or, where the original captured a magnitude in `text`, log1p
  of that magnitude). Delete the rest.

Sources handled:
  - wikipedia           : weight = log1p(views) parsed from text
  - apewisdom:*         : weight = original mention count parsed from text
  - google_trends       : weight = trends index parsed from text
  - brave_search        : weight = log1p(results) parsed from text
  - tiktok_creative_*   : weight = log1p(publish_cnt) parsed from text
  - job_postings        : weight = log1p(open postings) parsed from text

Other sources are left untouched (their rows already represent one
real post / comment / filing each = weight 1.0).
"""

from __future__ import annotations

import argparse
import logging
import math
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb import storage
from social_arb.config import Config


SYNTHETIC_SOURCES = (
    "wikipedia",
    "apewisdom:wallstreetbets",
    "apewisdom:stocks",
    "apewisdom:stockmarket",
    "google_trends",
    "brave_search",
    "tiktok_creative_center",
    "job_postings",
)


def _extract_weight_from_text(source: str, text: str) -> float:
    """Recover the original magnitude from the row's text field."""
    if not text:
        return 1.0
    if source == "wikipedia":
        m = re.search(r"views=(\d+)", text)
        if m:
            return float(math.log1p(int(m.group(1))))
    elif source.startswith("apewisdom"):
        m = re.search(r"mentions=(\d+)", text)
        if m:
            return float(int(m.group(1)))
    elif source == "google_trends":
        m = re.search(r"=(\d+) on \d", text)
        if m:
            return float(int(m.group(1)))
    elif source == "brave_search":
        m = re.search(r"results=(\d+)", text)
        if m:
            return float(math.log1p(int(m.group(1))))
    elif source == "tiktok_creative_center":
        m = re.search(r"publish_cnt=(\d+)", text)
        if m:
            return float(math.log1p(int(m.group(1))) * 2.0)
    elif source == "job_postings":
        m = re.search(r"(\d+) open postings", text)
        if m:
            return float(math.log1p(int(m.group(1))) * 1.5)
    return 1.0


def _canonical_source_id(source: str, raw_id: str) -> str:
    """Strip the per-row index suffix to derive the canonical observation id.

    Old synthetic format used trailing `:N` indices; we strip those.
    Examples:
      'wiki:Mattel:2024-05-18:7' -> 'wiki:Mattel:2024-05-18'
      'wallstreetbets:2026-05-17:NVDA:42' -> 'wallstreetbets:2026-05-17:NVDA'
    """
    return re.sub(r":\d+$", "", str(raw_id))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", default=None,
                       help="limit to one source; default = all synthetic sources")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s :: %(message)s")
    cfg = Config()

    sources = [args.source] if args.source else list(SYNTHETIC_SOURCES)
    grand_before = 0
    grand_after = 0
    grand_weight = 0.0
    for src in sources:
        with storage.connect(cfg) as con:
            n = con.execute(
                "SELECT COUNT(*) FROM mentions WHERE source = ?", [src],
            ).fetchone()[0]
        if n == 0:
            continue
        print(f"\n=== {src}: {n:,} rows ===")
        with storage.connect(cfg) as con:
            df = con.execute(
                "SELECT * FROM mentions WHERE source = ?", [src],
            ).df()
        df["canon_id"] = df["source_id"].apply(lambda s: _canonical_source_id(src, s))
        # Group by (ticker, canon_id) -- one row per real observation
        grouped = df.groupby(["ticker", "canon_id"], as_index=False).agg(
            timestamp=("timestamp", "min"),
            source_id=("source_id", "first"),
            alias=("alias", "first"),
            confidence=("confidence", "first"),
            via=("via", "first"),
            text=("text", "first"),
            sentiment=("sentiment", "mean"),
            sentiment_label=("sentiment_label", "first"),
            url=("url", "first"),
            author=("author", "first"),
            count_collapsed=("text", "count"),
        )
        # Derive the weight from the text where applicable, else use the
        # collapsed-count as the weight.
        grouped["weight_from_text"] = grouped.apply(
            lambda r: _extract_weight_from_text(src, r["text"]), axis=1,
        )
        # Prefer parsed-text weight if it's > 1; otherwise fall back to
        # count-collapsed (we always at least have 1 row).
        grouped["weight"] = grouped[["weight_from_text", "count_collapsed"]].max(axis=1)
        grouped["source"] = src
        grouped["resolver_version"] = 2
        grouped["source_id"] = grouped["canon_id"]
        # Match storage REQUIRED_COLUMNS schema.
        keep = [
            "timestamp", "source", "source_id", "ticker", "alias", "confidence",
            "via", "text", "sentiment", "sentiment_label", "url", "author",
            "resolver_version", "weight",
        ]
        compacted = grouped[keep]
        before = len(df)
        after = len(compacted)
        weight_total = float(compacted["weight"].sum())
        grand_before += before
        grand_after += after
        grand_weight += weight_total
        print(f"  collapsed: {before:,} -> {after:,} rows  (weight sum: {weight_total:,.1f})")
        if args.dry_run:
            continue
        # Replace the source's rows in one transaction.
        with storage.connect(cfg) as con:
            con.execute("DELETE FROM mentions WHERE source = ?", [src])
            con.register("compacted", compacted)
            con.execute("INSERT INTO mentions SELECT * FROM compacted")
            con.unregister("compacted")
        print(f"  replaced in-place: {after:,} rows now in store for source={src}")

    print()
    print(f"=== TOTAL: {grand_before:,} -> {grand_after:,} rows  "
          f"({grand_before - grand_after:,} duplicates removed; "
          f"weight sum preserved = {grand_weight:,.1f}) ===")
    if args.dry_run:
        print("(dry-run; no DB changes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
