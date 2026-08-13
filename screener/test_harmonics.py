"""Offline validation of the harmonic scanner against constructed
zigzag series with book-exact and deliberately broken ratios."""
import numpy as np
import pandas as pd
import harmonics as m

fails = 0
def check(name, cond):
    global fails
    status = 'PASS' if cond else 'FAIL'
    if not cond: fails += 1
    print(f"  [{status}] {name}")


def legs_to_bars(points, bars_per_leg=8, pad_end=4):
    """Piecewise-linear path through pivot prices -> OHLC arrays. pad_end
    flat-ish bars after the last point let the final pivot confirm."""
    path = []
    for i in range(len(points) - 1):
        seg = np.linspace(points[i], points[i + 1], bars_per_leg,
                          endpoint=False)
        path.extend(seg)
    path.append(points[-1])
    last = points[-1]
    drift = 1.0 if points[-1] < points[-2] else -1.0   # bounce off D
    for j in range(pad_end):
        path.append(last + drift * 0.4 * (j + 1))
    p = np.array(path, float)
    return p + 0.05, p - 0.05    # high, low


# Bullish Gartley, book-exact: X=100 A=200 B=138.2 C=176.4 D=121.4
#   XAB=0.618  ABC=0.618  BCD=1.4397(~1.414)  XAD=0.786
# A lead-in leg before X lets the X pivot confirm (needs a left window).
GARTLEY = [150.0, 100.0, 200.0, 138.2, 176.4, 121.4]

# --- 1. zigzag pivots -----------------------------------------------------
h, l = legs_to_bars(GARTLEY)
piv = m.zigzag(h, l, depth=3)
kinds = [k for _, _, k in piv]
check('zigzag alternates', all(kinds[i] != kinds[i+1] for i in range(len(kinds)-1)))
check('zigzag found the 5 formation pivots', len(piv) >= 5)

# --- 2. exact bullish Gartley detected as BUY -----------------------------
res = m.scan(h, l, depth=3, tol=0.05, within_bars=10)
check('bullish Gartley found', any('Gartley' in r['patterns'] for r in res))
check('D is a low -> buy signal',
      all(r['signal'] == 'buy' for r in res if 'Gartley' in r['patterns']))
check('D price is the probe low',
      any(abs(r['d_price'] - (121.4 - 0.05)) < 0.2 for r in res))

# --- 3. bearish mirror -> SELL --------------------------------------------
mirror = [300 - p for p in GARTLEY]
h2, l2 = legs_to_bars(mirror)
res2 = m.scan(h2, l2, depth=3, tol=0.05, within_bars=10)
check('bearish Gartley found as sell',
      any(r['signal'] == 'sell' and 'Gartley' in r['patterns'] for r in res2))

# --- 4. tolerance actually constrains -------------------------------------
broken = [150.0, 100.0, 200.0, 155.0, 176.4, 121.4]  # XAB=0.45, off 0.618 by 27%
h3, l3 = legs_to_bars(broken)
res3 = m.scan(h3, l3, depth=3, tol=0.05, within_bars=10)
check('broken XAB rejected at 5% tol',
      not any('Gartley' in r['patterns'] for r in res3))
res3b = m.scan(h3, l3, depth=3, tol=0.30, within_bars=10)
check('same shape matches some pattern at 30% tol (Bat-like BCD)',
      any(r['patterns'] for r in res3b))

# --- 5. recency window ----------------------------------------------------
h4 = np.concatenate([h, np.full(40, 121.4 + 2.0)])
l4 = np.concatenate([l, np.full(40, 121.4 + 1.9)])
res4 = m.scan(h4, l4, depth=3, tol=0.05, within_bars=10)
check('stale completion outside N bars not flagged', res4 == [])

# --- 6. ratio matcher unit checks ----------------------------------------
check('Shark has no XAB constraint',
      m._ratio_ok(99.0, None, 0.05) is True)
check('ratio within 5% of 1.618 accepted', m._ratio_ok(1.69, [1.618], 0.05))
check('ratio 10% off 1.618 rejected', not m._ratio_ok(1.79, [1.618], 0.05))
# Bat vs Gartley separation: XAB=0.5 fits Bat, not Gartley (5% tol)
bat = m.match_patterns(100, 200, 150, 180.9, 111.4, 0.05)
check('XAB=0.5 shape matches Bat, not Gartley',
      'Bat' in bat and 'Gartley' not in bat)

# --- 7. latest_signal flat columns ---------------------------------------
idx = pd.date_range('2025-01-01', periods=len(h), freq='D')
df = pd.DataFrame({'High': h, 'Low': l, 'Close': (h + l) / 2,
                   'Open': (h + l) / 2, 'Volume': 1e6}, index=idx)
sig = m.latest_signal(df, depth=3, tol=0.05, within_bars=10)
check('latest_signal returns buy + Gartley',
      sig['harm_signal'] == 'buy' and 'Gartley' in sig['harm_patterns'])
empty = m.latest_signal(df.head(8), depth=3)
check('too-short history -> empty flags', empty['harm_signal'] == '')

print(f"\n{'ALL TESTS PASSED' if fails == 0 else f'{fails} FAILURES'}")
raise SystemExit(fails)
