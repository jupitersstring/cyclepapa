"""Command-line interface for the UK earnings-modelling toolkit.

Examples
--------
    # 1. Build the UK LSE/GBP universe (industry + size bucket)
    python -m earnings_model build-universe

    # 2. Fetch fundamentals (cached + backoff). Start small to test:
    python -m earnings_model fetch --limit 50

    # 3. Score, aggregate by industry, find the inflecting-but-cheap names
    python -m earnings_model analyze --group-cols industry

    # 4. Cluster by growth/acceleration behaviour
    python -m earnings_model cluster

    # Or the whole pipeline at once:
    python -m earnings_model run --limit 200 --group-cols industry,size_bucket
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import config, pipeline, screens


def _csv_list(value: str | None):
    if not value:
        return None
    return tuple(v.strip() for v in value.split(",") if v.strip())


def _show(path: Path, n: int) -> None:
    import pandas as pd

    if not path.exists():
        raise SystemExit(f"not found: {path} (run the relevant step first)")
    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_parquet(path)
    with pd.option_context("display.width", 220, "display.max_columns", 40):
        print(f"# {path}  ({len(df)} rows)")
        print(df.head(n).to_string(index=False))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="earnings_model", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    u = sub.add_parser("build-universe", help="build the universe from financedatabase")
    u.add_argument("--preset", choices=list(config.UNIVERSE_PRESETS), default=None,
                   help="named universe (overrides country/exchanges): uk, us-small, uk+us-small")
    u.add_argument("--country", default=config.DEFAULT_COUNTRY)
    u.add_argument("--exchanges", default=",".join(config.DEFAULT_EXCHANGES),
                   help="comma-separated; empty string = no filter")
    u.add_argument("--currencies", default=",".join(config.DEFAULT_CURRENCIES),
                   help="comma-separated; empty string = no filter")
    u.add_argument("--require-industry", action="store_true")
    u.add_argument("--out", type=Path, default=config.UNIVERSE_PATH)

    f = sub.add_parser("fetch", help="fetch fundamentals via yfinance (cached)")
    f.add_argument("--universe", type=Path, default=config.UNIVERSE_PATH)
    f.add_argument("--limit", type=int, default=None)
    f.add_argument("--sample", type=int, default=None, help="fetch a random N-name sample")
    f.add_argument("--symbols", default=None, help="comma-separated symbols to fetch instead")
    f.add_argument("--refresh", action="store_true", help="ignore cache, refetch")
    f.add_argument("--no-backfill-size", action="store_true",
                   help="don't fill Unclassified buckets from live market cap")
    f.add_argument("--out", type=Path, default=config.FUNDAMENTALS_PATH)

    a = sub.add_parser("analyze", help="score, aggregate, find valuation gaps")
    a.add_argument("--in", dest="inp", type=Path, default=config.FUNDAMENTALS_PATH)
    a.add_argument("--group-cols", default="",
                   help="peer group for ranking. Empty (default) = whole universe "
                        "(cross-sectional). Use 'industry' or 'industry,size_bucket' "
                        "for sector-relative ranking.")
    a.add_argument("--top", type=int, default=40)
    a.add_argument("--out-dir", type=Path, default=config.CACHE_DIR)

    c = sub.add_parser("cluster", help="K-means on growth/acceleration behaviour")
    c.add_argument("--in", dest="inp", type=Path, default=None,
                   help="defaults to scored.parquet, falling back to fundamentals")
    c.add_argument("--k", type=int, default=None, help="fixed k (default: auto via silhouette)")
    c.add_argument("--features", default=None, help="comma-separated feature columns")
    c.add_argument("--out-dir", type=Path, default=config.CACHE_DIR)

    r = sub.add_parser("run", help="run the full pipeline")
    r.add_argument("--preset", choices=list(config.UNIVERSE_PRESETS), default=None)
    r.add_argument("--sample", type=int, default=None, help="fetch a random N-name sample")
    r.add_argument("--country", default=config.DEFAULT_COUNTRY)
    r.add_argument("--exchanges", default=",".join(config.DEFAULT_EXCHANGES))
    r.add_argument("--currencies", default=",".join(config.DEFAULT_CURRENCIES))
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--refresh", action="store_true")
    r.add_argument("--no-backfill-size", action="store_true")
    r.add_argument("--group-cols", default="",
                   help="peer group for per-name ranking; empty = whole universe")
    r.add_argument("--k", type=int, default=None)
    r.add_argument("--out-dir", type=Path, default=config.CACHE_DIR)

    sc = sub.add_parser("screen", help="run a named screen over scored.parquet")
    sc.add_argument("name", choices=list(screens.SCREENS), help="which screen")
    sc.add_argument("--in", dest="inp", type=Path, default=config.CACHE_DIR / "scored.parquet")
    sc.add_argument("-n", type=int, default=30)
    sc.add_argument("--region", default=None, help="filter to one region (UK/US/EU)")

    s = sub.add_parser("show", help="print the head of a cached output")
    s.add_argument("name", help="one of: universe, fundamentals, scored, industry, "
                                "industry_size, inflecting_lagging, valuation_gap, "
                                "clusters, cluster_profile (or a path)")
    s.add_argument("-n", type=int, default=20)
    s.add_argument("--out-dir", type=Path, default=config.CACHE_DIR)
    return p


_NAMED = {
    "universe": "universe.parquet",
    "fundamentals": "fundamentals.parquet",
    "scored": "scored.parquet",
    "industry": "industry.csv",
    "industry_size": "industry_size.csv",
    "inflecting_lagging": "inflecting_lagging.csv",
    "valuation_gap": "valuation_gap.csv",
    "prebreakout": "prebreakout.csv",
    "case_studies": "case_studies.csv",
    "clusters": "clusters.csv",
    "cluster_profile": "cluster_profile.csv",
}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.cmd == "build-universe":
        pipeline.step_universe(
            preset=args.preset,
            country=args.country,
            exchanges=_csv_list(args.exchanges),
            currencies=_csv_list(args.currencies),
            require_industry=args.require_industry,
            out=args.out,
        )
    elif args.cmd == "fetch":
        pipeline.step_fetch(
            universe_path=args.universe,
            limit=args.limit,
            sample=args.sample,
            symbols=list(_csv_list(args.symbols) or []) or None,
            refresh=args.refresh,
            backfill_size=not args.no_backfill_size,
            out=args.out,
        )
    elif args.cmd == "analyze":
        pipeline.step_analyze(
            fundamentals_path=args.inp,
            group_cols=_csv_list(args.group_cols),
            out_dir=args.out_dir,
            top=args.top,
        )
    elif args.cmd == "cluster":
        pipeline.step_cluster(
            scored_path=args.inp,
            features=list(_csv_list(args.features) or []) or None,
            k=args.k,
            out_dir=args.out_dir,
        )
    elif args.cmd == "run":
        pipeline.run_all(
            preset=args.preset,
            sample=args.sample,
            country=args.country,
            exchanges=_csv_list(args.exchanges),
            currencies=_csv_list(args.currencies),
            limit=args.limit,
            refresh=args.refresh,
            backfill_size=not args.no_backfill_size,
            group_cols=_csv_list(args.group_cols),
            k=args.k,
            out_dir=args.out_dir,
        )
    elif args.cmd == "screen":
        import pandas as pd
        df = pd.read_parquet(args.inp)
        if args.region:
            df = df[df["region"] == args.region]
        res = screens.SCREENS[args.name](df, top=args.n)
        with pd.option_context("display.width", 240, "display.max_columns", 40,
                               "display.max_colwidth", 28):
            print(f"# screen: {args.name}  ({len(res)} rows)")
            print(res.to_string(index=False))
    elif args.cmd == "show":
        target = _NAMED.get(args.name)
        path = (args.out_dir / target) if target else Path(args.name)
        _show(path, args.n)


if __name__ == "__main__":
    main()
