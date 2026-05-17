"""Command-line entry points.

Examples:

    python -m social_arb.cli universe --refresh
    python -m social_arb.cli collect reddit --subreddit wallstreetbets --days 1
    python -m social_arb.cli collect apewisdom --filter wallstreetbets --pages 2
    python -m social_arb.cli collect gdelt --query "Mattel Barbie"
    python -m social_arb.cli collect stocktwits --ticker NVDA
    python -m social_arb.cli anomalies --ticker GME
    python -m social_arb.cli backtest --signals signals.csv
"""

from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from .anomaly import AnomalyParams
from .backtest import EventStudyParams, event_study
from .config import Config
from .pipeline import Pipeline


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_universe(args: argparse.Namespace) -> int:
    cfg = Config()
    pipe = Pipeline.build(cfg, refresh_universe=args.refresh)
    print(f"universe: {len(pipe.universe_df)} rows -> {cfg.universe_parquet}")
    if args.search:
        from . import universe as uni_mod
        print(uni_mod.search(pipe.universe_df, args.search).to_string(index=False))
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    pipe = Pipeline.build()
    if args.source == "reddit":
        n = pipe.run_reddit(
            query=args.query, subreddit=args.subreddit,
            days_back=args.days, include_comments=args.comments, size=args.size,
        )
        print(f"reddit: {n} mentions stored")
    elif args.source == "apewisdom":
        n = pipe.run_apewisdom(filter_name=args.filter, pages=args.pages)
        print(f"apewisdom: {n} mentions stored")
    elif args.source == "gdelt":
        n = pipe.run_gdelt(query=args.query, hours_back=args.hours, max_records=args.max_records)
        print(f"gdelt: {n} mentions stored")
    elif args.source == "stocktwits":
        n = pipe.run_stocktwits(ticker=args.ticker)
        print(f"stocktwits[{args.ticker}]: {n} mentions stored")
    else:
        print(f"unknown source: {args.source}", file=sys.stderr)
        return 2
    return 0


def cmd_anomalies(args: argparse.Namespace) -> int:
    pipe = Pipeline.build()
    params = AnomalyParams(halflife_days=args.halflife, z_thresh=args.z, min_periods=args.min_periods)
    df = pipe.detect_anomalies(args.ticker, params=params)
    if df.empty:
        print(f"no mentions for {args.ticker}")
        return 0
    print(df.tail(args.tail).to_string())
    flagged = df[df["anomaly"]]
    print(f"\nflagged: {len(flagged)} days (z > {args.z})")
    if not flagged.empty:
        print(flagged.tail(20).to_string())
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    signals = pd.read_csv(args.signals)
    if not {"ticker", "signal_date"}.issubset(signals.columns):
        print("signals.csv must have columns: ticker, signal_date", file=sys.stderr)
        return 2
    params = EventStudyParams(pre_days=args.pre, post_days=args.post, benchmark=args.benchmark)
    result = event_study(signals, params)
    if result.empty:
        print("no valid events")
        return 0
    print(result.to_string(index=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="social_arb", description="Social arbitrage pipeline")
    p.add_argument("--verbose", "-v", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    pu = sub.add_parser("universe", help="Build or refresh the ticker universe")
    pu.add_argument("--refresh", action="store_true")
    pu.add_argument("--search", default=None)
    pu.set_defaults(func=cmd_universe)

    pc = sub.add_parser("collect", help="Run a collector")
    pc.add_argument("source", choices=["reddit", "apewisdom", "gdelt", "stocktwits"])
    pc.add_argument("--query", default=None)
    pc.add_argument("--subreddit", default=None)
    pc.add_argument("--days", type=int, default=1)
    pc.add_argument("--comments", action="store_true")
    pc.add_argument("--size", type=int, default=100)
    pc.add_argument("--filter", default="wallstreetbets")
    pc.add_argument("--pages", type=int, default=1)
    pc.add_argument("--hours", type=int, default=24)
    pc.add_argument("--max-records", dest="max_records", type=int, default=250)
    pc.add_argument("--ticker", default=None)
    pc.set_defaults(func=cmd_collect)

    pa = sub.add_parser("anomalies", help="Run anomaly detection on stored mentions")
    pa.add_argument("--ticker", required=True)
    pa.add_argument("--halflife", type=int, default=14)
    pa.add_argument("--z", type=float, default=3.0)
    pa.add_argument("--min-periods", dest="min_periods", type=int, default=7)
    pa.add_argument("--tail", type=int, default=14)
    pa.set_defaults(func=cmd_anomalies)

    pb = sub.add_parser("backtest", help="Event-study backtest")
    pb.add_argument("--signals", required=True)
    pb.add_argument("--pre", type=int, default=5)
    pb.add_argument("--post", type=int, default=20)
    pb.add_argument("--benchmark", default="SPY")
    pb.set_defaults(func=cmd_backtest)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
