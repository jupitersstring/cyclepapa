#!/usr/bin/env python3
"""Mind Over Markets / Dalton-style asymmetric setup screener.
Computes Market Profile / Auction Market Theory signals on weekly bars.
"""
import pandas as pd, numpy as np, yfinance as yf, sys, time, warnings, argparse
warnings.filterwarnings('ignore')

ap = argparse.ArgumentParser()
ap.add_argument('--universe', required=True)
ap.add_argument('--out', required=True)
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().unique().tolist()
syms = [s for s in syms if isinstance(s,str) and not ('-' in s or s.endswith('U') or s.endswith('W'))]
print(f"universe: {len(syms)}", file=sys.stderr)

def screen_one(t, df):
    if df is None or len(df) < 30: return None
    df = df.dropna()
    if len(df) < 30: return None
    df = df.copy()

    # Last 12 weeks for analysis
    last = df.iloc[-1]
    prev = df.iloc[-2]

    px       = float(last['Close'])
    px_open  = float(last['Open'])
    px_high  = float(last['High'])
    px_low   = float(last['Low'])
    rng      = px_high - px_low
    if rng <= 0: return None

    p_open   = float(prev['Open'])
    p_high   = float(prev['High'])
    p_low    = float(prev['Low'])
    p_close  = float(prev['Close'])
    p_rng    = p_high - p_low

    out = {'ticker': t, 'price': px}

    # ---- 1. COMPOSITE WEEK CLASSIFICATION ----
    # Open in bottom quartile = Buying Composite (market spent most time above open)
    open_quartile = (px_open - px_low) / rng
    if open_quartile < 0.25:    out['composite_week'] = 'BUYING'
    elif open_quartile > 0.75:  out['composite_week'] = 'SELLING'
    else:                       out['composite_week'] = 'NEUTRAL'
    out['close_quartile'] = (px - px_low) / rng  # 0=close on low, 1=close on high

    # ---- 2. 3-TO-I WEEK (BULLISH) — 94% stat ----
    # Conditions:
    #   - Open in bottom quartile (initiative tail bottom)
    #   - Close in top quartile
    #   - Range extension UP (high > prior high)
    #   - Higher low (low > prior low)
    out['three_to_i_bull'] = (
        open_quartile < 0.25 and
        out['close_quartile'] > 0.75 and
        px_high > p_high and
        px_low > p_low
    )
    # 3-to-I bearish
    out['three_to_i_bear'] = (
        open_quartile > 0.75 and
        out['close_quartile'] < 0.25 and
        px_low < p_low and
        px_high < p_high
    )

    # ---- 3. NEUTRAL-EXTREME WEEK (92% stat) ----
    # Outside week (high > prior high AND low < prior low) closing on one extreme
    outside = px_high > p_high and px_low < p_low
    out['neutral_extreme_bull'] = outside and out['close_quartile'] > 0.75
    out['neutral_extreme_bear'] = outside and out['close_quartile'] < 0.25

    # ---- 4. ONE-TIMEFRAMING STATUS ----
    # Count consecutive weeks where each low > prior low (one-tf higher)
    streak_up = 0
    for i in range(2, min(len(df)+1, 20)):
        if df['Low'].iloc[-i] > df['Low'].iloc[-i-1]:
            streak_up += 1
        else:
            break
    out['otf_higher_streak'] = streak_up
    streak_dn = 0
    for i in range(2, min(len(df)+1, 20)):
        if df['High'].iloc[-i] < df['High'].iloc[-i-1]:
            streak_dn += 1
        else:
            break
    out['otf_lower_streak'] = streak_dn

    # OTF cessation signal — was OTF higher 3+ wks but most recent week broke
    # (low < prior low after sustained higher-lows)
    # Look at weeks N-7 through N-2 for consistency, then last week breaks
    if len(df) >= 8:
        prior_otf_up = all(df['Low'].iloc[-i] > df['Low'].iloc[-i-1] for i in range(2, 8))
        out['otf_up_broke'] = prior_otf_up and (px_low < p_low)
        prior_otf_dn = all(df['High'].iloc[-i] < df['High'].iloc[-i-1] for i in range(2, 8))
        out['otf_dn_broke'] = prior_otf_dn and (px_high > p_high)
    else:
        out['otf_up_broke'] = False
        out['otf_dn_broke'] = False

    # ---- 5. BALANCE-AREA + BREAKOUT DETECTION ----
    # Look at last 8 weeks. Compute median range and overlap.
    w8 = df.tail(8)
    w8_high = float(w8['High'].max())
    w8_low  = float(w8['Low'].min())
    w8_rng_pct = (w8_high / w8_low - 1) * 100 if w8_low > 0 else np.nan

    # Balance condition: 8w range tight (<20%), most weeks overlap
    overlaps = 0
    for i in range(1, 8):
        h_i, l_i = float(w8['High'].iloc[-i]), float(w8['Low'].iloc[-i])
        h_p, l_p = float(w8['High'].iloc[-i-1]) if i+1 <= len(w8) else h_i, float(w8['Low'].iloc[-i-1]) if i+1 <= len(w8) else l_i
        if min(h_i, h_p) - max(l_i, l_p) > 0:
            overlaps += 1
    out['balance_overlaps'] = overlaps
    out['balance_8w_rng_pct'] = w8_rng_pct

    # Balance breakout this week
    prior7_high = float(df['High'].iloc[-9:-1].max()) if len(df) >= 9 else float(df['High'].iloc[:-1].max())
    prior7_low  = float(df['Low'].iloc[-9:-1].min()) if len(df) >= 9 else float(df['Low'].iloc[:-1].min())
    out['breakout_above_balance'] = (overlaps >= 5 and w8_rng_pct < 20 and px_high > prior7_high)
    out['breakout_below_balance'] = (overlaps >= 5 and w8_rng_pct < 20 and px_low < prior7_low)

    # ---- 6. FAILED AUCTION → OUTSIDE WEEK ----
    # Prior week probed beyond balance (above OR below balance high) but failed
    # This week reverses with outside bar in opposite direction
    if len(df) >= 10:
        bal9_hi = float(df['High'].iloc[-9:-2].max())
        bal9_lo = float(df['Low'].iloc[-9:-2].min())
        # Last week probed above bal but closed back inside, then this week outside-down
        prev_probed_up = p_high > bal9_hi and p_close < bal9_hi
        out['failed_up_outside_down'] = prev_probed_up and outside and out['close_quartile'] < 0.25
        prev_probed_dn = p_low < bal9_lo and p_close > bal9_lo
        out['failed_dn_outside_up'] = prev_probed_dn and outside and out['close_quartile'] > 0.75
    else:
        out['failed_up_outside_down'] = False
        out['failed_dn_outside_up'] = False

    # ---- 7. SPIKE DETECTION (last week was a spike) ----
    # Prior week: large range vs avg, close near one extreme
    avg_rng = float(df['High'].subtract(df['Low']).tail(13).mean())
    p_close_quart = (p_close - p_low) / p_rng if p_rng > 0 else 0.5
    spike_up = p_rng > 1.5 * avg_rng and p_close_quart > 0.75
    spike_dn = p_rng > 1.5 * avg_rng and p_close_quart < 0.25
    out['prior_week_spike_up'] = spike_up
    out['prior_week_spike_dn'] = spike_dn
    # This week's resolution
    if spike_up:
        # Spike top reference = p_high. Spike bottom = at or near p_open or breakout level
        spike_top = p_high
        spike_bot = (p_high + p_low) / 2  # approximate spike midpoint
        if px_open > spike_top:
            out['spike_resolution'] = 'CONTINUATION'
        elif px_open < spike_bot:
            out['spike_resolution'] = 'REJECTION'
        else:
            out['spike_resolution'] = 'ACCEPTANCE'
    elif spike_dn:
        spike_bot = p_low
        spike_top = (p_high + p_low) / 2
        if px_open < spike_bot:
            out['spike_resolution'] = 'CONTINUATION'
        elif px_open > spike_top:
            out['spike_resolution'] = 'REJECTION'
        else:
            out['spike_resolution'] = 'ACCEPTANCE'
    else:
        out['spike_resolution'] = ''

    # ---- 8. P-FORMATION (short-covering rally — fade signal) ----
    # After downtrend (prior 12wk return < -10%), recent rally with descending highs + flat volume
    if len(df) >= 16:
        ret_12_4 = (p_close / float(df['Close'].iloc[-16]) - 1) * 100  # 12wk return ending 4 wks ago
        recent4_highs = [float(df['High'].iloc[-i]) for i in range(4, 0, -1)]
        descending_highs = all(recent4_highs[i] >= recent4_highs[i+1] for i in range(3))
        recent4_vol = df['Volume'].tail(4).mean()
        prior4_vol  = df['Volume'].iloc[-8:-4].mean()
        vol_not_expanding = recent4_vol <= prior4_vol * 1.1
        out['p_formation_short_cover'] = (ret_12_4 < -10) and descending_highs and vol_not_expanding
    else:
        out['p_formation_short_cover'] = False

    # ---- 9. b-FORMATION (long liquidation — fade signal) ----
    if len(df) >= 16:
        ret_12_4 = (p_close / float(df['Close'].iloc[-16]) - 1) * 100
        recent4_lows = [float(df['Low'].iloc[-i]) for i in range(4, 0, -1)]
        ascending_lows = all(recent4_lows[i] <= recent4_lows[i+1] for i in range(3))
        recent4_vol = df['Volume'].tail(4).mean()
        prior4_vol  = df['Volume'].iloc[-8:-4].mean()
        vol_not_expanding = recent4_vol <= prior4_vol * 1.1
        out['b_formation_long_liq'] = (ret_12_4 > 10) and ascending_lows and vol_not_expanding
    else:
        out['b_formation_long_liq'] = False

    # ---- 10. POC MIGRATION (volume-weighted average price across 4 wks) ----
    # Use VWAP-style as POC proxy. Compare last week to 4-week avg.
    def vwap(window):
        tp = (window['High'] + window['Low'] + window['Close']) / 3
        return (tp * window['Volume']).sum() / window['Volume'].sum() if window['Volume'].sum() > 0 else np.nan
    poc_now = vwap(df.tail(4))
    poc_prev = vwap(df.iloc[-8:-4]) if len(df) >= 8 else np.nan
    out['poc_now'] = poc_now
    out['poc_migration_pct'] = (poc_now / poc_prev - 1) * 100 if not np.isnan(poc_prev) and poc_prev > 0 else np.nan
    out['px_above_poc'] = px > poc_now if not np.isnan(poc_now) else False

    # ---- 11. VALUE AREA RULE trigger ----
    # Open outside prior week's range AND accepted back inside
    opened_outside_up = px_open > p_high
    opened_outside_dn = px_open < p_low
    accepted_back_in = (px_low <= p_high and px_high >= p_low)
    out['value_area_rule_bull'] = opened_outside_dn and accepted_back_in and px > p_high  # opened low, traversed up through prior range
    out['value_area_rule_bear'] = opened_outside_up and accepted_back_in and px < p_low  # opened high, traversed down

    # ---- 12. UNSECURED HIGHS / LOWS (poor extremes) ----
    # An unsecured high = high made without a tail. Approximation: high formed in last 1-2 wks AND closed near that high
    high_5w = float(df['High'].tail(5).max())
    high_5w_idx = df['High'].tail(5).values.argmax()
    high_5w_close = float(df['Close'].tail(5).iloc[high_5w_idx])
    high_5w_low = float(df['Low'].tail(5).iloc[high_5w_idx])
    high_5w_rng = high_5w - high_5w_low
    out['unsecured_high'] = (high_5w_rng > 0) and ((high_5w - high_5w_close) / high_5w_rng < 0.2)  # close within top 20%

    low_5w = float(df['Low'].tail(5).min())
    low_5w_idx = df['Low'].tail(5).values.argmin()
    low_5w_close = float(df['Close'].tail(5).iloc[low_5w_idx])
    low_5w_high = float(df['High'].tail(5).iloc[low_5w_idx])
    low_5w_rng = low_5w_high - low_5w
    out['unsecured_low'] = (low_5w_rng > 0) and ((low_5w_close - low_5w) / low_5w_rng < 0.2)

    # ---- 13. ROTATION FACTOR (last 4 weeks) ----
    rf = 0
    for i in range(0, 4):
        h_i = float(df['High'].iloc[-(i+1)])
        h_p = float(df['High'].iloc[-(i+2)])
        l_i = float(df['Low'].iloc[-(i+1)])
        l_p = float(df['Low'].iloc[-(i+2)])
        rf += (1 if h_i > h_p else -1 if h_i < h_p else 0)
        rf += (1 if l_i > l_p else -1 if l_i < l_p else 0)
    out['rotation_factor_4w'] = rf  # range -8 to +8

    # ---- 14. VOLUME context ----
    avg_vol = float(df['Volume'].iloc[-13:-1].mean())
    out['vol_vs_avg'] = float(df['Volume'].iloc[-1]) / avg_vol if avg_vol > 0 else np.nan
    p_vol_vs_avg = float(df['Volume'].iloc[-2]) / avg_vol if avg_vol > 0 else np.nan
    out['prev_vol_vs_avg'] = p_vol_vs_avg

    # ---- 15. OFF-HIGH context ----
    high_52w = float(df['High'].tail(52).max()) if len(df) >= 52 else float(df['High'].max())
    out['pct_below_52w_high'] = (high_52w / px - 1) * 100

    return out

results = []
chunk = 50
for i in range(0, len(syms), chunk):
    batch = syms[i:i+chunk]
    try:
        data = yf.download(' '.join(batch), period='3y', interval='1wk',
                          group_by='ticker', threads=True, progress=False, auto_adjust=True)
        for t in batch:
            try:
                df = data[t].copy() if isinstance(data.columns, pd.MultiIndex) else data.copy()
                m = screen_one(t, df)
                if m: results.append(m)
            except Exception:
                pass
        if (i+len(batch)) % 500 == 0 or i+len(batch) == len(syms):
            print(f"  {i+len(batch)}/{len(syms)} processed; kept {len(results)}", file=sys.stderr)
    except Exception as e:
        print(f"  batch err {str(e)[:60]}", file=sys.stderr)
    time.sleep(1.0)

out = pd.DataFrame(results)
out.to_csv(args.out, index=False)
print(f"DONE: {len(out)} rows -> {args.out}")
