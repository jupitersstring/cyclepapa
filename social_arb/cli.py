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
    CamilloParams, RankParams, asymmetric_setups, best_today, bullish_leaderboard,
    bullish_ranking, camillo_ranking, camillo_social_first,
    crossover_intersect_social, pure_social_momentum, rank_improvers,
    rank_inflecters, sentiment_ema_history, sentiment_ema_history_weekly,
    sentiment_momentum_scan, sentiment_momentum_scan_weekly,
    small_mid_cap_asymmetric, social_asymmetric_setups,
    mention_spike_vs_price, momentum_acceleration_rank, ordinal_social_rank,
    early_stage_momentum,
    recent_spike_rank, rising_mentions_flat_price, social_price_divergence,
    social_signal_score,
    social_weekly_history, social_weekly_movers, social_weekly_pivot,
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


def cmd_divergence(args: argparse.Namespace) -> int:
    """Rank tickers by positive social-vs-price divergence."""
    cfg = Config()
    out = social_price_divergence(
        cfg, top=args.top, lookback_weeks=args.lookback,
        min_mentions_per_week=args.min_mentions_per_week,
        min_total_mentions=args.min_total,
        require_positive=not args.allow_negative,
    )
    if out.empty:
        print("no candidates")
        return 0
    print(out.to_string(index=False))
    return 0


def cmd_plot(args: argparse.Namespace) -> int:
    """Generate per-ticker plot panels (price + smoothed social with EMAs)."""
    from .plots import plot_many
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    paths = plot_many(
        tickers, short=args.short, long=args.long, months=args.months,
        min_periods_ratio=args.min_periods,
    )
    for p in paths:
        print(p)
    return 0


def cmd_changepoints(args: argparse.Namespace) -> int:
    """Detect structural change-points in social signals via ruptures."""
    from .changepoint import scan_tickers_for_changes
    cfg = Config()
    out = scan_tickers_for_changes(
        cfg, method=args.method, penalty=args.penalty,
        min_total_mentions=args.min_total, top_recent=args.top,
    )
    if out.empty:
        print("no change-points; install `ruptures` or lower --min-total")
        return 0
    import pandas as pd
    pd.set_option("display.max_rows", 60)
    pd.set_option("display.width", 200)
    print(out.to_string(index=False))
    return 0


def cmd_bot_filter(args: argparse.Namespace) -> int:
    """Score every mention for bot-likeness and optionally apply filter."""
    from . import storage
    from .bot_filter import score_bots, BotFilterParams
    cfg = Config()
    with storage.connect(cfg) as con:
        df = con.execute("SELECT * FROM mentions").df()
    if df.empty:
        print("no mentions")
        return 0
    scored = score_bots(df, BotFilterParams(
        max_posts_per_day=args.max_per_day,
        dup_text_threshold=args.dup_threshold,
    ))
    counts = scored["bot_score"].describe()
    print("bot_score distribution across full mention store:")
    print(counts.round(3).to_string())
    bot_mask = scored["bot_score"] >= 0.5
    print(f"\nrows with bot_score >= 0.5: {int(bot_mask.sum()):,} / {len(scored):,}")
    print("\nTop-suspicious authors by row count:")
    sus = scored[bot_mask].groupby("author").size().sort_values(ascending=False).head(15)
    print(sus.to_string())
    return 0


def cmd_pit_snapshot(args: argparse.Namespace) -> int:
    """Snapshot IWV (Russell 3000 ETF) constituents to data/universe_pit/."""
    from .universe_pit import save_constituents_snapshot
    cfg = Config()
    path = save_constituents_snapshot(cfg)
    if path is None:
        print("snapshot failed")
        return 1
    print(f"snapshot saved: {path}")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """Pipeline health & coverage audit."""
    from .health import collect as _hc
    rep = _hc(Config())
    print(rep.to_text())
    return 0


def cmd_daily_refresh(args: argparse.Namespace) -> int:
    """Bulk-refresh daily price cache for the US-liquid (or consumer) slice."""
    cfg = Config()
    from . import universe as uni_mod
    from .technicals_daily import refresh_daily_cache
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    if args.north_america:
        uni = uni_mod.filter_north_american_liquid(uni)
    else:
        uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    if args.limit:
        tickers = tickers[: args.limit]
    refresh_daily_cache(cfg, tickers, years=args.years, chunk=args.chunk)
    return 0


def cmd_daily_scan(args: argparse.Namespace) -> int:
    """Latest daily-indicator snapshot for a universe."""
    cfg = Config()
    from . import universe as uni_mod
    from .technicals_daily import scan_daily_universe
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    out = scan_daily_universe(cfg, tickers)
    if out.empty:
        print("no daily cache; run `daily-refresh` first")
        return 0
    if args.rsi_max is not None:
        out = out[out["rsi_14"].fillna(100) <= args.rsi_max]
    if args.rsi_min is not None:
        out = out[out["rsi_14"].fillna(0) >= args.rsi_min]
    if args.vol_z_min is not None:
        out = out[out["vol_z_30"].fillna(-99) >= args.vol_z_min]
    if args.near_52w_low:
        out = out[out["pct_from_52w_low"].fillna(99) <= args.near_52w_low]
    out = out.sort_values("vol_z_30", ascending=False).head(args.top)
    print(out.to_string(index=False))
    return 0


def cmd_finviz(args: argparse.Namespace) -> int:
    """Fetch Finviz fundamentals + insider for a list of tickers."""
    from .collectors.finviz import collect_finviz_batch
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    df = collect_finviz_batch(tickers, sleep_between=args.sleep)
    if df.empty:
        print("no data")
        return 0
    cols = [
        "ticker", "market_cap", "pe", "short_float_pct", "insider_trans_pct",
        "inst_trans_pct", "perf_month_pct", "perf_quarter_pct",
        "high_52w_pct", "low_52w_pct", "rsi_14", "earnings_date", "sector", "industry",
    ]
    cols = [c for c in cols if c in df.columns]
    print(df[cols].to_string(index=False))
    return 0


