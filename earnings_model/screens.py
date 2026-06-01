"""Reproducible stock screens over the scored universe.

Each screen returns a ranked DataFrame and is built from the same primitives so
results are consistent and reproducible (no ad-hoc notebooks). All screens:

* operate on **operating companies** only (``valuation.is_operating``);
* rank **cross-sectionally within region** (a multiple only means something
  against same-market peers), pooling when a single region is present;
* apply **artifact guardrails** — drop nano-caps, require a sane positive
  valuation multiple, and exclude ratio-growth blow-ups off a near-zero base
  (the lottery-ticket / mark-to-market distortions the raw scores reward).

Audit note: yfinance quarterly data is only ~40% populated, so QoQ enters as a
*bonus* (applied only where present) rather than equal-weighted with the
reliable annual (YoY) signal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import valuation as val

# Columns shown by the name-level screens.
_SHOW = [
    "symbol", "name", "region", "industry", "size_bucket", "score",
    "revenue_growth", "ebitda_growth", "earnings_growth",
    "ebitda_accel_abs", "enterpriseToEbitda", "priceToSalesTrailing12Months",
    "priceToBook", "forwardPE", "ret_12m", "ret_24m",
]


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _rank(df: pd.DataFrame, col: str, asc: bool = True) -> pd.Series:
    """Percentile rank within region (global if region absent/single)."""
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    if "region" in df.columns and df["region"].nunique(dropna=True) > 1:
        return df.groupby("region")[col].rank(pct=True, ascending=asc)
    return df[col].rank(pct=True, ascending=asc)


def eligible(df: pd.DataFrame, min_periods: int = 3, allow_nano: bool = False,
             require_multiple: bool = True) -> pd.DataFrame:
    """Operating-company universe with artifact guardrails applied."""
    out = df[val.is_operating(df, min_periods)].copy()
    if not allow_nano and "size_bucket" in out.columns:
        out = out[out["size_bucket"] != "Nano Cap"]
    if require_multiple:
        ev = out.get("enterpriseToEbitda", pd.Series(np.nan, index=out.index))
        pe = out.get("forwardPE", pd.Series(np.nan, index=out.index))
        pb = out.get("priceToBook", pd.Series(np.nan, index=out.index))
        sane = (ev.between(2, 25)) | (pe.between(2, 30)) | (pb.between(0.1, 10))
        out = out[sane]
    # Drop ratio-growth blow-ups off a near-zero base unless EBITDA genuinely
    # inflected (kills lottery-ticket / mark-to-market distortions).
    rev_g = out.get("revenue_growth", pd.Series(np.nan, index=out.index))
    eb_infl = out.get("ebitda_inflecting", pd.Series(False, index=out.index)).fillna(False)
    out = out[(rev_g.between(-0.6, 3.0)) | eb_infl]
    # Drop negative-EV/EBITDA (loss-making at the operating line — "cheap" is a
    # sign artifact, not value): if EV/EBITDA present it must be positive.
    if "enterpriseToEbitda" in out.columns:
        ev = out["enterpriseToEbitda"]
        out = out[ev.isna() | (ev > 0)]
    # Collapse cross-listing duplicates of the same company (e.g. SKB.F/SKB.DE,
    # PAH3.F/PAH3.DE) — keep one line per name+region.
    if {"name", "region"}.issubset(out.columns):
        out = out.drop_duplicates(subset=["name", "region"], keep="first")
    return out


def _cheap(df: pd.DataFrame) -> pd.Series:
    """0..1 cheapness from peer-ranked richness; neutral 0.5 when unknown."""
    if "valuation_richness" in df.columns:
        return (1.0 - df["valuation_richness"]).fillna(0.5)
    return pd.Series(0.5, index=df.index)


def _quiet(df: pd.DataFrame) -> pd.Series:
    """0..1 price dormancy from trailing 12m+24m returns (low = dormant)."""
    parts = [1.0 - _rank(df, c) for c in ("ret_12m", "ret_24m") if c in df.columns]
    if not parts:
        return pd.Series(0.5, index=df.index)
    return pd.concat(parts, axis=1).mean(axis=1, skipna=True).fillna(0.5)


def _yoy_momentum(df: pd.DataFrame) -> pd.Series:
    """Annual growth + acceleration + inflection breadth (the reliable signal)."""
    growth = pd.concat([_rank(df, c) for c in
                        ("revenue_growth", "ebitda_growth", "earnings_growth")],
                       axis=1).mean(axis=1, skipna=True)
    accel = pd.concat([_rank(df, c) for c in
                       ("revenue_accel", "ebitda_accel_abs", "earnings_accel_abs")],
                      axis=1).mean(axis=1, skipna=True)
    flags = df[[c for c in ("revenue_inflecting", "ebitda_inflecting", "earnings_inflecting")
                if c in df.columns]].astype(float).mean(axis=1, skipna=True)
    return (0.30 * growth.fillna(0.5) + 0.45 * accel.fillna(0.5)
            + 0.25 * flags.fillna(0.0))


def _qoq_bonus(df: pd.DataFrame) -> pd.Series:
    """Quarterly YoY + accel as a BONUS — only where present (~40% coverage),
    else neutral 0.5, so sparse quarterly data can't distort rankings."""
    cols = [c for c in ("revenue_q_yoy", "revenue_q_accel", "ebitda_q_yoy",
                        "ebitda_q_accel", "earnings_q_yoy", "earnings_q_accel")
            if c in df.columns]
    if not cols:
        return pd.Series(0.5, index=df.index)
    return pd.concat([_rank(df, c) for c in cols], axis=1).mean(axis=1, skipna=True).fillna(0.5)


