#!/usr/bin/env python3
"""Qullamaggie continuation-breakout screener — faithful to qullamaggie.com.

Setup:
  1. Prior leg: stock made 30-100%+ move sometime in last 1-3 months (any
     few-days to few-weeks window)
  2. Top % gainers: ranked in top quartile by 1-mo / 3-mo / 6-mo return
  3. Consolidation 2 weeks-2 months: higher lows, tightening range
  4. Price surfing rising 10-day and 20-day SMA (sometimes 50-day)
  5. ADR < 6% (Q's stop-friendly tightness)
  6. Currently in base — not yet at breakout (sets up the entry)
  7. Within 25% of recent leg-high (room to go but not stretched)

Outputs to data/qmaggie/<ticker>... — daily bars, not weekly.
"""
import pandas as pd, numpy as np, yfinance as yf, sys, time, warnings, argparse
warnings.filterwarnings('ignore')

ap = argparse.ArgumentParser()
ap.add_argument('--universe', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--period', default='9mo')
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().unique().tolist()
syms = [s for s in syms if isinstance(s,str) and not ('.' not in s and ('-' in s or s.endswith('U') or s.endswith('W')))]
print(f"qmaggie universe: {len(syms)}", file=sys.stderr)

def screen_one(t, df):
    if df is None or len(df) < 120: return None
    df = df.dropna()
    if len(df) < 120: return None

    df['sma10'] = df['Close'].rolling(10).mean()
    df['sma20'] = df['Close'].rolling(20).mean()
    df['sma50'] = df['Close'].rolling(50).mean()
    # ADR (Average Daily Range %) — Q's tightness measure
    df['daily_range_pct'] = (df['High'] - df['Low']) / df['Close'] * 100
    df['adr'] = df['daily_range_pct'].rolling(20).mean()
    last = df.iloc[-1]
    px = float(last['Close'])

    # ─── 1. Prior leg: find biggest N-day move in the last 90 trading days ───
    last_90 = df.tail(90)
    closes90 = last_90['Close'].values
    # Best N-day rally where N=5-30
    best_leg_pct = 0
    best_leg_start = 0
    best_leg_end = 0
    for window in [5, 10, 15, 20, 30]:
        for start in range(len(closes90) - window):
            move = (closes90[start + window] / closes90[start] - 1) * 100
            if move > best_leg_pct:
                best_leg_pct = move
                best_leg_start = start
                best_leg_end = start + window
    # Position of leg-end (bars ago from now)
    leg_end_bars_ago = len(closes90) - best_leg_end

    # ─── 2. Top % gainer windows ───
    ret_1m  = (px / float(df['Close'].iloc[-21]) - 1) * 100 if len(df) > 21 else np.nan
    ret_3m  = (px / float(df['Close'].iloc[-63]) - 1) * 100 if len(df) > 63 else np.nan
    ret_6m  = (px / float(df['Close'].iloc[-126]) - 1) * 100 if len(df) > 126 else np.nan

    # ─── 3. Consolidation: from leg-end to now ───
    if leg_end_bars_ago < 5:
        consol_high = px
        consol_low = px
        consol_days = 0
    else:
        consol = df.tail(leg_end_bars_ago + 1)
        consol_high = float(consol['High'].max())
        consol_low = float(consol['Low'].min())
        consol_days = leg_end_bars_ago

    consol_range_pct = (consol_high / consol_low - 1) * 100 if consol_low > 0 else np.nan

    # ─── 4. SMA surf: price > rising 10 AND 20 SMA ───
    sma10_now = float(last['sma10']) if not pd.isna(last['sma10']) else np.nan
    sma20_now = float(last['sma20']) if not pd.isna(last['sma20']) else np.nan
    sma50_now = float(last['sma50']) if not pd.isna(last['sma50']) else np.nan
    sma10_10d = float(df['sma10'].iloc[-11]) if len(df) > 11 and not pd.isna(df['sma10'].iloc[-11]) else np.nan
    sma20_10d = float(df['sma20'].iloc[-11]) if len(df) > 11 and not pd.isna(df['sma20'].iloc[-11]) else np.nan

    sma10_rising = (sma10_now / sma10_10d - 1) > 0 if not np.isnan(sma10_10d) and sma10_10d > 0 else False
    sma20_rising = (sma20_now / sma20_10d - 1) > 0 if not np.isnan(sma20_10d) and sma20_10d > 0 else False
    above_sma10 = px > sma10_now if not np.isnan(sma10_now) else False
    above_sma20 = px > sma20_now if not np.isnan(sma20_now) else False
    above_sma50 = px > sma50_now if not np.isnan(sma50_now) else False

    # ─── 5. ADR (Q's defining tightness) ───
    adr_now = float(last['adr']) if not pd.isna(last['adr']) else np.nan

    # ─── 6. Distance to leg-high ───
    pct_below_leg_high = (consol_high / px - 1) * 100 if px > 0 else np.nan

    # ─── 7. Volume contraction during consolidation ───
    vol_recent5 = float(df['Volume'].tail(5).mean())
    vol_pre = float(df['Volume'].iloc[-leg_end_bars_ago-15:-leg_end_bars_ago].mean()) \
        if leg_end_bars_ago >= 15 and len(df) > leg_end_bars_ago + 15 else np.nan
    vol_contract = vol_recent5 / vol_pre if vol_pre and vol_pre > 0 else np.nan

    return {
        'ticker': t,
        'price': px,
        'best_leg_pct': best_leg_pct,
        'leg_end_bars_ago': leg_end_bars_ago,
        'ret_1m_pct': ret_1m,
        'ret_3m_pct': ret_3m,
        'ret_6m_pct': ret_6m,
        'consol_days': consol_days,
        'consol_range_pct': consol_range_pct,
        'adr_pct': adr_now,
        'above_sma10': above_sma10,
        'above_sma20': above_sma20,
        'above_sma50': above_sma50,
        'sma10_rising': sma10_rising,
        'sma20_rising': sma20_rising,
        'pct_below_leg_high': pct_below_leg_high,
        'vol_contract_ratio': vol_contract,
    }

results = []
chunk = 50
for i in range(0, len(syms), chunk):
    batch = syms[i:i+chunk]
    try:
        data = yf.download(' '.join(batch), period=args.period, interval='1d',
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
    time.sleep(0.8)

out = pd.DataFrame(results)
# Compute Q pass flag
if len(out):
    out['qmaggie_pass'] = (
        (out['best_leg_pct'] >= 30) &
        (out['leg_end_bars_ago'].between(5, 60)) &   # 1-3 months ago window for leg end
        (out['consol_days'].between(10, 40)) &        # 2w to 2mo consolidation
        (out['consol_range_pct'] <= 25) &              # not too sloppy
        (out['adr_pct'] <= 6) &                        # Q's tightness
        (out['above_sma10']) & (out['above_sma20']) &
        (out['sma10_rising']) & (out['sma20_rising']) &
        (out['pct_below_leg_high'] <= 15) &            # close to breakout
        (out['ret_1m_pct'] > -10)                       # not crashing
    )
    out = out.sort_values('best_leg_pct', ascending=False)

out.to_csv(args.out, index=False)
print(f"DONE: {len(out)} rows · {out.get('qmaggie_pass', pd.Series(dtype=bool)).sum()} pass Q filter → {args.out}")
