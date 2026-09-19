"""Lynch "years of progress rewarded in a year" — price-series signals.

The Fannie Mae pattern (Beating the Street): a business advances fundamentally
for YEARS while the stock goes nowhere, then the market pays it all at once
($16 -> $42 in 1989 — "several years' worth of patience was rewarded in one").
The fundamental legs live in the master; THIS enricher computes the price-
series legs, transcribing the Squeeze & Release + Volatility Asymmetry Pine v5
methodology EXACTLY (© malikmck, MPL 2.0 — the reference indicator we already
use elsewhere):

  Volatility asymmetry (per timeframe: monthly / quarterly — MONTHLY BARS
  ONLY are fetched; the weekly tactical layer is deferred):
    upwardMove   = max(high - close[1], 0)
    downwardMove = max(close[1] - low, 0)
    upATR = ema(upwardMove, 14); dnATR = ema(downwardMove, 14)
    asymmetryValue = ema(upATR / (upATR + dnATR + 0.0001) * 100, 7)
    asymmetryValueMA = ema(asymmetryValue, 14)
    upper/lower asymmetry flags per ta.roc(upATR/dnATR, 5) vs the 5.0 threshold.
    "near-50 rising" = |asym - 50| <= 5 AND roc(asym,5) > 0 — balanced coil
    just starting to tip upward (monthly/quarterly = the setup).

  Squeeze & Release (monthly = long-term):
    atr = ema(tr(true), 14); emaOfATR = ema(atr, 28)
    squeezeValue = ema((emaOfATR - atr) / ema(high - low, 28) * 100, 7)
    squeezeValueMA = ema(squeezeValue, 14)
    state: squeeze while value > MA, RELEASE while value < MA;
    "recent release after squeezing" = crossunder within the last 6 bars after
    a sustained (>= 6-bar) squeeze run.

  Long-horizon ROC: 3.5y (42 months) and 10y (120 months) price ROC, plus
  ROC-of-ROC (the rolling ROC now minus its value 12 months ago) — the
  attractive setup is a subdued long ROC that is ACCELERATING.

One v8-chart request per symbol (range=12y, interval=1mo), OHLC adjusted by
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
        release_recent = int(bars_since < recent_bars and run >= min_run)  # 6-bar window (0..5)
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
    # FRESH short-horizon ROC (from the bars just fetched — the master's
    # momentum_12m can lag by months). Used for the "reward not yet paid"
    # gate: a release + rising asymmetry AFTER a 100% rally is the payment
    # already arriving, not the coil Lynch wants to buy.
    for label, months in (('6m', 6), ('12m', 12)):
        # (audit #7) capped +/-1000%: a near-zero prior price prints a
        # multi-thousand-percent "ROC" that is a base artifact, not a return
        out[f'roc_{label}'] = (round(float(np.clip(c.iloc[-1] / c.iloc[-1 - months] - 1.0, -10.0, 10.0)), 4)
                               if len(c) > months and c.iloc[-1 - months] > 0 else np.nan)
    for label, months in (('3_5y', 42), ('10y', 120)):
        r = (c / c.shift(months).where(c.shift(months) > 0) - 1.0)
        r = r.replace([np.inf, -np.inf], np.nan)
        out[f'roc_{label}'] = (round(float(np.clip(r.iloc[-1], -10.0, 10.0)), 4)
                               if len(c) > months and pd.notna(r.iloc[-1]) else np.nan)
        if len(c) > months + 12 and pd.notna(r.iloc[-1]) and pd.notna(r.iloc[-13]):
            out[f'roc_accel_{label}'] = round(float(np.clip(r.iloc[-1] - r.iloc[-13], -10.0, 10.0)), 4)
        else:
            out[f'roc_accel_{label}'] = np.nan
    return out




# ---- 52-week-high block (absolute + relative to the country index) ----
_BENCH = None
_SUFFIX_INDEX = {
    '.T': '^N225', '.KS': '^KS11', '.KQ': '^KS11', '.TW': '^TWII', '.TWO': '^TWII',
    '.HK': '^HSI', '.SS': '000001.SS', '.SZ': '000001.SS', '.NS': '^NSEI',
    '.BO': '^NSEI', '.BK': '^SET.BK', '.JK': '^JKSE', '.KL': '^KLSE',
    '.SI': '^STI', '.AX': '^AXJO', '.L': '^FTSE', '.DE': '^GDAXI',
    '.F': '^GDAXI', '.PA': '^FCHI', '.SA': '^BVSP', '.MX': '^MXX',
    '.IS': '^XU100',
}


def _benchmarks():
    global _BENCH
    if _BENCH is None:
        _BENCH = {}
        if os.path.exists('benchmark_series.csv'):
            try:
                b = pd.read_csv('benchmark_series.csv', index_col=0, parse_dates=True)
                for c in b.columns:
                    s = b[c].dropna()
                    s.index = s.index.to_period('M')
                    _BENCH[c] = s[~s.index.duplicated(keep='last')]
            except Exception:
                _BENCH = {}
    return _BENCH


def _index_for(symbol: str):
    for suf, idx in _SUFFIX_INDEX.items():
        if symbol.endswith(suf):
            return idx
    return '^GSPC'                       # US listings and default


def high_metrics(mo: pd.DataFrame, symbol: str):
    """52-week-high position, absolute and relative to the country index.
    Monthly bars: 52w = trailing 12 bars. is_high uses a 3% proximity band
    (monthly closes never sit exactly on the intramonth high). base_depth =
    where the name stood vs ITS OWN then-52w-high a year ago — a low value
    means the current high is a FRESH emergence from a base, not the middle
    of an old uptrend."""
    out = {}
    c = mo['close'].dropna()
    h = mo['high'].dropna()
    if len(c) < 13:
        return out
    hi12 = float(h.tail(12).max())
    out['pct_52w_high'] = round(float(c.iloc[-1] / hi12), 4) if hi12 > 0 else np.nan
    out['is_52w_high'] = int(out.get('pct_52w_high', 0) >= 0.97)
    tail_h = h.tail(12)
    out['months_since_52w_high'] = int(len(tail_h) - 1 - int(tail_h.values.argmax()))
    hi12_ago = float(h.iloc[-24:-12].max()) if len(h) >= 24 else np.nan
    out['base_depth_12m'] = (round(float(c.iloc[-13] / hi12_ago), 4)
                             if len(c) >= 13 and pd.notna(hi12_ago) and hi12_ago > 0 else np.nan)
    # relative-strength ratio vs the country benchmark. A STALE or
    # near-empty benchmark silently anchors the "current" ratio years in
    # the past (Turkey's ^XU100 froze at 2021; Thailand had 1 point) —
    # require a live, populated series or emit no rel metrics at all.
    bench = _benchmarks().get(_index_for(symbol))
    if bench is not None and len(bench) >= 13:
        _bench_age_mo = (pd.Period.now('M') - bench.index.max()).n
        if _bench_age_mo > 2:
            bench = None
    else:
        bench = None
    if bench is not None:
        cp = c.copy()
        cp.index = cp.index.to_period('M')
        cp = cp[~cp.index.duplicated(keep='last')]
        ratio = (cp / bench).dropna()
        if len(ratio) >= 13:
            rhi12 = float(ratio.tail(12).max())
            out['rel_pct_52w_high'] = round(float(ratio.iloc[-1] / rhi12), 4) if rhi12 > 0 else np.nan
            out['rel_is_52w_high'] = int(out.get('rel_pct_52w_high', 0) >= 0.97)
    return out


def fetch_monthly(sess: YahooSession, symbol: str) -> pd.DataFrame:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?range=12y&interval=1mo")
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
            factor = (pd.Series(adj, index=idx)
              / df['close'].where(df['close'] > 0))   # 0-close -> NaN, not inf
            for col in ('open', 'high', 'low', 'close'):
                df[col] = df[col] * factor
        return df.dropna()
    except Exception:
        return pd.DataFrame()


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule).agg({'open': 'first', 'high': 'max',
                                  'low': 'min', 'close': 'last'}).dropna()



# Canonical output schema. compute_row's sections are conditional (short
# history, no benchmark, thin tape), so raw dicts have VARIABLE key sets —
# serializing them directly misaligned ~12% of rows (columns shifted past
# every gap). Every row is normalized to this exact field order.
ALL_FIELDS = [
    'symbol',
    'asym_m', 'asym_m_ma', 'asym_m_roc', 'asym_m_upper', 'asym_m_lower',
    'asym_m_near50_rising',
    'asym_q', 'asym_q_ma', 'asym_q_roc', 'asym_q_upper', 'asym_q_lower',
    'asym_q_near50_rising',
    'sr_m_value', 'sr_m_ma', 'sr_m_release', 'sr_m_release_recent',
    'sr_m_squeeze_run',
    'price_years', 'roc_6m', 'roc_12m', 'roc_3_5y', 'roc_accel_3_5y',
    'roc_10y', 'roc_accel_10y',
    'pct_52w_high', 'is_52w_high', 'months_since_52w_high', 'base_depth_12m',
    'rel_pct_52w_high', 'rel_is_52w_high',
    'stale_tape', 'last_bar_age_days',
]

def compute_row(symbol: str, mo: pd.DataFrame):
    if len(mo) < 27:            # asym needs period+smooth+lookback monthly bars
        return None
    qt = resample_ohlc(mo, 'QE')
    row = {'symbol': symbol}
    for tag, frame in (('m', mo), ('q', qt)):
        a = asym_metrics(frame)
        if a:
            row.update({f'{k}_{tag}' if k == 'asym' else k.replace('asym', f'asym_{tag}'): v
                        for k, v in a.items()})
    sr_m = squeeze_release(mo)
    if sr_m:
        row.update({k.replace('sr_', 'sr_m_'): v for k, v in sr_m.items()})
    row.update(long_roc(mo['close']))
    row.update(high_metrics(mo, symbol))
    # Halted / frozen-tape guard (the Icure lesson: a 13-month trading
    # suspension manufactures a fake "stagnation + release"). A run of
    # identical closes at the tail, or a last bar far in the past, marks the
    # tape as not live; the archetype excludes such names.
    tail = mo['close'].dropna().tail(4)
    row['stale_tape'] = int(len(tail) >= 3 and tail.nunique() == 1)
    row['last_bar_age_days'] = int((pd.Timestamp.now() - mo.index[-1]).days)
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
            mo = fetch_monthly(sess, sym)
            row = compute_row(sym, mo) if len(mo) else None
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
            row = {k: row.get(k, np.nan) for k in ALL_FIELDS}   # fixed schema
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
