"""
Python port of the TradingView indicator "Multi ZigZag Harmonic Patterns"
(c) HeWhoMustNotBeNamed — Pine Script v5, Mozilla Public License 2.0
(https://mozilla.org/MPL/2.0/). This file is a derivative work of that
source and carries the same MPL-2.0 terms for the ported logic.

Faithful to the original in the three ways that matter and that a
spec-only reimplementation gets wrong:

1. The ZigZag is CAUSAL: a bar is a pivot the moment it is the
   highest/lowest of the trailing `length` bars (ta.highestbars==0 /
   ta.lowestbars==0) — no forward window. While direction persists the
   pivot extends to the more extreme value. Pivot dirs are graded
   +/-2 for higher-highs / lower-lows (used by Double Top/Bottom).
2. Ratio rules are AND(xab, abc) + OR(bcd, xad) with err_min/err_max
   bounds on the range endpoints — not all-four-AND. Shark has no XAB
   leg; 3 Drives adds the Y pivot (yxa); ABCD variants use time and
   price symmetry; Double Top/Bottom uses graded pivot dirs plus a
   risk-per-reward guard.
3. Detection replays EVERY bar and a signal fires on the false->true
   transition (pattern and not pattern[1]) with waitForConfirmation:
   D is the last CONFIRMED pivot (index 1), not the live one.

Defaults mirror the script: four ZigZag lengths 5/10/15/20,
errorPercent 10, MaxRiskPerReward 30, waitForConfirmation true.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_LENGTHS = (5, 10, 15, 20)
MAX_PIVOTS = 100

WM_NAMES = ('Gartley', 'Crab', 'Deep Crab', 'Bat', 'Butterfly', 'Shark',
            'Cypher', '3 Drive', '5-0')
ABCD_NAMES = ('ABCD', 'AB=CD', 'ABCD Ext')


def _rolling_extreme_flags(high, low, length):
    """hb[i] True when high[i] is the max of the trailing `length` bars
    (ta.highestbars(high, length) == 0); lb likewise for lows."""
    h = pd.Series(high, dtype=float)
    l = pd.Series(low, dtype=float)
    hb = (h >= h.rolling(length, min_periods=1).max()).values
    lb = (l <= l.rolling(length, min_periods=1).min()).values
    return hb, lb


def replay(high, low, length, err_pct=10.0, max_rr=30.0,
           wait_confirmation=True):
    """Bar-by-bar replay of one ZigZag length. Returns the LAST firing:
    {'bar', 'd_bar', 'd_price', 'dir', 'patterns'} or None. `dir` > 0 is
    a bullish completion (buy), < 0 bearish (sell), exactly the label
    colour logic of the original."""
    high = np.asarray(high, float)
    low = np.asarray(low, float)
    n = len(high)
    em = (100.0 - err_pct) / 100.0
    eM = (100.0 + err_pct) / 100.0
    hb, lb = _rolling_extreme_flags(high, low, length)

    pv, pb, pdirs = [], [], []          # newest-first, like Pine unshift
    dir_ = 0
    prev_wm = prev_ab = prev_db = False
    last_fire = None

    for i in range(n):
        phigh = high[i] if hb[i] else None
        plow = low[i] if lb[i] else None
        if phigh is not None and plow is None:
            newd = 1
        elif plow is not None and phigh is None:
            newd = -1
        else:
            newd = dir_
        dirchanged = newd != dir_
        dir_ = newd

        if phigh is not None or plow is not None:
            value = phigh if dir_ == 1 else plow
            bar = i
            if not dirchanged and pv:
                opv, opb, opd = pv.pop(0), pb.pop(0), pdirs.pop(0)
                if value * opd < opv * opd:      # old pivot more extreme
                    value, bar = opv, opb
            nd = dir_
            if len(pv) >= 2:
                lastpt = pv[1]
                nd = dir_ * 2 if dir_ * value > dir_ * lastpt else dir_
            pv.insert(0, value)
            pb.insert(0, bar)
            pdirs.insert(0, nd)
            if len(pv) > MAX_PIVOTS:
                pv.pop(); pb.pop(); pdirs.pop()

        # --- detection, every bar --------------------------------------
        st = 1 if wait_confirmation else 0
        wm = ab_ = db = False
        labels = []
        if len(pv) >= 6 + st:
            d, dB, dD = pv[st], pb[st], pdirs[st]
            c, cB, cD = pv[st + 1], pb[st + 1], pdirs[st + 1]
            b, bB, bD = pv[st + 2], pb[st + 2], pdirs[st + 2]
            a, aB = pv[st + 3], pb[st + 3]
            x, xB = pv[st + 4], pb[st + 4]
            y = pv[st + 5]
            xa, ab, bc = abs(b - a), abs(c - b), abs(d - c)  # leg sizes
            den_xa, den_ab, den_bc = abs(x - a), abs(a - b), abs(b - c)
            den_yx = abs(y - x)
            if min(den_xa, den_ab, den_bc) > 0:
                xab = abs(b - a) / den_xa
                abc = abs(c - b) / den_ab
                bcd = abs(d - c) / den_bc
                xad = abs(d - a) / den_xa
                yxa = abs(a - x) / den_yx if den_yx > 0 else np.inf
                hiP = max(x, a, b, c, d)
                loP = min(x, a, b, c, d)
                pdir = 1 if c > d else -1
                abT, cdT = abs(aB - bB), abs(cB - dB)
                abP, cdP = abs(a - b), abs(c - d)
                t_ratio = cdT / abT if abT > 0 else np.inf
                p_ratio = cdP / abP if abP > 0 else np.inf
                abcd_dir = (1 if (a < b and a < c and c < b and c < d
                                  and a < d and b < d) else
                            -1 if (a > b and a > c and c > b and c > d
                                   and a > d and b > d) else 0)
                risk, reward = abs(b - d), abs(c - d)
                rpr = (risk * 100 / (risk + reward)
                       if risk + reward > 0 else 100.0)

                if loP < b < hiP:
                    def rng(v, lo_r, hi_r):
                        return lo_r * em <= v <= hi_r * eM
                    if (rng(xab, .618, .618) and rng(abc, .382, .886) and
                            (rng(bcd, 1.272, 1.618) or rng(xad, .786, .786))):
                        wm = True; labels.append('Gartley')
                    if (rng(xab, .382, .618) and rng(abc, .382, .886) and
                            (rng(bcd, 2.24, 3.618) or rng(xad, 1.618, 1.618))):
                        wm = True; labels.append('Crab')
                    if (rng(xab, .886, .886) and rng(abc, .382, .886) and
                            (rng(bcd, 2.0, 3.618) or rng(xad, 1.618, 1.618))):
                        wm = True; labels.append('Deep Crab')
                    if (rng(xab, .382, .50) and rng(abc, .382, .886) and
                            (rng(bcd, 1.618, 2.618) or rng(xad, .886, .886))):
                        wm = True; labels.append('Bat')
                    if (rng(xab, .786, .786) and rng(abc, .382, .886) and
                            (rng(bcd, 1.618, 2.618) or rng(xad, 1.272, 1.618))):
                        wm = True; labels.append('Butterfly')
                    if (rng(abc, 1.13, 1.618) and rng(bcd, 1.618, 2.24) and
                            rng(xad, .886, 1.13)):
                        wm = True; labels.append('Shark')
                    if (rng(xab, .382, .618) and rng(abc, 1.13, 1.414) and
                            (rng(bcd, 1.272, 2.0) or rng(xad, .786, .786))):
                        wm = True; labels.append('Cypher')
                    if (rng(yxa, .618, .618) and rng(xab, 1.27, 1.618) and
                            rng(abc, .618, .618) and rng(bcd, 1.27, 1.618)):
                        wm = True; labels.append('3 Drive')
                    if (rng(xab, 1.13, 1.618) and rng(abc, 1.618, 2.24) and
                            rng(bcd, .5, .5)):
                        wm = True; labels.append('5-0')
                    if (rng(abc, .618, .786) and rng(bcd, 1.272, 1.618) and
                            abcd_dir != 0):
                        ab_ = True; labels.append('ABCD')
                    if (em <= t_ratio <= eM and em <= p_ratio <= eM and
                            abcd_dir != 0):
                        ab_ = True; labels.append('AB=CD')
                    if (rng(p_ratio, 1.272, 1.618) and rng(abc, .618, .786)
                            and abcd_dir != 0):
                        ab_ = True; labels.append('ABCD Ext')
                    if (((dD == 1 and bD == 2 and cD == -1) or
                         (dD == -1 and bD == -2 and cD == 1)) and
                            rpr < max_rr):
                        db = True
                        labels.append('Double Top' if pdir < 0
                                      else 'Double Bottom')

                fired = ((wm and not prev_wm) or (ab_ and not prev_ab)
                         or (db and not prev_db))
                if fired:
                    last_fire = {'bar': i, 'd_bar': int(dB),
                                 'd_price': float(d), 'dir': int(pdir),
                                 'patterns': labels[:]}
        prev_wm, prev_ab, prev_db = wm, ab_, db
    return last_fire


def latest_signal(df: pd.DataFrame, lengths=DEFAULT_LENGTHS,
                  err_pct: float = 10.0, within_bars: int = 15,
                  max_rr: float = 30.0) -> dict:
    """Most recent firing across the ZigZag lengths whose firing bar lies
    within `within_bars` of the last bar, flattened for a screener row."""
    empty = {'harm_signal': '', 'harm_patterns': '', 'harm_bars_ago': np.nan,
             'harm_d_price': np.nan, 'harm_zz': np.nan}
    if df is None or len(df) < max(lengths) * 3:
        return empty
    hi, lo = df['High'].values, df['Low'].values
    n = len(hi)
    best, best_len = None, None
    for L in lengths:
        lf = replay(hi, lo, L, err_pct, max_rr)
        if lf and (n - 1 - lf['bar']) <= within_bars:
            if best is None or lf['bar'] > best['bar']:
                best, best_len = lf, L
    if best is None:
        return empty
    return {'harm_signal': 'buy' if best['dir'] > 0 else 'sell',
            'harm_patterns': '+'.join(best['patterns']),
            'harm_bars_ago': n - 1 - best['bar'],
            'harm_d_price': best['d_price'],
            'harm_zz': best_len}
