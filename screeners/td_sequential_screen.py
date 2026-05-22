#!/usr/bin/env python3
"""TD Sequential (DeMark) — mean-reversion screener across 5 timeframes.

Port of malikmck's "Enhanced MTF TD Sequential" Pine indicator. Computes the
canonical DeMark setup (1-9) and countdown (1-13) per timeframe, plus
"perfection" (the bar-8/9 lower-low confirmation for buy setups, higher-high
for sell setups). Aggregates across timeframes into two primary readings:

    net_setup   =  buy_setup_prop  -  sell_setup_prop      (% of max)
    net_perfect =  buy_perfect_prop - sell_perfect_prop    (% of TFs perfect)

Timeframes:  1h, 4h (resampled from 1h), 1d, 1w, 1M.

Strongly negative net_setup / net_perfect = stretched DOWN → bullish mean
reversion candidate (buy setups firing across the stack). Strongly positive =
stretched UP → bearish reversion (short / take-profit candidate).

TD rules implemented:
  • Bull (buy) setup: 9 consecutive bars of close < close[4]; resets on a
    bar where close >= close[4]. Bar count caps at 9.
  • Bear (sell) setup: 9 bars of close > close[4]; symmetric.
  • Buy perfection: at bar 8 or 9, low <= min(low[2], low[3]).
  • Sell perfection: at bar 8 or 9, high >= max(high[2], high[3]).
  • Countdown buy (after setup=9): close <= low[2], cumulative to 13.
  • Countdown sell: close >= high[2], cumulative to 13.

Usage:
    python3 td_sequential_screen.py \\
        --universe my_universe.csv \\
        --out td_seq.csv \\
        [--hourly-days 60]    # how many days of hourly data (yfinance limit ~730)
"""
import argparse, sys, time, warnings
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

ap = argparse.ArgumentParser()
ap.add_argument('--universe', required=True)
ap.add_argument('--out', required=True)
ap.add_argument('--hourly-days', type=int, default=60,
                help='Days of hourly history (yfinance caps at ~730)')
ap.add_argument('--daily-period', default='5y')
ap.add_argument('--sleep', type=float, default=0.3)
ap.add_argument('--checkpoint', type=int, default=100)
args = ap.parse_args()


# ─── TD Sequential core ────────────────────────────────────────────────────

