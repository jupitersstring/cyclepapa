"""Volatility-asymmetry & Squeeze-Release screener.

Python translation of the malikmck Pine v5 indicator:
"Squeeze & Release + Volatility Asymmetry [YourName]"

Applied on weekly AND monthly bars, per the user's request. The Pine
formulas are reproduced precisely:

  ATR_p          = EMA(TR, p)                              # p = period
  emaOfATR       = EMA(ATR_p, 2p)
  volatility     = emaOfATR - ATR_p
  emaHL          = EMA(high - low, 2p)
  squeezeValue   = EMA(volatility / emaHL * 100, smoothLen)
  squeezeValueMA = EMA(squeezeValue, emaLen)
  state          = "squeeze" if squeezeValue > squeezeValueMA else "release"
  hyper_squeeze  = squeezeValue > 0 AND rising over `hyperLen` bars

  upMove         = max(high - close[-1], 0)
  dnMove         = max(close[-1] - low, 0)
  upATR          = EMA(upMove, p)
  dnATR          = EMA(dnMove, p)
  asym_ratio     = upATR / (upATR + dnATR + eps)
  asym_value     = EMA(asym_ratio * 100, smoothLen)
  asym_MA        = EMA(asym_value, p)
  upRoc          = ROC(upATR, asymLookback)
  dnRoc          = ROC(dnATR, asymLookback)
  upperAsym      = upRoc > thresh  AND (|dnRoc| < thresh/2  OR  dnRoc < 0)
  lowerAsym      = dnRoc > thresh  AND (|upRoc| < thresh/2  OR  upRoc < 0)

The Pine defaults are used as-is: period=14, smoothLen=7, emaLen=14,
hyperLen=5, asymLookback=5, thresh=5.0%.

For each ticker × timeframe (weekly, monthly) the script reports:
  - latest squeeze value + MA
  - state (squeeze / release / hyper_squeeze)
  - bars-since-state-change (recency)
  - asym value + MA
  - asym state (upper / lower / neutral)
  - bars-since-asym-flag

Output: results_volasym/volatility_asymmetry.csv
"""
from __future__ import annotations
import argparse, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

OUTDIR = Path('results_volasym'); OUTDIR.mkdir(exist_ok=True)


def ema(s: pd.Series, length: int) -> pd.Series:
    """Pine ta.ema: exponential weighted mean with alpha = 2/(length+1)."""
    return s.ewm(span=length, adjust=False, min_periods=length).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
                     axis=1).max(axis=1)


def squeeze_release(high: pd.Series, low: pd.Series, close: pd.Series,
                     period: int = 14, smooth_len: int = 7, ema_len: int = 14,
                     hyper_len: int = 5) -> dict:
    """Returns dict of Series + the latest values, mirroring the Pine indicator."""
    atr = ema(true_range(high, low, close), period)
    ema_atr = ema(atr, period * 2)
    vol = ema_atr - atr
    ema_hl = ema(high - low, period * 2)
    raw = (vol / ema_hl.replace(0, np.nan)) * 100
    sq = ema(raw, smooth_len)
    sq_ma = ema(sq, ema_len)
    rising_hyper = sq.diff(hyper_len) > 0
    return {'sq': sq, 'sq_ma': sq_ma, 'rising_hyper': rising_hyper,
            'in_squeeze': sq > sq_ma, 'sq_above_zero': sq > 0}


