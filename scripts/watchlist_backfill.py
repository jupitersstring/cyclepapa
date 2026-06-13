"""Comprehensive per-ticker backfill across all working free collectors.

For each ticker in `tickers`:
  1. HackerNews historical (365 days, sweeps in 30d chunks)
  2. yfinance news (last 30 days of headlines)
  3. Stocktwits (last 30 messages)
  4. Bluesky search (last week)

Skips collectors that previously failed for that ticker. Idempotent
via storage.upsert_mentions on (source, source_id, ticker).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb.config import Config
from social_arb.pipeline import Pipeline
from social_arb import storage
from social_arb.collectors.hackernews import backfill_hackernews
from social_arb.collectors.yfinance_news import collect_yfinance_news
from social_arb.collectors.stocktwits import collect_stocktwits
from social_arb.collectors.bluesky import collect_bluesky


def backfill_one_ticker(pipe: Pipeline, ticker: str, *, hn_days: int = 365,
                        skip: tuple[str, ...] = ()) -> dict[str, int]:
    """Backfill a single ticker across the working free collectors."""
    cfg = pipe.cfg
    totals: dict[str, int] = {"hn": 0, "yf_news": 0, "stocktwits": 0, "bluesky": 0}
    # 1. HackerNews -- DISAMBIGUATED query: cashtag OR "TICKER stock"
    #    so we don't catch the dictionary-word sense of symbols like
    #    RENT, JACK, SAT, AIR, etc. Algolia treats quoted phrases as
    #    exact-match.
    if "hn" not in skip:
        try:
            query = f'"${ticker}" OR "{ticker} stock"'
            df = backfill_hackernews(
                cfg, pipe.resolver, pipe.sentiment,
                query=query, days_back=int(hn_days), chunk_days=30,
            )
            totals["hn"] = storage.upsert_mentions(cfg, df)
        except Exception as exc:  # noqa: BLE001
            logging.warning("hn failed for %s: %s", ticker, exc)
    # 2. yfinance news
    if "yf_news" not in skip:
        try:
            df = collect_yfinance_news(cfg, pipe.sentiment, ticker=ticker)
            totals["yf_news"] = storage.upsert_mentions(cfg, df)
        except Exception as exc:  # noqa: BLE001
            logging.warning("yf news failed for %s: %s", ticker, exc)
    # 3. Stocktwits
    if "stocktwits" not in skip:
        try:
            df = collect_stocktwits(cfg, pipe.sentiment, ticker=ticker)
            totals["stocktwits"] = storage.upsert_mentions(cfg, df)
        except Exception as exc:  # noqa: BLE001
            logging.warning("stocktwits failed for %s: %s", ticker, exc)
    # 4. Bluesky search by cashtag
    if "bluesky" not in skip:
        try:
            df = collect_bluesky(cfg, pipe.resolver, pipe.sentiment,
                                  query=f"${ticker}", hours_back=168, limit=50)
            totals["bluesky"] = storage.upsert_mentions(cfg, df)
        except Exception as exc:  # noqa: BLE001
            logging.warning("bluesky failed for %s: %s", ticker, exc)
    return totals


def load_watchlist(args: argparse.Namespace, pipe: Pipeline) -> list[str]:
    """Resolve --tickers, --file, or --from-asymmetric into a list."""
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if args.file:
        return [
            line.strip().upper()
            for line in Path(args.file).read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
    # Default: top N small/mid-cap names from previous asymmetric scan.
    return [
        # Pure small/mid-cap consumer + recognizable brands
        "RENT", "BBW", "VITL", "TRIP", "PTLO", "NRDS", "CURI", "BYRN",
        "CTEV", "FOUR", "DOCS", "TEM", "RXRX", "FND", "COTY", "WHR",
        "EXPI", "FLO", "SPRY", "LENZ", "CERT", "EMBC", "GTM", "GT",
        "CABO", "SAM", "BYD", "SIRI", "GAP", "RYAN", "CIA", "MAX",
        "TILE", "GLAD", "AKA", "EARN", "CTO", "PAYS", "DECK", "MAT",
        "CROX", "NWL", "UAA", "LULU", "CELH", "HOOD",
        # Industrial / mid-cap turnarounds
        "MANH", "FICO", "SNOW", "FTDR", "DOV", "UPS", "BIRD", "INSP",
        "BLKB", "CMPR", "ATKR", "TEX", "BC", "PVH", "TACO", "AENT",
        # Healthcare
        "AZTA", "QTRX", "RGNX", "ABR", "FWRD", "KROS",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Comprehensive per-ticker backfill across free collectors"
    )
    parser.add_argument("--tickers", default=None,
                       help="comma-separated tickers; default = built-in watchlist")
    parser.add_argument("--file", default=None,
                       help="file with one ticker per line")
    parser.add_argument("--hn-days", dest="hn_days", type=int, default=365)
    parser.add_argument("--skip", nargs="*", default=[],
                       choices=["hn", "yf_news", "stocktwits", "bluesky"])
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--throttle", type=float, default=0.5,
                       help="seconds to sleep between tickers")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    pipe = Pipeline.build()
    tickers = load_watchlist(args, pipe)
    print(f"backfilling {len(tickers)} tickers x {4 - len(args.skip)} collectors")

    grand = {"hn": 0, "yf_news": 0, "stocktwits": 0, "bluesky": 0}
    for i, t in enumerate(tickers, 1):
        totals = backfill_one_ticker(pipe, t, hn_days=args.hn_days, skip=tuple(args.skip))
        for k, v in totals.items():
            grand[k] += v
        if i % 5 == 0 or i == len(tickers):
            print(f"  {i}/{len(tickers)}  {t:<8}  +{sum(totals.values())} rows  "
                  f"running totals: {grand}")
        time.sleep(args.throttle)

    print()
    print("=" * 60)
    for k, v in grand.items():
        print(f"{k:>14}: {v:,}")
    print(f"{'TOTAL':>14}: {sum(grand.values()):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
