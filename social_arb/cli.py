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
from .ranking import (
    CamilloParams, RankParams, bullish_ranking, camillo_ranking,
    crossover_intersect_social, rank_improvers, rank_inflecters,
    union_ranking, weekly_momentum,
)
from .technicals import (
    load_price_cache, refresh_price_cache,
    scan_technicals, scan_universe, weekly_signals,
)


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
    elif args.source == "hackernews":
        n = pipe.run_hackernews(query=args.query, hours_back=args.hours, hits=args.size)
        print(f"hackernews: {n} mentions stored")
    elif args.source == "reddit_rss":
        n = pipe.run_reddit_rss(subreddit=args.subreddit, listing=args.listing, period=args.period)
        print(f"reddit_rss r/{args.subreddit}: {n} mentions stored")
    elif args.source == "yfinance_news":
        n = pipe.run_yfinance_news(ticker=args.ticker)
        print(f"yfinance_news[{args.ticker}]: {n} mentions stored")
    elif args.source == "wikipedia":
        n = pipe.run_wikipedia(title=args.query, ticker=args.ticker, days_back=args.days * 1)
        print(f"wikipedia[{args.query} -> {args.ticker}]: {n} rows stored")
    elif args.source == "form4":
        n = pipe.run_form4(days_back=args.days, max_records=args.max_records)
        print(f"sec_form4: {n} ticker-rows stored")
    else:
        print(f"unknown source: {args.source}", file=sys.stderr)
        return 2
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    cfg = Config()
    if args.mode == "bullish":
        params = RankParams(
            min_total_mentions=args.min_total,
            halflife_days=args.halflife,
            window_days=args.window,
        )
        out = bullish_ranking(cfg, params=params, top=args.top)
    else:
        out = weekly_momentum(cfg, min_total=args.min_total, top=args.top)
    if out.empty:
        print("no data -- run a collector first")
        return 0
    print(out.to_string(index=False))
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


def cmd_technicals(args: argparse.Namespace) -> int:
    cfg = Config()
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    else:
        # Fall back to whatever has social mentions, intersected with the
        # universe to skip private/delisted tickers.
        pipe = Pipeline.build()
        from . import storage
        tickers = storage.all_tickers(cfg)
        uni = set(pipe.universe_df["symbol"].astype(str).tolist())
        tickers = [t for t in tickers if t in uni][: args.top]
    if args.detail:
        df = weekly_signals(args.detail.upper(), years=args.years)
        if df.empty:
            print(f"no data for {args.detail}")
            return 0
        print(df.tail(args.tail).to_string())
        return 0
    snap = scan_technicals(tickers, years=args.years)
    if snap.empty:
        print("no data")
        return 0
    if args.filter:
        snap = snap[snap["signal"].str.contains(args.filter, na=False) | (snap["state"] == args.filter)]
    snap = snap.sort_values(["state", "hma_slope_20w"], ascending=[True, False])
    print(snap.to_string(index=False))
    return 0


def cmd_camillo(args: argparse.Namespace) -> int:
    """Camillo composite ranking: attention + sentiment + tech + not-stretched."""
    cfg = Config()
    from . import universe as uni_mod
    from .technicals import load_price_cache
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()

    # Coverage report -- be explicit about what's tradeable vs stale.
    cache = load_price_cache(cfg)
    if cache.empty:
        print("no price cache; run `scan --refresh` first")
        return 0
    valid_in_cache = {c for c in cache.columns if cache[c].notna().sum() >= 42}
    scannable = set(tickers) & valid_in_cache
    missing = set(tickers) - valid_in_cache
    # Reasons a ticker can be in financedatabase but not in our cache:
    # delisted, acquired, recently renamed (e.g. VIAC -> PARA), recent IPO
    # with <42 weeks of history, or SPAC remnant. None of these are
    # tradeable in the sense Camillo's framework cares about.
    pct = 100.0 * len(scannable) / max(1, len(tickers))
    print(
        f"coverage: scanning {len(scannable):,} of {len(tickers):,} "
        f"US-liquid tickers in financedatabase ({pct:.1f}%)"
    )
    print(
        f"  {len(missing):,} not in cache (delisted/acquired/SPAC remnant/"
        f"recent IPO without 42w history -- not actionable)"
    )

    snap = scan_universe(cfg, tickers, years=args.years, use_cache=True, lookback_weeks=args.lookback)
    if snap.empty:
        print("no cached technical data; run `scan --refresh` first")
        return 0
    print(f"scan produced signals for {len(snap):,} tickers")
    out = camillo_ranking(cfg, snap, min_total_mentions=args.min_total, top=args.top)
    if out.empty:
        # No technical-tier hit -- fall back to social-only bullish ranking so
        # we never silently return nothing.
        from .ranking import bullish_ranking
        soc = bullish_ranking(cfg, top=args.top)
        if soc.empty:
            print("no intersection and no social data either")
            return 0
        print("\nNo socially-mentioned tickers passed the technical filter.")
        print("Falling back to pure-social bullish ranking:\n")
        print(soc.to_string(index=False))
        return 0
    print()
    print(out.to_string(index=False))
    return 0