def asymmetry(high: pd.Series, low: pd.Series, close: pd.Series,
              period: int = 14, smooth_len: int = 7,
              lookback: int = 5, thresh_pct: float = 5.0) -> dict:
    prev_close = close.shift(1)
    up_move = (high - prev_close).clip(lower=0)
    dn_move = (prev_close - low).clip(lower=0)
    up_atr = ema(up_move, period)
    dn_atr = ema(dn_move, period)
    asym_ratio = up_atr / (up_atr + dn_atr + 1e-4)
    asym_value = ema(asym_ratio * 100, smooth_len)
    asym_ma = ema(asym_value, period)
    up_roc = up_atr.pct_change(lookback) * 100
    dn_roc = dn_atr.pct_change(lookback) * 100
    upper_asym = (up_roc > thresh_pct) & ((dn_roc.abs() < thresh_pct / 2) | (dn_roc < 0))
    lower_asym = (dn_roc > thresh_pct) & ((up_roc.abs() < thresh_pct / 2) | (up_roc < 0))
    return {'asym': asym_value, 'asym_ma': asym_ma,
            'up_roc': up_roc, 'dn_roc': dn_roc,
            'upper_asym': upper_asym, 'lower_asym': lower_asym}


def bars_since(flag: pd.Series) -> int:
    """Bars since the last True in a boolean series. Returns -1 if never True."""
    if flag is None or flag.empty: return -1
    true_idx = flag[flag.fillna(False)].index
    if len(true_idx) == 0: return -1
    last = true_idx[-1]
    return int(flag.index.get_loc(flag.index[-1]) - flag.index.get_loc(last))


def analyze(ticker: str, period_yf: str = '10y') -> Optional[dict]:
    try:
        t = yf.Ticker(ticker)
        # Pull weekly + monthly OHLC in two calls
        wk = t.history(period=period_yf, interval='1wk', auto_adjust=True)
        mo = t.history(period='max', interval='1mo', auto_adjust=True)
    except Exception as exc:
        return {'ticker': ticker, 'error': str(exc)[:80]}
    if wk is None or wk.empty or mo is None or mo.empty:
        return {'ticker': ticker, 'error': 'no OHLC'}

    out = {'ticker': ticker}
    for label, df, min_bars in (('w', wk, 40), ('m', mo, 30)):
        if len(df) < min_bars:
            out[f'{label}_error'] = f'only {len(df)} bars'
            continue
        sr = squeeze_release(df['High'], df['Low'], df['Close'])
        asym = asymmetry(df['High'], df['Low'], df['Close'])

        # Detect state transitions on the squeeze series
        squeezed = sr['in_squeeze']
        cross_to_sq = squeezed & ~squeezed.shift(1).fillna(False)
        cross_to_rel = (~squeezed) & squeezed.shift(1).fillna(False)
        hyper = sr['sq_above_zero'] & sr['rising_hyper']

        latest_idx = -1
        out[f'{label}_sq']        = float(sr['sq'].iloc[latest_idx]) if not sr['sq'].empty else float('nan')
        out[f'{label}_sq_ma']     = float(sr['sq_ma'].iloc[latest_idx]) if not sr['sq_ma'].empty else float('nan')
        out[f'{label}_state']     = 'hyper_squeeze' if bool(hyper.iloc[latest_idx]) else (
                                     'squeeze' if bool(squeezed.iloc[latest_idx]) else 'release')
        out[f'{label}_bars_since_squeeze_cross']  = bars_since(cross_to_sq)
        out[f'{label}_bars_since_release_cross']  = bars_since(cross_to_rel)
        out[f'{label}_bars_since_hyper']           = bars_since(hyper)

        # Asymmetry
        out[f'{label}_asym']    = float(asym['asym'].iloc[latest_idx])    if not asym['asym'].empty else float('nan')
        out[f'{label}_asym_ma'] = float(asym['asym_ma'].iloc[latest_idx]) if not asym['asym_ma'].empty else float('nan')
        out[f'{label}_up_roc']  = float(asym['up_roc'].iloc[latest_idx])  if not asym['up_roc'].empty else float('nan')
        out[f'{label}_dn_roc']  = float(asym['dn_roc'].iloc[latest_idx])  if not asym['dn_roc'].empty else float('nan')
        out[f'{label}_asym_state'] = ('upper'   if bool(asym['upper_asym'].iloc[latest_idx]) else
                                       'lower'  if bool(asym['lower_asym'].iloc[latest_idx]) else
                                       'neutral')
        out[f'{label}_bars_since_upper_asym'] = bars_since(asym['upper_asym'])
        out[f'{label}_bars_since_lower_asym'] = bars_since(asym['lower_asym'])

    return out


