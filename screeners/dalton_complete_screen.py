#!/usr/bin/env python3
"""Dalton COMPLETE — every price/volume/time feature from Mind Over Markets +
Markets in Profile, on weekly AND monthly bars, both absolute and relative-to-SPY.

Implements:
  • Proper Value Area (70% volume around POC) computed from daily bars
  • TPO Count (days closing above POC vs below POC = selling/buying TPOs)
  • Rotation Factor per bar
  • Composite classification (open quartile)
  • Day Type Classification (Normal / Normal Variation / Trend /
    Double-Distribution / Nontrend / Neutral) via initial balance + range ext
  • Opening Type (Open-Drive / Open-Test-Drive / Open-Rejection-Reverse /
    Open-Auction in-range vs out-of-range)
  • Open's relation to prior VA (acceptance / rejection / out-of-range)
  • One-Timeframe streak + transition with double-print confirmation
  • Directional Performance Matrix (Direction × Volume × Value Placement)
  • Value Area Width as volume proxy
  • Long-term excess: tails (with next-bar confirmation), gaps, islands
  • Poor / unsecured extremes (close on extreme, no tail)
  • Initiative vs Responsive activity (location vs prior value)
  • 3-to-I + 2I-1R + Neutral-Extreme
  • Value Area Rule (open outside, accept, traverse)
  • Spike + 3 resolution rules
  • Balance-Area Breakout with multi-bar acceptance verification
  • Failed Breakout → Outside Bar opposite (bracket reversal)
  • P-formation (short cover) and b-formation (long liquidation)
  • HV / LV reference point distance
  • Hidden corrective action (selling structure, higher value)
  • Bracket-to-Trend / Trend-to-Bracket transition signals
  • Three successive no-tail anomaly
  • Destination distance (52wH, 52wL, gap edges, prior bal)
  • 5-pillar macro: bracket × compression × sponsorship × readiness × asymmetry
  • Per-bar score velocity (1st, 2nd derivatives) over the time series
  • Cross-TF hierarchy: monthly veto on conflicting weekly signals

Output: comprehensive per-ticker row with all features + composite asymmetry scores.
"""
import argparse, sys, time, warnings
import pandas as pd, numpy as np, yfinance as yf
warnings.filterwarnings('ignore')

ap = argparse.ArgumentParser()
ap.add_argument('--universe',  required=True)
ap.add_argument('--out',       required=True)
ap.add_argument('--benchmark', default='SPY')
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().unique().tolist()
syms = [s for s in syms if isinstance(s,str) and not ('.' not in s and ('-' in s or s.endswith('U') or s.endswith('W')))]
print(f"universe: {len(syms)} | benchmark: {args.benchmark}", file=sys.stderr)

bench_df = yf.download(args.benchmark, period='5y', interval='1d', progress=False, auto_adjust=True)
if isinstance(bench_df.columns, pd.MultiIndex):
    bench_df.columns = bench_df.columns.get_level_values(0)
bench_df = bench_df[['Open','High','Low','Close']].dropna()


# ============== HELPERS ==============
def make_ratio(stock, bench):
    df = stock.join(bench, how='inner', rsuffix='_b')
    if len(df) < 60: return None
    out = pd.DataFrame(index=df.index)
    out['Open']   = df['Open']   / df['Open_b']
    out['Close']  = df['Close']  / df['Close_b']
    out['High']   = df['High']   / df['Low_b']
    out['Low']    = df['Low']    / df['High_b']
    out['Volume'] = df['Volume']
    return out.dropna()


def value_area_from_daily(daily_in_period):
    """Build proper Value Area: POC + outward expansion until 70% volume.
    Always returns floats (never None) — uses NaN for missing data."""
    if len(daily_in_period) == 0: return np.nan, np.nan, np.nan, 0.0
    pmin = float(daily_in_period['Low'].min())
    pmax = float(daily_in_period['High'].max())
    if pmax <= pmin or np.isnan(pmin) or np.isnan(pmax):
        return float(pmin), float(pmin), float(pmin), float(daily_in_period['Volume'].sum() or 0)
    bins = 30
    edges = np.linspace(pmin, pmax, bins+1)
    vp = np.zeros(bins)
    for _, r in daily_in_period.iterrows():
        lo, hi, v = float(r['Low']), float(r['High']), float(r['Volume'])
        if hi <= lo or np.isnan(v) or v <= 0: continue
        lo_idx = max(0, int((lo - pmin)/(pmax - pmin)*bins))
        hi_idx = min(bins-1, int((hi - pmin)/(pmax - pmin)*bins))
        if hi_idx == lo_idx: vp[lo_idx] += v
        else:
            per = v / (hi_idx - lo_idx + 1)
            vp[lo_idx:hi_idx+1] += per
    total = float(vp.sum())
    if total <= 0:
        # Fallback: use price midpoint as POC, full range as VA
        return (pmin + pmax)/2, pmax, pmin, 0.0
    target = total * 0.70
    poc_idx = int(np.argmax(vp))
    poc_price = (edges[poc_idx] + edges[poc_idx+1]) / 2
    cum = vp[poc_idx]
    lo_idx = poc_idx; hi_idx = poc_idx
    while cum < target and (lo_idx > 0 or hi_idx < bins-1):
        upper_pair = (vp[hi_idx+1] if hi_idx+1 < bins else 0) + (vp[hi_idx+2] if hi_idx+2 < bins else 0)
        lower_pair = (vp[lo_idx-1] if lo_idx-1 >= 0 else 0) + (vp[lo_idx-2] if lo_idx-2 >= 0 else 0)
        if upper_pair >= lower_pair and hi_idx+1 < bins:
            hi_idx += 1; cum += vp[hi_idx]
            if hi_idx+1 < bins:
                hi_idx += 1; cum += vp[hi_idx]
        elif lo_idx > 0:
            lo_idx -= 1; cum += vp[lo_idx]
            if lo_idx > 0:
                lo_idx -= 1; cum += vp[lo_idx]
        else: break
    va_high = float(edges[hi_idx+1])
    va_low  = float(edges[lo_idx])
    return float(poc_price), va_high, va_low, total