def cmd_leaderboard(args: argparse.Namespace) -> int:
    """Top N most-bullish names under EACH bullish measure + a composite."""
    cfg = Config()
    out = bullish_leaderboard(cfg, top=args.top, min_mentions=args.min_mentions)
    if not out or all(v.empty for v in out.values()):
        print("no data; run collectors first")
        return 0
    for name, df in out.items():
        if df.empty:
            continue
        print(f"\n=== TOP {len(df)} :: {name} ===")
        # Cap printed width.
        print(df.to_string(index=False))
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    """Run historic backfills of free sources that support time-window queries."""
    cfg = Config()
    pipe = Pipeline.build(cfg)
    if args.source == "hackernews":
        from .collectors.hackernews import backfill_hackernews
        from . import storage
        queries = (args.queries.split(",") if args.queries else [
            "NVIDIA", "Tesla", "Apple", "Palantir", "Crocs", "Celsius",
            "Mattel", "Stanley tumbler", "Hoka", "Cheesecake Factory",
        ])
        total = 0
        for q in queries:
            df = backfill_hackernews(
                cfg, pipe.resolver, pipe.sentiment,
                query=q.strip(), days_back=args.days, chunk_days=args.chunk,
            )
            total += storage.upsert_mentions(cfg, df)
        print(f"hn backfill: {total} mentions stored")
    elif args.source == "wikipedia":
        # Sweep Wikipedia pageviews over a long horizon.
        titles = (args.queries.split(",") if args.queries else [
            "Mattel", "Crocs", "Celsius_Holdings", "Deckers_Outdoor_Corporation",
            "Nvidia", "GameStop", "Lululemon_Athletica", "Newell_Brands",
            "Under_Armour", "Tapestry,_Inc.", "Build-A-Bear_Workshop",
            "Vital_Farms", "TripAdvisor",
        ])
        # Best-effort title -> ticker map; users should edit aliases.csv.
        title_to_ticker = {
            "Mattel": "MAT", "Crocs": "CROX", "Celsius_Holdings": "CELH",
            "Deckers_Outdoor_Corporation": "DECK", "Nvidia": "NVDA",
            "GameStop": "GME", "Lululemon_Athletica": "LULU",
            "Newell_Brands": "NWL", "Under_Armour": "UAA",
            "Tapestry,_Inc.": "TPR", "Build-A-Bear_Workshop": "BBW",
            "Vital_Farms": "VITL", "TripAdvisor": "TRIP",
        }
        total = 0
        for t in titles:
            t = t.strip()
            ticker = title_to_ticker.get(t, t.upper())
            total += pipe.run_wikipedia(title=t, ticker=ticker, days_back=args.days)
        print(f"wikipedia backfill ({args.days}d): {total} rows stored")
    elif args.source == "bluesky":
        from .collectors.bluesky import collect_bluesky
        from . import storage
        queries = (args.queries.split(",") if args.queries else [
            "$NVDA", "$CELH", "$NWL", "Crocs", "Stanley tumbler", "TripAdvisor",
            "Allbirds", "Birkenstock", "Cheesecake Factory", "Build-A-Bear",
        ])
        total = 0
        for q in queries:
            df = collect_bluesky(cfg, pipe.resolver, pipe.sentiment,
                               query=q.strip(), hours_back=args.hours, limit=100)
            total += storage.upsert_mentions(cfg, df)
        print(f"bluesky: {total} mentions stored")
    elif args.source == "openinsider":
        from .collectors.openinsider import collect_openinsider_cluster_buys
        from . import storage
        df = collect_openinsider_cluster_buys(cfg)
        n = storage.upsert_mentions(cfg, df)
        print(f"openinsider cluster buys: {n} mentions stored")
    elif args.source == "google-trends":
        from .collectors.google_trends import collect_google_trends
        from . import storage
        # Default Camillo-archetype list with brand-query for the
        # consumer-attention layer (not just $TICKER).
        targets = (args.queries.split(",") if args.queries else None) or [
            "CELH:Celsius Holdings:Celsius energy drink",
            "NWL:Newell Brands:Sharpie",
            "MAT:Mattel:Barbie",
            "CROX:Crocs",
            "DECK:Deckers Outdoor:Hoka",
            "TPR:Tapestry:Coach handbag",
            "BBW:Build-A-Bear:Build-A-Bear",
            "VITL:Vital Farms:Vital Farms eggs",
            "TRIP:TripAdvisor",
            "NVDA:NVIDIA",
            "GME:GameStop",
            "LULU:Lululemon",
            "UAA:Under Armour",
            "BIRD:Allbirds",
        ]
        total = 0
        for spec in targets:
            parts = [p.strip() for p in spec.split(":") if p.strip()]
            ticker = parts[0]
            company = parts[1] if len(parts) > 1 else None
            brand = parts[2] if len(parts) > 2 else None
            df = collect_google_trends(
                cfg, ticker=ticker, company_name=company, brand_query=brand,
                timeframe=args.timeframe,
            )
            total += storage.upsert_mentions(cfg, df)
        print(f"google_trends ({args.timeframe}): {total} rows stored")
    elif args.source == "brave-search":
        from .collectors.brave_search import collect_brave_search_attention
        from . import storage
        tickers = (args.queries.split(",") if args.queries else None) or [
            "CELH", "NWL", "MAT", "CROX", "DECK", "TPR", "BBW", "VITL",
            "TRIP", "NVDA", "GME", "LULU", "UAA", "BIRD",
        ]
        total = 0
        for t in tickers:
            df = collect_brave_search_attention(cfg, ticker=t.strip())
            total += storage.upsert_mentions(cfg, df)
        print(f"brave_search: {total} rows stored")
    elif args.source == "nitter":
        from .collectors.nitter import collect_nitter
        from . import storage
        queries = (args.queries.split(",") if args.queries else None) or [
            "$CELH", "$NVDA", "$NWL", "$TRIP", "$DECK", "$BBW", "$VITL",
            "Crocs review", "Build-A-Bear", "Stanley tumbler",
        ]
        total = 0
        for q in queries:
            df = collect_nitter(cfg, pipe.resolver, pipe.sentiment,
                               query=q.strip(), max_tweets=100)
            total += storage.upsert_mentions(cfg, df)
        print(f"nitter (X via mirrors): {total} mentions stored")
    elif args.source == "youtube":
        from .collectors.youtube_comments import collect_search_videos
        from . import storage
        targets = (args.queries.split(",") if args.queries else None) or [
            "Celsius energy drink review:CELH",
            "Stanley tumbler review:ELUX-B.ST",
            "Crocs unboxing:CROX",
            "Allbirds review:BIRD",
            "Birkenstock review:BIRK",
            "Build-A-Bear:BBW",
            "Vital Farms eggs:VITL",
        ]
        total = 0
        for spec in targets:
            parts = spec.split(":")
            query = parts[0].strip()
            ticker = parts[1].strip() if len(parts) > 1 else None
            df = collect_search_videos(
                cfg, pipe.resolver, pipe.sentiment,
                query=query, ticker_hint=ticker,
                max_videos=3, max_comments_per_video=80,
            )
            total += storage.upsert_mentions(cfg, df)
        print(f"youtube comments: {total} mentions stored")
    elif args.source == "mastodon":
        from .collectors.mastodon import collect_mastodon
        from . import storage
        queries = (args.queries.split(",") if args.queries else None) or [
            "$CELH", "$NVDA", "$NWL", "Celsius drink", "Crocs",
            "Build-A-Bear", "Stanley tumbler",
        ]
        total = 0
        for q in queries:
            df = collect_mastodon(cfg, pipe.resolver, pipe.sentiment,
                                  query=q.strip(), limit=40)
            total += storage.upsert_mentions(cfg, df)
        print(f"mastodon: {total} mentions stored")
    elif args.source == "twitter":
        from .collectors.twitter_twikit import collect_twitter
        from . import storage
        queries = (args.queries.split(",") if args.queries else None) or [
            "$CELH", "$NVDA", "$NWL", "$TRIP", "$DECK",
        ]
        total = 0
        for q in queries:
            df = collect_twitter(cfg, pipe.resolver, pipe.sentiment,
                                 query=q.strip(), count=100)
            total += storage.upsert_mentions(cfg, df)
        print(f"twitter (twikit): {total} mentions stored")
    elif args.source == "telegram":
        from .collectors.telegram import collect_telegram
        from . import storage
        channels = (args.queries.split(",") if args.queries else None) or [
            "@WSBchatter", "@CryptoNewsPlus", "@stocktitan",
            "@finance_news_eng",
        ]
        df = collect_telegram(cfg, pipe.resolver, pipe.sentiment,
                              channels=[c.strip() for c in channels],
                              limit_per_channel=300)
        n = storage.upsert_mentions(cfg, df)
        print(f"telegram: {n} mentions stored")
    elif args.source == "tiktok":
        from .collectors.tiktok_creative import collect_tiktok_hashtags_as_mentions
        from . import storage
        hashtag_to_ticker = {
            "celsius": "CELH",
            "celsiusdrink": "CELH",
            "stanleycup": "ELUX-B.ST",
            "stanleytumbler": "ELUX-B.ST",
            "crocs": "CROX",
            "ugg": "DECK",
            "hoka": "DECK",
            "birkenstock": "BIRK",
            "lululemon": "LULU",
            "allbirds": "BIRD",
            "buildabear": "BBW",
            "vitalfarms": "VITL",
            "nvidia": "NVDA",
        }
        if args.queries:
            hashtag_to_ticker = dict(
                tuple(kv.split(":")) for kv in args.queries.split(",") if ":" in kv
            )
        df = collect_tiktok_hashtags_as_mentions(cfg, hashtag_to_ticker)
        n = storage.upsert_mentions(cfg, df)
        print(f"tiktok creative center: {n} rows stored")
    elif args.source == "google-play":
        from .collectors.app_stores import collect_app_signals
        from . import storage
        app_to_ticker = {
            "com.celsius.celsius": "CELH",
            "com.crocs.android": "CROX",
            "com.lululemon.app": "LULU",
            "com.tripadvisor.tripadvisor": "TRIP",
            "com.starbucks.mobilecard": "SBUX",
            "com.robinhood.android": "HOOD",
            "com.cheesecakefactory.app": "CAKE",
            "com.dutchbros.app": "BROS",
            "com.gap.gap": "GPS",
        }
        if args.queries:
            app_to_ticker = dict(
                tuple(kv.split(":")) for kv in args.queries.split(",") if ":" in kv
            )
        df = collect_app_signals(cfg, app_to_ticker, reviews_per_app=50)
        n = storage.upsert_mentions(cfg, df)
        print(f"google_play: {n} rows stored")
    elif args.source == "jobs":
        from .collectors.job_postings import collect_job_postings
        from . import storage
        ticker_to_board = {
            "CELH": ("greenhouse", "celsius"),
            "FTDR": ("greenhouse", "frontdoor"),
            "CROX": ("greenhouse", "crocs"),
            "HOOD": ("greenhouse", "robinhood"),
            "DECK": ("greenhouse", "deckersbrands"),
            "BBW": ("greenhouse", "buildabear"),
            "VITL": ("greenhouse", "vitalfarms"),
            "TRIP": ("greenhouse", "tripadvisor"),
            "GPS": ("greenhouse", "gapinc"),
        }
        if args.queries:
            ticker_to_board = {}
            for kv in args.queries.split(","):
                parts = kv.split(":")
                if len(parts) == 3:
                    ticker_to_board[parts[0]] = (parts[1], parts[2])
        df = collect_job_postings(cfg, ticker_to_board)
        n = storage.upsert_mentions(cfg, df)
        print(f"job_postings: {n} rows stored")
    elif args.source == "capitol":
        from .collectors.capitol_trades import collect_capitol_trades
        from . import storage
        df = collect_capitol_trades(cfg, days_back=args.days)
        n = storage.upsert_mentions(cfg, df)
        print(f"capitol_trades: {n} filings stored")
    elif args.source == "patents":
        from .collectors.uspto import collect_patents
        from . import storage
        assignee_to_ticker = {
            "Mattel, Inc.": "MAT",
            "Crocs, Inc.": "CROX",
            "Newell Brands": "NWL",
            "Nvidia Corporation": "NVDA",
            "Deckers Outdoor Corporation": "DECK",
        }
        if args.queries:
            assignee_to_ticker = dict(
                tuple(kv.split(":")) for kv in args.queries.split(",") if ":" in kv
            )
        df = collect_patents(cfg, assignee_to_ticker)
        n = storage.upsert_mentions(cfg, df)
        print(f"uspto patents: {n} rows stored")
    elif args.source == "rss":
        from .collectors.rss_news import collect_rss_for_ticker
        from . import storage
        tickers = (args.queries.split(",") if args.queries else None) or [
            "CELH", "NVDA", "NWL", "TRIP", "DECK", "BBW", "VITL",
        ]
        total = 0
        for t in tickers:
            df = collect_rss_for_ticker(cfg, pipe.sentiment,
                                         ticker=t.strip(), fetch_bodies=args.fetch_bodies)
            total += storage.upsert_mentions(cfg, df)
        print(f"rss news: {total} rows stored")
    else:
        print(f"unknown source: {args.source}", file=sys.stderr)
        return 2
    return 0


