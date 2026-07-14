#!/usr/bin/env python3
"""Technical breakout pre-setup screener.
Conditions on weekly bars:
  1. Top of range: last close within 5% of 2y high AND >= 1y high (in upper 90%)
  2. MFI(14) inflecting: MFI > 50 AND MFI > MFI 4w ago AND MFI < 80 (not yet overbought)
  3. ROC(12) positive or just turning: ROC > -2% AND ROC > ROC 4w ago AND ROC < 25
  4. Volume shelf w/ air pocket above:
        - POC (point of control) within 15% below current price
        - Volume above current price < 50% of volume at POC bin (clear air)
"""
import pandas as pd
import numpy as np
import yfinance as yf
import warnings, sys, time
warnings.filterwarnings('ignore')

# Load universe
uni = pd.read_csv('/tmp/screen_universe.csv')
from _ticker_filter import common_stock_tickers
syms = common_stock_tickers(uni)
print(f"universe: {len(syms)}", file=sys.stderr)

def mfi(h, l, c, v, n=14):
    tp = (h + l + c) / 3
    mf = tp * v
    pos = mf.where(tp > tp.shift(1), 0)
    neg = mf.where(tp < tp.shift(1), 0)
    pos_sum = pos.rolling(n).sum()
    neg_sum = neg.rolling(n).sum()
    mr = pos_sum / neg_sum.replace(0, np.nan)
    return 100 - 100/(1 + mr)

def roc(s, n=12):
    return (s / s.shift(n) - 1) * 100

def screen_one(ticker, df):
    """Return dict of metrics for one ticker. df is weekly OHLCV."""
    if df is None or len(df) < 60:
        return None
    df = df.dropna()
    if len(df) < 60:
        return None
    df['mfi'] = mfi(df['High'], df['Low'], df['Close'], df['Volume'])
    df['roc'] = roc(df['Close'])

    last = df.iloc[-1]
    px = float(last['Close'])
    high_2y = float(df['High'].tail(104).max())
    high_1y = float(df['High'].tail(52).max())
    mfi_now = float(last['mfi']) if not pd.isna(last['mfi']) else np.nan
    mfi_4w  = float(df['mfi'].iloc[-5]) if len(df)>5 and not pd.isna(df['mfi'].iloc[-5]) else np.nan
    roc_now = float(last['roc']) if not pd.isna(last['roc']) else np.nan
    roc_4w  = float(df['roc'].iloc[-5]) if len(df)>5 and not pd.isna(df['roc'].iloc[-5]) else np.nan

    # Volume profile over last 2 yrs
    win = df.tail(104)
    if len(win) < 50: return None
    pmin, pmax = float(win['Low'].min()), float(win['High'].max())
    if pmax <= pmin: return None
    bins = 40
    edges = np.linspace(pmin, pmax, bins+1)
    # distribute weekly volume across the bar's H-L range
    vp = np.zeros(bins)
    for _, r in win.iterrows():
        lo, hi, vol = float(r['Low']), float(r['High']), float(r['Volume'])
        if hi <= lo or np.isnan(vol): continue
        lo_idx = max(0, int((lo - pmin)/(pmax-pmin) * bins))
        hi_idx = min(bins-1, int((hi - pmin)/(pmax-pmin) * bins))
        if hi_idx == lo_idx:
            vp[lo_idx] += vol
        else:
            per_bin = vol / (hi_idx - lo_idx + 1)
            vp[lo_idx:hi_idx+1] += per_bin
    poc_idx = int(np.argmax(vp))
    poc_price = (edges[poc_idx] + edges[poc_idx+1]) / 2
    cur_idx = max(0, min(bins-1, int((px - pmin)/(pmax-pmin) * bins)))
    vol_above = float(vp[cur_idx+1:].sum()) if cur_idx < bins-1 else 0.0
    vol_at_poc = float(vp[poc_idx])
    vol_below = float(vp[:cur_idx+1].sum())

    return {
        'ticker': ticker,
        'price': px,
        'high_1y': high_1y,
        'high_2y': high_2y,
        'pct_below_2y_high': (high_2y/px - 1)*100,
        'pct_above_1y_low': (px/df['Low'].tail(52).min() - 1)*100,
        'mfi': mfi_now,
        'mfi_4w_ago': mfi_4w,
        'mfi_chg': mfi_now - mfi_4w if not (np.isnan(mfi_now) or np.isnan(mfi_4w)) else np.nan,
        'roc': roc_now,
        'roc_4w_ago': roc_4w,
        'roc_chg': roc_now - roc_4w if not (np.isnan(roc_now) or np.isnan(roc_4w)) else np.nan,
        'poc_price': poc_price,
        'poc_pct_below_px': (px/poc_price - 1)*100 if poc_price > 0 else np.nan,
        'vol_above_vs_poc': vol_above / vol_at_poc if vol_at_poc > 0 else np.nan,
        'vol_below_vs_poc': vol_below / vol_at_poc if vol_at_poc > 0 else np.nan,
    }

# Bulk download in chunks of 50
results = []
chunk = 50
for i in range(0, len(syms), chunk):
    batch = syms[i:i+chunk]
    try:
        data = yf.download(' '.join(batch), period='3y', interval='1wk',
                          group_by='ticker', threads=True, progress=False, auto_adjust=True)
        for t in batch:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    df = data[t].copy()
                else:
                    df = data.copy()
                m = screen_one(t, df)
                if m: results.append(m)
            except Exception:
                pass
        print(f"  {i+len(batch)}/{len(syms)} processed; kept {len(results)}", file=sys.stderr)
    except Exception as e:
        print(f"  batch err {str(e)[:60]}", file=sys.stderr)
    time.sleep(1.0)

out = pd.DataFrame(results)
out.to_csv('/tmp/tech_setups.csv', index=False)
print(f"DONE: {len(out)} rows")