def cmd_union(args: argparse.Namespace) -> int:
    """Confluence ranking: names appearing in multiple Camillo views."""
    cfg = Config()
    from . import universe as uni_mod
    from .technicals import load_price_cache
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    cache = load_price_cache(cfg)
    valid = {c for c in cache.columns if cache[c].notna().sum() >= 42}
    scannable = set(tickers) & valid
    pct = 100.0 * len(scannable) / max(1, len(tickers))
    print(f"coverage: {len(scannable):,} of {len(tickers):,} US-liquid ({pct:.1f}%)")
    out = union_ranking(cfg, tickers, top_each=args.top_each, weeks=args.weeks,
                       short=args.short, long=args.long, min_score_now=args.min_score)
    if out.empty:
        print("no data")
        return 0
    if args.min_confluence > 1:
        out = out[out["confluence"] >= args.min_confluence]
    print()
    print(out.head(args.top).to_string(index=False))
    return 0


def cmd_improvers(args: argparse.Namespace) -> int:
    """Tickers whose technical Camillo score has improved over N weeks."""
    cfg = Config()
    from . import universe as uni_mod
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    out = rank_improvers(cfg, tickers, lookback_weeks=args.weeks, top=args.top,
                        min_score_now=args.min_score)
    if out.empty:
        print("no data; run `scan --refresh` first")
        return 0
    if args.min_mentions:
        out = out[out["mentions"] >= args.min_mentions]
    print(out.to_string(index=False))
    return 0


def cmd_inflecters(args: argparse.Namespace) -> int:
    """Tickers whose technical Camillo score is accelerating."""
    cfg = Config()
    from . import universe as uni_mod
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    out = rank_inflecters(cfg, tickers, short=args.short, long=args.long,
                         top=args.top, min_score_now=args.min_score)
    if out.empty:
        print("no data; run `scan --refresh` first")
        return 0
    if args.min_mentions:
        out = out[out["mentions"] >= args.min_mentions]
    print(out.to_string(index=False))
    return 0