def cmd_sentiment_momentum(args: argparse.Namespace) -> int:
    """Sentiment-EMA momentum scan.

    Daily sentiment time series per ticker, EMA(short) vs EMA(long), with
    bullish/bearish state plus a fresh-cross flag. Also computes the same
    EMAs on mention VOLUME so we see attention momentum independently.
    """
    cfg = Config()
    if args.ticker:
        hist = sentiment_ema_history(
            cfg, args.ticker.upper(),
            short=args.short, long=args.long, min_periods_ratio=args.min_periods,
        )
        if hist.empty:
            print(f"insufficient sentiment history for {args.ticker}")
            return 0
        print(hist.tail(args.tail).to_string())
        return 0
    out = sentiment_momentum_scan(
        cfg, top=args.top, short=args.short, long=args.long,
        min_mentions=args.min_mentions, min_periods_ratio=args.min_periods,
    )
    if out.empty:
        print(f"no candidates with enough history -- try smaller --short/--long, current ({args.short}/{args.long})")
        return 0
    print(out.to_string(index=False))
    return 0


def cmd_social_momentum(args: argparse.Namespace) -> int:
    """Pure social momentum: no price, no technicals.

    Surfaces tickers whose social conversation is accelerating, the
    bull/bear polarity is shifting positive, and new sources are picking
    up the topic. The "people are talking about it more, and more
    positively" filter.
    """
    cfg = Config()
    out = pure_social_momentum(
        cfg, top=args.top, min_mentions=args.min_mentions,
        half_life=args.halflife,
        require_positive_sentiment=args.positive_only,
    )
    if out.empty:
        print("no data; run collectors first")
        return 0
    cols_main = [
        "ticker", "social_momentum", "total_mentions", "mentions_7d", "mentions_prev7d",
        "growth_7d", "growth_3d", "inflection", "mention_z",
        "bull_7d", "bear_7d", "neutral_7d",
        "bull_minus_bear_7d", "bull_bear_delta",
        "polarity_volume_7d", "polarity_vol_growth", "polarised_share", "bull_share",
        "sentiment_7d", "sentiment_delta",
        "sources_now", "new_sources",
    ]
    cols_main = [c for c in cols_main if c in out.columns]
    print(out[cols_main].to_string(index=False))
    return 0


