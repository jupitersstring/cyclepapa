"""Peer-ranked inflection, valuation richness and the earnings/valuation gap.

The headline output is ``gap_score``: high when a name's earnings are
inflecting/accelerating *yet* its valuation is cheap and its price hasn't
responded — i.e. exactly the "earnings inflecting, multiple not following"
setup. Ranks default to the **whole universe** (cross-sectional), which is the
right lens for "which industries are inflecting while valuations lag"; pass
``group_cols=("industry",)`` for sector-relative ranking instead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Signals where "higher = more inflecting / accelerating".
_ACCEL_SIGNALS = [
    "revenue_growth",
    "revenue_accel",
    "ebitda_accel_abs",
    "earnings_accel_abs",
    "revenue_q_yoy",
]
_INFLECTION_FLAGS = ["revenue_inflecting", "earnings_inflecting", "ebitda_inflecting"]

# Valuation multiples where "higher = more expensive". Non-positive values are
# masked (a negative P/E is not "cheap", it's not-meaningful).
_VALUATION_MULTIPLES = [
    "forwardPE",
    "trailingPE",
    "enterpriseToEbitda",
    "priceToSalesTrailing12Months",
    "priceToBook",
]


def _group_pct_rank(df: pd.DataFrame, col: str, group_cols=None, min_n: int = 3) -> pd.Series:
    """Percentile rank (0..1) of ``col``; global if ``group_cols`` is falsy.

    ``group_cols=None`` ranks across the whole universe — the right lens for the
    cross-sectional "earnings inflecting but valuation/price not responding"
    question. Pass e.g. ``("industry",)`` for sector-relative ranking instead.
    Thin samples (< ``min_n`` non-null) yield NaN so they fall back to neutral.
    """
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index)

    def _rank(x: pd.Series) -> pd.Series:
        if x.notna().sum() < min_n:
            return pd.Series(np.nan, index=x.index)
        return x.rank(pct=True)

    if not group_cols:
        return _rank(df[col])
    return df.groupby(list(group_cols), dropna=False)[col].transform(_rank)


def _mean_ignore_nan(frame: pd.DataFrame) -> pd.Series:
    """Row-wise mean ignoring NaN; all-NaN rows -> NaN (no warning)."""
    return frame.mean(axis=1, skipna=True)


def add_inflection_score(df: pd.DataFrame, group_cols=None) -> pd.DataFrame:
    """Add ``inflection_score`` (0..1): peer-ranked accel signals + flag bonus."""
    out = df.copy()
    group_cols = list(group_cols) if group_cols else None

    rank_cols = []
    for sig in _ACCEL_SIGNALS:
        if sig in out.columns:
            rc = f"_rank_{sig}"
            out[rc] = _group_pct_rank(out, sig, group_cols)
            rank_cols.append(rc)
    accel_rank = _mean_ignore_nan(out[rank_cols]) if rank_cols else pd.Series(np.nan, index=out.index)

    flag_cols = [c for c in _INFLECTION_FLAGS if c in out.columns]
    if flag_cols:
        flag_bonus = out[flag_cols].astype(float).mean(axis=1, skipna=True)
    else:
        flag_bonus = pd.Series(np.nan, index=out.index)

    # 70% peer-ranked acceleration, 30% hard inflection flags.
    out["accel_rank"] = accel_rank
    out["inflection_flag_score"] = flag_bonus
    out["inflection_score"] = (
        0.7 * accel_rank.fillna(0.5) + 0.3 * flag_bonus.fillna(0.0)
    )
    out = out.drop(columns=rank_cols)
    return out


def add_valuation_richness(df: pd.DataFrame, group_cols=None) -> pd.DataFrame:
    """Add ``valuation_richness`` (0..1, higher = more expensive vs peers)."""
    out = df.copy()
    group_cols = list(group_cols) if group_cols else None

    rank_cols = []
    for mult in _VALUATION_MULTIPLES:
        if mult not in out.columns:
            continue
        pos = out[mult].where(out[mult] > 0)  # mask non-positive multiples
        tmp = out.assign(_pos=pos)
        rc = f"_vrank_{mult}"
        out[rc] = _group_pct_rank(tmp, "_pos", group_cols)
        rank_cols.append(rc)

    out["valuation_richness"] = (
        _mean_ignore_nan(out[rank_cols]) if rank_cols else pd.Series(np.nan, index=out.index)
    )
    out["n_valuation_multiples"] = (
        out[rank_cols].notna().sum(axis=1) if rank_cols else 0
    )
    out = out.drop(columns=rank_cols)
    return out


def add_price_response(df: pd.DataFrame, group_cols=None) -> pd.DataFrame:
    """Add ``price_response`` (0..1): peer rank of trailing return (12m, else 6m)."""
    out = df.copy()
    group_cols = list(group_cols) if group_cols else None
    base = "ret_12m" if "ret_12m" in out.columns else "ret_6m"
    out["price_response"] = _group_pct_rank(out, base, group_cols) if base in out.columns else np.nan
    return out


def add_gap_score(
    df: pd.DataFrame,
    group_cols=None,
    w_inflection: float = 0.5,
    w_cheap: float = 0.3,
    w_quiet: float = 0.2,
) -> pd.DataFrame:
    """Add the composite ``gap_score`` and its components.

    gap_score = w_inflection * inflection_score
              + w_cheap      * cheapness        (= 1 - valuation_richness)
              + w_quiet       * price_quiet      (= 1 - price_response)

    Missing cheapness / quietness fall back to a neutral 0.5 so a name is never
    rewarded or punished merely for missing valuation data.
    """
    out = df.copy()
    if "inflection_score" not in out.columns:
        out = add_inflection_score(out, group_cols)
    if "valuation_richness" not in out.columns:
        out = add_valuation_richness(out, group_cols)
    if "price_response" not in out.columns:
        out = add_price_response(out, group_cols)

    cheapness = (1.0 - out["valuation_richness"]).fillna(0.5)
    price_quiet = (1.0 - out["price_response"]).fillna(0.5)
    out["cheapness"] = cheapness
    out["price_quiet"] = price_quiet
    out["gap_score"] = (
        w_inflection * out["inflection_score"]
        + w_cheap * cheapness
        + w_quiet * price_quiet
    )
    return out


def add_all_scores(df: pd.DataFrame, group_cols=None) -> pd.DataFrame:
    """Convenience: inflection + valuation + price + gap in one pass."""
    out = add_inflection_score(df, group_cols)
    out = add_valuation_richness(out, group_cols)
    out = add_price_response(out, group_cols)
    out = add_gap_score(out, group_cols)
    return out


def valuation_gap_table(df: pd.DataFrame, top: int | None = 30, min_n_periods: int = 2) -> pd.DataFrame:
    """Ranked 'earnings inflecting but valuation lagging' shortlist."""
    cols = [
        "symbol", "name", "industry", "size_bucket",
        "gap_score", "inflection_score", "valuation_richness", "price_response",
        "revenue_growth", "revenue_accel", "earnings_growth", "earnings_accel_abs",
        "ebitda_accel_abs", "forwardPE", "enterpriseToEbitda",
        "priceToSalesTrailing12Months", "ret_12m", "broad_inflection",
    ]
    present = [c for c in cols if c in df.columns]
    out = df[present].copy()
    if "revenue_n_periods" in df.columns:
        out = out[df["revenue_n_periods"].fillna(0) >= min_n_periods]
    out = out.sort_values("gap_score", ascending=False)
    return out.head(top) if top else out
