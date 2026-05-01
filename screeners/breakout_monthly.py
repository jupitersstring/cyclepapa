#!/usr/bin/env python3
"""Monthly-bar version of the breakout pre-setup screener.
Same 4 conditions but on monthly bars over 7 years:
  1. Top of multi-year range: within 8% of 5y high, 25%+ off 2y low
  2. MFI(14) inflecting: 30-80 zone, rising over 2 months
  3. ROC(12) turning: > -15%, rising over 2 months, < 30
  4. Volume shelf w/ air pocket: POC within 25% below current, vol above < 60% of POC
"""
import pandas as pd, numpy as np, yfinance as yf, sys, time, warnings
warnings.filterwarnings('ignore')

uni = pd.read_csv('/tmp/screen_universe.csv')
syms = uni['ticker'].dropna().unique().tolist()
syms = [s for s in syms if isinstance(s,str) and not ('-' in s or s.endswith('U') or s.endswith('W'))]
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
    if df is None or len(df) < 30: return None
    df = df.dropna()
    if len(df) < 30: return None
    df['mfi'] = mfi(df['High'], df['Low'], df['Close'], df['Volume'])
    df['roc'] = roc(df['Close'])

    last = df.iloc[-1]
    px = float(last['Close'])
    high_5y = float(df['High'].tail(60).max())
    high_2y = float(df['High'].tail(24).max())
    low_2y  = float(df['Low'].tail(24).min())
    mfi_now = float(last['mfi']) if not pd.isna(last['mfi']) else np.nan
    mfi_2m  = float(df['mfi'].iloc[-3]) if len(df)>3 and not pd.isna(df['mfi'].iloc[-3]) else np.nan
    roc_now = float(last['roc']) if not pd.isna(last['roc']) else np.nan
    roc_2m  = float(df['roc'].iloc[-3]) if len(df)>3 and not pd.isna(df['roc'].iloc[-3]) else np.nan

    # Volume profile over last 5y monthly
    win = df.tail(60)
    if len(win) < 24: return None
    pmin, pmax = float(win['Low'].min()), float(win['High'].max())
    if pmax <= pmin: return None
    bins = 40
    edges = np.linspace(pmin, pmax, bins+1)
    vp = np.zeros(bins)
    for _, r in win.iterrows():
        lo, hi, vol = float(r['Low']), float(r['High']), float(r['Volume'])
        if hi <= lo or np.isnan(vol): continue
        lo_idx = max(0, int((lo - pmin)/(pmax-pmin) * bins))
        hi_idx = min(bins-1, int((hi - pmin)/(pmax-pmin) * bins))
        if hi_idx == lo_idx: vp[lo_idx] += vol
        else:
            per_bin = vol / (hi_idx - lo_idx + 1)
            vp[lo_idx:hi_idx+1] += per_bin
    poc_idx = int(np.argmax(vp))
    poc_price = (edges[poc_idx] + edges[poc_idx+1]) / 2
    cur_idx = max(0, min(bins-1, int((px - pmin)/(pmax-pmin) * bins)))
    vol_above = float(vp[cur_idx+1:].sum()) if cur_idx < bins-1 else 0.0
    vol_at_poc = float(vp[poc_idx])

    return {
        'ticker': ticker,
        'price': px,
        'high_5y': high_5y,
        'high_2y': high_2y,
        'pct_below_5y_high': (high_5y/px - 1)*100,
        'pct_above_2y_low':  (px/low_2y - 1)*100,
        'mfi': mfi_now,
        'mfi_2m_ago': mfi_2m,
        'mfi_chg': mfi_now - mfi_2m if not (np.isnan(mfi_now) or np.isnan(mfi_2m)) else np.nan,
        'roc': roc_now,
        'roc_2m_ago': roc_2m,
        'roc_chg': roc_now - roc_2m if not (np.isnan(roc_now) or np.isnan(roc_2m)) else np.nan,
        'poc_price': poc_price,
        'poc_pct_below_px': (px/poc_price - 1)*100 if poc_price > 0 else np.nan,
        'vol_above_vs_poc': vol_above / vol_at_poc if vol_at_poc > 0 else np.nan,
    }

results = []
chunk = 50
for i in range(0, len(syms), chunk):
    batch = syms[i:i+chunk]
    try:
        data = yf.download(' '.join(batch), period='7y', interval='1mo',
                          group_by='ticker', threads=True, progress=False, auto_adjust=True)
        for t in batch:
            try:
                df = data[t].copy() if isinstance(data.columns, pd.MultiIndex) else data.copy()
                m = screen_one(t, df)
                if m: results.append(m)
            except Exception:
                pass
        print(f"  {i+len(batch)}/{len(syms)} processed; kept {len(results)}", file=sys.stderr)
    except Exception as e:
        print(f"  batch err {str(e)[:60]}", file=sys.stderr)
    time.sleep(1.0)

out = pd.DataFrame(results)
out.to_csv('/tmp/tech_setups_monthly.csv', index=False)
print(f"DONE: {len(out)} rows")