def cmd_social_asymmetric(args: argparse.Namespace) -> int:
    """Information-arbitrage ranker: broken price + rising social signal."""
    cfg = Config()
    from . import universe as uni_mod
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    if args.north_america:
        uni = uni_mod.filter_north_american_liquid(uni)
    else:
        uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    out = social_asymmetric_setups(
        cfg, tickers, top=args.top,
        min_mentions=args.min_mentions,
        min_upside_pct=args.min_upside,
        min_social_score=args.min_social,
        enrich_finviz=args.finviz,
    )
    if out.empty:
        print("no candidates: try lower --min-mentions or --min-social")
        return 0
    print(out.to_string(index=False))
    return 0


def cmd_rising_flat(args: argparse.Namespace) -> int:
    """Mentions rising over a window AND price essentially flat (dormant attention)."""
    cfg = Config()
    out = rising_mentions_flat_price(
        cfg, window_days=args.window, top=args.top,
        min_total_mentions=args.min_total,
        max_abs_price_pct=args.max_price_move,
        min_mention_slope=args.min_slope,
        min_r2=args.min_r2,
        require_positive_sentiment=args.positive_sentiment,
    )
    if out.empty:
        print("no candidates; widen --max-price-move or lower --min-slope/--min-r2")
        return 0
    import pandas as pd
    pd.set_option("display.max_rows", 60)
    pd.set_option("display.width", 240)
    print(out.to_string(index=False))
    return 0


def cmd_mention_vs_price(args: argparse.Namespace) -> int:
    """Acute mention spike z minus price spike z (5d vs 30d, both windows)."""
    cfg = Config()
    out = mention_spike_vs_price(
        cfg, short_window_days=args.short, baseline_window_days=args.baseline,
        top=args.top, min_total_mentions=args.min_total,
        min_mention_spike=args.min_spike,
        require_positive_div=not args.allow_negative,
    )
    if out.empty:
        print("no candidates")
        return 0
    import pandas as pd
    pd.set_option("display.max_rows", 60)
    pd.set_option("display.width", 240)
    print(out.to_string(index=False))
    return 0