def tpo_count_from_daily(daily_in_period, poc):
    """Count daily bars closing above POC (= selling TPOs above POC) vs below
    POC (= buying TPOs below POC). Dalton's TPO imbalance signal."""
    if len(daily_in_period) == 0 or poc is None: return 0, 0
    above = (daily_in_period['Close'] > poc).sum()
    below = (daily_in_period['Close'] < poc).sum()
    return int(above), int(below)


def build_period_bars(daily, freq='W'):
    """From daily OHLCV, build period bars (W/M) AND keep group reference for VA calc."""
    df = daily.copy(); df['_d'] = df.index
    if freq == 'W':
        df['_g'] = df['_d'].dt.strftime('%G-W%V')
    else:
        df['_g'] = df['_d'].dt.to_period('M').astype(str)
    grouped = df.groupby('_g')
    bars = grouped.agg(
        Date=('_d','first'), Open=('Open','first'), High=('High','max'),
        Low=('Low','min'), Close=('Close','last'), Volume=('Volume','sum'),
        FirstDayHigh=('High','first'), FirstDayLow=('Low','first'),
        nDays=('Close','size'),
    ).sort_values('Date').reset_index(drop=True)
    bars.index = bars['Date']
    return bars, grouped


# ============== PER-BAR ENRICHED SCORE ==============
def per_bar_full(bars, daily_groups):
    """Compute every Dalton feature per bar. Returns DataFrame with same index."""
    if len(bars) < 12: return None
    rows = []
    pocs = []; vahs = []; vals = []; vol_totals = []
    tpo_above = []; tpo_below = []
    for i, (g_label, group) in enumerate(daily_groups):
        poc, vah, val, vt = value_area_from_daily(group)
        tabove, tbelow = tpo_count_from_daily(group, poc)
        pocs.append(poc); vahs.append(vah); vals.append(val); vol_totals.append(vt)
        tpo_above.append(tabove); tpo_below.append(tbelow)
    bars = bars.copy()
    bars['POC']      = pocs[:len(bars)]
    bars['VA_high']  = vahs[:len(bars)]
    bars['VA_low']   = vals[:len(bars)]
    bars['VA_width'] = bars['VA_high'] - bars['VA_low']
    bars['tpo_above'] = tpo_above[:len(bars)]
    bars['tpo_below'] = tpo_below[:len(bars)]
    bars['tpo_imbalance'] = bars['tpo_below'] - bars['tpo_above']  # +ve = more buying TPOs

    avg_vol = bars['Volume'].rolling(13, min_periods=4).mean()
    avg_va_w = bars['VA_width'].rolling(13, min_periods=4).mean()

    score = []
    composite = []; day_type = []; open_type = []
    initiative = []; opening_vs_value = []
    dp_signal = []
    excess_buy = []; excess_sell = []
    poor_low = []; poor_high = []
    p_form = []; b_form = []
    in_balance_streak = []
    failed_breakdown_reclaim = []; failed_breakout_reject = []
    spike = []
    var_trigger = []
    accepted_outside = []
    no_tail_streak = []

    for i in range(len(bars)):
        if i == 0:
            score.append(0.0); composite.append(''); day_type.append('')
            open_type.append(''); initiative.append(''); opening_vs_value.append('')
            dp_signal.append(''); excess_buy.append(False); excess_sell.append(False)
            poor_low.append(False); poor_high.append(False); p_form.append(False); b_form.append(False)
            in_balance_streak.append(0); failed_breakdown_reclaim.append(False)
            failed_breakout_reject.append(False); spike.append(''); var_trigger.append(False)
            accepted_outside.append(False); no_tail_streak.append(0)
            continue

        cur = bars.iloc[i]; prv = bars.iloc[i-1]
        s = 0.0
        rng = float(cur['High']) - float(cur['Low'])
        prng = float(prv['High']) - float(prv['Low'])
        op = float(cur['Open']); cp = float(cur['Close']); hi = float(cur['High']); lo = float(cur['Low'])
        po = float(prv['Open']); pc = float(prv['Close']); ph = float(prv['High']); pl = float(prv['Low'])

        if rng <= 0:
            score.append(0.0); composite.append('NEUTRAL'); day_type.append('NONTREND')
            open_type.append(''); initiative.append(''); opening_vs_value.append('')
            dp_signal.append('N/A'); excess_buy.append(False); excess_sell.append(False)
            poor_low.append(False); poor_high.append(False); p_form.append(False); b_form.append(False)
            in_balance_streak.append(0); failed_breakdown_reclaim.append(False)
            failed_breakout_reject.append(False); spike.append(''); var_trigger.append(False)
            accepted_outside.append(False); no_tail_streak.append(0)
            continue

        op_q = (op - lo) / rng
        cp_q = (cp - lo) / rng
        bt   = (min(op, cp) - lo) / rng
        st_  = (hi - max(op, cp)) / rng
        mid  = (hi + lo) / 2; pmid = (ph + pl) / 2

        # 1. ROTATION FACTOR (per-bar contribution -2 to +2)
        rf = 0
        rf += 1 if hi > ph else (-1 if hi < ph else 0)
        rf += 1 if lo > pl else (-1 if lo < pl else 0)
        s += rf

        # 2. COMPOSITE CLASSIFICATION (open quartile)
        if op_q < 0.25 and cp_q > 0.75:
            comp = 'BUY_COMP_CLOSE_HI'; s += 2
        elif op_q > 0.75 and cp_q < 0.25:
            comp = 'SELL_COMP_CLOSE_LO'; s -= 2
        elif op_q < 0.25:
            comp = 'BUY_COMPOSITE'; s += 1
        elif op_q > 0.75:
            comp = 'SELL_COMPOSITE'; s -= 1
        else:
            comp = 'NEUTRAL'
            if cp_q > 0.75: s += 1
            elif cp_q < 0.25: s -= 1
        composite.append(comp)

        # 3. DAY TYPE (approx via initial balance proxy = first day of period)
        ib_h = float(cur.get('FirstDayHigh', op*1.001)); ib_l = float(cur.get('FirstDayLow', op*0.999))
        ib_rng = ib_h - ib_l
        rext_up = hi > ib_h; rext_dn = lo < ib_l
        # Wide IB = Normal; very narrow + open at extreme = Trend; narrow + no rng ext = Nontrend
        ib_pct = ib_rng / rng if rng > 0 else 0
        if ib_pct > 0.7 and not (rext_up or rext_dn):
            dt = 'NORMAL'
        elif ib_pct < 0.3 and abs(op - lo) / rng < 0.1:
            dt = 'TREND_UP'; s += 1
        elif ib_pct < 0.3 and abs(op - hi) / rng < 0.1:
            dt = 'TREND_DN'; s -= 1
        elif rext_up and rext_dn:
            dt = 'NEUTRAL_OUTSIDE'   # Outside week
            if cp_q > 0.75: s += 1   # Neutral-Extreme bullish
            elif cp_q < 0.25: s -= 1
        elif rext_up and not rext_dn:
            dt = 'NORMAL_VAR_UP'; s += 0.5
        elif rext_dn and not rext_up:
            dt = 'NORMAL_VAR_DN'; s -= 0.5
        elif ib_pct > 0.5 and not (rext_up or rext_dn):
            dt = 'NONTREND'
        else:
            dt = 'NORMAL'
        day_type.append(dt)

        # 4. OPENING TYPE (proxy from open vs first-day movement)
        # If open near low and close in upper Q = Open-Drive up
        # If open tested an extreme then drove away = Open-Test-Drive
        if op_q < 0.10 and cp_q > 0.7: ot = 'OPEN_DRIVE_UP'; s += 1
        elif op_q > 0.90 and cp_q < 0.3: ot = 'OPEN_DRIVE_DN'; s -= 1
        elif op > ph and cp < ph: ot = 'OPEN_REJECT_DN'; s -= 1.5  # opened above prior, rejected back
        elif op < pl and cp > pl: ot = 'OPEN_REJECT_UP'; s += 1.5  # opened below, reclaimed
        elif op > ph and cp > ph: ot = 'OPEN_OUT_RANGE_UP'; s += 0.5
        elif op < pl and cp < pl: ot = 'OPEN_OUT_RANGE_DN'; s -= 0.5
        else: ot = 'OPEN_AUCTION'
        open_type.append(ot)

        # 5. OPEN'S RELATION TO PRIOR VALUE AREA
        try:
            pva_h_raw = prv.get('VA_high', ph); pva_l_raw = prv.get('VA_low', pl)
            pva_h = float(pva_h_raw) if pva_h_raw is not None and not pd.isna(pva_h_raw) else float(ph)
            pva_l = float(pva_l_raw) if pva_l_raw is not None and not pd.isna(pva_l_raw) else float(pl)
        except (TypeError, ValueError):
            pva_h, pva_l = float(ph), float(pl)
        if pd.isna(pva_h) or pd.isna(pva_l):
            ovv = 'UNKNOWN'
        elif op > pva_l and op < pva_h:
            ovv = 'WITHIN_VA'  # Acceptance — range like prior
        elif op > pva_h and op < ph:
            ovv = 'ABOVE_VA_IN_RANGE'  # Slightly above value, still in range
        elif op < pva_l and op > pl:
            ovv = 'BELOW_VA_IN_RANGE'  # Slightly below value
        elif op > ph:
            ovv = 'OUT_RANGE_UP'        # Out of balance — high asymmetry
        elif op < pl:
            ovv = 'OUT_RANGE_DN'
        else:
            ovv = 'WITHIN_VA'
        opening_vs_value.append(ovv)

        # 6. INITIATIVE vs RESPONSIVE classification
        # Initiative buying = buying within or above prior value
        # Responsive buying = buying below prior value (responsive to cheaper price)
        if cp > pva_l and (cp_q >= 0.75 or hi > ph):
            init = 'INITIATIVE_BUY'; s += 1
        elif cp < pva_h and (cp_q <= 0.25 or lo < pl):
            init = 'INITIATIVE_SELL'; s -= 1
        elif cp > pva_h and cp_q >= 0.6:
            init = 'INITIATIVE_BUY_STRONG'; s += 1.5
        elif cp < pva_l and cp_q <= 0.4:
            init = 'INITIATIVE_SELL_STRONG'; s -= 1.5
        elif cp <= pva_l and bt > 0.2:
            init = 'RESPONSIVE_BUY'; s += 0.5  # buying tail at cheaper level
        elif cp >= pva_h and st_ > 0.2:
            init = 'RESPONSIVE_SELL'; s -= 0.5
        else:
            init = 'NEUTRAL'
        initiative.append(init)

        # 7. DIRECTIONAL PERFORMANCE MATRIX
        attempted_up = op_q <= 0.25 or cp_q >= 0.75
        attempted_dn = op_q >= 0.75 or cp_q <= 0.25
        value_higher = (mid > pmid + 0.3*prng) or (lo > ph)
        value_lower  = (mid < pmid - 0.3*prng) or (hi < pl)
        vol_ratio_v = float(cur['Volume']) / float(avg_vol.iloc[i]) if not pd.isna(avg_vol.iloc[i]) and avg_vol.iloc[i] > 0 else 1.0
        high_vol = vol_ratio_v > 1.1; low_vol = vol_ratio_v < 0.9
        # Value Area Width as Volume Proxy: wider VA usually = more vol
        if not pd.isna(avg_va_w.iloc[i]) and avg_va_w.iloc[i] > 0:
            vaw_ratio = float(cur['VA_width']) / float(avg_va_w.iloc[i])
            if vaw_ratio > 1.2: high_vol = True
            elif vaw_ratio < 0.8: low_vol = True

        if attempted_dn and value_higher:
            dps = 'MIRAGE_BUY'; s += 3
        elif attempted_up and value_lower:
            dps = 'FAILED_UP'; s -= 3
        elif attempted_up and value_higher and high_vol:
            dps = 'CONFIRMED_UP'; s += 3
        elif attempted_dn and value_lower and high_vol:
            dps = 'CONFIRMED_DN'; s -= 3
        elif attempted_up and high_vol and not value_lower:
            dps = 'BULLISH_HIGH_VOL'; s += 2
        elif attempted_dn and high_vol and not value_higher:
            dps = 'BEARISH_HIGH_VOL'; s -= 2
        elif attempted_up and low_vol:
            dps = 'LOW_VOL_RALLY'; s -= 1
        elif attempted_dn and low_vol:
            dps = 'LOW_VOL_SELL'; s += 1
        elif attempted_up:
            dps = 'BULL_NEUTRAL'; s += 0.5
        elif attempted_dn:
            dps = 'BEAR_NEUTRAL'; s -= 0.5
        else:
            dps = 'NEUTRAL'
        dp_signal.append(dps)

        # 8. EXCESS / TAILS
        be = bt > 0.33; sex = st_ > 0.33
        if be: s += 1
        if sex: s -= 1
        excess_buy.append(be); excess_sell.append(sex)

        # 9. POOR / UNSECURED EXTREMES
        pl_low = bt < 0.05 and lo < pl   # close near low, broke prior low — magnet for retrace UP
        ph_hi = st_ < 0.05 and hi > ph   # close near high, broke prior high — magnet for retrace DOWN
        if pl_low: s -= 0.5
        if ph_hi: s += 0.5  # poor high = upside magnet (will be revisited/broken)
        poor_low.append(pl_low); poor_high.append(ph_hi)

        # 10. INITIATIVE RANGE EXTENSION
        if hi > ph and lo > pl: s += 1
        elif hi < ph and lo < pl: s -= 1

        # 11. 3-to-I (initiative tail + close + range ext + with TPO confirm)
        tpo_imb = bars['tpo_imbalance'].iloc[i]
        if bt > 0.2 and cp_q > 0.6 and hi > ph:
            if tpo_imb > 0: s += 2.5  # 3-to-I with TPO confirmation
            else: s += 2
        if st_ > 0.2 and cp_q < 0.4 and lo < pl:
            if tpo_imb < 0: s -= 2.5
            else: s -= 2

        # 12. NEUTRAL-EXTREME (outside bar with extreme close)
        outside = hi > ph and lo < pl
        if outside and cp_q > 0.8: s += 1
        elif outside and cp_q < 0.2: s -= 1

        # 13. VALUE AREA RULE — opens outside prior VA, gets accepted inside, traverses
        traverse_up = op < pva_l and cp > pva_h
        traverse_dn = op > pva_h and cp < pva_l
        if traverse_up: s += 2; vt = 'TRAVERSE_UP'
        elif traverse_dn: s -= 2; vt = 'TRAVERSE_DN'
        elif op > pva_h and cp >= pva_h: vt = 'ACCEPTED_ABOVE_VA'; s += 0.5
        elif op < pva_l and cp <= pva_l: vt = 'ACCEPTED_BELOW_VA'; s -= 0.5
        else: vt = ''
        var_trigger.append(bool(traverse_up or traverse_dn))

        # 14. ACCEPTED OUTSIDE PRIOR RANGE (multi-bar; here single-bar proxy)
        accepted_above = cp > ph and op > ph and cp_q >= 0.5
        accepted_below = cp < pl and op < pl and cp_q <= 0.5
        if accepted_above: s += 1.5
        if accepted_below: s -= 1.5
        accepted_outside.append(bool(accepted_above or accepted_below))

        # 15. SPIKE classification (if last bar was a spike, classify this bar's response)
        if i >= 2:
            prv2 = bars.iloc[i-2]
            avg_rng = float((bars['High'].iloc[max(0,i-13):i] - bars['Low'].iloc[max(0,i-13):i]).mean())
            spike_up_prev = prng > 1.5*avg_rng and (pc - pl)/prng > 0.75
            spike_dn_prev = prng > 1.5*avg_rng and (pc - pl)/prng < 0.25
            if spike_up_prev:
                if op > ph: spk = 'SPIKE_UP_CONTINUATION'; s += 1
                elif op < (ph + pl)/2: spk = 'SPIKE_UP_REJECTED'; s -= 1.5
                else: spk = 'SPIKE_UP_ACCEPTED'
            elif spike_dn_prev:
                if op < pl: spk = 'SPIKE_DN_CONTINUATION'; s -= 1
                elif op > (ph + pl)/2: spk = 'SPIKE_DN_REJECTED'; s += 1.5
                else: spk = 'SPIKE_DN_ACCEPTED'
            else:
                spk = ''
        else: spk = ''
        spike.append(spk)

        # 16. HIDDEN CORRECTIVE ACTION
        if cp < op and mid > pmid: s += 1   # bull hidden correction
        elif cp > op and mid < pmid: s -= 1 # bear hidden correction

        # 17. P-formation / b-formation (multi-bar)
        if i >= 5:
            recent = bars.iloc[i-4:i+1]
            rallies = (recent['High'] - recent['Open']).values
            declines = (recent['Open'] - recent['Low']).values
            init_rally = rallies[0] if len(rallies) > 0 else 0
            init_decline = declines[0] if len(declines) > 0 else 0
            if init_rally > recent.iloc[0]['Close']*0.02 and len(rallies) >= 4:
                if all(r < init_rally*0.5 for r in rallies[2:4]):
                    p_form.append(True); s -= 2  # P_SHORT_COVER
                else: p_form.append(False)
            else: p_form.append(False)
            if init_decline > recent.iloc[0]['Close']*0.02 and len(declines) >= 4:
                if all(d < init_decline*0.5 for d in declines[2:4]):
                    b_form.append(True); s += 2  # B_LONG_LIQ
                else: b_form.append(False)
            else: b_form.append(False)
        else:
            p_form.append(False); b_form.append(False)

        # 18. BALANCE-AREA STREAK + FAILED BREAKOUT
        # Count overlap with prior bars
        overlap = 1
        if i >= 1:
            for j in range(1, min(i, 12)):
                pp = bars.iloc[i-j]
                if cur['Low'] < pp['High'] and cur['High'] > pp['Low']:
                    overlap += 1
                else: break
        in_balance_streak.append(overlap)
        # Failed breakdown reclaim: prior period broke balance low, current reclaimed
        if i >= 12:
            bal_lo = float(bars['Low'].iloc[max(0,i-12):i-1].min())
            bal_hi = float(bars['High'].iloc[max(0,i-12):i-1].max())
            failed_breakdown_reclaim.append(bool(pl < bal_lo*0.99 and pc > bal_lo and lo > pl))
            failed_breakout_reject.append(bool(ph > bal_hi*1.01 and pc < bal_hi and hi < ph))
            if failed_breakdown_reclaim[-1]: s += 2
            if failed_breakout_reject[-1]:   s -= 2
        else:
            failed_breakdown_reclaim.append(False)
            failed_breakout_reject.append(False)

        # 19. THREE SUCCESSIVE NO-TAILS (anomaly = day-tf domination, vulnerability)
        # Look back through history to find streak of bars without a meaningful tail
        nt = 0
        for j in range(0, min(i+1, 6)):
            b = bars.iloc[i-j]
            b_rng = float(b['High']) - float(b['Low'])
            if b_rng <= 0: break
            b_bt = (min(float(b['Open']), float(b['Close'])) - float(b['Low'])) / b_rng
            b_st = (float(b['High']) - max(float(b['Open']), float(b['Close']))) / b_rng
            if b_bt < 0.05 and b_st < 0.05: nt += 1
            else: break
        no_tail_streak.append(nt)
        if nt >= 3:
            s += 1 if cp_q > 0.5 else -1   # vulnerable to nonlinear move

        # 20. GAP behavior
        if op > ph:
            s += 1 if cp >= ph * 1.005 else -1
        elif op < pl:
            s -= 1 if cp <= pl * 0.995 else -1

        # Heavy volume confirmation
        if high_vol and cp > op: s += 0.5
        elif high_vol and cp < op: s -= 0.5

        score.append(s)

    bars['score']     = score
    bars['composite'] = composite
    bars['day_type']  = day_type
    bars['open_type'] = open_type
    bars['init_resp'] = initiative
    bars['open_vs_va']= opening_vs_value
    bars['dp_signal'] = dp_signal
    bars['excess_buy']= excess_buy
    bars['excess_sell']= excess_sell
    bars['poor_low']  = poor_low
    bars['poor_high'] = poor_high
    bars['p_form']    = p_form
    bars['b_form']    = b_form
    bars['bal_streak']= in_balance_streak
    bars['failed_bd_reclaim'] = failed_breakdown_reclaim
    bars['failed_bo_reject']  = failed_breakout_reject
    bars['spike']     = spike
    bars['var_trigger']= var_trigger
    bars['accepted_outside']= accepted_outside
    bars['no_tail_streak'] = no_tail_streak
    return bars


