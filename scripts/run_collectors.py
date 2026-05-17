"""One-shot collector runner intended for cron / GitHub Actions.

Pulls a sensible default cross-section of free sources and persists into the
DuckDB store. Safe to re-run -- upserts dedupe on (source, source_id, ticker).

Usage:
    python scripts/run_collectors.py
    python scripts/run_collectors.py --skip gdelt
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_arb.pipeline import Pipeline


CONSUMER_SUBS = [
    "wallstreetbets", "stocks", "investing", "stockmarket",
    "SkincareAddiction", "BuyItForLife", "MaleFashionAdvice",
    "Sneakers", "GenZ",
]

CAMILLO_GDELT_QUERIES = [
    '"Mattel" OR "Barbie"',
    '"Crocs"',
    '"Celsius energy drink"',
    '"Tapestry" OR "Coach handbags"',
    '"Newell Brands" OR "Elmer\'s Glue"',
    '"Stanley tumbler"',
    '"Hoka"',
    '"Yeti"',
]

WATCHLIST_STOCKTWITS = ["NVDA", "GME", "MAT", "CROX", "CELH", "TPR", "DECK"]

HN_QUERIES = ["NVIDIA", "AMD", "Tesla", "Apple", "Palantir", "OpenAI", "Anthropic", "Crocs", "Stanley tumbler"]

CONSUMER_REDDIT_RSS = [
    "wallstreetbets", "stocks", "investing", "stockmarket",
    "SkincareAddiction", "BuyItForLife", "MaleFashionAdvice",
    "Sneakers", "frugalmalefashion", "Sephora", "femalefashionadvice",
]

WIKI_TARGETS = [
    ("Mattel", "MAT"),
    ("Crocs", "CROX"),
    ("Celsius_Holdings", "CELH"),
    ("Deckers_Outdoor_Corporation", "DECK"),
    ("Nvidia", "NVDA"),
    ("GameStop", "GME"),
    ("Tapestry,_Inc.", "TPR"),
    ("Lululemon_Athletica", "LULU"),
    ("Newell_Brands", "NWL"),
    ("Under_Armour", "UAA"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip", nargs="*", default=[],
                        choices=["reddit", "apewisdom", "gdelt", "stocktwits",
                                 "hackernews", "reddit_rss", "yfinance_news",
                                 "wikipedia", "form4"])
    parser.add_argument("--reddit-days", type=int, default=1)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
    )

    pipe = Pipeline.build()
    totals = {
        "reddit": 0, "apewisdom": 0, "gdelt": 0, "stocktwits": 0,
        "hackernews": 0, "reddit_rss": 0, "yfinance_news": 0,
        "wikipedia": 0, "form4": 0,
    }

    if "reddit" not in args.skip:
        for sub in CONSUMER_SUBS:
            try:
                totals["reddit"] += pipe.run_reddit(subreddit=sub, days_back=args.reddit_days)
            except Exception as exc:  # noqa: BLE001
                logging.warning("reddit %s failed: %s", sub, exc)

    if "apewisdom" not in args.skip:
        for f in ("wallstreetbets", "stocks", "stockmarket"):
            try:
                totals["apewisdom"] += pipe.run_apewisdom(filter_name=f)
            except Exception as exc:  # noqa: BLE001
                logging.warning("apewisdom %s failed: %s", f, exc)

    if "gdelt" not in args.skip:
        for q in CAMILLO_GDELT_QUERIES:
            try:
                totals["gdelt"] += pipe.run_gdelt(query=q, hours_back=24)
            except Exception as exc:  # noqa: BLE001
                logging.warning("gdelt %s failed: %s", q, exc)

    if "stocktwits" not in args.skip:
        for t in WATCHLIST_STOCKTWITS:
            try:
                totals["stocktwits"] += pipe.run_stocktwits(ticker=t)
            except Exception as exc:  # noqa: BLE001
                logging.warning("stocktwits %s failed: %s", t, exc)

    if "hackernews" not in args.skip:
        for q in HN_QUERIES:
            try:
                totals["hackernews"] += pipe.run_hackernews(query=q, hours_back=72)
            except Exception as exc:  # noqa: BLE001
                logging.warning("hackernews %s failed: %s", q, exc)

    if "reddit_rss" not in args.skip:
        for sub in CONSUMER_REDDIT_RSS:
            try:
                totals["reddit_rss"] += pipe.run_reddit_rss(subreddit=sub, listing="new")
                totals["reddit_rss"] += pipe.run_reddit_rss(subreddit=sub, listing="top", period="week")
            except Exception as exc:  # noqa: BLE001
                logging.warning("reddit_rss %s failed: %s", sub, exc)

    if "yfinance_news" not in args.skip:
        for t in WATCHLIST_STOCKTWITS:
            try:
                totals["yfinance_news"] += pipe.run_yfinance_news(ticker=t)
            except Exception as exc:  # noqa: BLE001
                logging.warning("yfinance_news %s failed: %s", t, exc)

    if "wikipedia" not in args.skip:
        for title, t in WIKI_TARGETS:
            try:
                totals["wikipedia"] += pipe.run_wikipedia(title=title, ticker=t, days_back=45)
            except Exception as exc:  # noqa: BLE001
                logging.warning("wikipedia %s failed: %s", title, exc)

    if "form4" not in args.skip:
        try:
            totals["form4"] += pipe.run_form4(days_back=7, max_records=200)
        except Exception as exc:  # noqa: BLE001
            logging.warning("sec form4 failed: %s", exc)

    for k, v in totals.items():
        print(f"{k:>14}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
