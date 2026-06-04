"""End-to-end orchestration: universe -> fetch -> score -> aggregate -> cluster.

Each step persists to the cache directory so they can be run independently
(e.g. fetch overnight on a machine with clean Yahoo access, analyse anywhere).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import aggregate, cluster, config, fundamentals, prebreakout, screens, universe, valuation


def step_universe(
    preset: str | None = None,
    country: str = config.DEFAULT_COUNTRY,
    exchanges=config.DEFAULT_EXCHANGES,
    currencies=config.DEFAULT_CURRENCIES,
    require_industry: bool = False,
    out: Path = config.UNIVERSE_PATH,
) -> pd.DataFrame:
    if preset:
        if preset not in config.UNIVERSE_PRESETS:
            raise ValueError(f"unknown preset {preset!r}; choose from {list(config.UNIVERSE_PRESETS)}")
        uni = universe.build_combined(config.UNIVERSE_PRESETS[preset])
    else:
        uni = universe.build_universe(
            country=country, exchanges=exchanges, currencies=currencies,
            require_industry=require_industry,
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    uni.to_parquet(out, index=False)
    by_region = uni["region"].value_counts().to_dict() if "region" in uni.columns else {}
    print(f"universe: {len(uni)} names {by_region} -> {out}")
    return uni


def step_fetch(
    universe_path: Path = config.UNIVERSE_PATH,
    limit: int | None = None,
    sample: int | None = None,
    symbols: list[str] | None = None,
    refresh: bool = False,
    backfill_size: bool = True,
    out: Path = config.FUNDAMENTALS_PATH,
) -> pd.DataFrame:
    uni = pd.read_parquet(universe_path)
    if sample and not symbols:
        n = min(sample, len(uni))
        symbols = uni.sample(n, random_state=config.RANDOM_STATE)["symbol"].tolist()
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
    if group_cols is None and "region" in funda.columns and funda["region"].nunique() > 1:
        group_cols = ("region",)  # rank within each market (UK vs US)
    scored = valuation.add_all_scores(funda, group_cols=group_cols)
    scored = prebreakout.add_prebreakout_score(scored, group_cols=group_cols)
    scored["is_operating"] = valuation.is_operating(scored)

    out_dir.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(out_dir / "scored.parquet", index=False)

    # Industry aggregates and shortlists use operating companies only (warrants,
    # preferreds, CEFs/BDCs and shells would otherwise pollute the medians).
    op = scored[scored["is_operating"]]
    ind = aggregate.industry_table(op)
    ind_size = aggregate.industry_size_table(op)
    lagging = aggregate.inflecting_lagging(op)
    gap = valuation.valuation_gap_table(scored, top=top)
    pre = prebreakout.prebreakout_table(scored, top=top)
    cases = prebreakout.case_studies()

    ind.to_csv(out_dir / "industry.csv", index=False)
    ind_size.to_csv(out_dir / "industry_size.csv", index=False)
    lagging.to_csv(out_dir / "inflecting_lagging.csv", index=False)
    gap.to_csv(out_dir / "valuation_gap.csv", index=False)
    pre.to_csv(out_dir / "prebreakout.csv", index=False)
    if not cases.empty:
        cases.to_csv(out_dir / "case_studies.csv", index=False)

    # Reproducible name screens (operating-only, region-aware, guardrailed).
    # 'conviction' runs the others internally, so it lands last and synthesises.
    screen_counts = {}
    for name, fn in screens.SCREENS.items():
        try:
            res = fn(scored, top=None)
            res.to_csv(out_dir / f"screen_{name.replace('-', '_')}.csv", index=False)
            screen_counts[name] = len(res)
        except Exception as err:  # a screen shouldn't break the pipeline
            print(f"  screen {name} skipped: {err}")
    print(
        f"analysis -> {out_dir}/: industry({len(ind)}) industry_size({len(ind_size)}) "
        f"inflecting_lagging({len(lagging)}) valuation_gap({len(gap)}) "
        f"prebreakout({len(pre)}) case_studies({len(cases)})"
    )
    if screen_counts:
        conv = screen_counts.get("conviction", 0)
        print(f"  screens: {', '.join(f'{k}({v})' for k, v in screen_counts.items())}"
              f"  -> conviction has {conv} multi-screen names")
    return {"scored": scored, "industry": ind, "industry_size": ind_size,
            "inflecting_lagging": lagging, "valuation_gap": gap,
            "prebreakout": pre, "case_studies": cases, "screen_counts": screen_counts}


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
    preset: str | None = None,
    country: str = config.DEFAULT_COUNTRY,
    exchanges=config.DEFAULT_EXCHANGES,
    currencies=config.DEFAULT_CURRENCIES,
    limit: int | None = None,
    sample: int | None = None,
    refresh: bool = False,
    backfill_size: bool = True,
    group_cols=None,
    k: int | None = None,
    out_dir: Path = config.CACHE_DIR,
) -> dict:
    step_universe(preset=preset, country=country, exchanges=exchanges, currencies=currencies)
    step_fetch(limit=limit, sample=sample, refresh=refresh, backfill_size=backfill_size)
    analysis = step_analyze(group_cols=group_cols, out_dir=out_dir)
    try:
        clusters = step_cluster(out_dir=out_dir, k=k)
    except ValueError as err:
        print(f"clustering skipped: {err}")
        clusters = None
    return {"analysis": analysis, "clusters": clusters}