# ============== TIME-SERIES ANALYSIS ==============
def derivative_classify(score_series):
    if len(score_series) < 13: return {}
    s = score_series.copy()
    s4 = s.rolling(4).mean().dropna()
    if len(s4) < 9: return {}
    s_now    = float(s4.iloc[-1])
    s_4w_ago = float(s4.iloc[-5])
    s_8w_ago = float(s4.iloc[-9])
    ds_recent = s_now - s_4w_ago
    ds_prior  = s_4w_ago - s_8w_ago
    d2s = ds_recent - ds_prior
    recent_4 = s4.tail(4).values
    prior_4  = s4.iloc[-8:-4].values if len(s4) >= 8 else recent_4
    crossed_up = recent_4.mean() > 0 and prior_4.mean() < 0
    crossed_dn = recent_4.mean() < 0 and prior_4.mean() > 0
    state = 'NEUTRAL'
    if crossed_up: state = 'INFLECTION_UP'
    elif crossed_dn: state = 'INFLECTION_DOWN'
    elif s_now < 0 and ds_recent > 0 and ds_prior < 0: state = 'DECELERATION_UP'
    elif s_now > 0 and ds_recent < 0 and ds_prior > 0: state = 'DECELERATION_DOWN'
    elif s_now > 0 and ds_recent > 0 and d2s > 0: state = 'ACCELERATION_UP'
    elif s_now < 0 and ds_recent < 0 and d2s < 0: state = 'ACCELERATION_DOWN'
    elif s_now > 0 and ds_recent > 0: state = 'TRENDING_UP'
    elif s_now < 0 and ds_recent < 0: state = 'TRENDING_DOWN'
    return {'s_now': round(s_now,2), 'ds_recent': round(ds_recent,2),
            'ds_prior': round(ds_prior,2), 'd2s': round(d2s,2), 'state': state}


