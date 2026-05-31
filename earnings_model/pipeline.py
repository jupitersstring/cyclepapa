"""End-to-end orchestration: universe -> fetch -> score -> aggregate -> cluster.

Each step persists to the cache directory so they can be run independently
(e.g. fetch overnight on a machine with clean Yahoo access, analyse anywhere).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import aggregate, cluster, config, fundamentals, universe, valuation


def step_universe(
    country: str = config.DEFAULT_COUNTRY,
    exchanges=config.DEFAULT_EXCHANGES,
    currencies=config.DEFAULT_CURRENCIES,
    require_industry: bool = False,
    out: Path = config.UNIVERSE_PATH,
) -> pd.DataFrame:
    uni = universe.build_universe(
        country=country, exchanges=exchanges, currencies=currencies,
        require_industry=require_industry,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    uni.to_parquet(out, index=False)
    print(f"universe: {len(uni)} names -> {out}")
    return uni


def step_fetch(
    universe_path: Path = config.UNIVERSE_PATH,
    limit: int | None = None,
    symbols: list[str] | None = None,
    refresh: bool = False,
    backfill_size: bool = True,
    out: Path = config.FUNDAMENTALS_PATH,
) -> pd.DataFrame:
    uni = pd.read_parquet(universe_path)
    funda = fundamentals.build_fundamentals(
        uni, limit=limit, symbols=symbols, refresh=refresh
    )
    if backfill_size:
        # Recompute size buckets for Unclassified names from live market cap,
        # then re-attach so downstream grouping uses the filled buckets.
        uni_filled = universe.backfill_size_buckets(uni, funda)
        funda = funda.drop(columns=["size_bucket"], errors="ignore").merge(
            uni_filled[["symbol", "size_bucket"]], on="symbol", how="left"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    funda.to_parquet(out, index=False)
    ok = int(funda["fetch_ok"].sum()) if "fetch_ok" in funda.columns else len(funda)
    print(f"fundamentals: {len(funda)} rows ({ok} with data) -> {out}")
    return funda


def step_analyze(
    fundamentals_path: Path = config.FUNDAMENTALS_PATH,
    group_cols=None,
    out_dir: Path = config.CACHE_DIR,
    top: int | None = 40,
) -> dict:
    funda = pd.read_parquet(fundamentals_path)
    scored = valuation.add_all_scores(funda, group_cols=group_cols)

    out_dir.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(out_dir / "scored.parquet", index=False)

    ind = aggregate.industry_table(scored)
    ind_size = aggregate.industry_size_table(scored)
    lagging = aggregate.inflecting_lagging(scored)
    gap = valuation.valuation_gap_table(scored, top=top)

    ind.to_csv(out_dir / "industry.csv", index=False)
    ind_size.to_csv(out_dir / "industry_size.csv", index=False)
    lagging.to_csv(out_dir / "inflecting_lagging.csv", index=False)
    gap.to_csv(out_dir / "valuation_gap.csv", index=False)
    print(
        f"analysis -> {out_dir}/: industry.csv ({len(ind)}), "
        f"industry_size.csv ({len(ind_size)}), inflecting_lagging.csv ({len(lagging)}), "
        f"valuation_gap.csv ({len(gap)})"
    )
    return {"scored": scored, "industry": ind, "industry_size": ind_size,
            "inflecting_lagging": lagging, "valuation_gap": gap}


def step_cluster(
    scored_path: Path | None = None,
    fundamentals_path: Path = config.FUNDAMENTALS_PATH,
    features: list[str] | None = None,
    k: int | None = None,
    out_dir: Path = config.CACHE_DIR,
) -> dict:
    path = scored_path or (out_dir / "scored.parquet")
    src = path if Path(path).exists() else fundamentals_path
    df = pd.read_parquet(src)
    result = cluster.run_kmeans(df, features=features, k=k)

    out_dir.mkdir(parents=True, exist_ok=True)
    keep = [c for c in ["symbol", "name", "industry", "size_bucket", "cluster", "cluster_label",
                        "inflection_score", "gap_score", "revenue_growth", "earnings_accel_abs"]
            if c in result["labeled"].columns]
    result["labeled"][keep].dropna(subset=["cluster"]).to_csv(out_dir / "clusters.csv", index=False)
    result["profile"].to_csv(out_dir / "cluster_profile.csv", index=False)
    print(f"clusters: k={result['k']} silhouette={result['silhouette']} -> {out_dir}/clusters.csv")
    return result


def run_all(
    country: str = config.DEFAULT_COUNTRY,
    exchanges=config.DEFAULT_EXCHANGES,
    currencies=config.DEFAULT_CURRENCIES,
    limit: int | None = None,
    refresh: bool = False,
    backfill_size: bool = True,
    group_cols=None,
    k: int | None = None,
    out_dir: Path = config.CACHE_DIR,
) -> dict:
    step_universe(country=country, exchanges=exchanges, currencies=currencies)
    step_fetch(limit=limit, refresh=refresh, backfill_size=backfill_size)
    analysis = step_analyze(group_cols=group_cols, out_dir=out_dir)
    try:
        clusters = step_cluster(out_dir=out_dir, k=k)
    except ValueError as err:
        print(f"clustering skipped: {err}")
        clusters = None
    return {"analysis": analysis, "clusters": clusters}
