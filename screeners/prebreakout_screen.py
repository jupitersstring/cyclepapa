#!/usr/bin/env python3
"""Weinstein / Qullamaggie / O'Neil PRE-breakout screener.

Pattern: stock is currently consolidating tight after a prior leg up.
Has NOT yet broken out — sitting in the basing/handle phase.

Conditions on weekly bars (3y history):
  1. Prior leg-up: 6-month return >= 25% AND 12-month return >= 30%
     (proves there's a real uptrend that needs continuation, not a dead cat)
  2. Currently consolidating: last 8-12 weeks
     - ATR/price < 3.5% (tight)
     - max-min range < 15% (true base, not chop)
  3. Near 52w high but NOT making new highs:
     - within 3-15% of 52w high
     - last 4 weeks did NOT print a new 52w high (still consolidating)
  4. Above 30-week MA AND 30w MA flattening or just turning up (Weinstein):
     - close > 30wMA
     - 30wMA slope (last 8 weeks) >= -2% but <= +5% (flat, not still cratering, not extended)
  5. Volume drying up during consolidation:
     - avg vol of last 4 weeks < avg vol of weeks 13-26 (dry-up)
     - ratio < 0.95
  6. MFI in neutral consolidation zone:
     - 40 <= MFI <= 65 (not overbought, not crashed)
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

def mfi_calc(h,l,c,v,n=14):
    tp = (h+l+c)/3; mf = tp*v
    pos = mf.where(tp>tp.shift(1),0); neg = mf.where(tp<tp.shift(1),0)
    ps, ns = pos.rolling(n).sum(), neg.rolling(n).sum()
    mr = ps/ns.replace(0, np.nan)
    return 100 - 100/(1+mr)

def atr(h,l,c,n=6):
    tr = pd.concat([(h-l), (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def screen_one(ticker, df):
    if df is None or len(df) < 60: return None
    df = df.dropna()
    if len(df) < 60: return None

    df['ma30'] = df['Close'].rolling(30).mean()
    df['atr']  = atr(df['High'], df['Low'], df['Close'])
    df['atr_pct'] = df['atr'] / df['Close']
    df['mfi']  = mfi_calc(df['High'], df['Low'], df['Close'], df['Volume'])

    last = df.iloc[-1]
    px = float(last['Close'])

    # 1. Prior leg-up
    px_6m  = float(df['Close'].iloc[-26]) if len(df)>26 else np.nan
    px_12m = float(df['Close'].iloc[-52]) if len(df)>52 else np.nan
    ret_6m  = (px / px_6m  - 1) * 100 if not np.isnan(px_6m)  and px_6m  > 0 else np.nan
    ret_12m = (px / px_12m - 1) * 100 if not np.isnan(px_12m) and px_12m > 0 else np.nan

    # 2. Tight consolidation — last 8 weeks
    w8 = df.tail(8)
    atr_pct_avg = float(w8['atr_pct'].mean()) * 100
    range_8w = (float(w8['High'].max()) / float(w8['Low'].min()) - 1) * 100

    # 3. 52w high distance + no fresh new highs
    high_52 = float(df['High'].tail(52).max())
    pct_below_52h = (high_52 / px - 1) * 100
    last_4 = df.tail(4)
    new_high_recent = bool((last_4['High'] >= high_52 * 0.999).any())

    # 4. 30wMA position & slope
    ma30_now = float(last['ma30']) if not pd.isna(last['ma30']) else np.nan
    ma30_8w  = float(df['ma30'].iloc[-9]) if len(df)>9 and not pd.isna(df['ma30'].iloc[-9]) else np.nan
    above_ma30 = px > ma30_now if not np.isnan(ma30_now) else False
    ma30_slope = (ma30_now/ma30_8w - 1)*100 if not np.isnan(ma30_now) and not np.isnan(ma30_8w) and ma30_8w > 0 else np.nan

    # 5. Volume dry-up
    vol_recent = float(df['Volume'].tail(4).mean())
    vol_consol = float(df['Volume'].iloc[-26:-13].mean()) if len(df) > 26 else np.nan
    vol_dryup_ratio = vol_recent / vol_consol if not np.isnan(vol_consol) and vol_consol > 0 else np.nan

    # 6. MFI neutral
    mfi_now = float(last['mfi']) if not pd.isna(last['mfi']) else np.nan

    return {
        'ticker': ticker,
        'price': px,
        'ret_6m_pct': ret_6m,
        'ret_12m_pct': ret_12m,
        'atr_pct_avg_8w': atr_pct_avg,
        'range_8w_pct': range_8w,
        'pct_below_52w_high': pct_below_52h,
        'new_high_in_last4w': new_high_recent,
        'above_ma30': above_ma30,
        'ma30_slope_8w_pct': ma30_slope,
        'vol_dryup_ratio': vol_dryup_ratio,
        'mfi': mfi_now,
    }

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
