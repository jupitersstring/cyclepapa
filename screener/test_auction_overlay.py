"""Offline validation of auction_overlay's computational core against
synthetic OHLCV frames."""
import numpy as np
import pandas as pd
import auction_overlay as m

fails = 0
def check(name, cond):
    global fails
    status = 'PASS' if cond else 'FAIL'
    if not cond: fails += 1
    print(f"  [{status}] {name}")


def bars(n, freq='D', close=None, high=None, low=None, vol=None, start='2024-01-01'):
    idx = pd.date_range(start, periods=n, freq=freq)
    c = np.asarray(close if close is not None else np.full(n, 100.0), float)
    h = np.asarray(high if high is not None else c * 1.01, float)
    l = np.asarray(low if low is not None else c * 0.99, float)
    v = np.asarray(vol if vol is not None else np.full(n, 1e6), float)
    return pd.DataFrame({'Open': c, 'High': h, 'Low': l, 'Close': c,
                         'Volume': v}, index=idx)

# --- 1. volume profile & value area --------------------------------------
# volume concentrated at 100: bars at 100 with heavy volume, one bar at 120
h = [101]*9 + [121]; l = [99]*9 + [119]; v = [1e6]*9 + [1e5]
c, vol = m.volume_profile(h, l, v, bins=50)
poc, val, vah = m.poc_value_area(c, vol)
check('POC lands in the heavy cluster', 99 <= poc <= 101)
check('value area excludes the outlier bar', vah < 119)
check('VAL <= POC <= VAH', val <= poc <= vah)
c0, v0 = m.volume_profile([], [], [])
check('empty profile -> (None,None,None)', m.poc_value_area(c0, v0) == (None, None, None))

# --- 2. Corwin-Schultz spread --------------------------------------------
wide = bars(60); wide['High'] = 102.0; wide['Low'] = 98.0
tight = bars(60); tight['High'] = 100.2; tight['Low'] = 99.8
s_wide = m.corwin_schultz(wide['High'], wide['Low'])
s_tight = m.corwin_schultz(tight['High'], tight['Low'])
check('CS spread non-negative', s_wide >= 0 and s_tight >= 0)
check('wider H/L -> larger spread estimate', s_wide > s_tight)

# --- 3. Amihud -----------------------------------------------------------
calm = bars(21)
jumpy = bars(21, close=100 + np.cumsum(np.tile([3, -3], 11))[:21] / 10 * 5)
check('Amihud higher for jumpier prices',
      m.amihud(jumpy['Close'], jumpy['Volume']) > m.amihud(calm['Close'], calm['Volume']))

# --- 4. one-timeframing --------------------------------------------------
lows = pd.Series([10, 9, 9.5, 10, 10.5, 11])
check('OTF counts trailing higher lows', m.one_timeframing_up(lows) == 4)
check('OTF zero after a lower low', m.one_timeframing_up(pd.Series([10, 11, 9])) == 0)

# --- 5. failed auction at the lows ---------------------------------------
n = 40
lo = np.full(n, 95.0); cl = np.full(n, 100.0)
lo[35] = 88.0          # probes under the 26w reference low (95)
cl[35] = 99.0          # closes back above it
w = bars(n, freq='W-FRI', close=cl, low=lo, high=np.full(n, 105.0))
fa, probe = m.failed_auction_low(w)
check('failed low detected', fa is True and probe == 88.0)
lo2 = lo.copy(); lo2[38] = 87.0     # later week trades below the probe...
cl2 = cl.copy(); cl2[38] = 87.5     # ...and STAYS below the old reference
w2 = bars(n, freq='W-FRI', close=cl2, low=lo2, high=np.full(n, 105.0))
fa2, _ = m.failed_auction_low(w2)
check('accepted breakdown is NOT a failed low', fa2 is False)

# --- 6. weekly breakout + acceptance -------------------------------------
n = 30
cl = np.full(n, 100.0); hi = np.full(n, 102.0); lo = np.full(n, 98.0)
vol = np.full(n, 1e6)
cl[-2:] = [106.0, 108.0]; hi[-2:] = [107.0, 109.0]; lo[-2:] = [104.0, 106.0]
vol[-2:] = 3e6          # heavy volume beyond the bracket -> value migrates
w = bars(n, freq='W-FRI', close=cl, high=hi, low=lo, vol=vol)
wf = m.weekly_features(w)
check('breakout above 13w bracket detected', wf['breakout_up'] is True)
check('two closes outside + value migration = acceptance', wf['acceptance_up'] is True)
flat = m.weekly_features(bars(30, freq='W-FRI'))
check('flat series: no breakout, no failure', not flat['breakout_up'] and not flat['failed_low'])

# --- 7. alignment score bounds & weekly dominance ------------------------
best_w = {'weekly_ok': True, 'failed_low': True, 'value_migration_up': True,
          'otf_up_weeks': 4, 'vol_up_down_ratio': 1.5, 'breakout_up': True,
          'compression_4_26': 0.5}
best_m = {'monthly_ok': True, 'm_context': 1, 'm_value_migration_up': True}
best_d = {'daily_ok': True, 'd_above_20d_bracket': True, 'd_excess_low': True,
          'd_accepts_weekly_break': True}
none_ = {}
top = m.alignment(best_m, best_w, best_d)['alignment_score']
w_only = m.alignment(none_, best_w, none_)['alignment_score']
m_only = m.alignment(best_m, none_, none_)['alignment_score']
d_only = m.alignment(none_, none_, best_d)['alignment_score']
check('full confluence scores 100', top == 100.0)
check('weekly leg alone outweighs monthly and daily combined',
      w_only > m_only + d_only - 1e-9 and w_only == 50.0)
check('labels: failed_auction_low wins when no acceptance',
      m.alignment(none_, {**best_w, 'acceptance_up': False}, none_)['auction_label']
      == 'failed_auction_low')

# --- 8. geometry ---------------------------------------------------------
g = m.geometry({'weekly_ok': True, 'close': 100.0, 'poc_26w': 110.0,
                'vah_26w': 115.0, 'failed_low_level': 95.0,
                'bracket_low': 90.0})
check('RR uses failed-low invalidation and POC destination',
      g['destination'] == 110.0 and g['invalidation'] == 95.0
      and g['rr_struct'] == 2.0)
g2 = m.geometry({'weekly_ok': True, 'close': 94.0, 'poc_26w': 110.0,
                 'vah_26w': 115.0, 'failed_low_level': 95.0,
                 'bracket_low': 90.0})
check('close below invalidation -> no RR', np.isnan(g2['rr_struct']))

print(f"\n{'ALL TESTS PASSED' if fails == 0 else f'{fails} FAILURES'}")
raise SystemExit(fails)