def cmd_recent_spike(args: argparse.Namespace) -> int:
    """Acute short-window spike detector: short MA vs baseline z-score."""
    cfg = Config()
    out = recent_spike_rank(
        cfg, short_window_days=args.short, baseline_window_days=args.baseline,
        top=args.top, min_total_mentions=args.min_total,
        require_positive=not args.allow_negative,
    )
    if out.empty:
        print("no candidates")
        return 0
    import pandas as pd
    pd.set_option("display.max_rows", 60)
    pd.set_option("display.width", 240)
    print(out.to_string(index=False))
    return 0


def cmd_early_stage(args: argparse.Namespace) -> int:
    """Early-stage momentum: NVDA-2023-shape, BEFORE the parabolic."""
    cfg = Config()
    from . import universe as uni_mod
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    if args.north_america:
        uni = uni_mod.filter_north_american_liquid(uni)
    else:
        uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    out = early_stage_momentum(
        cfg, tickers, top=args.top,
        social_window_days=args.window,
        min_total_mentions=args.min_total,
        max_vs_sma40_pct=args.max_vs_sma40,
        min_vs_sma40_pct=args.min_vs_sma40,
        max_weeks_in_state=args.max_weeks_in_state,
        require_positive_velocity=not args.allow_decel,
        require_positive_sentiment=not args.allow_neg_sentiment,
        enrich_finviz=args.finviz,
    )
    if out.empty:
        print("no candidates -- try widening --max-vs-sma40 or --max-weeks-in-state")
        return 0
    import pandas as pd
    pd.set_option("display.max_rows", 60)
    pd.set_option("display.width", 240)
    print(out.to_string(index=False))
    return 0


def cmd_momentum_accel(args: argparse.Namespace) -> int:
    """Cross-sectional rank by 44d social/sentiment velocity + acceleration."""
    cfg = Config()
    out = momentum_acceleration_rank(
        cfg, window_days=args.window, top=args.top,
        min_total_mentions=args.min_total,
        require_positive=not args.allow_negative,
    )
    if out.empty:
        print("no candidates")
        return 0
    import pandas as pd
    pd.set_option("display.max_rows", 60)
    pd.set_option("display.width", 240)
    print(out.to_string(index=False))
    return 0


def cmd_ordinal_rank(args: argparse.Namespace) -> int:
    """Cross-sectional ordinal rank on 44d sentiment + 14d modal mentions."""
    cfg = Config()
    out = ordinal_social_rank(
        cfg, sentiment_window_days=args.sentiment_window,
        mention_modal_window_days=args.modal_window,
        min_total_mentions=args.min_total, top=args.top,
    )
    if out.empty:
        print("no data")
        return 0
    import pandas as pd
    pd.set_option("display.max_rows", 60)
    pd.set_option("display.width", 200)
    print(out.to_string(index=False))
    return 0


def cmd_social_weekly(args: argparse.Namespace) -> int:
    """Weekly social comparisons -- WoW deltas + per-ticker history + pivot."""
    cfg = Config()
    import pandas as pd
    pd.set_option("display.max_rows", 60)
    pd.set_option("display.width", 240)

    if args.ticker:
        hist = social_weekly_history(cfg, args.ticker, weeks=args.weeks)
        if hist.empty:
            print(f"no weekly history for {args.ticker}")
            return 0
        print(f"\n=== {args.ticker.upper()} -- last {len(hist)} weeks ===")
        print(hist.to_string())
        return 0

    if args.pivot:
        wide = social_weekly_pivot(cfg, weeks=args.weeks,
                                    n_tickers=args.top, metric=args.metric)
        if wide.empty:
            print("no data")
            return 0
        print(f"\n=== Weekly pivot of {args.metric} (top {args.top}, last {args.weeks} weeks) ===")
        print(wide.to_string())
        return 0

    out = social_weekly_movers(
        cfg, top=args.top, min_mentions=args.min_mentions,
        sort_by=args.sort_by,
    )
    if out.empty:
        print("no movers; lower --min-mentions or wait for more collector runs")
        return 0
    print(f"\n=== Weekly social MOVERS (sorted by {args.sort_by}) ===")
    print(out.to_string(index=False))
    return 0


def cmd_camillo_social_first(args: argparse.Namespace) -> int:
    """Social-first Camillo: divergence + spike + small/mid-cap + asymmetric."""
    cfg = Config()
    from . import universe as uni_mod
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    if args.north_america:
        uni = uni_mod.filter_north_american_liquid(uni)
    else:
        uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    out = camillo_social_first(
        cfg, tickers, top=args.top,
        mcap_min=args.mcap_min * 1e6, mcap_max=args.mcap_max * 1e6,
        min_divergence=args.min_divergence, min_social_z=args.min_social_z,
        min_close=args.min_close,
    )
    if out.empty:
        print("no candidates matched; lower --min-divergence or --min-social-z")
        return 0
    import pandas as pd
    pd.set_option("display.max_rows", 60)
    pd.set_option("display.width", 240)
    print(out.to_string(index=False))
    return 0


def cmd_smid_asymmetric(args: argparse.Namespace) -> int:
    """Small/mid-cap-filtered asymmetric setups."""
    cfg = Config()
    from . import universe as uni_mod
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    if args.north_america:
        uni = uni_mod.filter_north_american_liquid(uni)
    else:
        uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    out = small_mid_cap_asymmetric(
        cfg, tickers,
        top=args.top, candidate_pool=args.pool, enrich_top=args.enrich,
        mcap_min=args.mcap_min * 1e6, mcap_max=args.mcap_max * 1e6,
        min_upside_pct=args.min_upside, min_asym_ratio=args.min_ratio,
        min_close=args.min_close,
    )
    if out.empty:
        print("no candidates in the small/mid-cap band; widen --mcap-min/max")
        return 0
    import pandas as pd
    pd.set_option("display.max_rows", 60)
    pd.set_option("display.width", 220)
    print(out.to_string(index=False))
    return 0


