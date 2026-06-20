"""Orchestrate the 14 creative screeners against the cache.

Each existing screener has its own main() and produces a CSV under
results_<name>/. This launcher invokes each in subprocess so we can
capture errors and timing without polluting the namespace.

After all screeners finish, summarise output paths + row counts so
build_workbook_creative.py knows what to pull in.

Run: python run_creative_screeners.py [--min-mcap 50e6]
"""
from __future__ import annotations
import argparse, subprocess, sys, time
from pathlib import Path

# (Screener filename, output CSV path relative to repo, friendly label)
SCREENERS = [
    ('clean_topline_screener.py',         'results_clean_topline/screener.csv',     'Clean Top-Line'),
    ('operating_leverage_screener.py',    'results_op_leverage/screener.csv',        'Operating Leverage'),
    ('fcf_yield_screener.py',             'results_fcf_yield/screener.csv',          'FCF Yield'),
    ('multiple_compression_screener.py',  'results_multiple_compression/screener.csv','Multiple Compression'),
    ('ev_compression_screener.py',        'results_ev_compression/screener.csv',     'EV Compression'),
    ('ev_fcf_leverage_screener.py',       'results_ev_fcf_leverage/screener.csv',    'EV/FCF Leverage'),
    ('fiftytwo_week_high_screener.py',    'results_52wh/screener.csv',                '52-Week High'),
    ('flat_with_inflection_screener.py',  'results_flat_inflection/screener.csv',    'Flat + Inflection'),
    ('akre_compounder_screener.py',       'results_akre/screener.csv',                'Akre Compounder'),
    ('volatility_asymmetry_screener.py',  'results_volasym/screener.csv',             'Vol Asymmetry'),
    ('segment_inflection_screener.py',    'results_segment_inflection/screener.csv', 'Segment Inflection'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--min-mcap', type=float, default=200e6)
    ap.add_argument('--timeout', type=int, default=600,
                    help='Per-screener timeout in seconds.')
    args = ap.parse_args()

    print(f'Running {len(SCREENERS)} creative screeners (min-mcap=${args.min_mcap/1e6:.0f}M)\n')
    results = []
    for script, csv_path, label in SCREENERS:
        if not Path(script).exists():
            print(f'  skip {script:42s} (not found)')
            continue
        t0 = time.time()
        # Run with reasonable flags; not every screener takes --min-mcap, run with defaults
        # and tolerate non-zero exits (some screeners exit cleanly without finds).
        try:
            r = subprocess.run([sys.executable, script],
                               capture_output=True, text=True, timeout=args.timeout)
            ok = r.returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
            r = None
        el = time.time() - t0
        out_path = Path(csv_path)
        rows = 0
        if out_path.exists():
            try:
                import pandas as pd
                rows = sum(1 for _ in open(out_path)) - 1
            except Exception:
                rows = 0
        results.append((script, label, csv_path, ok, rows, el))
        status = 'OK' if ok else 'FAIL'
        print(f'  {label:24s} [{status}] {rows:>4} rows  {el:5.0f}s   -> {csv_path}')

    print('\n--- Summary ---')
    n_ok = sum(1 for _,_,_,ok,_,_ in results if ok)
    n_rows = sum(rows for _,_,_,ok,rows,_ in results if ok)
    print(f'  {n_ok}/{len(results)} screeners succeeded; {n_rows} total surviving rows')


if __name__ == '__main__':
    main()
