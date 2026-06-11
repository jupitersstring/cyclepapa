#!/usr/bin/env python3
"""Bullish absorption screener.
Pattern: Money flowed out (MFI declined materially) but price didn't follow
(stayed flat / consolidated). That asymmetry = stealth accumulation.

Conditions on weekly + monthly bars:
  1. MFI declined: mfi_change over last 12 bars <= -10 (clear outflow)
  2. Price held: |price_change| over same window <= 7% (didn't follow money out)
  3. Volatility low: realized ATR% during window <= 5% (true consolidation, not chaos)
  4. Constructive context: price in upper 60% of 1y range (not crashing)
  5. Divergence ratio: |price_chg| / |mfi_chg| < 0.4 (price moved much less than money flow)
"""
import pandas as pd, numpy as np, yfinance as yf, sys, time, warnings
warnings.filterwarnings('ignore')

import argparse
ap = argparse.ArgumentParser()
ap.add_argument('--universe', default='/tmp/screen_universe.csv')
ap.add_argument('--out', default='/tmp/absorption_setups.csv')
ap.add_argument('--interval', default='1wk')   # 1wk or 1mo
ap.add_argument('--period', default='3y')
ap.add_argument('--window', type=int, default=12)  # bars to measure outflow over
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().unique().tolist()
syms = [s for s in syms if isinstance(s,str) and not ('.' not in s and ('-' in s or s.endswith('U') or s.endswith('W')))]
print(f"universe: {len(syms)}", file=sys.stderr)

W = args.window

def mfi_calc(h, l, c, v, n=14):
    tp = (h + l + c) / 3
    mf = tp * v
    pos = mf.where(tp > tp.shift(1), 0)
    neg = mf.where(tp < tp.shift(1), 0)
    pos_sum = pos.rolling(n).sum()
    neg_sum = neg.rolling(n).sum()
    mr = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - 100/(1 + mr)

def atr(h, l, c, n=6):
    tr = pd.concat([(h-l), (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def screen_one(ticker, df):
    if df is None or len(df) < W + 20: return None
    df = df.dropna()
    if len(df) < W + 20: return None
    df['mfi'] = mfi_calc(df['High'], df['Low'], df['Close'], df['Volume'])
    df['atr'] = atr(df['High'], df['Low'], df['Close'])
    df['atr_pct'] = df['atr'] / df['Close']

    last = df.iloc[-1]
    px = float(last['Close'])
    px_then = float(df['Close'].iloc[-W])
    mfi_now  = float(last['mfi']) if not pd.isna(last['mfi']) else np.nan
    mfi_then = float(df['mfi'].iloc[-W]) if not pd.isna(df['mfi'].iloc[-W]) else np.nan
    if np.isnan(mfi_now) or np.isnan(mfi_then) or px_then == 0: return None

    px_chg = (px / px_then - 1) * 100
    mfi_chg = mfi_now - mfi_then
    avg_atr_window = float(df['atr_pct'].iloc[-W:].mean()) * 100
    range_window = (float(df['High'].iloc[-W:].max()) / float(df['Low'].iloc[-W:].min()) - 1) * 100

    # Position in 1y range
    n1y = 52 if args.interval=='1wk' else 12
    high_1y = float(df['High'].tail(n1y).max())
    low_1y  = float(df['Low'].tail(n1y).min())
    pos_in_1y = (px - low_1y) / (high_1y - low_1y) if high_1y > low_1y else np.nan

    # Volume signal: recent vol vs prior to detect institutional support
    rec_vol = float(df['Volume'].tail(4).mean())
    prior_vol = float(df['Volume'].iloc[-(W+4):-4].mean())
    vol_ratio = rec_vol / prior_vol if prior_vol > 0 else np.nan

    # Up/down vol asymmetry during window
    win = df.iloc[-W:]
    ups = win[win['Close'] > win['Open']]['Volume']
    dns = win[win['Close'] <= win['Open']]['Volume']
    up_dn = float(ups.sum() / dns.sum()) if len(dns) > 0 and dns.sum() > 0 else np.nan

    return {
        'ticker': ticker,
        'price': px,
        'px_chg_pct': px_chg,
        'mfi_now': mfi_now,
        'mfi_then': mfi_then,
        'mfi_chg': mfi_chg,
        'atr_pct_avg': avg_atr_window,
        'range_window_pct': range_window,
        'pos_in_1y': pos_in_1y * 100 if not np.isnan(pos_in_1y) else np.nan,
        'vol_ratio_recent_vs_prior': vol_ratio,
        'up_dn_vol_window': up_dn,
        'divergence_ratio': abs(px_chg) / abs(mfi_chg) if abs(mfi_chg) > 0 else np.nan,
    }

results = []
chunk = 50
for i in range(0, len(syms), chunk):
    batch = syms[i:i+chunk]
    try:
        data = yf.download(' '.join(batch), period=args.period, interval=args.interval,
                          group_by='ticker', threads=True, progress=False, auto_adjust=True)
        for t in batch:
            try:
                df = data[t].copy() if isinstance(data.columns, pd.MultiIndex) else data.copy()
                m = screen_one(t, df)
                if m: results.append(m)
            except Exception:
                pass
        if (i+len(batch)) % 250 == 0 or i+len(batch) == len(syms):
            print(f"  {i+len(batch)}/{len(syms)} processed; kept {len(results)}", file=sys.stderr)
    except Exception as e:
        print(f"  batch err {str(e)[:60]}", file=sys.stderr)
    time.sleep(1.0)

out = pd.DataFrame(results)
out.to_csv(args.out, index=False)
print(f"DONE: {len(out)} rows -> {args.out}")
