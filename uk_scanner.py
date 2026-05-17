"""UK universe scanner — bypasses get_earnings_dates by using the quarterly +
annual income_stmt directly. yfinance returns 5-7 quarters of
quarterly_income_stmt and 4-5 years of annual income_stmt for most LSE names;
combining them gives enough history for QoQ + YoY single-Q + annual YoY
growth checks.

Output: results_uk/growth_uk.csv with one row per (ticker, metric) showing
QoQ / single-Q YoY / annual YoY direction and latest level.
"""
from __future__ import annotations
import time, re, math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np, pandas as pd, yfinance as yf

UA_SLEEP = 0.3
WORKERS = 6
OUTDIR = Path('results_uk'); OUTDIR.mkdir(exist_ok=True)


def _sym(a, b):
    d = abs(a)+abs(b)
    return 2*(a-b)/d if d > 0 else float('nan')


def fetch_one(tkr: str) -> Optional[dict]:
    """Pull quarterly + annual + info for one UK ticker. Returns dict with
    three-window growth on revenue / net income / EBITDA + valuation."""
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

    REV_TAGS = ('Total Revenue','Operating Revenue','Revenue')
    EBITDA_TAGS = ('EBITDA','Normalized EBITDA')
    NI_TAGS = ('Net Income','Net Income Common Stockholders')
    EPS_TAGS = ('Diluted EPS','Basic EPS')

    def pick(df, tags):
        if df is None or df.empty: return pd.Series(dtype=float)
        for tag in tags:
            if tag in df.index:
                s = pd.to_numeric(df.loc[tag], errors='coerce').dropna()
                if not s.empty: return s
        return pd.Series(dtype=float)

    for label, q_tags, a_tags in [
        ('revenue', REV_TAGS, REV_TAGS),
        ('ebitda',  EBITDA_TAGS, EBITDA_TAGS),
        ('net_inc', NI_TAGS, NI_TAGS),
        ('eps',     EPS_TAGS, EPS_TAGS),
    ]:
        # Quarterly: index of dates, values
        q = pick(q_inc, q_tags); a = pick(a_inc, a_tags)
        # quarterly: yfinance returns transposed; columns = dates
        # actually pick returns the row for given tag — its index are the date columns
        q_series = q.copy(); q_series.index = pd.to_datetime(q_series.index, errors='coerce')
        q_series = q_series[~q_series.index.isna()].sort_index()
        a_series = a.copy(); a_series.index = pd.to_datetime(a_series.index, errors='coerce')
        a_series = a_series[~a_series.index.isna()].sort_index()

        rec: dict = {'n_q': len(q_series), 'n_a': len(a_series)}

        # QoQ and YoY single-Q from quarterly if 5+ quarters available
        if len(q_series) >= 2:
            rec['q_now']    = float(q_series.iloc[-1])
            rec['q_prev_q'] = float(q_series.iloc[-2])
            rec['qoq']      = _sym(rec['q_now'], rec['q_prev_q'])
        if len(q_series) >= 5:
            rec['q_prev_yr'] = float(q_series.iloc[-5])
            rec['yoy_q']     = _sym(rec['q_now'], rec['q_prev_yr'])

        # Annual YoY (and 2y-CAGR)
        if len(a_series) >= 2:
            rec['a_now']    = float(a_series.iloc[-1])
            rec['a_prev']   = float(a_series.iloc[-2])
            rec['yoy_a']    = _sym(rec['a_now'], rec['a_prev'])
        if len(a_series) >= 3:
            rec['a_prev2']  = float(a_series.iloc[-3])
            rec['yoy_a_prior'] = _sym(rec['a_prev'], rec['a_prev2'])
            rec['accel_a'] = rec['yoy_a'] - rec['yoy_a_prior']

        # LTM-non-overlapping from quarterly if 8+ quarters available
        if len(q_series) >= 8:
            ltm_now = float(q_series.iloc[-4:].sum())
            ltm_prev = float(q_series.iloc[-8:-4].sum())
            rec['ltm_now'] = ltm_now; rec['ltm_prev'] = ltm_prev
            rec['ltm_chg'] = _sym(ltm_now, ltm_prev)

        out[label] = rec

    # Valuation snapshot
    out['info'] = {k: info.get(k) for k in
                   ('marketCap','priceToBook','priceToSalesTrailing12Months',
                    'enterpriseToEbitda','trailingPE','currentPrice',
                    'enterpriseValue','totalCash','totalDebt','sharesOutstanding',
                    'currency')}
    out['name'] = info.get('longName') or info.get('shortName') or ''
    out['sector'] = info.get('sector') or ''
    out['industry'] = info.get('industry') or ''
    return out


def flatten_rows(results: list) -> pd.DataFrame:
    rows = []
    for r in results:
        if not r or 'error' in r: continue
        row = {'ticker': r['ticker'],
               'name': r.get('name',''),
               'sector': r.get('sector',''),
               'industry': r.get('industry','')}
        info = r.get('info', {})
        for k,v in info.items(): row[f'info_{k}'] = v
        for met in ('revenue','ebitda','net_inc','eps'):
            d = r.get(met, {})
            for k,v in d.items(): row[f'{met}_{k}'] = v
        rows.append(row)
    return pd.DataFrame(rows).set_index('ticker') if rows else pd.DataFrame()


def main():
    uk = pd.read_csv('universe_wider.csv', index_col=0)
    uk = uk[uk['_country']=='United Kingdom']
    print(f"Universe: {len(uk)} UK tickers")
    tickers = uk.index.astype(str).tolist()
    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(fetch_one, t): t for t in tickers}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                r = fut.result(timeout=60)
            except Exception as exc:
                r = {'ticker': futs[fut], 'error': f'worker exc: {exc}'}
            results.append(r)
            if i % 25 == 0 or i == len(tickers):
                el = time.time() - t0
                ok = sum(1 for x in results if x and 'error' not in x)
                print(f"  {i}/{len(tickers)}  ({i/el:.1f}/s)  valid={ok}")
            time.sleep(UA_SLEEP / WORKERS)
    print(f"done in {time.time()-t0:.0f}s")

    df = flatten_rows(results)
    df.to_csv(OUTDIR / 'growth_uk.csv')
    print(f"wrote {OUTDIR/'growth_uk.csv'} with {len(df)} rows")

    # Quick summary: how many cleared at least quarterly QoQ + annual YoY?
    if not df.empty:
        for met in ('revenue','ebitda','net_inc'):
            sub = df[df[f'{met}_qoq'].notna() & df[f'{met}_yoy_a'].notna()]
            print(f"  {met}: {len(sub)} have both QoQ and annual YoY data")


if __name__ == '__main__':
    main()