def run_universe(tickers: list[str], workers: int = 4, sleep: float = 0.3) -> pd.DataFrame:
    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(analyze, tk): tk for tk in tickers}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                r = fut.result(timeout=90)
            except Exception as exc:
                r = {'ticker': futs[fut], 'error': f'worker exc: {exc}'}
            results.append(r)
            if i % 25 == 0 or i == len(tickers):
                el = time.time() - t0
                ok = sum(1 for x in results if x and 'error' not in x)
                print(f"  {i}/{len(tickers)}  ({i/el:.1f}/s)  valid={ok}")
            time.sleep(sleep / workers)
    return pd.DataFrame([r for r in results if r and 'error' not in r]).set_index('ticker')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tickers', nargs='+', default=None,
                    help='Explicit list of tickers (overrides --top-from)')
    ap.add_argument('--top-from', type=Path, default=None,
                    help='CSV file with index=ticker; takes the rows')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--sleep', type=float, default=0.3)
    args = ap.parse_args()

    if args.tickers:
        tickers = args.tickers
    elif args.top_from and args.top_from.exists():
        df = pd.read_csv(args.top_from, index_col=0)
        tickers = df.index.astype(str).tolist()
    else:
        # Default: scan the entire price cache
        tickers = sorted({p.name.split('__')[0]
                          for p in Path('.cache/yf').glob('*__price.parquet')})
    print(f"Tickers to analyze: {len(tickers)}")
    out = run_universe(tickers, workers=args.workers, sleep=args.sleep)
    out.to_csv(OUTDIR / 'volatility_asymmetry.csv')
    print(f"wrote {OUTDIR/'volatility_asymmetry.csv'} ({len(out)} rows)")

    # Print headline summary
    if not out.empty:
        pd.set_option('display.width', 240); pd.set_option('display.max_columns', 30)
        # Sort by interesting filter: monthly hyper_squeeze with positive upper_asym recent
        interesting = out[
            (out.get('m_state','').isin(['hyper_squeeze','squeeze']))
            & (out.get('m_asym_state','').isin(['upper']))
        ]
        print("\nMONTHLY in squeeze/hyper-squeeze AND upper-asymmetry (bullish setup):")
        cols = ['m_state','m_sq','m_sq_ma','m_asym_state','m_asym','m_up_roc','m_dn_roc',
                'm_bars_since_squeeze_cross','w_state','w_asym_state']
        cols = [c for c in cols if c in interesting.columns]
        for c in ('m_sq','m_sq_ma','m_asym','m_up_roc','m_dn_roc'):
            if c in interesting.columns:
                interesting[c] = pd.to_numeric(interesting[c], errors='coerce').round(2)
        print(interesting[cols].to_string() if not interesting.empty else "  (none)")

        print("\nWEEKLY hyper-squeeze + upper-asymmetry (shorter-term bullish setup):")
        interesting2 = out[
            (out.get('w_state','') == 'hyper_squeeze')
            & (out.get('w_asym_state','') == 'upper')
        ]
        for c in ('w_sq','w_sq_ma','w_asym','w_up_roc','w_dn_roc'):
            if c in interesting2.columns:
                interesting2[c] = pd.to_numeric(interesting2[c], errors='coerce').round(2)
        cols2 = ['w_state','w_sq','w_sq_ma','w_asym_state','w_asym','w_up_roc','w_dn_roc',
                 'w_bars_since_squeeze_cross','m_state']
        cols2 = [c for c in cols2 if c in interesting2.columns]
        print(interesting2[cols2].to_string() if not interesting2.empty else "  (none)")


if __name__ == '__main__':
    main()
