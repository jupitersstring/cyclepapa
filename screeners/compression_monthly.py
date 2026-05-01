#!/usr/bin/env python3
"""Refined monthly screener for the compression + MFI-higher-low + inflection pattern.

Conditions on monthly bars (last 5–7 years):
  1. MFI higher low: most recent MFI trough > prior MFI trough (within last 36 months)
  2. Range compression: ATR(6) at recent low < ATR(6) at prior low (volatility contracting)
  3. MFI just inflecting: MFI rising last 1-2 months from a low; MFI < 60 (still early)
  4. Sitting on volume shelf: price within ±10% of POC (point of control)
  5. Near top of multi-year range: within 12% of 5y high
"""
import pandas as pd, numpy as np, yfinance as yf, sys, time, warnings
warnings.filterwarnings('ignore')

def find_troughs(arr, min_prominence=5, min_distance=3):
    """Pure-numpy local minima finder. Returns indices of troughs."""
    arr = np.asarray(arr, dtype=float)
    n = len(arr)
    if n < 5: return []
    # Local minima: lower than 2 neighbors on each side
    troughs = []
    for i in range(2, n-2):
        if arr[i] < arr[i-1] and arr[i] < arr[i-2] and arr[i] < arr[i+1] and arr[i] < arr[i+2]:
            # Check prominence: how much lower than nearest higher peak
            left_max = arr[max(0,i-12):i].max() if i > 0 else arr[i]
            right_max = arr[i+1:min(n,i+13)].max() if i < n-1 else arr[i]
            prominence = min(left_max, right_max) - arr[i]
            if prominence >= min_prominence:
                troughs.append(i)
    # Enforce min distance
    if len(troughs) < 2: return troughs
    filtered = [troughs[0]]
    for t in troughs[1:]:
        if t - filtered[-1] >= min_distance:
            filtered.append(t)
    return filtered

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

def atr(h, l, c, n=6):
    tr = pd.concat([(h-l), (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def screen_one(ticker, df):
    if df is None or len(df) < 36: return None
    df = df.dropna()
    if len(df) < 36: return None
    df['mfi'] = mfi(df['High'], df['Low'], df['Close'], df['Volume'])
    df['atr'] = atr(df['High'], df['Low'], df['Close'])
    df['atr_pct'] = df['atr'] / df['Close']

    last = df.iloc[-1]
    px = float(last['Close'])
    high_5y = float(df['High'].tail(60).max())

    # Find MFI troughs in last 36 months
    mfi_series = df['mfi'].tail(36).dropna()
    if len(mfi_series) < 18: return None
    # Inverted to find minima
    troughs = find_troughs(mfi_series.values, min_prominence=5, min_distance=3)
    if len(troughs) < 2: return None

    # Most recent two troughs
    last_trough_idx_local  = troughs[-1]
    prior_trough_idx_local = troughs[-2]
    last_mfi_low  = float(mfi_series.iloc[last_trough_idx_local])
    prior_mfi_low = float(mfi_series.iloc[prior_trough_idx_local])

    # Map back to df indices
    series_start_offset = len(df) - len(mfi_series)
    last_trough_df_idx  = series_start_offset + last_trough_idx_local
    prior_trough_df_idx = series_start_offset + prior_trough_idx_local

    # Bars since last trough (inflection age)
    bars_since_low = len(df) - 1 - last_trough_df_idx

    # ATR % at each trough
    atr_at_last  = float(df['atr_pct'].iloc[last_trough_df_idx]) if last_trough_df_idx < len(df) else np.nan
    atr_at_prior = float(df['atr_pct'].iloc[prior_trough_df_idx]) if prior_trough_df_idx < len(df) else np.nan

    # Current MFI vs trough
    mfi_now = float(last['mfi']) if not pd.isna(last['mfi']) else np.nan
    mfi_inflect_amount = mfi_now - last_mfi_low

    # Volume profile last 60 months
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
        'pct_below_5y_high': (high_5y/px - 1)*100,
        'mfi_now': mfi_now,
        'mfi_last_low': last_mfi_low,
        'mfi_prior_low': prior_mfi_low,
        'mfi_higher_low': last_mfi_low - prior_mfi_low,  # positive = higher low
        'mfi_inflect_amt': mfi_inflect_amount,
        'months_since_low': bars_since_low,
        'atr_pct_last_low': atr_at_last*100 if not np.isnan(atr_at_last) else np.nan,
        'atr_pct_prior_low': atr_at_prior*100 if not np.isnan(atr_at_prior) else np.nan,
        'atr_compression': (atr_at_prior - atr_at_last)*100 if not (np.isnan(atr_at_prior) or np.isnan(atr_at_last)) else np.nan,
        'poc_price': poc_price,
        'pct_to_poc': (px/poc_price - 1)*100 if poc_price > 0 else np.nan,
        'vol_above_vs_poc': vol_above/vol_at_poc if vol_at_poc > 0 else np.nan,
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
out.to_csv('/tmp/tech_compression.csv', index=False)
print(f"DONE: {len(out)} rows")