def cmd_crossovers_social(args: argparse.Namespace) -> int:
    """Intersect a broad universe technical scan with stored social mentions."""
    cfg = Config()
    from . import universe as uni_mod
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    if args.limit:
        tickers = tickers[: args.limit]
    snap = scan_universe(cfg, tickers, years=args.years, use_cache=True, lookback_weeks=args.lookback)
    if snap.empty:
        print("no cached technical data; run `scan --refresh` first")
        return 0
    out = crossover_intersect_social(
        cfg, snap, min_total_mentions=args.min_total,
    )
    if out.empty:
        print("no intersection between socially-mentioned tickers and bullish technical state")
        return 0
    cols = ["ticker", "total_mentions", "sentiment_mean", "close", "close_vs_sma40_pct",
            "state", "weeks_in_state", "signal", "hma_slope_20w"]
    cols = [c for c in cols if c in out.columns]
    print(out[cols].head(args.top).to_string(index=False))
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    """Broad universe scan for fresh crossovers."""
    cfg = Config()
    from . import universe as uni_mod
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    if args.limit:
        tickers = tickers[: args.limit]
    print(f"scanning {len(tickers)} tickers (cache={'yes' if not args.refresh else 'refresh'})")
    if args.refresh:
        refresh_price_cache(cfg, tickers, years=args.years)
    snap = scan_universe(cfg, tickers, years=args.years, use_cache=not args.refresh, lookback_weeks=args.lookback)
    if snap.empty:
        print("no data")
        return 0
    # Liquidity floor: drop sub-$2 close (penny stocks have meaningless MAs).
    snap = snap[snap["close"] >= args.min_close]
    if args.signal:
        snap = snap[snap["signal"].fillna("").str.contains(args.signal)]
    if args.state:
        snap = snap[snap["state"] == args.state]
    if args.max_above_sma40 is not None:
        snap = snap[snap["close_vs_sma40_pct"].fillna(1e9) <= args.max_above_sma40]
    snap = snap.sort_values(
        ["signal", "hma_slope_20w"], ascending=[True, False]
    ).reset_index(drop=True)
    print(f"\n{len(snap)} matches")
    print(snap.head(args.top).to_string(index=False))

    # If no explicit filter was set, summarize counts by signal/state.
    if not (args.signal or args.state):
        print("\n=== Signal counts ===")
        print(snap["signal"].value_counts().to_string())
        print("\n=== State counts ===")
        print(snap["state"].value_counts().to_string())
    return 0


