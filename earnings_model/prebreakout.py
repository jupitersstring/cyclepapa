"""The "pre-breakout mood" mechanic.

Encodes the pattern from the cited posts: a stock that is *dead money* for 1-2
years while the *business quietly improves*, trading at a cheap / mispriced
multiple — the coiled spring that later "triples in a month". It is the tax you
pay for buying mispriced assets instead of consensus stories.

The screen is deliberately **gated on improving fundamentals**: a cheap, dormant
stock whose earnings are *not* improving is a value trap, not a pre-breakout.

    pre_breakout_score = w_improve * inflection_score   (business improving; GATED)
                       + w_dormant * dormancy           (dead money 1-2y: flat/down,
                                                          range-bound, lagged peers)
                       + w_cheap   * cheapness          (mispriced vs consensus)

Extra context: ``basing_tightness`` (low realised vol = coiled), ``breaking_out``
(dormant + improving, but price just starting to lift off the base).

``case_studies`` scans the cached monthly price series for the historical
"long flat base -> explosive move" archetype, to characterise the price shape
empirically (the fundamental-improvement leg is then applied to live candidates).
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from . import valuation as val


def add_prebreakout_score(
    df: pd.DataFrame,
    group_cols=("region",),
    min_inflection: float = 0.5,
    w_improve: float = 0.45,
    w_dormant: float = 0.30,
    w_cheap: float = 0.25,
    gate_penalty: float = 0.30,
) -> pd.DataFrame:
    """Add ``prebreakout_score`` and its components (improving × dormant × cheap)."""
    out = df.copy()
    if "inflection_score" not in out.columns:
        out = val.add_inflection_score(out, group_cols)
    if "valuation_richness" not in out.columns:
        out = val.add_valuation_richness(out, group_cols)
    gc = list(group_cols) if group_cols else None

    # --- dormancy: "dead money" over 1-2 years ------------------------------
    base_ret = "ret_24m" if "ret_24m" in out.columns else "ret_12m"
    peer_lag = 1.0 - val._group_pct_rank(out, base_ret, gc)          # lagged peers
    if "trend_slope" in out.columns:                                  # flat 2y trend
        flat = 1.0 - (out["trend_slope"].abs() / 0.5).clip(upper=1.0)
    else:
        flat = pd.Series(np.nan, index=out.index)
    if "range_position" in out.columns:                               # sitting near base
        near_base = 1.0 - out["range_position"].clip(0, 1)
    else:
        near_base = pd.Series(np.nan, index=out.index)
    out["dormancy"] = pd.concat([peer_lag, flat, near_base], axis=1).mean(axis=1, skipna=True).fillna(0.5)

    out["cheapness"] = (1.0 - out["valuation_richness"]).fillna(0.5)
    if "realized_vol" in out.columns:
        out["basing_tightness"] = (1.0 - val._group_pct_rank(out, "realized_vol", gc)).fillna(0.5)
    else:
        out["basing_tightness"] = 0.5

    improve = out["inflection_score"].fillna(0.0)
    raw = w_improve * improve + w_dormant * out["dormancy"] + w_cheap * out["cheapness"]
    # Value-trap guard: discount names whose business isn't actually improving.
    out["prebreakout_gated"] = improve >= min_inflection
    out["prebreakout_score"] = np.where(out["prebreakout_gated"], raw, raw * gate_penalty)

    r3 = out["ret_3m"] if "ret_3m" in out.columns else pd.Series(np.nan, index=out.index)
    out["breaking_out"] = out["prebreakout_gated"] & (r3 > 0.12) & (out["dormancy"] > 0.5)
    return out


def prebreakout_table(df: pd.DataFrame, top: int | None = 30, min_n_periods: int = 2,
                      only_gated: bool = True, quality: bool = True) -> pd.DataFrame:
    """Ranked pre-breakout shortlist (improving, dormant, cheap).

    ``quality=True`` restricts to operating companies (see valuation.is_operating).
    """
    work = df[val.is_operating(df, min_n_periods)] if quality else df
    if only_gated and "prebreakout_gated" in work.columns:
        work = work[work["prebreakout_gated"]]
    work = work.sort_values("prebreakout_score", ascending=False)
    cols = ["symbol", "name", "region", "industry", "size_bucket",
            "prebreakout_score", "inflection_score", "dormancy", "cheapness",
            "basing_tightness", "breaking_out", "ret_24m", "ret_12m", "trend_slope",
            "range_position", "forwardPE", "revenue_growth", "earnings_accel_abs"]
    present = [c for c in cols if c in work.columns]
    out = work[present]
    return out.head(top) if top else out


# --------------------------------------------------------------------------- #
# Case studies: the historical "long flat base -> explosive move" price shape
# --------------------------------------------------------------------------- #
def detect_base_then_breakout(
    dates: list, close: list,
    base_min_months: int = 15, base_max_drift: float = 0.35,
    breakout_move: float = 0.8, breakout_window: int = 6, max_move: float = 4.0,
) -> dict | None:
    """If the monthly series shows a long flat base then a sharp rise, describe it.

    A base of >= ``base_min_months`` whose high/low spread is <= ``base_max_drift``,
    immediately followed by a rise in [``breakout_move``, ``max_move``] within
    ``breakout_window`` months. ``max_move`` caps implausible jumps (>400% in a
    few months) that are almost always unadjusted-split / penny data artifacts.
    Returns the strongest qualifying episode, else None.
    """
    c = np.asarray(close, dtype=float)
    n = len(c)
    if n < base_min_months + breakout_window + 1:
        return None
    best = None
    for start_w in range(base_min_months, n - 1):
        base = c[start_w - base_min_months:start_w]
        if base.min() <= 0 or (base.max() / base.min() - 1.0) > base_max_drift:
            continue
        pre = c[start_w - 1]
        end = min(n, start_w + breakout_window)
        peak = c[start_w:end].max() if end > start_w else pre
        move = (peak / pre - 1.0) if pre > 0 else 0.0
        if breakout_move <= move <= max_move and (best is None or move > best["breakout_move"]):
            best = {
                "breakout_move": float(move),
                "base_start": dates[start_w - base_min_months],
                "breakout_from": dates[start_w - 1],
                "base_months": int(base_min_months),
            }
    return best


def case_studies(raw_dir: Path | None = None, top: int | None = 25, **kwargs) -> pd.DataFrame:
    """Scan cached monthly price series for the dead-money -> breakout archetype."""
    raw_dir = Path(raw_dir or config.RAW_CACHE_DIR)
    rows = []
    for p in glob.glob(str(raw_dir / "*.json")):
        try:
            raw = json.loads(Path(p).read_text())
        except (json.JSONDecodeError, OSError):
            continue
        mon = (raw.get("prices") or {}).get("monthly") or {}
        d, c = mon.get("dates") or [], mon.get("close") or []
        hit = detect_base_then_breakout(d, c, **kwargs)
        if hit:
            hit["symbol"] = raw.get("symbol")
            rows.append(hit)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("breakout_move", ascending=False).reset_index(drop=True)
    return df.head(top) if top else df
