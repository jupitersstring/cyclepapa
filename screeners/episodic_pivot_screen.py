#!/usr/bin/env python3
"""Episodic Pivot (EP) detector — Qullamaggie's gap-up earnings catalyst setup.

Looks for the daily-bar signature of an EP:
  1. Gap up ≥ 10% on a single day
  2. Volume on gap day = at least 2× average daily volume (proxy for 1 ADV
     in first 15-30 min — we can't measure intraday from daily bars)
  3. Prior 3-6 months were sideways (10-15% range max) — surprise factor
  4. (Optional, when fund data present) revenue growth ≥ 25% YoY

Universe csv with --gap-day-window N: scan last N trading days for any
gap ≥ threshold. Default: last 5 days only (live setups).
"""
import pandas as pd, numpy as np, yfinance as yf, sys, time, warnings, argparse
warnings.filterwarnings('ignore')

ap = argparse.ArgumentParser()
ap.add_argument('--universe', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--period', default='9mo')
ap.add_argument('--gap-pct', type=float, default=0.10, help='Min gap (close/prev_close - 1)')
ap.add_argument('--window-days', type=int, default=5, help='Recent N days to look for the gap')
args = ap.parse_args()

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().unique().tolist()
syms = [s for s in syms if isinstance(s,str) and not ('.' not in s and ('-' in s or s.endswith('U') or s.endswith('W')))]
print(f"EP universe: {len(syms)}", file=sys.stderr)

def screen_one(t, df):
    if df is None or len(df) < 130: return None
    df = df.dropna().sort_index()
    if len(df) < 130: return None

    df['vol_avg20'] = df['Volume'].rolling(20).mean()
    df['adr_pct'] = (df['High'] - df['Low']) / df['Close'].shift(1) * 100
    df['gap_pct'] = (df['Open'] - df['Close'].shift(1)) / df['Close'].shift(1)
    df['day_pct'] = (df['Close'] - df['Close'].shift(1)) / df['Close'].shift(1)
    df['vol_ratio'] = df['Volume'] / df['vol_avg20']

    # Find biggest gap in last N days
    recent = df.tail(args.window_days)
    if len(recent) == 0: return None
    gap_idx = recent['gap_pct'].idxmax()
    biggest_gap = recent.loc[gap_idx]
    gap_pct = float(biggest_gap['gap_pct']) if pd.notna(biggest_gap['gap_pct']) else 0
    day_pct = float(biggest_gap['day_pct']) if pd.notna(biggest_gap['day_pct']) else 0
    vol_ratio = float(biggest_gap['vol_ratio']) if pd.notna(biggest_gap['vol_ratio']) else 0

    # Pre-gap 3-6 month range (sideways check)
    pre_gap = df.loc[:gap_idx].iloc[-130:-1]  # 130 trading days = ~6 months
    if len(pre_gap) < 60:
        pre_range_pct = np.nan
        pre_ret_pct = np.nan
    else:
        pre_low = float(pre_gap['Low'].min())
        pre_high = float(pre_gap['High'].max())
        pre_range_pct = (pre_high / pre_low - 1) * 100 if pre_low > 0 else np.nan
        pre_first = float(pre_gap['Close'].iloc[0])
        pre_last = float(pre_gap['Close'].iloc[-1])
        pre_ret_pct = (pre_last / pre_first - 1) * 100 if pre_first > 0 else np.nan

    # Hold-up since gap (still in EP window?)
    days_since_gap = len(df.loc[gap_idx:]) - 1
    close_at_gap = float(biggest_gap['Close'])
    close_now = float(df.iloc[-1]['Close'])
    hold_pct = (close_now / close_at_gap - 1) * 100 if close_at_gap > 0 else np.nan

    return {
        'ticker': t,
        'price': close_now,
        'biggest_gap_pct': gap_pct * 100,
        'day_pct_gap_day': day_pct * 100,
        'vol_ratio_gap_day': vol_ratio,
        'pre_gap_range_6m_pct': pre_range_pct,
        'pre_gap_return_6m_pct': pre_ret_pct,
        'days_since_gap': days_since_gap,
        'hold_pct_since_gap': hold_pct,
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
if len(out):
    out['ep_pass'] = (
        (out['biggest_gap_pct'] >= args.gap_pct * 100) &
        (out['vol_ratio_gap_day'] >= 2.0) &
        (out['pre_gap_range_6m_pct'].fillna(99) <= 30) &
        (out['hold_pct_since_gap'] >= -5)  # still above gap day minus small bleed
    )
    out = out.sort_values('biggest_gap_pct', ascending=False)
out.to_csv(args.out, index=False)
print(f"DONE: {len(out)} rows · {int(out.get('ep_pass', pd.Series(dtype=bool)).sum())} pass → {args.out}")
