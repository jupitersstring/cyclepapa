"""Non-US country scanner — generalized from uk_scanner.py.

Bypasses yfinance get_earnings_dates (which fails for most non-US/DE names)
by using quarterly_income_stmt + annual income_stmt directly. Works for
any region where yfinance returns these endpoints (~most LSE, MCE, OSL,
CPH, HEL, BRU, ATH, LIS, VIE names).

Usage:
    python scan_country.py --universe universe_eu_extra.csv --output-dir results_eu_extra
    python scan_country.py --tickers VOD.L SAP.DE  --output-dir results_adhoc

Output: <output-dir>/growth_<region>.csv with one row per ticker showing
three-window growth (QoQ + single-Q YoY + annual YoY) per metric +
valuation snapshot.
"""
from __future__ import annotations
import argparse, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np, pandas as pd, yfinance as yf

UA_SLEEP_DEFAULT = 0.8
WORKERS_DEFAULT = 4


def _sym(a, b):
    d = abs(a) + abs(b)
    return 2 * (a - b) / d if d > 0 else float('nan')


REV_TAGS = ('Total Revenue', 'Operating Revenue', 'Revenue')
EBITDA_TAGS = ('EBITDA', 'Normalized EBITDA')
NI_TAGS = ('Net Income', 'Net Income Common Stockholders')
EPS_TAGS = ('Diluted EPS', 'Basic EPS')


def fetch_one(tkr: str) -> Optional[dict]:
    try:
        t = yf.Ticker(tkr)
        q_inc = t.quarterly_income_stmt
        a_inc = t.income_stmt
        info = t.info or {}
    except Exception as exc:
        return {'ticker': tkr, 'error': str(exc)[:80]}

    if (q_inc is None or q_inc.empty) and (a_inc is None or a_inc.empty):
        return {'ticker': tkr, 'error': 'no income data'}

    out: dict = {'ticker': tkr}

    def pick(df, tags):
        if df is None or df.empty: return pd.Series(dtype=float)
        for tag in tags:
            if tag in df.index:
                s = pd.to_numeric(df.loc[tag], errors='coerce').dropna()
                if not s.empty: return s
        return pd.Series(dtype=float)

    for label, tags in (('revenue', REV_TAGS), ('ebitda', EBITDA_TAGS),
                        ('net_inc', NI_TAGS), ('eps', EPS_TAGS)):
        q = pick(q_inc, tags); a = pick(a_inc, tags)
        q_series = q.copy()
        q_series.index = pd.to_datetime(q_series.index, errors='coerce')
        q_series = q_series[~q_series.index.isna()].sort_index()
        a_series = a.copy()
        a_series.index = pd.to_datetime(a_series.index, errors='coerce')
        a_series = a_series[~a_series.index.isna()].sort_index()

        rec: dict = {'n_q': len(q_series), 'n_a': len(a_series)}

        if len(q_series) >= 2:
            rec['q_now'] = float(q_series.iloc[-1])
            rec['q_prev_q'] = float(q_series.iloc[-2])
            rec['qoq'] = _sym(rec['q_now'], rec['q_prev_q'])
        if len(q_series) >= 5:
            rec['q_prev_yr'] = float(q_series.iloc[-5])
            rec['yoy_q'] = _sym(rec['q_now'], rec['q_prev_yr'])
        if len(a_series) >= 2:
            rec['a_now'] = float(a_series.iloc[-1])
            rec['a_prev'] = float(a_series.iloc[-2])
            rec['yoy_a'] = _sym(rec['a_now'], rec['a_prev'])
        if len(a_series) >= 3:
            rec['a_prev2'] = float(a_series.iloc[-3])
            rec['yoy_a_prior'] = _sym(rec['a_prev'], rec['a_prev2'])
            rec['accel_a'] = rec['yoy_a'] - rec['yoy_a_prior']
        if len(q_series) >= 8:
            ltm_now = float(q_series.iloc[-4:].sum())
            ltm_prev = float(q_series.iloc[-8:-4].sum())
            rec['ltm_now'] = ltm_now
            rec['ltm_prev'] = ltm_prev
            rec['ltm_chg'] = _sym(ltm_now, ltm_prev)

        out[label] = rec

    out['info'] = {k: info.get(k) for k in
                   ('marketCap', 'priceToBook', 'priceToSalesTrailing12Months',
                    'enterpriseToEbitda', 'trailingPE', 'currentPrice',
                    'enterpriseValue', 'totalCash', 'totalDebt',
                    'sharesOutstanding', 'currency')}
    out['name'] = info.get('longName') or info.get('shortName') or ''
    out['sector'] = info.get('sector') or ''
    out['industry'] = info.get('industry') or ''
    return out