def cmd_combined(args: argparse.Namespace) -> int:
    """Cross-join social bullish ranking with technical scan."""
    cfg = Config()
    pipe = Pipeline.build()
    soc = bullish_ranking(cfg, top=args.top)
    if soc.empty:
        print("no social data")
        return 0
    uni = set(pipe.universe_df["symbol"].astype(str).tolist())
    tickers = [t for t in soc["ticker"].tolist() if t in uni]
    tech = scan_technicals(tickers, years=args.years)
    if tech.empty:
        print(soc.to_string(index=False))
        return 0
    merged = soc.merge(tech, on="ticker", how="left")
    bullish_states = {"golden", "hma_up"}
    merged["aligned"] = merged["state"].isin(bullish_states) & (merged["bullish_score"] > 1.0)
    print(merged.to_string(index=False))
    print()
    aligned = merged[merged["aligned"]].sort_values("bullish_score", ascending=False)
    if not aligned.empty:
        print("=== Aligned (social bullish AND price trend up) ===")
        print(aligned[["ticker", "bullish_score", "latest_z", "state", "weeks_in_state", "signal", "close_vs_sma40_pct"]].to_string(index=False))
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
    pc.add_argument("source", choices=[
        "reddit", "apewisdom", "gdelt", "stocktwits",
        "hackernews", "reddit_rss", "yfinance_news", "wikipedia", "form4",
    ])
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
    pc.add_argument("--listing", default="new", choices=["new", "hot", "top"])
    pc.add_argument("--period", default=None, choices=[None, "hour", "day", "week", "month", "year", "all"])
    pc.set_defaults(func=cmd_collect)

    pr = sub.add_parser("rank", help="Cross-ticker bullishness / momentum ranking")
    pr.add_argument("mode", choices=["bullish", "momentum"], default="bullish")
    pr.add_argument("--top", type=int, default=25)
    pr.add_argument("--min-total", dest="min_total", type=int, default=20)
    pr.add_argument("--halflife", type=int, default=14)
    pr.add_argument("--window", type=int, default=90)
    pr.set_defaults(func=cmd_rank)

    pa = sub.add_parser("anomalies", help="Run anomaly detection on stored mentions")
    pa.add_argument("--ticker", required=True)
    pa.add_argument("--halflife", type=int, default=14)
    pa.add_argument("--z", type=float, default=3.0)
    pa.add_argument("--min-periods", dest="min_periods", type=int, default=7)
    pa.add_argument("--tail", type=int, default=14)
    pa.set_defaults(func=cmd_anomalies)

    pt = sub.add_parser("technicals", help="Weekly MA crossover + Hull MA scan")
    pt.add_argument("--tickers", default=None, help="comma-separated; default = stored mentions")
    pt.add_argument("--top", type=int, default=50)
    pt.add_argument("--years", type=int, default=5)
    pt.add_argument("--filter", default=None, help="state or signal substring filter")
    pt.add_argument("--detail", default=None, help="single ticker -> full weekly history")
    pt.add_argument("--tail", type=int, default=12)
    pt.set_defaults(func=cmd_technicals)

    po = sub.add_parser("combined", help="Cross-join social bullish ranking with technical scan")
    po.add_argument("--top", type=int, default=30)
    po.add_argument("--years", type=int, default=5)
    po.set_defaults(func=cmd_combined)

    ps = sub.add_parser("scan", help="Broad US-equity weekly crossover scan with parquet cache")
    ps.add_argument("--top", type=int, default=50)
    ps.add_argument("--years", type=int, default=5)
    ps.add_argument("--limit", type=int, default=None, help="cap universe size for speed")
    ps.add_argument("--lookback", type=int, default=4, help="weeks to look back for a 'recent' signal")
    ps.add_argument("--min-close", dest="min_close", type=float, default=2.0)
    ps.add_argument("--max-above-sma40", dest="max_above_sma40", type=float, default=None,
                    help="filter out tickers more than N%% above 40w SMA (avoids late chases)")
    ps.add_argument("--signal", default=None, help="filter by signal substring")
    ps.add_argument("--state", default=None, choices=["golden", "death", "hma_up", "hma_down", "mixed", "warmup"])
    ps.add_argument("--refresh", action="store_true", help="re-download price cache")
    ps.add_argument("--consumer", action="store_true", help="restrict to consumer + comms sectors")
    ps.set_defaults(func=cmd_scan)

    pcam = sub.add_parser("camillo", help="Camillo composite: attention + sentiment + tech + not-stretched")
    pcam.add_argument("--top", type=int, default=30)
    pcam.add_argument("--years", type=int, default=4)
    pcam.add_argument("--lookback", type=int, default=4)
    pcam.add_argument("--min-total", dest="min_total", type=int, default=5)
    pcam.add_argument("--consumer", action="store_true")
    pcam.set_defaults(func=cmd_camillo)

    pun = sub.add_parser("union", help="Confluence ranking across Camillo views")
    pun.add_argument("--top", type=int, default=40)
    pun.add_argument("--top-each", dest="top_each", type=int, default=50)
    pun.add_argument("--weeks", type=int, default=4)
    pun.add_argument("--short", type=int, default=4)
    pun.add_argument("--long", type=int, default=8)
    pun.add_argument("--min-score", dest="min_score", type=float, default=1.0)
    pun.add_argument("--min-confluence", dest="min_confluence", type=int, default=1)
    pun.add_argument("--consumer", action="store_true")
    pun.set_defaults(func=cmd_union)

    pimp = sub.add_parser("improvers", help="Technical-score improvers over N weeks")
    pimp.add_argument("--top", type=int, default=30)
    pimp.add_argument("--weeks", type=int, default=4)
    pimp.add_argument("--min-score", dest="min_score", type=float, default=None)
    pimp.add_argument("--min-mentions", dest="min_mentions", type=int, default=0)
    pimp.add_argument("--consumer", action="store_true")
    pimp.set_defaults(func=cmd_improvers)

    pinf = sub.add_parser("inflecters", help="Tickers whose technical score is accelerating")
    pinf.add_argument("--top", type=int, default=30)
    pinf.add_argument("--short", type=int, default=4, help="recent window")
    pinf.add_argument("--long", type=int, default=8, help="prior window")
    pinf.add_argument("--min-score", dest="min_score", type=float, default=None)
    pinf.add_argument("--min-mentions", dest="min_mentions", type=int, default=0)
    pinf.add_argument("--consumer", action="store_true")
    pinf.set_defaults(func=cmd_inflecters)

    pxs = sub.add_parser("crossovers-social", help="Crossovers filtered to socially-mentioned tickers")
    pxs.add_argument("--top", type=int, default=40)
    pxs.add_argument("--years", type=int, default=4)
    pxs.add_argument("--lookback", type=int, default=4)
    pxs.add_argument("--limit", type=int, default=None)
    pxs.add_argument("--min-total", dest="min_total", type=int, default=5)
    pxs.add_argument("--consumer", action="store_true")
    pxs.set_defaults(func=cmd_crossovers_social)

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
