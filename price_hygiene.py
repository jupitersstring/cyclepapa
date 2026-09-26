"""Isolated price SPIKES in the weekly panel -> blanked, not trusted.

FMP's weekly bars occasionally carry a unit / scale glitch for a week or two
(KHDHF trades at 2.0-2.3 but shows closes of 240.0 on 2026-09-04 and -11:
100x, then back). Every price measure built on such a week is corrupt — the
52-week high (price at "1% of its high"), drawdowns, returns, breakouts,
multibagger labels.

A week is a SPIKE when its close is >= 4x (or <= 1/4 of) the price level its
neighbours agree on — the median of the 4 weeks before and the 4 weeks after,
which must themselves agree within 1.5x — i.e. the price jumps away and comes
straight back. Such a week's bar is blanked and the last good bar carried
forward (no information that week), never clamped or interpolated. A genuine
move that HOLDS (a takeover, a re-rating, a collapse) moves the later
neighbours too, fails the agreement test and is left untouched; the latest
weeks, whose "after" is not yet observed, are never blanked.

Intraweek extremes: a HIGH >= 4x the larger of the week's open / close (or a
LOW <= 1/4 of the smaller) is a bad tick inside an otherwise normal bar; the
extreme is replaced by that week's open / close envelope.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

JUMP = 4.0
AGREE = 1.5


def clean_weekly(p: pd.DataFrame) -> pd.DataFrame:
    """p: symbol, week, (open,) high, low, close[, volume, dvol] — any subset of
    OHLC present. Returns a copy with spike weeks blanked and bad intraweek
    extremes replaced; adds `px_spike` (1 = blanked week)."""
    p = p.sort_values(["symbol", "week"]).copy()
    cols = [x for x in ("open", "high", "low", "close", "dvol") if x in p.columns]
    spike = pd.Series(False, index=p.index)
    # iterate: a multi-week glitch hides behind its own weeks until the first
    # blanked week stops polluting its neighbours' reference level
    for _ in range(4):
        c = p["close"].astype(float).where(p["close"] > 0)
        g = c.groupby(p["symbol"], sort=False)
        before = g.transform(lambda s: s.shift(1).rolling(4, min_periods=2).median())
        after = g.transform(lambda s: s[::-1].shift(1).rolling(4, min_periods=2).median()[::-1])
        lo_nb, hi_nb = np.minimum(before, after), np.maximum(before, after)
        agree = (hi_nb / lo_nb.where(lo_nb > 0)) <= AGREE
        level = np.sqrt(before * after)
        ratio = c / level.where(level > 0)
        new = (agree & ((ratio >= JUMP) | (ratio <= 1.0 / JUMP))).fillna(False) & ~spike
        if not new.any():
            break
        spike |= new
        p.loc[new, cols] = np.nan
    p["px_spike"] = spike.astype(int)
    # a blanked week carries no information: carry the last good bar forward
    # so rolling windows downstream stay continuous (never an interpolation)
    if spike.any():
        p[cols] = p.groupby("symbol", sort=False)[cols].ffill()
    # bad intraweek extremes inside a normal bar, judged against this week's
    # close AND the previous close (the open can be corrupt with the high)
    prev_c = p["close"].groupby(p["symbol"], sort=False).shift(1)
    env_hi = pd.concat([p["close"], prev_c], axis=1).max(axis=1)
    env_lo = pd.concat([p["close"], prev_c], axis=1).min(axis=1)
    for col, bad in (("high", lambda x: x >= JUMP * env_hi), ("open", lambda x: (x >= JUMP * env_hi) | (x <= env_lo / JUMP)),
                     ("low", lambda x: x <= env_lo / JUMP)):
        if col in p.columns:
            b = bad(p[col]).fillna(False) & env_hi.notna()
            p.loc[b, col] = (env_hi if col == "high" else env_lo if col == "low" else p["close"])[b]
    return p
