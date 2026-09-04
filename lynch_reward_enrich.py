"""Lynch "years of progress rewarded in a year" — price-series signals.

The Fannie Mae pattern (Beating the Street): a business advances fundamentally
for YEARS while the stock goes nowhere, then the market pays it all at once
($16 -> $42 in 1989 — "several years' worth of patience was rewarded in one").
The fundamental legs live in the master; THIS enricher computes the price-
series legs, transcribing the Squeeze & Release + Volatility Asymmetry Pine v5
methodology EXACTLY (© malikmck, MPL 2.0 — the reference indicator we already
use elsewhere):

  Volatility asymmetry (per timeframe: weekly / monthly / quarterly):
    upwardMove   = max(high - close[1], 0)
    downwardMove = max(close[1] - low, 0)
    upATR = ema(upwardMove, 14); dnATR = ema(downwardMove, 14)
    asymmetryValue = ema(upATR / (upATR + dnATR + 0.0001) * 100, 7)
    asymmetryValueMA = ema(asymmetryValue, 14)
    upper/lower asymmetry flags per ta.roc(upATR/dnATR, 5) vs the 5.0 threshold.
    "near-50 rising" = |asym - 50| <= 5 AND roc(asym,5) > 0 — balanced coil
    just starting to tip upward (monthly/quarterly = the setup; weekly =
    tactical timing).

  Squeeze & Release (monthly = long-term; weekly = tactical):
    atr = ema(tr(true), 14); emaOfATR = ema(atr, 28)
    squeezeValue = ema((emaOfATR - atr) / ema(high - low, 28) * 100, 7)
    squeezeValueMA = ema(squeezeValue, 14)
    state: squeeze while value > MA, RELEASE while value < MA;
    "recent release after squeezing" = crossunder within the last 6 bars after
    a sustained (>= 6-bar) squeeze run.

  Long-horizon ROC: 3.5y (42 months) and 10y (120 months) price ROC, plus
  ROC-of-ROC (the rolling ROC now minus its value 12 months ago) — the
  attractive setup is a subdued long ROC that is ACCELERATING.

One v8-chart request per symbol (range=10y, interval=1wk), OHLC adjusted by
adjclose/close so splits don't distort the EMAs. Output:
lynch_reward_signals.csv, merged optionally by archetype_tags.py.

Pine-faithful primitives: ta.ema(x,n) == x.ewm(span=n, adjust=False).mean();
ta.tr(true) == max(h-l, |h-pc|, |l-pc|) with first bar h-l;
ta.roc(x,n) == 100*(x-x[n])/x[n].
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse

import numpy as np
import pandas as pd

from ticker_yf import YahooSession, Throttled, StaleCrumb


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def roc(s: pd.Series, n: int) -> pd.Series:
    prev = s.shift(n)
    return 100.0 * (s - prev) / prev


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df['close'].shift(1)
    tr = pd.concat([df['high'] - df['low'],
                    (df['high'] - pc).abs(),
                    (df['low'] - pc).abs()], axis=1).max(axis=1)
    if len(tr):
        tr.iloc[0] = df['high'].iloc[0] - df['low'].iloc[0]
    return tr


def asym_metrics(df, period=14, smooth=7, lookback=5, thresh=5.0):
    """Volatility asymmetry block, exactly per the reference indicator."""
    if len(df) < period + smooth + lookback:
        return None
    pc = df['close'].shift(1)
    up = (df['high'] - pc).clip(lower=0)
    dn = (pc - df['low']).clip(lower=0)
    upATR = ema(up, period)
    dnATR = ema(dn, period)
    ratio = upATR / (upATR + dnATR + 0.0001)
    asym = ema(ratio * 100.0, smooth)          # smoothing enabled (default)
    asymMA = ema(asym, period)
    aroc = roc(asym, lookback)
    upC = roc(upATR, lookback)
    dnC = roc(dnATR, lookback)
    upper = (upC > thresh) & ((dnC.abs() < thresh / 2) | (dnC < 0))
    lower = (dnC > thresh) & ((upC.abs() < thresh / 2) | (upC < 0))
    a, m, r = asym.iloc[-1], asymMA.iloc[-1], aroc.iloc[-1]
    return {
        'asym': round(float(a), 2),
        'asym_ma': round(float(m), 2),
        'asym_roc': round(float(r), 2) if pd.notna(r) else np.nan,
        'asym_upper': int(bool(upper.iloc[-1])),
        'asym_lower': int(bool(lower.iloc[-1])),
        'asym_near50_rising': int(bool(pd.notna(a) and pd.notna(r)
                                       and abs(a - 50.0) <= 5.0 and r > 0)),
    }


def squeeze_release(df, period=14, smooth=7, ema_len=14,
                    recent_bars=6, min_run=6):
    """Squeeze & Release block, exactly per the reference indicator."""
    if len(df) < period * 2 + smooth + ema_len:
        return None
    tr = true_range(df)
    atr = ema(tr, period)
    ema_atr = ema(atr, period * 2)
    vol_ind = ema_atr - atr
    ema_hl = ema(df['high'] - df['low'], period * 2)
    sq = ema(vol_ind / ema_hl * 100.0, smooth)
    sq_ma = ema(sq, ema_len)
    in_squeeze = (sq > sq_ma)                      # release = value < MA
    # most recent crossunder (squeeze -> release) and the run length before it
    trans = in_squeeze.astype(int).diff()          # -1 at a release crossunder
    release_idx = np.where(trans.values == -1)[0]
    release_recent = 0
    squeeze_run = 0
    if len(release_idx):
        last_rel = release_idx[-1]
        bars_since = len(df) - 1 - last_rel
        # run of consecutive squeeze bars immediately before the crossunder
        run = 0
        j = last_rel - 1
        while j >= 0 and bool(in_squeeze.iloc[j]):
            run += 1
            j -= 1
        squeeze_run = run
        release_recent = int(bars_since <= recent_bars and run >= min_run)
    return {
        'sr_value': round(float(sq.iloc[-1]), 2),
        'sr_ma': round(float(sq_ma.iloc[-1]), 2),
        'sr_release': int(not bool(in_squeeze.iloc[-1])),
        'sr_release_recent': release_recent,
        'sr_squeeze_run': int(squeeze_run),
    }


def long_roc(monthly_close: pd.Series):
    """3.5y / 10y ROC and their 12-month acceleration (ROC of ROC)."""
    out = {}
    c = monthly_close.dropna()
    out['price_years'] = round(len(c) / 12.0, 1)
    for label, months in (('3_5y', 42), ('10y', 120)):
        r = c / c.shift(months) - 1.0
        out[f'roc_{label}'] = (round(float(r.iloc[-1]), 4)
                               if len(c) > months and pd.notna(r.iloc[-1]) else np.nan)
        if len(c) > months + 12 and pd.notna(r.iloc[-1]) and pd.notna(r.iloc[-13]):
            out[f'roc_accel_{label}'] = round(float(r.iloc[-1] - r.iloc[-13]), 4)
        else:
            out[f'roc_accel_{label}'] = np.nan
    return out


def fetch_weekly(sess: YahooSession, symbol: str) -> pd.DataFrame:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?range=10y&interval=1wk")
    try:
        r = sess.opener.open(url, timeout=15)
        d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise Throttled()
        if e.code in (401, 403):
            raise StaleCrumb()
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()
    try:
        res = d['chart']['result'][0]
        q = res['indicators']['quote'][0]
        adj = (res.get('indicators', {}).get('adjclose') or [{}])[0].get('adjclose')
        idx = pd.to_datetime([pd.Timestamp(t, unit='s') for t in res['timestamp']])
        df = pd.DataFrame({'open': q['open'], 'high': q['high'],
                           'low': q['low'], 'close': q['close']}, index=idx)
        if adj is not None:
            factor = pd.Series(adj, index=idx) / df['close']
            for col in ('open', 'high', 'low', 'close'):
                df[col] = df[col] * factor
        return df.dropna()
    except Exception:
        return pd.DataFrame()


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule).agg({'open': 'first', 'high': 'max',
                                  'low': 'min', 'close': 'last'}).dropna()


def compute_row(symbol: str, wk: pd.DataFrame):
    if len(wk) < 60:            # need a bit over a year of weekly bars minimum
        return None
    mo = resample_ohlc(wk, 'ME')
    qt = resample_ohlc(wk, 'QE')
    row = {'symbol': symbol}
    for tag, frame in (('w', wk), ('m', mo), ('q', qt)):
        a = asym_metrics(frame)
        if a:
            row.update({f'{k}_{tag}' if k == 'asym' else k.replace('asym', f'asym_{tag}'): v
                        for k, v in a.items()})
    sr_m = squeeze_release(mo)
    if sr_m:
        row.update({k.replace('sr_', 'sr_m_'): v for k, v in sr_m.items()})
    sr_w = squeeze_release(wk)
    if sr_w:
        row.update({k.replace('sr_', 'sr_w_'): v for k, v in sr_w.items()})
    row.update(long_roc(mo['close']))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbols-from', default='lynch_universe.csv')
    ap.add_argument('--out', default='lynch_reward_signals.csv')
    ap.add_argument('--attempts', default='lynch_attempts.json')
    ap.add_argument('--rate', type=float, default=2.5)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--max-attempts', type=int, default=2)
    args = ap.parse_args()

    uni = pd.read_csv(args.symbols_from)['symbol'].dropna().drop_duplicates().tolist()
    done = set()
    if os.path.exists(args.out):
        try:
            done = set(pd.read_csv(args.out, usecols=['symbol'])['symbol'].dropna())
        except Exception:
            pass
    attempts = {}
    if os.path.exists(args.attempts):
        try:
            attempts = json.load(open(args.attempts))
        except Exception:
            attempts = {}
    todo = [s for s in uni if s not in done
            and attempts.get(s, 0) < args.max_attempts]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} to fetch ({len(done)} done)", file=sys.stderr)
    if not todo:
        return

    sess = YahooSession()
    print("warming session...", file=sys.stderr)
    if not sess.warm():
        sys.exit(2)

    header_written = os.path.exists(args.out) and os.path.getsize(args.out) > 0
    fout = open(args.out, 'a')
    min_int = 1.0 / args.rate if args.rate > 0 else 0
    last = ok = fail = consec = 0
    start = time.time()
    for i, sym in enumerate(todo, 1):
        gap = time.time() - last
        if gap < min_int:
            time.sleep(min_int - gap)
        last = time.time()
        try:
            wk = fetch_weekly(sess, sym)
            row = compute_row(sym, wk) if len(wk) else None
        except StaleCrumb:
            consec += 1
            if not sess.warm(force=True):
                time.sleep(30)
            continue
        except Throttled:
            consec += 1
            time.sleep(min(90, 8 * (1 + consec // 3)))
            continue
        except Exception:
            row = None
        if row is not None:
            pd.DataFrame([row]).to_csv(fout, header=not header_written, index=False)
            header_written = True
            fout.flush()
            ok += 1
            consec = 0
        else:
            fail += 1
            attempts[sym] = attempts.get(sym, 0) + 1
        if i % 50 == 0:
            json.dump(attempts, open(args.attempts, 'w'))
            rate = i / max(1.0, time.time() - start)
            print(f"  {i:,}/{len(todo):,} ok={ok} fail={fail} "
                  f"({rate:.2f}/s, ETA {(len(todo)-i)/rate/60:.0f}m)", file=sys.stderr)
            sys.stderr.flush()
    json.dump(attempts, open(args.attempts, 'w'))
    fout.close()
    print(f"DONE ok={ok} fail={fail}", file=sys.stderr)


if __name__ == '__main__':
    main()