def _finish(df: pd.DataFrame, score: pd.Series, top: int | None,
            extra: list[str] | None = None) -> pd.DataFrame:
    out = df.copy()
    out["score"] = score
    cols = _SHOW + [c for c in (extra or []) if c in out.columns]
    out = out[[c for c in cols if c in out.columns]].sort_values("score", ascending=False)
    return out.head(top) if top else out


# --------------------------------------------------------------------------- #
# Screens
# --------------------------------------------------------------------------- #
def yoy_unpriced(df: pd.DataFrame, top: int | None = 40, **elig) -> pd.DataFrame:
    """Annual (YoY) growth acceleration/inflection that the price hasn't paid for."""
    e = eligible(df, **elig)
    score = 0.55 * _yoy_momentum(e) + 0.45 * (0.6 * _cheap(e) + 0.4 * _quiet(e))
    return _finish(e, score, top)


def accel_unpriced(df: pd.DataFrame, top: int | None = 40, **elig) -> pd.DataFrame:
    """YoY momentum with a quarterly (QoQ) bonus, cheap + dormant."""
    e = eligible(df, **elig)
    mom = 0.8 * _yoy_momentum(e) + 0.2 * _qoq_bonus(e)   # QoQ is a bonus only
    score = 0.55 * mom + 0.45 * (0.6 * _cheap(e) + 0.4 * _quiet(e))
    return _finish(e, score, top)


def asymmetry(df: pd.DataFrame, top: int | None = 40, **elig) -> pd.DataFrame:
    """Operating inflection (catalyst) + cheap (downside) + dormant (unrecognised)."""
    e = eligible(df, **elig)
    infl = e["inflection_score"].fillna(0.0) if "inflection_score" in e else pd.Series(0.5, index=e.index)
    score = 0.40 * infl + 0.30 * _cheap(e) + 0.30 * _quiet(e)
    return _finish(e, score, top)


def inflecting_positive(df: pd.DataFrame, top: int | None = 40, **elig) -> pd.DataFrame:
    """Sales or EBITDA growth crossing from <=0 to >0 (a genuine rate-of-change turn)."""
    e = eligible(df, **elig)
    def crossed(g, p):
        return (e.get(p, pd.Series(np.nan, index=e.index)).fillna(0) <= 0) & (e.get(g, pd.Series(np.nan, index=e.index)) > 0)
    sales = crossed("revenue_growth", "revenue_prev_growth") | e.get("revenue_trough_up", False).fillna(False)
    ebitda = (crossed("ebitda_growth", "ebitda_prev_growth")
              | e.get("ebitda_turned_positive", False).fillna(False)
              | e.get("ebitda_trough_up", False).fillna(False))
    e = e[sales | ebitda].copy()
    e["sales_inflected"] = sales[e.index]
    e["ebitda_inflected"] = ebitda[e.index]
    score = 0.45 * _cheap(e) + 0.30 * _quiet(e) + 0.25 * (
        e["inflection_score"].fillna(0.0) if "inflection_score" in e else 0.5)
    return _finish(e, score, top, extra=["sales_inflected", "ebitda_inflected"])


SCREENS = {
    "yoy-unpriced": yoy_unpriced,
    "accel-unpriced": accel_unpriced,
    "asymmetry": asymmetry,
    "inflecting-positive": inflecting_positive,
}