def td_setup_counts(c: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Returns (bull_count, bear_count) arrays — current TD setup count per bar.

    Bull count increments while close < close[4]; resets to 0 otherwise. Caps
    visually at 9 but we keep raw value so downstream can detect 13-extension.
    """
    if len(c) < 5:
        z = pd.Series(np.zeros(len(c), dtype=int), index=c.index)
        return z, z.copy()
    cm4 = c.shift(4)
    bull_step = (c < cm4).astype(int)
    bear_step = (c > cm4).astype(int)
    bull = np.zeros(len(c), dtype=int)
    bear = np.zeros(len(c), dtype=int)
    bs = bull_step.values
    br = bear_step.values
    for i in range(len(c)):
        if bs[i] == 1:
            bull[i] = bull[i-1] + 1 if i > 0 else 1
        else:
            bull[i] = 0
        if br[i] == 1:
            bear[i] = bear[i-1] + 1 if i > 0 else 1
        else:
            bear[i] = 0
    return pd.Series(bull, index=c.index), pd.Series(bear, index=c.index)


def td_perfection(bull: pd.Series, bear: pd.Series,
                  high: pd.Series, low: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Per-bar buy_perfect / sell_perfect flags.

    Standard DeMark perfection: at setup bar 8 or 9, the low (for buy) must
    be <= min(low[2], low[3]); symmetric for sell with highs.
    """
    l2, l3 = low.shift(2), low.shift(3)
    h2, h3 = high.shift(2), high.shift(3)
    in_buy = bull.isin([8, 9])
    in_sell = bear.isin([8, 9])
    buy_perf = in_buy & (low <= np.minimum(l2, l3))
    sell_perf = in_sell & (high >= np.maximum(h2, h3))
    return buy_perf.fillna(False), sell_perf.fillna(False)


def td_countdown(close: pd.Series, high: pd.Series, low: pd.Series,
                 bull: pd.Series, bear: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Cumulative TD Countdown 0..13 once setup hits 9.

    Buy countdown: starts the bar after bull setup == 9, increments when
    close <= low[2]; runs until 13. Sell symmetric (close >= high[2]).
    A new setup-9 in the opposite direction cancels the countdown.
    """
    n = len(close)
    cd_buy = np.zeros(n, dtype=int)
    cd_sell = np.zeros(n, dtype=int)
    active_buy = False
    active_sell = False
    cb, cs = 0, 0
    l2 = low.shift(2).values
    h2 = high.shift(2).values
    c = close.values
    bl = bull.values
    br = bear.values
    for i in range(n):
        if bl[i] == 9:
            active_buy = True
            active_sell = False
            cb = 0
            cs = 0
        if br[i] == 9:
            active_sell = True
            active_buy = False
            cs = 0
            cb = 0
        if active_buy and i >= 2 and not np.isnan(l2[i]) and c[i] <= l2[i]:
            cb = min(cb + 1, 13)
        if active_sell and i >= 2 and not np.isnan(h2[i]) and c[i] >= h2[i]:
            cs = min(cs + 1, 13)
        cd_buy[i] = cb
        cd_sell[i] = cs
        if cb >= 13:
            active_buy = False
        if cs >= 13:
            active_sell = False
    return pd.Series(cd_buy, index=close.index), pd.Series(cd_sell, index=close.index)


def td_snapshot(df: pd.DataFrame) -> dict:
    """Returns the last-bar TD readings for one timeframe."""
    if df is None or len(df) < 10:
        return dict(bull=0, bear=0, buy_perf=False, sell_perf=False,
                    cd_buy=0, cd_sell=0, has_data=False)
    c, h, l = df['Close'], df['High'], df['Low']
    bull, bear = td_setup_counts(c)
    bp, sp = td_perfection(bull, bear, h, l)
    cdb, cds = td_countdown(c, h, l, bull, bear)
    return dict(
        bull=int(bull.iloc[-1]),
        bear=int(bear.iloc[-1]),
        buy_perf=bool(bp.iloc[-1]),
        sell_perf=bool(sp.iloc[-1]),
        cd_buy=int(cdb.iloc[-1]),
        cd_sell=int(cds.iloc[-1]),
        has_data=True,
    )


# ─── Resampling helpers ────────────────────────────────────────────────────

OHLC_AGG = {'Open': 'first', 'High': 'max', 'Low': 'min',
            'Close': 'last', 'Volume': 'sum'}


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.resample(rule).agg(OHLC_AGG).dropna(subset=['Close'])
    return out


def fetch_one(t: str) -> dict:
    """Fetch OHLCV at multiple resolutions for one ticker.

    yfinance only supports intraday for trailing windows. We pull hourly for
    `args.hourly_days` to feed 1h and 4h, daily for `args.daily_period` to feed
    1d / 1w / 1M.
    """
    out = {'1h': None, '4h': None, '1d': None, '1w': None, '1M': None}
    try:
        # Hourly (and derived 4h)
        hr = yf.download(t, period=f'{args.hourly_days}d', interval='1h',
                         progress=False, auto_adjust=False, threads=False)
        if isinstance(hr.columns, pd.MultiIndex):
            hr.columns = hr.columns.get_level_values(0)
        if hr is not None and len(hr) > 10:
            hr = hr.dropna(subset=['Close'])
            out['1h'] = hr
            out['4h'] = resample(hr, '4h')
    except Exception:
        pass
    try:
        # Daily (and derived weekly/monthly)
        dly = yf.download(t, period=args.daily_period, interval='1d',
                          progress=False, auto_adjust=False, threads=False)
        if isinstance(dly.columns, pd.MultiIndex):
            dly.columns = dly.columns.get_level_values(0)
        if dly is not None and len(dly) > 30:
            dly = dly.dropna(subset=['Close'])
            out['1d'] = dly
            out['1w'] = resample(dly, 'W-FRI')
            out['1M'] = resample(dly, 'ME')
    except Exception:
        pass
    return out


# ─── Main loop ─────────────────────────────────────────────────────────────

uni = pd.read_csv(args.universe)
syms = uni['ticker'].dropna().astype(str).unique().tolist()
print(f"TD Sequential screen — {len(syms)} tickers", file=sys.stderr)

TFS = ['1h', '4h', '1d', '1w', '1M']
N_TFS = len(TFS)
MAX_SETUP_SUM = 9 * N_TFS   # 45

rows = []
for i, t in enumerate(syms):
    try:
        bars = fetch_one(t)
        rec = {'ticker': t}
        bull_sum = bear_sum = 0
        buy_perf_n = sell_perf_n = 0
        cd_buy_sum = cd_sell_sum = 0
        live_tfs = 0
        for tf in TFS:
            snap = td_snapshot(bars.get(tf))
            rec[f'bull_{tf}'] = snap['bull']
            rec[f'bear_{tf}'] = snap['bear']
            rec[f'bp_{tf}'] = snap['buy_perf']
            rec[f'sp_{tf}'] = snap['sell_perf']
            rec[f'cdb_{tf}'] = snap['cd_buy']
            rec[f'cds_{tf}'] = snap['cd_sell']
            if snap['has_data']:
                live_tfs += 1
                bull_sum += min(snap['bull'], 9)
                bear_sum += min(snap['bear'], 9)
                buy_perf_n += int(snap['buy_perf'])
                sell_perf_n += int(snap['sell_perf'])
                cd_buy_sum += snap['cd_buy']
                cd_sell_sum += snap['cd_sell']

        if live_tfs == 0:
            continue

        buy_setup_prop = bull_sum / MAX_SETUP_SUM * 100
        sell_setup_prop = bear_sum / MAX_SETUP_SUM * 100
        buy_perf_prop = buy_perf_n / N_TFS * 100
        sell_perf_prop = sell_perf_n / N_TFS * 100

        rec['buy_setup_prop'] = round(buy_setup_prop, 2)
        rec['sell_setup_prop'] = round(sell_setup_prop, 2)
        rec['buy_perfect_prop'] = round(buy_perf_prop, 2)
        rec['sell_perfect_prop'] = round(sell_perf_prop, 2)
        rec['net_setup'] = round(buy_setup_prop - sell_setup_prop, 2)
        rec['net_perfect'] = round(buy_perf_prop - sell_perf_prop, 2)
        rec['cd_buy_sum'] = cd_buy_sum
        rec['cd_sell_sum'] = cd_sell_sum
        rec['tfs_with_data'] = live_tfs

        # Mean-reversion conviction score:
        #   strongly negative net_setup + perfection across TFs = BUY signal
        #   strongly positive = SELL signal
        rec['mr_buy_score']  = round(-rec['net_setup'] * 0.6 - rec['net_perfect'] * 0.4
                                     + (cd_buy_sum - cd_sell_sum) * 0.5, 2)
        rec['mr_sell_score'] = round( rec['net_setup'] * 0.6 + rec['net_perfect'] * 0.4
                                     + (cd_sell_sum - cd_buy_sum) * 0.5, 2)
        rows.append(rec)
    except Exception as e:
        print(f"  {t} err: {e}", file=sys.stderr)

    time.sleep(args.sleep)
    if (i + 1) % args.checkpoint == 0:
        pd.DataFrame(rows).to_csv(args.out, index=False)
        print(f"  {i+1}/{len(syms)} | with-data {len(rows)}", file=sys.stderr)

df = pd.DataFrame(rows)
if len(df):
    df = df.sort_values('mr_buy_score', ascending=False)
df.to_csv(args.out, index=False)
print(f"DONE: {len(df)} rows -> {args.out}", file=sys.stderr)

# ─── Display top mean-reversion candidates ────────────────────────────────
if len(df):
    pd.set_option('display.width', 200); pd.set_option('display.max_colwidth', 18)
    print(f"\n{'='*120}")
    print(f"  TOP MEAN-REVERSION BUYS (negative net_setup + buy perfection across TFs)")
    print(f"{'='*120}")
    cols = ['ticker','net_setup','net_perfect',
            'buy_setup_prop','sell_setup_prop',
            'buy_perfect_prop','sell_perfect_prop',
            'cd_buy_sum','cd_sell_sum','mr_buy_score']
    print(df.head(40)[[c for c in cols if c in df.columns]].to_string(index=False))

    print(f"\n{'='*120}")
    print(f"  TOP MEAN-REVERSION SELLS (positive net_setup + sell perfection)")
    print(f"{'='*120}")
    sells = df.sort_values('mr_sell_score', ascending=False).head(40)
    print(sells[[c for c in cols if c in sells.columns]].to_string(index=False))
