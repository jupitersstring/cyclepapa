"""
Harmonic pattern scanner — spec-faithful port of TradingView's
"Harmonic Scanner" (PatternsHunters, script OeaGmeDz).

The original Pine source is closed, so this reimplements its documented
behaviour exactly: ZigZag pivots with a configurable depth (default 10),
patterns matched on up to the last 50 high/low points (X, A, B, C, D need
not be consecutive pivots — any parity-preserving selection is tried),
each leg ratio allowed to differ from the ideal book value by a
configurable error tolerance (percent), and the completion point D
labelled BUY when it is a swing low (bullish formation) or SELL when it
is a swing high.

Ratio tables are copied verbatim from the script's release notes:

    leg ratios: XAB = |B-A|/|X-A|, ABC = |C-B|/|A-B|,
                BCD = |D-C|/|C-B|, XAD = |D-A|/|X-A|

Like the original, the last ZigZag point is only as final as the data:
a pivot needs `depth` bars on both sides, so a brand-new extreme can
still move (the script's own comments call this out).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Verbatim from the script's release notes. Shark has no XAB constraint
# (points assumed named X,A,B,C,D as in the script, not 0,X,A,B,C).
PATTERNS = {
    'Gartley':       {'XAB': [0.618],
                      'ABC': [0.382, 0.5, 0.618, 0.786, 0.886],
                      'BCD': [1.13, 1.272, 1.414, 1.618],
                      'XAD': [0.786]},
    'Butterfly':     {'XAB': [0.786],
                      'ABC': [0.382, 0.5, 0.618, 0.786, 0.886],
                      'BCD': [1.618, 2.0, 2.24],
                      'XAD': [1.27]},
    'Bat':           {'XAB': [0.382, 0.5],
                      'ABC': [0.382, 0.5, 0.618, 0.786, 0.886],
                      'BCD': [1.618, 2.0, 2.24, 2.618],
                      'XAD': [0.886]},
    'Alternate Bat': {'XAB': [0.382],
                      'ABC': [0.382, 0.5, 0.618, 0.786, 0.886],
                      'BCD': [2.0, 2.24, 2.618, 3.14, 3.618],
                      'XAD': [1.13]},
    'Crab':          {'XAB': [0.382, 0.5, 0.618],
                      'ABC': [0.382, 0.5, 0.618, 0.786, 0.886],
                      'BCD': [2.618, 3.14, 3.618],
                      'XAD': [1.618]},
    'Deep Crab':     {'XAB': [0.886],
                      'ABC': [0.382, 0.5, 0.618, 0.786, 0.886],
                      'BCD': [2.24, 2.618, 3.14, 3.618],
                      'XAD': [1.618]},
    'Cypher':        {'XAB': [0.382, 0.5, 0.618],
                      'ABC': [1.13, 1.272, 1.414],
                      'BCD': [1.272, 1.414, 1.618, 2.0],
                      'XAD': [0.786]},
    'Shark':         {'XAB': None,
                      'ABC': [1.13, 1.272, 1.414, 1.618],
                      'BCD': [1.618, 2.0, 2.24],
                      'XAD': [0.886, 1.13]},
}

MAX_PIVOTS = 50     # "checks up to 50 last high/low points"


def zigzag(high, low, depth: int = 10):
    """ZigZag pivots: bar i is a pivot high when high[i] is the maximum of
    the window [i-depth, i+depth] (pivot lows symmetric). Consecutive
    same-side pivots collapse to the more extreme one so the sequence
    strictly alternates. Returns list of (bar_index, price, kind) with
    kind +1 = high, -1 = low."""
    h = np.asarray(high, float)
    l = np.asarray(low, float)
    n = len(h)
    raw = []
    for i in range(n):
        a, b = max(0, i - depth), min(n, i + depth + 1)
        if i - a == depth and b - i - 1 == depth:   # full window only
            if h[i] == h[a:b].max():
                raw.append((i, h[i], +1))
            if l[i] == l[a:b].min():
                raw.append((i, l[i], -1))
    piv = []
    for p in sorted(raw):
        if piv and piv[-1][2] == p[2]:
            keep = (p[1] > piv[-1][1]) if p[2] == +1 else (p[1] < piv[-1][1])
            if keep:
                piv[-1] = p
        else:
            piv.append(p)
    return piv


def _ratio_ok(measured, ideals, tol):
    if ideals is None:
        return True
    return any(abs(measured / r - 1.0) <= tol for r in ideals if r > 0)


def match_patterns(px, pa, pb, pc, pd_, tol):
    """Names of every pattern whose four leg ratios all fit within tol."""
    xa, ab = abs(pa - px), abs(pb - pa)
    bc, cd = abs(pc - pb), abs(pd_ - pc)
    ad = abs(pd_ - pa)
    if min(xa, ab, bc) <= 0:
        return []
    xab, abc, bcd, xad = ab / xa, bc / ab, cd / bc, ad / xa
    out = []
    for name, r in PATTERNS.items():
        if (_ratio_ok(xab, r['XAB'], tol) and _ratio_ok(abc, r['ABC'], tol)
                and _ratio_ok(bcd, r['BCD'], tol)
                and _ratio_ok(xad, r['XAD'], tol)):
            out.append(name)
    return out


# Pre-computed pruning bounds so the (C,B) inner loops die early.
_ALL_BCD = [v for r in PATTERNS.values() for v in r['BCD']]
_ALL_ABC = [v for r in PATTERNS.values() for v in r['ABC']]


def scan(high, low, depth: int = 10, tol: float = 0.15,
         within_bars: int = 15):
    """Scan for harmonic completions whose D pivot lies within the last
    `within_bars` bars. X,A,B,C are drawn from up to MAX_PIVOTS pivots
    before D, any parity-preserving (still-alternating) selection, exactly
    as the original scans beyond five consecutive points.

    Returns a list of dicts: {signal, pattern(s), d_index, d_price,
    bars_ago}, newest D first."""
    n = len(high)
    piv = zigzag(high, low, depth)
    if len(piv) < 5:
        return []
    piv = piv[-(MAX_PIVOTS + 1):]
    results = []
    bcd_lo = min(_ALL_BCD) * (1 - tol)
    bcd_hi = max(_ALL_BCD) * (1 + tol)
    abc_lo = min(_ALL_ABC) * (1 - tol)
    abc_hi = max(_ALL_ABC) * (1 + tol)
    for m in range(len(piv) - 1, 3, -1):
        d_idx, d_px, d_kind = piv[m]
        bars_ago = (n - 1) - d_idx
        if bars_ago > within_bars:
            break
        found = set()
        for c in range(m - 1, 2, -2):           # parity: C opposite of D
            pc = piv[c][1]
            bc_ref = None
            for b in range(c - 1, 1, -2):
                pb = piv[b][1]
                bc = abs(pc - pb)
                if bc <= 0:
                    continue
                bcd = abs(d_px - pc) / bc
                if not (bcd_lo <= bcd <= bcd_hi):
                    continue
                for a in range(b - 1, 0, -2):
                    pa = piv[a][1]
                    ab = abs(pb - pa)
                    if ab <= 0:
                        continue
                    abc = bc / ab
                    if not (abc_lo <= abc <= abc_hi):
                        continue
                    for x in range(a - 1, -1, -2):
                        found.update(match_patterns(
                            piv[x][1], pa, pb, pc, d_px, tol))
        if found:
            results.append({
                'signal': 'buy' if d_kind == -1 else 'sell',
                'patterns': sorted(found),
                'd_index': int(d_idx),
                'd_price': float(d_px),
                'bars_ago': int(bars_ago),
            })
    return results


def latest_signal(df: pd.DataFrame, depth: int = 10, tol: float = 0.15,
                  within_bars: int = 15) -> dict:
    """Most recent harmonic completion within `within_bars`, as flat
    columns ready to merge onto a screener row."""
    empty = {'harm_signal': '', 'harm_patterns': '', 'harm_bars_ago': np.nan,
             'harm_d_price': np.nan}
    if df is None or len(df) < 4 * depth:
        return empty
    res = scan(df['High'].values, df['Low'].values, depth, tol, within_bars)
    if not res:
        return empty
    r = res[0]
    return {'harm_signal': r['signal'],
            'harm_patterns': '+'.join(r['patterns']),
            'harm_bars_ago': r['bars_ago'],
            'harm_d_price': r['d_price']}
