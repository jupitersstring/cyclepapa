"""Fill NaN gaps in per-country *_yartseva.csv files using yfinance `info`
as a secondary source.

Background. Our primary extraction (yartseva_db.py) computes every
ratio from raw quarterly + annual statements, which is the most
accurate path but suffers from:
  - yfinance row-name drift between releases (e.g. EBITDA missing
    because the alias list didn't catch this quarter's row label)
  - semi-annual reporters with sparse quarterly tables
  - negative EBIT / negative equity making ratios undefined

yfinance's `info` dict separately exposes provider-computed ratios
(`enterpriseToEbitda`, `priceToBook`, `ebitdaMargins`, etc.) and
canonical levels (`totalDebt`, `totalCash`, `ebitda`, `freeCashflow`).
We use those as fallbacks ONLY when our own extraction returned NaN
— primary numbers are never overwritten, since the info-derived ratios
sometimes use shifted or annualised periods.

Usage:
    python fill_fundamentals_gaps.py                  # all files, gap rows only
    python fill_fundamentals_gaps.py --max 500        # cap rows per file
    python fill_fundamentals_gaps.py --workers 8      # parallelism
    python fill_fundamentals_gaps.py --files ca_yartseva.csv us_largecap_yartseva.csv
"""
from __future__ import annotations
import argparse
import glob
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd


# Fields whose presence we evaluate when deciding "is this row a gap row?"
CRITICAL_FIELDS = [
    'pb', 'p_e', 'p_s', 'ev_ebitda', 'ev_ebit', 'ev_sales',
    'ebitda_margin', 'gross_margin', 'fcf_yield',
    'net_debt_ebitda', 'roce',
]


def _safe_float(v):
    try:
        if v is None:
            return None
        f = float(v)
        if not np.isfinite(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


import threading

# Global pause-token: when any worker sees a rate-limit error, it bumps the
# pause horizon and every worker stalls until that time passes. Cooperative
# rate-limit handling for the parallel fetcher.
_PAUSE_UNTIL = 0.0
_PAUSE_LOCK = threading.Lock()


def _wait_if_paused():
    global _PAUSE_UNTIL
    while True:
        remaining = _PAUSE_UNTIL - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 5.0))


def _signal_rate_limit(seconds: float = 30.0):
    global _PAUSE_UNTIL
    with _PAUSE_LOCK:
        _PAUSE_UNTIL = max(_PAUSE_UNTIL, time.time() + seconds)


def fetch_info(symbol: str, attempts: int = 4, per_call_delay: float = 0.20) -> dict | None:
    """Fetch yfinance Ticker(symbol).info with retry on transient errors and
    cooperative rate-limit backoff across workers."""
    import yfinance as yf
    _wait_if_paused()
    for i in range(attempts):
        try:
            time.sleep(per_call_delay)
            info = yf.Ticker(symbol).info
            return info or {}
        except Exception as e:
            msg = str(e)
            transient = ("401" in msg or "429" in msg or "Crumb" in msg
                         or "Too Many Requests" in msg or "Rate limit" in msg
                         or "YFRateLimitError" in msg)
            if transient:
                # Bump the global pause and back off; longer each retry.
                _signal_rate_limit(seconds=30.0 + 30.0 * i)
                _wait_if_paused()
                if i < attempts - 1:
                    continue
            return None
    return None


