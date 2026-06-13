"""Fast bulk purge: delete every mention attributed to a ticker that is
also a common English word, for any non-cashtag-confirmed source.

The per-row re-resolution job at ~1k rows/min is too slow on our 170k
store. We don't need per-row evaluation -- we know exactly what's wrong:

  - HackerNews backfill used the bare ticker string as the search
    query, so every result tagged a dictionary-word ticker (RENT,
    JACK, SAT, AIR, MAX, GAP, PAYS, EARN, etc.) is a word collision.
  - 4chan / Reddit RSS / Yahoo Conversations etc. resolved on free text
    where dictionary-word tickers fire on noise unless there was an
    explicit $cashtag.

Strategy:
  For each (source, ticker) cell where the ticker is a dictionary word
  AND the source is not a per-ticker stream (stocktwits, yfinance_news,
  yahoo_conversations, openinsider all confirm the ticker upstream):
    delete the rows.

This is conservative: we keep all stocktwits/yfinance_news/etc rows
because those collectors query by ticker directly, so the attribution
is upstream-confirmed. We only purge sources that resolve from open text.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb import storage
from social_arb.aliases import is_dictionary_word
from social_arb.config import Config


# Sources that resolve from free text (subject to word-collision FPs).
FREE_TEXT_SOURCES = (
    "hackernews",
    "fourchan_biz",
    "gdelt",
    "bluesky",
    "mastodon",
    "x_via_nitter",
    "telegram",
    "twitter_twikit",
    "youtube_comments",
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s :: %(message)s")
    cfg = Config()
    with storage.connect(cfg) as con:
        # 1. Enumerate (source, ticker) cells with attribution from free-text sources
        df = con.execute(
            f"""
            SELECT source, ticker, COUNT(*) AS n
            FROM mentions
            WHERE source IN {tuple(FREE_TEXT_SOURCES)}
            GROUP BY source, ticker
            ORDER BY n DESC
            """
        ).df()

    print(f"free-text-source cells: {len(df):,}")
    bad_cells = df[df["ticker"].astype(str).apply(is_dictionary_word)].copy()
    print(f"  cells where ticker is a dictionary word: {len(bad_cells):,}")
    bad_cells = bad_cells.sort_values("n", ascending=False)
    print()
    print("Top 25 dictionary-word cells to purge (by row count):")
    print(bad_cells.head(25).to_string(index=False))

    total_to_purge = int(bad_cells["n"].sum())
    print(f"\nrows to delete: {total_to_purge:,}")

    with storage.connect(cfg) as con:
        bad_pairs = bad_cells[["source", "ticker"]]
        con.register("bad_pairs", bad_pairs)
        before = con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
        con.execute(
            """
            DELETE FROM mentions
            WHERE (source, ticker) IN (SELECT source, ticker FROM bad_pairs)
            """
        )
        after = con.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
        con.unregister("bad_pairs")
    print(f"\nstore: {before:,} -> {after:,}  (deleted {before - after:,} rows)")
    # Also mark all remaining free-text rows as v2 since they survived the purge.
    with storage.connect(cfg) as con:
        con.execute(
            f"""
            UPDATE mentions SET resolver_version = 2
            WHERE source IN {tuple(FREE_TEXT_SOURCES)} AND resolver_version < 2
            """
        )
        marked = con.execute(
            "SELECT COUNT(*) FROM mentions WHERE resolver_version = 2"
        ).fetchone()[0]
    print(f"rows now marked v2: {marked:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
