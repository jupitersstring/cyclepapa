"""Aggregate per-name metrics up to industry and industry x size-bucket cells.

This is where the macro question gets answered: *which industries (within which
size band) are inflecting in aggregate while their valuations / prices lag?*
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# (output column, source column, aggregation) — only used if source present.
_NUMERIC_AGGS = [
    ("n", "symbol", "count"),
    ("rev_growth_med", "revenue_growth", "median"),
    ("rev_accel_med", "revenue_accel", "median"),
    ("ebitda_accel_med", "ebitda_accel_abs", "median"),
    ("earnings_accel_med", "earnings_accel_abs", "median"),
    ("rev_q_yoy_med", "revenue_q_yoy", "median"),
    ("inflection_med", "inflection_score", "median"),
    ("valuation_richness_med", "valuation_richness", "median"),
    ("fwd_pe_med", "forwardPE", "median"),
    ("ev_ebitda_med", "enterpriseToEbitda", "median"),
    ("ps_med", "priceToSalesTrailing12Months", "median"),
    ("ret_12m_med", "ret_12m", "median"),
    ("gap_score_med", "gap_score", "median"),
]
_FLAG_AGGS = [
    ("pct_rev_inflecting", "revenue_inflecting"),
    ("pct_earnings_inflecting", "earnings_inflecting"),
    ("pct_ebitda_inflecting", "ebitda_inflecting"),
    ("pct_broad_inflection", "broad_inflection"),
]


def _build_agg(df: pd.DataFrame) -> dict:
    spec = {}
    for out_col, src, how in _NUMERIC_AGGS:
        if src in df.columns:
            spec[out_col] = pd.NamedAgg(column=src, aggfunc=how)
    for out_col, src in _FLAG_AGGS:
        if src in df.columns:
            spec[out_col] = pd.NamedAgg(
                column=src, aggfunc=lambda s: float(np.nanmean(s.astype(float)))
            )
    return spec


def aggregate_by(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    spec = _build_agg(df)
    if not spec:
        raise ValueError("No aggregatable columns present — run metrics/scoring first.")
    grouped = df.groupby(group_cols, dropna=False).agg(**spec).reset_index()
    return grouped.sort_values(group_cols).reset_index(drop=True)


def industry_table(df: pd.DataFrame) -> pd.DataFrame:
    return aggregate_by(df, ["industry"])


def industry_size_table(df: pd.DataFrame) -> pd.DataFrame:
    return aggregate_by(df, ["industry", "size_bucket"])


def inflecting_lagging(df: pd.DataFrame, min_n: int = 3, top: int | None = 25) -> pd.DataFrame:
    """Rank industries: high aggregate inflection, lagging valuation/price.

    All three legs are ranked **across industries** from absolute medians (a
    within-industry percentile would be ~0.5 everywhere and carry no signal):

    * ``industry_inflection`` — breadth of inflection + growth + acceleration;
    * ``industry_richness``  — median forward P/E, EV/EBITDA, P/S (higher = dearer);
    * ``industry_quiet``      — low trailing price return (price hasn't responded).

    ``cell_gap`` = inflection − richness + ¼·(quiet − ½). High = inflecting,
    cheap, and the market hasn't re-rated it yet.
    """
    tbl = industry_table(df)
    tbl = tbl[tbl["n"] >= min_n].copy()
    if tbl.empty:
        return tbl

    def _rank(col: str) -> pd.Series:
        if col not in tbl.columns:
            return pd.Series(np.nan, index=tbl.index)
        return tbl[col].rank(pct=True)

    industry_inflection = pd.concat(
        [_rank("pct_broad_inflection"), _rank("rev_growth_med"),
         _rank("earnings_accel_med"), _rank("ebitda_accel_med")],
        axis=1,
    ).mean(axis=1, skipna=True)

    rich_parts = []
    for col in ("fwd_pe_med", "ev_ebitda_med", "ps_med"):
        if col in tbl.columns:
            rich_parts.append(tbl[col].where(tbl[col] > 0).rank(pct=True))
    industry_richness = (
        pd.concat(rich_parts, axis=1).mean(axis=1, skipna=True)
        if rich_parts else pd.Series(0.5, index=tbl.index)
    )

    ret = tbl.get("ret_12m_med", pd.Series(0.0, index=tbl.index)).fillna(0.0)
    industry_quiet = 1.0 - ret.rank(pct=True)

    tbl["industry_inflection"] = industry_inflection.fillna(0.5)
    tbl["industry_richness"] = industry_richness.fillna(0.5)
    tbl["industry_quiet"] = industry_quiet
    tbl["cell_gap"] = (
        tbl["industry_inflection"] - tbl["industry_richness"]
        + 0.25 * (industry_quiet - 0.5)
    )
    tbl = tbl.sort_values("cell_gap", ascending=False)
    return tbl.head(top) if top else tbl
