"""Phase 1 re-resolution: walk every stored mention through the v2 resolver.

For each row, run the stored `text` through the new resolver. Three outcomes:

  - VALID:   the v2 resolver also returns the same ticker -> mark v2, keep
  - INVALID: the v2 resolver returns no ticker (the original was a
             dictionary-word collision) -> mark dropped, delete from store
  - MIGRATE: the v2 resolver returns DIFFERENT tickers
             (rare; for safety we keep both rows but log)

Reports per-source precision before/after so the impact is auditable.

Usage:
    python scripts/reresolve_mentions.py [--dry-run] [--source hackernews]

Safe to re-run; idempotent on resolver_version.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb import storage
from social_arb.config import Config
from social_arb.pipeline import Pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                       help="report only, no DB modifications")
    parser.add_argument("--source", default=None,
                       help="re-resolve only this source (default: all v1 rows)")
    parser.add_argument("--batch", type=int, default=10000)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s :: %(message)s",
    )

    cfg = Config()
    pipe = Pipeline.build(cfg)

    where = "resolver_version IS NULL OR resolver_version < 2"
    if args.source:
        where += f" AND source = '{args.source}'"

    with storage.connect(cfg) as con:
        total = con.execute(f"SELECT COUNT(*) FROM mentions WHERE {where}").fetchone()[0]
        print(f"rows to re-resolve: {total:,}")
        if total == 0:
            print("nothing to do")
            return 0

    kept_per_source: dict[str, int] = defaultdict(int)
    invalid_per_source: dict[str, int] = defaultdict(int)
    migrate_per_source: dict[str, int] = defaultdict(int)
    invalid_pkeys: list[tuple[str, str, str]] = []  # (source, source_id, ticker)
    migrate_inserts: list[dict] = []

    offset = 0
    while offset < total:
        with storage.connect(cfg) as con:
            chunk = con.execute(f"""
                SELECT timestamp, source, source_id, ticker, alias, confidence,
                       via, text, sentiment, sentiment_label, url, author
                FROM mentions
                WHERE {where}
                ORDER BY source, source_id
                LIMIT {args.batch} OFFSET {offset}
            """).df()
        if chunk.empty:
            break
        for _, row in chunk.iterrows():
            text = str(row["text"]) if pd.notna(row["text"]) else ""
            current_ticker = str(row["ticker"]) if pd.notna(row["ticker"]) else ""
            src = str(row["source"])
            mentions = pipe.resolver.resolve(text)
            tickers_now = {m.ticker for m in mentions}
            if current_ticker in tickers_now:
                kept_per_source[src] += 1
            elif not tickers_now:
                invalid_per_source[src] += 1
                invalid_pkeys.append((src, str(row["source_id"]), current_ticker))
            else:
                migrate_per_source[src] += 1
                for m in mentions:
                    migrate_inserts.append({
                        "timestamp": row["timestamp"],
                        "source": src,
                        "source_id": str(row["source_id"]) + ":v2",
                        "ticker": m.ticker,
                        "alias": m.alias,
                        "confidence": m.confidence,
                        "via": m.via,
                        "text": text[:4000],
                        "sentiment": float(row["sentiment"]) if pd.notna(row["sentiment"]) else 0.0,
                        "sentiment_label": str(row["sentiment_label"]) if pd.notna(row["sentiment_label"]) else "neutral",
                        "url": str(row["url"]) if pd.notna(row["url"]) else "",
                        "author": str(row["author"]) if pd.notna(row["author"]) else "",
                        "resolver_version": 2,
                    })
        offset += len(chunk)
        print(f"  processed {offset:,}/{total:,}  "
              f"valid={sum(kept_per_source.values()):,}  "
              f"invalid={sum(invalid_per_source.values()):,}  "
              f"migrated={sum(migrate_per_source.values()):,}")

    print()
    print("=== Per-source resolver v1 -> v2 outcomes ===")
    sources = sorted(set(kept_per_source) | set(invalid_per_source) | set(migrate_per_source))
    df = pd.DataFrame([
        {
            "source": s,
            "v2_valid": kept_per_source.get(s, 0),
            "v2_invalid": invalid_per_source.get(s, 0),
            "migrated": migrate_per_source.get(s, 0),
            "precision_v1": round(
                kept_per_source.get(s, 0)
                / max(1, kept_per_source.get(s, 0) + invalid_per_source.get(s, 0)),
                3,
            ),
        }
        for s in sources
    ])
    df = df.sort_values("v2_invalid", ascending=False)
    pd.set_option("display.width", 220)
    print(df.to_string(index=False))

    if args.dry_run:
        print("\n(dry-run; no DB changes)")
        return 0

    # 1. Mark kept rows as v2.
    with storage.connect(cfg) as con:
        con.execute(f"UPDATE mentions SET resolver_version = 2 WHERE {where}")
    # 2. Delete invalid rows.
    if invalid_pkeys:
        with storage.connect(cfg) as con:
            con.register("invalid_pk", pd.DataFrame(invalid_pkeys, columns=["source", "source_id", "ticker"]))
            con.execute("""
                DELETE FROM mentions
                WHERE (source, source_id, ticker) IN
                  (SELECT source, source_id, ticker FROM invalid_pk)
            """)
            con.unregister("invalid_pk")
    print(f"\n marked {sum(kept_per_source.values()):,} as v2_valid")
    print(f" deleted {sum(invalid_per_source.values()):,} v1-invalid rows")

    # 3. Insert migrated re-attributions (deduped via PK).
    if migrate_inserts:
        storage.upsert_mentions(cfg, pd.DataFrame(migrate_inserts))
        print(f" inserted {len(migrate_inserts):,} v2-migrated rows")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