def flatten_rows(results: list) -> pd.DataFrame:
    rows = []
    for r in results:
        if not r or 'error' in r: continue
        row = {'ticker': r['ticker'],
               'name': r.get('name', ''),
               'sector': r.get('sector', ''),
               'industry': r.get('industry', '')}
        info = r.get('info', {})
        for k, v in info.items():
            row[f'info_{k}'] = v
        for met in ('revenue', 'ebitda', 'net_inc', 'eps'):
            d = r.get(met, {})
            for k, v in d.items():
                row[f'{met}_{k}'] = v
        rows.append(row)
    return pd.DataFrame(rows).set_index('ticker') if rows else pd.DataFrame()


def fix_ticker_for_yf(t: str) -> str:
    """Restore exchange suffix if the universe-builder stripped it.

    The universe-builder rewrites BRK.B -> BRK-B (correct for share class),
    but it sometimes also rewrites .L / .OL / .CO / .HE / .MC / .BR / .AT /
    .LS / .VI suffixes to dash when the symbol matches the share-class
    regex. This restores them.
    """
    KNOWN_EU_SUFFIXES = ('-L', '-OL', '-CO', '-HE', '-MC', '-BR', '-AT',
                        '-LS', '-VI', '-PA', '-DE', '-AS', '-MI', '-SW',
                        '-ST', '-TO', '-V', '-WA', '-WSE')
    for suf in KNOWN_EU_SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= 2:
            # Only restore if dash-suffix is non-share-class (>=2 chars)
            if len(suf) > 2:  # genuine exchange suffix
                return t[:len(t)-len(suf)] + '.' + suf[1:]
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--universe', type=Path, default=Path('universe_eu_extra.csv'),
                    help='CSV indexed by ticker; can also pass --tickers')
    ap.add_argument('--tickers', nargs='+', default=None)
    ap.add_argument('--output-dir', type=Path, default=Path('results_eu_extra'))
    ap.add_argument('--workers', type=int, default=WORKERS_DEFAULT)
    ap.add_argument('--sleep', type=float, default=UA_SLEEP_DEFAULT)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.tickers:
        raw = args.tickers
    elif args.universe.exists():
        df = pd.read_csv(args.universe, index_col=0)
        raw = df.index.astype(str).tolist()
    else:
        print(f"No tickers or universe specified")
        return

    tickers = [fix_ticker_for_yf(t) for t in raw]
    print(f"Universe: {len(tickers)} tickers")
    print(f"Sample fixed tickers: {tickers[:8]}")

    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(fetch_one, t): t for t in tickers}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                r = fut.result(timeout=60)
            except Exception as exc:
                r = {'ticker': futs[fut], 'error': f'worker exc: {exc}'}
            results.append(r)
            if i % 50 == 0 or i == len(tickers):
                el = time.time() - t0
                ok = sum(1 for x in results if x and 'error' not in x)
                print(f"  {i}/{len(tickers)}  ({i/el:.1f}/s)  valid={ok}")
            time.sleep(args.sleep / args.workers)
    print(f"done in {time.time()-t0:.0f}s")

    df = flatten_rows(results)
    out_path = args.output_dir / 'growth.csv'
    df.to_csv(out_path)
    print(f"wrote {out_path} with {len(df)} rows")


if __name__ == '__main__':
    main()
