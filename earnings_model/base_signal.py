"""MU-style base-consolidation detector (local, no network).

Identifies the "coiled spring" setup — a stock in a long, contained sideways base
(like Micron's multi-year range before it broke out) that is now pressing the top
of that base with contracting volatility, sitting above its long-term moving
average. Computed from the monthly close history already cached in the raws
(~61 bars / 5y for 96% of names), so no price fetch is needed.

The base signal is deliberately PRICE-ONLY. The ``base-inflection`` screen then
multiplies it by the fundamental inflection the pipeline already scores, so a
name qualifies only when a genuine long base coincides with real fundamental
turn — a base without a fundamental reason is just a dead stock.

    python scripts/fetch_base.py      # raws -> data/base_metrics.parquet (no network)
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import config, util

BASE_METRICS_PATH = config.DATA_DIR / "base_metrics.parquet"

_WIN = 18          # months of "base" lookback (~1.5y contained range)
_MA = 10           # months for the long moving average (~40-week)
_MIN_BARS = 24     # need >=2y of history to call something a long base


def compute_base_metrics(closes) -> dict:
    """Base-consolidation metrics for one monthly close series (oldest->newest)."""
    c = np.asarray([x for x in (closes or []) if isinstance(x, (int, float)) and x == x], float)
    if len(c) < _MIN_BARS or (c <= 0).any():
        return {}
    win = c[-_WIN:] if len(c) >= _WIN else c
    hi, lo, last = float(win.max()), float(win.min()), float(win[-1])
    mean = float(win.mean())
    rng = (hi - lo) / mean if mean > 0 else np.nan          # contained-range width
    pos = (last - lo) / (hi - lo) if hi > lo else 0.5        # position in range (~1 = top)
    sma = float(c[-_MA:].mean())
    above_ma = last >= sma
    ext = (last - sma) / sma if sma > 0 else np.nan          # extension above the MA

    rets = np.diff(c) / c[:-1]
    recent = rets[-6:]
    prior = rets[-(_WIN):-6] if len(rets) >= _WIN else rets[:-6]
    rv = float(np.std(recent)) if len(recent) >= 3 else np.nan
    pv = float(np.std(prior)) if len(prior) >= 3 else np.nan
    contraction = (rv / pv) if (pv and pv > 1e-9) else np.nan   # <1 = volatility coiling in

    # How long has price stayed inside a +/-22% band of the current level (base age)?
    band = 0.22
    base_len = 0
    for x in reversed(c):
        if abs(x / last - 1.0) <= band:
            base_len += 1
        else:
            break

    # --- transparent 0..1 base_score ---------------------------------------- #
    # pressing the top (but not a vertical blow-off at the very top)
    s_pos = np.clip(pos, 0, 1) * (0.5 if pos > 0.98 else 1.0)
    # range healthy: reward a real-but-contained band, peak ~0.30, penalise
    # too-tight (dead) and too-wide (trending, not basing)
    s_range = float(np.clip(1.0 - abs((rng if rng == rng else 0.3) - 0.30) / 0.30, 0, 1))
    # volatility contracting into the base
    s_contract = float(np.clip(1.20 - (contraction if contraction == contraction else 1.0), 0, 1))
    # base maturity (longer = better, saturating at ~24 months)
    s_len = float(np.clip(base_len / 24.0, 0, 1))
    base_score = float(np.mean([s_pos, s_range, s_contract, s_len]))
    # a base must sit above its long MA and not already be extended far above it
    if not above_ma or (ext == ext and ext > 0.20):
        base_score *= 0.25

    return {
        "base_range": round(rng, 4) if rng == rng else np.nan,
        "base_pos": round(pos, 4),
        "base_vol_contraction": round(contraction, 4) if contraction == contraction else np.nan,
        "base_extension": round(ext, 4) if ext == ext else np.nan,
        "base_above_ma": bool(above_ma),
        "base_len_months": int(base_len),
        "base_score": round(base_score, 4),
    }


def build_base_overlay(symbols: set[str] | None = None) -> pd.DataFrame:
    """Compute base metrics for every cached raw with a monthly close history."""
    want = set(map(str, symbols)) if symbols is not None else None
    rows = []
    for p in glob.glob(str(config.RAW_CACHE_DIR / "*.json")):
        try:
            d = json.loads(Path(p).read_text())
        except (json.JSONDecodeError, OSError):
            continue
        sym = d.get("symbol")
        if not sym or not d.get("fetch_ok"):
            continue
        if want is not None and str(sym) not in want:
            continue
        closes = ((d.get("prices") or {}).get("monthly") or {}).get("close") or []
        m = compute_base_metrics(closes)
        if m:
            rows.append({"symbol": sym, **m})
    return pd.DataFrame(rows)


def save_overlay(df: pd.DataFrame, path: Path = BASE_METRICS_PATH) -> None:
    util.atomic_to_parquet(df, path)


def load_overlay(path: Path = BASE_METRICS_PATH) -> pd.DataFrame | None:
    if not Path(path).exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def attach(scored: pd.DataFrame, path: Path = BASE_METRICS_PATH) -> pd.DataFrame:
    """Left-join base metrics onto a scored frame. No-op when the overlay is absent."""
    ov = load_overlay(path)
    if ov is None or "symbol" not in scored.columns:
        return scored
    dup = [c for c in ov.columns if c != "symbol" and c in scored.columns]
    scored = scored.drop(columns=dup, errors="ignore")
    return scored.merge(ov, on="symbol", how="left")
