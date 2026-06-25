"""Extract TRUE axis-level segment revenue from SEC 10-K XBRL filings via
edgartools. This is the data SEC's `companyfacts` JSON drops — the per-
segment values that companies report under dimensional axes like
srt:ProductOrServiceAxis, us-gaap:StatementBusinessSegmentsAxis,
srt:StatementGeographicalAxis.

Per ticker we extract the latest 10-K and pull every revenue fact carried
along these three axes. Output one parquet per ticker:
  .cache/segments/<safe_ticker>__segments.parquet

A .dead sentinel is written when a filing has no dimensional revenue
data (most non-multi-segment small caps).

Rate-limited at ~1 req/s to stay well below SEC's 10/s cap (each filing
involves multiple SEC HTTP calls: header + XBRL instance + linkbase).
"""
from __future__ import annotations
import argparse, os, time, json, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault('EDGAR_IDENTITY', 'cyclepapa screener research@example.com')

import pandas as pd
from edgar import Company  # noqa: E402

CACHE = Path('.cache/segments')
CACHE.mkdir(parents=True, exist_ok=True)

# The three segment axes that carry product/segment/geographic revenue
SEGMENT_AXES = (
    'srt:ProductOrServiceAxis',
    'us-gaap:StatementBusinessSegmentsAxis',
    'srt:StatementGeographicalAxis',
)

# Concepts that represent revenue (other forms exist but these are 90% of cases)
REVENUE_CONCEPTS = (
    'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
    'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax',
    'us-gaap:Revenues',
    'us-gaap:SalesRevenueNet',
    'us-gaap:SalesRevenueGoodsNet',
)


def _safe(t): return ''.join(c if c.isalnum() or c in '-_' else '_' for c in t)


def _outpath(ticker: str) -> Path: return CACHE / f'{_safe(ticker)}__segments.parquet'
def _deadpath(ticker: str) -> Path: return CACHE / f'{_safe(ticker)}__segments.dead'


def extract_one(ticker: str) -> tuple[str, int]:
    """Fetch latest 10-K, extract every (concept × axis × member × period)
    revenue fact. Returns ('ok' | 'empty' | 'error', n_rows_written)."""
    if _outpath(ticker).exists() or _deadpath(ticker).exists():
        return 'cached', 0
    try:
        c = Company(ticker)
        filing = c.get_filings(form='10-K').latest()
        if filing is None:
            _deadpath(ticker).touch()
            return 'empty', 0
        xbrl = filing.xbrl()
    except Exception:
        return 'error', 0

    rows = []
    for concept in REVENUE_CONCEPTS:
        for axis in SEGMENT_AXES:
            try:
                facts = xbrl.facts.query().by_concept(concept).by_dimension(axis).execute()
            except Exception:
                continue
            for f in facts:
                # Filter to facts that ACTUALLY carry the axis (sanity check)
                if not f.get('is_dimensioned'): continue
                rows.append({
                    'ticker': ticker,
                    'concept': concept,
                    'axis': axis,
                    'member': f.get('member'),
                    'member_label': f.get('dimension_member_label') or f.get('label'),
                    'period_start': f.get('period_start'),
                    'period_end': f.get('period_end'),
                    'period_type': f.get('period_type'),
                    'fiscal_year': f.get('fiscal_year'),
                    'fiscal_period': f.get('fiscal_period'),
                    'value': f.get('numeric_value'),
                    'currency': f.get('currency'),
                    'unit': f.get('unit_ref'),
                })
    if not rows:
        _deadpath(ticker).touch()
        return 'empty', 0
    df = pd.DataFrame(rows)
    try:
        df.to_parquet(_outpath(ticker), compression='snappy')
        return 'ok', len(df)
    except Exception:
        _deadpath(ticker).touch()
        return 'error', 0


def universe_us_tickers() -> list[str]:
    """Every ticker in the SEC company_tickers map (we already cached
    companyfacts for ~3,400 of them — those are the natural priority)."""
    with open('.cache/edgar/company_tickers.json') as f:
        raw = json.load(f)
    # Prioritise CIKs we've already cached companyfacts for
    have = {int(p.name.split('_')[1].split('.')[0])
            for p in Path('.cache/edgar').glob('CF_*.json.gz')}
    front, back = [], []
    seen = set()
    for r in raw.values():
        tkr = r['ticker'].upper()
        if tkr in seen: continue
        seen.add(tkr)
        cik = int(r['cik_str'])
        (front if cik in have else back).append(tkr)
    return front + back


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-tickers', type=int, default=4000)
    ap.add_argument('--sleep', type=float, default=0.05,
                    help='Per-worker sleep — tiny since we now have N parallel workers')
    ap.add_argument('--workers', type=int, default=8,
                    help='Concurrent edgartools sessions. SEC allows 10 req/s; we '
                         'use 8 workers each with a 0.05s delay = ~70-80 effective rps headroom.')
    ap.add_argument('--progress-every', type=int, default=50)
    args = ap.parse_args()

    universe = universe_us_tickers()
    todo = [t for t in universe
            if not _outpath(t).exists() and not _deadpath(t).exists()]
    print(f'Universe: {len(universe):,} US tickers')
    print(f'Already cached/dead: {len(universe) - len(todo):,}')
    print(f'To extract: {len(todo):,}')
    if not todo:
        return
    target = todo[:args.max_tickers]
    t0 = time.time()
    n_ok = n_empty = n_err = total_rows = 0
    counter_lock = threading.Lock()
    progress_counter = [0]

    def worker(tk):
        nonlocal n_ok, n_empty, n_err, total_rows
        status, n = extract_one(tk)
        with counter_lock:
            progress_counter[0] += 1
            i = progress_counter[0]
            if status == 'ok': n_ok += 1; total_rows += n
            elif status == 'empty': n_empty += 1
            elif status == 'error': n_err += 1
            if i % args.progress_every == 0:
                el = time.time() - t0
                rate = i / el if el > 0 else 0
                eta = (len(target) - i) / rate / 60 if rate > 0 else float('inf')
                print(f'  {i:>5,}/{len(target):,}  ok={n_ok:,} empty={n_empty:,} '
                      f'err={n_err:,} rows={total_rows:,} rate={rate:.2f}/s eta={eta:.0f}min',
                      flush=True)
        time.sleep(args.sleep)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(worker, target))

    print(f'\nFinal: ok={n_ok:,} empty={n_empty:,} err={n_err:,} '
          f'rows={total_rows:,} across {len(target):,} tickers')


if __name__ == '__main__':
    main()