def cmd_asymmetric(args: argparse.Namespace) -> int:
    """Camillo-style asymmetric setups: limited downside, large upside."""
    cfg = Config()
    from . import universe as uni_mod
    pipe = Pipeline.build(cfg)
    uni = pipe.universe_df
    if args.consumer:
        uni = uni_mod.filter_consumer_focused(uni)
    if args.north_america:
        uni = uni_mod.filter_north_american_liquid(uni)
    else:
        uni = uni_mod.filter_us_liquid(uni)
    tickers = uni["symbol"].astype(str).tolist()
    out = asymmetric_setups(
        cfg, tickers, top=args.top,
        enrich_finviz=args.finviz,
        min_close=args.min_close,
        min_upside_pct=args.min_upside,
        min_asym_ratio=args.min_ratio,
    )
    if out.empty:
        print("no candidates")
        return 0
    print(out.to_string(index=False))
    return 0


def cmd_best_today(args: argparse.Namespace) -> int:
    """Best-today: own-history percentile + cross-section z-score."""
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
    print(f"coverage: {len(scannable):,} of {len(tickers):,} US-liquid ({100*len(scannable)/len(tickers):.1f}%)")
    out = best_today(
        cfg, tickers, top=args.top,
        short_w=args.short, long_w=args.long,
        history_lookback=args.history,
        min_score_now=args.min_score,
        min_close=args.min_close,
    )
    if out.empty:
        print("no data")
        return 0
    if args.min_mentions:
        out = out[out["mentions"] >= args.min_mentions]
    if args.max_above_sma40 is not None:
        out = out[out["vs_sma40_pct"].fillna(1e9) <= args.max_above_sma40]
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

    phc = sub.add_parser("health", help="Pipeline health & coverage audit")
    phc.set_defaults(func=cmd_health)

    pcp = sub.add_parser("changepoints",
                        help="Structural change-point detection via ruptures (CUSUM/PELT)")
    pcp.add_argument("--top", type=int, default=30)
    pcp.add_argument("--method", default="pelt", choices=["pelt", "binseg", "window"])
    pcp.add_argument("--penalty", type=float, default=5.0)
    pcp.add_argument("--min-total", dest="min_total", type=int, default=30)
    pcp.set_defaults(func=cmd_changepoints)

    pbot = sub.add_parser("bot-filter",
                        help="Score every mention for bot-likeness")
    pbot.add_argument("--max-per-day", dest="max_per_day", type=int, default=30)
    pbot.add_argument("--dup-threshold", dest="dup_threshold", type=int, default=3)
    pbot.set_defaults(func=cmd_bot_filter)

    ppit = sub.add_parser("pit-snapshot",
                        help="Snapshot iShares Russell 3000 (IWV) constituents")
    ppit.set_defaults(func=cmd_pit_snapshot)

    pdv = sub.add_parser("divergence", help="Find tickers where social leads price (information edge)")
    pdv.add_argument("--top", type=int, default=30)
    pdv.add_argument("--lookback", type=int, default=13)
    pdv.add_argument("--min-mentions-per-week", dest="min_mentions_per_week", type=float, default=2.0)
    pdv.add_argument("--min-total", dest="min_total", type=int, default=15)
    pdv.add_argument("--allow-negative", action="store_true",
                    help="don't filter out negative-divergence rows (default: positive only)")
    pdv.set_defaults(func=cmd_divergence)

    pplot = sub.add_parser("plot", help="4-panel per-ticker plots (price + mentions + sentiment + divergence)")
    pplot.add_argument("--tickers", required=True, help="comma-separated")
    pplot.add_argument("--short", type=int, default=20)
    pplot.add_argument("--long", type=int, default=50)
    pplot.add_argument("--months", type=int, default=24)
    pplot.add_argument("--min-periods", dest="min_periods", type=float, default=0.3)
    pplot.set_defaults(func=cmd_plot)

    pdr = sub.add_parser("daily-refresh", help="Bulk-download daily price cache")
    pdr.add_argument("--years", type=int, default=3)
    pdr.add_argument("--chunk", type=int, default=50)
    pdr.add_argument("--consumer", action="store_true")
    pdr.add_argument("--north-america", dest="north_america", action="store_true")
    pdr.add_argument("--limit", type=int, default=None)
    pdr.set_defaults(func=cmd_daily_refresh)

    pds = sub.add_parser("daily-scan", help="Snapshot daily indicators (RSI, vol z, 52w distance)")
    pds.add_argument("--top", type=int, default=40)
    pds.add_argument("--rsi-max", dest="rsi_max", type=float, default=None)
    pds.add_argument("--rsi-min", dest="rsi_min", type=float, default=None)
    pds.add_argument("--vol-z-min", dest="vol_z_min", type=float, default=None)
    pds.add_argument("--near-52w-low", dest="near_52w_low", type=float, default=None,
                    help="filter to names within N%% above their 52w low")
    pds.add_argument("--consumer", action="store_true")
    pds.set_defaults(func=cmd_daily_scan)

    pfv = sub.add_parser("finviz", help="Scrape Finviz fundamentals + insider for tickers")
    pfv.add_argument("--tickers", required=True, help="comma-separated")
    pfv.add_argument("--sleep", type=float, default=0.7)
    pfv.set_defaults(func=cmd_finviz)

    plb = sub.add_parser("leaderboard", help="Top N most bullish under EACH measure + composite")
    plb.add_argument("--top", type=int, default=50)
    plb.add_argument("--min-mentions", dest="min_mentions", type=int, default=5)
    plb.set_defaults(func=cmd_leaderboard)

    pbf = sub.add_parser("backfill",
                         help="Historic backfills (hn, wikipedia, bluesky, openinsider, google-trends, brave-search)")
    pbf.add_argument("source", choices=[
        "hackernews", "wikipedia", "bluesky", "openinsider",
        "google-trends", "brave-search",
        "nitter", "youtube", "mastodon", "twitter",
        "telegram", "tiktok", "google-play", "jobs",
        "capitol", "patents", "rss",
    ])
    pbf.add_argument("--fetch-bodies", dest="fetch_bodies", action="store_true",
                    help="rss-news: fetch article body via trafilatura")
    pbf.add_argument("--queries", default=None,
                    help="comma-separated query/title list; defaults to Camillo-archetype set")
    pbf.add_argument("--days", type=int, default=365, help="days of history (hn/wikipedia)")
    pbf.add_argument("--chunk", type=int, default=14, help="hn backfill chunk size in days")
    pbf.add_argument("--hours", type=int, default=72, help="bluesky lookback hours")
    pbf.add_argument("--timeframe", default="today 12-m",
                    help="google-trends timeframe (e.g. 'today 5-y', 'today 12-m', 'today 3-m')")
    pbf.set_defaults(func=cmd_backfill)

    pse = sub.add_parser("sentiment-momentum",
                         help="Sentiment-EMA momentum scan (short vs long, e.g. 20/50)")
    pse.add_argument("--top", type=int, default=25)
    pse.add_argument("--short", type=int, default=20, help="short EMA span")
    pse.add_argument("--long", type=int, default=50, help="long EMA span")
    pse.add_argument("--min-mentions", dest="min_mentions", type=int, default=5)
    pse.add_argument("--min-periods", dest="min_periods", type=float, default=0.5,
                    help="EMA min_periods as fraction of span (default 0.5)")
    pse.add_argument("--ticker", default=None, help="single ticker -> full history")
    pse.add_argument("--tail", type=int, default=30)
    pse.set_defaults(func=cmd_sentiment_momentum)

    psm = sub.add_parser("social-momentum",
                         help="Pure social momentum: mentions accelerating + bull/bear flip")
    psm.add_argument("--top", type=int, default=30)
    psm.add_argument("--min-mentions", dest="min_mentions", type=int, default=5)
    psm.add_argument("--halflife", type=int, default=14)
    psm.add_argument("--positive-only", dest="positive_only", action="store_true",
                    help="exclude tickers with net-negative last-7d sentiment")
    psm.set_defaults(func=cmd_social_momentum)

    psa = sub.add_parser("social-asymmetric",
                         help="Information arbitrage: broken price + rising social signal")
    psa.add_argument("--top", type=int, default=30)
    psa.add_argument("--min-mentions", dest="min_mentions", type=int, default=5)
    psa.add_argument("--min-upside", dest="min_upside", type=float, default=30.0)
    psa.add_argument("--min-social", dest="min_social", type=float, default=1.5)
    psa.add_argument("--finviz", type=int, default=0)
    psa.add_argument("--consumer", action="store_true")
    psa.add_argument("--north-america", dest="north_america", action="store_true")
    psa.set_defaults(func=cmd_social_asymmetric)

    prfl = sub.add_parser("rising-flat",
                        help="Mentions rising over N days AND price essentially flat")
    prfl.add_argument("--top", type=int, default=30)
    prfl.add_argument("--window", type=int, default=30, help="window length in days")
    prfl.add_argument("--max-price-move", dest="max_price_move", type=float, default=5.0,
                    help="max abs price move pct over window (default 5%%)")
    prfl.add_argument("--min-slope", dest="min_slope", type=float, default=0.05,
                    help="min mention slope mentions/day (default 0.05)")
    prfl.add_argument("--min-r2", dest="min_r2", type=float, default=0.15,
                    help="min OLS R^2 to qualify as 'trending' (default 0.15)")
    prfl.add_argument("--min-total", dest="min_total", type=int, default=15)
    prfl.add_argument("--positive-sentiment", action="store_true",
                    help="also require sentiment_mean > 0")
    prfl.set_defaults(func=cmd_rising_flat)

    pmvp = sub.add_parser("mention-vs-price",
                        help="Acute mention spike minus price spike (5d vs 30d both)")
    pmvp.add_argument("--top", type=int, default=30)
    pmvp.add_argument("--short", type=int, default=5)
    pmvp.add_argument("--baseline", type=int, default=30)
    pmvp.add_argument("--min-total", dest="min_total", type=int, default=15)
    pmvp.add_argument("--min-spike", dest="min_spike", type=float, default=1.0,
                    help="minimum mention_spike_z (default 1.0)")
    pmvp.add_argument("--allow-negative", action="store_true",
                    help="don't require positive divergence")
    pmvp.set_defaults(func=cmd_mention_vs_price)

    prs = sub.add_parser("recent-spike",
                        help="Acute short-window spike detector (5d vs 30d baseline z-score)")
    prs.add_argument("--top", type=int, default=30)
    prs.add_argument("--short", type=int, default=5, help="recent window in days")
    prs.add_argument("--baseline", type=int, default=30, help="trailing baseline window in days")
    prs.add_argument("--min-total", dest="min_total", type=int, default=15)
    prs.add_argument("--allow-negative", action="store_true",
                    help="don't require positive mention spike (default: positive only)")
    prs.set_defaults(func=cmd_recent_spike)

    pes = sub.add_parser("early-stage",
                        help="Early-stage momentum: NVDA-2023 shape, social accelerating but price not yet stretched")
    pes.add_argument("--top", type=int, default=20)
    pes.add_argument("--window", type=int, default=44)
    pes.add_argument("--min-total", dest="min_total", type=int, default=30)
    pes.add_argument("--max-vs-sma40", dest="max_vs_sma40", type=float, default=20.0,
                    help="max %% above 40w SMA -- keep names not yet stretched (default 20)")
    pes.add_argument("--min-vs-sma40", dest="min_vs_sma40", type=float, default=-15.0,
                    help="min %% above 40w SMA -- exclude too-broken names (default -15)")
    pes.add_argument("--max-weeks-in-state", dest="max_weeks_in_state", type=int, default=12,
                    help="max weeks in current bullish state -- keep RECENT turns (default 12)")
    pes.add_argument("--allow-decel", action="store_true",
                    help="don't require positive mention velocity (default: required)")
    pes.add_argument("--allow-neg-sentiment", action="store_true",
                    help="don't require positive sentiment velocity (default: required)")
    pes.add_argument("--finviz", type=int, default=0,
                    help="enrich top N with Finviz market cap + short float")
    pes.add_argument("--consumer", action="store_true")
    pes.add_argument("--north-america", dest="north_america", action="store_true")
    pes.set_defaults(func=cmd_early_stage)

    pma = sub.add_parser("momentum-accel",
                        help="44d social+sentiment velocity + acceleration cross-sectional rank")
    pma.add_argument("--top", type=int, default=30)
    pma.add_argument("--window", type=int, default=44, help="rolling window in days")
    pma.add_argument("--min-total", dest="min_total", type=int, default=20)
    pma.add_argument("--allow-negative", action="store_true",
                    help="don't require positive velocities (default: positive-only)")
    pma.set_defaults(func=cmd_momentum_accel)

    por = sub.add_parser("ordinal-rank",
                         help="Cross-sectional ordinal rank: 44d sentiment + 14d modal mentions")
    por.add_argument("--top", type=int, default=30)
    por.add_argument("--sentiment-window", dest="sentiment_window", type=int, default=44)
    por.add_argument("--modal-window", dest="modal_window", type=int, default=14)
    por.add_argument("--min-total", dest="min_total", type=int, default=10)
    por.set_defaults(func=cmd_ordinal_rank)

    psw = sub.add_parser("social-weekly",
                         help="Weekly social WoW comparisons: movers, pivot, or per-ticker history")
    psw.add_argument("--top", type=int, default=25)
    psw.add_argument("--weeks", type=int, default=6, help="history depth (per-ticker / pivot)")
    psw.add_argument("--min-mentions", dest="min_mentions", type=int, default=10)
    psw.add_argument("--sort-by", dest="sort_by", default="mentions_wow_pct",
                    help="movers sort col: mentions_wow_pct, mentions_wow_chg, sentiment_delta, polarity_gap_delta")
    psw.add_argument("--ticker", default=None, help="single ticker -> show full weekly history table")
    psw.add_argument("--pivot", action="store_true",
                    help="show wide-form weekly pivot of --metric across top N tickers")
    psw.add_argument("--metric", default="mentions",
                    choices=["mentions", "sentiment", "polarity_gap", "bull", "bear"])
    psw.set_defaults(func=cmd_social_weekly)

    pcsf = sub.add_parser("camillo-social-first",
                         help="Social-first Camillo: divergence + spike + small/mid-cap")
    pcsf.add_argument("--top", type=int, default=20)
    pcsf.add_argument("--mcap-min", dest="mcap_min", type=float, default=250.0)
    pcsf.add_argument("--mcap-max", dest="mcap_max", type=float, default=10000.0)
    pcsf.add_argument("--min-divergence", dest="min_divergence", type=float, default=0.3)
    pcsf.add_argument("--min-social-z", dest="min_social_z", type=float, default=0.3)
    pcsf.add_argument("--min-close", dest="min_close", type=float, default=1.0)
    pcsf.add_argument("--consumer", action="store_true")
    pcsf.add_argument("--north-america", dest="north_america", action="store_true")
    pcsf.set_defaults(func=cmd_camillo_social_first)

    psm = sub.add_parser("smid-asymmetric",
                        help="Small/mid-cap asymmetric setups: Finviz-filtered mcap, social-spike bonus")
    psm.add_argument("--top", type=int, default=25)
    psm.add_argument("--pool", type=int, default=300, help="size of pre-Finviz candidate pool")
    psm.add_argument("--enrich", type=int, default=150, help="how many to Finviz-enrich")
    psm.add_argument("--mcap-min", dest="mcap_min", type=float, default=250.0,
                    help="market cap floor in millions (default 250)")
    psm.add_argument("--mcap-max", dest="mcap_max", type=float, default=10000.0,
                    help="market cap ceiling in millions (default 10000 = $10B)")
    psm.add_argument("--min-close", dest="min_close", type=float, default=1.5)
    psm.add_argument("--min-upside", dest="min_upside", type=float, default=50.0)
    psm.add_argument("--min-ratio", dest="min_ratio", type=float, default=3.0)
    psm.add_argument("--consumer", action="store_true")
    psm.add_argument("--north-america", dest="north_america", action="store_true")
    psm.set_defaults(func=cmd_smid_asymmetric)

    pas = sub.add_parser("asymmetric", help="Camillo-style asymmetric setups: capped downside, large upside")
    pas.add_argument("--top", type=int, default=30)
    pas.add_argument("--min-close", dest="min_close", type=float, default=1.0)
    pas.add_argument("--min-upside", dest="min_upside", type=float, default=30.0,
                    help="minimum upside pct to 52w high (default 30%%)")
    pas.add_argument("--min-ratio", dest="min_ratio", type=float, default=2.0,
                    help="minimum upside/downside ratio (default 2x)")
    pas.add_argument("--finviz", type=int, default=0,
                    help="enrich top N with Finviz (short float, earnings date)")
    pas.add_argument("--consumer", action="store_true")
    pas.add_argument("--north-america", dest="north_america", action="store_true")
    pas.set_defaults(func=cmd_asymmetric)

    pbt = sub.add_parser("best-today", help="Best today: own-history percentile + cross-section z-score")
    pbt.add_argument("--top", type=int, default=40)
    pbt.add_argument("--short", type=int, default=4)
    pbt.add_argument("--long", type=int, default=8)
    pbt.add_argument("--history", type=int, default=156, help="weeks of own history to compare against (default 3y)")
    pbt.add_argument("--min-score", dest="min_score", type=float, default=0.0)
    pbt.add_argument("--min-close", dest="min_close", type=float, default=1.0)
    pbt.add_argument("--min-mentions", dest="min_mentions", type=int, default=0)
    pbt.add_argument("--max-above-sma40", dest="max_above_sma40", type=float, default=None,
                    help="filter out names more than N%% above 40w SMA")
    pbt.add_argument("--consumer", action="store_true")
    pbt.set_defaults(func=cmd_best_today)

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