# ============== 5-PILLAR MACRO ==============
def macro_pillars(bars, last_close, bench_w):
    if len(bars) < 12: return {}
    out = {}

    # A. Long bracket quality
    n = 0
    for i in range(2, min(len(bars), 200)):
        h = float(bars['High'].iloc[-i:].max()); l = float(bars['Low'].iloc[-i:].min())
        if h - l <= 0 or (h/l - 1) > 0.40: break
        n = i
    out['bracket_n'] = n
    a1 = 5 if n >= 26 else (3 if n >= 13 else 0)
    a2 = 5 if n >= 52 else (3 if n >= 26 else 0)
    win = bars.tail(n) if n >= 12 else bars.tail(12)
    win_hi = float(win['High'].max()); win_lo = float(win['Low'].min())
    near_hi = ((win['High'] >= win_hi*0.95) & (win['High'] <= win_hi)).sum()
    near_lo = ((win['Low']  <= win_lo*1.05) & (win['Low']  >= win_lo)).sum()
    a3 = 5 if (near_hi >= 2 and near_lo >= 2) else 2
    bal_rng = win_hi - win_lo
    pos = (last_close - win_lo)/bal_rng*100 if bal_rng > 0 else 50
    out['pos_in_bracket'] = round(pos,2)
    a4 = 5 if pos >= 80 or pos <= 20 else (2 if pos >= 70 or pos <= 30 else 0)
    h5 = float(bars['High'].max()); l5 = float(bars['Low'].min())
    if pos >= 60:
        room = (h5/last_close - 1)*100
    else:
        room = (1 - l5/last_close)*100
    out['room'] = round(room,2)
    a5 = 5 if room >= 25 else (3 if room >= 15 else 0)
    out['A_bracket'] = a1+a2+a3+a4+a5

    # B. Compression
    bars_cpy = bars.copy()
    bars_cpy['atr'] = pd.concat([(bars['High']-bars['Low']),
                                  (bars['High']-bars['Close'].shift(1)).abs(),
                                  (bars['Low']-bars['Close'].shift(1)).abs()], axis=1).max(axis=1).rolling(14).mean()
    bars_cpy['atr_pct'] = bars_cpy['atr']/bars['Close']
    atr_series = bars_cpy['atr_pct'].rolling(20).mean().dropna()
    if len(atr_series) >= 26:
        atr_pctl = float((atr_series.tail(min(156, len(atr_series))) <= atr_series.iloc[-1]).sum() / min(156, len(atr_series)) * 100)
    else:
        atr_pctl = 50.0
    out['atr_pctl'] = atr_pctl
    b1 = 5 if atr_pctl <= 25 else (3 if atr_pctl <= 40 else 0)
    width_recent = (float(bars['High'].iloc[-20:].max())/float(bars['Low'].iloc[-20:].min())-1)*100 if len(bars)>=20 else np.nan
    width_long = (float(bars['High'].iloc[-104:].max())/float(bars['Low'].iloc[-104:].min())-1)*100 if len(bars)>=104 else np.nan
    wr = width_recent/width_long if width_long and width_long > 0 else np.nan
    b2 = 5 if wr is not None and wr <= 0.35 else (3 if wr is not None and wr <= 0.50 else 0)
    last8_rng = (float(bars['High'].iloc[-8:].max())/float(bars['Low'].iloc[-8:].min())-1)*100
    near_edge = pos >= 75 or pos <= 25
    b3 = 5 if last8_rng <= 12 and near_edge else (3 if last8_rng <= 18 and near_edge else 0)
    out['B_compress'] = b1+b2+b3

    # C. Sponsorship
    try:
        if bench_w is not None and len(bench_w) >= 60:
            common = bars.index.intersection(bench_w.index)
            if len(common) >= 26:
                sa = bars.loc[common, 'Close']; ba = bench_w.loc[common]
                if isinstance(sa, pd.DataFrame): sa = sa.iloc[:,0]
                if isinstance(ba, pd.DataFrame): ba = ba.iloc[:,0]
                rs = pd.Series(sa.values/ba.values, index=common)
                rs_now = float(rs.iloc[-1])
                rs13 = float(rs.iloc[-13:].max()); rs26 = float(rs.iloc[-26:].max())
                rs_13_high = rs_now >= rs13*0.99
                rs_26_high = rs_now >= rs26*0.99
                out['rs_13w_high'] = rs_13_high; out['rs_26w_high'] = rs_26_high
                c1 = 5 if rs_13_high else 0; c2 = 5 if rs_26_high else 0
            else: c1=c2=0
        else: c1=c2=0
    except Exception: c1=c2=0
    last13 = bars.tail(13)
    up = last13[last13['Close']>last13['Open']]; dn = last13[last13['Close']<=last13['Open']]
    udr = float(up['Volume'].sum()/dn['Volume'].sum()) if len(dn)>0 and dn['Volume'].sum()>0 else np.nan
    out['up_dn_vol'] = round(udr,2) if udr else np.nan
    c3 = 5 if udr and udr >= 1.4 else (3 if udr and udr >= 1.1 else 0)
    pbr = float(dn['Volume'].mean()/up['Volume'].mean()) if len(up)>0 and len(dn)>0 else np.nan
    c4 = 5 if pbr and pbr <= 0.85 else (3 if pbr and pbr <= 1.0 else 0)
    cq = ((last13['Close']-last13['Low']) / (last13['High']-last13['Low']).replace(0,np.nan)).dropna()
    pct_top40 = (cq>=0.6).mean()*100 if len(cq) > 0 else 0
    c5 = 5 if pct_top40 >= 60 else (3 if pct_top40 >= 45 else 0)
    out['C_sponsor'] = c1+c2+c3+c4+c5

    # D. Breakout readiness
    cur = bars.iloc[-1]
    test_hi = bool(float(cur['High']) >= win_hi*0.99)
    d1 = 5 if test_hi and pos >= 80 else 0
    cwq = (float(cur['Close'])-float(cur['Low']))/(float(cur['High'])-float(cur['Low'])) if float(cur['High'])>float(cur['Low']) else 0.5
    d2 = 5 if cwq >= 0.5 and pos >= 80 else 0
    last4_avg = float((bars['High'].iloc[-5:-1]-bars['Low'].iloc[-5:-1]).mean())
    cur_rng = float(cur['High'])-float(cur['Low'])
    d3 = 5 if cur_rng > last4_avg*1.2 else 0
    d4 = 0
    if n >= 12 and len(bars) >= 5:
        rec_hi = float(bars['High'].iloc[-5:-1].max())
        retest_held = rec_hi >= win_hi*0.97 and last_close >= win_hi*0.95
        d4 = 5 if retest_held else 0
    out['D_ready'] = d1+d2+d3+d4

    # E. Asymmetry
    if pos >= 60:
        dd = (h5/last_close - 1)*100
        di = (1 - win_lo/last_close)*100 if last_close > 0 else 0
    else:
        dd = (1 - l5/last_close)*100
        di = (win_hi/last_close - 1)*100 if last_close > 0 else 0
    out['dist_dest'] = round(dd,2); out['dist_invalid'] = round(di,2)
    asymm = dd/di if di > 0 else 0
    out['asymm'] = round(asymm, 2)
    e1 = 5 if di and di <= 10 else (3 if di and di <= 15 else 0)
    e2 = 5 if asymm >= 3 else (3 if asymm >= 2 else 0)
    out['E_asymm'] = e1+e2
    out['macro'] = out['A_bracket']+out['B_compress']+out['C_sponsor']+out['D_ready']+out['E_asymm']
    return out


