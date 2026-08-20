"""Offline validation of the Multi ZigZag Harmonic Patterns port:
causal zigzag semantics, AND+OR ratio rules, fire-on-transition with
waitForConfirmation, and the flattened screener output."""
import numpy as np
import pandas as pd
import harmonics as m

fails = 0
def check(name, cond):
    global fails
    status = 'PASS' if cond else 'FAIL'
    if not cond: fails += 1
    print(f"  [{status}] {name}")


def legs_to_bars(points, bars_per_leg=8, pad_end=8):
    """Piecewise-linear path through pivot prices; pad_end bars bounce off
    the last point so its pivot confirms (a NEW opposite pivot forms and
    D becomes index 1 under waitForConfirmation)."""
    path = []
    for i in range(len(points) - 1):
        path.extend(np.linspace(points[i], points[i + 1], bars_per_leg,
                                endpoint=False))
    path.append(points[-1])
    drift = 1.0 if points[-1] < points[-2] else -1.0
    for j in range(pad_end):
        path.append(points[-1] + drift * 1.5 * (j + 1))
    p = np.array(path, float)
    return p + 0.05, p - 0.05


# Book-exact bullish Gartley: X=100 A=200 B=138.2 C=176.4 D=121.4
# (xab=.618 abc=.618 bcd=1.44 xad=.786); lead-in leg so X confirms.
G = [150.0, 100.0, 200.0, 138.2, 176.4, 121.4]
h, l = legs_to_bars(G)

# --- 1. causal zigzag ----------------------------------------------------
lf = m.replay(h, l, length=3, err_pct=10)
check('bullish Gartley fires', lf is not None and 'Gartley' in lf['patterns'])
check('completion dir is bullish (buy)', lf and lf['dir'] == 1)
check('D anchored at the probe low', lf and abs(lf['d_price'] - 121.35) < 0.3)
check('firing bar AFTER the D bar (confirmation lag)',
      lf and lf['bar'] > lf['d_bar'])

# --- 2. bearish mirror ---------------------------------------------------
h2, l2 = legs_to_bars([300 - p for p in G])
lf2 = m.replay(h2, l2, length=3, err_pct=10)
check('bearish mirror fires as sell',
      lf2 is not None and lf2['dir'] == -1 and 'Gartley' in lf2['patterns'])

# --- 3. OR rule: bad BCD but exact XAD still matches ---------------------
# bcd=2.0 (outside Gartley's 1.272-1.618+10%) but xad exactly .786:
# C = B + 0.4*(A-B) = 162.9 -> bcd = (162.9-121.4)/24.7 = 1.68... build
# instead with abc=0.5: C=169.1, bcd=(169.1-121.4)/30.9=1.544 in range.
# For the OR test use a D that misses bcd but nails xad:
#   abc=.886 -> C=192.9; D=121.4: bcd=(192.9-121.4)/54.7=1.31 in range...
# Take bcd deliberately out: abc=.382 -> C=161.8, bcd=(161.8-121.4)/23.6
# = 1.71 (Gartley bcd max 1.618*1.1=1.78 -> still in!). Use err 5:
lf3 = m.replay(*legs_to_bars([150.0, 100.0, 200.0, 138.2, 161.8, 121.4]),
               length=3, err_pct=5)
check('OR rule: xad=.786 rescues out-of-range bcd',
      lf3 is not None and 'Gartley' in lf3['patterns'])

# --- 4. AND legs still binding: broken XAB kills Gartley ------------------
lf4 = m.replay(*legs_to_bars([150.0, 100.0, 200.0, 155.0, 176.4, 121.4]),
               length=3, err_pct=10)   # xab=.45, outside .618±10%
check('broken XAB: no Gartley', not (lf4 and 'Gartley' in lf4['patterns']))

# --- 5. B-interior guard --------------------------------------------------
# B above A would make b the extreme high -> guard rejects everything.
lf5 = m.replay(*legs_to_bars([150.0, 100.0, 200.0, 210.0, 176.4, 121.4]),
               length=3, err_pct=20)
check('B at the extreme is rejected by interior guard',
      not (lf5 and set(lf5['patterns']) & set(m.WM_NAMES)))

# --- 6. recency window in latest_signal ----------------------------------
idx = pd.date_range('2024-01-01', periods=len(h), freq='D')
df = pd.DataFrame({'High': h, 'Low': l, 'Close': (h + l) / 2,
                   'Open': (h + l) / 2, 'Volume': 1e6}, index=idx)
sig = m.latest_signal(df, lengths=(3,), err_pct=10, within_bars=20)
check('latest_signal: buy + Gartley + zz length',
      sig['harm_signal'] == 'buy' and 'Gartley' in sig['harm_patterns']
      and sig['harm_zz'] == 3)
h6 = np.concatenate([h, np.full(60, h[-1])])
l6 = np.concatenate([l, np.full(60, l[-1])])
df6 = pd.DataFrame({'High': h6, 'Low': l6, 'Close': (h6 + l6) / 2,
                    'Open': (h6 + l6) / 2, 'Volume': 1e6},
                   index=pd.date_range('2024-01-01', periods=len(h6),
                                       freq='D'))
sig6 = m.latest_signal(df6, lengths=(3,), err_pct=10, within_bars=15)
check('stale firing outside window -> empty', sig6['harm_signal'] == '')
check('too-short history -> empty',
      m.latest_signal(df.head(6), lengths=(3,))['harm_signal'] == '')

# --- 7. AB=CD symmetry ---------------------------------------------------
# a<b<d, c between: a=100,b=150,c=120,d=170: ab=50,cd=50 price ratio 1,
# equal leg times -> AB=CD; abc=|c-b|/|a-b|=.6 -> also ABCD at 10%? abc
# needs .618*.9=.556<=.6 ok, bcd=|d-c|/|b-c|=50/30=1.67 vs 1.618*1.1 ok
# -> ABCD too. Accept either label; require AB=CD present.
# Alternating pivots: y=55(lo) x=140(hi) a=100(lo) b=150(hi) c=120(lo)
# d=170(hi); ab and cd both 50 points over 8 bars -> ratios 1.0.
lf7 = m.replay(*legs_to_bars([120.0, 55.0, 140.0, 100.0, 150.0, 120.0,
                              170.0], bars_per_leg=8), length=3, err_pct=10)
check('AB=CD fires on symmetric legs',
      lf7 is not None and 'AB=CD' in lf7['patterns'])

# --- 8. causal pivot mechanics -------------------------------------------
hh = np.array([10, 11, 12, 11, 10, 9, 10, 11, 12, 13], float)
ll = hh - 0.5
lfz = m.replay(hh, ll, length=2, err_pct=10)
check('replay survives short choppy series (no crash)', lfz is None)

print(f"\n{'ALL TESTS PASSED' if fails == 0 else f'{fails} FAILURES'}")
raise SystemExit(fails)