def apply_fallbacks(row: pd.Series, info: dict) -> dict[str, float]:
    """Return a dict of {field: value} to PATCH the row.

    Only fills NaN cells in `row`. Primary-extracted values are never
    overwritten. Skips info values that look like data errors (e.g.
    P/B > 100 or negative ratios).
    """
    out: dict[str, float] = {}

    def patch(field: str, info_key: str, sanity=lambda x: True):
        if field not in row.index:
            return
        if pd.notna(row[field]):
            return  # primary value present — keep it
        v = _safe_float(info.get(info_key))
        if v is None or not sanity(v):
            return
        out[field] = v

    # Direct yfinance-info ratios
    patch('pb', 'priceToBook', sanity=lambda x: 0 < x < 100)
    patch('p_e', 'trailingPE', sanity=lambda x: 0 < x < 2000)
    if 'p_e' in out and out['p_e'] is None:
        patch('p_e', 'forwardPE', sanity=lambda x: 0 < x < 2000)
    patch('p_s', 'priceToSalesTrailing12Months', sanity=lambda x: 0 < x < 200)
    patch('ev_ebitda', 'enterpriseToEbitda', sanity=lambda x: x != 0 and abs(x) < 500)
    patch('ev_sales', 'enterpriseToRevenue', sanity=lambda x: x != 0 and 0 < x < 200)
    patch('ebitda_margin', 'ebitdaMargins', sanity=lambda x: -1 < x < 1)
    patch('gross_margin', 'grossMargins', sanity=lambda x: -1 < x < 1)

    # Derived fields - construct from info canonical levels
    market_cap = _safe_float(row.get('market_cap')) or _safe_float(info.get('marketCap'))
    ev = _safe_float(row.get('enterprise_value')) or _safe_float(info.get('enterpriseValue'))
    ebitda = _safe_float(row.get('ebitda_ttm')) or _safe_float(info.get('ebitda'))

    if 'fcf_yield' in row.index and pd.isna(row['fcf_yield']) and market_cap and market_cap > 0:
        fcf = _safe_float(info.get('freeCashflow'))
        if fcf is not None:
            y = fcf / market_cap
            if -2 < y < 2:
                out['fcf_yield'] = y

    if 'net_debt_ebitda' in row.index and pd.isna(row['net_debt_ebitda']) and ebitda:
        td = _safe_float(info.get('totalDebt'))
        tc = _safe_float(info.get('totalCash'))
        if td is not None and tc is not None and ebitda > 0:
            nde = (td - tc) / ebitda
            if -100 < nde < 100:
                out['net_debt_ebitda'] = nde

    if 'ev_ebit' in row.index and pd.isna(row['ev_ebit']) and ev:
        # Derive EBIT from EBITDA - D&A is not in info; instead approximate
        # via operatingCashflow proxy. Conservative: skip if both ev_ebitda and
        # operatingMargins missing. Use info["ebitda"] - 0 as upper bound proxy
        # ONLY when EBITDA equals EBIT (rare); otherwise leave NaN.
        # Better: use operatingMargins * totalRevenue as EBIT proxy.
        op_m = _safe_float(info.get('operatingMargins'))
        tr = _safe_float(info.get('totalRevenue'))
        if op_m is not None and tr is not None and op_m > 0:
            ebit_proxy = op_m * tr
            if ebit_proxy > 0:
                eve = ev / ebit_proxy
                if 0 < eve < 200:
                    out['ev_ebit'] = eve

    # ROCE proxy: when our primary extraction returned NaN (typically
    # because we couldn't compute invested capital cleanly), fall back
    # to returnOnEquity which is the closest proxy yfinance exposes.
    if 'roce' in row.index and pd.isna(row['roce']):
        roe = _safe_float(info.get('returnOnEquity'))
        if roe is not None and -1 < roe < 5:
            out['roce'] = roe

    # ebitda_margin: secondary fallback from operatingMargins
    if 'ebitda_margin' in row.index and pd.isna(row['ebitda_margin']) and 'ebitda_margin' not in out:
        op_m = _safe_float(info.get('operatingMargins'))
        if op_m is not None and -1 < op_m < 1:
            out['ebitda_margin'] = op_m  # operating margin as lower-bound proxy

    return out


def process_file(path: str, max_rows: int | None = None, workers: int = 8,
                 only_gap_rows: bool = True) -> tuple[int, int, int]:
    """Process one yartseva CSV: fill NaN gaps from yfinance info.

    Returns (rows_in_file, rows_fetched, fields_patched).
    """
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f'  {path}: read failed - {e}', file=sys.stderr)
        return (0, 0, 0)

    if 'symbol' not in df.columns:
        return (len(df), 0, 0)

    n_total = len(df)

    # Identify gap rows: at least one critical field is NaN
    if only_gap_rows:
        crit = [c for c in CRITICAL_FIELDS if c in df.columns]
        gap_mask = df[crit].isna().any(axis=1)
        targets = df[gap_mask].index.tolist()
    else:
        targets = df.index.tolist()

    if max_rows is not None:
        targets = targets[:max_rows]

    if not targets:
        print(f'  {path}: {n_total} rows, no gaps to fill', file=sys.stderr)
        return (n_total, 0, 0)

    print(f'  {path}: {n_total} rows, fetching {len(targets)} gap rows...', file=sys.stderr)

    # Pre-fetch all info dicts in parallel
    sym_to_info: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_info, df.at[i, 'symbol']): i for i in targets}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                info = fut.result()
            except Exception:
                info = None
            sym_to_info[df.at[i, 'symbol']] = info or {}

    # Apply patches
    patches_applied = 0
    fields_patched_total = 0
    for i in targets:
        sym = df.at[i, 'symbol']
        info = sym_to_info.get(sym)
        if not info:
            continue
        patch = apply_fallbacks(df.loc[i], info)
        if patch:
            for k, v in patch.items():
                df.at[i, k] = v
            patches_applied += 1
            fields_patched_total += len(patch)

    if patches_applied:
        df.to_csv(path, index=False)

    print(f'  {path}: {patches_applied}/{len(targets)} rows patched, '
          f'{fields_patched_total} fields filled', file=sys.stderr)
    return (n_total, len(targets), fields_patched_total)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--files', nargs='*', default=None,
                    help='specific yartseva CSVs to process (default: all)')
    ap.add_argument('--max', type=int, default=None,
                    help='cap rows per file (for testing)')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--all-rows', action='store_true',
                    help='process all rows, not just gap rows')
    args = ap.parse_args()

    if args.files:
        files = args.files
    else:
        files = sorted(set(glob.glob('*_yartseva.csv')))
    if not files:
        print('no *_yartseva.csv files found', file=sys.stderr)
        sys.exit(1)

    print(f'processing {len(files)} files, workers={args.workers}', file=sys.stderr)
    start = time.time()
    total_rows = 0
    total_fetched = 0
    total_patches = 0
    for f in files:
        rows, fetched, patches = process_file(
            f, max_rows=args.max, workers=args.workers,
            only_gap_rows=not args.all_rows,
        )
        total_rows += rows
        total_fetched += fetched
        total_patches += patches
    elapsed = time.time() - start
    print(f'\ndone in {elapsed:.0f}s: {total_rows:,} rows scanned, '
          f'{total_fetched:,} fetched, {total_patches:,} field-values filled',
          file=sys.stderr)


if __name__ == '__main__':
    main()