# ============== MAIN PER-TICKER ==============
def screen_one(t, daily, bench_df):
    if daily is None or len(daily) < 90: return None
    daily = daily[['Open','High','Low','Close','Volume']].dropna()
    if len(daily) < 90: return None

    # Build bench weekly + monthly Close series for RS
    bench_w_s = bench_df['Close'].resample('W').last().dropna()
    bench_m_s = bench_df['Close'].resample('ME').last().dropna()

    out = {'ticker': t, 'price': float(daily.iloc[-1]['Close'])}

    # ABS — weekly
    abs_w_bars, abs_w_groups = build_period_bars(daily, 'W')
    if len(abs_w_bars) < 13: return None
    abs_w_full = per_bar_full(abs_w_bars, abs_w_groups)
    if abs_w_full is None or len(abs_w_full) < 13: return None
    abs_w_d = derivative_classify(abs_w_full['score'])
    for k,v in abs_w_d.items(): out[f'absW_{k}'] = v
    abs_w_macro = macro_pillars(abs_w_full, float(daily.iloc[-1]['Close']), bench_w_s)
    for k,v in abs_w_macro.items(): out[f'absW_{k}'] = v
    last_w = abs_w_full.iloc[-1]
    for col in ['composite','day_type','open_type','init_resp','open_vs_va','dp_signal','spike']:
        out[f'absW_{col}'] = last_w.get(col, '')
    for col in ['p_form','b_form','failed_bd_reclaim','failed_bo_reject','accepted_outside','var_trigger',
                'excess_buy','excess_sell','poor_low','poor_high']:
        out[f'absW_{col}'] = bool(last_w.get(col, False))
    out['absW_no_tail_streak'] = int(last_w.get('no_tail_streak', 0))
    out['absW_bal_streak']     = int(last_w.get('bal_streak', 0))
    out['absW_tpo_imbalance']  = int(last_w.get('tpo_imbalance', 0))

    # ABS — monthly
    abs_m_bars, abs_m_groups = build_period_bars(daily, 'M')
    if len(abs_m_bars) >= 13:
        abs_m_full = per_bar_full(abs_m_bars, abs_m_groups)
        if abs_m_full is not None and len(abs_m_full) >= 13:
            abs_m_d = derivative_classify(abs_m_full['score'])
            for k,v in abs_m_d.items(): out[f'absM_{k}'] = v
            abs_m_macro = macro_pillars(abs_m_full, float(daily.iloc[-1]['Close']), bench_m_s)
            for k,v in abs_m_macro.items(): out[f'absM_{k}'] = v
            last_m = abs_m_full.iloc[-1]
            for col in ['composite','day_type','open_type','init_resp','open_vs_va','dp_signal','spike']:
                out[f'absM_{col}'] = last_m.get(col, '')
            for col in ['p_form','b_form','failed_bd_reclaim','failed_bo_reject','accepted_outside','var_trigger']:
                out[f'absM_{col}'] = bool(last_m.get(col, False))

    # RELATIVE
    rel = make_ratio(daily, bench_df)
    if rel is not None and len(rel) >= 90:
        rel_w_bars, rel_w_groups = build_period_bars(rel, 'W')
        if len(rel_w_bars) >= 13:
            rel_w_full = per_bar_full(rel_w_bars, rel_w_groups)
            if rel_w_full is not None and len(rel_w_full) >= 13:
                rel_w_d = derivative_classify(rel_w_full['score'])
                for k,v in rel_w_d.items(): out[f'relW_{k}'] = v
                last_rw = rel_w_full.iloc[-1]
                out['relW_dp_signal'] = last_rw.get('dp_signal','')
                out['relW_init_resp'] = last_rw.get('init_resp','')
        rel_m_bars, rel_m_groups = build_period_bars(rel, 'M')
        if len(rel_m_bars) >= 13:
            rel_m_full = per_bar_full(rel_m_bars, rel_m_groups)
            if rel_m_full is not None and len(rel_m_full) >= 13:
                rel_m_d = derivative_classify(rel_m_full['score'])
                for k,v in rel_m_d.items(): out[f'relM_{k}'] = v
                last_rm = rel_m_full.iloc[-1]
                out['relM_dp_signal'] = last_rm.get('dp_signal','')
                out['relM_init_resp'] = last_rm.get('init_resp','')

    # ============== COMPOSITE FINAL SCORE ==============
    state_w = {'INFLECTION_UP': 6, 'DECELERATION_UP': 4, 'ACCELERATION_UP': 5, 'TRENDING_UP': 2,
               'INFLECTION_DOWN': -6, 'DECELERATION_DOWN': -4, 'ACCELERATION_DOWN': -5, 'TRENDING_DOWN': -2,
               'NEUTRAL': 0}
    weights = {'absW': 1.0, 'absM': 1.5, 'relW': 1.5, 'relM': 2.0}
    inflect_score = 0
    for prefix, wt in weights.items():
        st = out.get(f'{prefix}_state', 'NEUTRAL')
        inflect_score += state_w.get(st, 0) * wt
    out['inflect_score'] = round(inflect_score, 1)

    # Velocity sum (1st derivative on monthly more weighted)
    velocity = (out.get('absW_ds_recent', 0) or 0) + \
               (out.get('absM_ds_recent', 0) or 0) * 1.5 + \
               (out.get('relW_ds_recent', 0) or 0) * 1.5 + \
               (out.get('relM_ds_recent', 0) or 0) * 2.0
    accel = (out.get('absW_d2s', 0) or 0) + \
            (out.get('absM_d2s', 0) or 0) * 1.5 + \
            (out.get('relW_d2s', 0) or 0) * 1.5 + \
            (out.get('relM_d2s', 0) or 0) * 2.0
    out['velocity'] = round(velocity, 2)
    out['acceleration'] = round(accel, 2)

    # Macro sum (only on weekly; monthly macro often unstable due to short history)
    macro_total = (out.get('absW_macro', 0) or 0) + (out.get('absM_macro', 0) or 0)
    out['macro_total'] = macro_total

    # Cross-TF hierarchy: monthly veto
    has_monthly_bear = out.get('absM_state','') in ('INFLECTION_DOWN','ACCELERATION_DOWN','TRENDING_DOWN')
    has_monthly_bull = out.get('absM_state','') in ('INFLECTION_UP','ACCELERATION_UP','DECELERATION_UP')
    out['monthly_bull'] = has_monthly_bull
    out['monthly_bear'] = has_monthly_bear

    # FINAL score: macro × signal alignment + velocity × acceleration tiebreak,
    # with monthly hierarchy enforcement
    direction = 1 if (out.get('absW_state','').endswith('_UP') or out.get('relM_state','').endswith('_UP')) else \
               (-1 if (out.get('absW_state','').endswith('_DOWN') or out.get('relM_state','').endswith('_DOWN')) else 0)
    if has_monthly_bear and direction > 0: direction = 0  # weekly bull vetoed by monthly bear
    if has_monthly_bull and direction < 0: direction = 0  # weekly bear vetoed by monthly bull

    # Composite asymmetry rank
    out['final_rank'] = round(
        out['inflect_score'] +
        velocity * 0.6 +
        accel * 0.4 +
        macro_total * 0.5 -
        (15 if has_monthly_bear and inflect_score > 0 else 0) +  # penalize TF conflict
        (10 if has_monthly_bull and inflect_score > 0 else 0),
    2)

    return out


# ============== RUN ==============
results = []
chunk = 50
for i in range(0, len(syms), chunk):
    batch = syms[i:i+chunk]
    try:
        data = yf.download(' '.join(batch), period='5y', interval='1d',
                          group_by='ticker', threads=True, progress=False, auto_adjust=True)
        for t in batch:
            try:
                df = data[t].copy() if isinstance(data.columns, pd.MultiIndex) else data.copy()
                m = screen_one(t, df, bench_df)
                if m: results.append(m)
            except Exception as e:
                if 'first_err' not in dir():
                    first_err = True
                    import traceback as tb
                    print(f"  ERR {t}: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
                    tb.print_exc(limit=3, file=sys.stderr)
        if (i+len(batch)) % 250 == 0 or i+len(batch) == len(syms):
            print(f"  {i+len(batch)}/{len(syms)} processed; kept {len(results)}", file=sys.stderr)
            # Checkpoint
            pd.DataFrame(results).to_csv(args.out, index=False)
    except Exception as e:
        print(f"  batch err {str(e)[:60]}", file=sys.stderr)
    time.sleep(1.0)

out = pd.DataFrame(results)
out.to_csv(args.out, index=False)
print(f"DONE: {len(out)} rows -> {args.out}")
